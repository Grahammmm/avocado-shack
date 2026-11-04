"""AV0022-10 (H16): a reply sent over 15 minutes after the owner message it answers starts
"Late reply to your message from <Weekday HH:MM>:" and a line break (Pacific; older than 6 days: the date).

The prefix is added only to the text given to the adapter; the stored row never changes. Fixture clock and a recording
adapter (stdlib, offline). Run: python3 -m unittest hass.tests.test_late_reply -v
"""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from hass import conversation
from hass.conversation import PHOTO_QUESTION, Inbound
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, ConversationTestCase
from hass.tests.test_label_reader import LION, SHA, FakePhotos, PhotoInterpreter, PhotoRepo, _settings, recorded, reader

T0 = datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc)  # Saturday 09:00 PST
HEAD = "Late reply to your message from Saturday 09:00:\n"


class LateReplyOutboxTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(conversation.SCHEMA)
        self.now, self.out = T0, FixtureAdapter()
        self.box = conversation.Outbox(self.db, lambda: self.now)

    def flush(self):
        before = len(self.out.sent)
        self.box.flush(self.out)
        return [m["text"] for m in self.out.sent[before:]]

    def answer(self, text, wait, reply_to=T0.isoformat()):
        """Write a reply `wait` after T0, then send it at once, so the older-reply (AVB-07) heading never applies."""
        self.now = T0 + wait
        self.box.add(CHAT, text, reply_to=reply_to)
        return self.flush()

    def test_constant(self):
        self.assertEqual(conversation.LATE_AFTER, timedelta(minutes=15))

    def test_ten_minutes_unprefixed_sixteen_prefixed(self):
        self.assertEqual(self.answer("Cancelled a1b2.", timedelta(minutes=10)), ["Cancelled a1b2."])
        self.assertEqual(self.answer("Applied c3d4.", timedelta(minutes=16)), [HEAD + "Applied c3d4."])

    def test_exactly_fifteen_minutes_unprefixed_a_second_more_prefixed(self):
        self.assertEqual(self.answer("hello", timedelta(minutes=15)), ["hello"])
        self.assertEqual(self.answer("hello", timedelta(minutes=15, seconds=1)), [HEAD + "hello"])

    def test_failed_send_retried_later_prefixes_that_row_and_later_rows_stored_text_unchanged(self):
        self.box.add(CHAT, "one", reply_to=T0.isoformat())
        self.box.add(CHAT, "two", reply_to=(T0 + timedelta(minutes=1)).isoformat())
        self.out.fail_sends = 1
        with self.assertRaises(ConnectionError): self.box.flush(self.out)
        self.now = T0 + timedelta(hours=1)  # 10:00
        self.assertEqual(self.flush(), [HEAD + "one", "Late reply to your message from Saturday 09:01:\ntwo"])
        self.assertEqual([r["text"] for r in self.db.execute("SELECT text FROM outbox ORDER BY id")], ["one", "two"])
        self.now += timedelta(hours=1)
        self.assertEqual(self.flush(), [])  # sent once

    def test_message_older_than_six_days_names_its_date(self):
        old = datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc)  # Friday 09:00 PDT
        self.now = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)
        self.box.add(CHAT, "Applied a1b2.", reply_to=old.isoformat())
        self.assertEqual(self.flush(), ["Late reply to your message from 2026-10-23 09:00:\nApplied a1b2."])
        for days, form in ((6, "Friday 09:00:\n"), (6.1, "2026-10-23 09:00:\n")):  # the sixth day is still a weekday
            with self.subTest(days=days):
                self.now = old + timedelta(days=days)
                self.box.add(CHAT, "x", reply_to=old.isoformat())
                self.assertEqual(self.flush(), [f"Late reply to your message from {form}x"])

    def test_unusable_reply_to_is_unprefixed_without_error(self):
        self.now = T0 + timedelta(hours=3)
        for i, bad in enumerate(("", None, "garbage", "2026-11-07T09:00:00", (T0 + timedelta(hours=4)).isoformat())):
            with self.subTest(reply_to=bad):
                self.db.execute("INSERT INTO outbox(chat, text, attachments, created_at, reply_to) VALUES (?, ?, '[]', ?, ?)",
                                (CHAT, f"row {i}", conversation._iso(self.now), bad))
                self.assertEqual(self.flush(), [f"row {i}"])

    def test_late_heading_replaces_the_older_reply_heading_and_keeps_attachments(self):
        self.now = T0
        self.box.add(CHAT, "preview", ["/tmp/a.png"], reply_to=T0.isoformat())
        self.now = T0 + timedelta(hours=2)
        self.assertEqual(self.flush(), [HEAD + "preview"])
        self.assertEqual(self.out.sent[-1]["attachments"], ["/tmp/a.png"])
        self.now = T0
        self.box.add(CHAT, "no message")  # no reply_to: AVB-07 heading alone, as before
        self.now = T0 + timedelta(hours=2)
        self.assertEqual(self.flush(), ["(Delayed reply, written 2026-11-07 09:00 PST) no message"])

    def test_an_old_database_without_reply_to_gains_the_column_and_flushes_unprefixed(self):
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        _settings(repo, **SETTINGS, mediaRoot=str(repo.media))
        make = lambda: conversation.Conversation(str(repo.state), conversation.Editor(repo.state), PhotoInterpreter(), lambda: self.now)
        conv = make()
        conv.db.executescript("ALTER TABLE outbox DROP COLUMN reply_to;")
        conv.db.execute("INSERT INTO outbox(chat, text, attachments, created_at) VALUES (?, 'old row', '[]', ?)",
                        (CHAT, conversation._iso(self.now)))
        conv.db.close()
        conv = make()
        self.addCleanup(conv.db.close)
        self.assertIn("reply_to", {r["name"] for r in conv.db.execute("PRAGMA table_info(outbox)")})
        self.now = T0 + timedelta(minutes=9)  # old row (written at T0): under both thresholds
        conv.flush(self.out)
        self.assertEqual([m["text"] for m in self.out.sent], ["old row"])


class LateReplyConversationTest(ConversationTestCase):
    def test_a_reply_is_tagged_with_the_message_it_answers_and_only_while_handling_it(self):
        self.now = T0
        self.assertEqual(self.say("hours"), "proposed")
        self.assertEqual(self.conv.outbox.unsent()[-1]["reply_to"], T0.isoformat())
        self.assertIsNone(self.conv._answering)
        self.now = T0 + timedelta(minutes=16)
        [reply] = self.replies()
        self.assertTrue(reply.startswith(HEAD + "Draft "), reply)

    def test_a_reply_sent_in_time_is_unprefixed(self):
        self.now = T0
        self.say("hours")
        self.now = T0 + timedelta(minutes=5)
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Draft "), reply)

    def test_a_failed_handling_still_clears_the_answering_time(self):
        self.interp.interpret = lambda text, pending: 1 / 0
        with self.assertRaises(ZeroDivisionError): self.say("hours")
        self.assertIsNone(self.conv._answering)

    def test_a_startup_recovery_reply_answers_no_message_and_is_never_prefixed(self):
        self.say("hours")
        self.say("yes")
        self.replies()
        self.conv.db.execute("UPDATE drafts SET state = 'approved' WHERE state = 'applied'")  # an interrupted apply
        self.conv.db.close()
        self.now = T0 + timedelta(hours=3)
        self.conv = self.open()
        rows = self.conv.outbox.unsent()
        self.assertTrue(rows and all(r["reply_to"] is None for r in rows), [dict(r) for r in rows])
        self.assertFalse(any(t.startswith("Late reply") for t in self.replies()))


class LateReplyLabelTest(unittest.TestCase):
    def test_a_label_line_appended_to_an_unsent_reply_follows_the_late_heading(self):
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        _settings(repo, **SETTINGS, mediaRoot=str(repo.media))
        self.now, out = T0, FixtureAdapter()
        category = sorted({p["category"] for p in repo.products()})[0]
        labels, _ = reader(recorded({**LION, "category": category}))
        conv = conversation.Conversation(str(repo.state), conversation.Editor(repo.state), PhotoInterpreter(),
                                         lambda: self.now, photos=FakePhotos(), labels=labels)
        self.addCleanup(conv.db.close)
        conv.handle(Inbound("m1", CHAT, OWNER, "", received_at=T0.isoformat(), attachments=1))
        self.now = T0 + timedelta(hours=1)
        conv.flush(out)
        [sent] = [m["text"] for m in out.sent]
        asked = f"{PHOTO_QUESTION} Reply with the product and description (draft {SHA[:4]})."
        self.assertEqual(sent, HEAD + asked + f" The label looks like: Far West Fungi Lion's Mane ({category}). "
                         "Is that right? Say which product it is either way.")


if __name__ == "__main__":
    unittest.main()
