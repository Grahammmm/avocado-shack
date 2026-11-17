"""Unit-only and sold-by intake answers never erase a number (RF1210-15).

Run: python3 -B -m unittest hass.tests.test_item_intake_unit_admission -q
"""
import unittest
from datetime import date

from hass.skills import item_intake as ii

TODAY = date(2026, 11, 16)


class UnitAdmission(unittest.TestCase):
    def test_unit_only_does_not_discard_numeric_qualifiers(self):
        self.assertEqual(ii._parse_unit("jars"), "jar")
        for bad in ("2 jars", "jar2", "jar 2", "\u0662 jars", "jar\uff12", "\u00bd jar", "jar\u00b2"):
            self.assertIsNone(ii._parse_unit(bad), bad)
            self.assertEqual(ii.read("qty_unit", bad, {}, today=TODAY)[0], "again", bad)

    def test_sold_by_does_not_change_denominator(self):
        for bad in ("per 2 pounds", "2 per pound", "pound2", "per \u00bd pound"):
            self.assertIsNone(ii._parse_sold_by(bad), bad)
        self.assertEqual(ii._parse_sold_by("per pound"), "pound")
        self.assertEqual(ii._parse_sold_by("by the bag"), "bag")
        self.assertEqual(ii._parse_sold_by("each"), "item")

    def test_reader_values_use_same_unit_admission(self):
        self.assertIsNone(ii.from_reader("qty_unit", {"value": "jar2"}, TODAY))
        self.assertIsNone(ii.from_reader("qty", {"value": {"number": 3, "unit": "2 jars"}}, TODAY))
        self.assertEqual(ii.from_reader("qty_unit", {"value": "jars"}, TODAY), {"qty_unit": "jar"})
        self.assertEqual(ii.from_reader("qty", {"value": {"number": 3, "unit": "jars"}}, TODAY), {"qty": 3, "qty_unit": "jar"})

    def test_reask_reader_once_then_blank(self):
        self.assertEqual(ii.read("qty_unit", "jar2", {}, today=TODAY)[0], "again")
        calls = []

        def reader(key, words):
            calls.append(key)
            return {"value": "jar2"}

        self.assertEqual(ii.read("qty_unit", "jar2", {}, today=TODAY, asks=1, reader=reader)[0], "again")
        self.assertEqual(len(calls), 1)
        self.assertEqual(ii.read("qty_unit", "jar2", {}, today=TODAY, asks=2, reader=reader)[0], "again")
        self.assertEqual(len(calls), 1)
        got = ii.read("qty_unit", "jar2", {}, today=TODAY, asks=3, reader=reader)
        self.assertEqual(got[:2], ("ok", {"qty_unit": None}))
        self.assertIn("left", got[3])

    def test_quantity_question_still_accepts_numbers(self):
        self.assertEqual(ii.read("qty", "12 jars", {}, today=TODAY)[1], {"qty": 12, "qty_unit": "jar"})
        self.assertEqual(ii.read("qty", "2.5 pounds", {}, today=TODAY)[1]["qty"], 2.5)
        self.assertEqual(ii.read("qty_unit", "skip", {}, today=TODAY)[1], {"qty_unit": None})
        self.assertEqual(ii.read("qty_unit", "cancel", {}, today=TODAY)[0], "abort")


if __name__ == "__main__":
    unittest.main()
