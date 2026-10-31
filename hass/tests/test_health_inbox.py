"""H19 x H16 tests: hass/health.py reports a stuck or unreadable inbound queue (inbox-stuck, inbox-integrity).

Temp 0700 state dirs, the queue built by hass.inbox.Inbox with placeholder messages, rows aged by a direct UPDATE here
only, an injected clock. Never the real private state. Run: python3 -m unittest hass.tests.test_health_inbox -v
"""
import contextlib, hashlib, io, json, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta, timezone
from pathlib import Path

from hass import conversation, health
from hass.conversation import Inbound
from hass.inbox import Inbox
from hass.tests import test_health as base

NOW, SECRET = base.NOW, "SECRET-SENTINEL"


def ago(minutes):
    return (NOW - timedelta(minutes=minutes)).astimezone(timezone.utc).isoformat(timespec="microseconds")


class HealthInboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": base.SETTINGS}))
        self.path = self.state / "inbox.sqlite3"

    def inbox(self, *msgs, start=ago(60 * 24 * 30)):
        """Queue (provider_id, received_at, text) messages at NOW; returns their stored states."""
        box = Inbox(str(self.state), start, clock=lambda: NOW)
        try:
            return [box.enqueue(Inbound(pid, "chat@example.invalid", "owner@example.invalid", text, received_at=at))
                    for pid, at, text in msgs]
        finally:
            box.close()

    def sql(self, statement, *params):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute(statement, params)

    def run_raw(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state), *extra], now=NOW)
        [line] = out.getvalue().splitlines()
        return code, line

    def run_health(self, *extra):
        code, line = self.run_raw(*extra)
        return code, json.loads(line)["problems"]

    def snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(self.state.rglob("*"))}

    def test_no_inbox_file_output_unchanged(self):
        code, line = self.run_raw()
        self.assertEqual(code, 0)
        self.assertEqual(line, '{"fingerprint": "%s", "info": [{"check": "conversation", "detail": "no conversation yet"}], '
                         '"notify": false, "ok": true, "problems": []}' % hashlib.sha256(b"").hexdigest())
        self.assertFalse(self.path.exists())

    def test_empty_inbox_is_healthy(self):
        self.inbox()
        self.assertEqual(self.run_health(), (0, []))

    def test_pending_age_threshold_and_flag(self):
        self.inbox(("m1", ago(1), "hours"))
        self.assertEqual(self.run_health(), (0, []))  # just enqueued
        self.sql("UPDATE inbound SET enqueued_at = ?", ago(16))
        self.assertEqual(self.run_health(), (1, [{"check": "inbox-stuck", "detail": "1"}]))
        self.assertEqual(self.run_health("--inbox-minutes", "60"), (0, []))
        for bad in ("0", "-1"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                health.main(["--state", str(self.state), "--inbox-minutes", bad], now=NOW)
            self.assertEqual(exc.exception.code, 2)
        self.sql("UPDATE inbound SET enqueued_at = ?", ago(15))  # exactly the limit: not strictly older
        self.assertEqual(self.run_health(), (0, []))

    def test_done_history_and_late_delivery_ignored(self):
        states = self.inbox(("d1", ago(500), "a"), ("h1", ago(60 * 24 * 40), "b"), ("late", ago(60 * 24 * 10), "c"))
        self.assertEqual(states, ["queued", "history", "queued"])
        self.sql("UPDATE inbound SET state = 'done', payload = NULL WHERE provider_id = 'd1'")
        self.sql("UPDATE inbound SET enqueued_at = ? WHERE provider_id IN ('d1', 'h1')", ago(60 * 24 * 9))
        self.assertEqual(self.run_health(), (0, []))  # 'late' has an old received_at but was enqueued at NOW

    def test_unreadable_time_counts(self):
        self.inbox(("g1", ago(1), "a"), ("g2", ago(1), "b"))
        self.sql("UPDATE inbound SET enqueued_at = 'garbage' WHERE provider_id = 'g1'")
        self.assertEqual(self.run_health(), (1, [{"check": "inbox-stuck", "detail": "1"}]))

    def test_corrupt_inbox_and_conversation_still_checked(self):
        self.path.write_bytes(b"not a database " * 100)
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db, db:
            db.executescript(conversation.SCHEMA)
            db.execute("INSERT INTO outbox(chat, text, attachments, created_at, sent_at) VALUES ('c', 't', '[]', ?, NULL)",
                       (ago(30),))
        self.assertEqual(self.run_health(), (1, [{"check": "outbox-stuck", "detail": "1"},
                                                 {"check": "inbox-integrity", "detail": "database unreadable"}]))

    def test_missing_inbound_table(self):
        self.sql("CREATE TABLE other(x)")
        self.assertEqual(self.run_health(), (0, []))

    def test_read_only_no_leak_and_change_only_notify(self):
        self.inbox((f"{SECRET}-id", ago(1), f"{SECRET} text"))
        self.sql("UPDATE inbound SET enqueued_at = ?", ago(20))
        before, seen = self.snapshot(), self.tmp / "seen"
        runs = [self.run_raw("--seen", str(seen)) for _ in range(2)]
        self.assertEqual(self.snapshot(), before)  # bytes, mtimes and file set (no -journal/-wal/-shm, no lock)
        self.assertNotIn(SECRET, "".join(line for _, line in runs))
        docs = [json.loads(line) for _, line in runs]
        self.assertEqual([d["problems"] for d in docs], [[{"check": "inbox-stuck", "detail": "1"}]] * 2)
        self.assertEqual([(c, d["notify"]) for (c, _), d in zip(runs, docs)], [(1, True), (1, False)])


if __name__ == "__main__":
    unittest.main()
