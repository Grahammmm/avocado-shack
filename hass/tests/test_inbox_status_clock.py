"""RF0110-4 (H16): `inbox status` never prints a negative oldest_pending_minutes; a future-stamped pending row sets
`clock_behind`. Synthetic inbox with an injectable clock. Run: python3 -m unittest hass.tests.test_inbox_status_clock -v
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path

from hass import inbox as inbox_mod
from hass.conversation import Inbound
from hass.tests.test_conversation import T0

PID = "pid-SENTINEL-4b2d"  # must never reach the output
NOW = T0 + timedelta(hours=2)


class ClockBehindTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.state.mkdir(mode=0o700)
        self.at = NOW
        self.box = inbox_mod.Inbox(str(self.state), T0.isoformat(), clock=lambda: self.at)
        self.addCleanup(self.box.close)

    def add(self, pid, enqueued_offset_min):
        self.at = NOW + timedelta(minutes=enqueued_offset_min)
        msg = Inbound(pid, "chat-fixture", "owner@example.invalid", "hours", False, "new", T0.isoformat())
        self.assertEqual(self.box.enqueue(msg), "queued")

    def report(self):
        return inbox_mod.status(str(self.state), NOW)

    def test_only_future_row_is_zero_and_clock_behind(self):
        self.add(PID, 120)
        report, code = self.report()
        self.assertEqual((report["oldest_pending_minutes"], report["clock_behind"], code), (0, True, 0))

    def test_past_row_wins_over_future_row(self):
        self.add("p1", -30)
        self.add("p2", 45)
        report, _ = self.report()
        self.assertEqual((report["oldest_pending_minutes"], report["clock_behind"]), (30, True))

    def test_row_stamped_exactly_now_is_zero_without_key(self):
        self.add("p1", 0)
        report, _ = self.report()
        self.assertEqual(report["oldest_pending_minutes"], 0)
        self.assertNotIn("clock_behind", report)

    def test_only_past_rows_keep_todays_value_without_key(self):
        self.add("p1", -90)
        self.add("p2", -10)
        report, _ = self.report()
        self.assertEqual(report["oldest_pending_minutes"], 90)
        self.assertNotIn("clock_behind", report)

    def test_no_pending_rows_is_none_without_key(self):
        report, _ = self.report()
        self.assertIsNone(report["oldest_pending_minutes"])
        self.assertNotIn("clock_behind", report)

    def test_malformed_time_is_unreadable_and_wins_over_future_row(self):
        self.add("p1", 120)
        self.add("p2", -5)
        self.box.db.execute("UPDATE inbound SET enqueued_at = 'garbage' WHERE provider_id = 'p2'")
        report, code = self.report()
        self.assertEqual((report["oldest_pending_minutes"], code), ("unreadable", 0))
        self.assertNotIn("clock_behind", report)

    def test_command_line_prints_clock_behind_and_no_id(self):
        self.add(PID, 120)
        out = io.StringIO()
        with redirect_stdout(out):
            code = inbox_mod.main(["status", "--state", str(self.state)], now=NOW)
        lines = out.getvalue().splitlines()
        self.assertEqual((code, len(lines)), (0, 1))
        report = json.loads(lines[0])
        self.assertIs(report["clock_behind"], True)
        self.assertEqual(report["oldest_pending_minutes"], 0)
        self.assertNotIn(PID, out.getvalue())


if __name__ == "__main__":
    unittest.main()
