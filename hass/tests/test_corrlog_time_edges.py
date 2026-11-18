"""Calendar-overflow containment for correspondence-log timestamps (synthetic, offline)."""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass import corrlog

FIXED = datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)
UNKNOWN = "an unknown time"
GOOD = "2026-11-16T18:00:00+00:00"
EDGE = "9999-12-31T23:59:59-14:00"


def _row(at, kind, reason):
    return json.dumps({"at": at, "kind": kind, "reason": reason})


class TimeEdges(unittest.TestCase):
    def _state(self, now=FIXED):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = Path(tmp.name)
        day = state / corrlog.FOLDER
        day.mkdir()
        path = day / f"{now:%Y-%m-%d}.jsonl"
        path.write_text(_row(now.isoformat(), "slow", "healthy-control") + "\n" + _row(EDGE, "error", "edge-row") + "\n")
        return state, path

    def test_local_calendar_edges_return_unknown_time(self):
        for iso in ("0001-01-01T00:00:00+00:00", "0001-01-01T00:00:00+14:00", EDGE):
            self.assertEqual(corrlog._local(iso, None), UNKNOWN, iso)

    def test_mixed_problems_report_keeps_rows_when_time_conversion_overflows(self):
        state, path = self._state()
        before = path.read_bytes()
        log = corrlog.CorrLog(state, lambda: FIXED)
        self.assertEqual(len(log.rows()), 2)
        text = corrlog.problems_text(log)
        self.assertIn("The last 2 problems", text)
        self.assertIn("healthy-control", text)
        self.assertIn("edge-row", text)
        self.assertEqual(text.count(UNKNOWN), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_problems_cli_contains_bad_time_without_losing_good_row(self):
        now = datetime.now(timezone.utc)
        state, path = self._state(now)
        before = path.read_bytes()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(corrlog.main(["problems", "--state", str(state)], out=out), 0)
        self.assertEqual(err.getvalue(), "")
        self.assertIn(UNKNOWN, out.getvalue())
        self.assertIn("healthy-control", out.getvalue())
        self.assertEqual(path.read_bytes(), before)

    def test_local_ordinary_and_parse_fallbacks_are_unchanged(self):
        self.assertEqual(corrlog._local(GOOD, None), "Mon Nov 16, 10:00 am")
        self.assertEqual(corrlog._local("2026-11-16T10:00:00-08:00", None), "Mon Nov 16, 10:00 am")
        self.assertEqual(corrlog._local("2026-07-16T17:00:00+00:00", None), "Thu Jul 16, 10:00 am")
        self.assertEqual(corrlog._local("2026-07-16T10:00:00-07:00", None), "Thu Jul 16, 10:00 am")
        self.assertEqual(corrlog._local(None, None), UNKNOWN)
        self.assertEqual(corrlog._local("not a date", None), UNKNOWN)

    def test_rendering_does_not_change_weekly_or_reader_membership(self):
        state, path = self._state()
        before = path.read_bytes()
        log = corrlog.CorrLog(state, lambda: FIXED)
        first = log.rows()
        corrlog.problems_text(log)
        self.assertEqual(log.rows(), first)
        self.assertEqual(sum(count for _, count in log.top()), 2)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
