"""RF1501-10: Backlog.forget refuses identifiers SQLite cannot bind. Synthetic in-memory rows only."""

import sqlite3
import unittest
from datetime import datetime, timezone

from hass.skills import backlog

MAX_ID = 2**63 - 1
MIN_ID = -(2**63)


def make_store():
    db = sqlite3.connect(":memory:", isolation_level=None)
    store = backlog.Backlog(db, lambda: datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc))
    return store, db


def snapshot(db):
    return db.execute("SELECT * FROM backlog ORDER BY id").fetchall(), db.total_changes


class ForgetBoundsTests(unittest.TestCase):
    def test_forget_outside_sqlite_integer_range_is_false_without_mutation(self):
        for bad in (2**63, MIN_ID - 1, 10**100, -(10**100)):
            with self.subTest(bad=bad):
                store, db = make_store()
                store.record("other", "one", "first")
                store.record("other", "two", "second")
                before = snapshot(db)
                statements = []
                db.set_trace_callback(statements.append)
                self.assertIs(store.forget(bad), False)
                db.set_trace_callback(None)
                self.assertEqual(snapshot(db), before)
                self.assertFalse([s for s in statements if s.lstrip().upper().startswith("DELETE")])

    def test_forget_supported_missing_boundary_ids_is_false(self):
        store, db = make_store()
        store.record("other", "one", "first")
        before = snapshot(db)
        for missing in (MIN_ID, -1, 0, MAX_ID):
            with self.subTest(missing=missing):
                self.assertIs(store.forget(missing), False)
                self.assertEqual(snapshot(db), before)

    def test_forget_maximum_supported_existing_id_removes_only_target(self):
        store, db = make_store()
        keep = store.record("other", "keep", "ordinary")
        db.execute("INSERT INTO backlog(id, received_at, reason, summary, text) VALUES (?,?,?,?,?)",
                   (MAX_ID, "2026-11-08T17:00:00+00:00", "other", "max", "synthetic"))
        self.assertIs(store.forget(MAX_ID), True)
        self.assertEqual([r[0] for r in db.execute("SELECT id FROM backlog")], [keep])
        self.assertIs(store.forget(MAX_ID), False)

    def test_forget_valid_id_and_invalid_types_preserve_existing_contract(self):
        store, db = make_store()
        first = store.record("other", "one", "first")
        second = store.record("other", "two", "second")
        for bad in (True, "1", 1.0, None):
            with self.subTest(bad=bad):
                self.assertIs(store.forget(bad), False)
        self.assertIs(store.forget(first), True)
        self.assertIs(store.forget(first), False)
        self.assertEqual([r[0] for r in db.execute("SELECT id FROM backlog")], [second])
        self.assertGreater(store.record("other", "three", "third"), second)


if __name__ == "__main__":
    unittest.main()
