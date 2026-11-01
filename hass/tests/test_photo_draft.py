"""NB-AV-09 (H12) tests: a photo opens one needs-details product.set_photo draft; a later text (or the caption)
fills it; the same photo again while it waits adds no second draft.

PhotoRepo harness (temp Git repo + writer worktree, private media root outside the repo), a fake photo source and a
fixture interpreter. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_photo_draft -v
"""

import hashlib
import json
import os
import stat
import unittest

from hass import conversation, media
from hass.conversation import PHOTO_QUESTION, ConfigError, Inbound
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_set_photo import ALT, FIXTURES, PID, PhotoRepo, _settings

JPG = (FIXTURES / "pixel.jpg").read_bytes()
PNG = (FIXTURES / "pixel.png").read_bytes()
SHA, PNG_SHA = hashlib.sha256(JPG).hexdigest(), hashlib.sha256(PNG).hexdigest()
ANSWER = "lion's mane, jar of dried mushrooms"


class FakePhotos:
    def __init__(self, data=JPG):
        self.data, self.calls = data, []

    def fetch(self, provider_id, count):
        self.calls.append((provider_id, count))
        return [self.data] * count


class PhotoInterpreter:
    """Fixture: mapped texts answer the waiting needs-details draft (revises its code); anything else unsupported."""

    def __init__(self):
        self.mapping, self.texts = {ANSWER: {"id": PID, "imageAlt": ALT}}, []

    def interpret(self, text, pending):
        self.texts.append(text)
        if text not in self.mapping: return {"unsupported": "Sorry, I can't do that yet."}
        waiting = [p["code"] for p in pending if p["state"] == "needs-details"]
        return {"ops": [{"op": "product.set_photo", "args": dict(self.mapping[text])}],
                "revises": waiting[-1] if waiting else None}


def _photo_ids(row):
    return {c["args"].get("photo") for c in json.loads(row["ops_json"]) if c["op"] == "product.set_photo"} - {None}


class PhotoDraftTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.photos, self.interp, self.out, self.n = FakePhotos(), PhotoInterpreter(), FixtureAdapter(), 0
        self.conv = self.open()

    def open(self, photos="fake"):
        return conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp,
                                         lambda: T0, photos=self.photos if photos == "fake" else photos)

    def say(self, text="", attachments=0, pid=None):
        self.n += 1
        msg = Inbound(pid or f"m{self.n}", CHAT, OWNER, text, received_at=T0.isoformat(), attachments=attachments)
        return self.conv.handle(msg)

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def originals(self):
        root = self.repo.media / "originals"
        return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []

    def asked(self, code):
        return f"{PHOTO_QUESTION} Reply with the product and description (draft {code})."

    def test_photo_opens_one_needs_details_draft_and_stores_the_original_once(self):
        self.assertEqual(self.say(attachments=1), "photo-draft")
        [row] = self.drafts()
        self.assertEqual((row["state"], row["code"], row["summary"]), ("needs-details", SHA[:4], PHOTO_QUESTION))
        self.assertEqual(_photo_ids(row), {SHA})
        self.assertEqual(self.replies(), [self.asked(SHA[:4])])
        [original, _sidecar] = sorted(self.originals(), key=lambda p: p.suffix != ".jpg")
        self.assertEqual((original.name, stat.S_IMODE(os.stat(original).st_mode)), (f"{SHA}.jpg", 0o600))
        self.assertEqual((self.interp.texts, self.photos.calls), ([], [("m1", 1)]))

    def test_later_text_fills_the_draft_and_yes_sets_the_product_image(self):
        self.say(attachments=1)
        self.replies()
        self.interp.mapping["lion's mane"] = {"id": PID}  # a partial answer keeps the photo and asks again
        self.assertEqual(self.say("lion's mane"), "needs-details")
        self.replies()
        self.assertEqual([(d["state"], _photo_ids(d)) for d in self.drafts()], [("needs-details", {SHA})])
        self.assertEqual(self.say(ANSWER), "proposed")
        [row] = self.drafts()
        self.assertEqual((row["state"], row["code"]), ("proposed", SHA[:4]))
        self.assertEqual(_photo_ids(row), {SHA})
        [reply] = self.replies()
        self.assertTrue(reply.startswith(f"Draft {SHA[:4]}:"), reply)
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.drafts()[0]["state"], "applied")
        self.assertEqual(self.repo.product(PID)["image"], f"assets/products/photo-{SHA[:16]}.jpg")
        self.assertEqual(self.repo.product(PID)["imageAlt"], ALT)

    def test_caption_that_answers_proposes_in_one_message(self):
        self.assertEqual(self.say(ANSWER, attachments=1), "proposed")
        [row] = self.drafts()
        self.assertEqual((row["state"], row["code"]), ("proposed", SHA[:4]))
        replies = self.replies()
        self.assertEqual(replies[0], self.asked(SHA[:4]))
        self.assertTrue(replies[1].startswith(f"Draft {SHA[:4]}:"), replies)
        self.assertEqual(self.interp.texts, [ANSWER])

    def test_caption_is_never_a_keyword_or_command(self):
        self.say(ANSWER, attachments=1)
        self.replies()
        for i, caption in enumerate(["yes", f"yes {SHA[:4]}", "pause changes", "status", "\ufffc"]):
            with self.subTest(caption):
                self.photos.data = PNG if i == 0 else JPG
                expected = "unsupported" if i == 0 else "photo-duplicate"
                self.assertEqual(self.say(caption, attachments=1), expected)
        self.assertEqual([d["state"] for d in self.drafts()], ["proposed", "needs-details"])
        self.assertEqual(self.interp.texts, [ANSWER, "yes"])  # only the new photo's caption reached the interpreter
        self.assertIsNone(self.conv._paused())
        self.assertEqual(self.repo.product(PID)["image"], "assets/products/photo-product-001.webp")

    def test_same_photo_again_is_named_not_redrafted(self):
        self.say(attachments=1)
        self.replies()
        self.assertEqual(self.say(attachments=1), "photo-duplicate")
        self.assertEqual(self.replies(), [f"That photo is already in draft {SHA[:4]}. {PHOTO_QUESTION}"])
        self.say(ANSWER)
        self.replies()
        self.assertEqual(self.say(ANSWER, attachments=1), "photo-duplicate")  # still waiting as a proposal
        self.assertEqual(self.replies(), [f"That photo is already in draft {SHA[:4]}."])
        self.assertEqual((len(self.drafts()), len(self.originals())), (1, 2))
        self.assertEqual(self.interp.texts, [ANSWER])
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.say(attachments=1), "photo-draft")  # after it was applied: a new draft, new code
        old, new = self.drafts()
        self.assertEqual((old["state"], new["state"]), ("applied", "needs-details"))
        self.assertNotEqual(new["code"], old["code"])

    def test_several_attachments_and_refused_photos_store_and_draft_nothing(self):
        self.assertEqual(self.say(attachments=2), "attachment-many")
        self.assertEqual(self.replies(), ["One photo at a time, please; nothing was saved."])
        self.assertEqual(self.photos.calls, [])
        for data, code in ((b"", "empty"), (b"GIF89a\x01\x00\x01\x00", "unsupported-type"), (JPG[:-2], "truncated")):
            with self.subTest(code):
                self.photos.data = data
                self.assertEqual(self.say(ANSWER, attachments=1), "photo-refused")
                self.assertEqual(self.replies(), [media.REPLIES[code]])
        self.assertEqual((self.drafts(), self.originals(), self.interp.texts), ([], [], []))

    def test_fill_naming_another_photo_is_refused_and_no_cancels(self):
        self.say(attachments=1)
        self.replies()
        self.interp.mapping["other"] = {"id": PID, "imageAlt": ALT, "photo": PNG_SHA}
        self.assertEqual(self.say("other"), "photo-mismatch")
        self.assertEqual(self.replies(), ["That draft is for another photo."])
        [row] = self.drafts()
        self.assertEqual((row["state"], _photo_ids(row)), ("needs-details", {SHA}))
        self.interp.mapping["same"] = {"id": PID, "imageAlt": ALT, "photo": SHA}  # naming its own photo is fine
        self.assertEqual(self.say("same"), "proposed")
        self.replies()
        self.assertEqual(self.say(f"no {SHA[:4]}"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {SHA[:4]}; nothing changed."])
        self.assertEqual(self.say(attachments=1), "photo-draft")  # a cancelled draft no longer holds the photo
        self.assertEqual([d["state"] for d in self.drafts()], ["rejected", "needs-details"])
        self.assertEqual(self.repo.product(PID)["image"], "assets/products/photo-product-001.webp")

    def test_photos_need_a_media_root(self):
        for bad in ({}, {"mediaRoot": ""}, {"mediaRoot": "  "}, {"mediaRoot": 7}):
            with self.subTest(bad):
                _settings(self.repo, **SETTINGS, **bad)
                with self.assertRaises(ConfigError) as ctx:
                    self.open()
                self.assertIn("mediaRoot must be set to use photos", str(ctx.exception))
        self.open(photos=None).db.close()  # without a photo source the setting is not needed

    def test_duplicate_delivery_does_not_fetch_again(self):
        self.assertEqual(self.say(attachments=1, pid="photo-1"), "photo-draft")
        self.assertEqual(self.say(attachments=1, pid="photo-1"), "duplicate")
        self.assertEqual((self.photos.calls, len(self.drafts()), len(self.replies())), ([("photo-1", 1)], 1, 1))


if __name__ == "__main__":
    unittest.main()
