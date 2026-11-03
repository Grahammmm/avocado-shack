"""RF1050-5 (H10) tests: the label reader never offers a value containing U+2028/U+2029 (Zl/Zp).

Such a value is dropped like a control character; the other fields are still offered. Spaces (Zs) are not refused.
str.strip() already trims leading/trailing U+2028/U+2029, so an edge separator is trimmed and the value offered.
Run: python3 -m unittest hass.tests.test_label_reader_separators -v
"""

import unittest

from hass.label_reader import keep, question

CATS = ["fruit", "honey", "tea"]
LS, PS = "\u2028", "\u2029"


class SeparatorTests(unittest.TestCase):
    def test_line_separator_in_name_drops_name_keeps_brand(self):
        self.assertEqual(keep({"name": "Lion's Mane\u2028Tea", "brand": "Linn's"}, CATS), {"brand": "Linn's"})

    def test_paragraph_separator_in_brand_drops_brand_keeps_name(self):
        self.assertEqual(keep({"name": "Lion's Mane Tea", "brand": "Linn\u2029s"}, CATS), {"name": "Lion's Mane Tea"})

    def test_separator_in_category_drops_category(self):
        self.assertEqual(keep({"name": "Ranch Honey", "category": "ho" + LS + "ney"}, CATS), {"name": "Ranch Honey"})
        self.assertEqual(keep({"name": "Ranch Honey", "category": "ho" + PS + "ney"}, CATS), {"name": "Ranch Honey"})

    def test_both_separators_refused_in_every_field(self):
        for sep in (LS, PS):
            for field in ("name", "brand"):
                with self.subTest(sep=hex(ord(sep)), field=field):
                    found = keep({"name": "Ranch Honey", "brand": "Etto", "category": "honey",
                                  field: f"Big{sep}Value"}, CATS)
                    self.assertNotIn(field, found)
                    self.assertEqual(len(found), 2)

    def test_nbsp_and_em_space_are_still_offered(self):
        for name in ("Lion's\u00a0Mane Tea", "Lion's\u2003Mane Tea"):
            with self.subTest(name=repr(name)):
                self.assertEqual(keep({"name": name, "brand": "Linn's"}, CATS), {"name": name, "brand": "Linn's"})

    def test_edge_separators_are_trimmed_by_strip_and_value_offered(self):
        self.assertTrue(LS.isspace() and PS.isspace())  # why strip() removes them before the check
        for raw in (LS + "Lion's Mane Tea", "Lion's Mane Tea" + PS, LS + PS + "Lion's Mane Tea" + LS):
            with self.subTest(raw=repr(raw)):
                self.assertEqual(keep({"name": raw}, CATS), {"name": "Lion's Mane Tea"})
        self.assertEqual(keep({"name": LS + "Lion's" + LS + "Mane" + PS}, CATS), {})  # inner one still refused
        self.assertEqual(keep({"name": LS + PS}, CATS), {})  # nothing left after strip

    def test_question_from_kept_fields_has_no_separator(self):
        found = keep({"name": "Lion's Mane\u2028Tea", "brand": "Linn\u2029s", "category": "tea" + LS}, CATS)
        line = question(found)
        self.assertNotIn(LS, line)
        self.assertNotIn(PS, line)
        self.assertEqual(found, {"category": "tea"})
        mixed = keep({"name": "Lion's Mane Tea" + PS, "brand": "Linn's"}, CATS)
        self.assertEqual(question(mixed).count(PS) + question(mixed).count(LS), 0)
        self.assertIn("Linn's Lion's Mane Tea", question(mixed))


if __name__ == "__main__":
    unittest.main()
