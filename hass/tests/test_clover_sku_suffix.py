"""RF1911-13: the Hass SKU recognizer admits only ASCII suffixes 01 through 99."""
import unittest

from hass.clover.sku import SKU_MAX, generate_sku, is_hass_sku

STEM = "AS-PAN-HONEY-"


class SkuSuffixTests(unittest.TestCase):
    def test_zero_suffix_is_not_hass_issued(self):
        self.assertFalse(is_hass_sku(STEM + "00"))

    def test_unicode_and_mixed_digit_suffixes_are_not_hass_issued(self):
        for suffix in ("\u0660\u0661", "\u06f0\u06f1", "\uff10\uff11", "0\u0661", "\uff11" + "1", "1\u0662"):
            with self.subTest(suffix=suffix):
                self.assertFalse(is_hass_sku(STEM + suffix))

    def test_all_ascii_suffixes_one_through_ninety_nine_are_valid(self):
        for n in range(1, 100):
            with self.subTest(n=n):
                self.assertTrue(is_hass_sku(f"{STEM}{n:02d}"))
        for bad in ("1", "001", "+1", "-1", " 1", "1 ", "01 ", "01\n", "100"):
            with self.subTest(bad=bad):
                self.assertFalse(is_hass_sku(STEM + bad))

    def test_generated_sku_and_existing_nonstring_length_guards_are_unchanged(self):
        self.assertTrue(is_hass_sku(generate_sku("Honey", "pantry", [])))
        for value in (None, ["AS-PAN-HONEY-01"], 1):
            with self.subTest(value=value):
                self.assertFalse(is_hass_sku(value))
        self.assertFalse(is_hass_sku("AS-PAN-" + "A" * SKU_MAX + "-01"))


if __name__ == "__main__":
    unittest.main()
