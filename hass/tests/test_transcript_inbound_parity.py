"""Offline CLI contract for the count-only inbound/transcript comparison."""

from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/transcript_inbound_parity.py"
PASS = "PASS transcript_inbound_parity"
FAIL = "FAIL transcript_inbound_parity"
SINCE = "2000-01-01T10:00:00+00:00"
UNTIL = "2000-01-01T11:00:00+00:00"
MID = "2000-01-01T10:30:00+00:00"
OFFSET_START = "2000-01-01T05:00:00-05:00"
BEFORE = "2000-01-01T04:59:59-05:00"
CANARIES = (
    "synthetic-provider-canary", "synthetic-text-canary", "synthetic-chat-canary",
    "synthetic-sender-canary", "synthetic-digest-canary",
)


class TranscriptInboundParityTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / "synthetic state ?#%"
        self.root.mkdir()
        self.inbox = self.root / "inbox.sqlite3"
        self.transcript = self.root / "transcript.sqlite3"

    def make_inbox(self, rows=()):
        with closing(sqlite3.connect(self.inbox)) as db, db:
            db.execute("CREATE TABLE inbound(provider_id TEXT PRIMARY KEY, state TEXT, received_at TEXT)")
            db.executemany("INSERT INTO inbound VALUES (?, ?, ?)", rows)

    def make_transcript(self, rows=(), *, wal=False):
        with closing(sqlite3.connect(self.transcript)) as db, db:
            if wal:
                self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            db.execute("CREATE TABLE events(provider_id TEXT, direction TEXT, utc TEXT, "
                       "text TEXT, chat TEXT, sender TEXT, attachments TEXT)")
            db.execute("CREATE UNIQUE INDEX inbound_id ON events(provider_id) WHERE direction='in'")
            db.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                           ((*row, *CANARIES[1:]) for row in rows))

    def invoke(self, *options, since=SINCE, until=UNTIL):
        args = options or ("--state", str(self.root), "--since", since, "--until", until)
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def assert_result(self, result, code, *lines):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stdout, "\n".join(lines) + "\n" if lines else "")
        if code != 2:
            self.assertEqual(result.stderr, "")

    def test_c1_full_pass(self):
        # String ordering, either wrong endpoint, or malformed-time inclusion changes these counts.
        self.make_inbox([
            ("start", "done", OFFSET_START), ("middle", "done", MID),
            ("before", "done", BEFORE), ("end", "done", UNTIL),
            ("missing-time", "done", None), ("invalid-time", "done", "invalid"),
        ])
        self.make_transcript([
            ("start", "in", SINCE), ("middle", "in", MID), ("middle", "out", MID),
            ("before", "in", BEFORE), ("end", "in", UNTIL),
            ("extra", "in", MID), ("extra-out", "out", MID),
            ("no-zone", "in", "2000-01-01T10:30:00"),
        ])
        self.assert_result(self.invoke(), 0, "inbound-done 2", "matched 2",
                           "note transcript-only 1", "unparsed 3", PASS)

    def test_c2_1_missing_db(self):
        # A normal read/write connect would create the absent databases.
        self.assert_result(self.invoke(), 1, "FAIL missing-db inbox.sqlite3",
                           "FAIL missing-db transcript.sqlite3", FAIL)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_c2_2_unsafe_db(self):
        # The symlink points at a usable inbox; following it wouldn't yield unsafe-db.
        self.make_inbox()
        target = self.root / "db-fixture"
        self.inbox.rename(target)
        self.inbox.symlink_to(target.name)
        self.transcript.mkdir()
        self.assert_result(self.invoke(), 1, "FAIL unsafe-db inbox.sqlite3",
                           "FAIL unsafe-db transcript.sqlite3", FAIL)

    def test_c2_3_not_sqlite(self):
        # SQLite may accept connect() on bad bytes; reading required columns must still fail.
        self.inbox.write_bytes(b"not a database fixture")
        with closing(sqlite3.connect(self.transcript)) as db, db:
            db.execute("CREATE TABLE events(provider_id TEXT, direction TEXT)")
        self.assert_result(self.invoke(), 1, "FAIL not-sqlite inbox.sqlite3",
                           "FAIL not-sqlite transcript.sqlite3", FAIL)

    def test_c2_4_bad_window(self):
        # Do not normalize naive times, allow equal instants, or silently swap reversed endpoints.
        self.make_inbox()
        self.make_transcript()
        for since, until in (("invalid", UNTIL), (SINCE, "2000-01-01T11:00:00"),
                             (SINCE, OFFSET_START), (UNTIL, SINCE)):
            with self.subTest(since=since, until=until):
                self.assert_result(self.invoke(since=since, until=until), 1, "FAIL bad-window", FAIL)

    def test_c2_5_inbound_not_in_transcript(self):
        # Outbound and stale receipts don't cover handled inbound rows, even with the same ID.
        self.make_inbox([(key, "done", MID) for key in ("ok", "gone", "out", "stale", "invalid")])
        self.make_transcript([
            ("ok", "in", MID), ("out", "out", MID), ("stale", "in", UNTIL),
            ("invalid", "in", "invalid"), ("unrelated", "in", MID),
        ])
        self.assert_result(self.invoke(), 1, "inbound-done 5", "matched 1",
                           "note transcript-only 1", "unparsed 1",
                           "FAIL inbound-not-in-transcript 4", FAIL)

    def test_c3_usage_exit_2(self):
        # A missing argument, missing value, or unknown flag must stay a usage error.
        for args in (("--state", str(self.root), "--since", SINCE),
                     ("--state", str(self.root), "--since", SINCE, "--until"),
                     ("--state", str(self.root), "--since", SINCE, "--until", UNTIL, "--extra")):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assert_result(result, 2)  # C3 has no stdout line, including the last.
                self.assertTrue(result.stderr.startswith("usage:"))

    def test_c4_read_only(self):
        # A WAL-mode store without sidecars detects read-only readers that still make sidecars.
        self.make_inbox()
        self.make_transcript(wal=True)

        def snapshot():
            return {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
                    if p.is_file() else None for p in self.root.rglob("*")}

        before = snapshot()
        self.assertEqual(set(before), {Path(self.inbox.name), Path(self.transcript.name)})
        self.assert_result(self.invoke(), 0, "inbound-done 0", "matched 0",
                           "note transcript-only 0", "unparsed 0", PASS)
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Check both result and error paths for ID, row, argv, path, or exception leakage.
        self.make_inbox([(CANARIES[0], "done", MID), ("only-inbox", "done", MID)])
        self.make_transcript([(CANARIES[0], "in", MID)])
        finding = self.invoke()
        self.assert_result(finding, 1, "inbound-done 2", "matched 1", "note transcript-only 0",
                           "unparsed 0", "FAIL inbound-not-in-transcript 1", FAIL)
        usage = self.invoke("--state", str(self.root), "--since", SINCE, "--until", UNTIL,
                            "--unexpected", str(self.root))
        self.assert_result(usage, 2)
        for result in (finding, usage):
            for stream in (result.stdout, result.stderr):
                for canary in (*CANARIES, "only-inbox", str(self.root)):
                    self.assertNotIn(canary, stream)

    def test_c6_pending_history_ignored(self):
        # A pending transcript row is informational, and an absent history row isn't a finding.
        self.make_inbox([("pending", "pending", MID), ("history", "history", MID)])
        self.make_transcript([("pending", "in", MID)])
        self.assert_result(self.invoke(), 0, "inbound-done 0", "matched 0",
                           "note transcript-only 1", "unparsed 0", PASS)
