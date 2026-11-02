"""RF0310-2 (H10): imageAlt refuses a placeholder word with only an article or number around it with the fixed reply.

Calls ``_alt_problem`` directly plus op round trips through the test_set_photo WriterRepo harness. No network.
"""

import unittest

from hass.ops.photos import ALT_REPLY, _alt_problem
from hass.tests.test_product_add_photo import _add
from hass.tests.test_set_photo import PID, SetPhotoTestCase, _photo, _settings

SHA = "ab" * 32
REFUSED = ("a photo", "The Image", "photo 1", "image #2", "Pic no. 3", "product photo 12", "our product", "Photo.",
           "  picture 7!  ", "an img", "this pic no 4", "my product image #5", "the picture...")
ACCEPTED = ("photo of Hass avocados in a crate", "Product shelf with honey jars", "a photo booth sign at the stand",
            "Picture-perfect peaches", "The product stand at dawn")


class AltProblemTests(unittest.TestCase):
    def test_placeholder_with_article_or_number_is_refused(self):
        for alt in REFUSED:
            with self.subTest(alt=alt):
                self.assertEqual(_alt_problem(alt, SHA), ALT_REPLY)

    def test_real_descriptions_containing_a_placeholder_word_pass(self):
        for alt in ACCEPTED:
            with self.subTest(alt=alt):
                self.assertIsNone(_alt_problem(alt, SHA))

    def test_four_digit_number_stays_refused_by_the_camera_rule(self):
        self.assertEqual(_alt_problem("photo 1234", SHA), ALT_REPLY)


class AltArticleOpTests(SetPhotoTestCase):
    def test_set_photo_refuses_before_the_store_is_read(self):
        _settings(self.repo)  # mediaRoot unset: the alt refusal must come first
        before = self.repo.product(PID)
        result = self.rejected("refused", _photo(PID, self.jpg, "a photo"))
        self.assertEqual(result["reason"], ALT_REPLY)
        self.assertEqual(self.repo.product(PID), before)
        self.assertFalse((self.repo.wt / self.target(self.jpg)).exists())

    def test_product_add_refuses_a_numbered_placeholder(self):
        before = self.repo.products()
        result = self.rejected("refused", _add(photo=self.jpg, imageAlt="photo 2"))
        self.assertEqual(result["reason"], ALT_REPLY)
        self.assertEqual(self.repo.products(), before)
        self.assertFalse((self.repo.media / "web").exists())

    def test_a_real_description_is_still_installed(self):
        alt = "a photo booth sign at the stand"
        self.repo.run(_photo(PID, self.jpg, alt))
        self.assertEqual(self.repo.product(PID)["imageAlt"], alt)
        self.assertTrue((self.repo.wt / self.target(self.jpg)).is_file())


if __name__ == "__main__":
    unittest.main()
