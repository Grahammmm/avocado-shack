"""HASS-CHAT-1 tests: the worker cycle rides out a busy sqlite store instead of failing.

2026-11-09 19:50:01 the live worker logged "cycle failed: OperationalError" (class name only). Every Hass store is a
rollback-journal sqlite file with the default 5 s busy timeout, and other processes (the 5-minute health check, the receiver's
paused read) hold read locks; under load a commit can wait longer than 5 s and sqlite raises "database is locked". These tests
pin that the classifier matches sqlite's real message, that cycle() retries a busy store with backoff (and nothing else), and
that run() now logs sqlite's own short message. Run: python3 -m unittest hass.tests.test_worker_busy -v
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import host
from hass.tests.test_host import HostCase, event

LOCKED = sqlite3.OperationalError("database is locked")


class BusyClassifierTests(unittest.TestCase):
    def test_a_real_lock_is_busy_and_other_errors_are_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.sqlite3"
            holder = sqlite3.connect(path, isolation_level=None)
            holder.execute("CREATE TABLE t (x)")
            holder.execute("BEGIN EXCLUSIVE")
            other = sqlite3.connect(path, timeout=0.05, isolation_level=None)
            with self.assertRaises(sqlite3.OperationalError) as got:
                other.execute("INSERT INTO t VALUES (1)")
            holder.execute("ROLLBACK")
            holder.close()
            other.close()
        self.assertTrue(host.is_busy(got.exception), str(got.exception))
        self.assertFalse(host.is_busy(sqlite3.OperationalError("no such table: t")))
        self.assertFalse(host.is_busy(RuntimeError("database is locked")))


class CycleRetryTests(HostCase):
    def setUp(self):
        super().setUp()
        self.srv, self.work = self.server(), self.worker(False)
        self.waits = []
        self.work.sleep = self.waits.append

    def flaky(self, failures):
        real, calls = self.work.rx.drain, []

        def drain(*a, **kw):
            calls.append(1)
            if len(calls) <= failures:
                raise LOCKED
            return real(*a, **kw)
        return drain

    def test_busy_twice_then_the_message_is_answered(self):
        self.inbound(self.srv, self.seal(event("new-message")))
        with mock.patch.object(self.work.rx, "drain", self.flaky(2)):
            self.work.cycle()
        self.assertEqual(self.waits, [0.5, 1.0])
        self.assertEqual(len(self.relay_rows()), 1)  # answered once, no duplicate

    def test_still_busy_after_the_last_wait_raises_for_run_to_back_off(self):
        with mock.patch.object(self.work.rx, "drain", side_effect=LOCKED), self.assertRaises(sqlite3.OperationalError):
            self.work.cycle()
        self.assertEqual(self.waits, list(host.BUSY_WAITS))

    def test_any_other_error_is_raised_at_once(self):
        for exc in (sqlite3.OperationalError("no such table: drafts"), RuntimeError("crash")):
            with self.subTest(exc=exc), mock.patch.object(self.work.rx, "drain", side_effect=exc), self.assertRaises(type(exc)):
                self.work.cycle()
        self.assertEqual(self.waits, [])

    def test_run_logs_the_sqlite_message_not_only_the_class(self):
        stop = mock.Mock()
        stop.is_set.side_effect = [False, True]
        with mock.patch.object(self.work, "cycle", side_effect=LOCKED), self.assertLogs("hass.host", "ERROR") as logs:
            self.work.run(stop)
        self.assertEqual(logs.output, ["ERROR:hass.host:cycle failed: OperationalError: database is locked"])
        with mock.patch.object(self.work, "cycle", side_effect=RuntimeError("owner text here")), self.assertLogs("hass.host", "ERROR") as logs:
            stop.is_set.side_effect = [False, True]
            self.work.run(stop)
        self.assertEqual(logs.output, ["ERROR:hass.host:cycle failed: RuntimeError"])  # never a non-sqlite message


if __name__ == "__main__":
    unittest.main()
