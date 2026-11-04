"""AVB-23 tests: the morning shelf report prints the owner's last confirmed availability, never stock counts.

Temporary content dirs only (no repo content, no state). Run: python3 -m unittest hass.tests.test_morning_report -v
"""

import contextlib
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hass import morning_report

TODAY = date(2026, 11, 2)
LAST = "These are your last shelf checks, not stock counts."


def product(name, available=None, status="active"):
    return {"id": name.lower().replace(" ", "-")[:60], "name": name, "status": status,
            **({} if available is None else {"available": available})}


class MorningReportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def content(self, products, checked_days_ago=None):
        store = {"schemaVersion": 1} | ({} if checked_days_ago is None else
                                        {"selection_checked_on": (TODAY - timedelta(days=checked_days_ago)).isoformat()})
        if "selection_checked_on" in store:  # AV1102-01: each word was set on that check
            products = [p | ({"available_on": store["selection_checked_on"]} if "available" in p else {}) for p in products]
        for name, doc in (("products", {"schemaVersion": 1, "products": products}),
                          ("makers", {"schemaVersion": 1, "makers": {}}), ("community", {"schemaVersion": 1}),
                          ("store", store)):
            (self.dir / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")

    def run_report(self, *args, expect=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                code = morning_report.main([*args], content_dir=self.dir, out=out)
            except SystemExit as exc:
                code = exc.code
        self.assertEqual(code, expect, err.getvalue())
        return out.getvalue().rstrip("\n")

    def report(self, *args):
        return self.run_report("--today", TODAY.isoformat(), *args)

    def test_no_check_yet_ignores_availability(self):
        self.content([product("Apples", "limited"), product("Pears", "no"), product("Figs", "yes"), product("Kale")])
        lines = self.report().split("\n")
        self.assertEqual(lines, ["Shelf check: not done yet",
                                 "Available 0 · Limited 0 · Sold out 0 · Not confirmed 4", LAST])

    def test_recent_check_counts_and_names(self):
        self.content([product("Zucchini", "limited"), product("apples", "limited"), product("Pears", "no"),
                      product("Figs", "yes"), product("Kale"), product("Plums", "maybe")], checked_days_ago=3)
        lines = self.report().split("\n")
        self.assertEqual(lines, ["Shelf check: Friday, October 30",
                                 "Available 1 · Limited 2 · Sold out 1 · Not confirmed 2",
                                 "Limited: apples, Zucchini", "Sold out: Pears", LAST])

    def test_stale_after_more_than_seven_days(self):
        self.content([product("Figs", "yes")], checked_days_ago=7)
        self.assertNotIn("more than a week ago", self.report())
        self.content([product("Figs", "yes")], checked_days_ago=8)
        lines = self.report().split("\n")
        self.assertEqual(lines[0], "Shelf check: Sunday, October 25 - more than a week ago")
        self.assertEqual(lines[-1], LAST)
        self.assertEqual(json.loads(self.report("--json"))["stale"], True)

    def test_twelve_limited_show_ten_names_and_stay_short(self):
        names = [f"Product {i:02d} " + "x" * 69 for i in range(12)]  # 80 characters each, the longest allowed
        self.assertEqual({len(n) for n in names}, {80})
        self.content([product(n, "limited") for n in names], checked_days_ago=1)
        text = self.report()
        self.assertEqual(text.split("\n")[2], "Limited: " + ", ".join(names[:10]) + ", +2 more")
        self.assertLessEqual(len(text), 1200)
        sold = [n[:-1] + "s" for n in names]  # distinct names, still the 80-character maximum
        self.content([product(n, "limited") for n in names] + [product(n, "no") for n in sold], checked_days_ago=1)
        text = self.report()
        self.assertLessEqual(len(text), 1200)
        self.assertEqual(text.split("\n")[-1], LAST)
        self.assertIn("Limited 12 · Sold out 12", text)  # counts stay exact when names are shortened

    def test_ten_names_without_more_line(self):
        self.content([product(f"P{i:02d}", "no") for i in range(10)], checked_days_ago=1)
        self.assertNotIn("more", self.report().split("\n")[2])

    def test_hidden_and_held_products_never_appear(self):
        self.content([product("Held thing", "no", "held"), product("Hidden thing", "limited", "hidden"),
                      product("Open thing", "yes")], checked_days_ago=1)
        text = self.report()
        self.assertIn("Available 1 · Limited 0 · Sold out 0 · Not confirmed 0", text)
        self.assertNotIn("thing", text.replace("Open thing", ""))
        self.assertNotIn("Sold out:", text)
        facts = json.loads(self.report("--json"))
        self.assertEqual((facts["sold_out"], facts["limited"], facts["sold_out_names"]), (0, 0, []))

    def test_json_carries_the_same_facts(self):
        self.content([product("Pears", "no"), product("Figs", "limited"), product("Kale")], checked_days_ago=3)
        self.assertEqual(json.loads(self.report("--json")),
                         {"checked_on": "2026-10-30", "stale": False, "future": False, "available": 0, "limited": 1, "sold_out": 1,
                          "not_confirmed": 1, "limited_names": ["Figs"], "sold_out_names": ["Pears"]})

    def test_invalid_today_exits_2_and_prints_no_report(self):
        self.content([product("Figs", "yes")], checked_days_ago=1)
        for bad in ("2026-13-01", "20261101", "tomorrow", "2026-11-1"):
            self.assertEqual(self.run_report("--today", bad, expect=2), "")

    def test_default_today_is_the_shop_date(self):
        self.content([product("Figs", "yes")])
        self.assertTrue(self.run_report().startswith("Shelf check: not done yet"))

    def test_unreadable_content_exits_1_and_changes_nothing(self):
        self.content([product("Figs", "yes")], checked_days_ago=1)
        (self.dir / "store.json").write_text("{not json", encoding="utf-8")
        before = sorted((p.name, p.read_bytes()) for p in self.dir.iterdir())
        self.run_report("--today", "2026-11-02", expect=1)
        self.assertEqual(before, sorted((p.name, p.read_bytes()) for p in self.dir.iterdir()))


if __name__ == "__main__":
    unittest.main()
