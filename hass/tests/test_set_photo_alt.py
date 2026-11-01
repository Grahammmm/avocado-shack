"""RF1730-2 (H10): product.set_photo refuses an imageAlt that is a file name, camera name, placeholder, the photo id or too short.

Reuses the test_set_photo WriterRepo harness (temp Git repo, fixture media store outside it). No live service, no network.
"""

import unittest

from hass.ops.photos import ALT_REPLY
from hass.tests.test_set_photo import PID, SetPhotoTestCase, _photo, _settings

REPLY = ("imageAlt should say what the photo shows (for example \"Hass avocados in a wooden crate\"), "
         "not a file name or placeholder")


class SetPhotoAltTests(SetPhotoTestCase):
    def refused_alt(self, alt):
        before = self.repo.product(PID)
        result = self.rejected("refused", _photo(PID, self.jpg, alt))
        self.assertEqual(result["reason"], REPLY, alt)
        self.assertEqual(self.repo.product(PID), before)
        self.assertFalse((self.repo.wt / self.target(self.jpg)).exists())  # no photo file queued or written

    def test_reply_is_the_fixed_owner_reply(self):
        self.assertEqual(ALT_REPLY, REPLY)

    def test_file_and_camera_names_are_refused(self):
        for alt in ("IMG_4021.JPG", "pxl_20261030_101500.jpg", "DSC 0042", "dscn0042", "Photo-123", "image_07",
                    "Avocado logo.png", "crate.HEIC", "scan.tiff", "x.webp"):
            with self.subTest(alt=alt):
                self.refused_alt(alt)

    def test_placeholder_words_are_refused_in_any_case_or_spacing(self):
        for alt in ("Photo", "IMAGE", "N/A", "TBD", "picture", "PIC", "img", "Product Photo", "alt", "na", "None",
                    "todo", "product"):
            with self.subTest(alt=alt):
                self.refused_alt(alt)
        for alt in (" image ", "TBD "):  # outer spacing: Arg("text") refuses it before the op runs; nothing written
            with self.subTest(alt=alt):
                result = self.rejected("invalid", _photo(PID, self.jpg, alt))
                self.assertTrue(any("imageAlt: leading/trailing whitespace" in p for p in result["problems"]), result)

    def test_photo_id_in_the_alt_is_refused(self):
        for alt in (self.jpg[:12], f"Crate {self.jpg[:12]} front", self.jpg[:12].upper(), self.jpg):
            with self.subTest(alt=alt):
                self.refused_alt(alt)

    def test_fewer_than_three_letters_is_refused(self):
        for alt in ("ok", "A1", "12345", "a-b", "Ab 99"):
            with self.subTest(alt=alt):
                self.refused_alt(alt)

    def test_real_descriptions_are_accepted(self):
        for alt in ("Avocados.", "Photo of Hass avocados in a crate", "Avocado logo png", "Image of a lime tree",
                    "Pic of 12 avocados"):
            with self.subTest(alt=alt):
                self.repo.run(_photo(PID, self.jpg, alt))
                self.assertEqual(self.repo.product(PID)["imageAlt"], alt)
                self.assertTrue((self.repo.wt / self.target(self.jpg)).is_file())

    def test_alt_refusal_comes_before_the_media_store_is_read(self):
        _settings(self.repo)  # mediaRoot unset
        self.refused_alt("IMG_4021.JPG")
        self.assertEqual(self.rejected("refused", _photo(PID, self.jpg))["reason"], "photo store is not configured")


if __name__ == "__main__":
    unittest.main()
