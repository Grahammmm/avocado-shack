"""RF0015-12 tests: social_draft's hidden --now admits only timezone-aware timestamps. Run:
python3 -m unittest hass.tests.test_social_draft_now -v

Synthetic content only; nothing is posted.
"""
import contextlib
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import social_draft
from hass.tests.test_social_draft_hike import content, hike

MODES = (["p1"], ["--hike", "h1"], ["--maker", "k"], ["--recap", "h1"])


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(social_draft, "load_content", return_value=content(hike())) as load, \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try: code = social_draft.main(argv, Path("c"), Path("s"))
        except SystemExit as e: code = e.code
    return code, out.getvalue(), err.getvalue(), load.call_count


class NowClockTests(unittest.TestCase):
    def test_date_only_and_naive_clock_are_usage(self):
        for bad in ("2026-10-01", "2026-10-01T00:00:00", "2026-10-01T00:00:00.123456"):
            code, out, err, loads = run(["--hike", "h1", "--now", bad])
            self.assertEqual((code, out, loads), (2, "", 0), bad)
            self.assertIn("--now needs a timezone offset", err)
            self.assertNotIn("Traceback", err)

    def test_malformed_clock_is_usage(self):
        for bad in ("", "soon", "2026-13-45T00:00:00Z", "2026-10-01T00:00:00+99:99"):
            code, out, err, loads = run(["--hike", "h1", "--now", bad])
            self.assertEqual((code, out, loads), (2, "", 0), bad)
            self.assertIn("--now needs", err)
            self.assertNotIn("Traceback", err)

    def test_aware_clocks_preserve_hike_decision(self):
        for now in ("2026-10-01T00:00:00Z", "2026-10-01T00:00:00+00:00", "2026-09-30T17:00:00-07:00"):
            code, out, err, loads = run(["--hike", "h1", "--now", now])
            self.assertEqual((code, loads), (0, 1), now)
            self.assertTrue(json.loads(out)["draft"])
        # same instant as the 16:00Z start, expressed at +05:00: not yet started; one minute later: started
        for now, ok in (("2026-10-17T21:00:00+05:00", True), ("2026-10-17T21:01:00+05:00", False)):
            code, out, _err, _loads = run(["--hike", "h1", "--now", now])
            self.assertEqual(json.loads(out)["draft"], ok, now)

    def test_all_modes_validate_supplied_clock(self):
        for mode in MODES:
            code, out, _err, loads = run([*mode, "--now", "2026-10-01"])
            self.assertEqual((code, out, loads), (2, "", 0), mode)
            code, _out, _err, loads = run([*mode, "--now", "2026-10-01T00:00:00Z"])
            self.assertIn(code, (0, 1), mode)
            self.assertEqual(loads, 1)

    def test_default_clock_help_and_exclusivity_unchanged(self):
        code, out, _err, loads = run(["--help"])
        self.assertEqual((code, loads), (0, 0))
        self.assertNotIn("--now", out)
        self.assertEqual(run([])[0], 2)
        self.assertEqual(run(["p1", "--hike", "h1"])[0], 2)
        code, out, _err, _loads = run(["--hike", "h1"])  # default clock is aware UTC; the fixture hike is long past by then or not, but never a crash
        self.assertIn(code, (0, 1))
        self.assertIn("draft", json.loads(out))

    def test_converter_keeps_instant_and_offset(self):
        got = social_draft._aware_clock("2026-10-01T05:00:00+05:30")
        self.assertEqual(got.utcoffset(), timedelta(hours=5, minutes=30))
        self.assertEqual(got, datetime(2026, 10, 1, 5, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))))


if __name__ == "__main__":
    unittest.main()
