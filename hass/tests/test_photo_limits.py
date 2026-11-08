"""NB-AV-10 (H12) tests: an oversize, unsupported or unreadable photo gets one fixed reply naming the limit, and no
original, web copy or draft is left behind; an exactly 20 MiB photo is still accepted.

PhotoRepo harness (temp Git repo, private media root outside the repo), a fake photo source and the fixture
interpreter from test_photo_draft. Every bad image is built in memory. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_photo_limits -v
"""

import hashlib
import re
import unittest

from hass import conversation, media
from hass.conversation import Inbound
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_media_web import PNG_DATA, PNG_KEPT, SCAN, chunk, jpeg, png, seg, tiff
from hass.tests.test_photo_draft import ANSWER, JPG, PNG, FakePhotos, PhotoInterpreter
from hass.tests.test_set_photo import PhotoRepo, _settings

# The exact owner texts (pinned here in full so a reply edit is a visible test change).
TOO_LARGE = 'That photo is too big for me. Could you send a smaller copy, or a screenshot of it?'
UNSUPPORTED = "I can't use that kind of photo, so nothing was saved. Could you send a screenshot of it instead? On an iPhone you can also set Camera, then Formats, to Most Compatible."
UNREADABLE = "I couldn't read that photo safely, so nothing changed. Could you send it again as a screenshot?"
SIDEWAYS = "That photo is sideways and I can't turn it, so nothing changed. Could you send it again as a screenshot?"
EMPTY, INCOMPLETE = 'That photo came through empty. Could you send it again?', 'That photo only came through partly. Could you send it again?'
MANY = "Please send one photo at a time. I haven't saved any of these."
AUDIO = "That looks like a voice note. I can't understand voice notes yet, so nothing was saved. Could you type the change instead?"

BAD_IDAT = PNG_DATA[0][:-1] + bytes([PNG_DATA[0][-1] ^ 1])  # one CRC bit flipped
CASES = {  # name: (bytes, code, full reply)
    "empty": (b"", "empty", EMPTY),
    "20 MiB + 1": (JPG + b"\0" * (media.MAX_BYTES + 1 - len(JPG)), "too-large", TOO_LARGE),
    "gif": (b"GIF89a\x01\x00\x01\x00" + b"\0" * 32, "unsupported-type", UNSUPPORTED),
    "heic": (b"\x00\x00\x00\x18ftypheic" + b"\0" * 64, "unsupported-type", UNSUPPORTED),
    "pdf": (b"%PDF-1.4\n%fake\n%%EOF\n", "unsupported-type", UNSUPPORTED),
    "voice note (m4a)": (b"\x00\x00\x00\x1cftypM4A " + b"\0" * 64, "audio", AUDIO),
    "truncated jpeg": (JPG[:-2], "truncated", INCOMPLETE),
    "jpeg comment between scans": (jpeg(scan=SCAN[:-2] + seg(0xFE, b"GPS") + SCAN), "unreadable", UNREADABLE),
    "png bad crc": (media.KINDS["png"] + b"".join(PNG_KEPT) + BAD_IDAT + b"".join(PNG_DATA[1:]), "unreadable",
                    UNREADABLE),
    "png eXIf orientation 8": (png(chunk(b"eXIf", tiff("MM", 8))), "needs-rotation", SIDEWAYS),
    "png eXIf orientation 6 little-endian": (png(chunk(b"eXIf", tiff("II", 6))), "needs-rotation", SIDEWAYS),
}


class PhotoLimitsTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.photos, self.interp, self.out, self.n = FakePhotos(), PhotoInterpreter(), FixtureAdapter(), 0
        self.conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp,
                                              lambda: T0, photos=self.photos)

    def say(self, text="", attachments=1, pid=None):
        self.n += 1
        return self.conv.handle(Inbound(pid or f"m{self.n}", CHAT, OWNER, text, received_at=T0.isoformat(),
                                        attachments=attachments))

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def stored(self):
        """Every entry under originals/ or web/ (folders included)."""
        return sorted(str(p) for sub in ("originals", "web") for p in (self.repo.media / sub).glob("**/*")) + \
            [sub for sub in ("originals", "web") if (self.repo.media / sub).exists()]

    def disposition(self, pid):
        return self.conv.db.execute("SELECT disposition FROM messages WHERE provider_id = ?", (pid,)).fetchone()[0]

    def assertNothingKept(self):
        self.assertEqual((self.stored(), self.drafts(), self.interp.texts), ([], [], []))

    def test_each_refusal_replies_its_fixed_text_and_stores_or_drafts_nothing(self):
        for name, (data, code, reply) in CASES.items():
            with self.subTest(name):
                self.photos.data = data
                self.assertEqual(self.say(ANSWER, pid=name), f"photo-refused:{code}")
                self.assertEqual(self.disposition(name), f"photo-refused:{code}")
                self.assertEqual(self.replies(), [reply])
                self.assertNothingKept()

    def test_a_refused_photo_sent_again_or_with_an_approval_caption_is_refused_again(self):
        self.photos.data = CASES["png eXIf orientation 8"][0]
        for caption in ("", "yes", "approve all", ANSWER):
            with self.subTest(caption=caption):
                self.assertEqual(self.say(caption), "photo-refused:needs-rotation")
                self.assertEqual(self.replies(), [SIDEWAYS])
        self.assertEqual(self.say(pid="m1"), "duplicate")  # a redelivered provider id is not handled twice
        self.assertEqual(self.replies(), [])
        self.assertNothingKept()

    def test_refusal_leaves_a_waiting_draft_alone_and_a_good_photo_after_it_works(self):
        self.assertEqual(self.say(), "photo-draft")
        [waiting] = self.drafts()
        self.replies()
        self.photos.data = CASES["png bad crc"][0]
        self.assertEqual(self.say(), "photo-refused:unreadable")
        self.assertEqual(self.drafts(), [waiting])
        self.photos.data = PNG
        self.assertEqual(self.say(), "photo-draft")
        self.assertEqual(len(self.drafts()), 2)
        self.assertEqual(len(list((self.repo.media / "originals").glob("*/*.png"))), 1)

    def test_exactly_20_mib_photo_is_accepted_and_drafted(self):
        self.photos.data = JPG + b"\0" * (media.MAX_BYTES - len(JPG))
        self.assertEqual(len(self.photos.data), 20 * 1024 * 1024)
        self.assertEqual(self.say(), "photo-draft")
        [row] = self.drafts()
        sha = hashlib.sha256(self.photos.data).hexdigest()
        self.assertEqual((row["state"], row["code"]), ("needs-details", sha[:4]))
        self.assertTrue((self.repo.media / "originals" / sha[:2] / f"{sha}.jpg").is_file())

    def test_several_attachments_reply_many_and_fetch_nothing(self):
        for count in (2, 5):
            with self.subTest(count=count):
                self.assertEqual(self.say("yes", attachments=count), "attachment-many")
                self.assertEqual(self.replies(), [MANY])
        self.assertEqual(self.photos.calls, [])
        self.assertNothingKept()


class CheckPhotoTests(unittest.TestCase):
    def test_check_photo_returns_the_kind_of_the_fixtures(self):
        self.assertEqual((media.check_photo(JPG), media.check_photo(PNG)), ("jpeg", "png"))
        self.assertEqual(media.check_photo(bytearray(PNG)), "png")
        with self.assertRaises(TypeError): media.check_photo("not bytes")

    def test_check_photo_refuses_every_case_with_its_code(self):
        for name, (data, code, reply) in CASES.items():
            with self.subTest(name), self.assertRaises(media.Refused) as cm: media.check_photo(data)
            self.assertEqual((cm.exception.code, cm.exception.reply), (code, reply))

    def test_store_original_alone_still_refuses_as_before(self):
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        for name in ("empty", "20 MiB + 1", "gif", "heic", "truncated jpeg"):
            data, code, _ = CASES[name]
            with self.subTest(name), self.assertRaises(media.Refused) as cm: repo.store(data)
            self.assertEqual(cm.exception.code, code)
        self.assertFalse((repo.media / "originals").exists())
        # it never ran the web-copy filter: a sideways original is kept, and web_copy is what refuses it
        sha = repo.store(CASES["png eXIf orientation 8"][0])
        with self.assertRaises(media.Refused) as cm: media.web_copy(repo.media, sha)
        self.assertEqual(cm.exception.code, "needs-rotation")

    def test_replies_name_no_path_hash_or_byte_count_except_20_mb(self):
        for code, reply in media.REPLIES.items():
            with self.subTest(code):
                self.assertNotIn("/", reply)
                self.assertNotRegex(reply, r"[0-9a-f]{8}")
                self.assertEqual(re.findall(r"\d", reply.replace("20 MB", "")), [])  # no number but the 20 MB limit
        for name, (data, _, reply) in CASES.items():
            with self.subTest(name):
                self.assertNotIn(hashlib.sha256(data).hexdigest()[:8], reply)
        for reply, limit in ((TOO_LARGE, "smaller copy"), (UNREADABLE, "screenshot"),
                             (UNSUPPORTED, "Most Compatible"), (SIDEWAYS, "sideways"), (MANY, "one photo at a time")):
            self.assertIn(limit, reply)


if __name__ == "__main__":
    unittest.main()
