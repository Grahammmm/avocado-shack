"""Offline contract tests for comparing store copies against the release schema."""

from contextlib import closing, redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import inbox
from hass.relay import RelayStore


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/install_store_schema.py"
START = "2026-01-01T00:00:00+00:00"
PASS = "PASS install_store_schema"
FAIL = "FAIL install_store_schema"
INBOX_OK = ["ok inbox.inbound", "ok inbox.meta", "ok inbox.nonces"]


class InstallStoreSchemaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def own_relay(self):
        directory = self.root / "relay copies"
        directory.mkdir(mode=0o700)
        RelayStore(directory).db.close()
        return directory / "relay.sqlite3"

    def own_inbox(self):
        directory = self.root / "inbox copies"
        directory.mkdir(mode=0o700)
        inbox.Inbox(directory, start_at=START).db.close()
        return directory / "inbox.sqlite3"

    def invoke(self, *args, env=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, timeout=10, env=env,
        )

    def snapshot(self, *directories):
        # Directory mtime catches transient sidecars as well as persistent ones.
        return {
            directory: (directory.stat().st_mtime_ns, {
                entry.name: (entry.read_bytes(), entry.stat().st_mtime_ns)
                for entry in directory.iterdir()
            })
            for directory in directories
        }

    def assert_verdict(self, result, code, last):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1:], [last])
        return lines[:-1]

    def assert_findings(self, result, *expected):
        lines = self.assert_verdict(result, 1, FAIL)
        self.assertEqual([line for line in lines if line.startswith("FAIL ")], list(expected))
        return lines

    def sql(self, path, statement, parameters=()):
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(statement, parameters)

    def test_c1_full_pass(self):
        # The real CLI runs from outside the checkout and must report both stores.
        relay = self.own_relay().relative_to(self.root)
        inbox_path = self.own_inbox().relative_to(self.root)
        lines = self.assert_verdict(self.invoke("--relay", relay, "--inbox", inbox_path), 0, PASS)
        self.assertCountEqual(lines, [
            "ok relay.card_receipt", "ok relay.meta", "ok relay.picture", "ok relay.relay",
            "ok inbox.inbound", "ok inbox.meta", "ok inbox.nonces",
        ])

    def test_c2_1_no_store(self):
        # Empty input is a finding rather than vacuous success or a usage error.
        self.assertEqual(self.assert_findings(self.invoke(), "FAIL no-store"), ["FAIL no-store"])

    def test_c2_2_not_sqlite(self):
        # A link to a good store, a FIFO, or merely openable bytes are not valid inputs.
        linked = self.root / "linked.sqlite3"
        linked.symlink_to(self.own_relay())
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        invalid = self.root / "invalid.sqlite3"
        invalid.write_bytes(b"not a database")
        for path in (self.root / "absent.sqlite3", linked, self.root, fifo, invalid):
            with self.subTest(name=path.name):
                self.assert_findings(self.invoke("--relay", path), "FAIL not-sqlite relay")

    def test_c2_3_reference_error(self):
        # Constructor refusal must fail closed without disclosing the exception or leaving temp state.
        path = self.own_inbox()
        spec = importlib.util.spec_from_file_location("install_store_schema", SCRIPT)
        assert spec is not None and spec.loader is not None
        script = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(script)
        calls = []

        def refuse(directory, *, start_at):
            calls.append((directory, stat.S_IMODE(directory.stat().st_mode), start_at))
            raise RuntimeError("synthetic constructor error")

        stdout, stderr = StringIO(), StringIO()
        with patch.object(inbox, "Inbox", side_effect=refuse), redirect_stdout(stdout), redirect_stderr(stderr):
            code = script.main(["--inbox", str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue().splitlines(), ["FAIL reference-error inbox", FAIL])
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(calls), 1)
        directory, mode, start_at = calls[0]
        self.assertNotEqual(directory, path.parent)
        self.assertEqual((mode, start_at), (0o700, START))
        self.assertFalse(directory.exists())

    def test_c2_4_missing_table(self):
        # Comparing only the intersection would silently miss a required table.
        path = self.own_relay()
        self.sql(path, "DROP TABLE picture")
        self.assert_findings(self.invoke("--relay", path), "FAIL missing-table relay.picture")

    def test_c2_5_missing_column(self):
        # Checking only table names would falsely accept this store.
        path = self.own_relay()
        self.sql(path, "ALTER TABLE relay DROP COLUMN acked_at")
        lines = self.assert_findings(self.invoke("--relay", path), "FAIL missing-column relay.relay.acked_at")
        self.assertNotIn("ok relay.relay", lines)

    def test_c2_6_type_mismatch(self):
        # VARCHAR and TEXT have the same affinity, but not the same declaration.
        path = self.own_relay()
        self.sql(path, "ALTER TABLE meta DROP COLUMN value")
        self.sql(path, "ALTER TABLE meta ADD COLUMN value VARCHAR(80)")
        lines = self.assert_findings(self.invoke("--relay", path), "FAIL type-mismatch relay.meta.value")
        self.assertNotIn("ok relay.meta", lines)

    def test_c3_usage_exit_2(self):
        # The CLI must not translate argparse's own errors into schema findings.
        for args in (("--relay",), ("--inbox",), ("--unknown",)):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout.splitlines(), [])  # No terminal line on usage errors.
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr)

    def test_c4_read_only(self):
        # A checkpointed WAL-mode input must not acquire sidecars or scratch files.
        relay = self.own_relay()
        path = self.own_inbox()
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
        env = dict(os.environ, TMPDIR=str(relay.parent), TEMP=str(self.root))
        before = self.snapshot(relay.parent, path.parent)
        lines = self.assert_verdict(self.invoke("--relay", relay, "--inbox", path, env=env), 0, PASS)
        self.assertEqual(lines, [
            "ok relay.card_receipt", "ok relay.meta", "ok relay.picture", "ok relay.relay", *INBOX_OK,
        ])
        self.assertEqual(self.snapshot(relay.parent, path.parent), before)

    def test_a1_uncheckpointed_wal(self):
        # Rejecting the WAL or opening the base alone loses the committed column.
        original = self.own_inbox()
        wal_copy_dir = self.root / "offline copy"
        wal_copy_dir.mkdir()
        copy = wal_copy_dir / original.name
        with closing(sqlite3.connect(original)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone(), ("wal",))
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("INSERT INTO meta VALUES ('fixture-key', 'fixture-value')")
            db.commit()
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            db.execute("ALTER TABLE inbound ADD COLUMN wal_only TEXT")
            db.commit()
            shutil.copyfile(original, copy)
            shutil.copyfile(original.with_name(original.name + "-wal"), copy.with_name(copy.name + "-wal"))

        before = self.snapshot(wal_copy_dir)
        lines = self.assert_verdict(self.invoke("--inbox", copy), 0, PASS)
        self.assertEqual(lines, [INBOX_OK[0], "note extra inbox.inbound.wal_only", *INBOX_OK[1:]])
        self.assertEqual(self.snapshot(wal_copy_dir), before)

    def test_a1_harmless_journal(self):
        # The mere presence of a journal is not a reason to refuse the store.
        path = self.own_inbox()
        path.with_name(path.name + "-journal").write_bytes(b"")
        before = self.snapshot(path.parent)
        self.assertEqual(self.assert_verdict(self.invoke("--inbox", path), 0, PASS), INBOX_OK)
        self.assertEqual(self.snapshot(path.parent), before)

    def test_a1_symlinked_sidecar(self):
        # Following a sidecar symlink would accept this empty target as an empty WAL.
        path = self.own_inbox()
        target = self.root / "empty"
        target.write_bytes(b"")
        path.with_name(path.name + "-wal").symlink_to(target)
        lines = self.assert_findings(self.invoke("--inbox", path), "FAIL not-sqlite inbox")
        self.assertEqual(lines, ["FAIL not-sqlite inbox"])

    def test_c5_no_private_values(self):
        # Diagnostics must never dump rows, SQLite errors containing a path, or a resolved input URI.
        relay, inbound = self.own_relay(), self.own_inbox()
        chat, sender, text = "canary-chat", "canary-sender", "canary-message body"
        provider = "canary-provider-identifier-in-full"
        digest = "ab" * 32
        self.sql(relay, "INSERT INTO relay (chat, text, pictures, created_at) VALUES (?, ?, 1, 0)", (chat, text))
        self.sql(relay, "INSERT INTO picture VALUES (1, 0, ?, 1, NULL)", (digest,))
        self.sql(inbound, "INSERT INTO inbound (provider_id, received_at, payload, state, enqueued_at) "
                 "VALUES (?, ?, ?, 'pending', ?)",
                 (provider, START, json.dumps(dict(chat=chat, sender=sender, text=text)), START))
        malformed = self.root / "private ?#%.sqlite3"
        malformed.write_text(text, encoding="utf-8")
        for path, code, last in ((relay, 0, PASS), (malformed, 1, FAIL)):
            with self.subTest(code=code):
                result = self.invoke("--relay", path, "--inbox", inbound)
                self.assert_verdict(result, code, last)
                for canary in (chat, sender, text, provider, digest, str(relay), str(inbound), str(malformed)):
                    self.assertNotIn(canary, result.stdout + result.stderr)

    def test_c6_bare_schema_is_not_a_pass(self):
        # Deriving the reference from SCHEMA alone misses both constructor migrations.
        path = self.root / "bare.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            db.executescript(inbox.SCHEMA)
        self.assert_findings(self.invoke("--inbox", path),
                             "FAIL missing-column inbox.inbound.tries", "FAIL missing-column inbox.inbound.next_try_at")

    def test_c7_own_stores_pass_extra_noted(self):
        # Reference comparison is one-way: additional schema is visible but not a failure.
        relay, inbound = self.own_relay(), self.own_inbox()
        unusual_path = inbound.with_name("copy ?#%.sqlite3")
        inbound.rename(unusual_path)
        self.sql(unusual_path, "ALTER TABLE inbound ADD COLUMN addition TEXT")
        self.sql(unusual_path, 'CREATE TABLE "extra""table" (value TEXT)')
        lines = self.assert_verdict(self.invoke("--relay", relay, "--inbox", unusual_path), 0, PASS)
        self.assertIn("ok relay.relay", lines)
        self.assertIn("ok inbox.inbound", lines)
        self.assertEqual([line for line in lines if line.startswith("note ")],
                         ['note extra inbox.inbound.addition', 'note extra inbox.extra"table'])
