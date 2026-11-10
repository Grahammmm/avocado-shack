"""SKILLS-FW-1: the 'I can't do that yet' backlog. A temp private state dir; no model, no network, no content write."""

import contextlib
import io
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import conversation, memory
from hass.skills import backlog, load_skills

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


class BacklogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.clock = Clock()
        self.store = backlog.Backlog.open(self.state, self.clock)
        self.addCleanup(self.store.close)

    def test_record_round_trip(self):
        n = self.store.record("unknown-skill", "order more eggs from the farm", "can you order more eggs from the farm")
        rows = self.store.rows(text=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], n)
        self.assertEqual((rows[0]["reason"], rows[0]["state"]), ("unknown-skill", "open"))
        self.assertEqual(rows[0]["summary"], "order more eggs from the farm")
        self.assertEqual(rows[0]["text"], "can you order more eggs from the farm")
        self.assertEqual(rows[0]["received_at"], T0.isoformat())

    def test_summary_defaults_to_the_start_of_the_message_and_is_capped(self):
        self.store.record("other", "", "x" * 500)
        self.store.record("other", "y" * 500, "z")
        a, b = self.store.rows()[1], self.store.rows()[0]
        self.assertEqual(len(a["summary"]), backlog.MAX_SUMMARY)
        self.assertEqual(len(b["summary"]), backlog.MAX_SUMMARY)

    def test_owner_text_is_capped_and_control_characters_removed(self):
        self.store.record("other", "s", "a\u202eb\x00c" + "d" * (backlog.MAX_TEXT + 50))
        text = self.store.rows(text=True)[0]["text"]
        self.assertEqual(len(text), backlog.MAX_TEXT)
        self.assertNotIn("\u202e", text)
        self.assertNotIn("\x00", text)

    def test_text_cap_matches_the_owner_message_cap(self):
        self.assertEqual(backlog.MAX_TEXT, conversation.MAX_OWNER_TEXT)

    def test_unknown_reason_is_refused(self):
        with self.assertRaises(ValueError):
            self.store.record("because", "s", "t")
        self.assertEqual(self.store.rows(), [])

    def test_rows_are_newest_first_and_last_ten(self):
        for i in range(12):
            self.store.record("other", f"ask {i}", "t")
        rows = self.store.rows()
        self.assertEqual(len(rows), backlog.LIST_MAX)
        self.assertEqual(rows[0]["summary"], "ask 11")

    def test_summary_listing_never_holds_the_text(self):
        self.store.record("other", "s", "private words")
        self.assertNotIn("text", self.store.rows()[0])
        self.assertNotIn("private words", self.store.owner_list())

    def test_owner_list_is_plain(self):
        self.assertEqual(self.store.owner_list(), backlog.EMPTY_LIST)
        n = self.store.record("other", "add a gift card option", "t")
        reply = self.store.owner_list()
        self.assertIn(f"{n}. 2026-11-08 - add a gift card option", reply)
        for jargon in ("backlog_", "sqlite", "reason", "unknown-skill"):
            self.assertNotIn(jargon, reply)

    def test_forget_removes_one_row_and_zeroes_nothing_else(self):
        a = self.store.record("other", "a", "t1")
        b = self.store.record("other", "b", "t2")
        self.assertTrue(self.store.forget(a))
        self.assertFalse(self.store.forget(a))
        self.assertFalse(self.store.forget("1"))
        self.assertFalse(self.store.forget(True))
        self.assertEqual([r["id"] for r in self.store.rows()], [b])

    def test_numbers_are_not_reused_after_forget_or_purge(self):
        a = self.store.record("other", "a", "t1")
        self.assertTrue(self.store.forget(a))
        b = self.store.record("other", "b", "t2")
        self.assertNotEqual(a, b)
        self.assertFalse(self.store.forget(a))  # stale forget for A leaves B
        self.assertEqual([r["id"] for r in self.store.rows()], [b])
        self.clock.now = self.clock.now + timedelta(days=200)
        self.assertEqual(self.store.purge(), 1)  # purge the highest row
        c = self.store.record("other", "c", "t3")
        self.assertGreater(c, b)
        self.assertFalse(self.store.forget(b))
        self.assertEqual([r["id"] for r in self.store.rows()], [c])

    def test_retention_is_ninety_days(self):
        self.assertEqual(backlog.RETENTION_DAYS, 90)
        self.store.record("other", "old", "t")
        self.clock.now = T0 + timedelta(days=89)
        self.store.record("other", "mid", "t")
        self.assertEqual(self.store.purge(), 0)
        self.clock.now = T0 + timedelta(days=91)
        self.assertEqual(self.store.purge(), 1)
        self.assertEqual([r["summary"] for r in self.store.rows()], ["mid"])

    def _seed(self, stamp, state="open", text="t"):
        cur = self.store.db.execute("INSERT INTO backlog(received_at, reason, summary, text, state) VALUES (?,?,?,?,?)",
                                    (stamp, "other", "s", text, state))
        return cur.lastrowid

    def _ids(self):
        return [r[0] for r in self.store.db.execute("SELECT id FROM backlog ORDER BY id")]

    def test_purge_uses_instants_for_positive_and_negative_offsets(self):
        self.clock.now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)  # cutoff 2026-08-11T12:00Z
        cases = {
            "2026-08-11T13:00:00+02:00": True,   # 11:00Z, expired
            "2026-08-11T07:00:00-07:00": False,  # 14:00Z, fresh
            "2026-08-11T14:00:00+02:00": False,  # 12:00Z exactly
            "2026-08-11T05:00:00-07:00": False,  # 12:00Z exactly
            "2026-08-11T11:00:00+00:00": True,
            "2026-08-11T13:00:00+00:00": False,
        }
        ids = {s: self._seed(s) for s in cases}
        self.assertEqual(self.store.purge(), sum(cases.values()))
        self.assertEqual(self._ids(), sorted(i for s, i in ids.items() if not cases[s]))

    def test_purge_preserves_microsecond_boundary(self):
        self.clock.now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        gone = self._seed("2026-08-11T11:59:59.999999+00:00")
        keep = [self._seed(s) for s in ("2026-08-11T12:00:00+00:00", "2026-08-11T12:00:00Z",
                                        "2026-08-11T05:00:00-07:00", "2026-08-11T12:00:00.000001+00:00")]
        self.assertEqual(self.store.purge(), 1)
        self.assertNotIn(gone, self._ids())
        self.assertEqual(self._ids(), keep)

    def test_purge_uses_elapsed_days_across_dst(self):
        from zoneinfo import ZoneInfo
        pac = ZoneInfo("America/Los_Angeles")
        # 90 elapsed days before 2026-11-09 12:00 PST (20:00Z) is 2026-08-11 20:00Z = 13:00 PDT.
        self.clock.now = datetime(2026, 11, 9, 12, 0, tzinfo=pac)
        gone = self._seed("2026-08-11T19:59:59+00:00")
        keep = self._seed("2026-08-11T20:00:00+00:00")
        self.assertEqual(self.store.purge(), 1)
        self.assertEqual(self._ids(), [keep])
        self.assertNotEqual(gone, keep)

    def test_purge_ages_legacy_open_and_closed_rows_without_rewriting(self):
        self.clock.now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        self.store.db.execute("CREATE TABLE sentinel(v TEXT)")
        self.store.db.execute("INSERT INTO sentinel VALUES ('x')")
        self._seed("2026-08-11T13:00:00+02:00", "open")
        self._seed("2026-08-11T13:00:00+02:00", "closed")
        a = self._seed("2026-08-11T07:00:00-07:00", "open")
        b = self._seed("2026-08-11T07:00:00-07:00", "closed")
        before = self.store.db.execute("SELECT * FROM backlog WHERE id IN (?,?) ORDER BY id", (a, b)).fetchall()
        self.assertEqual(self.store.purge(), 2)
        after = self.store.db.execute("SELECT * FROM backlog ORDER BY id").fetchall()
        self.assertEqual([tuple(r) for r in after], [tuple(r) for r in before])
        self.assertEqual(self.store.db.execute("SELECT v FROM sentinel").fetchall()[0][0], "x")
        self.assertEqual(self.store.purge(), 0)
        self.assertGreater(self.store.record("other", "n", "n"), b)

    def test_purge_retains_unknown_age_without_disclosing_text(self):
        self.clock.now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        keep = [self._seed(s, text="CANARY-PRIVATE") for s in ("garbage", "2026-01-01", "2026-01-01T00:00:00", "")]
        self._seed("2026-08-11T11:00:00+00:00", text="CANARY-PRIVATE")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(self.store.purge(), 1)
        self.assertEqual(self._ids(), keep)
        self.assertNotIn("CANARY", out.getvalue() + err.getvalue())
        self.clock.now = datetime(2026, 11, 9, 12, 0)  # naive
        with self.assertRaises(ValueError) as ctx:
            self.store.purge()
        self.assertNotIn("CANARY", str(ctx.exception))
        self.assertEqual(self._ids(), keep)

    def test_purge_cli_count_matches_offset_aware_deletions(self):
        self.clock.now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        self._seed("2026-08-11T13:00:00+02:00")
        keep = self._seed("2026-08-11T07:00:00-07:00")
        from unittest import mock
        out = io.StringIO()
        with mock.patch.object(backlog.Backlog, "open", return_value=self.store), contextlib.redirect_stdout(out):
            code = backlog._main(["purge", "--state", str(self.state)])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "removed 1 rows older than 90 days\n")

    def test_state_file_is_private_and_shared_with_conversation_db(self):
        path = self.state / "conversation.sqlite3"
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        db = sqlite3.connect(path)
        self.addCleanup(db.close)
        self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='backlog'").fetchone(), ("backlog",))

    def test_works_on_a_shared_connection_next_to_memory(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        db.row_factory = sqlite3.Row
        memory.Memory.on_connection(db, self.clock)
        shared = backlog.Backlog(db, self.clock)
        shared.record("price", "s", "t")
        self.assertEqual(len(shared.rows()), 1)

    def test_recording_changes_no_content_file(self):
        before = {p: p.stat().st_mtime_ns for p in (ROOT / "hass" / "content").glob("*.json")}
        self.store.record("policy", "make the logo bigger", "t")
        after = {p: p.stat().st_mtime_ns for p in (ROOT / "hass" / "content").glob("*.json")}
        self.assertEqual(before, after)

    def test_state_inside_the_checkout_is_refused(self):
        with self.assertRaises(Exception):
            backlog.Backlog.open(ROOT / "hass" / "tests" / "nope-state", self.clock)


class SkillTests(unittest.TestCase):
    def test_both_skills_are_read_only_and_plan_nothing(self):
        reg = load_skills()
        for name in ("backlog.log", "page.faq"):
            s = reg.skills[name]
            self.assertEqual((s.approval, s.live_class, s.edits, s.preview), ("none", "read-only", (), "none"))
            self.assertEqual(s.plan({}, None), [])
            self.assertIn("backlog-row", s.side_effects)
            self.assertEqual(s.undo.mode, "forget")

    def test_catalog_sentences_are_the_triggers(self):
        reg = load_skills()
        self.assertEqual(len(reg.skills["backlog.log"].triggers), 10)
        self.assertEqual(len(reg.skills["page.faq"].triggers), 10)

    def test_owner_replies_are_plain_and_honest(self):
        for text in (backlog.CANT_DO, backlog.NO_FAQ):
            self.assertIn("can't", text)
            self.assertIn("Nothing on the site changed", text)
            self.assertNotIn("#", text)
            self.assertNotRegex(text, r"\d")
        self.assertIn("I don't have", backlog.NOT_THERE)

    def test_reasons_match_the_table(self):
        db = sqlite3.connect(":memory:")
        db.execute(backlog.TABLE)
        for reason in backlog.REASONS:
            db.execute("INSERT INTO backlog(received_at, reason, summary, text) VALUES ('t', ?, 's', 't')", (reason,))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO backlog(received_at, reason, summary, text) VALUES ('t', 'zzz', 's', 't')")


class CliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        store = backlog.Backlog.open(self.state, Clock())
        store.record("other", "add a gift card option", "SECRET-OWNER-WORDS")
        store.close()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "hass" / "skills" / "backlog.py"), *args],
                              capture_output=True, text=True, cwd=ROOT)

    def test_list_shows_summaries_only(self):
        r = self.run_cli("list", "--state", str(self.state))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("add a gift card option", r.stdout)
        self.assertNotIn("SECRET-OWNER-WORDS", r.stdout)

    def test_list_text_is_the_operator_view(self):
        r = self.run_cli("list", "--state", str(self.state), "--text")
        self.assertIn("SECRET-OWNER-WORDS", r.stdout)

    def test_purge_reports(self):
        r = self.run_cli("purge", "--state", str(self.state))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("removed 0 rows", r.stdout)

    def test_unsafe_state_exits_2(self):
        r = self.run_cli("list", "--state", str(ROOT / "hass" / "tests" / "nope-state"))
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
