"""AV1052-10 (H17/H19) tests: a request the reader could not read stays visible in `status`.

Fake interpreters only (no model, no network); injected clock; same H06 setup as the other status tests.
Run: python3 -m unittest hass.tests.test_status_reader_failed -v
"""

import unittest
from datetime import timedelta
from pathlib import Path

from hass import conversation
from hass.tests.test_interpreter_cap import CapTestCase
from hass.tests.test_undo import H06TestCase

FAILED = {"unsupported": "I couldn't work that out just now, so nothing was changed. Please try again in a few minutes."}
LINE = "Last request not read: Monday 09:00 - the reader was not working; send it again"
SUPPORT = Path(__file__).resolve().parents[2] / "docs" / "hass" / "SUPPORT.md"


class Reader(conversation.FixtureInterpreter):
    """Fixture interpreter with LocalInterpreter's last_error contract: 'down' fails, 'boom' raises."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.last_error, self.calls = None, 0

    def interpret(self, text, pending, **kw):
        self.calls += 1
        if text == "boom": raise RuntimeError("simulated")  # last_error deliberately left as it was
        self.last_error = "http-503" if text == "down" else None
        return dict(FAILED) if text == "down" else super().interpret(text, pending)


class ReaderFailedTests(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp = Reader(self.interp.mapping)
        self.conv = self.open()

    def status(self):
        self.replies()
        self.assertEqual(self.say("status"), "status")
        [reply] = self.replies()
        return reply.splitlines()

    def control(self):
        return [tuple(r) for r in self.conv.db.execute("SELECT name, value, set_at FROM control")] \
            if "control" in {r[0] for r in self.conv.db.execute("SELECT name FROM sqlite_master")} else None

    def test_failure_is_recorded_reply_unchanged_and_shown_in_status(self):
        self.assertEqual(self.say("down", pid="f1"), "reader-failed")
        self.assertEqual(self.replies(), [FAILED["unsupported"]])
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.conv.db.execute("SELECT disposition FROM messages WHERE provider_id = 'f1'")
                         .fetchone()[0], "reader-failed")
        self.assertEqual(self.control(), [("reader-failed", "1", "2026-11-02T17:00:00+00:00")])
        lines = self.status()
        self.assertEqual(lines.count(LINE), 1)
        self.assertEqual(self.status().count(LINE), 1)  # status again, still there
        self.assertEqual(self.interp.calls, 1)  # status never calls the reader, nothing is retried
        self.conv = self.open()  # restart
        self.assertEqual(self.status().count(LINE), 1)

    def test_line_sits_before_waiting_drafts_and_survives_commands_and_pause(self):
        self.propose("hours")
        self.say("down")
        self.say("pause changes")
        lines = self.status()
        i = lines.index(LINE)
        self.assertTrue(lines[i + 1].endswith(": store store: hours") or "waiting" in lines[i + 1], lines)
        self.assertTrue(lines[0].startswith("Changes: paused"))
        self.now += timedelta(days=3)
        self.assertEqual(self.status().count("Last request not read: Monday 09:00 - the reader was not working; "
                                             "send it again"), 1)

    def test_a_read_request_clears_only_the_marker(self):
        self.say("pause changes")
        self.say("down")
        self.assertEqual(self.say("when?"), "question")  # a clarification is still a read
        self.replies()
        self.assertNotIn(LINE, self.status())
        self.assertTrue(self.status()[0].startswith("Changes: paused"))
        self.assertEqual(self.conv.db.execute("SELECT name FROM control").fetchall()[0][0], "paused")
        self.assertEqual(self.conv.db.execute(
            "SELECT disposition FROM messages WHERE disposition = 'reader-failed'").fetchone()[0], "reader-failed")

    def test_nonreads_neither_clear_nor_create_and_ordinary_success_makes_no_control_table(self):
        self.say("hours")
        self.assertIsNone(self.control())
        self.say("down")
        for text in ("status", "history", "remember parking: back lot"):
            self.say(text)
        self.assertEqual(self.control(), [("reader-failed", "1", "2026-11-02T17:00:00+00:00")])
        self.say("hours")  # a draft is proposed: read again
        self.assertEqual(self.control(), [])

    def test_latest_failure_wins_and_bad_timestamp_stays_visible(self):
        self.say("down")
        self.now += timedelta(hours=2)
        self.say("down")
        self.assertIn("Last request not read: Monday 11:00 - the reader was not working; send it again", self.status())
        self.conv.db.execute("UPDATE control SET set_at = 'garbage' WHERE name = 'reader-failed'")
        self.assertIn("Last request not read: time unavailable - the reader was not working; send it again",
                      self.status())

    def test_no_marker_means_no_line_and_no_control_table_from_status(self):
        self.assertFalse(any(line.startswith("Last request not read") for line in self.status()))
        self.assertIsNone(self.control())

    def test_support_row_is_not_a_health_heading(self):
        text = SUPPORT.read_text("utf-8")
        head, _, _ = text.partition("## Problems")
        self.assertIn("## Reader not working", head)
        self.assertIn("the reader was not working; send it again", head)
        self.assertNotIn("### `reader-failed`", text)


class ReaderFailedCapTests(CapTestCase):
    CAP = 3

    def setUp(self):
        super().setUp()
        self.interp = Reader(self.interp.mapping)
        self.conv = self.open()

    def test_failure_counts_once_and_cap_or_raise_do_not_mark(self):
        self.assertEqual(self.say("down"), "reader-failed")
        self.assertEqual(self.interp.calls, 1)
        self.assertEqual(self.conv.db.execute("SELECT calls FROM usage").fetchone()[0], 1)
        self.say("hours")  # read again: cleared
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM control").fetchone()[0], 0)
        self.interp.last_error = "http-503"  # stale error from earlier; a capped exception is not a new failure
        self.assertEqual(self.say("boom"), "unsupported")
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM control").fetchone()[0], 0)
        self.replies()
        self.limited("desc")  # over the cap: no read
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM control").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
