"""Fixture-only tests for the attended pilot's inbound metadata receipt."""

from contextlib import closing, redirect_stdout
from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass.inbox import SCHEMA


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/pilot_inbound.py"
SPEC = importlib.util.spec_from_file_location("pilot_inbound", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)
SINCE = "2030-01-01T12:00:00+00:00"
UNTIL = "2030-01-01T12:01:00+00:00"
INSIDE = "2030-01-01T12:00:30.123456+00:00"
PAYLOAD = "synthetic-payload-marker"


def digest(provider_id):
    return sha256(provider_id.encode()).hexdigest()[:12]


class PilotInboundTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / "fixture #?.sqlite3"
        self.ids = []
        with closing(sqlite3.connect(self.db)) as db:
            db.executescript(SCHEMA)

    def add(self, name, received=INSIDE, state="done", disposition: str | bytes | None = "unreadable",
            done: str | bytes | None = UNTIL):
        provider_id = f"synthetic-provider-{name}"
        self.ids.append(provider_id)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("INSERT INTO inbound VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (provider_id, received, PAYLOAD if state == "pending" else None,
                        state, disposition, INSIDE, done))
        return digest(provider_id)

    def args(self, since=SINCE, until=UNTIL):
        return ["--inbox-db", str(self.db), "--since", since, "--until", until]

    def run_cli(self, *window):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *self.args(*window)],
                                capture_output=True, text=True, timeout=10)
        for marker in [PAYLOAD, str(self.db), *self.ids]:
            self.assertNotIn(marker, result.stdout + result.stderr)
        return result

    def report(self, code):
        result = self.run_cli()
        self.assertEqual((result.returncode, result.stderr), (code, ""))
        *rows, summary = map(json.loads, result.stdout.splitlines())
        return {row["provider_id"]: row for row in rows}, summary

    def test_inclusive_window_compares_instants_and_received_not_completion(self):
        # Text comparisons, second-level truncation or filtering by done_at misclassify these rows.
        self.add("before", "2030-01-01T11:59:59.999999+00:00", "pending", None, None)
        self.add("after", "2030-01-01T12:01:00.000001+00:00", "pending", None, None)
        offset_start = "2030-01-01T07:00:00-05:00"
        start = self.add("start", offset_start, "history", None, None)
        done = "2030-01-01T12:02:00+00:00"
        end = self.add("end", UNTIL, disposition="approved", done=done)
        rows, summary = self.report(0)
        self.assertEqual(rows, {
            start: dict(provider_id=start, received_at=offset_start, state="history", disposition="other", done_at=None),
            end: dict(provider_id=end, received_at=UNTIL, state="done", disposition="approved", done_at=done),
        })
        self.assertEqual(summary, {"counts": {"pending": 0, "done": 1, "history": 1}})

    def test_pending_is_listed_without_payload_and_sets_exit_one(self):
        # Skipping unfinished rows or returning success would clear an undrained queue.
        pending = self.add("pending", state="pending", disposition=None, done=None)
        before = self.db.read_bytes()
        rows, summary = self.report(1)
        self.assertEqual(rows, {pending: dict(provider_id=pending, received_at=INSIDE,
                                             state="pending", disposition="other", done_at=None)})
        self.assertEqual(summary, {"counts": {"pending": 1, "done": 0, "history": 0}})
        self.assertEqual(self.db.read_bytes(), before)

    def test_bad_times_are_visible_without_echoing_damaged_values(self):
        # SQL text filters can drop malformed received_at, and raw fallback would leak damaged cells.
        cases = (
            ("bad-received", "synthetic-bad-received\nmarker", UNTIL, "bad-time", UNTIL),
            ("bad-done", INSIDE, b"synthetic-bad-done", INSIDE, "bad-time"),
            ("no-zone", "2030-01-01T12:00:30", "2030-01-01", "bad-time", "bad-time"),
            ("utc-overflow", "0001-01-01T00:00:00+01:00", UNTIL, "bad-time", UNTIL),
        )
        expected = {self.add(name, received, done=done): (shown_received, shown_done)
                    for name, received, done, shown_received, shown_done in cases}
        rows, summary = self.report(0)
        self.assertEqual({key: (row["received_at"], row["done_at"]) for key, row in rows.items()}, expected)
        self.assertEqual(summary, {"counts": {"pending": 0, "done": len(cases), "history": 0}})

    def test_disposition_is_an_exact_allowlist_not_a_pattern(self):
        # Status-looking private values and suffixes must not pass a pattern/prefix check.
        known = ("unreadable", "npp-working", "npp-expired", "npp-unavailable", "proposed", "duplicate",
                 "approval-held", "ignored", "photo-refused:audio")
        unknown = ("synthetic-private", "approved\nsynthetic-private", "npp-private",
                   "photo-refused:synthetic-private", b"unreadable", None)
        expected = {self.add(f"known-{i}", disposition=code): code for i, code in enumerate(known)}
        expected.update({self.add(f"other-{i}", disposition=code): "other" for i, code in enumerate(unknown)})
        rows, _ = self.report(0)
        self.assertEqual({key: row["disposition"] for key, row in rows.items()}, expected)

    def test_query_never_reads_payload_and_connection_rejects_writes(self):
        # Redacting after SELECT * is not enough; deny payload access on the actual connection.
        self.add("guarded", state="pending", disposition=None, done=None)
        connect = sqlite3.connect

        def guarded_connect(*args, **kwargs):
            db = connect(*args, **kwargs)
            with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                db.execute("UPDATE inbound SET state = 'done'")

            def authorize(action, table, column, *_):
                return (sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ
                        and table == "inbound" and column == "payload" else sqlite3.SQLITE_OK)

            db.set_authorizer(authorize)
            return db

        with patch.object(REPORT.sqlite3, "connect", side_effect=guarded_connect) as guarded:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(REPORT.main(self.args()), 1)
            self.assertTrue(guarded.called)

    def test_invalid_window_and_missing_store_are_sanitized_errors(self):
        # An invalid window can look like a clean empty receipt; an ordinary open can create a missing store.
        for window in (("synthetic-invalid-bound", UNTIL), (SINCE, "2030-01-01T12:01:00"), (UNTIL, SINCE)):
            with self.subTest(window=window):
                result = self.run_cli(*window)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("timezone-aware", result.stderr)
                self.assertNotIn("synthetic-invalid-bound", result.stderr)
        self.db.unlink()
        result = self.run_cli()
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("could not read inbox store", result.stderr)
        self.assertFalse(self.db.exists())
