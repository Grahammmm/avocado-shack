"""RF1520-11: inbox.sqlite3 is opened through memory.private_db, so a link or non-regular file is refused."""
import contextlib, io, json, os, signal, sqlite3, stat, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import editor, fixture_chat, inbox

START = "2026-11-01T12:00:00+00:00"


class InboxNoFollowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        self.path = self.state / "inbox.sqlite3"

    def assert_unsafe(self):
        with self.assertRaisesRegex(editor.UnsafeState, "inbox.sqlite3 must be a regular file"):
            inbox.Inbox(self.state, START)

    def test_link_to_outside_file_never_touches_target(self):
        target = self.root / "outside.sqlite3"
        with contextlib.closing(sqlite3.connect(target)) as db, db:
            db.execute("CREATE TABLE original(value TEXT)")
            db.execute("INSERT INTO original VALUES ('kept')")
        os.chmod(target, 0o644)
        before = target.read_bytes()
        self.path.symlink_to(target)
        self.assert_unsafe()
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
        self.assertEqual(target.read_bytes(), before)
        with contextlib.closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master").fetchall(), [("original",)])

    def test_dangling_link_creates_nothing(self):
        target = self.root / "missing.sqlite3"
        self.path.symlink_to(target)
        self.assert_unsafe()
        self.assertFalse(target.exists())
        self.assertTrue(self.path.is_symlink())

    def test_directory_and_fifo_refused_without_hanging(self):
        def hung(signum, frame): raise TimeoutError("opening the inbox hung")
        self.addCleanup(signal.signal, signal.SIGALRM, signal.signal(signal.SIGALRM, hung))
        for kind in ("directory", "fifo"):
            with self.subTest(kind=kind):
                self.path.mkdir(0o750) if kind == "directory" else os.mkfifo(self.path, 0o640)
                before = stat.S_IMODE(self.path.lstat().st_mode)
                signal.alarm(3)
                try: self.assert_unsafe()
                finally: signal.alarm(0)
                self.assertEqual(stat.S_IMODE(self.path.lstat().st_mode), before)
                self.path.rmdir() if kind == "directory" else self.path.unlink()

    def test_absent_and_regular_files_stay_private_and_rows_survive(self):
        old = os.umask(0)
        try: box = inbox.Inbox(self.state, START)
        finally: os.umask(old)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(box.db.execute("SELECT value FROM meta WHERE name='start_at'").fetchone()[0],
                         inbox._iso(inbox.parse_aware(START)))
        box.db.execute("INSERT INTO inbound(provider_id, received_at, state, enqueued_at) VALUES ('q1', ?, 'done', ?)",
                       (START, START))
        box.close()
        os.chmod(self.path, 0o640)
        box = inbox.Inbox(self.state)
        self.addCleanup(box.close)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(box.db.execute("SELECT provider_id FROM inbound").fetchall()[0][0], "q1")

    def test_fixture_chat_queue_refuses_link_without_queueing_or_sending(self):
        (self.state / "config.json").write_text(json.dumps({"settings": {
            "ownerSenders": ["owner"], "ownerChat": "chat", "approvalTtlSeconds": 600}}))
        self.path.symlink_to(target := self.root / "outside.sqlite3")
        mapping, fixture = self.root / "mapping.json", self.root / "fixture.jsonl"
        mapping.write_text("{}")
        fixture.write_text(json.dumps({"id": "1", "chat": "chat", "sender": "owner", "text": "help", "at": START}) + "\n")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(fixture_chat.FixtureAdapter, "send") as send, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fixture_chat.main(["--state", str(self.state), "--fixture", str(fixture),
                                      "--interpreter", str(mapping), "--queue", START])
        self.assertEqual((code, out.getvalue()), (2, ""))
        self.assertIn("fixture_chat: UnsafeState: inbox.sqlite3 must be a regular file", err.getvalue())
        self.assertNotIn("queued=", err.getvalue())
        send.assert_not_called()
        self.assertFalse(target.exists())
