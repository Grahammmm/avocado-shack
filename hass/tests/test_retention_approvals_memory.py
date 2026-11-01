"""AV2022-13 tests: hass/retention.py also counts approvals rows and closed (superseded/forgotten) memory rows.

Temp state dir built from the real schemas with canary values and an injected clock; never the real private state.
Run: python3 -B -m unittest hass.tests.test_retention_approvals_memory -v
"""
import contextlib, io, json, os, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import conversation, inbox, memory, retention

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
DAYS = 30
OLD, OLDER, NEW = NOW - timedelta(days=31), NOW - timedelta(days=40), NOW - timedelta(days=1)
CANARIES = ("sender-canary-a", "chat-canary-b", "pid-canary-c", "key-canary-d", "value-canary-e", "change-canary-f")
SENDER, CHAT, PID, KEY, VALUE, CHANGE = CANARIES


def iso(dt):
    return dt.isoformat(timespec="microseconds")


class ApprovalsMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        self.conv = self.state / "conversation.sqlite3"
        with contextlib.closing(sqlite3.connect(self.state / "inbox.sqlite3")) as db, db:
            db.executescript(inbox.SCHEMA)

    def schema(self, schema=conversation.SCHEMA):
        with contextlib.closing(sqlite3.connect(self.conv)) as db, db:
            db.executescript(schema)

    def db(self, schema=conversation.SCHEMA):
        self.schema(schema)
        return contextlib.closing(sqlite3.connect(self.conv))

    def approval(self, db, approved_at):
        db.execute("INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, "
                   "approved_at) VALUES (?, ?, ?, ?, 'h', 'b', ?, ?)", (SENDER, CHAT, PID, CHANGE, iso(NEW), approved_at))

    def remember(self, db, created, superseded=None, forgotten=None):
        db.execute("INSERT INTO memory(key, value, kind, source, approved_change, created_at, superseded_at, "
                   "forgotten_at) VALUES (?, ?, 'fact', ?, ?, ?, ?, ?)",
                   (KEY, VALUE, f"owner-stated:{SENDER}", CHANGE, created, superseded, forgotten))

    def report(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = retention.main(["report", "--state", str(self.state), "--days", str(DAYS), "--now", iso(NOW)])
        return code, json.loads(out.getvalue()), out.getvalue()

    def test_approvals_one_old_one_new(self):
        with self.db() as db, db:
            self.approval(db, iso(OLD))
            self.approval(db, iso(NEW))
        code, doc, _ = self.report()
        self.assertEqual((code, doc["approvals"]), (0, {"rows": 1, "oldest": OLD.date().isoformat()}))

    def test_missing_approvals_and_memory_tables_count_zero(self):
        self.schema("CREATE TABLE messages(provider_id TEXT PRIMARY KEY, disposition TEXT NOT NULL, received_at TEXT)")
        code, doc, _ = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(doc["approvals"], {"rows": 0, "oldest": None})
        self.assertEqual(doc["memory"], {"forgotten": 0, "superseded": 0, "oldest": None})
        self.schema()  # approvals schema present, memory still never created (it is lazy)
        self.assertEqual(self.report()[1]["memory"], {"forgotten": 0, "superseded": 0, "oldest": None})

    def test_memory_closed_rows_only_forgotten_dated_by_forgotten_at_once(self):
        with self.db(memory.TABLE) as db, db:
            self.remember(db, iso(OLDER))  # active, however old: current data, not counted
            self.remember(db, iso(OLDER), superseded=iso(OLD))
            self.remember(db, iso(OLDER), superseded=iso(NEW))
            self.remember(db, iso(OLDER), superseded=iso(OLDER), forgotten=iso(OLD))
            self.remember(db, iso(OLDER), superseded=iso(OLDER), forgotten=iso(NEW))  # superseded long ago, forgot now
        code, doc, _ = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(doc["memory"], {"forgotten": 1, "superseded": 1, "oldest": OLD.date().isoformat()})

    def test_zoneless_or_malformed_times_count_nowhere(self):
        with self.db() as db, db:
            db.executescript(memory.TABLE)
            for bad in ("2026-01-01T00:00:00", "not-a-time", ""):
                self.approval(db, bad)
                self.remember(db, iso(OLDER), forgotten=bad)
                self.remember(db, iso(OLDER), superseded=bad)
        code, doc, _ = self.report()
        self.assertEqual(code, 0)
        self.assertEqual(doc["approvals"], {"rows": 0, "oldest": None})
        self.assertEqual(doc["memory"], {"forgotten": 0, "superseded": 0, "oldest": None})

    def test_corrupt_conversation_db_is_unavailable_exit_1(self):
        self.conv.write_bytes(b"not a database at all, just junk bytes" * 40)
        code, doc, _ = self.report()
        self.assertEqual((code, doc["approvals"], doc["memory"]), (1, "unavailable", "unavailable"))
        self.assertEqual(doc["inbox"]["done"], 0)

    def test_output_has_no_values_and_dbs_are_untouched(self):
        with self.db() as db, db:
            db.executescript(memory.TABLE)
            self.approval(db, iso(OLD))
            self.remember(db, iso(OLDER), superseded=iso(OLD))
            self.remember(db, iso(OLDER), forgotten=iso(OLD))
        files = sorted(self.state.iterdir())
        before = {p.name: (p.read_bytes(), os.stat(p).st_mtime_ns) for p in files}
        code, doc, out = self.report()
        self.assertEqual((code, doc["approvals"]["rows"], doc["memory"]["forgotten"]), (0, 1, 1))
        self.assertEqual(out.count("\n"), 1)
        for canary in CANARIES: self.assertNotIn(canary, out)
        self.assertEqual(sorted(self.state.iterdir()), files)  # no -wal, -shm or -journal
        self.assertEqual({p.name: (p.read_bytes(), os.stat(p).st_mtime_ns) for p in files}, before)


if __name__ == "__main__":
    unittest.main()
