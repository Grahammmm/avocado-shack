"""Read-only status survives an unreadable superseded-request expiry (synthetic SQLite state only)."""
import contextlib
import io
import logging
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from hass.skills.openreq import OpenRequests

UTC = timezone.utc
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
CANARY = "private-expiry-canary"


class Registry:
    def __init__(self, labels):
        self.labels = labels

    def get(self, name):
        if name not in self.labels:
            return None
        return SimpleNamespace(label=self.labels[name])


REG = Registry({"hike.add": "an earlier hike", "item.describe": "a description"})


def snapshot(db):
    return [tuple(r) for r in db.execute("SELECT * FROM open_requests ORDER BY request_id")]


class StatusExpiryCase(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.store = OpenRequests(self.db)

    def replaced_pair(self, owner="o1", first="hike.add", second="item.describe"):
        old = self.store.put(owner, "m1", NOW, texts=["a"], skill=first)
        self.store.put(owner, "m2", NOW, texts=["b"], skill=second)
        return old

    def set_expiry(self, rid, value):
        self.db.execute("UPDATE open_requests SET expires_at = ? WHERE request_id = ?", (value, rid))
        self.db.commit()

    def status(self, now=NOW, owner="o1", registry=REG):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertNoLogs(level=logging.DEBUG):
            lines = self.store.status_lines(owner, now, registry)
        self.assertEqual(out.getvalue() + err.getvalue(), "")
        return lines


class DamagedExpiryTests(StatusExpiryCase):
    def test_invalid_superseded_iso_does_not_discard_live_status(self):
        old = self.replaced_pair()
        self.assertEqual(self.status(), ["Open: a description", "Replaced: an earlier hike"])
        self.set_expiry(old, CANARY)
        before = snapshot(self.db)
        lines = self.status()
        self.assertEqual(lines, ["Open: a description"])
        self.assertNotIn(CANARY, "".join(lines))
        self.assertEqual(snapshot(self.db), before)

    def test_blob_and_naive_superseded_expiries_are_not_status_failures(self):
        for bad in (b"\x00\xffblob", "2026-13-45T99:00:00+00:00", "2026-11-01T13:00:00"):
            with self.subTest(bad=bad):
                self.db.execute("DROP TABLE IF EXISTS open_requests")
                old = self.replaced_pair()
                self.set_expiry(old, bad)
                before = snapshot(self.db)
                self.assertEqual(self.status(), ["Open: a description"])
                self.assertEqual(snapshot(self.db), before)

    def test_healthy_replaced_status_inclusive_boundary_and_offsets(self):
        old = self.replaced_pair()
        expiry = datetime(2026, 11, 1, 12, 30, tzinfo=UTC)
        spellings = ["2026-11-01T12:30:00+00:00", "2026-11-01T12:30:00Z", "2026-11-01T04:30:00-08:00",
                     "2026-11-01T14:30:00+02:00"]
        for text in spellings:
            self.set_expiry(old, text)
            for now, shown in ((expiry - timedelta(microseconds=1), True), (expiry, True),
                               (expiry + timedelta(microseconds=1), False)):
                with self.subTest(text=text, now=now):
                    lines = self.status(now)
                    self.assertEqual("Replaced: an earlier hike" in lines, shown)
        # registry label fallback
        self.set_expiry(old, "2026-11-01T12:30:00+00:00")
        self.assertEqual(self.status(registry=Registry({})), ["Open: a request", "Replaced: an earlier request"])
        self.assertEqual(self.status(registry=None), ["Open: a request", "Replaced: an earlier request"])
        # valid naive expiry with naive clock keeps its existing behaviour
        self.set_expiry(old, "2026-11-01T12:30:00")
        naive = NOW.replace(tzinfo=None)
        self.assertIn("Replaced: an earlier hike", self.store.status_lines("o1", naive, REG))
        self.assertNotIn("Replaced: an earlier hike", self.store.status_lines("o1", naive + timedelta(hours=1), REG))

    def test_other_owner_and_newest_only_selection_unchanged(self):
        oldest = self.replaced_pair("o1", "hike.add", "item.describe")  # superseded #1 (healthy)
        self.store.put("o1", "m3", NOW, texts=["c"], skill="hike.add")  # supersedes the live one -> newest superseded
        self.replaced_pair("o2")
        self.set_expiry(oldest, "2026-11-01T12:30:00+00:00")
        # the newest superseded row of o1 is the item.describe request closed by the third put
        newest = self.db.execute("SELECT MAX(request_id) FROM open_requests WHERE owner='o1' AND state='superseded'").fetchone()[0]
        self.assertNotEqual(newest, oldest)
        self.set_expiry(newest, CANARY)
        before = snapshot(self.db)
        self.assertEqual(self.status(), ["Open: an earlier hike"])  # no fall back to the older healthy row
        self.assertEqual(self.status(owner="o2"), ["Open: a description", "Replaced: an earlier hike"])
        self.assertEqual(snapshot(self.db), before)

    def test_no_live_request_and_no_table_remain_read_only(self):
        self.assertEqual(self.status(), [])
        self.assertFalse(self.store.exists())
        old = self.replaced_pair()
        self.db.execute("UPDATE open_requests SET state = 'closed' WHERE state IN ('open','drafted')")
        self.set_expiry(old, CANARY)
        before, changes = snapshot(self.db), self.db.total_changes
        for _ in range(2):
            self.assertEqual(self.status(), [])
        self.assertEqual(snapshot(self.db), before)
        self.assertEqual(self.db.total_changes, changes)

    def test_non_timestamp_programming_errors_are_not_swallowed(self):
        self.replaced_pair()

        class Broken:
            def get(self, name):
                raise RuntimeError("registry failure")

        with self.assertRaises(RuntimeError):
            self.store.status_lines("o1", NOW, Broken())


if __name__ == "__main__":
    unittest.main()
