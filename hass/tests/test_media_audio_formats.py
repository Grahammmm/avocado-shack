"""AVB-11 (H11) tests: WAV, MP3 (ID3 tag or MPEG frame sync), Ogg, FLAC, M4P and the 3GPP audio brands an MMS voice
message uses get the voice-note reply (code `audio`); JPEG/PNG photos, HEIC, RIFF video/WebP, MP4 video and tiny
inputs keep their current result.

Every sample is a few synthetic header bytes built in memory; no real recording. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_media_audio_formats -v
"""

import unittest

from hass import media
from hass.tests import test_photo_limits as limits
from hass.tests.test_media import JPEG, PNG
from hass.tests.test_photo_draft import ANSWER
from hass.tests.test_set_photo import PhotoRepo

PAD = b"\0" * 64
NEW_AUDIO = {
    "wav": b"RIFF\x24\x08\x00\x00WAVEfmt " + PAD,
    "id3 mp3": b"ID3\x04\x00\x00\x00\x00\x00\x00" + PAD,
    "frame-sync mp3 FF FB": b"\xff\xfb\x90\x64" + PAD,
    "frame-sync mpeg-2 layer 3 FF F3": b"\xff\xf3\x48\xc4" + PAD,
    "frame-sync layer 2 FF FD": b"\xff\xfd\x90\x64" + PAD,
    "ogg opus": b"OggS\x00\x02" + PAD,
    "flac": b"fLaC\x00\x00\x00\x22" + PAD,
    "m4p": b"\x00\x00\x00\x20ftypM4P " + PAD,
    **{f"3gpp {b}": b"\x00\x00\x00\x18ftyp" + b.encode() + PAD for b in ("3gp4", "3gp5", "3gp6", "3gr6", "3g2a")},
}
STILL_UNSUPPORTED = {
    "heic": b"\x00\x00\x00\x18ftypheic" + PAD,
    "riff avi": b"RIFF\x24\x08\x00\x00AVI LIST" + PAD,
    "riff webp": b"RIFF\x24\x08\x00\x00WEBPVP8 " + PAD,
    "riff wave lower-case": b"RIFF\x24\x08\x00\x00wave" + PAD,
    "mp4 video isom": b"\x00\x00\x00\x18ftypisom" + PAD,
    "mp4 video mp42": b"\x00\x00\x00\x18ftypmp42" + PAD,
    "aac adts FF F1 (layer bits zero)": b"\xff\xf1\x50\x80" + PAD,
    "one FF byte": b"\xff",
    "FF then a non-sync byte": b"\xff\x00" + PAD,
    "ID3 not at the start": b"\x00ID3" + PAD,
}


class NewAudioFormatTests(unittest.TestCase):
    def test_each_new_audio_header_is_refused_as_audio_with_the_exact_text(self):
        for name, data in NEW_AUDIO.items():
            with self.subTest(name):
                self.assertTrue(media.is_audio(data))
                self.assertIsNone(media.sniff(data))
                with self.assertRaises(media.Refused) as cm: media.check_photo(data)
                self.assertEqual((cm.exception.code, cm.exception.reply), ("audio", limits.AUDIO))

    def test_store_original_refuses_each_new_audio_header_and_creates_nothing(self):
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        for name, data in NEW_AUDIO.items():
            with self.subTest(name), self.assertRaises(media.Refused) as cm: repo.store(data)
            self.assertEqual((cm.exception.code, cm.exception.reply), ("audio", limits.AUDIO))
        self.assertFalse((repo.media / "originals").exists())
        self.assertFalse((repo.media / "web").exists())

    def test_non_audio_keeps_unsupported_type(self):
        for name, data in STILL_UNSUPPORTED.items():
            with self.subTest(name):
                self.assertFalse(media.is_audio(data))
                with self.assertRaises(media.Refused) as cm: media.check_photo(data)
                self.assertEqual((cm.exception.code, cm.exception.reply), ("unsupported-type", limits.UNSUPPORTED))

    def test_empty_bytes_are_not_audio_and_stay_empty(self):
        self.assertFalse(media.is_audio(b""))  # no IndexError
        with self.assertRaises(media.Refused) as cm: media.check_photo(b"")
        self.assertEqual(cm.exception.code, "empty")


class PhotosUnchangedTests(unittest.TestCase):
    def test_the_frame_sync_rule_never_matches_a_jpeg_start(self):
        for head in (b"\xff\xd8", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1"):
            with self.subTest(head=head):
                self.assertNotIn(head[1] & 0xE6, (0xE2, 0xE4, 0xE6))
                self.assertFalse(media.is_audio(head))

    def test_real_jpeg_and_png_are_still_photos(self):
        for kind, data in (("jpeg", JPEG), ("png", PNG)):
            with self.subTest(kind):
                self.assertFalse(media.is_audio(data))
                self.assertEqual(media.check_photo(data), kind)
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        self.assertRegex(repo.store(JPEG), r"^[0-9a-f]{64}$")  # accepted and stored under its sha256

    def test_a_cut_off_jpeg_header_is_still_truncated_not_audio(self):
        data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + PAD
        self.assertFalse(media.is_audio(data))
        with self.assertRaises(media.Refused) as cm: media.check_photo(data)
        self.assertEqual(cm.exception.code, "truncated")


class WavVoiceNoteConversationTests(unittest.TestCase):
    """The PhotoLimitsTests harness, borrowed method by method so its own tests do not run twice here."""
    P = limits.PhotoLimitsTests
    setUp, say, replies, drafts, stored, disposition = P.setUp, P.say, P.replies, P.drafts, P.stored, P.disposition
    assertNothingKept = P.assertNothingKept

    def test_owner_wav_attachment_gets_the_audio_reply_and_nothing_else(self):
        self.photos.data = NEW_AUDIO["wav"]
        self.assertEqual(self.say(ANSWER, pid="wav"), "photo-refused:audio")
        self.assertEqual(self.disposition("wav"), "photo-refused:audio")
        self.assertEqual(self.replies(), [limits.AUDIO])
        self.assertNothingKept()  # no originals/web files, no draft, interpreter never called

    def test_ogg_and_3gpp_with_an_approval_caption_draft_nothing_and_a_redelivery_is_not_answered_twice(self):
        for pid, data in (("ogg", NEW_AUDIO["ogg opus"]), ("mms", NEW_AUDIO["3gpp 3gp5"])):
            with self.subTest(pid):
                self.photos.data = data
                self.assertEqual(self.say("approve all", pid=pid), "photo-refused:audio")
                self.assertEqual(self.replies(), [limits.AUDIO])
        self.assertEqual(self.say(pid="ogg"), "duplicate")
        self.assertEqual(self.replies(), [])
        self.assertNothingKept()


if __name__ == "__main__":
    unittest.main()
