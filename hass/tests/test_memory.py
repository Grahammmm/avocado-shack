"""H15 tests: owner memory store (source/date, correct, forget) in a private temp state dir; no chat wiring."""

import contextlib, os, sqlite3, stat, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import memory, statebackup
from hass.tests.test_statebackup import BackupTestCase

T0 = datetime(2026, 11, 3, 17, 0, tzinfo=timezone.utc)
SECRET = "kumquat-tree-by-the-gate"


class Clock:
    """Advances one minute per call; raises once `fail_at` calls have been made (None: never)."""

    def __init__(self):
        self.calls: int = 0
        self.fail_at: int | None = None

    def __call__(self):
        if self.fail_at is not None and self.calls >= self.fail_at: raise RuntimeError("clock failed")
        self.calls += 1
        return T0 + timedelta(minutes=self.calls)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()  # 0700; the state dir below does not exist yet
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.clock = Clock()
        self.mem = memory.Memory(str(self.state), self.clock)
        self.addCleanup(self.mem.close)

    def rows(self, key=None):
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            sql, args = ("SELECT * FROM memory WHERE key = ? ORDER BY id", (key,)) if key else \
                ("SELECT * FROM memory ORDER BY id", ())
            return [dict(r) for r in db.execute(sql, args)]

    def test_remember_get_correct_list_keeps_dated_history(self):
        self.mem.remember("pickup.day", "Saturday", "fact", "owner-approved:chg-1", approved_change="chg-1")
        self.assertEqual(self.mem.get("pickup.day"), "Saturday")
        self.mem.correct("pickup.day", "Sunday", "owner-stated:msg-9")
        self.mem.remember("tone", "short replies", "preference", "operator:set at onboarding")
        listed = self.mem.list()
        self.assertEqual([(r["key"], r["value"]) for r in listed], [("pickup.day", "Sunday"), ("tone", "short replies")])
        self.assertEqual((listed[0]["kind"], listed[0]["source"]), ("fact", "owner-stated:msg-9"))
        old, new = self.rows("pickup.day")
        self.assertEqual((old["value"], old["approved_change"], new["value"]), ("Saturday", "chg-1", "Sunday"))
        self.assertTrue(old["created_at"] < old["superseded_at"] < new["created_at"])
        self.assertIsNone(new["superseded_at"])
        self.assertIsNone(self.mem.get("unknown"))

    def test_unverified_sources_write_nothing(self):
        for source in ("chat-history:msg-1", "model:guess", "", "owner-approved:", "Owner-Approved:chg-1",
                       " operator:x", "chat-history:owner-approved:chg-1", "owner-stated:msg\n1", None, "repeated"):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "unverified source"):
                self.mem.remember("pickup.day", "Saturday", "fact", source)
        self.mem.remember("pickup.day", "Saturday", "fact", "operator:ok")
        with self.assertRaisesRegex(ValueError, "unverified source"):
            self.mem.correct("pickup.day", "Sunday", "chat-history:msg-2")
        self.assertEqual([r["value"] for r in self.rows()], ["Saturday"])

    def test_duplicate_remember_requires_correct(self):
        self.mem.remember("pickup.day", "Saturday", "fact", "operator:ok")
        for value in ("Sunday", "Saturday"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "use correct"):
                self.mem.remember("pickup.day", value, "fact", "owner-approved:chg-2")
        self.assertEqual(len(self.rows()), 1)

    def test_forget_removes_text_keeps_dates(self):
        self.mem.remember("gate.code.hint", SECRET, "fact", "owner-stated:msg-1")
        self.mem.correct("gate.code.hint", SECRET + "-2", "owner-stated:msg-2")
        self.mem.remember("tone", "short replies", "preference", "operator:ok")
        self.mem.forget("gate.code.hint")
        self.assertIsNone(self.mem.get("gate.code.hint"))
        self.assertEqual([r["key"] for r in self.mem.list()], ["tone"])
        rows = self.rows("gate.code.hint")
        self.assertEqual([r["value"] for r in rows], ["", ""])
        self.assertTrue(rows[0]["superseded_at"] and rows[1]["forgotten_at"] and all(r["created_at"] for r in rows))
        self.assertNotIn(SECRET.encode(), (self.state / "conversation.sqlite3").read_bytes())
        with self.assertRaises(KeyError):
            self.mem.forget("gate.code.hint")  # already forgotten: nothing active
        self.mem.remember("gate.code.hint", "ask the owner", "fact", "operator:ok")
        self.assertEqual(self.mem.get("gate.code.hint"), "ask the owner")
        self.assertEqual(self.rows("tone")[0]["value"], "short replies")

    def test_forget_or_correct_unknown_key_changes_nothing(self):
        self.mem.remember("tone", "short replies", "preference", "operator:ok")
        before = self.rows()
        for call in (lambda: self.mem.forget("missing"), lambda: self.mem.correct("missing", "x", "operator:ok")):
            with self.assertRaises(KeyError):
                call()
        self.assertEqual(self.rows(), before)

    def test_bad_input_writes_nothing(self):
        cases = [("Pickup", "x", "fact"), ("pick up", "x", "fact"), ("-lead", "x", "fact"), ("a" * 65, "x", "fact"),
                 ("ok", "x" * 501, "fact"), ("ok", "a\x00b", "fact"), ("ok", "a\x7fb", "fact"), ("ok", "", "fact"),
                 ("ok", "line\nbreak", "fact"), ("ok", 5, "fact"), ("ok", "x", "rumour"), (None, "x", "fact")]
        for key, value, kind in cases:
            with self.subTest(key=key, value=value, kind=kind), self.assertRaises(ValueError):
                self.mem.remember(key, value, kind, "operator:ok")
        with self.assertRaises(ValueError):
            self.mem.remember("ok", "x", "fact", "operator:ok", approved_change="chg\x001")
        self.mem.remember("ok", "x" * 500, "fact", "operator:ok")
        with self.assertRaises(ValueError):
            self.mem.correct("ok", "y" * 501, "operator:ok")
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.clock.calls, 1)  # validation runs before any write or clock read

    def test_correct_is_atomic_when_the_clock_fails(self):
        self.mem.remember("pickup.day", "Saturday", "fact", "operator:ok")
        before = self.rows()
        self.clock.fail_at = self.clock.calls + 1  # the supersede stamp succeeds, the new row's stamp fails
        with self.assertRaisesRegex(RuntimeError, "clock failed"):
            self.mem.correct("pickup.day", "Sunday", "operator:ok")
        self.assertEqual((self.rows(), self.mem.get("pickup.day")), (before, "Saturday"))
        self.clock.fail_at = self.clock.calls  # forget fails at its first stamp: nothing blanked
        with self.assertRaises(RuntimeError):
            self.mem.forget("pickup.day")
        self.assertEqual(self.rows(), before)

    def test_database_is_private(self):
        path = self.state / "conversation.sqlite3"
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        os.chmod(path, 0o644)
        memory.Memory(str(self.state), self.clock).close()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


class BackupWithMemoryTests(BackupTestCase):
    def test_backup_covers_memory_rows(self):
        mem = memory.Memory(str(self.repo.state), lambda: T0)
        self.addCleanup(mem.close)
        mem.remember("pickup.day", "Saturday", "fact", "operator:ok")
        backup = self.backup()  # asserts result ok: memory adds no unknown state entry
        self.assertEqual(statebackup.verify(str(backup))["result"], "ok")
        with contextlib.closing(sqlite3.connect(backup / "conversation.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT key, value FROM memory").fetchall(), [("pickup.day", "Saturday")])


if __name__ == "__main__":
    unittest.main()
