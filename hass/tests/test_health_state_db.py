"""RF1520-12 (H19): health names a conversation.sqlite3 or inbox.sqlite3 that is a symlink or not a regular file
(`state-db`) and never opens it. Temp 0700 state dirs, placeholder rows, an injected clock, sqlite3.connect wrapped
to record every open. Run: python3 -m unittest hass.tests.test_health_state_db -v
"""
import contextlib, io, json, os, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import conversation, health
from hass.tests import test_health as base

NOW, CONV, INBOX = base.NOW, "conversation.sqlite3", "inbox.sqlite3"


def ago(minutes):
    return (NOW - timedelta(minutes=minutes)).isoformat()


class HealthStateDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": base.SETTINGS}))
        self.elsewhere = self.tmp / "elsewhere"
        self.elsewhere.mkdir()

    def stuck_conversation(self, path):
        with contextlib.closing(sqlite3.connect(path)) as db, db:
            db.executescript(conversation.SCHEMA)
            db.execute("INSERT INTO outbox(chat, text, attachments, created_at, sent_at) VALUES ('c', 't', '[]', ?, NULL)",
                       (ago(30),))
        return path

    def stuck_inbox(self, path):
        with contextlib.closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE inbound(enqueued_at TEXT, state TEXT)")
            db.execute("INSERT INTO inbound VALUES (?, 'pending')", (ago(60),))
        return path

    def run_health(self):
        out, opened, real = io.StringIO(), [], sqlite3.connect
        def connect(target, *a, **kw):
            opened.append(str(target))
            return real(target, *a, **kw)
        with mock.patch.object(health.sqlite3, "connect", connect), contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state)], now=NOW)
        [line] = out.getvalue().splitlines()
        return code, json.loads(line), opened

    def assert_state_db(self, name, doc, code, opened):
        self.assertEqual(code, 1)
        self.assertFalse(doc["ok"])
        self.assertIn({"check": "state-db", "detail": f"{name} is not a regular file"}, doc["problems"])
        self.assertFalse([o for o in opened if name in o or "elsewhere" in o], "a linked or odd file was opened")

    def test_linked_conversation_is_named_never_opened(self):
        (self.state / CONV).symlink_to(self.stuck_conversation(self.elsewhere / CONV))
        code, doc, opened = self.run_health()
        self.assert_state_db(CONV, doc, code, opened)
        self.assertEqual(doc["problems"], [{"check": "state-db", "detail": "conversation.sqlite3 is not a regular file"}])
        self.assertEqual(doc["info"], [])  # no "no conversation yet" either

    def test_linked_inbox_is_named_never_opened(self):
        self.stuck_conversation(self.state / CONV)
        (self.state / INBOX).symlink_to(self.stuck_inbox(self.elsewhere / INBOX))
        code, doc, opened = self.run_health()
        self.assert_state_db(INBOX, doc, code, opened)
        checks = [p["check"] for p in doc["problems"]]
        self.assertFalse({"inbox-stuck", "inbox-integrity"} & set(checks))
        self.assertIn("outbox-stuck", checks)  # the rest of the run continues on the regular conversation file

    def test_dangling_link_directory_and_fifo(self):
        for name in (CONV, INBOX):
            for kind, make in (("dangling", lambda p: p.symlink_to(self.elsewhere / "gone")),
                               ("directory", lambda p: p.mkdir()), ("fifo", os.mkfifo)):
                with self.subTest(name=name, kind=kind):
                    path = self.state / name
                    make(path)
                    try:
                        code, doc, opened = self.run_health()  # a FIFO opened for reading would hang here
                        self.assert_state_db(name, doc, code, opened)
                        if name == CONV: self.assertEqual(doc["info"], [])
                    finally:
                        path.rmdir() if path.is_dir() and not path.is_symlink() else path.unlink()

    def test_absent_and_regular_files_unchanged(self):
        code, doc, _ = self.run_health()
        self.assertEqual((code, doc["problems"], doc["info"]),
                         (0, [], [{"check": "conversation", "detail": "no conversation yet"}]))
        self.stuck_conversation(self.state / CONV)
        self.stuck_inbox(self.state / INBOX)
        code, doc, opened = self.run_health()
        self.assertEqual((code, doc["problems"]), (1, [{"check": "outbox-stuck", "detail": "1"},
                                                       {"check": "inbox-stuck", "detail": "1"}]))
        self.assertEqual(len([o for o in opened if CONV in o or INBOX in o]), 2)

    def test_fingerprint_changes_and_is_stable(self):
        self.stuck_conversation(self.state / CONV)
        before = self.run_health()[1]["fingerprint"]
        (self.state / INBOX).symlink_to(self.elsewhere / "gone")
        runs = [self.run_health()[1]["fingerprint"] for _ in range(2)]
        self.assertNotEqual(runs[0], before)
        self.assertEqual(runs[0], runs[1])


if __name__ == "__main__":
    unittest.main()
