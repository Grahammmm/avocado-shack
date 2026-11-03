"""RF1230-18 (H10): imageAlt refuses more camera default names (IMG_E, MVIMG_, PANO_, GoPro, DJI, _DSC, P1010001).

Reuses the test_set_photo WriterRepo harness (temp Git repo, fixture media store outside it). No live service, no network.
"""

import unittest

from hass.ops.photos import _CAMERA_RE, ALT_REPLY, _alt_problem
from hass.tests.test_product_add_photo import _add
from hass.tests.test_set_photo import PID, SetPhotoTestCase, _photo, _settings

CAMERAS = ("IMG_E1234", "img_e1234 copy", "MVIMG_20261102_101500", "PANO_20261102_101500", "GOPR1234", "GX010123",
           "GH012345", "DJI_0001", "dji 0042", "_DSC1234", "P1010001")
ACCEPTED = ("Gopher-shaped avocado", "Panorama of the orchard at dawn", "Pano of the shop front",
            "Dji drone shot of the orchard", "Hass avocados in a crate", "P101 crate of avocados", "GX12 avocado crate")
EXISTING = ("IMG_1234", "photo 1", "Screenshot 2026-11-01 at 10.15.32", "https://example.com/crate")


def _variants(alt):
    """The name as written, lower, upper and with mixed case (the op itself refuses outer spacing, see below)."""
    return (alt, alt.lower(), alt.upper(), alt.swapcase())


class SetPhotoAltCameraTests(SetPhotoTestCase):
    def refused_alt(self, alt, add=False):
        before = self.repo.products()
        req = _add(photo=self.jpg, imageAlt=alt) if add else _photo(PID, self.jpg, alt)
        self.assertEqual(self.rejected("refused", req)["reason"], ALT_REPLY, alt)
        self.assertEqual(self.repo.products(), before)
        self.assertFalse((self.repo.wt / self.target(self.jpg)).exists())  # no photo file queued or written
        self.assertFalse((self.repo.media / "web").exists())  # media store never read

    def test_camera_default_names_are_refused_in_any_case(self):
        for name in CAMERAS:
            for alt in _variants(name):
                with self.subTest(alt=alt):
                    self.refused_alt(alt)

    def test_surrounding_spaces_still_give_the_owner_reply(self):
        for name in CAMERAS:  # outer spacing never reaches the op (Arg refuses it); _alt_problem strips it anyway
            for alt in (f"  {name} ", f"\t{name.swapcase()}\n"):
                with self.subTest(alt=alt):
                    self.assertEqual(_alt_problem(alt, self.jpg), ALT_REPLY)

    def test_refusal_comes_before_the_media_store_is_read(self):
        _settings(self.repo)  # mediaRoot unset: a refused alt is still the alt reply, not "not configured"
        for alt in ("PANO_20261102_101500", "_DSC1234"):
            with self.subTest(alt=alt):
                self.refused_alt(alt)

    def test_product_add_gives_the_same_reply(self):
        for alt in ("IMG_E1234", "GX010123", "DJI_0001", "P1010001"):
            with self.subTest(alt=alt):
                self.refused_alt(alt, add=True)

    def test_real_descriptions_starting_with_these_letters_are_accepted(self):
        for alt in ACCEPTED:
            with self.subTest(alt=alt):
                self.repo.run(_photo(PID, self.jpg, alt))
                self.assertEqual(self.repo.product(PID)["imageAlt"], alt)
                self.assertTrue((self.repo.wt / self.target(self.jpg)).is_file())

    def test_too_few_digits_is_not_a_camera_name(self):
        for alt in ("P101", "GX12", "gx12", "GOPR12", "DJI_01", "PANO_12345", "MVIMG_12345", "IMG_E12", "P101000"):
            with self.subTest(alt=alt):
                self.assertIsNone(_CAMERA_RE.match(alt.casefold()))
        for alt in ("P101", "GX12"):  # falls through to today's result: fewer than 3 letters
            with self.subTest(alt=alt):
                self.assertEqual(_alt_problem(alt, self.jpg), ALT_REPLY)

    def test_existing_refusals_are_unchanged(self):
        for alt in EXISTING:
            with self.subTest(alt=alt):
                self.refused_alt(alt)


if __name__ == "__main__":
    unittest.main()
