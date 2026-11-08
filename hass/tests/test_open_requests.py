"""SKILLS-FW-3 tests: the open request store (hass/skills/openreq.py) and the rules of spec 2.6 that belong to it.

Pure store tests run on a temporary sqlite file with an explicit clock; the conversation tests run the real Conversation on the
H02 throwaway repo (see test_skill_dispatch for the skill replies). Owner text is private: no test prints it, and one checks that
nothing in a turn writes it to stdout, stderr or a logger.
Run: python3 -m unittest hass.tests.test_open_requests -v
"""
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import conversation
from hass.skills import openreq
from hass.skills.model import Slot
from hass.tests.test_conversation import CHAT, OWNER, STRANGER
from hass.tests.test_skill_dispatch import FIRST, MILL, OPEN1, SkillCase, skill_reply

T0 = datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc)
OWNER_ID, OTHER_ID = "chat-owner", "chat-other"
SECRET = "my-private-sentence-zq81"


class StoreCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = sqlite3.connect(Path(self._tmp.name) / "c.sqlite3", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.store = openreq.OpenRequests(self.db)

    def put(self, at, owner=OWNER_ID, **kw):
        kw.setdefault("texts", [SECRET])
        return self.store.put(owner, kw.pop("provider_id", "m1"), at, **kw)


class TableTests(StoreCase):
    def test_no_table_until_the_first_write_and_reads_are_empty(self):
        self.assertFalse(self.store.exists())
        self.assertIsNone(self.store.get(OWNER_ID, T0))
        self.assertEqual(self.store.status_lines(OWNER_ID, T0), [])
        self.assertFalse(self.store.exists())  # reading made nothing

    def test_one_live_request_per_owner_and_the_old_one_is_superseded_not_kept_live(self):
        a = self.put(T0, skill="hike.add")
        b = self.put(T0 + timedelta(minutes=1), skill="item.describe", provider_id="m2")
        live = self.db.execute("SELECT request_id FROM open_requests WHERE state IN ('open','drafted')").fetchall()
        self.assertEqual([r[0] for r in live], [b])
        self.assertEqual(self.db.execute("SELECT state FROM open_requests WHERE request_id = ?", (a,)).fetchone()[0], "superseded")
        with self.assertRaises(sqlite3.IntegrityError):  # the table itself refuses a second live row for one owner
            self.db.execute("INSERT INTO open_requests(provider_id, owner, state, texts_json, created_at, updated_at, expires_at)"
                            " VALUES ('x', ?, 'open', '[]', 'a', 'a', 'a')", (OWNER_ID,))

    def test_another_owner_or_chat_never_reads_it(self):
        self.put(T0, skill="hike.add", slots={"title": "x"})
        self.assertIsNotNone(self.store.get(OWNER_ID, T0))
        for other in (OTHER_ID, "", OWNER_ID.upper()):
            self.assertIsNone(self.store.get(other, T0))
            self.assertIsNone(self.store.by_provider(other, "m1", T0))
            self.assertIsNone(self.store.pending_of(other, T0))
            self.assertEqual(self.store.status_lines(other, T0), [])
        self.assertIsNone(self.store.bind_attachment(OTHER_ID, "p", "a" * 64, T0)[1]["skill"])  # it opens its own, never joins ours
        self.assertEqual(self.store.get(OWNER_ID, T0)["attachments"], [])

    def test_a_table_that_is_not_ours_or_a_damaged_row_is_no_request(self):
        self.put(T0)
        self.db.execute("UPDATE open_requests SET slots_json = 'not json', texts_json = '{\"a\":1}', calls_json = '3'")
        req = self.store.get(OWNER_ID, T0)
        self.assertEqual((req["slots"], req["texts"], req["calls"]), ({}, [], []))
        self.db.execute("UPDATE open_requests SET expires_at = 'garbage'")
        self.assertIsNone(self.store.get(OWNER_ID, T0))


class TimeToLiveTests(StoreCase):
    def test_a_request_lives_30_minutes_after_the_last_owner_message(self):
        rid = self.put(T0, skill="s")
        self.assertIsNotNone(self.store.get(OWNER_ID, T0 + timedelta(minutes=openreq.TTL_MINUTES)))
        self.assertIsNone(self.store.get(OWNER_ID, T0 + timedelta(minutes=openreq.TTL_MINUTES, seconds=1)))
        self.put(T0 + timedelta(minutes=20), request_id=rid, skill="s")  # another owner message renews it
        self.assertIsNotNone(self.store.get(OWNER_ID, T0 + timedelta(minutes=49)))

    def test_but_never_more_than_two_hours_after_the_first(self):
        rid = self.put(T0, skill="s")
        for minutes in (25, 50, 75, 100):
            self.put(T0 + timedelta(minutes=minutes), request_id=rid, skill="s")
        self.assertIsNotNone(self.store.get(OWNER_ID, T0 + timedelta(minutes=120)))
        self.assertIsNone(self.store.get(OWNER_ID, T0 + timedelta(minutes=121)))

    def test_sweep_expires_a_skill_request_and_erases_a_legacy_one_at_once(self):
        self.put(T0, skill="s")
        self.store.sweep(T0 + timedelta(minutes=31))
        self.assertEqual(self.db.execute("SELECT state FROM open_requests").fetchone()[0], "expired")
        self.put(T0 + timedelta(minutes=40))  # legacy kind: no skill, nothing attached
        self.store.sweep(T0 + timedelta(minutes=80))
        self.assertEqual([r[0] for r in self.db.execute("SELECT state FROM open_requests")], ["expired"])


class RetentionTests(StoreCase):
    """D7: a closed request's text is erased 24 hours after it closed."""

    def test_the_text_of_a_closed_request_goes_24_hours_after_it_closed(self):
        rid = self.put(T0, skill="s")
        self.store.mark(rid, "closed", T0 + timedelta(minutes=5))
        self.store.sweep(T0 + timedelta(hours=23))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM open_requests").fetchone()[0], 1)
        self.store.sweep(T0 + timedelta(hours=24, minutes=6))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM open_requests").fetchone()[0], 0)

    def test_cancelled_superseded_and_expired_requests_follow_the_same_rule(self):
        for state in ("cancelled", "superseded", "expired"):
            rid = self.put(T0, skill="s")
            self.store.mark(rid, state, T0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM open_requests").fetchone()[0], 3)
        self.store.sweep(T0 + timedelta(hours=25))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM open_requests").fetchone()[0], 0)

    def test_a_legacy_question_request_is_erased_when_it_closes(self):
        rid = self.put(T0)
        self.store.mark(rid, "closed", T0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM open_requests").fetchone()[0], 0)

    def test_owner_text_is_capped_per_text_and_in_total(self):
        long = "x" * (openreq.MAX_OWNER_TEXT + 500)
        self.put(T0, skill="s", texts=[long, long, long])
        kept = self.store.get(OWNER_ID, T0)["texts"]
        self.assertTrue(all(len(t) <= openreq.MAX_OWNER_TEXT for t in kept))
        self.assertLessEqual(sum(map(len, kept)), openreq.MAX_TOTAL_TEXT)
        self.assertEqual(openreq.bound_texts(["a", "b", "c"], turns=2), ["b", "c"])
        self.assertEqual(openreq.bound_texts(["", None, "a"]), ["a"])


class MigrationTests(StoreCase):
    def test_open_asks_rows_move_into_the_one_store_and_the_old_table_is_dropped(self):
        self.db.execute("CREATE TABLE open_asks(provider_id TEXT PRIMARY KEY, asked_at TEXT NOT NULL, texts_json TEXT NOT NULL, pending_json TEXT)")
        pending = json.dumps({"ops": [{"op": "store.confirm_selection", "args": {}}], "revises": None})
        self.db.execute("INSERT INTO open_asks VALUES ('m9', ?, ?, ?)", (T0.isoformat(), json.dumps(["add a hike", "Saturday"]), pending))
        self.assertEqual(self.store.adopt_legacy(OWNER_ID), 1)
        self.assertIsNone(self.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'open_asks'").fetchone())
        row = self.store.get(OWNER_ID, T0 + timedelta(minutes=29))
        self.assertEqual((row["texts"], row["provider_id"], row["skill"]), (["add a hike", "Saturday"], "m9", None))
        self.assertEqual(row["pending"]["ops"][0]["op"], "store.confirm_selection")
        self.assertIsNone(self.store.get(OWNER_ID, T0 + timedelta(minutes=31)))  # the old 30 minutes still apply
        self.assertEqual(self.store.adopt_legacy(OWNER_ID), 0)  # nothing left to move

    def test_an_unreadable_old_row_is_dropped_not_carried(self):
        self.db.execute("CREATE TABLE open_asks(provider_id TEXT PRIMARY KEY, asked_at TEXT NOT NULL, texts_json TEXT NOT NULL)")
        self.db.execute("INSERT INTO open_asks VALUES ('a', 'x', '[\"t\"]')")
        self.db.execute("INSERT INTO open_asks VALUES ('b', ?, 'not json')", (T0.isoformat(),))
        self.assertEqual(self.store.adopt_legacy(OWNER_ID), 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM open_requests").fetchone()[0], 0)


class CheapAnswerTests(unittest.TestCase):
    IDS = {"ids": ["photo-product-015", "photo-product-122"], "names": ["Brian's sourdough bread", "Rye bread"]}

    def test_a_choice_by_number_ordinal_or_name(self):
        pick = openreq.pick_candidate
        self.assertEqual(pick("2", self.IDS), "photo-product-122")
        self.assertEqual(pick("the first one", self.IDS), "photo-product-015")
        self.assertEqual(pick("the rye one", self.IDS), "photo-product-122")
        self.assertEqual(pick("sourdough", self.IDS), "photo-product-015")
        self.assertIsNone(pick("bread", self.IDS))  # both: not a choice
        self.assertIsNone(pick("3", self.IDS))
        self.assertIsNone(pick("the blue one", self.IDS))
        self.assertIsNone(pick("2", {}))

    def test_only_the_cheap_kinds_and_short_plain_answers_are_read_by_code(self):
        day = Slot("day", "day", True, ask="Which day?")
        today = datetime(2026, 11, 2).date()
        self.assertEqual(openreq.cheap_answer(day, "2026-11-07", today=today), (True, "2026-11-07"))
        self.assertEqual(openreq.cheap_answer(day, "Saturday", today=today), (True, "2026-11-07"))
        self.assertEqual(openreq.cheap_answer(day, "saturday and also call it the beach hike", today=today), (False, None))
        self.assertEqual(openreq.cheap_answer(day, " ".join(["word"] * 13), today=today), (False, None))
        self.assertEqual(openreq.cheap_answer(Slot("t", "text", True, ask="What?"), "anything"), (False, None))
        self.assertEqual(openreq.cheap_answer(None, "x"), (False, None))
        self.assertEqual(openreq.cheap_answer(Slot("c", "clock", True, ask="When?"), "9"), (False, None))  # am or pm is not guessed
        self.assertEqual(openreq.cheap_answer(Slot("c", "clock", True, ask="When?"), "9am"), (True, "09:00"))

    def test_merge_keeps_valid_values_and_ignores_unknown_names_and_none(self):
        merged = openreq.merge({"a": 1, "b": 2}, {"b": 3, "c": 4, "a": None}, {"a", "b"})
        self.assertEqual(merged, {"a": 1, "b": 3})


class PhotoBindingTests(StoreCase):
    SHA = "c" * 64

    def test_a_photo_with_no_request_opens_one_with_only_its_sha(self):
        how, req = self.store.bind_attachment(OWNER_ID, "p1", self.SHA, T0)
        self.assertEqual((how, req["attachments"], req["skill"], req["texts"]), ("opened", [self.SHA], None, []))

    def test_a_bad_sha_is_refused_and_bytes_never_stored(self):
        for bad in ("short", "g" * 64, b"\x89PNG", None, 5):
            with self.assertRaises(ValueError):
                self.store.bind_attachment(OWNER_ID, "p1", bad, T0)
        self.assertFalse(self.store.exists())

    def test_the_same_photo_twice_does_not_double_attach(self):
        self.store.bind_attachment(OWNER_ID, "p1", self.SHA, T0)
        how, req = self.store.bind_attachment(OWNER_ID, "p2", self.SHA, T0 + timedelta(seconds=5))
        self.assertEqual((how, req["attachments"]), ("attached", [self.SHA]))


class ConversationRuleTests(SkillCase):
    def test_a_message_judged_twice_is_judged_once_duplicate_ids_change_nothing(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.assertEqual(self.say(OPEN1, pid="same-id"), "question")
        before = (self.table(), len(self.asked))
        self.assertEqual(self.say(OPEN1, pid="same-id"), "duplicate")
        self.assertEqual((self.table(), len(self.asked)), before)

    def test_a_crash_while_a_message_is_handled_rolls_the_request_back_and_the_replay_is_whole(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        real = self.conv.outbox.add
        self.conv.outbox.add = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash after the request row was written"))
        with self.assertRaises(RuntimeError):
            self.say(OPEN1, pid="p1")
        self.assertEqual(self.table(), [])  # the request row went with the message disposition and the reply: all or nothing
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        self.conv.outbox.add = real
        self.conv = self.open()  # the service restarts and the same message arrives again
        self.assertEqual(self.say(OPEN1, pid="p1"), "question")
        self.assertEqual(len(self.table()), 1)
        self.assertEqual(self.say(OPEN1, pid="p1"), "duplicate")

    def test_after_30_minutes_the_answer_is_a_new_request_not_joined(self):
        self.script(FIRST, skill_reply("hike.add", title="Beach hike", day=MILL["day"], time="08:00"))
        self.say(FIRST)
        self.now += timedelta(minutes=31)
        self.script("Fiscalini Ranch", skill_reply("hike.add", place="Fiscalini Ranch"))
        self.say("Fiscalini Ranch")
        text, recent = self.asked[-1]
        self.assertIsNone(recent)  # the model was shown no earlier request: it had lapsed
        self.assertEqual(self.live()["slots"], {"place": "Fiscalini Ranch"})

    def test_owner_text_is_never_written_to_stdout_stderr_or_a_log(self):
        self.script(f"add a hike {SECRET}", skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertNoLogs(level="DEBUG"):
            self.say(f"add a hike {SECRET}")
            self.replies()
            self.say("status")
            self.say("backlog")
        self.assertNotIn(SECRET, out.getvalue() + err.getvalue())

    def test_a_strangers_message_changes_no_request_and_is_not_read(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        rows = self.table()
        for kw in ({"sender": STRANGER}, {"chat": "other-chat"}, {"from_me": True}):
            self.say("8am", **kw)
        self.assertEqual(self.table(), rows)

    def test_the_request_row_is_written_in_the_same_transaction_as_the_message(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1, pid="tx1")
        [msg] = self.conv.db.execute("SELECT provider_id, disposition FROM messages").fetchall()
        [req] = self.table()
        self.assertEqual((msg["provider_id"], msg["disposition"], req["provider_id"]), ("tx1", "question", "tx1"))

    def test_a_third_unanswered_ask_of_the_same_slot_is_counted_on_the_row(self):
        self.script(FIRST, skill_reply("hike.add", title="Beach hike", day=MILL["day"], time="08:00"))
        self.say(FIRST)
        self.assertEqual(self.table()[0]["asks"], 1)
        self.script("hm", skill_reply("hike.add", place=None))
        self.say("hm")
        self.assertEqual(self.table()[0]["asks"], 2)


class DocPinsTests(unittest.TestCase):
    def test_owner_text_caps_match_the_conversation_cap(self):
        self.assertEqual(openreq.MAX_OWNER_TEXT, conversation.MAX_OWNER_TEXT)
        self.assertEqual(openreq.TTL_MINUTES, conversation.RECENT_MINUTES)
        self.assertEqual(openreq.RETENTION_HOURS, 24)  # D7


if __name__ == "__main__":
    unittest.main()
