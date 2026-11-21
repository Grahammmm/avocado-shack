"""Offline CLI contract tests using disposable audit stores."""

from contextlib import closing, redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/interpreter_audit_report.py"
SPEC = importlib.util.spec_from_file_location("interpreter_audit_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)
SINCE = "2031-02-03T12:00:00+00:00"
UNTIL = "2031-02-03T13:00:00+00:00"
DB_NAME = "conversation.sqlite3"
PASS = "PASS interpreter_audit_report"
FAIL = "FAIL interpreter_audit_report"
SCHEMA = """CREATE TABLE interpreter_audit (
    at TEXT, backend TEXT, fallback INTEGER, primary_error TEXT, error TEXT, seconds REAL
)"""


class InterpreterAuditReportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "state #?% snapshot"
        self.root.mkdir()
        self.db = self.root / DB_NAME

    def seed(self, rows=(), schema=SCHEMA):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute(schema)
            if rows:
                db.executemany("INSERT INTO interpreter_audit VALUES (?, ?, ?, ?, ?, ?)", rows)

    def invoke(self, *extra, since=SINCE, until=UNTIL, argv=None, env=None):
        if argv is None:
            argv = ["--state", str(self.root), "--since", since, "--until", until, *extra]
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *argv], cwd=self.root,
                              capture_output=True, text=True, timeout=10, env=env)

    def assert_result(self, result, exit_code, last):
        self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[-1], last)
        return lines

    def assert_findings(self, result, *reasons):
        lines = self.assert_result(result, 1, FAIL)
        self.assertEqual([line for line in lines[:-1] if line.startswith("FAIL ")],
                         [f"FAIL {reason}" for reason in reasons])
        return lines

    def input_state(self):
        return self.root.stat().st_mtime_ns, {
            path.relative_to(self.root): (
                None if path.is_dir() else path.read_bytes(),
                path.stat().st_mtime_ns,
                path.stat().st_mode,
            )
            for path in self.root.rglob("*")
        }

    def test_c1_full_pass(self):
        # Lexical time filtering, inclusive end, interpolated ranks, and counting
        # NULL durations would each change this report.
        rows = [("2031-02-03T07:00:00-05:00", "cloud", 0, None, None, 10)]
        rows += [(SINCE, "cloud", 0, None, None, seconds) for seconds in range(8, 0, -1)]
        rows += [
            (SINCE, "local", 1, "time_out", "no-result", 9.1254),
            (SINCE, "local", 1, "time_out", None, None),
            ("2031-02-03T12:59:59.999999Z", "local", 0, None, "no-result", None),
            ("2031-02-03T06:59:59.999999-05:00", "before", 1, "hidden", None, 99),
            ("2031-02-03T08:00:00-05:00", "after", 1, "hidden", None, 99),
            ("2031-02-03T12:30:00", "naive", 1, "hidden", None, 99),
            (None, "missing", 1, "hidden", None, 99),
            ("invalid timestamp", "malformed", 1, "hidden", None, 99),
        ]
        self.seed(rows)
        result = self.invoke("--expect-backend", "cloud", "--expect-backend", "local")
        self.assertEqual(self.assert_result(result, 0, PASS), [
            "calls 12", "backend cloud 9", "backend local 3", "fallback 2",
            "primary-error time_out 2", "error no-result 2",
            "seconds p50 5.000 p90 9.125", "unparsed 3", PASS,
        ])

    def test_c2_1_missing_db(self):
        # A default SQLite connection would create the missing file.
        self.assertEqual(self.assert_findings(self.invoke(), f"missing-db {DB_NAME}"),
                         [f"FAIL missing-db {DB_NAME}", FAIL])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_c2_2_unsafe_db(self):
        # A stat/exists check would follow an existing link or miss a dangling one.
        self.seed()
        target = self.root / "target.sqlite3"
        self.db.rename(target)
        for kind in ("symlink", "dangling", "directory"):
            with self.subTest(kind=kind):
                if kind == "directory":
                    self.db.mkdir()
                else:
                    self.db.symlink_to(target if kind == "symlink" else self.root / "absent")
                self.assertEqual(self.assert_findings(self.invoke(), f"unsafe-db {DB_NAME}"),
                                 [f"FAIL unsafe-db {DB_NAME}", FAIL])
                self.db.rmdir() if kind == "directory" else self.db.unlink()

    def test_c2_3_not_sqlite(self):
        # Connecting may succeed on corrupt bytes until the first query; a
        # missing required column is not the lazy-table case either.
        self.db.write_bytes(b"this is not a database")
        self.assertEqual(self.assert_findings(self.invoke(), f"not-sqlite {DB_NAME}"),
                         [f"FAIL not-sqlite {DB_NAME}", FAIL])
        self.db.unlink()
        self.seed(schema=SCHEMA.replace(", seconds REAL", ""))
        self.assertEqual(self.assert_findings(self.invoke(), f"not-sqlite {DB_NAME}"),
                         [f"FAIL not-sqlite {DB_NAME}", FAIL])

    def test_c2_4_bad_window(self):
        # Zone-less and malformed bounds aren't argparse errors; compare actual instants.
        self.seed()
        for since, until in (("broken", UNTIL), (SINCE, "2031-02-03T13:00:00"),
                             ("2031-02-03T12:00:00", UNTIL), (SINCE, "broken"),
                             (SINCE, "2031-02-03T07:00:00-05:00"), (UNTIL, SINCE)):
            with self.subTest(since=since, until=until):
                self.assertEqual(self.assert_findings(self.invoke(since=since, until=until),
                                                      "bad-window"), ["FAIL bad-window", FAIL])

    def test_c2_5_unexpected_backend(self):
        # Per-row FAIL lines would duplicate one finding; comparing only the
        # emitted label would let a malformed backend through as literal `other`.
        self.seed([(SINCE, backend, 0, None, None, None) for backend in
                   ("cloud", "local", "local", "Invalid Backend", "other")])
        lines = self.assert_findings(self.invoke("--expect-backend", "cloud", "--expect-backend", "other"),
                                     "unexpected-backend local", "unexpected-backend other")
        self.assertEqual(lines[:5], ["calls 5", "backend cloud 1", "backend local 2",
                                     "backend other 2", "fallback 0"])

    def test_c3_usage_exit_2(self):
        # Missing and unknown options must not accidentally enter named-finding handling.
        for result in (self.invoke(argv=[]), self.invoke("--unknown-flag"), self.invoke("--expect-backend")):
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")  # No last line on a usage error.
            self.assertTrue(result.stderr.startswith("usage: "))

    def test_c4_read_only(self):
        # Neither SQLite nor tempfile may create files inside the input directory.
        with closing(sqlite3.connect(self.db)) as writer, writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute(SCHEMA)
            writer.execute("INSERT INTO interpreter_audit VALUES (?, 'local', 0, NULL, NULL, 1)", (SINCE,))
        self.assertEqual(set(self.root.iterdir()), {self.db})
        before = self.input_state()
        result = self.invoke(env={**os.environ, "TMPDIR": str(self.root)})
        self.assertEqual(self.assert_result(result, 0, PASS), [
            "calls 1", "backend local 1", "fallback 0", "seconds p50 1.000 p90 1.000", "unparsed 0", PASS,
        ])
        self.assertEqual(self.input_state(), before)

    def test_a1_uncheckpointed_wal(self):
        # Rejecting the WAL or reading only the main DB would lose the second call.
        source = self.root.parent / DB_NAME
        wal = self.db.with_name(DB_NAME + "-wal")
        with closing(sqlite3.connect(source)) as writer:
            self.assertEqual(writer.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute(SCHEMA)
            writer.execute("INSERT INTO interpreter_audit VALUES (?, 'cloud', 0, NULL, NULL, 1)", (SINCE,))
            writer.commit()
            self.assertEqual(writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone(), (0, 0, 0))
            writer.execute("INSERT INTO interpreter_audit VALUES (?, 'local', 1, 'time_out', NULL, 2)", (SINCE,))
            writer.commit()
            shutil.copyfile(source, self.db)
            shutil.copyfile(source.with_name(wal.name), wal)
        self.assertGreater(wal.stat().st_size, 0)
        self.assertEqual(set(self.root.iterdir()), {self.db, wal})
        before = self.input_state()
        self.assertEqual(self.assert_result(self.invoke(), 0, PASS), [
            "calls 2", "backend cloud 1", "backend local 1", "fallback 1", "primary-error time_out 1",
            "seconds p50 1.000 p90 2.000", "unparsed 0", PASS,
        ])
        self.assertEqual(self.input_state(), before)

    def test_a1_harmless_journal(self):
        # A regular zero-byte journal must not trigger a blanket sidecar refusal.
        self.seed([(SINCE, "local", 0, None, None, None)])
        self.db.with_name(DB_NAME + "-journal").write_bytes(b"")
        before = self.input_state()
        self.assertEqual(self.assert_result(self.invoke(), 0, PASS), [
            "calls 1", "backend local 1", "fallback 0", "seconds none", "unparsed 0", PASS,
        ])
        self.assertEqual(self.input_state(), before)

    def test_a1_hot_journal(self):
        # Ignoring a hot journal can expose an uncommitted audit row change.
        source = self.root.parent / DB_NAME
        journal = self.db.with_name(DB_NAME + "-journal")
        with closing(sqlite3.connect(source)) as writer:
            writer.execute("PRAGMA journal_mode=DELETE")
            writer.execute("PRAGMA synchronous=FULL")
            writer.execute(SCHEMA)
            writer.execute("INSERT INTO interpreter_audit VALUES (?, 'cloud', 0, NULL, NULL, NULL)", (SINCE,))
            writer.execute("CREATE TABLE padding (data BLOB)")
            writer.executemany("INSERT INTO padding VALUES (zeroblob(4096))", [()] * 8)
            writer.commit()
            committed = source.read_bytes()
            # Force dirty pages to disk without committing, then copy the crash snapshot.
            writer.execute("PRAGMA cache_size=1")
            writer.execute("UPDATE interpreter_audit SET backend = 'local'")
            writer.execute("UPDATE padding SET data = randomblob(4096)")
            shutil.copyfile(source, self.db)
            shutil.copyfile(source.with_name(journal.name), journal)
        self.assertNotEqual(self.db.read_bytes(), committed)
        before = self.input_state()
        self.assertEqual(self.assert_result(self.invoke(), 0, PASS), [
            "calls 1", "backend cloud 1", "fallback 0", "seconds none", "unparsed 0", PASS,
        ])
        self.assertEqual(self.input_state(), before)

    def test_a1_symlinked_sidecar(self):
        # Following a symlink would accept an otherwise harmless empty sidecar.
        self.seed()
        target = self.root.parent / "empty"
        target.touch()
        for suffix in ("-wal", "-journal"):
            with self.subTest(suffix=suffix):
                sidecar = self.db.with_name(DB_NAME + suffix)
                sidecar.symlink_to(target)
                self.assertEqual(self.assert_findings(self.invoke(), f"not-sqlite {DB_NAME}"),
                                 [f"FAIL not-sqlite {DB_NAME}", FAIL])
                self.assertTrue(sidecar.is_symlink())
                sidecar.unlink()

    def assert_a2_temp_fallback(self):
        self.seed([(SINCE, "local", 0, None, None, None)])
        before = self.input_state()
        parent_mtime = self.root.parent.stat().st_mtime_ns
        self.assertEqual(self.assert_result(self.invoke(), 0, PASS), [
            "calls 1", "backend local 1", "fallback 0", "seconds none", "unparsed 0", PASS,
        ])
        self.assertEqual(self.input_state(), before)
        # Neither the state tree nor its unlisted parent is a valid fallback.
        self.assertEqual(self.root.parent.stat().st_mtime_ns, parent_mtime)

    def test_a2_tmpdir_is_input(self):
        # Reject equality rather than allocating in --state or its unlisted parent.
        with patch.dict(os.environ, dict.fromkeys(("TMPDIR", "TEMP", "TMP"), str(self.root))):
            self.assert_a2_temp_fallback()

    def test_a2_tmpdir_below_input(self):
        # Reject descendants as well; the child directory's mtime detects transient writes.
        nested = self.root / "nested"
        nested.mkdir()
        with patch.dict(os.environ, dict.fromkeys(("TMPDIR", "TEMP", "TMP"), str(nested))):
            self.assert_a2_temp_fallback()

    def test_a2_tmpdir_missing(self):
        # A missing TMPDIR must not produce not-sqlite for a valid store.
        with patch.dict(os.environ, {"TMPDIR": str(self.root / "absent"), "TEMP": "", "TMP": ""}):
            self.assert_a2_temp_fallback()

    def test_a2_no_usable_temp(self):
        # Exhaustion must fail distinctly without creating anything in the input tree.
        self.seed()
        before = self.input_state()
        stdout, stderr = StringIO(), StringIO()
        with (patch.object(REPORT, "_temp_candidates", return_value=[self.root, self.root / "absent"]),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            code = REPORT.main(["--state", str(self.root), "--since", SINCE, "--until", UNTIL])
        self.assertEqual((code, stdout.getvalue(), stderr.getvalue()),
                         (1, f"FAIL temp-unavailable\n{FAIL}\n", ""))
        self.assertEqual(self.input_state(), before)

    def test_c5_no_private_values(self):
        # Check both streams on successful output, unexpected-backend output,
        # and argparse diagnostics (which can otherwise echo a path).
        private = ("Fixture Message!", "Fixture Chat!", "Fixture Sender!",
                   "Fixture Full ID!", "a" * 64)
        self.seed([(SINCE, private[0], 0, private[1], private[2], None),
                   (SINCE, private[3], 0, private[4], "invalid\n", None)])
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("ALTER TABLE interpreter_audit ADD COLUMN provider_id TEXT")
            db.execute("UPDATE interpreter_audit SET provider_id = ?", (private[3],))
            db.execute("CREATE TABLE messages (message TEXT, chat TEXT, sender TEXT)")
            db.execute("INSERT INTO messages VALUES (?, ?, ?)", private[:3])
        good = self.invoke()
        self.assertEqual(self.assert_result(good, 0, PASS), [
            "calls 2", "backend other 2", "fallback 0", "primary-error other 2",
            "error other 2", "seconds none", "unparsed 0", PASS,
        ])
        bad = self.invoke("--expect-backend", "cloud")
        self.assert_findings(bad, "unexpected-backend other")
        usage = self.invoke(str(self.root))
        self.assertEqual((usage.returncode, usage.stdout), (2, ""))
        for result in (good, bad, usage):
            for canary in (*private, str(self.root), str(self.db)):
                self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_no_expectation_no_finding(self):
        # A backend can be valid without being one of the currently deployed names.
        backend = "b" + "_2-" * 10 + "z"
        self.seed([(SINCE, backend, 0, None, None, None)])
        self.assertEqual(self.assert_result(self.invoke(), 0, PASS), [
            "calls 1", f"backend {backend} 1", "fallback 0", "seconds none", "unparsed 0", PASS,
        ])

    def test_lazy_audit_table(self):
        # An initialized SQLite store can legitimately have no interpreter audit rows or table.
        self.seed(schema="CREATE TABLE unrelated (fixture TEXT)")
        self.assertEqual(self.assert_result(self.invoke("--expect-backend", "local"), 0, PASS), [
            "note no-audit-table", "calls 0", "fallback 0", "seconds none", "unparsed 0", PASS,
        ])
