"""RF2330-9 (H10): imageAlt refuses screenshot and messaging-app default names and web links with the fixed owner reply.

Reuses the test_set_photo WriterRepo harness (temp Git repo, fixture media store outside it). No live service, no network.
"""

import unittest

from hass.ops.photos import ALT_REPLY
from hass.tests.test_product_add_photo import _add
from hass.tests.test_set_photo import PID, SetPhotoTestCase, _photo, _settings

APP_DEFAULTS = ("Screenshot 2026-11-01 at 10.15.32", "Screen Shot 2026-11-01 at 10.15.32 AM", "screenshot_20261101-101532",
                "Screen Recording 2026-11-01 at 10.15.32", "WhatsApp Image 2026-11-01 at 10.15.32",
                "signal-2026-11-01-101532", "Screenshot", "SCREENSHOT (3)", "Screen Shot(12)")
LINKS = ("https://example.com/crate.jpg?w=800", "http://x.y/z", "www.avocadoshack.example/crate")
ACCEPTED = ("Screenshot of the farm stand price board", "Screen printed avocado tote bag", "Signal sign at the farm gate",
            "WhatsApp group flyer for the hike", "Photo of Hass avocados in a crate", "Image of a lime tree",
            "Pic of 12 avocados")


class SetPhotoAltDefaultsTests(SetPhotoTestCase):
    def refused_alt(self, alt):
        before = self.repo.product(PID)
        result = self.rejected("refused", _photo(PID, self.jpg, alt))
        self.assertEqual(result["reason"], ALT_REPLY, alt)
        self.assertEqual(self.repo.product(PID), before)
        self.assertFalse((self.repo.wt / self.target(self.jpg)).exists())  # no photo file queued or written

    def test_screenshot_and_app_default_names_are_refused(self):
        for alt in APP_DEFAULTS:
            with self.subTest(alt=alt):
                self.refused_alt(alt)

    def test_web_links_are_refused(self):
        for alt in LINKS:
            with self.subTest(alt=alt):
                self.refused_alt(alt)

    def test_real_descriptions_mentioning_screens_or_apps_are_accepted(self):
        for alt in ACCEPTED:
            with self.subTest(alt=alt):
                self.repo.run(_photo(PID, self.jpg, alt))
                self.assertEqual(self.repo.product(PID)["imageAlt"], alt)
                self.assertTrue((self.repo.wt / self.target(self.jpg)).is_file())

    def test_product_add_refuses_a_screenshot_name_before_the_store_is_read(self):
        before = self.repo.products()
        result = self.rejected("refused", _add(photo=self.jpg, imageAlt="Screenshot 2026-11-01 at 10.15.32"))
        self.assertEqual(result["reason"], ALT_REPLY)
        self.assertEqual(self.repo.products(), before)
        self.assertFalse((self.repo.media / "web").exists())

    def test_refusal_comes_before_the_media_store_is_read(self):
        _settings(self.repo)  # mediaRoot unset
        self.refused_alt("WhatsApp Image 2026-11-01 at 10.15.32")
        self.refused_alt("https://example.com/crate.jpg?w=800")
        self.assertEqual(self.rejected("refused", _photo(PID, self.jpg))["reason"], "photo store is not configured")


if __name__ == "__main__":
    unittest.main()
