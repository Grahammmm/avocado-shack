"""Elapsed inactivity deadlines on synthetic stores and the real conversation path."""
import contextlib
import io
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from hass.skills.openreq import OpenRequests
from hass.tests.test_skill_dispatch import FIRST, MILL, SkillCase, skill_reply

UTC = timezone.utc
PACIFIC = ZoneInfo("America/Los_Angeles")
START = datetime(2026, 11, 1, 1, 45, tzinfo=PACIFIC, fold=0)
DUE = datetime(2026, 11, 1, 9, 15, tzinfo=UTC)
CANARY = "synthetic-earlier-text-zq81"


class ElapsedStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.store = OpenRequests(self.db)

    def put(self, at, **kwargs):
        return self.store.put("owner", kwargs.pop("provider_id", "m1"), at,
                              texts=[CANARY], skill="hike.add", **kwargs)

    def row(self, rid):
        return dict(self.db.execute("SELECT * FROM open_requests WHERE request_id = ?", (rid,)).fetchone())

    def assert_deadline(self, rid, due):
        self.assertEqual(datetime.fromisoformat(self.row(rid)["expires_at"]).astimezone(UTC), due)
        self.assertIsNotNone(self.store.get("owner", due))
        self.assertIsNone(self.store.get("owner", due + timedelta(microseconds=1)))

    def test_new_request_fall_back_deadline_is_thirty_elapsed_minutes(self):
        rid = self.put(START)
        self.assert_deadline(rid, DUE)
        self.assertEqual(self.row(rid)["expires_at"], "2026-11-01T01:15:00-08:00")
        self.store.sweep(datetime(2026, 11, 1, 9, 16, tzinfo=UTC))
        self.assertEqual(self.row(rid)["state"], "expired")

    def test_renewed_request_fall_back_deadline_is_thirty_elapsed_minutes(self):
        first = datetime(2026, 11, 1, 1, 20, tzinfo=PACIFIC, fold=0)
        rid = self.put(first)
        self.assertEqual(self.put(START, request_id=rid, provider_id="m2"), rid)
        self.assert_deadline(rid, DUE)
        row = self.row(rid)
        self.assertEqual(row["created_at"], first.isoformat())
        self.assertEqual(row["updated_at"], START.isoformat())
        self.assertEqual(row["provider_id"], "m2")
        self.store.sweep(datetime(2026, 11, 1, 9, 16, tzinfo=UTC))
        self.assertEqual(self.row(rid)["state"], "expired")

    def test_second_fold_spring_and_fixed_offset_controls_preserve_deadlines(self):
        cases = [
            (datetime(2026, 11, 1, 1, 45, tzinfo=PACIFIC, fold=1),
             "2026-11-01T10:15:00+00:00", "2026-11-01T02:15:00-08:00"),
            (datetime(2026, 3, 8, 1, 45, tzinfo=PACIFIC),
             "2026-03-08T10:15:00+00:00", "2026-03-08T03:15:00-07:00"),
            (datetime(2026, 11, 2, 1, 45, tzinfo=PACIFIC),
             "2026-11-02T10:15:00+00:00", "2026-11-02T02:15:00-08:00"),
            (datetime.fromisoformat("2026-11-01T08:45:00.123456+00:00"),
             "2026-11-01T09:15:00.123456+00:00", "2026-11-01T09:15:00.123456+00:00"),
            (datetime.fromisoformat("2026-11-01T14:15:00.123456+05:30"),
             "2026-11-01T09:15:00.123456+00:00", "2026-11-01T14:45:00.123456+05:30"),
            (datetime.fromisoformat("2026-11-01T01:45:00.123456-07:00"),
             "2026-11-01T09:15:00.123456+00:00", "2026-11-01T02:15:00.123456-07:00"),
        ]
        for at, due, spelling in cases:
            with self.subTest(at=at.isoformat()):
                rid = self.put(at)
                self.assert_deadline(rid, datetime.fromisoformat(due))
                self.assertEqual(self.row(rid)["expires_at"], spelling)
                self.assertEqual(self.row(rid)["created_at"], at.isoformat())
                self.assertEqual(self.row(rid)["updated_at"], at.isoformat())
                self.put(at, request_id=rid)
                self.assertEqual(self.row(rid)["expires_at"], spelling)

    def test_repeated_renewal_preserves_two_hour_cap_across_fall_back(self):
        first = datetime(2026, 11, 1, 8, 20, tzinfo=UTC)
        rid = self.put(first.astimezone(PACIFIC))
        # Independent UTC deadlines include both occurrences of the repeated hour.
        for at, due in [("08:45", "09:15"), ("09:10", "09:40"),
                        ("09:35", "10:05"), ("10:00", "10:20")]:
            with self.subTest(at=at):
                now = datetime.fromisoformat("2026-11-01T" + at + ":00+00:00")
                expected = datetime.fromisoformat("2026-11-01T" + due + ":00+00:00")
                self.assertIsNotNone(self.store.get("owner", now))
                self.assertEqual(self.put(now.astimezone(PACIFIC), request_id=rid), rid)
                self.assert_deadline(rid, expected)
                self.assertEqual(self.row(rid)["created_at"], "2026-11-01T01:20:00-07:00")

    def test_legacy_renewal_uses_elapsed_idle_time_without_new_hard_cap(self):
        first = datetime(2026, 11, 1, 6, 20, tzinfo=UTC).astimezone(PACIFIC)
        rid = self.store.put("owner", "legacy1", first, texts=[CANARY], legacy=True)
        self.store.put("owner", "legacy2", START, texts=[CANARY], request_id=rid, legacy=True)
        self.assert_deadline(rid, DUE)  # beyond first + two hours, still allowed for legacy
        self.store.sweep(datetime(2026, 11, 1, 9, 16, tzinfo=UTC))
        self.assertIsNone(self.db.execute("SELECT * FROM open_requests WHERE request_id = ?", (rid,)).fetchone())
        self.db.execute("CREATE TABLE open_asks(provider_id TEXT, asked_at TEXT, texts_json TEXT)")
        self.db.execute("INSERT INTO open_asks VALUES (?, ?, ?)",
                        ("old", "2026-11-01T01:45:00-07:00", json.dumps([CANARY])))
        self.assertEqual(self.store.adopt_legacy("migrated"), 1)
        row = self.store.get("migrated", DUE)
        self.assertEqual(row["expires_at"], "2026-11-01T02:15:00-07:00")
        self.assertIsNone(self.store.get("migrated", DUE + timedelta(microseconds=1)))

    def test_lookup_and_status_do_not_continue_an_expired_request(self):
        rid = self.put(START, pending={"ops": []}, asked_slot="time")
        self.store.put("other", "other1", DUE, texts=["unrelated"], skill="hike.add")
        other = dict(self.db.execute("SELECT * FROM open_requests WHERE owner = 'other'").fetchone())
        self.db.execute("CREATE TABLE sentinel(value TEXT)")
        self.db.execute("INSERT INTO sentinel VALUES ('untouched')")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertNoLogs(level="DEBUG"):
            for now, live in [(DUE, True), (DUE + timedelta(microseconds=1), False)]:
                for req in (self.store.get("owner", now), self.store.by_provider("owner", "m1", now),
                            self.store.pending_of("owner", now)):
                    self.assertEqual(req is not None, live)
                self.assertEqual(bool(self.store.status_lines("owner", now)), live)
            self.store.sweep(DUE + timedelta(minutes=1))
        self.assertNotIn(CANARY, out.getvalue() + err.getvalue())
        self.assertEqual(self.row(rid)["state"], "expired")
        after = dict(self.db.execute("SELECT * FROM open_requests WHERE owner = 'other'").fetchone())
        self.assertEqual(after, other)
        self.assertEqual(self.db.execute("SELECT value FROM sentinel").fetchone()[0], "untouched")

    def test_cancelled_and_replaced_requests_never_reappear_at_the_boundary(self):
        cancelled = self.put(START)
        self.store.mark(cancelled, "cancelled", START)
        self.assertIsNone(self.store.get("owner", DUE))
        old = self.put(START, provider_id="old")
        new = self.put(START, provider_id="new")
        self.assertNotEqual(old, new)
        self.assertIsNone(self.store.by_provider("owner", "old", DUE))
        self.assertEqual(self.store.get("owner", DUE)["request_id"], new)
        self.assertIsNone(self.store.get("owner", DUE + timedelta(microseconds=1)))


class ElapsedConversationTests(SkillCase):
    def test_conversation_after_fall_back_ttl_does_not_reuse_earlier_request(self):
        self.now = START
        text = FIRST + " " + CANARY
        self.script(text, skill_reply("hike.add", title="Beach hike", day=MILL["day"], time="08:00"))
        self.assertEqual(self.say(text, pid="fall-first"), "question")
        old = self.live()["request_id"]
        self.assertIn(CANARY, self.live()["texts"][0])
        before = (self.table(), len(self.asked))
        self.assertEqual(self.say(text, pid="fall-first"), "duplicate")
        self.assertEqual((self.table(), len(self.asked)), before)
        self.now = datetime(2026, 11, 1, 9, 16, tzinfo=UTC).astimezone(PACIFIC)
        self.script("Fiscalini Ranch", skill_reply("hike.add", place="Fiscalini Ranch"))
        self.assertEqual(self.say("Fiscalini Ranch", pid="fall-next"), "question")
        self.assertIsNone(self.asked[-1][1])
        self.assertNotEqual(self.live()["request_id"], old)
        self.assertEqual(self.live()["slots"], {"place": "Fiscalini Ranch"})
        self.assertNotIn(CANARY, json.dumps(self.live()["texts"]))
        self.nothing_written()


if __name__ == "__main__":
    unittest.main()
