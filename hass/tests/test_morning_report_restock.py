"""AV1109-04 tests: the private restock day on the morning shelf report (one line per active product, today or later).

Temporary content dirs only (no repo content, no state). Run: python3 -B -m unittest hass.tests.test_morning_report_restock -v
"""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from hass import morning_report, voice

TODAY = date(2026, 11, 9)  # a Monday
LAST = "These come from your last shelf check, so they are not stock counts."


def product(name, restock=None, status="active", pid=None, **more):
    return {"id": pid or name.lower().replace(" ", "-")[:60], "name": name, "status": status,
            **({} if restock is None else {"restock_on": restock}), **more}


class RestockReport(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def content(self, products):
        for name, doc in (("products", {"schemaVersion": 1, "products": products}), ("makers", {"schemaVersion": 1, "makers": {}}),
                          ("community", {"schemaVersion": 1}), ("store", {"schemaVersion": 1})):
            (self.dir / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")

    def run_report(self, *args, expect=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            code = morning_report.main(["--today", TODAY.isoformat(), *args], content_dir=self.dir, out=out)
        self.assertEqual(code, expect, err.getvalue())
        return out.getvalue().rstrip("\n") if expect == 0 else err.getvalue()

    def lines(self):
        return self.run_report().split("\n")

    def test_one_line_per_active_product_with_the_day_in_fixed_english(self):
        self.content([product("Honey", "2026-11-12")])
        self.assertEqual(self.lines()[-1], "Honey: more expected Thu Nov 12")
        self.assertEqual(self.lines()[:-1], ["I still need your shelf check.",
                         "On the shelves: 0 available, 0 running low, 0 sold out, 1 not confirmed.", LAST])  # the old block, then the line
        self.assertEqual(json.loads(self.run_report("--json"))["restocks"], [{"id": "honey", "name": "Honey", "day": "2026-11-12"}])

    def test_today_and_later_show_and_past_days_never_do(self):
        self.content([product("Past", "2026-11-08"), product("Today", "2026-11-09"), product("Far", "2027-03-01"),
                      product("Leap", "2028-02-29"), product("Never")])
        self.assertEqual(self.lines()[3:], ["Today: more expected Mon Nov 9", "Far: more expected Mon Mar 1", "Leap: more expected Tue Feb 29"])
        self.content([product("Past", "2026-11-08"), product("Older", "2020-01-01")])
        self.assertEqual(len(self.lines()), 3)
        self.assertNotIn("restocks", json.loads(self.run_report("--json")))

    def test_hidden_and_held_products_never_appear_even_with_a_bad_day(self):
        self.content([product("Gone", "2026-11-12", status="hidden"), product("Held", "2026-11-12", status="held"),
                      product("Held two", "not a day", status="held"), product("Shown", "2026-11-13")])
        self.assertEqual(self.lines()[3:], ["Shown: more expected Fri Nov 13"])

    def test_sorted_by_day_then_name_and_same_names_stay_separate_lines(self):
        self.content([product("Salt", "2026-11-12", pid="salt-b"), product("salt", "2026-11-12", pid="salt-a"), product("Beans", "2026-11-12"),
                      product("Honey", "2026-11-10"), product("  Big   Sur  \"honey\"  ", "2026-11-11")])
        self.assertEqual(self.lines()[3:], ["Honey: more expected Tue Nov 10", "Big Sur \"honey\": more expected Wed Nov 11",
                                            "Beans: more expected Thu Nov 12", "salt: more expected Thu Nov 12", "Salt: more expected Thu Nov 12"])
        self.assertEqual([r["id"] for r in json.loads(self.run_report("--json"))["restocks"]][2:], ["beans", "salt-a", "salt-b"])

    def test_a_bad_day_on_an_active_product_is_the_existing_unreadable_exit(self):
        for bad in ("2026-13-01", "20261112", "", None, 5, "2026-11-12 "):
            with self.subTest(bad=bad):
                self.content([product("Honey", "2026-11-12"), {**product("Bad"), "restock_on": bad}])
                self.assertIn("products.json product 2: restock_on is not a real date", self.run_report(expect=1))

    def test_no_restock_keeps_the_old_facts_json_and_text_exactly(self):
        self.content([product("Eggs", available="yes"), product("Gone", "2026-01-01")])
        facts = morning_report.facts(morning_report.load_content(self.dir), TODAY)
        self.assertNotIn("restocks", facts)
        self.assertEqual(json.loads(self.run_report("--json")), {"checked_on": None, "stale": False, "future": False, "available": 0, "limited": 0,
                                                                  "sold_out": 0, "not_confirmed": 2, "limited_names": [], "sold_out_names": []})
        self.assertEqual(self.lines(), ["I still need your shelf check.",
                                        "On the shelves: 0 available, 0 running low, 0 sold out, 2 not confirmed.", LAST])
        self.assertEqual(morning_report.render({**facts, "restocks": []}), morning_report.render(facts))  # empty is no line

    def test_a_long_list_is_complete_and_the_old_block_is_unchanged(self):
        limited = [product(f"Low {i:02d} " + "x" * 60, available="limited", pid=f"low-{i:02d}") for i in range(12)]
        names = [f"Item {i:02d} " + "y" * 70 for i in range(14)]
        plain = [product(n, pid=f"item-{i:02d}") for i, n in enumerate(names)]
        self.content(limited + plain)
        old = self.run_report()
        self.content(limited + [{**p, "restock_on": f"2026-12-{i + 1:02d}"} for i, p in enumerate(plain)])
        new = self.run_report()
        self.assertTrue(new.startswith(old + "\n"))
        added = new[len(old) + 1:].split("\n")
        self.assertEqual(added, [f"{n}: more expected {morning_report.restock_day(date(2026, 12, i + 1))}" for i, n in enumerate(names)])
        self.assertTrue(all("and " not in line.split(":")[0] and "more)" not in line for line in added))  # none coalesced or cut
        self.assertGreater(len(new), morning_report.MAX_CHARS)  # the additive lines may exceed the legacy cap: stated, not hidden

    def test_the_report_only_reads_and_every_line_passes_the_voice_rules(self):
        self.content([product("Honey", "2026-11-12"), product("Eggs", "2026-11-14")])
        digest = lambda: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(self.dir.iterdir())}  # noqa: E731
        before = digest()
        text = self.run_report()
        self.assertEqual(digest(), before)
        self.assertEqual(voice.check(text, long_ok=True), [])
        self.assertEqual(morning_report.restock_day("2027-01-01"), "Fri Jan 1")  # not the host's locale or zone
        self.assertEqual(morning_report.restock_day(date(2026, 3, 8)), "Sun Mar 8")  # the day the clocks change


if __name__ == "__main__":
    unittest.main()
