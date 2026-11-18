"""HASS-CHAOS-1: the drunk-owner regression suite (hass/tests/chaos/) replays every case from its recorded tape: no network, no model.

A failing check that is not listed under the case's `known` findings fails this test (a regression). A `known` check that now passes
is printed as `fixed` by the runner; the builder who fixed it removes it from `known` in hass/tests/chaos/cases.json (see FIX-PLAN.md).
Run: python3 -B -m unittest hass.tests.test_chaos_suite -v   (or python3 -B hass/tests/chaos/run_chaos.py for the per-case lines)
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "chaos" / "run_chaos.py"


class ChaosSuite(unittest.TestCase):
    def test_every_case_replays_with_no_unexpected_failure(self):
        jobs = str(max(1, min(4, os.cpu_count() or 1)))
        with tempfile.TemporaryDirectory(prefix="hass-chaos-test-") as out:
            done = subprocess.run([sys.executable, "-B", str(RUNNER), "--jobs", jobs, "--out", out],
                                  capture_output=True, text=True, timeout=900, check=False)
        bad = [line for line in done.stdout.splitlines() if ": FAIL" in line]
        self.assertEqual(done.returncode, 0, "\n".join(bad) or done.stdout[-2000:] + done.stderr[-2000:])
        self.assertIn("merged 72/72 cases", done.stdout)


if __name__ == "__main__":
    unittest.main()
