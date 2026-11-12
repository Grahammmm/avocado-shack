"""RF0010-12 (H09/H16): a fixture `at` that parses with an offset but cannot be represented in UTC (year 1 east of
UTC, year 9999 west of it) is refused at row admission, so the whole fixture stops with exit 2 before any row is
handled, queued, sent or drained. Run: python3 -B -m unittest hass.tests.test_fixture_chat_utc_range -v
"""

import json
import tempfile
import unittest
from pathlib import Path

from hass.conversation import Inbound
from hass.fixture_chat import FixtureAdapter
from hass.inbox import Inbox
from hass.tests import test_fixture_chat_queue as queue_tests
from hass.tests import test_fixture_chat_rows as row_tests

PAIR, START, line = queue_tests.PAIR, queue_tests.START, queue_tests.line
UTC_RANGE = "at must be representable in UTC"
LOW, HIGH = "0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"
BAD = [LOW, HIGH, "0001-01-01T00:59:59.999999+01:00", "9999-12-31T23:00:00.000001-01:00"]
GOOD = ["0001-01-01T00:00:00+00:00", "0001-01-01T01:00:00+01:00", "9999-12-31T23:59:59.999999+00:00",
        "9999-12-31T22:59:59.999999-01:00", "0001-01-01T00:00:00Z"]


class FixtureUtcRangeTests(unittest.TestCase):
    fresh, run_cli, query, refused = (row_tests.FixtureRowTests.fresh, row_tests.FixtureRowTests.run_cli,
                                      row_tests.FixtureRowTests.query, row_tests.FixtureRowTests.refused)

    def admit(self, text):  # FixtureAdapter.inbound on a temporary fixture file
        folder = tempfile.TemporaryDirectory(prefix="hass-utc-")
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "fixture.jsonl"
        path.write_text(text, "utf-8")
        return FixtureAdapter(path).inbound()

    def refused_with(self, text, message):
        with self.assertRaises(ValueError) as caught:
            self.admit(text)
        self.assertEqual(str(caught.exception), f"fixture {message}")
        return str(caught.exception)

    def mixed(self):  # ordinary row, blank line, out-of-range row on physical line 3, ordinary row
        return json.dumps(PAIR[0]) + "\n\n" + json.dumps(line("q-3", "yes", LOW)) + "\n" + json.dumps(PAIR[1]) + "\n"

    def nothing_handled(self, repo):
        for table in ("messages", "drafts", "approvals", "outbox"):
            self.assertEqual(self.query(repo, "conversation", f"SELECT * FROM {table}"), [], table)

    def test_utc_underflow_and_overflow_refused_at_row_admission(self):
        for at in BAD:
            with self.subTest(at=at):
                error = self.refused_with(json.dumps(line("u-1", "hi", at)) + "\n", f"line 1: {UTC_RANGE}")
                self.assertNotIn(at[:4], error)
                self.assertNotIn("Overflow", error)

    def test_bad_later_time_stops_direct_before_first_handle(self):
        repo, head = self.fresh()
        run = self.run_cli(repo, [], text=self.mixed())
        self.refused(run, f"fixture line 3: {UTC_RANGE}", repo, head)  # exit 2, empty stdout: nothing sent
        self.nothing_handled(repo)
        self.assertEqual(repo.head(), head)

    def test_bad_later_time_stops_queue_before_first_enqueue_or_drain(self):
        repo, head = self.fresh()
        inbox = Inbox(repo.state, start_at=START)
        try:
            self.assertEqual(inbox.enqueue(Inbound("p-1", PAIR[0]["chat"], PAIR[0]["sender"], "hello", False, "new",
                                                   "2026-11-02T08:45:00-08:00")), "queued")
        finally:
            inbox.close()
        before = self.query(repo, "inbox", "SELECT provider_id, state, payload IS NOT NULL FROM inbound")
        self.assertEqual(before, [("p-1", "pending", 1)])
        run = self.run_cli(repo, [], "--queue", START, text=self.mixed())
        self.refused(run, f"fixture line 3: {UTC_RANGE}", repo, head)
        self.nothing_handled(repo)
        self.assertEqual(self.query(repo, "inbox", "SELECT provider_id, state, payload IS NOT NULL FROM inbound"),
                         before)  # no fixture row queued; the preloaded entry is still pending and undrained

    def test_representable_endpoint_offsets_remain_exact(self):
        rows = self.admit("".join(json.dumps(line(f"g-{i}", "hi", at)) + "\n" for i, at in enumerate(GOOD)))
        self.assertEqual([r.received_at for r in rows], GOOD)

    def test_ordinary_offsets_and_subseconds_preserve_replay(self):
        repo, _ = self.fresh()
        rows = [{**PAIR[0], "at": "2026-11-02T17:00:00.250000+00:00"}, {**PAIR[1], "at": "2026-11-02T09:01:00.5-08:00"}]
        run = self.run_cli(repo, rows)
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        texts = [json.loads(r)["text"] for r in run.stdout.splitlines()]
        self.assertEqual([t.split(" ")[0] for t in texts], ["Here's", "Saved:"])
        self.assertEqual(self.query(repo, "conversation", "SELECT received_at FROM messages ORDER BY provider_id"),
                         [(rows[0]["at"],), (rows[1]["at"],)])

    def test_first_bad_field_and_physical_line_precedence(self):
        no_sender = {k: v for k, v in line("s-1", "hi", PAIR[0]["at"]).items() if k != "sender"}
        cases = [  # (rows with "" as a blank line, expected message)
            ([{**PAIR[0], "at": "2026-11-02T09:00:00"}, line("u-2", "hi", HIGH)], f"line 1: {row_tests.OFFSET}"),
            (["", no_sender, line("u-3", "hi", LOW)], "line 2: sender must be a string"),
            (["", line("u-2", "CANARY-9", HIGH), no_sender], f"line 2: {UTC_RANGE}"),
            ([PAIR[0], line("u-2", "hi", "not a time"), line("u-3", "hi", LOW)], f"line 2: {row_tests.OFFSET}"),
        ]
        for rows, message in cases:
            with self.subTest(message=message):
                text = "".join((json.dumps(r) if r else "") + "\n" for r in rows)
                self.assertNotIn("CANARY", self.refused_with(text, message))


if __name__ == "__main__":
    unittest.main()
