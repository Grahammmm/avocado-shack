"""RF0140-5 tests: a shelf check dated after --today is named ("check the clock"), never reported as a fresh check.

Temporary content dirs only. Run: python3 -m unittest hass.tests.test_morning_report_future -v
"""

import json
import unittest

from hass.tests import test_morning_report as base  # module import: the AVB-23 tests are not collected twice

LAST, product, FUTURE = base.LAST, base.product, " - dated after today, check the clock"


class MorningReportFutureTests(unittest.TestCase):
    setUp, content, run_report, report = (base.MorningReportTests.setUp, base.MorningReportTests.content,
                                          base.MorningReportTests.run_report, base.MorningReportTests.report)

    def test_check_dated_tomorrow_is_named_not_fresh(self):
        self.content([product("Figs", "yes"), product("Pears", "no")], checked_days_ago=-1)
        lines = self.report().split("\n")
        self.assertEqual(lines[0], "Shelf check: Tuesday, November 3" + FUTURE)
        self.assertEqual(lines[1:], ["Available 1 · Limited 0 · Sold out 1 · Not confirmed 0", "Sold out: Pears", LAST])
        facts = json.loads(self.report("--json"))
        self.assertEqual((facts["checked_on"], facts["future"], facts["stale"]), ("2026-11-03", True, False))
        self.assertEqual(list(facts)[:3], ["checked_on", "stale", "future"])

    def test_far_future_check_is_never_stale(self):
        self.content([product("Figs", "yes")], checked_days_ago=-30)
        line = self.report().split("\n")[0]
        self.assertTrue(line.endswith(FUTURE), line)
        self.assertNotIn("more than a week ago", line)
        facts = json.loads(self.report("--json"))
        self.assertEqual((facts["future"], facts["stale"]), (True, False))

    def test_check_dated_today_has_no_suffix(self):
        self.content([product("Figs", "yes")], checked_days_ago=0)
        self.assertEqual(self.report().split("\n")[0], "Shelf check: Monday, November 2")
        facts = json.loads(self.report("--json"))
        self.assertEqual((facts["future"], facts["stale"]), (False, False))

    def test_stale_check_keeps_stale_suffix_only(self):
        self.content([product("Figs", "yes")], checked_days_ago=8)
        self.assertEqual(self.report().split("\n")[0], "Shelf check: Sunday, October 25 - more than a week ago")
        facts = json.loads(self.report("--json"))
        self.assertEqual((facts["future"], facts["stale"]), (False, True))

    def test_no_check_yet_is_not_future(self):
        self.content([product("Figs", "yes")])
        self.assertEqual(self.report().split("\n")[0], "Shelf check: not done yet")
        facts = json.loads(self.report("--json"))
        self.assertEqual((facts["checked_on"], facts["future"], facts["stale"]), (None, False, False))

    def test_past_today_flag_makes_the_check_future(self):
        self.content([product("Figs", "yes")], checked_days_ago=0)
        self.assertTrue(self.run_report("--today", "2026-11-01").split("\n")[0].endswith(FUTURE))

    def test_future_check_with_twelve_limited_stays_short(self):
        names = [f"Product {i:02d} " + "x" * 66 for i in range(12)]
        self.content([product(n, "limited") for n in names], checked_days_ago=-1)
        text = self.report()
        self.assertTrue(text.split("\n")[0].endswith(FUTURE))
        self.assertEqual(text.split("\n")[2], "Limited: " + ", ".join(names[:10]) + ", +2 more")
        self.assertLessEqual(len(text), 1200)
        self.content([product(n, "limited") for n in names] + [product(n + "s", "no") for n in names], checked_days_ago=-1)
        text = self.report()
        self.assertLessEqual(len(text), 1200)
        self.assertTrue(text.split("\n")[0].endswith(FUTURE))
        self.assertEqual(text.split("\n")[-1], LAST)
        self.assertIn("Limited 12 · Sold out 12", text)

    def test_bad_today_and_unreadable_content_exit_codes_unchanged(self):
        self.content([product("Figs", "yes")], checked_days_ago=-1)
        self.assertEqual(self.run_report("--today", "2026-02-30", expect=2), "")
        (self.dir / "store.json").write_text("{not json", encoding="utf-8")
        self.run_report("--today", "2026-11-02", expect=1)


if __name__ == "__main__":
    unittest.main()
