"""AV2152-04 (H12) tests: a message with 2 to 4 photos opens one coded needs-details draft per photo, in the order sent; every
photo is checked before any is stored; the caption is never read; 5 or more are refused without a fetch.

PhotoRepo harness (temp Git repo, private media root), a batch photo source, the fixture interpreter and a recorded label
transport. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_photo_batch -v
"""

import hashlib
import json
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, media, voice
from hass.conversation import FETCH_FAILED, PHOTO_QUESTION, AttachmentPending, Inbound
from hass.fixture_chat import FixtureAdapter
from hass.label_reader import LabelReader
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_editor import git
from hass.tests.test_label_reader import LION, URL, MODEL, Transport, recorded
from hass.tests.test_media_web import jpeg, seg
from hass.tests.test_photo_limits import CASES, EMPTY, SIDEWAYS, TOO_LARGE, UNSUPPORTED
from hass.tests.test_photo_draft import ANSWER, JPG
from hass.tests.test_set_photo import ALT, PID, PhotoRepo, _settings

FOOTER = "Reply to each draft with its code, place and description."
NOT_READ = "I did not read the caption because there is more than one photo. "
NONE_SAVED = "Nothing from this message was saved."


def pic(i):
    """A distinct, valid JPEG per i (the comment segment is dropped from the web copy)."""
    return jpeg(seg(0xFE, f"photo {i}".encode()))


def _colliding():
    """Two valid photos whose sha256 starts with the same four hex digits (found by search)."""
    seen = {}
    for i in range(100, 5000):
        data = pic(i)
        prefix = hashlib.sha256(data).hexdigest()[:4]
        if prefix in seen: return seen[prefix], data
        seen[prefix] = data


COLLIDING = _colliding()
PICS = [pic(i) for i in range(4)]
SHAS = [hashlib.sha256(p).hexdigest() for p in PICS]


class BatchPhotos:
    """Returns `items` (or the first `count` of the default four) and records every fetch."""

    def __init__(self, items=None):
        self.items, self.calls = items, []

    def fetch(self, provider_id, count):
        self.calls.append((provider_id, count))
        if isinstance(self.items, BaseException): raise self.items
        return list(PICS[:count]) if self.items is None else self.items


class CodeInterpreter:
    """Fixture: `<code> <answer>` answers that code's waiting draft (revises it); anything else is unsupported."""

    def __init__(self):
        self.texts = []

    def interpret(self, text, pending, **kw):
        self.texts.append(text)
        code, _, rest = text.partition(" ")
        if rest != ANSWER or code not in {p["code"] for p in pending}: return {"unsupported": "Sorry, I can't do that yet."}
        return {"ops": [{"op": "product.set_photo", "args": {"id": PID, "imageAlt": ALT}}], "revises": code}


class Base(unittest.TestCase):
    labels = None

    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.photos, self.interp, self.out, self.n = BatchPhotos(), CodeInterpreter(), FixtureAdapter(), 0
        self.conv = self.open()

    def open(self):
        conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp,
                                         lambda: T0, photos=self.photos, labels=self.labels)
        self.addCleanup(conv.db.close)
        return conv

    def say(self, text="", attachments=0, pid=None, **kw):
        self.n += 1
        return self.conv.handle(Inbound(pid or f"m{self.n}", CHAT, OWNER, text, received_at=T0.isoformat(),
                                        attachments=attachments), **kw)

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def originals(self):
        root = self.repo.media / "originals"
        return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []

    def kept(self):
        return (self.originals(), self.drafts(), self.interp.texts)

    def disposition(self, pid):
        return self.conv.db.execute("SELECT disposition FROM messages WHERE provider_id = ?", (pid,)).fetchone()[0]


class BatchDraftTests(Base):
    def test_two_three_four_photos_order_and_codes(self):
        for count in (2, 3, 4):
            with self.subTest(count=count):
                self.setUp()
                self.assertEqual(self.say(attachments=count), "photo-drafts")
                rows = self.drafts()
                self.assertEqual([r["code"] for r in rows], [s[:4] for s in SHAS[:count]])
                for i, row in enumerate(rows):
                    self.assertEqual((row["state"], row["summary"], json.loads(row["ops_json"])),
                                     ("needs-details", PHOTO_QUESTION, [{"op": "product.set_photo", "args": {"photo": SHAS[i]}}]))
                    self.assertEqual(self.conv._expiry(row), T0 + timedelta(seconds=self.conv.settings["approvalTtlSeconds"]))
                self.assertEqual(self.replies(), [f"Photo {i + 1} out of {count}: {PHOTO_QUESTION} Reply with the code {SHAS[i][:4]}."
                                                  for i in range(count)] + [FOOTER])
                self.assertEqual((self.photos.calls, len(self.originals()), self.interp.texts), ([("m1", count)], 2 * count, []))
                self.assertEqual(self.disposition("m1"), "photo-drafts")

    def test_five_plus_fetches_nothing(self):
        for count in (5, 10, 11):
            with self.subTest(count=count):
                self.assertEqual(self.say("yes", attachments=count), "attachment-many")
                self.assertEqual(self.replies(), ["Please send up to 4 photos per message; nothing was saved."])
        self.assertEqual((self.photos.calls, *self.kept()), ([], [], [], []))

    def test_each_bad_position_saves_none(self):
        bad = {name: CASES[name] for name in ("empty", "20 MiB + 1", "gif", "truncated jpeg", "png eXIf orientation 8")}
        for name, (data, code, reply) in bad.items():
            for position in (1, 2, 3):
                with self.subTest(name=name, position=position):
                    self.setUp()
                    items = [*PICS[:3]]
                    items[position - 1] = data
                    self.photos.items = items
                    self.assertEqual(self.say("yes", attachments=3), f"photo-refused:{code}")
                    self.assertEqual(self.replies(), [f"Photo {position} out of 3: {reply}\n{NONE_SAVED}"])
                    self.assertEqual(self.kept(), ([], [], []))

    def test_every_bad_position_is_named_and_the_first_code_is_the_disposition(self):
        self.photos.items = [b"", PICS[0], CASES["gif"][0], CASES["png eXIf orientation 8"][0]]
        self.assertEqual(self.say(attachments=4), "photo-refused:empty")
        self.assertEqual(self.replies(), [f"Photo 1 out of 4: {EMPTY}\nPhoto 3 out of 4: {UNSUPPORTED}\nPhoto 4 out of 4: {SIDEWAYS}\n{NONE_SAVED}"])
        self.assertEqual((self.kept(), self.disposition("m1")), (([], [], []), "photo-refused:empty"))

    def test_four_unsupported_photos_are_all_named_past_the_length_guard(self):
        gif = CASES["gif"][0]
        self.photos.items = [gif, gif, gif, gif]
        self.assertEqual(self.say(attachments=4), "photo-refused:unsupported-type")
        want = "\n".join([*(f"Photo {i} out of 4: {UNSUPPORTED}" for i in range(1, 5)), NONE_SAVED])
        self.assertGreater(len(want), voice.LONG_AFTER)  # the guard would have swapped this for SAFE_LINE
        self.assertEqual(self.replies(), [want])
        self.assertEqual(voice.check(want, long_ok=True), [])
        self.assertEqual(self.kept(), ([], [], []))

    def test_refused_photo_leaves_earlier_stored_files_and_drafts_alone(self):
        self.photos.items = [PICS[0]]
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        before = [(p, p.read_bytes()) for p in self.originals()]
        self.photos.items = [PICS[0], PICS[1], CASES["20 MiB + 1"][0]]
        self.assertEqual(self.say(attachments=3), "photo-refused:too-large")
        self.assertEqual(self.replies(), [f"Photo 3 out of 3: {TOO_LARGE}\n{NONE_SAVED}"])
        self.assertEqual(([(p, p.read_bytes()) for p in self.originals()], len(self.drafts())), (before, 1))

    def test_twenty_mb_per_photo_boundary(self):
        big = JPG + b"\0" * (media.MAX_BYTES - len(JPG))
        self.photos.items = [big, PICS[1]]
        self.assertEqual(self.say(attachments=2), "photo-drafts")
        self.assertEqual([r["code"] for r in self.drafts()], [hashlib.sha256(big).hexdigest()[:4], SHAS[1][:4]])
        self.setUp()
        self.photos.items = [PICS[0], CASES["20 MiB + 1"][0]]
        self.assertEqual(self.say(attachments=2), "photo-refused:too-large")
        self.assertEqual(self.kept(), ([], [], []))

    def test_exact_count_fetch_retry(self):
        for name, got in (("short", PICS[:1]), ("extra", PICS[:3]), ("non-byte", [PICS[0], "text"]), ("not a list", tuple(PICS[:2])),
                          ("error", OSError("bridge down"))):
            with self.subTest(name):
                self.setUp()
                self.photos.items = got
                with self.assertRaises(AttachmentPending): self.say(attachments=2, pid="m1")
                self.assertEqual((self.kept(), self.replies(), self.conv.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]),
                                 (([], [], []), [], 0))
                self.assertEqual(self.say(attachments=2, pid="m1", last_try=True), "attachment-failed")
                self.assertEqual((self.replies(), self.kept()), ([FETCH_FAILED], ([], [], [])))
        self.setUp()  # a good answer on the retry opens the drafts
        self.photos.items = PICS[:1]
        with self.assertRaises(AttachmentPending): self.say(attachments=2, pid="m1")
        self.photos.items = None
        self.assertEqual(self.say(attachments=2, pid="m1"), "photo-drafts")
        self.assertEqual(len(self.drafts()), 2)

    def test_duplicate_pending_product_and_within_batch(self):
        self.photos.items = [PICS[0]]
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        self.photos.items = [PICS[0], PICS[1], PICS[1], PICS[2]]
        self.assertEqual(self.say("yes", attachments=4), "photo-drafts")
        waiting = f"I already have that photo, and I'm waiting on you. {PHOTO_QUESTION}"
        self.assertEqual(self.replies(), [
            f"Photo 1 out of 4: {waiting}", f"Photo 2 out of 4: {PHOTO_QUESTION} Reply with the code {SHAS[1][:4]}.", f"Photo 3 out of 4: {waiting}",
            f"Photo 4 out of 4: {PHOTO_QUESTION} Reply with the code {SHAS[2][:4]}.", NOT_READ + FOOTER])
        self.assertEqual([r["code"] for r in self.drafts()], [SHAS[0][:4], SHAS[1][:4], SHAS[2][:4]])
        self.assertEqual(self.interp.texts, [])
        # a photo already waiting for a yes is named as today
        self.say(f"{SHAS[1][:4]} {ANSWER}")
        self.replies()
        self.photos.items = [PICS[1], PICS[3]]
        self.say(attachments=2)
        self.assertEqual(self.replies()[0], "Photo 1 out of 2: I already have that photo, and I'm waiting on you. It's in a change waiting for your yes.")
        # a photo that is an active product's picture is named, and opens no draft
        path = self.repo.wt / "hass" / "content" / "products.json"
        doc = json.loads(path.read_text("utf-8"))
        for product in doc["products"]:
            if product["id"] == PID: product.update(status="active", image=f"assets/products/photo-{hashlib.sha256(pic(8)).hexdigest()[:16]}.jpg")
        path.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        git(self.repo.wt, "commit", "-q", "-s", "-am", "point image")
        before = len(self.drafts())
        self.photos.items = [pic(8), pic(9)]
        self.say(attachments=2)
        first, second, _footer = self.replies()
        self.assertEqual(first, f"Photo 1 out of 2: That photo is already on {self.repo.product(PID)['name']}. To change that product, tell me what to change.")
        self.assertTrue(second.startswith("Photo 2 out of 2: " + PHOTO_QUESTION), second)
        self.assertEqual(len(self.drafts()), before + 1)

    def test_closed_draft_media_is_reused_with_a_new_code(self):
        self.say(attachments=2)
        self.replies()
        self.assertEqual(self.say(f"no {SHAS[0][:4]}"), "rejected")
        self.assertEqual(self.say(f"no {SHAS[1][:4]}"), "rejected")
        self.replies()
        self.assertEqual(self.say(attachments=2), "photo-drafts")
        rows = self.drafts()
        self.assertEqual([r["state"] for r in rows], ["rejected", "rejected", "needs-details", "needs-details"])
        self.assertEqual(len({r["code"] for r in rows}), 4)  # a code is never reissued
        self.assertEqual(len(self.originals()), 4)  # the same two originals and sidecars

    def test_short_code_collision_keeps_codes_unique(self):
        first, second = COLLIDING
        self.photos.items = [first, second]
        self.assertEqual(self.say(attachments=2), "photo-drafts")
        one, two = (hashlib.sha256(p).hexdigest() for p in COLLIDING)
        self.assertEqual(one[:4], two[:4])
        self.assertEqual([r["code"] for r in self.drafts()], [one[:4], two[:6]])
        self.assertEqual(len(self.replies()), 3)

    def test_batch_caption_never_interpreted(self):
        for caption in (ANSWER, "yes", f"yes {SHAS[0][:4]}", "status", "no", "\ufffc", "", " \ufffc "):
            with self.subTest(caption=caption):
                self.setUp()
                self.assertEqual(self.say(caption, attachments=2), "photo-drafts")
                *_, last = self.replies()
                self.assertEqual(last, (NOT_READ if caption.replace("\ufffc", "").strip() else "") + FOOTER)
                self.assertEqual(([r["state"] for r in self.drafts()], self.interp.texts), (["needs-details"] * 2, []))


    def test_answers_out_of_order_keep_photo_and_each_code_acts_alone(self):
        self.say(attachments=3)
        self.replies()
        a, b, c = (s[:4] for s in SHAS[:3])
        self.assertEqual(self.say("yes"), "no-target")  # yes cannot approve a needs-details draft
        self.replies()
        self.assertEqual({r["state"] for r in self.drafts()}, {"needs-details"})
        self.assertEqual(self.say(f"{c} {ANSWER}"), "proposed")
        self.assertEqual(self.say(f"{a} {ANSWER}"), "proposed")
        self.replies()
        photos = {r["code"]: json.loads(r["ops_json"])[0]["args"]["photo"] for r in self.drafts()}
        self.assertEqual(photos, {a: SHAS[0], b: SHAS[1], c: SHAS[2]})
        self.assertEqual({r["code"]: r["state"] for r in self.drafts()}, {a: "proposed", b: "needs-details", c: "proposed"})
        self.assertEqual(self.say(f"no {a}"), "rejected")
        self.assertEqual({r["code"]: r["state"] for r in self.drafts()}, {a: "rejected", b: "needs-details", c: "proposed"})

    def test_each_photo_counts_in_status_and_each_expires_alone(self):
        self.say(attachments=2)
        self.replies()
        self.say("status")
        [status] = self.replies()
        self.assertEqual(status.count("I'm waiting for details: " + PHOTO_QUESTION), 2)  # one line per photo
        self.assertEqual(sum(r["state"] == "needs-details" for r in self.drafts()), 2)
        self.conv.settings["approvalTtlSeconds"] = 60
        self.conv.db.execute("UPDATE drafts SET created_at = ? WHERE code = ?", ((T0 - timedelta(hours=2)).isoformat(), SHAS[0][:4]))
        self.say("yes")
        self.assertEqual({r["code"]: r["state"] for r in self.drafts()}, {SHAS[0][:4]: "expired", SHAS[1][:4]: "needs-details"})

    def test_batch_auth_and_replay(self):
        stranger = Inbound("s1", CHAT, "+15550000000", "", received_at=T0.isoformat(), attachments=3)
        self.assertEqual(self.conv.handle(stranger), "ignored")
        self.assertEqual((self.photos.calls, *self.kept()), ([], [], [], []))
        self.assertEqual(self.say(attachments=2, pid="p1"), "photo-drafts")
        self.replies()
        self.assertEqual(self.say(attachments=2, pid="p1"), "duplicate")  # same provider id: no second set
        self.assertEqual((self.replies(), len(self.drafts()), len(self.photos.calls)), ([], 2, 1))
        self.conv = self.open()  # a restart keeps the committed drafts and replays nothing
        self.assertEqual(self.say(attachments=2, pid="p1"), "duplicate")
        self.assertEqual((len(self.drafts()), len(self.photos.calls)), (2, 1))

    def test_unsupported_channel_still_replies_attachment_unsupported(self):
        conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp, lambda: T0)
        self.addCleanup(conv.db.close)
        self.assertEqual(conv.handle(Inbound("x1", CHAT, OWNER, "", received_at=T0.isoformat(), attachments=3)), "attachment-unsupported")

    def test_a_database_failure_rolls_back_every_row_and_reply(self):
        real = self.conv._photo_row
        calls = []

        def boom(sha, msg, now):
            calls.append(sha)
            if len(calls) == 2: raise RuntimeError("disk full")
            return real(sha, msg, now)
        with mock.patch.object(self.conv, "_photo_row", boom), self.assertRaises(RuntimeError): self.say(attachments=3, pid="m1")
        self.assertEqual((self.drafts(), self.replies(), self.conv.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]), ([], [], 0))
        self.assertEqual(self.say(attachments=3, pid="m1"), "photo-drafts")  # the originals were safe to keep: a retry works
        self.assertEqual(len(self.drafts()), 3)


class BatchLabelTests(Base):
    def setUp(self):
        self.transport = Transport(recorded(LION))
        self.labels = LabelReader(URL, MODEL, transport=self.transport)
        super().setUp()

    def test_labels_each_code_after_commit(self):
        held = []
        self.transport.probe = lambda: held.append(self.conv.db.in_transaction)
        self.assertEqual(self.say(attachments=3), "photo-drafts")
        self.assertEqual(held, [False] * 3)
        self.assertEqual(len(self.transport.calls), 3)
        for call in self.transport.calls: self.assertEqual(len(call[1]["messages"][0]["images"]), 1)
        replies = self.replies()
        line = "The label looks like"
        self.assertEqual([line in r for r in replies], [True, True, True, False])
        for i, row in enumerate(self.drafts()):
            self.assertTrue(row["summary"].startswith(PHOTO_QUESTION + " The label"), row["summary"])
            self.assertTrue(replies[i].startswith(f"Photo {i + 1} out of 3: {PHOTO_QUESTION} Reply with the code {row['code']}. The label"), replies[i])

    def test_first_enrichment_failure_does_not_stop_the_next_and_never_leaks(self):
        real, seen = self.conv._read_label, []

        def flaky(code, sha, reply_id):
            seen.append(code)
            if len(seen) == 1: raise RuntimeError("reader fell over")
            return real(code, sha, reply_id)
        with mock.patch.object(self.conv, "_read_label", flaky):
            self.assertEqual(self.say(attachments=2), "photo-drafts")
        first, second, footer = self.replies()
        self.assertNotIn("The label", first + footer)
        self.assertIn("The label", second)
        self.assertEqual(seen, [s[:4] for s in SHAS[:2]])
        self.photos.items = [PICS[3]]
        self.say(attachments=1)
        self.assertEqual(seen, [s[:4] for s in SHAS[:2]])  # the next message never re-runs an earlier job

    def test_duplicates_and_refused_photos_are_never_read(self):
        self.photos.items = [PICS[0], PICS[0]]
        self.say(attachments=2)
        self.assertEqual(len(self.transport.calls), 1)
        self.photos.items = [PICS[1], b""]
        self.say(attachments=2)
        self.assertEqual(len(self.transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
