"""RF1751-11: deeply nested self-test reports give the bounded invalid-report refusal, not a traceback."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

PARSER = Path(__file__).resolve().parents[1] / "scripts" / "hass" / "live_selftest_parse.py"
DEEP = "[" * 100000 + "]" * 100000
HEALTH = '{"ok": true, "problems": [], "extra": %s}'
INBOX = '{"pending": 1, "done": 3, "oldest_pending_minutes": 2, "extra": %s}'


def run(mode, text):
    p = subprocess.run(
        [sys.executable, "-B", str(PARSER), mode],
        input=text, capture_output=True, text=True, timeout=60,
    )
    return p.returncode, p.stdout, p.stderr


class DeepReportTests(unittest.TestCase):
    def test_health_deep_report_is_invalid_json(self):
        code, out, err = run("health", HEALTH % DEEP + "\n")
        self.assertEqual((code, out, err), (3, "invalid health report: report is not JSON\n", ""))

    def test_inbox_deep_report_is_invalid_json(self):
        code, out, err = run("inbox", INBOX % DEEP + "\n")
        self.assertEqual((code, out, err), (3, "invalid inbox report: report is not JSON\n", ""))

    def test_malformed_json_retains_existing_refusal(self):
        for mode in ("health", "inbox"):
            code, out, err = run(mode, "{not json\n")
            self.assertEqual((code, out, err), (3, f"invalid {mode} report: report is not JSON\n", ""))

    def test_valid_reports_and_last_nonempty_line_are_unchanged(self):
        shallow = json.dumps([[1, 2], {"a": [3]}])
        self.assertEqual(run("health", "note\n" + HEALTH % shallow + "\n\n\n"), (0, "\n", ""))
        self.assertEqual(run("inbox", "note\n" + INBOX % shallow + "\n\n"), (0, "1 2 3\n", ""))


if __name__ == "__main__":
    unittest.main()
