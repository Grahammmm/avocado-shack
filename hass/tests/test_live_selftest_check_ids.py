"""RF1911-9: scripts/hass/live_selftest_parse.py health refuses check ids that only match before a trailing newline.
Run: python3 -B -m unittest hass.tests.test_live_selftest_check_ids"""

import json, subprocess, sys, unittest  # noqa: E401
from pathlib import Path

PARSER = Path(__file__).resolve().parents[2] / "scripts" / "hass" / "live_selftest_parse.py"
INVALID = "invalid health report: a problem has no valid check id\n"


def run_health(*checks):
    report = {"ok": not checks, "problems": [{"check": c} for c in checks]}
    p = subprocess.run(
        [sys.executable, "-B", str(PARSER), "health"],
        input=json.dumps(report), capture_output=True, text=True, timeout=30,
    )
    return p.returncode, p.stdout, p.stderr


class CheckIdTests(unittest.TestCase):
    def test_trailing_lf_check_id_is_refused(self):
        self.assertEqual(run_health("disk\n"), (3, INVALID, ""))

    def test_control_char_and_length_boundaries(self):
        for bad in ("disk\r", "disk\r\n", "disk\tx", "disk\x00", "di\nsk", "d\u00efsk", "", "a" * 65):
            with self.subTest(bad=bad):
                self.assertEqual(run_health(bad), (3, INVALID, ""))
        for good in ("a", "a" * 64):
            with self.subTest(good=good):
                self.assertEqual(run_health(good), (0, good + "\n", ""))

    def test_valid_ids_stay_sorted_unique_on_one_line(self):
        self.assertEqual(run_health("zeta", "disk", "zeta", "a-1"), (0, "a-1 disk zeta\n", ""))
        self.assertEqual(run_health(), (0, "\n", ""))


if __name__ == "__main__":
    unittest.main()
