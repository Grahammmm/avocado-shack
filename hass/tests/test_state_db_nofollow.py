"""RF1520-9: private conversation database creation and unsafe file types."""
import contextlib
import io
import json
import os
import signal
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import conversation, editor, fixture_chat, memory


class PrivateDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"settings": {
            "ownerSenders": ["owner"], "ownerChat": "chat", "approvalTtlSeconds": 600}}))
        self.path = self.state / "conversation.sqlite3"

    def open(self, kind):
        if kind == "conversation":
            return conversation.Conversation(self.state, None, None, lambda: None)
        return memory.Memory(self.state, lambda: None)

    def close(self, obj):
        obj.db.close()

    def assert_unsafe(self):
        for kind in ("conversation", "memory"):
            with self.subTest(kind=kind), self.assertRaisesRegex(editor.UnsafeState, "regular file"):
                self.open(kind)

    def test_link_existing_file_never_touches_target(self):
        target = self.root / "outside.sqlite3"
        with sqlite3.connect(target) as db:
            db.execute("CREATE TABLE original(value TEXT)")
            db.execute("INSERT INTO original VALUES ('kept')")
        os.chmod(target, 0o644)
        before = target.read_bytes()
        self.path.symlink_to(target)
        self.assert_unsafe()
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
        self.assertEqual(target.read_bytes(), before)
        with sqlite3.connect(target) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("original",)])
            self.assertEqual(db.execute("SELECT value FROM original").fetchall(), [("kept",)])

    def test_dangling_link_never_creates_target(self):
        target = self.root / "missing.sqlite3"
        self.path.symlink_to(target)
        self.assert_unsafe()
        self.assertFalse(target.exists())

    def test_directory_and_fifo_rejected_without_hanging(self):
        def timeout(signum, frame):
            raise TimeoutError("opening unsafe database hung")
        previous = signal.signal(signal.SIGALRM, timeout)
        self.addCleanup(signal.signal, signal.SIGALRM, previous)
        for kind in ("directory", "fifo"):
            with self.subTest(type=kind):
                self.path.mkdir() if kind == "directory" else os.mkfifo(self.path, 0o640)
                before = stat.S_IMODE(self.path.stat().st_mode)
                try:
                    signal.alarm(3)
                    self.assert_unsafe()
                finally:
                    signal.alarm(0)
                self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), before)
                self.path.rmdir() if kind == "directory" else self.path.unlink()

    def test_created_and_existing_files_are_private_and_rows_survive(self):
        for kind in ("conversation", "memory"):
            with self.subTest(kind=kind):
                old_mask = os.umask(0)
                try:
                    obj = self.open(kind)
                finally:
                    os.umask(old_mask)
                self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
                obj.db.execute("CREATE TABLE preserved(value TEXT)")
                obj.db.execute("INSERT INTO preserved VALUES ('kept')")
                self.close(obj)
                os.chmod(self.path, 0o640)
                obj = self.open(kind)
                try:
                    self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
                    self.assertEqual(obj.db.execute("SELECT value FROM preserved").fetchone()[0], "kept")
                finally:
                    self.close(obj)
                self.path.unlink()

    def test_fixture_chat_refuses_link_without_sending(self):
        target = self.root / "outside.sqlite3"
        self.path.symlink_to(target)
        mapping, fixture = self.root / "mapping.json", self.root / "fixture.jsonl"
        mapping.write_text("{}")
        fixture.write_text('{"id":"1","chat":"chat","sender":"owner","text":"help",'
                           '"at":"2026-11-01T12:00:00+00:00"}\n')
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(fixture_chat.FixtureAdapter, "send") as send, \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = fixture_chat.main(["--state", str(self.state), "--fixture", str(fixture),
                                        "--interpreter", str(mapping)])
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("fixture_chat: UnsafeState:", stderr.getvalue())
        send.assert_not_called()
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
