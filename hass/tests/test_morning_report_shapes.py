"""RF0620-1 tests: a misshaped product record is named as `cannot read content`, exit 1, never a traceback.

Temporary content dirs only. Run: python3 -m unittest hass.tests.test_morning_report_shapes -v
"""

import contextlib
import io
import json
import unittest

from hass import morning_report
from hass.tests import test_morning_report as base  # module import: the AVB-23 tests are not collected twice

LAST, TODAY, product, CANNOT = base.LAST, base.TODAY, base.product, "morning_report: cannot read content"


class MorningReportShapeTests(unittest.TestCase):
    setUp, content, run_report, report = (base.MorningReportTests.setUp, base.MorningReportTests.content,
                                          base.MorningReportTests.run_report, base.MorningReportTests.report)

    def refused(self, products, *args):
        """Run with these products; assert exit 1, nothing on stdout, and return the one stderr line."""
        self.content(products, checked_days_ago=1)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            code = morning_report.main(["--today", TODAY.isoformat(), *args], content_dir=self.dir, out=out)
        self.assertEqual((code, out.getvalue()), (1, ""), err.getvalue())
        self.assertEqual(err.getvalue().count("\n"), 1, err.getvalue())  # one line, never a traceback
        return err.getvalue().rstrip("\n")

    def test_products_not_a_list(self):
        for bad in ({}, "Figs", 5, None, {"0": product("Figs", "yes")}):
            for args in ((), ("--json",)):
                self.assertEqual(self.refused(bad, *args), f"{CANNOT} (products.json: products is not a list)")

    def test_entry_not_an_object_names_its_position(self):
        for bad in ("oops", 5, None, [product("Figs", "yes")]):
            for args in ((), ("--json",)):
                self.assertEqual(self.refused([product("Figs", "yes"), bad], *args),
                                 f"{CANNOT} (products.json product 2: not an object)")
        self.assertEqual(self.refused(["oops", product("Figs", "yes")]), f"{CANNOT} (products.json product 1: not an object)")

    def test_active_name_not_text_or_empty(self):
        cases = (({k: v for k, v in product("Figs", "yes").items() if k != "name"}, "name is not text"),
                 (product("Figs", "yes") | {"name": 5}, "name is not text"),
                 (product("Figs", "yes") | {"name": None}, "name is not text"),
                 (product("Figs", "yes") | {"name": ["Figs"]}, "name is not text"),
                 (product("Figs", "yes") | {"name": "  "}, "name is empty"),
                 (product("Figs", "yes") | {"name": ""}, "name is empty"))
        for bad, what in cases:
            for args in ((), ("--json",)):
                self.assertEqual(self.refused([product("Pears", "no"), product("Kale"), bad], *args),
                                 f"{CANNOT} (products.json product 3: {what})")

    def test_active_name_with_line_break_or_control_character(self):
        for name in ("Avocado\noil", "Avocado\u2028oil", "Avocado\u2029oil", "Avocado\roil", "Avocado\toil",
                     "Avocado\u200boil", "Avocado\u202eoil", "Avocado oil\n"):
            for args in ((), ("--json",)):
                self.assertEqual(self.refused([product(name, "limited")], *args),
                                 f"{CANNOT} (products.json product 1: name has a line break or control character)")

    def test_name_length_limit_is_80(self):
        self.assertEqual(self.refused([product("A" * 81, "no")]), f"{CANNOT} (products.json product 1: name longer than 80 characters)")
        self.content([product("A" * 80, "no")], checked_days_ago=1)
        self.assertEqual(self.report().split("\n")[2:], ["Sold out: " + "A" * 80, LAST])

    def test_hidden_or_held_misshaped_name_is_ignored(self):
        good = [product("Pears", "no"), product("Figs", "limited"), product("Kale")]
        self.content(good, checked_days_ago=3)
        expected, expected_json = self.report(), self.report("--json")
        for status in ("hidden", "held"):
            for name in (5, None, "  ", "Bad\nname", "A" * 81):
                self.content(good + [product("X", "no", status) | {"name": name}], checked_days_ago=3)
                self.assertEqual((self.report(), self.report("--json")), (expected, expected_json))

    def test_valid_content_prints_the_same_report_as_before(self):  # golden strings from test_morning_report
        self.content([product("Zucchini", "limited"), product("apples", "limited"), product("Pears", "no"),
                      product("Figs", "yes"), product("Kale"), product("Plums", "maybe")], checked_days_ago=3)
        self.assertEqual(self.report(), "\n".join(["Your last shelf check was Friday, October 30.",
                                                   "On the shelves: 1 available, 2 running low, 1 sold out, 2 not confirmed.",
                                                   "Running low: apples, Zucchini", "Sold out: Pears", LAST]))
        self.content([product("Pears", "no"), product("Figs", "limited"), product("Kale")], checked_days_ago=3)
        self.assertEqual(self.report("--json"), json.dumps(
            {"checked_on": "2026-10-30", "stale": False, "future": False, "available": 0, "limited": 1, "sold_out": 1,
             "not_confirmed": 1, "limited_names": ["Figs"], "sold_out_names": ["Pears"]}))
        self.content([product("Figs", "yes")], checked_days_ago=8)
        self.assertEqual(self.report().split("\n")[0], "Your last shelf check was Sunday, October 25. That was more than a week ago, so the website says to call to confirm.")
        self.content([product("Figs", "yes"), product("Pears", "no")], checked_days_ago=-1)
        self.assertEqual(self.report().split("\n"), ["Your last shelf check is dated Tuesday, November 3, which is still to come. Please check the date on the computer.",
                                                    "On the shelves: 1 available, 0 running low, 1 sold out, 0 not confirmed.",
                                                    "Sold out: Pears", LAST])

    def test_unreadable_file_line_is_unchanged(self):
        self.content([product("Figs", "yes")], checked_days_ago=1)
        (self.dir / "products.json").write_text("{not json", encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(morning_report.main(["--today", TODAY.isoformat()], content_dir=self.dir, out=io.StringIO()), 1)
        self.assertEqual(err.getvalue(), CANNOT + "\n")


if __name__ == "__main__":
    unittest.main()
