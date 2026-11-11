"""RF0115-10: OpenRequests.put at the calendar end refuses unrepresentable idle deadlines before any write."""
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from hass.skills import openreq

UTC = timezone.utc
MSG = "request expiry is outside the supported date range"


def dump(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'open_requests'").fetchone():
        return None
    return [tuple(r) for r in db.execute("SELECT * FROM open_requests ORDER BY request_id")]


class CalendarEnd(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.store = openreq.OpenRequests(self.db)

    def put(self, at, owner="o1", **kw):
        return self.store.put(owner, "p1", at, texts=["hello"], **kw)

    def test_renewal_with_unrepresentable_nonbinding_hard_cap_keeps_valid_idle_deadline(self):
        rid = self.put(datetime(9999, 12, 31, 22, 30, tzinfo=UTC), skill="s")
        self.put(datetime(9999, 12, 31, 22, 45, tzinfo=UTC), skill="s", request_id=rid)
        row = self.db.execute("SELECT * FROM open_requests").fetchone()
        self.assertEqual(row["expires_at"], "9999-12-31T23:15:00+00:00")
        self.assertEqual(row["request_id"], rid)
        self.assertTrue(row["created_at"].startswith("9999-12-31T22:30:00"))

    def test_unrepresentable_new_idle_deadline_refuses_before_schema_creation(self):
        before = self.db.total_changes
        with self.assertRaises(ValueError) as cm:
            self.put(datetime(9999, 12, 31, 23, 45, tzinfo=UTC))
        self.assertEqual(str(cm.exception), MSG)
        self.assertIsNone(dump(self.db))
        self.assertEqual(self.db.total_changes, before)

    def test_unrepresentable_superseding_write_preserves_live_request(self):
        self.put(datetime(9999, 12, 31, 23, 20, tzinfo=UTC), skill="s")
        self.put(datetime(9999, 12, 31, 23, 20, tzinfo=UTC), owner="o2", skill="s")
        before, changes = dump(self.db), self.db.total_changes
        with self.assertRaises(ValueError):
            self.put(datetime(9999, 12, 31, 23, 45, tzinfo=UTC), skill="s2")
        self.assertEqual(dump(self.db), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_unrepresentable_renewal_is_write_free(self):
        rid = self.put(datetime(9999, 12, 31, 23, 20, tzinfo=UTC), skill="s")
        before, changes = dump(self.db), self.db.total_changes
        with self.assertRaises(ValueError):
            self.put(datetime(9999, 12, 31, 23, 45, tzinfo=UTC), skill="s", request_id=rid)
        self.assertEqual(dump(self.db), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_exact_last_representable_deadline_and_microseconds(self):
        edge = datetime.max.replace(tzinfo=UTC) - timedelta(minutes=30)
        self.put(edge)
        self.assertEqual(self.db.execute("SELECT expires_at FROM open_requests").fetchone()[0],
                         datetime.max.replace(tzinfo=UTC).isoformat())
        with self.assertRaises(ValueError):
            self.put(edge + timedelta(microseconds=1), owner="o2")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM open_requests").fetchone()[0], 1)

    def test_binding_cap_legacy_exemption_and_transaction_ownership(self):
        t = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
        rid = self.put(t, skill="s")
        self.put(t + timedelta(minutes=100), skill="s", request_id=rid)
        self.assertTrue(self.db.execute("SELECT expires_at FROM open_requests").fetchone()[0].startswith("2026-11-10T02:00"))
        lid = self.put(t, owner="o2")
        self.put(t + timedelta(minutes=100), owner="o2", request_id=lid, legacy=True)
        self.assertTrue(self.db.execute("SELECT expires_at FROM open_requests WHERE owner='o2'").fetchone()[0].startswith("2026-11-10T02:10"))
        self.db.execute("BEGIN")
        with self.assertRaises(ValueError):
            self.put(datetime(9999, 12, 31, 23, 45, tzinfo=UTC), owner="o3")
        self.assertTrue(self.db.in_transaction)
        self.db.execute("ROLLBACK")


if __name__ == "__main__":
    unittest.main()
