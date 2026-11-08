"""RF0250-4 (H10) tests: the label reader never offers a barcode, price or bare size as a product name or brand.

keep() is called directly (no transport, no model, no network).
Run: python3 -m unittest hass.tests.test_label_reader_amounts -v
"""

import unittest

from hass.label_reader import keep, question

CATS = ["fruit", "mushrooms", "vegetables", "12 oz"]
DROPPED = ["0 12345 67890 5", "012345678905", "$4.99", "4,99 €", "12 oz", "12 OZ.", "1.5 L", "500ml", "16 fl oz",
           "6 ct", "1/2", "£3", "2 lbs", "  12   oz  ", "１２ oz"]
KEPT = ["Route 1 Honey", "7 Sisters Salsa", "Cuvée 1999", "Lion's Mane", "V8", "3 Little Pigs", "Oz Farm"]


class AmountValues(unittest.TestCase):
    def test_no_letter_price_or_size_is_not_offered_as_name_or_brand(self):
        for value in DROPPED:
            with self.subTest(value=value):
                self.assertEqual(keep({"name": value}, CATS), {})
                self.assertEqual(keep({"brand": value}, CATS), {})

    def test_real_names_with_digits_still_pass(self):
        for value in KEPT:
            with self.subTest(value=value):
                self.assertEqual(keep({"name": value}, CATS), {"name": value})
                self.assertEqual(keep({"brand": value}, CATS), {"brand": value})

    def test_size_name_dropped_brand_kept_and_question_names_only_the_brand(self):
        found = keep({"name": "12 oz", "brand": "Linn's"}, CATS)
        self.assertEqual(found, {"brand": "Linn's"})
        line = question(found)
        self.assertTrue(line.startswith("The label looks like \ue000Linn's\ue001. Is that right?"), line)
        self.assertNotIn("12 oz", line)

    def test_two_dropped_prices_leave_nothing(self):
        self.assertEqual(keep({"name": "$4.99", "brand": "$4.99"}, CATS), {})

    def test_amount_beside_a_real_name_drops_only_the_amount(self):
        self.assertEqual(keep({"name": "Lion's Mane", "brand": "500ml", "category": "mushrooms"}, CATS),
                         {"name": "Lion's Mane", "category": "mushrooms"})

    def test_category_rule_unchanged(self):
        self.assertEqual(keep({"category": "12 oz"}, CATS), {"category": "12 oz"})
        self.assertEqual(keep({"category": "12 OZ"}, CATS), {"category": "12 oz"})
        self.assertEqual(keep({"category": "16 fl oz"}, CATS), {})  # still must be a catalog category

    def test_zero_width_joiner_digits_dropped_by_format_rule(self):
        for value in ("1\u200d2 3", "0 12345\u200d 67890"):
            with self.subTest(value=value):
                self.assertEqual(keep({"name": value, "brand": value}, CATS), {})

    def test_amount_with_trailing_words_is_a_name(self):
        self.assertEqual(keep({"name": "12 oz Coffee"}, CATS), {"name": "12 oz Coffee"})


if __name__ == "__main__":
    unittest.main()
