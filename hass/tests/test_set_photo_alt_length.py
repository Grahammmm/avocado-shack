"""RF1510-13 (H10/H13): photos.install refuses an imageAlt over 200 characters with one plain owner reply.

Covers product.set_photo, product.add with a photo and store.set_home_image. Same PhotoRepo harness as test_set_photo.
"""

import json
import unittest

from hass.ops import photos
from hass.tests.test_product_add_photo import _add
from hass.tests.test_set_photo import PID, SetPhotoTestCase, _photo

BASE = "Avocados in a wooden crate"
ALT200 = BASE + " " + "a" * (200 - len(BASE) - 1)


def _reply(n):
    return f"the photo description is longer than 200 characters (it has {n})"


def _home(sha, alt):
    return ("store.set_home_image", {"photo": sha, "imageAlt": alt})


class AltLengthTests(SetPhotoTestCase):
    def store(self):
        return self.repo.read("hass/content/store.json")

    def test_limit_is_the_content_model_limit(self):
        self.assertEqual(photos.MAX_ALT, 200)

    def test_set_photo_201_chars_is_refused_and_nothing_is_queued(self):
        before = self.repo.product(PID)
        result = self.rejected("refused", _photo(PID, self.jpg, BASE + " " + "a" * (201 - len(BASE) - 1)))
        self.assertEqual(result["reason"], _reply(201))
        self.assertEqual(self.repo.product(PID), before)
        self.assertFalse((self.repo.wt / self.target(self.jpg)).exists())

    def test_exactly_200_chars_is_accepted_and_reaches_the_page(self):
        self.assertEqual(len(ALT200), 200)
        self.repo.run(_photo(PID, self.jpg, ALT200))
        self.assertEqual(self.repo.product(PID)["imageAlt"], ALT200)
        record = next(p for p in self.repo.catalog() if p["id"] == PID)
        self.assertEqual(record["imageAlt"], ALT200)
        self.assertTrue((self.repo.wt / self.target(self.jpg)).is_file())

    def test_add_with_photo_and_300_chars_is_refused_and_no_product_added(self):
        before = self.repo.products()
        result = self.rejected("refused", _add(photo=self.jpg, imageAlt=BASE + " " + "a" * (300 - len(BASE) - 1)))
        self.assertEqual(result["reason"], _reply(300))
        self.assertEqual(self.repo.products(), before)
        self.assertFalse((self.repo.wt / self.target(self.jpg)).exists())

    def test_home_image_201_chars_is_refused_and_the_store_is_unchanged(self):
        before = self.store()
        result = self.rejected("refused", _home(self.jpg, BASE + " " + "a" * (201 - len(BASE) - 1)))
        self.assertEqual(result["reason"], _reply(201))
        self.assertEqual(self.store(), before)
        self.assertNotIn("homeImage", json.loads(before))
        self.assertFalse((self.repo.wt / self.target(self.jpg)).exists())

    def test_home_image_200_chars_is_accepted(self):
        self.repo.run(_home(self.jpg, ALT200))
        self.assertEqual(json.loads(self.store())["homeImage"]["imageAlt"], ALT200)

    def test_length_is_checked_before_the_camera_name_rule_one_reply(self):
        alt = "IMG_1234.JPG" + "x" * 238
        self.assertEqual(len(alt), 250)
        self.assertNotEqual(self.rejected("refused", _photo(PID, self.jpg, alt))["reason"], photos.ALT_REPLY)
        self.assertEqual(self.rejected("refused", _photo(PID, self.jpg, alt))["reason"], _reply(250))
        self.assertEqual(self.rejected("refused", _home(self.jpg, alt))["reason"], _reply(250))
        self.assertEqual(self.rejected("refused", _add(photo=self.jpg, imageAlt=alt))["reason"], _reply(250))

    def test_length_counts_characters_not_bytes(self):
        self.repo.run(_photo(PID, self.jpg, "\u00e9" * 200))
        self.assertEqual(self.repo.product(PID)["imageAlt"], "\u00e9" * 200)
        self.assertEqual(self.rejected("refused", _photo(PID, self.jpg, "\u00e9" * 201))["reason"], _reply(201))

    def test_a_short_bad_alt_still_gets_the_existing_reply(self):
        self.assertEqual(self.rejected("refused", _photo(PID, self.jpg, "IMG_1234.JPG"))["reason"], photos.ALT_REPLY)


if __name__ == "__main__":
    unittest.main()
