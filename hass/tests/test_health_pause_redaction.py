"""Exercise pause timestamp redaction in the emitted health report with SQLite fixtures only."""
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass import health

NOW = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


class HealthPauseRedactionTest(unittest.TestCase):
    def report(self, cell):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / "config.json").write_text(json.dumps({
                "worktree": str(state / "unused"),
                "settings": {"ownerSenders": ["owner@example.invalid"], "ownerChat": "chat@example.invalid",
                             "approvalTtlSeconds": 600},
            }), encoding="utf-8")
            with contextlib.closing(sqlite3.connect(state / health.DB)) as db, db:
                db.execute("CREATE TABLE control (name TEXT PRIMARY KEY, set_at TEXT NOT NULL)")
                db.execute("INSERT INTO control VALUES ('paused', ?)", (cell,))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = health.main(["--state", tmp], now=NOW)
            return code, out.getvalue()

    def test_unreadable_pause_reports_fixed_detail_without_echoing_cell(self):
        # A permissive parser or formatting the unvalidated row would leak the cell in JSON.
        for cell, forbidden in (("synthetic-private-marker", "synthetic-private-marker"),
                                ("2026-11-02T15:00:00", "2026-11-02T15:00:00"),
                                (b"2026-11-02T15:00:00+00:00", "2026-11-02T15:00:00+00:00")):
            with self.subTest(cell=cell):
                code, output = self.report(cell)
                self.assertNotIn(forbidden, output)
                report = json.loads(output)
                self.assertEqual(code, 1)
                self.assertEqual(report["problems"], [{"check": "paused-long", "detail": "unreadable time"}])
                self.assertIn({"check": "paused", "detail": "unreadable time"}, report["info"])

    def test_aware_pause_is_normalized_and_age_uses_the_instant(self):
        # An unusual separator must be normalized; ignoring the offset would swap the age verdicts.
        for cell, detail, problems in (
                ("2026-11-01 16:30:00-02:00", "2026-11-01T16:30:00-02:00", []),
                ("2026-11-01 17:30:00+02:00", "2026-11-01T17:30:00+02:00",
                 [{"check": "paused-long", "detail": "over 24 h"}])):
            with self.subTest(cell=cell):
                code, output = self.report(cell)
                report = json.loads(output)
                self.assertEqual(code, int(bool(problems)))
                self.assertEqual(report["problems"], problems)
                self.assertIn({"check": "paused", "detail": detail}, report["info"])
