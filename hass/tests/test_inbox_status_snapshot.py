"""RF0240-11 (H16/H17): one `inbox.py status` call reports one SQLite snapshot even while another connection writes.

A real second connection commits right after the state counts are read (via the reader's trace callback).
Run: python3 -B -m unittest hass.tests.test_inbox_status_snapshot -q
"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import inbox as inbox_mod

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW = T0 + timedelta(minutes=30)
SENTINEL = "pid-SENTINEL-1b2c"


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.state.mkdir(mode=0o700)
        self.db = self.state / "inbox.sqlite3"
        w = sqlite3.connect(self.db)
        w.executescript(inbox_mod.SCHEMA)
        w.execute("PRAGMA journal_mode=WAL")  # fixture only: lets the competing commit finish mid-report
        w.execute("INSERT INTO meta VALUES ('start_at', ?)", (T0.isoformat(),))
        w.execute("INSERT INTO inbound VALUES (?, ?, NULL, 'pending', NULL, ?, NULL)",
                  (SENTINEL, T0.isoformat(), T0.isoformat()))
        w.commit()
        self.writer = w
        self.addCleanup(w.close)

    def status_with_writer(self, write_sql):
        """Run the real status(); after the state-count SELECT, commit write_sql on the independent writer."""
        fired, real_connect = [], sqlite3.connect

        def connect(*a, **k):
            db = real_connect(*a, **k)

            def trace(sql):
                if sql.startswith("SELECT value FROM meta") and not fired:
                    fired.append(1)
                    for stmt in write_sql:
                        self.writer.execute(stmt)
                    self.writer.commit()
            db.set_trace_callback(trace)
            return db

        with mock.patch.object(inbox_mod.sqlite3, "connect", connect):
            result = inbox_mod.status(self.state, NOW)
        self.assertTrue(fired)
        return result

    def test_concurrent_drain_cannot_mix_state_counts_dispositions_and_age(self):
        report, code = self.status_with_writer(
            [f"UPDATE inbound SET state='done', disposition='handled' WHERE provider_id='{SENTINEL}'"])
        self.assertEqual(code, 0)
        self.assertEqual((report["pending"], report["done"], report["dispositions"], report["oldest_pending_minutes"]),
                         (1, 0, {}, 30))
        self.assertEqual(self.writer.execute("SELECT state FROM inbound").fetchall(), [("done",)])
        self.assertNotIn(SENTINEL, json.dumps(report))

    def test_concurrent_enqueue_and_nonce_commit_are_not_partially_visible(self):
        report, _ = self.status_with_writer([
            f"INSERT INTO inbound VALUES ('other', '{T0.isoformat()}', NULL, 'pending', NULL, '{T0.isoformat()}', NULL)",
            "INSERT INTO nonces VALUES ('n1', 'x')"])
        self.assertEqual((report["pending"], report["nonces"]), (1, 0))
        fresh, _ = inbox_mod.status(self.state, NOW)
        self.assertEqual((fresh["pending"], fresh["nonces"]), (2, 1))

    def test_next_status_call_observes_completed_writer(self):
        self.status_with_writer(
            [f"UPDATE inbound SET state='done', disposition='handled' WHERE provider_id='{SENTINEL}'"])
        fresh, _ = inbox_mod.status(self.state, NOW)
        self.assertEqual((fresh["pending"], fresh["done"], fresh["dispositions"], fresh["oldest_pending_minutes"]),
                         (0, 1, {"handled": 1}, None))

    def test_reader_closes_and_releases_lock_on_error(self):
        closed, real_connect = [], sqlite3.connect

        class Spy(sqlite3.Connection):
            def close(self):
                closed.append(1)
                super().close()

        def connect(*a, **k):
            return real_connect(*a, factory=Spy, **k)

        with mock.patch.object(inbox_mod.sqlite3, "connect", connect):
            self.assertEqual(inbox_mod.status(self.state, NOW)[1], 0)
            with mock.patch.object(inbox_mod, "_zoned", side_effect=sqlite3.DatabaseError("boom")):
                self.assertEqual(inbox_mod.status(self.state, NOW), ({"result": "unreadable"}, 1))
        self.assertEqual(len(closed), 2)
        self.writer.execute("INSERT INTO nonces VALUES ('after', 'x')")
        self.writer.commit()

    def test_missing_and_unreadable_files_keep_baseline_results(self):
        empty = Path(self.state.parent) / "empty"
        empty.mkdir(mode=0o700)
        self.assertEqual(inbox_mod.status(empty, NOW), ({"result": "ok", "inbox": "none"}, 0))
        bad = Path(self.state.parent) / "bad"
        bad.mkdir(mode=0o700)
        (bad / "inbox.sqlite3").write_bytes(b"not a database" * 100)
        self.assertEqual(inbox_mod.status(bad, NOW), ({"result": "unreadable"}, 1))


if __name__ == "__main__":
    unittest.main()
