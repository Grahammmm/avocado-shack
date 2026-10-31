"""RF1230-11 (H19 x H16): hass/health.py reports inbound messages marked unreadable in the last day (inbox-unreadable).

Temp 0700 state dirs, placeholder messages queued by hass.inbox.Inbox, rows marked by a direct UPDATE, a fixed clock."""
import contextlib, io, json, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path

from hass import health
from hass.conversation import Inbound
from hass.inbox import Inbox
from hass.tests import test_health as base

NOW, SECRET = base.NOW, "SECRET-SENTINEL"


def ago(hours):
    return (NOW - timedelta(hours=hours)).isoformat(timespec="microseconds")


class HealthUnreadableTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": base.SETTINGS}))
        self.path = self.state / "inbox.sqlite3"

    def queue(self, *ids):
        """Enqueue placeholder messages at NOW (all pending)."""
        box = Inbox(str(self.state), ago(24 * 30), clock=lambda: NOW)
        try:
            for pid in ids:
                box.enqueue(Inbound(pid, "chat@example.invalid", "owner@example.invalid", SECRET, received_at=ago(0)))
        finally:
            box.close()

    def mark(self, pid, done_at, disposition="unreadable"):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE inbound SET state = 'done', disposition = ?, done_at = ?, payload = NULL WHERE provider_id = ?",
                       (disposition, done_at, pid))

    def run_raw(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state), *extra], now=NOW)
        [line] = out.getvalue().splitlines()
        return code, line

    def run_health(self, *extra):
        code, line = self.run_raw(*extra)
        return code, json.loads(line)["problems"]

    def unreadable(self, n):
        return [{"check": "inbox-unreadable", "detail": str(n)}]

    def test_one_unreadable_an_hour_ago(self):
        self.queue("u1")
        self.mark("u1", ago(1))
        self.assertEqual(self.run_health(), (1, self.unreadable(1)))

    def test_window_default_and_flag(self):
        self.queue("u1")
        self.mark("u1", ago(25))
        self.assertEqual(self.run_health(), (0, []))
        self.assertEqual(self.run_health("--inbox-unreadable-hours", "48"), (1, self.unreadable(1)))
        self.mark("u1", ago(24))  # exactly the window edge: still inside
        self.assertEqual(self.run_health(), (1, self.unreadable(1)))
        self.mark("u1", ago(1))
        self.assertEqual(health.check(str(self.state), now=NOW, inbox_unreadable_hours=1)[0], self.unreadable(1))
        self.assertEqual(health.check(str(self.state), now=NOW + timedelta(seconds=1), inbox_unreadable_hours=1)[0], [])

    def test_mixed_rows_count_only_recent_unreadable(self):
        self.queue("in1", "in2", "out", "ok1", "ok2", "ok3", "wait")
        self.mark("in1", ago(1))
        self.mark("in2", ago(23))
        self.mark("out", ago(30))
        for pid in ("ok1", "ok2", "ok3"): self.mark(pid, ago(1), "handled")
        self.assertEqual(self.run_health(), (1, self.unreadable(2)))  # "wait" is pending but newly enqueued

    def test_bad_done_at_counts(self):
        self.queue("g1", "g2", "g3")
        self.mark("g1", "garbage")
        self.mark("g2", "2026-01-01T00:00:00")  # zone-less, even though long ago
        self.mark("g3", None)
        self.assertEqual(self.run_health(), (1, self.unreadable(3)))

    def test_no_inbox_file_or_table_creates_nothing(self):
        before = sorted(p.name for p in self.state.iterdir())
        self.assertEqual(self.run_health(), (0, []))
        self.assertEqual(sorted(p.name for p in self.state.iterdir()), before)
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE other(x)")
        before = sorted(p.name for p in self.state.iterdir())
        self.assertEqual(self.run_health(), (0, []))
        self.assertEqual(sorted(p.name for p in self.state.iterdir()), before)

    def test_table_without_disposition_column(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE inbound(provider_id TEXT, state TEXT, enqueued_at TEXT, done_at TEXT)")
            db.execute("INSERT INTO inbound VALUES ('u1', 'done', ?, ?)", (ago(1), ago(1)))
        self.assertEqual(self.run_health(), (0, []))

    def test_output_names_no_id_sender_or_text(self):
        self.queue(f"{SECRET}-id")
        self.mark(f"{SECRET}-id", ago(1))
        code, line = self.run_raw()
        self.assertEqual(code, 1)
        self.assertEqual([s for s in (SECRET, "example.invalid", "chat", "owner") if s in line], [])
        self.assertEqual(json.loads(line)["problems"], self.unreadable(1))

    def test_zero_or_negative_hours_refused(self):
        for bad in ("0", "-1"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                health.main(["--state", str(self.state), "--inbox-unreadable-hours", bad], now=NOW)
            self.assertEqual(exc.exception.code, 2)

    def test_fingerprint_changes_once_then_clears(self):
        self.queue("u1")
        self.mark("u1", ago(1))
        seen = self.tmp / "seen"
        runs = [json.loads(self.run_raw("--seen", str(seen))[1]) for _ in range(2)]
        self.assertEqual([r["notify"] for r in runs], [True, False])
        self.mark("u1", ago(25))  # aged out: clears by itself
        self.assertEqual(self.run_health("--seen", str(seen)), (0, []))


if __name__ == "__main__":
    unittest.main()
