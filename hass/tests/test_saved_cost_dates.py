"""RF1221-12: `margin <id> at <M>%` keeps its calculation when the saved cost's date cannot be read.
Offline: damaged synthetic metadata in the throwaway fixture state. Run:
python3 -B -m unittest hass.tests.test_saved_cost_dates -q
"""

from datetime import timedelta

from hass import margins
from hass.tests import test_purchase_cost as pc

FALLBACK = "Using your saved cost; I can't read when you gave it to me.\n"
BODY = margins.say(margins.compute("24", "12", "0", "35"))
ASK = f"margin {pc.AVO} at 35%"


class SavedDateTests(pc.CostTestCase):
    def saved(self):
        self.chat(f"cost {pc.AVO}: 24 for 12", "memory-saved")

    def damage(self, value):
        self.conv.db.execute("UPDATE memory SET created_at = ? WHERE key = ?", (value, f"cost.{pc.AVO}"))
        self.conv.db.commit()

    def test_malformed_saved_date_keeps_real_margin_reply(self):
        self.saved()
        for bad in ("", "not-a-date", b"\x00\xffcanary-blob"):
            self.damage(bad)
            got = self.chat(ASK, "margin")
            self.assertEqual(got, FALLBACK + BODY)
            self.assertNotIn("canary", got)
            self.assertNotIn("not-a-date", got)

    def test_naive_saved_date_is_not_assigned_the_host_timezone(self):
        self.saved()
        for naive in ("2026-11-02", "2026-11-02T17:00:00"):
            self.damage(naive)
            self.assertEqual(self.chat(ASK, "margin"), FALLBACK + BODY)

    def test_pacific_conversion_overflow_keeps_calculation(self):
        self.saved()
        for edge in ("0001-01-01T00:00:00+00:00", "0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-23:00"):
            self.damage(edge)
            self.assertEqual(self.chat(ASK, "margin"), FALLBACK + BODY)

    def test_aware_dates_preserve_existing_prefix_and_math(self):
        self.saved()
        self.now = pc.T0 + timedelta(hours=8)  # 2026-11-03T01:00Z, still Nov 2 in Los Angeles
        shrunk = margins.say(margins.compute("24", "12", "5", "35"))
        for stamp in ("2026-11-02T17:00:00+00:00", "2026-11-02T09:00:00-08:00", "2026-11-02T18:00:00+01:00"):
            self.damage(stamp)
            self.assertEqual(self.chat(ASK, "margin"), "Using the cost you gave me today at 9 am.\n" + BODY)
            self.assertEqual(self.chat(ASK + " shrink 5%", "margin"), "Using the cost you gave me today at 9 am.\n" + shrunk)

    def test_bad_date_read_is_readonly_and_duplicate_safe(self):
        self.saved()
        self.damage("not-a-date")
        before = self.rows()
        self.chat(ASK, "margin", FALLBACK + BODY, pid="m9")
        self.assertEqual(self.say(ASK, pid="m9"), "duplicate")
        self.replies()
        self.assertEqual(self.rows(), before)
        self.assertEqual((self.drafts(), self.calls, self.editor.applies), ([], [], 0))

    def test_missing_forgotten_and_numeric_refusals_stay_unchanged(self):
        self.assertEqual(self.chat(ASK, "margin"), pc.NONE)
        self.assertNotIn("memory", self.tables())
        self.saved()
        self.damage("not-a-date")
        self.assertTrue(self.chat(f"margin {pc.AVO} at 95%", "margin").startswith("I couldn't work that out."))
        self.chat(f"forget cost.{pc.AVO}", "memory-forgot")
        self.assertEqual(self.chat(ASK, "margin"), pc.NONE)


if __name__ == "__main__":
    import unittest
    unittest.main()
