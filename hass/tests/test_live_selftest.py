"""HASS-LIVE-AUDIT-1: scripts/hass/live_selftest.sh --synthetic-only (scripts/hass/live_selftest_synth.py) passes on
this checkout, and scripts/hass/live_selftest_model.py refuses an unknown case id before any model call.
Run: python3 -B -m unittest hass.tests.test_live_selftest"""

import subprocess, sys, unittest  # noqa: E401
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "hass"
ENV = {"HASS_PYTHON": sys.executable, "PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}


class LiveSelftestScript(unittest.TestCase):
    def test_synthetic_only_passes_and_touches_no_live_path(self):
        r = subprocess.run(["bash", str(SCRIPTS / "live_selftest.sh"), "--synthetic-only"], capture_output=True, text=True,
                           timeout=600, env=ENV, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('PASS synthetic {"failed": 0, "ran": 6, "synthetic": "pass"}', r.stdout)
        self.assertRegex(r.stdout, r"HASS-SELFTEST \S+Z pass=1 warn=0 fail=0 skip=0\n$")

    def test_model_helper_refuses_an_unknown_case_without_calling_a_model(self):
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "live_selftest_model.py"), "--url", "http://127.0.0.1:9",
                            "--model", "m", "--ids", "nope"], capture_output=True, text=True, timeout=60, cwd=ROOT)
        self.assertEqual((r.returncode, r.stdout.strip()), (2, '{"result": "error", "error": "--ids: unknown case id"}'))


if __name__ == "__main__":
    unittest.main()
