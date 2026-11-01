"""RF1710-5 (H15 x H19): hass/health.py reports owner-memory rows that break the store's rules (count only).

Rows are written through hass.memory.Memory with a fixed clock, then hand-broken with plain sqlite; health reads them
from a temp 0700 state dir. Output must never carry the key, value or source.
"""
import contextlib, io, json, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path

from hass import health, memory
from hass.tests import test_health as base

NOW = base.NOW
KEY, VALUE, SOURCE = "secret-key.sentinel", "SECRET-VALUE-SENTINEL", "operator:SECRET-SOURCE-SENTINEL"


class Clock:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return NOW - timedelta(days=1) + timedelta(minutes=self.calls)


class HealthMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": base.SETTINGS}))
        self.path = self.state / "conversation.sqlite3"
        self.clock = Clock()

    def mem(self):
        mem = memory.Memory(str(self.state), self.clock)
        self.addCleanup(mem.close)
        return mem

    def sql(self, statement, args=()):
        with contextlib.closing(sqlite3.connect(self.path)) as db, db:
            db.execute(statement, args)

    def run_raw(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state)], now=NOW)
        [line] = out.getvalue().splitlines()
        return code, line

    def run_health(self):
        code, line = self.run_raw()
        for sentinel in (KEY, VALUE, SOURCE, "SENTINEL"):
            self.assertNotIn(sentinel, line)
        return code, json.loads(line)["problems"]

    def broken(self, detail):
        return 1, [{"check": "memory-invariant", "detail": detail}]

    def history(self):
        """remember/correct a fact (one superseded row, one active), remember and forget another key."""
        mem = self.mem()
        mem.remember(KEY, VALUE, "fact", SOURCE)
        mem.correct(KEY, VALUE + "-2", SOURCE)
        mem.remember("gone.key", VALUE + "-gone", "preference", SOURCE)
        mem.correct("gone.key", VALUE + "-gone-2", SOURCE)
        mem.forget("gone.key")
        return mem

    def test_normal_history_is_ok(self):
        self.history()
        self.assertEqual(self.run_health(), (0, []))

    def test_remember_again_after_forget_is_ok(self):
        mem = self.history()
        mem.remember("gone.key", VALUE + "-back", "fact", SOURCE)
        mem.correct("gone.key", VALUE + "-back-2", SOURCE)
        self.assertEqual(self.run_health(), (0, []))

    def test_second_active_row_counts_both(self):
        self.history()
        self.sql("INSERT INTO memory(key, value, kind, source, created_at) VALUES (?, ?, 'fact', ?, ?)",
                 (KEY, VALUE + "-dup", SOURCE, NOW.isoformat()))
        self.assertEqual(self.run_health(), self.broken("2 row(s)"))

    def test_one_active_row_per_key_on_different_keys_is_ok(self):
        mem = self.history()
        mem.remember("other.key", VALUE, "fact", SOURCE)
        self.assertEqual(self.run_health(), (0, []))

    def test_text_restored_into_forgotten_row(self):
        self.history()
        self.sql("UPDATE memory SET value = ? WHERE key = 'gone.key' AND forgotten_at IS NOT NULL", (VALUE,))
        self.assertEqual(self.run_health(), self.broken("1 row(s)"))

    def test_older_superseded_row_with_text_is_counted(self):
        self.history()
        self.sql("UPDATE memory SET value = ? WHERE key = 'gone.key'", (VALUE,))
        self.assertEqual(self.run_health(), self.broken("2 row(s)"))

    def test_text_left_before_reremember_is_counted_but_new_row_is_not(self):
        mem = self.history()
        mem.remember("gone.key", VALUE + "-back", "fact", SOURCE)
        self.sql("UPDATE memory SET value = ? WHERE key = 'gone.key' AND forgotten_at IS NOT NULL", (VALUE,))
        self.assertEqual(self.run_health(), self.broken("1 row(s)"))

    def test_row_created_at_the_forget_time_is_counted(self):
        self.history()
        self.sql("INSERT INTO memory(key, value, kind, source, created_at, superseded_at) SELECT key, ?, kind, source,"
                 " forgotten_at, forgotten_at FROM memory WHERE forgotten_at IS NOT NULL", (VALUE,))
        self.assertEqual(self.run_health(), self.broken("1 row(s)"))

    def test_both_breaks_add_up(self):
        self.history()
        self.sql("INSERT INTO memory(key, value, kind, source, created_at) VALUES (?, ?, 'fact', ?, ?)",
                 (KEY, VALUE + "-dup", SOURCE, NOW.isoformat()))
        self.sql("UPDATE memory SET value = ? WHERE key = 'gone.key'", (VALUE,))
        self.assertEqual(self.run_health(), self.broken("4 row(s)"))

    def test_no_memory_table_is_ok(self):
        self.sql("CREATE TABLE notes(id INTEGER PRIMARY KEY)")
        self.assertEqual(self.run_health(), (0, []))

    def test_unreadable_memory_table_is_memory_invariant_not_db_integrity(self):
        self.sql("CREATE TABLE memory(id INTEGER PRIMARY KEY, key TEXT)")
        self.sql("INSERT INTO memory(key) VALUES (?)", (KEY,))
        self.assertEqual(self.run_health(), self.broken("memory table unreadable"))

    def test_fingerprint_changes_with_the_count(self):
        self.history()
        self.sql("UPDATE memory SET value = ? WHERE key = 'gone.key' AND forgotten_at IS NOT NULL", (VALUE,))
        one = json.loads(self.run_raw()[1])["fingerprint"]
        self.sql("UPDATE memory SET value = ? WHERE key = 'gone.key'", (VALUE,))
        self.assertNotEqual(json.loads(self.run_raw()[1])["fingerprint"], one)


if __name__ == "__main__":
    unittest.main()
