"""RF1810-9 tests: audit records with impossible calendar timestamps are bad lines (synthetic data, temp dirs only).
Run: python3 -B -m unittest hass.tests.test_audit_calendar -q
"""

import json, subprocess, sys, tempfile, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

from hass import audit
from hass.content_model import REPO_ROOT

BASE = dict(at="2026-11-16T12:00:00Z", seq=1, action=audit.new_action("cal"), step="applied", who="owner", pack="till",
            target="till", env="sandbox", result="ok")
SCRIPT = REPO_ROOT / "hass" / "audit.py"


def line(**over) -> bytes:
    return audit._encode({**BASE, **over}) + b"\n"


class CalendarTests(unittest.TestCase):
    def test_impossible_audit_timestamp_is_bad_at(self):
        for at in ("2026-02-30T12:00:00Z", "2026-13-01T12:00:00Z", "0000-01-01T00:00:00Z", "2026-11-16T25:00:00Z",
                   "2026-11-16T12:60:00Z", "2026-11-16T12:00:60Z", "2026-00-10T12:00:00Z", "2026-11-00T12:00:00Z"):
            with self.subTest(at=at):
                self.assertEqual(audit.check({**BASE, "at": at}), ["bad value: at"])
                self.assertIsNone(audit._decode(line(at=at).rstrip(b"\n")))

    def test_leap_day_and_calendar_boundaries_remain_valid(self):
        for at in ("2028-02-29T12:00:00Z", "2026-11-16T00:00:00Z", "2026-12-31T23:59:59Z"):
            with self.subTest(at=at):
                self.assertEqual(audit.check({**BASE, "at": at}), [])
                self.assertIsNotNone(audit._decode(line(at=at).rstrip(b"\n")))
        self.assertEqual(audit.check({**BASE, "at": "2026-02-29T12:00:00Z"}), ["bad value: at"])

    def test_scan_and_cli_count_invalid_calendar_line(self):
        with tempfile.TemporaryDirectory(prefix="rf1810-") as tmp:
            folder = Path(tmp) / audit.FOLDER
            folder.mkdir(mode=0o700)
            day = folder / "2026-11-16.jsonl"
            data = line() + line(seq=2, at="2026-02-30T12:00:00Z")
            day.write_bytes(data)
            log = audit.AuditLog(tmp, lambda: datetime(2026, 11, 16, 12, tzinfo=timezone.utc))
            records, bad = log.scan_day(day)
            self.assertEqual((len(records), bad), (1, 1))
            run = subprocess.run([sys.executable, str(SCRIPT), "check", "--state", tmp], capture_output=True, text=True)
            self.assertEqual((run.returncode, json.loads(run.stdout)), (1, {"result": "bad", "lines": 1, "bad": 1, "days": 1}))
            self.assertEqual(day.read_bytes(), data)

    def test_timestamp_lexical_and_privacy_contract_survives(self):
        for at in (20261116, None, "2026-11-16T12:00:00+00:00", "2026-11-16T12:00:00.5Z", "2026-11-16t12:00:00z"):
            with self.subTest(at=at):
                problems = audit.check({**BASE, "at": at})
                self.assertEqual(problems, ["bad value: at"])
        self.assertNotIn("2026-02-30", " ".join(audit.check({**BASE, "at": "2026-02-30T12:00:00Z"})))


if __name__ == "__main__":
    unittest.main()
