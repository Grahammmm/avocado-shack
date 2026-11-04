"""RF1050-8 (H10) tests: a label value is offered with its inner spacing collapsed (spaces, tabs, NBSP -> one space);
every check (length, placeholders, amounts, brand echo, category) runs on the collapsed value; line breaks still refuse.
Run: python3 -m unittest hass.tests.test_label_reader_spacing -v
"""

import unittest

from hass.content_model import TEXT_LIMITS
from hass.label_reader import keep

CATS = ["fruit", "honey", "tea"]


class SpacingTests(unittest.TestCase):
    def test_inner_spaces_tabs_and_nbsp_collapse(self):
        for raw, want in (("Big   Sur  Salt", "Big Sur Salt"), ("Big\tSur", "Big Sur"), ("Big\u00a0Sur", "Big Sur"),
                          ("  Big \t\u00a0 Sur\u2003Salt\t", "Big Sur Salt")):
            with self.subTest(raw=repr(raw)):
                self.assertEqual(keep({"name": raw, "brand": raw}, CATS), {"name": want})  # brand echoes the name
                self.assertEqual(keep({"brand": raw}, CATS), {"brand": want})

    def test_line_breaks_still_refuse_the_value(self):
        for sep in ("\n", "\r\n", "\r", "\v", "\f", "\x85", "\u2028", "\u2029"):
            with self.subTest(sep=repr(sep)):
                self.assertEqual(keep({"name": f"Big{sep}Sur", "brand": "Etto"}, CATS), {"brand": "Etto"})
                self.assertEqual(keep({"name": "Ranch Honey", "brand": f"Big{sep}Sur"}, CATS), {"name": "Ranch Honey"})
                self.assertEqual(keep({"name": "Ranch Honey", "category": f"ho{sep}ney"}, CATS), {"name": "Ranch Honey"})

    def test_other_control_characters_still_refuse(self):
        for bad in ("\x1f", "\x1c", "\x00", "\u200b"):  # \x1c-\x1f are str.split() whitespace but are not spacing
            with self.subTest(bad=repr(bad)):
                self.assertEqual(keep({"name": f"Big{bad}Sur"}, CATS), {})

    def test_length_is_checked_after_collapsing(self):
        limit = TEXT_LIMITS["product"]["name"]
        fits = "a" * (limit - 2) + " b"
        self.assertEqual(len(fits), limit)
        spaced = fits.replace(" ", "     \t ")
        self.assertGreater(len(spaced), limit)
        self.assertEqual(keep({"name": spaced}, CATS), {"name": fits})
        over = "a" * (limit - 1) + "    b"  # limit + 1 after collapsing
        self.assertEqual(keep({"name": over}, CATS), {})

    def test_placeholders_and_amounts_seen_through_spacing(self):
        for raw in ("  n/a  ", "not   printed", "not\tprinted", "no\u00a0brand"):
            with self.subTest(raw=repr(raw)):
                self.assertEqual(keep({"name": raw, "brand": raw}, CATS), {})
        for raw in ("12   oz", "12\toz", "4\u00a0\u00a0lbs"):
            with self.subTest(raw=repr(raw)):
                self.assertEqual(keep({"name": raw, "brand": "Etto"}, CATS), {"brand": "Etto"})

    def test_brand_echo_with_different_spacing_is_dropped(self):
        self.assertEqual(keep({"name": "Linn's", "brand": "  Linn's\t"}, CATS), {"name": "Linn's"})
        self.assertEqual(keep({"name": "Linn's  Farm", "brand": "Linn's\u00a0Farm"}, CATS), {"name": "Linn's Farm"})
        self.assertEqual(keep({"name": "Linn's Farm Tea", "brand": "Linn's  Farm"}, CATS),
                         {"name": "Linn's Farm Tea", "brand": "Linn's Farm"})  # not an echo: both kept, collapsed

    def test_category_matches_on_collapsed_value(self):
        self.assertEqual(keep({"category": " Honey\t"}, CATS), {"category": "honey"})
        self.assertEqual(keep({"category": "ho ney"}, CATS), {})
        self.assertEqual(keep({"category": "ho\nney"}, CATS), {})


if __name__ == "__main__":
    unittest.main()
