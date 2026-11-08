"""RF1240-22 tests: listed names have their spacing collapsed; a name shared by several products is listed once, as "Salt (2)".

Temporary content dirs only. Run: python3 -m unittest hass.tests.test_morning_report_names -v
"""

import contextlib
import io
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from hass import morning_report
from hass.tests.test_morning_report import LAST, TODAY, product


class MorningReportNameTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def report(self, products, *args, checked=True):
        store = {"schemaVersion": 1} | ({"selection_checked_on": (TODAY - timedelta(days=1)).isoformat()} if checked else {})
        items = [product(n, a) | {"id": f"p{i}"} for i, (n, a) in enumerate(products)]  # unique ids for shared names
        if checked:  # AV1102-01: each word was set on that check
            items = [p | ({"available_on": store["selection_checked_on"]} if "available" in p else {}) for p in items]
        for name, doc in (("products", {"schemaVersion": 1, "products": items}), ("makers", {"schemaVersion": 1, "makers": {}}),
                          ("community", {"schemaVersion": 1}), ("store", store)):
            (self.dir / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            code = morning_report.main(["--today", TODAY.isoformat(), *args], content_dir=self.dir, out=out)
        self.assertEqual(code, 0, err.getvalue())
        return out.getvalue().rstrip("\n")

    def test_spaced_name_is_collapsed_in_text_and_json(self):
        products = [("Big   Sur  Salt", "limited"), ("Sea\u00a0 Salt", "no")]  # a tab is still refused (shapes tests)
        lines = self.report(products).split("\n")
        self.assertEqual(lines[2:4], ["Running low: Big Sur Salt", "Sold out: Sea Salt"])
        facts = json.loads(self.report(products, "--json"))
        self.assertEqual((facts["limited_names"], facts["sold_out_names"]), (["Big Sur Salt"], ["Sea Salt"]))

    def test_shared_name_listed_once_with_its_count(self):
        products = [("Salt", "limited"), ("salt", "limited"), ("Salt ", "limited"), ("Honey", "limited")]
        lines = self.report(products).split("\n")
        self.assertEqual(lines[1:3], ["On the shelves: 0 available, 4 running low, 0 sold out, 0 not confirmed.", "Running low: Honey, Salt (3)"])
        self.assertEqual(json.loads(self.report(products, "--json"))["limited_names"], ["Honey", "Salt", "salt", "Salt"])

    def test_more_counts_groups_not_products(self):
        names = [f"N{i:02d}" for i in range(12)]
        text = self.report([(n, "limited") for n in names] + [("N03", "limited"), ("n03", "limited")])
        self.assertEqual(text.split("\n")[2], "Running low: N00, N01, N02, N03 (3), N04, N05, N06, N07, N08, N09, and 2 more")
        self.assertIn("14 running low,", text)

    def test_grouped_per_list_never_across_lists(self):
        lines = self.report([("Salt", "limited"), ("SALT", "limited"), ("Salt", "no"), ("Figs", "yes")]).split("\n")
        self.assertEqual(lines[1:4], ["On the shelves: 1 available, 2 running low, 1 sold out, 0 not confirmed.",
                                      "Running low: Salt (2)", "Sold out: Salt"])

    def test_no_check_yet_shows_no_names(self):
        lines = self.report([("Salt", "limited"), ("salt", "limited"), ("Big  Sur", "no")], checked=False).split("\n")
        self.assertEqual(lines, ["I still need your shelf check.", "On the shelves: 0 available, 0 running low, 0 sold out, 3 not confirmed.", LAST])

    def test_distinct_names_unchanged(self):
        text = self.report([("Sea Salt", "limited"), ("Salts", "limited"), ("Salt", "limited"), ("Pears", "no")])
        self.assertEqual(text, "\n".join(["Your last shelf check was Sunday, November 1.",
                                          "On the shelves: 0 available, 3 running low, 1 sold out, 0 not confirmed.",
                                          "Running low: Salt, Salts, Sea Salt", "Sold out: Pears", LAST]))

    def test_long_grouped_names_stay_within_max_chars(self):
        names = [f"Product {i:02d} " + "x" * 69 for i in range(12)]  # 80 characters, the longest allowed
        text = self.report([(n, a) for n in names for a in ("limited", "limited", "no", "no")])
        self.assertLessEqual(len(text), morning_report.MAX_CHARS)
        lines = text.split("\n")
        self.assertEqual((lines[1], lines[-1]), ("On the shelves: 0 available, 24 running low, 24 sold out, 0 not confirmed.", LAST))
        shown = lines[2].removeprefix("Running low: ").split(", ")
        self.assertEqual(shown[:-1], [n + " (2)" for n in names[:len(shown) - 1]])
        self.assertEqual(shown[-1], f"and {12 - (len(shown) - 1)} more")


if __name__ == "__main__":
    unittest.main()
