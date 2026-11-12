"""RF0440-12 (H16): reopening an Inbox whose recorded start point is damaged is refused with one fixed ValueError.
Run: python3 -B -m unittest hass.tests.test_inbox_recorded_start -v
"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass import editor
from hass.conversation import Inbound
from hass.inbox import Inbox
from hass.tests import test_fixture_chat_queue as fcq

FIXED = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
GOOD = "2026-11-11T12:00:00+00:00"
CANARY = "SYNTHETIC_BAD_START_CANARY"
REFUSAL = "recorded start point is unreadable"


def _msg(mid, at):
    return Inbound(provider_id=mid, chat="c", sender="s", text="t", from_me=False, kind="new", received_at=at)


class RecordedStartTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.state.mkdir(mode=0o700)
        Inbox(self.state, start_at=GOOD, clock=lambda: FIXED).close()

    def damage(self, value):
        con = sqlite3.connect(self.state / "inbox.sqlite3")
        try:
            con.execute("UPDATE meta SET value = ? WHERE name = 'start_at'", (value,))
            con.commit()
        finally:
            con.close()

    def cell(self):
        con = sqlite3.connect(self.state / "inbox.sqlite3")
        try:
            return con.execute("SELECT value FROM meta WHERE name = 'start_at'").fetchone()[0]
        finally:
            con.close()

    def test_zoneless_and_unreadable_cutoffs_refuse_before_enqueue(self):
        for bad in ("2026-11-11T12:00:00", "2026-11-11", "", CANARY, "2026-13-45T00:00:00Z", b"SYNTHETIC_BLOB"):
            for supplied in (None, GOOD):
                with self.subTest(bad=bad, supplied=supplied):
                    self.damage(bad)
                    with self.assertRaises(ValueError) as ctx:
                        Inbox(self.state, start_at=supplied)
                    self.assertEqual(str(ctx.exception), REFUSAL)
                    self.assertIsNone(ctx.exception.__cause__)
                    self.assertTrue(ctx.exception.__suppress_context__)
                    self.assertEqual(self.cell(), bad)  # not repaired, replaced or guessed

    def test_bad_cutoff_is_not_reinitialized_and_rows_survive(self):
        box = Inbox(self.state, clock=lambda: FIXED)
        self.assertEqual(box.enqueue(_msg("m1", "2026-11-11T13:00:00+00:00")), "queued")
        box.close()
        self.damage(CANARY)
        with self.assertRaises(ValueError):
            Inbox(self.state, start_at="2030-01-01T00:00:00+00:00")
        self.assertEqual(self.cell(), CANARY)
        con = sqlite3.connect(self.state / "inbox.sqlite3")
        try:
            self.assertEqual(con.execute("SELECT provider_id, state FROM inbound").fetchall(), [("m1", "pending")])
        finally:
            con.close()

    def test_invalid_supplied_argument_keeps_its_own_error(self):
        self.damage(CANARY)
        with self.assertRaises(ValueError) as ctx:
            Inbox(self.state, start_at="2026-11-11T12:00:00")
        self.assertEqual(str(ctx.exception), "start_at must be a timezone-aware ISO-8601 time")

    def test_valid_cutoffs_still_reopen(self):
        for ok in ("2026-11-11T04:00:00-08:00", "2026-11-11T12:00:00.250Z"):
            self.damage(ok)
            box = Inbox(self.state, clock=lambda: FIXED)
            self.assertEqual(box.enqueue(_msg("v" + ok[-6:], "2026-11-11T20:00:00+00:00")), "queued")
            box.close()
            self.assertEqual(self.cell(), ok)

    def test_fixture_chat_refusal_never_echoes_damaged_metadata(self):
        helper = fcq.FixtureChatQueueTests()
        repo = fcq.WriterRepo()
        self.addCleanup(repo.cleanup)
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor._write_json(repo.state / "config.json", {**cfg, "settings": fcq.SETTINGS})
        Inbox(repo.state, start_at=fcq.START).close()
        con = sqlite3.connect(repo.state / "inbox.sqlite3")
        con.execute("UPDATE meta SET value = ? WHERE name = 'start_at'", (CANARY,))
        con.commit()
        con.close()
        run = helper.run_cli(repo, fcq.PAIR, "--queue", fcq.START)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stdout, "")
        self.assertEqual(run.stderr, f"fixture_chat: ValueError: {REFUSAL}\n")
        self.assertEqual(helper.query(repo, "inbox", "SELECT COUNT(*) FROM inbound"), [(0,)])


if __name__ == "__main__":
    unittest.main()
