"""AV2022-05 (H11/H12) tests: a voice note or other audio file (CAF, M4A/M4B, AMR) is recognised from its bytes and
gets one 'please type it' reply with nothing stored and no draft; every other unknown file keeps the camera advice.

Every sample is built in memory. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_media_audio -v
"""

import unittest

from hass import media
from hass.tests import test_photo_limits as limits
from hass.tests.test_photo_draft import ANSWER
from hass.tests.test_set_photo import PhotoRepo

AUDIO = "That looks like a voice note. I can't understand voice notes yet, so nothing was saved. Could you type the change instead?"
UNSUPPORTED = "I can't use that kind of photo, so nothing was saved. Could you send a screenshot of it instead? On an iPhone you can also set Camera, then Formats, to Most Compatible."

PAD = b"\0" * 64
AUDIO_SAMPLES = {
    "caf voice note": b"caff\x00\x01" + PAD,
    "m4a": b"\x00\x00\x00\x1cftypM4A " + PAD,
    "m4b": b"\x00\x00\x00\x1cftypM4B " + PAD,
    "amr": b"#!AMR\n" + PAD,
    "amr-wb": b"#!AMR-WB\n" + PAD,
}
NOT_AUDIO = {
    "heic": b"\x00\x00\x00\x18ftypheic" + PAD,
    "mp4 video": b"\x00\x00\x00\x18ftypisom" + PAD,
    "gif": b"GIF89a\x01\x00\x01\x00" + PAD,
    "pdf": b"%PDF-1.4\n%fake\n%%EOF\n",
    "plain text": b"please add lion's mane, M4A caff #!AMR",
    "ftyp brand at the wrong offset": b"\x00\x00\x00\x00\x1cftypM4A " + PAD,
    "lower-case m4a brand": b"\x00\x00\x00\x1cftypm4a " + PAD,
    "too short for a brand": b"\x00\x00\x00\x1cftyp",
    "half a brand": b"\x00\x00\x00\x1cftypM4",
}


class IsAudioTests(unittest.TestCase):
    def test_audio_bytes_are_refused_as_audio_with_the_exact_text(self):
        for name, data in AUDIO_SAMPLES.items():
            with self.subTest(name):
                self.assertTrue(media.is_audio(data))
                with self.assertRaises(media.Refused) as cm: media.check_photo(data)
                self.assertEqual((cm.exception.code, cm.exception.reply), ("audio", AUDIO))

    def test_other_unknown_files_keep_the_camera_advice(self):
        for name, data in NOT_AUDIO.items():
            with self.subTest(name):
                self.assertFalse(media.is_audio(data))  # short bytes: no IndexError
                with self.assertRaises(media.Refused) as cm: media.check_photo(data)
                self.assertEqual((cm.exception.code, cm.exception.reply), ("unsupported-type", UNSUPPORTED))

    def test_size_checks_come_first(self):
        self.assertFalse(media.is_audio(b""))
        big = AUDIO_SAMPLES["m4a"] + b"\0" * (media.MAX_BYTES + 1 - len(AUDIO_SAMPLES["m4a"]))
        for data, code in ((b"", "empty"), (big, "too-large")):
            with self.subTest(code), self.assertRaises(media.Refused) as cm: media.check_photo(data)
            self.assertEqual(cm.exception.code, code)
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        for data, code in ((b"", "empty"), (big, "too-large")):
            with self.subTest(f"store {code}"), self.assertRaises(media.Refused) as cm: repo.store(data)
            self.assertEqual(cm.exception.code, code)

    def test_store_original_refuses_audio_and_creates_nothing(self):
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        for name, data in AUDIO_SAMPLES.items():
            with self.subTest(name), self.assertRaises(media.Refused) as cm: repo.store(data)
            self.assertEqual((cm.exception.code, cm.exception.reply), ("audio", AUDIO))
        self.assertFalse((repo.media / "originals").exists())
        self.assertFalse((repo.media / "web").exists())


class VoiceNoteEndToEndTests(unittest.TestCase):
    """The PhotoLimitsTests harness, borrowed method by method so its own tests do not run twice here."""
    P = limits.PhotoLimitsTests
    setUp, say, replies, drafts, stored, disposition = P.setUp, P.say, P.replies, P.drafts, P.stored, P.disposition
    assertNothingKept = P.assertNothingKept

    def test_one_m4a_attachment_gets_one_audio_reply_and_nothing_else(self):
        self.photos.data = AUDIO_SAMPLES["m4a"]
        self.assertEqual(self.say(ANSWER, pid="voice"), "photo-refused:audio")
        self.assertEqual(self.disposition("voice"), "photo-refused:audio")
        self.assertEqual(self.replies(), [AUDIO])
        self.assertEqual(self.photos.calls, [("voice", 1)])
        self.assertNothingKept()  # no originals/web files, no draft, interpreter never called

    def test_every_audio_kind_and_any_caption_is_refused_the_same_way(self):
        for i, (name, data) in enumerate(AUDIO_SAMPLES.items()):
            for caption in ("", "yes", "approve all", "this is a photo"):
                with self.subTest(name, caption=caption):
                    self.photos.data = data
                    self.assertEqual(self.say(caption, pid=f"a{i}-{caption}"), "photo-refused:audio")
                    self.assertEqual(self.replies(), [AUDIO])
        self.assertEqual(self.say(pid="a0-"), "duplicate")  # a redelivered voice note is not answered twice
        self.assertEqual(self.replies(), [])
        self.assertNothingKept()

    def test_a_heic_photo_still_gets_the_camera_advice(self):
        self.photos.data = NOT_AUDIO["heic"]
        self.assertEqual(self.say(ANSWER), "photo-refused:unsupported-type")
        self.assertEqual(self.replies(), [UNSUPPORTED])
        self.assertNothingKept()


if __name__ == "__main__":
    unittest.main()
