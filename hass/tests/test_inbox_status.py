"""RF1710-3 (H16): `inbox.py status --state DIR` prints read-only queue counts and never an id or text.

The queue is built through Inbox.enqueue/drain with a stub conversation and a fixed clock in a throwaway 0700 dir;
rows that only a damaged or older store could hold are hand-set. Run: python3 -m unittest hass.tests.test_inbox_status -v
"""

import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path

from hass import inbox as inbox_mod
from hass.conversation import Inbound
from hass.tests.test_conversation import T0

NOW = T0 + timedelta(minutes=65)
PID, TEXT = "pid-SENTINEL-7f3a", "text-SENTINEL-9c1e"  # must never reach the output
REPO = Path(__file__).resolve().parents[2]


class StubConversation:
    def handle(self, msg):
        return {"apply": "applied", "hold": "Bad Code!"}.get(msg.text.split()[0], "proposed")


class StatusTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.state.mkdir(mode=0o700)
        self.db = self.state / "inbox.sqlite3"
        self.clock = T0 + timedelta(minutes=5)

    def open_inbox(self):
        box = inbox_mod.Inbox(str(self.state), T0.isoformat(), clock=lambda: self.clock)
        self.addCleanup(box.close)
        return box

    def enqueue(self, box, pid, text, offset_s):
        return box.enqueue(Inbound(pid, "chat-fixture", "owner@example.invalid", text, False, "new",
                                   (T0 + timedelta(seconds=offset_s)).isoformat()))

    def snapshot(self):
        return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.state.iterdir()} \
            if self.state.is_dir() and not self.state.is_symlink() else None

    def run_status(self, state=None, now=NOW):
        before, out, err = self.snapshot(), io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = inbox_mod.main(["status", "--state", str(state or self.state)], now=now)
        self.assertEqual(err.getvalue(), "")  # no traceback, no warning
        self.assertEqual(self.snapshot(), before)  # read-only: same files, bytes and mtimes; no journal left
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertNotIn(PID, out.getvalue())
        self.assertNotIn(TEXT, out.getvalue())
        return json.loads(lines[0]), code

    def test_fresh_queue_counts_start_point_and_oldest_pending(self):
        box = self.open_inbox()
        self.assertEqual(self.enqueue(box, "p1", f"hours {TEXT}", 1), "queued")  # enqueued at T0+5 min
        self.clock = T0 + timedelta(minutes=20)
        self.assertEqual(self.enqueue(box, PID, f"desc {TEXT}", 2), "queued")
        self.assertEqual(self.enqueue(box, "h1", f"hours {TEXT}", -1), "history")
        self.assertEqual(self.enqueue(box, "p1", "hours", 1), "duplicate")  # counted once
        box.seen().add("nonce-1")
        self.assertEqual(self.run_status(), ({
            "result": "ok", "start_at": inbox_mod._iso(T0), "pending": 2, "done": 0, "history": 1,
            "dispositions": {}, "oldest_pending_minutes": 60, "nonces": 1}, 0))
        self.assertEqual(self.run_status(now=NOW + timedelta(seconds=59))[0]["oldest_pending_minutes"], 60)  # floor

    def test_after_drain_dispositions_are_counted_and_nothing_is_pending(self):
        box = self.open_inbox()
        self.enqueue(box, PID, f"apply {TEXT}", 1)
        self.enqueue(box, "poison", "apply", 2)
        box.db.execute("UPDATE inbound SET payload = 'not json' WHERE provider_id = 'poison'")
        self.enqueue(box, "p3", "apply too", 3)
        self.assertEqual(box.drain(StubConversation()), [(PID, "applied"), ("poison", "unreadable"), ("p3", "applied")])
        report, code = self.run_status()
        self.assertEqual((report["pending"], report["done"], report["dispositions"]), (0, 3, {"applied": 2, "unreadable": 1}))
        self.assertEqual((report["oldest_pending_minutes"], code), (None, 0))

    def test_bad_or_missing_disposition_code_is_not_echoed(self):
        box = self.open_inbox()
        for i, pid in enumerate(("a", "b", "c", "d")): self.enqueue(box, pid, "hold" if pid == "a" else "apply", i)
        box.drain(StubConversation())  # the handler's own "Bad Code!" is stored as given
        box.db.execute("UPDATE inbound SET disposition = NULL WHERE provider_id = 'b'")
        box.db.execute("UPDATE inbound SET disposition = ? WHERE provider_id = 'c'", ("x" * 33,))
        box.db.execute("UPDATE inbound SET disposition = ? WHERE provider_id = 'd'", (TEXT,))
        self.assertEqual(self.run_status()[0]["dispositions"], {"other": 3, "none": 1})

    def test_unreadable_enqueue_time_on_a_pending_row(self):
        box = self.open_inbox()
        self.enqueue(box, "p1", "hours", 1)
        self.enqueue(box, "p2", "hours", 2)
        box.db.execute("UPDATE inbound SET enqueued_at = 'garbage' WHERE provider_id = 'p2'")
        report, code = self.run_status()
        self.assertEqual((report["oldest_pending_minutes"], report["pending"], code), ("unreadable", 2, 0))
        box.db.execute("UPDATE inbound SET enqueued_at = '2026-11-02T17:00' WHERE provider_id = 'p2'")  # no zone
        self.assertEqual(self.run_status()[0]["oldest_pending_minutes"], "unreadable")

    def test_no_inbox_file_is_reported_and_never_created(self):
        self.assertEqual(self.run_status(), ({"result": "ok", "inbox": "none"}, 0))
        self.assertFalse(self.db.exists())
        self.assertEqual(list(self.state.iterdir()), [])

    def test_missing_or_symlinked_state_dir_is_unsafe(self):
        self.open_inbox()
        link = self.state.parent / "link"
        link.symlink_to(self.state, target_is_directory=True)
        for state in (self.state.parent / "absent", link, self.db):
            report, code = self.run_status(state)
            self.assertEqual((report["result"], code), ("unsafe", 2))
        self.assertFalse((self.state.parent / "absent").exists())

    def test_corrupt_store_is_unreadable_without_traceback(self):
        self.db.write_bytes(bytes((i * 151 + 7) % 256 for i in range(8192)))
        self.assertEqual(self.run_status(), ({"result": "unreadable"}, 1))
        self.db.write_bytes(b"")  # rebuilt below as a real store with a damaged page
        box = self.open_inbox()
        for i in range(60): self.enqueue(box, f"p{i:02}", "hours " + "x" * 200, i)
        box.close()
        data = bytearray(self.db.read_bytes())
        data[4096:8192] = b"\x55" * 4096
        self.db.write_bytes(bytes(data))
        self.assertEqual(self.run_status(), ({"result": "unreadable"}, 1))

    def test_older_schema_without_disposition_or_nonces(self):
        with sqlite3.connect(self.db) as db:
            db.executescript("CREATE TABLE meta(name TEXT PRIMARY KEY, value TEXT NOT NULL);"
                             "CREATE TABLE inbound(provider_id TEXT PRIMARY KEY, received_at TEXT NOT NULL, payload TEXT,"
                             " state TEXT NOT NULL, enqueued_at TEXT NOT NULL, done_at TEXT);")
            db.execute("INSERT INTO meta VALUES ('start_at', ?)", (inbox_mod._iso(T0),))
            db.executemany("INSERT INTO inbound VALUES (?, ?, ?, ?, ?, NULL)", [
                (PID, inbox_mod._iso(T0), TEXT, "pending", inbox_mod._iso(T0 + timedelta(minutes=5))),
                ("d1", inbox_mod._iso(T0), None, "done", inbox_mod._iso(T0))])
        db.close()
        self.assertEqual(self.run_status(), ({
            "result": "ok", "start_at": inbox_mod._iso(T0), "pending": 1, "done": 1, "history": 0,
            "oldest_pending_minutes": 60, "nonces": 0}, 0))

    def test_command_line_runs_as_a_script(self):
        box = self.open_inbox()
        self.enqueue(box, PID, f"hours {TEXT}", 1)
        before = self.snapshot()
        proc = subprocess.run([sys.executable, str(REPO / "hass" / "inbox.py"), "status", "--state", str(self.state)],
                              capture_output=True, text=True, timeout=60, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        report = json.loads(proc.stdout)
        self.assertEqual((report["result"], report["pending"], report["start_at"]), ("ok", 1, inbox_mod._iso(T0)))
        self.assertNotIn(PID, proc.stdout)
        self.assertNotIn(TEXT, proc.stdout)
        self.assertEqual(self.snapshot(), before)

    def status_cli(self, *planted):
        """Run the script with a 30 s cap (a FIFO handed to SQLite would hang); stdout must name no planted path."""
        proc = subprocess.run([sys.executable, str(REPO / "hass" / "inbox.py"), "status", "--state", str(self.state)],
                              capture_output=True, text=True, timeout=30, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(proc.stderr, "")
        for p in (self.state, *planted): self.assertNotIn(str(p), proc.stdout)
        return json.loads(proc.stdout), proc.returncode

    UNSAFE = ({"result": "unsafe", "reason": "inbox file is a link or not a regular file"}, 2)

    def test_symlinked_inbox_file_is_unsafe_and_its_target_never_reported(self):
        other = self.state.parent / "other"
        other.mkdir(mode=0o700)
        box = inbox_mod.Inbox(str(other), T0.isoformat(), clock=lambda: self.clock)
        self.enqueue(box, PID, f"hours {TEXT}", 1)
        box.close()
        target = other / "inbox.sqlite3"
        self.assertEqual(inbox_mod.status(other, NOW)[0]["pending"], 1)  # the target is a real, readable queue
        before = (target.read_bytes(), target.stat().st_mtime_ns)
        self.db.symlink_to(target)
        self.assertEqual(self.status_cli(target, other), self.UNSAFE)
        self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)
        self.db.unlink()
        self.db.symlink_to(self.state.parent / "no-such.sqlite3")  # dangling: a planted link, not "inbox: none"
        self.assertEqual(self.status_cli(self.state.parent / "no-such.sqlite3"), self.UNSAFE)
        self.assertFalse((self.state.parent / "no-such.sqlite3").exists())

    def test_directory_or_fifo_named_inbox_file_is_unsafe_without_opening(self):
        self.db.mkdir()
        self.assertEqual(self.status_cli(), self.UNSAFE)
        self.assertEqual(list(self.db.iterdir()), [])  # SQLite left no journal inside it
        self.db.rmdir()
        if not hasattr(os, "mkfifo"): self.skipTest("no os.mkfifo on this platform")
        os.mkfifo(self.db, 0o600)
        self.assertEqual(self.status_cli(), self.UNSAFE)  # returns at once: never opened for reading
        self.db.unlink()
        self.assertEqual(self.run_status(), ({"result": "ok", "inbox": "none"}, 0))  # no file: as before
        self.open_inbox()
        self.assertEqual(self.run_status()[0]["result"], "ok")  # a regular queue file: as before


if __name__ == "__main__":
    unittest.main()
