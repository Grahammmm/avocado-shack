"""AVB-07 (H16): an outbox reply held over DELAYED_AFTER_S is sent with "Sorry for the wait. ".

The prefix is added only to the text given to the adapter; the stored row never changes, so a retried send is
prefixed once. Fixture clock + recording adapter over an in-memory outbox (stdlib, offline).
Run: python3 -m unittest hass.tests.test_outbox_delayed -v
"""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from hass import conversation
from hass.fixture_chat import FixtureAdapter

CHAT = "chat-fixture-owner"
T0 = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)  # 09:00 PST
PREFIX0 = "Sorry for the wait. "


class OutboxDelayedTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(conversation.SCHEMA)
        self.now, self.out = T0, FixtureAdapter()
        self.box = conversation.Outbox(self.db, lambda: self.now)

    def flush(self):
        before = len(self.out.sent)
        self.box.flush(self.out)
        return self.out.sent[before:]

    def stored(self):
        return [(r["text"], r["sent_at"]) for r in self.db.execute("SELECT * FROM outbox ORDER BY id")]

    def test_599_seconds_unprefixed_601_prefixed(self):
        self.box.add(CHAT, "Reply yes to save it.")
        self.now = T0 + timedelta(seconds=599)
        self.assertEqual([m["text"] for m in self.flush()], ["Reply yes to save it."])
        self.box.add(CHAT, "Cancelled; nothing changed.")
        self.now += timedelta(seconds=601)
        self.assertEqual([m["text"] for m in self.flush()],
                         ["Sorry for the wait. Cancelled; nothing changed."])
        self.assertEqual([t for t, _ in self.stored()], ["Reply yes to save it.", "Cancelled; nothing changed."])

    def test_exactly_600_seconds_unprefixed(self):
        self.box.add(CHAT, "hello")
        self.now = T0 + timedelta(seconds=600)
        self.assertEqual([m["text"] for m in self.flush()], ["hello"])

    def test_failed_send_then_retry_prefixed_once(self):
        self.box.add(CHAT, "Reply yes to save it.")
        self.now, self.out.fail_sends = T0 + timedelta(minutes=20), 1
        with self.assertRaises(ConnectionError): self.box.flush(self.out)
        self.assertEqual(self.stored(), [("Reply yes to save it.", None)])
        self.now += timedelta(minutes=5)
        self.assertEqual([m["text"] for m in self.flush()], [PREFIX0 + "Reply yes to save it."])
        self.assertEqual(self.stored(), [("Reply yes to save it.", conversation._iso(self.now))])
        self.now += timedelta(minutes=5)
        self.assertEqual((self.box.flush(self.out), len(self.out.sent)), (0, 1))  # sent once, sent_at unchanged
        self.assertEqual(self.stored()[0][1], conversation._iso(self.now - timedelta(minutes=5)))

    def test_old_then_new_rows_keep_order(self):
        self.box.add(CHAT, "old")
        self.now = T0 + timedelta(minutes=30)
        self.box.add(CHAT, "new")
        self.now += timedelta(seconds=1)
        self.assertEqual([m["text"] for m in self.flush()], [PREFIX0 + "old", "new"])
        self.assertEqual([t for t, _ in self.stored()], ["old", "new"])

    def test_bad_naive_or_future_created_at_unprefixed(self):
        for i, created in enumerate(("garbage", "", "2026-11-02T08:00:00", conversation._iso(T0 + timedelta(hours=1)))):
            with self.subTest(created=created):
                self.db.execute("INSERT INTO outbox(chat, text, attachments, created_at) VALUES (?, ?, '[]', ?)",
                                (CHAT, f"row {i}", created))
                self.now = T0 + timedelta(hours=2) if i < 3 else T0
                self.assertEqual([m["text"] for m in self.flush()], [f"row {i}"])
        self.assertEqual(self.box.unsent(), [])

    def test_attachments_unchanged_prefix_on_text_only(self):
        self.box.add(CHAT, "Here is the preview.", ["/tmp/a.png", "/tmp/b.png"])
        self.now = T0 + timedelta(hours=1)
        self.assertEqual(self.flush(), [{"chat": CHAT, "text": PREFIX0 + "Here is the preview.",
                                         "attachments": ["/tmp/a.png", "/tmp/b.png"]}])
        self.assertEqual(self.stored()[0][0], "Here is the preview.")

    def test_dst_fall_back_still_marks_delayed_reply(self):
        self.now = datetime(2026, 11, 1, 8, 30, tzinfo=timezone.utc)  # 01:30 PDT on the fall-back day
        self.box.add(CHAT, "Saved the change.")
        self.now = datetime(2026, 11, 1, 9, 31, tzinfo=timezone.utc)  # 01:31 PST
        self.assertEqual([m["text"] for m in self.flush()],
                         ["Sorry for the wait. Saved the change."])
        self.assertEqual(self.stored()[0][0], "Saved the change.")


if __name__ == "__main__":
    unittest.main()
