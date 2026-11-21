"""Offline CLI contract tests using only synthetic SQLite stores."""

from contextlib import closing, redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/transcript_latency_report.py"
DB_NAME = "transcript.sqlite3"
SINCE = "2030-03-01T12:00:00Z"
UNTIL = "2030-03-01T13:00:00Z"
PASS = "PASS transcript_latency_report"
FAIL = "FAIL transcript_latency_report"


class TranscriptLatencyReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "fixture ?#% state"
        self.state.mkdir()
        self.db = self.state / DB_NAME

    def create(self, rows=(), path=None):
        with closing(sqlite3.connect(path if path is not None else self.db)) as db, db:
            db.execute("CREATE TABLE events (utc TEXT, direction TEXT, kind TEXT, latency_ms INTEGER)")
            db.executemany("INSERT INTO events VALUES (?, ?, ?, ?)", rows)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def invoke(self, since=SINCE, until=UNTIL):
        return self.run_cli("--state", str(self.state), "--since", since, "--until", until)

    def assert_outcome(self, result, code, last):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], last)
        return lines

    def assert_findings(self, result, *reasons):
        lines = self.assert_outcome(result, 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])
        return lines

    def test_c1_full_pass(self):
        # Lexical ISO ordering, including the end, or aggregating outbound/malformed rows shifts the result.
        self.create([
            ("2030-03-01T07:00:00-05:00", "in", "text", 14),  # exactly since
            ("2030-03-01T16:59:59.999999+04:00", "in", "text", 2),
            (SINCE, "in", "photo_1-a", None),
            (SINCE, "in", "invalid\n", 7),
            (SINCE, "in", "a" * 33, 11),
            ("2030-03-01T11:59:59.999999Z", "in", "text", 999),
            ("2030-03-01T08:00:00-05:00", "in", "text", 999),  # exactly until
            (SINCE, "out", "text", 999),
            (SINCE, "IN", "text", 999),
            (None, "in", "text", 999),
            ("2030-03-01T12:05:00", "in", "text", 999),
            ("not-a-time", "in", "text", 999),
            ("not-a-time", "out", "text", 999),
        ])
        lines = self.assert_outcome(self.invoke(), 0, PASS)
        self.assertCountEqual(lines[:-1], [
            "count 5", "unparsed 3", "null-latency 1", "p50_ms 7", "p90_ms 14", "max_ms 14",
            "kind other p50_ms 7 p90_ms 11 max_ms 11",
            "kind photo_1-a p50_ms none p90_ms none max_ms none",
            "kind text p50_ms 2 p90_ms 14 max_ms 14",
        ])
        empty = self.assert_outcome(self.invoke("2030-03-02T00:00:00Z", "2030-03-03T00:00:00Z"), 0, PASS)
        self.assertCountEqual(empty[:-1], ["count 0", "unparsed 3", "null-latency 0",
                                          "p50_ms none", "p90_ms none", "max_ms none"])

    def test_c2_1_missing_db(self):
        # Opening SQLite in its default mode silently creates a missing store.
        self.assert_findings(self.invoke(), f"missing-db {DB_NAME}")
        self.assertEqual(list(self.state.iterdir()), [])

    def test_c2_2_unsafe_db(self):
        # Following a regular target or treating a dangling symlink as absent breaks this.
        target = self.root / "decoy.sqlite3"
        self.create(path=target)
        for link_target in (target, self.root / "absent"):
            with self.subTest(dangling=not link_target.exists()):
                self.db.symlink_to(link_target)
                self.assert_findings(self.invoke(), f"unsafe-db {DB_NAME}")
                self.db.unlink()
        self.db.mkdir()
        self.assert_findings(self.invoke(), f"unsafe-db {DB_NAME}")

    def test_c2_3_not_sqlite(self):
        # Connect alone can succeed without reading a corrupt store or validating its schema.
        self.db.write_bytes(b"synthetic non-SQLite bytes")
        self.assert_findings(self.invoke(), f"not-sqlite {DB_NAME}")
        self.db.unlink()
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("CREATE TABLE decoy (example TEXT)")
        self.assert_findings(self.invoke(), f"not-sqlite {DB_NAME}")
        columns = ("utc", "direction", "kind", "latency_ms")
        for missing in columns:
            with self.subTest(missing=missing):
                with closing(sqlite3.connect(self.db)) as db, db:
                    db.execute("DROP TABLE IF EXISTS events")
                    db.execute("CREATE TABLE events (" + ", ".join(c for c in columns if c != missing) + ")")
                self.assert_findings(self.invoke(), f"not-sqlite {DB_NAME}")

    def test_c2_4_bad_window(self):
        # Zone-less inputs, reversed windows and equivalent endpoints must not pass.
        self.create()
        for since, until in (("bad", UNTIL), (SINCE, "bad"), (SINCE[:-1], UNTIL),
                             (SINCE, UNTIL[:-1]), (UNTIL, SINCE),
                             (SINCE, "2030-03-01T07:00:00-05:00")):
            with self.subTest(since=since, until=until):
                self.assert_findings(self.invoke(since, until), "bad-window")

    def test_c2_5_bad_latency(self):
        # Reject only invalid in-window values; do not round reals or confuse NULL and zero.
        self.create([(SINCE, "in", "text", x) for x in (-1, 2.5, "synthetic", b"3", None, 0)] + [
            (UNTIL, "in", "text", -1), ("bad", "in", "text", -1), (SINCE, "out", "text", -1),
        ])
        lines = self.assert_findings(self.invoke(), "bad-latency 4")
        self.assertCountEqual(lines[:-1], ["count 6", "unparsed 1", "null-latency 1", "p50_ms 0",
                                          "p90_ms 0", "max_ms 0", "kind text p50_ms 0 p90_ms 0 max_ms 0",
                                          "FAIL bad-latency 4"])

    def test_c3_usage_exit_2(self):
        # Keep malformed CLI shape in argparse, not in the report findings protocol.
        valid = ("--state", str(self.state), "--since", SINCE, "--until", UNTIL)
        for args in (valid[:4], (*valid, "--bogus"), (*valid[:2], "--since", *valid[4:])):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")  # No last line for usage errors.
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # Detect rewrites, chmod, and SQLite-created journal/SHM files.
        def snapshot():
            return {p.relative_to(self.state): (p.read_bytes() if p.is_file() else None,
                                                p.stat().st_mtime_ns, p.stat().st_mode)
                    for p in self.state.rglob("*")}

        self.create([(SINCE, "in", "text", 1)])
        (self.state / "nested").mkdir()
        (self.state / "nested" / "decoy").write_bytes(b"untouched")
        before = snapshot()
        self.assert_outcome(self.invoke(), 0, PASS)
        self.assertEqual(snapshot(), before)

        # A valid WAL with an uncheckpointed commit and no SHM must not
        # create a sidecar or silently report stale data from the main file.
        source = self.root / "wal-source.sqlite3"
        self.create(path=source)
        with closing(sqlite3.connect(source)) as writer, writer:
            writer.execute("PRAGMA journal_mode = WAL")
            writer.execute("INSERT INTO events VALUES (?, 'in', 'text', 9)", (SINCE,))
            writer.commit()
            self.db.write_bytes(source.read_bytes())
            (self.state / (DB_NAME + "-wal")).write_bytes(Path(str(source) + "-wal").read_bytes())
        before = snapshot()
        self.assert_findings(self.invoke(), f"not-sqlite {DB_NAME}")
        self.assertEqual(snapshot(), before)

    def test_c5_no_private_values(self):
        # Row dumps, raw malformed kind/time, or exception/usage details could leak canaries.
        extras = ("CANARY message text", "CANARY chat", "CANARY sender", "CANARY full id", "f2" * 32)
        bad_kind, bad_time = "CANARY kind", "CANARY time"
        self.create()
        with closing(sqlite3.connect(self.db)) as db, db:
            for column in ("text", "chat", "sender", "provider_id", "attachments"):
                db.execute(f"ALTER TABLE events ADD COLUMN {column} TEXT")
            db.executemany("INSERT INTO events VALUES (?, 'in', ?, 5, ?, ?, ?, ?, ?)",
                           [(SINCE, bad_kind, *extras), (bad_time, "text", *extras)])
        # Enforce the column projection as well as scanning output: a SELECT
        # * followed by output filtering should not pass the privacy check.
        spec = importlib.util.spec_from_file_location("transcript_latency_report", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        connect = sqlite3.connect

        def projected_connect(database, **kwargs):
            self.assertEqual(database, self.db.absolute().as_uri() + "?mode=ro")
            self.assertIs(kwargs.get("uri"), True)
            db = connect(database, **kwargs)

            def authorize(action, table, column, _database, _source):
                if action == sqlite3.SQLITE_READ and (
                    table != "events" or column not in ("utc", "direction", "kind", "latency_ms")
                ):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            db.set_authorizer(authorize)
            return db

        stdout, stderr = StringIO(), StringIO()
        args = ["--state", str(self.state), "--since", SINCE, "--until", UNTIL]
        with patch.object(sqlite3, "connect", projected_connect), redirect_stdout(stdout), redirect_stderr(stderr):
            code = module.main(args)
        result = subprocess.CompletedProcess(args, code, stdout.getvalue(), stderr.getvalue())
        self.assertIn("kind other p50_ms 5 p90_ms 5 max_ms 5", self.assert_outcome(result, 0, PASS))
        bad_window = self.invoke(since=bad_time)
        self.assert_findings(bad_window, "bad-window")
        usage_error = self.run_cli("--state", str(self.state), "--since", SINCE, "--until", UNTIL,
                                   "--unknown", str(self.db))
        self.assertEqual(usage_error.returncode, 2)
        self.assertEqual(usage_error.stdout, "")
        for result in (result, bad_window, usage_error):
            for canary in (*extras, bad_kind, bad_time, str(self.state), str(self.db)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_nearest_rank(self):
        # For 10 values p50 isn't a mean and p90 isn't the max or interpolated.
        values = [90, 8, 100, 2, 11, 5, 70, 1, 4, 9]
        self.create([(SINCE, "in", "text", x) for x in values] + [(SINCE, "in", "text", None)])
        lines = self.assert_outcome(self.invoke(), 0, PASS)
        self.assertCountEqual(lines[:-1], ["count 11", "unparsed 0", "null-latency 1", "p50_ms 8",
                                          "p90_ms 90", "max_ms 100", "kind text p50_ms 8 p90_ms 90 max_ms 100"])


if __name__ == "__main__":
    unittest.main()
