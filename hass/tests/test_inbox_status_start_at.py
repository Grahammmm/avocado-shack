"""RF1920-7 (H16): `inbox.py status` prints start_at only when it is a zoned ISO string; anything else is "unreadable".

Queues are built as test_inbox_status builds them (Inbox.enqueue/drain, fixed clock, throwaway 0700 dir); the meta
row is then hand-set as only a damaged or hand-edited store could hold it. Every run is one JSON line, no stderr, and
leaves the state dir's files, bytes and mtimes unchanged (StatusTests.run_status checks this).
Run: python3 -m unittest hass.tests.test_inbox_status_start_at -v
"""

import json
import os
import subprocess
import sys
import unittest

from hass.tests import test_inbox_status as base  # module import: its StatusTests is not collected a second time

GOOD = "2026-11-01T09:00:00+00:00"
REST = {"result": "ok", "pending": 1, "done": 1, "history": 1, "dispositions": {"applied": 1},
        "oldest_pending_minutes": 60, "nonces": 1}


class StartAtTests(unittest.TestCase):
    setUp, open_inbox, enqueue, snapshot, run_status = (base.StatusTests.setUp, base.StatusTests.open_inbox,
        base.StatusTests.enqueue, base.StatusTests.snapshot, base.StatusTests.run_status)

    def queue(self, untyped=False):
        """One pending, one done, one history row and a nonce. `untyped` swaps in a meta table whose value column has
        no type, so 42 stays an INTEGER and 4.5 a REAL (TEXT affinity would store them as '42' and '4.5')."""
        self.box = box = self.open_inbox()
        self.enqueue(box, "d1", "apply", 1)
        box.drain(base.StubConversation())
        self.enqueue(box, "p1", "hours", 2)
        self.enqueue(box, "h1", "hours", -1)
        box.seen().add("nonce-1")
        if untyped:
            box.db.execute("ALTER TABLE meta RENAME TO meta_typed")
            box.db.execute("CREATE TABLE meta(name TEXT PRIMARY KEY, value)")
            box.db.execute("INSERT INTO meta SELECT name, value FROM meta_typed")
        return box

    def set_start(self, value, kind):
        self.box.db.execute("UPDATE meta SET value = ? WHERE name = 'start_at'", (value,))
        self.assertEqual(self.box.db.execute("SELECT typeof(value) FROM meta WHERE name = 'start_at'").fetchone()[0],
                         kind)  # the cell really holds that storage class

    def assert_start(self, expected):
        report, code = self.run_status()
        self.assertEqual((report.pop("start_at"), code), (expected, 0))
        self.assertEqual(report, REST)  # every other key as main reports it

    def test_blob_start_at_is_unreadable_not_a_traceback(self):
        self.queue()
        self.box.db.execute("UPDATE meta SET value = X'00ff' WHERE name = 'start_at'")
        self.assertEqual(self.box.db.execute("SELECT typeof(value) FROM meta").fetchone()[0], "blob")
        self.assert_start("unreadable")  # main: TypeError: Object of type bytes is not JSON serializable

    def test_numbers_are_unreadable_not_printed_as_times(self):
        self.queue(untyped=True)
        for value, kind in ((42, "integer"), (4.5, "real"), (0, "integer"), (b"", "blob")):
            with self.subTest(value=value):
                self.set_start(value, kind)
                self.assert_start("unreadable")

    def test_garbage_or_zoneless_strings_are_unreadable(self):
        self.queue()
        for value in ("yesterday", "2026-11-01T09:00:00", "", "42", "4.5", GOOD + " junk", "2026-13-01T09:00:00+00:00"):
            with self.subTest(value=value):
                self.set_start(value, "text")
                self.assert_start("unreadable")

    def test_zoned_string_is_printed_unchanged(self):
        self.queue()
        for value in (GOOD, "2026-11-01T01:00:00-08:00", "2026-11-01T09:00:00.123456Z"):
            with self.subTest(value=value):
                self.set_start(value, "text")
                self.assert_start(value)  # as stored, not normalised

    def test_no_row_null_cell_or_no_meta_table_is_null(self):
        self.queue(untyped=True)
        self.set_start(None, "null")  # only an untyped, hand-edited table can hold it
        self.assert_start(None)
        self.box.db.execute("DELETE FROM meta")
        self.assert_start(None)
        self.box.db.execute("ALTER TABLE meta RENAME TO meta_gone")
        self.box.db.execute("ALTER TABLE meta_typed RENAME TO meta_old")
        self.assert_start(None)

    def test_bad_value_then_good_value_round_trip(self):
        self.queue()
        self.set_start("yesterday", "text")
        self.assert_start("unreadable")
        self.set_start(GOOD, "text")
        self.assert_start(GOOD)  # a repaired cell is read again; nothing was cached or rewritten

    def test_command_line_prints_one_line_for_a_blob(self):
        self.queue()
        self.box.db.execute("UPDATE meta SET value = X'00ff' WHERE name = 'start_at'")
        self.box.close()
        before = self.snapshot()
        proc = subprocess.run([sys.executable, str(base.REPO / "hass" / "inbox.py"), "status", "--state",
                               str(self.state)],
                              capture_output=True, text=True, timeout=60, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual((proc.returncode, proc.stderr, len(proc.stdout.splitlines())), (0, "", 1))
        self.assertEqual(json.loads(proc.stdout)["start_at"], "unreadable")
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
