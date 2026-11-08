"""RF1050-23 tests: an ftyp box whose aligned compatible-brand list names an audio brand gets the voice-note reply.

Every sample is a few synthetic header bytes built in memory. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_media_audio_compatible -v
"""

import unittest

from hass import media
from hass.tests import test_photo_limits as limits
from hass.tests.test_media import JPEG, PNG
from hass.tests.test_photo_draft import ANSWER
from hass.tests.test_set_photo import PhotoRepo

AUDIO = "That looks like a voice note. I can't understand voice notes yet, so nothing was saved. Could you type the change instead?"
PAD = b"\0" * 64


def ftyp(major=b"isom", minor=b"\0\0\0\0", brands=(), size=None, trailer=b""):
    body = major + minor + b"".join(brands)
    size = len(body) + 8 if size is None else size
    return size.to_bytes(4, "big") + b"ftyp" + body + trailer


class CompatibleBrandTests(unittest.TestCase):
    def test_compatible_brand_after_generic_major(self):
        probe = bytes.fromhex("000000186674797069736f6d0000000069736f6d4d344120")
        self.assertEqual(probe, ftyp(brands=(b"isom", b"M4A ")))
        cases = {"probe": probe}
        for b in media.AUDIO_BRANDS:
            cases[f"first {b}"] = ftyp(brands=(b, b"isom"))
            cases[f"later {b}"] = ftyp(brands=(b"isom", b"mp42", b"avc1", b"iso2", b))
        cases["mp42 major + noise"] = ftyp(b"mp42", brands=(b"avc1", b"iso6", b"3gp4"))
        for name, data in cases.items():
            with self.subTest(name):
                self.assertTrue(media.is_audio(data))
                with self.assertRaises(media.Refused) as cm: media.check_photo(data)
                self.assertEqual((cm.exception.code, cm.exception.reply), ("audio", AUDIO))

    def test_box_bounds_and_alignment(self):
        good = ftyp(brands=(b"M4A ",))
        bad = {f"len {n}": good[:n] for n in range(16)}
        bad.update({
            "size 0": ftyp(brands=(b"M4A ",), size=0), "size 1": ftyp(brands=(b"M4A ",), size=1),
            "size 15": ftyp(brands=(b"M4A ",), size=15),
            "end beyond bytes": ftyp(brands=(b"M4A ",), size=len(good) + 4),
            "body not multiple of 4": ftyp(brands=(b"M4A ", b"xy"), size=len(good) + 2),
            "no compatible entries": ftyp(),
            "wrong box type": good[:4] + b"moov" + good[8:],
        })
        for name, data in bad.items():
            with self.subTest(name):
                self.assertFalse(media.is_audio(data))
                with self.assertRaises(media.Refused) as cm: media.check_photo(data)
                self.assertNotEqual(cm.exception.code, "audio")

    def test_no_substring_minor_version_or_trailer_match(self):
        cases = {
            "minor version": ftyp(minor=b"M4A ", brands=(b"isom",)),
            "straddling entries": ftyp(brands=(b"xM4A", b" yyy")),
            "after declared end": ftyp(brands=(b"isom",), trailer=b"M4A "),
        }
        for name, data in cases.items():
            with self.subTest(name): self.assertFalse(media.is_audio(data))
        self.assertTrue(media.is_audio(ftyp(brands=(b"isom", b"M4A "), trailer=b"M4A trailing bytes" + PAD)))

    def test_existing_formats_and_non_audio_unchanged(self):
        for name, data in {
            "m4a major": b"\x00\x00\x00\x1cftypM4A " + PAD, "caf": b"caff" + PAD, "amr": b"#!AMR\n" + PAD,
            "wav": b"RIFF\x24\x08\x00\x00WAVEfmt " + PAD, "mp3": b"ID3\x04" + PAD, "ogg": b"OggS" + PAD,
            "flac": b"fLaC" + PAD,
        }.items():
            with self.subTest(name): self.assertTrue(media.is_audio(data))
        for name, data in {
            "jpeg": JPEG, "png": PNG, "isom": b"\x00\x00\x00\x18ftypisom" + PAD, "mp42": b"\x00\x00\x00\x18ftypmp42" + PAD,
            "heic": b"\x00\x00\x00\x18ftypheic" + PAD, "heic compat only": ftyp(b"heic", brands=(b"mif1", b"heic")),
        }.items():
            with self.subTest(name): self.assertFalse(media.is_audio(data))


class CompatibleAudioConversationTests(unittest.TestCase):
    P = limits.PhotoLimitsTests
    setUp, say, replies, drafts, stored, disposition = P.setUp, P.say, P.replies, P.drafts, P.stored, P.disposition
    assertNothingKept = P.assertNothingKept

    def test_owner_compatible_audio_caption_and_duplicate(self):
        self.photos.data = ftyp(brands=(b"isom", b"M4A "))
        self.assertEqual(self.say("approve all", pid="cmp"), "photo-refused:audio")
        self.assertEqual(self.disposition("cmp"), "photo-refused:audio")
        self.assertEqual(self.replies(), [AUDIO])
        self.assertEqual(self.say("approve all", pid="cmp"), "duplicate")
        self.assertEqual(self.replies(), [])
        self.assertNothingKept()


if __name__ == "__main__":
    unittest.main()
