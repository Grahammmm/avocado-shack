"""NB-AV-11 (H16) tests: a photo that cannot be fetched keeps its message pending (3 tries: now, +30 s, +2 min), holding
every later message in order; the 3rd failure replies FETCH_FAILED once and nothing is stored or drafted.
PhotoRepo harness, Inbox and Conversation on one fake clock, a photo source that fails N times; nothing is downloaded.
Run: python3 -m unittest hass.tests.test_attachment_retry -v"""

import contextlib
import json
import sqlite3
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, inbox as inbox_mod
from hass.conversation import FETCH_FAILED, PHOTO_QUESTION, AttachmentPending, Inbound
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_photo_draft import ANSWER, JPG, PhotoInterpreter
from hass.tests.test_set_photo import PhotoRepo, _settings

OLD_INBOUND = """CREATE TABLE meta(name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE inbound(provider_id TEXT PRIMARY KEY, received_at TEXT NOT NULL, payload TEXT,
  state TEXT NOT NULL CHECK (state IN ('pending', 'done', 'history')), disposition TEXT, enqueued_at TEXT NOT NULL,
  done_at TEXT);"""


class FlakyPhotos:
    """Fails the first `failures` fetches (raising, or returning `short` when given), then returns the photo."""

    def __init__(self, failures, short=False):
        self.failures, self.short, self.calls = failures, short, []

    def fetch(self, provider_id, count):
        self.calls.append(provider_id)
        if len(self.calls) <= self.failures:
            if self.short is not False: return self.short
            raise OSError("bridge unreachable")
        return [JPG] * count


class AttachmentRetryTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.now, self.out, self.interp = T0, FixtureAdapter(), PhotoInterpreter()
        self.photos = FlakyPhotos(1)

    @property
    def box(self):  # opened lazily, so a test can write an older inbox file first
        if "_box" not in vars(self):
            self._box = inbox_mod.Inbox(str(self.repo.state), T0.isoformat(), clock=lambda: self.now)
            self.addCleanup(self._box.close)
        return self._box

    @property
    def conv(self):
        if "_conv" not in vars(self):
            self._conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state),
                                                   self.interp, lambda: self.now, photos=self.photos)
            self.addCleanup(self._conv.db.close)
        return self._conv

    def queue(self, pid, text="", attachments=0, at=0):
        msg = Inbound(pid, CHAT, OWNER, text, received_at=(T0 + timedelta(seconds=at)).isoformat(),
                      attachments=attachments)
        self.assertEqual(self.box.enqueue(msg), "queued")

    def drain_at(self, seconds):
        self.now = T0 + timedelta(seconds=seconds)
        return self.box.drain(self.conv)

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def row(self, pid):
        return dict(self.box.db.execute("SELECT * FROM inbound WHERE provider_id = ?", (pid,)).fetchone())

    def drafts(self):
        return self.conv.db.execute("SELECT state FROM drafts").fetchall()

    def recorded(self, pid):
        return self.conv.db.execute("SELECT 1 FROM messages WHERE provider_id = ?", (pid,)).fetchone() is not None

    def test_one_failure_then_the_photo_is_drafted_after_30_seconds(self):
        self.queue("p1", attachments=1)
        self.assertEqual(self.drain_at(0), [])
        self.assertEqual((self.row("p1")["state"], self.row("p1")["tries"], self.box.waiting()), ("pending", 1, 1))
        self.assertEqual(self.row("p1")["next_try_at"], inbox_mod._iso(T0 + timedelta(seconds=30)))
        self.assertFalse(self.recorded("p1"))  # rolled back: nothing about the message was kept by Conversation
        self.assertEqual((self.replies(), self.drafts()), ([], []))
        self.assertEqual(self.drain_at(29), [])
        self.assertEqual(self.photos.calls, ["p1"])  # before next_try_at: no fetch
        self.assertEqual(self.drain_at(30), [("p1", "photo-draft")])
        self.assertEqual((len(self.drafts()), self.box.waiting(), self.photos.calls), (1, 0, ["p1", "p1"]))
        [reply] = self.replies()
        self.assertTrue(reply.startswith(PHOTO_QUESTION), reply)
        self.assertEqual(self.drain_at(600), [])

    def test_three_failures_reply_once_and_store_or_draft_nothing(self):
        self.photos = FlakyPhotos(99)
        self.queue("p1", ANSWER, attachments=1)
        self.assertEqual(self.drain_at(0), [])
        self.assertEqual(self.drain_at(30), [])
        self.assertEqual(self.row("p1")["next_try_at"], inbox_mod._iso(T0 + timedelta(seconds=150)))  # +2 min
        self.assertEqual(self.drain_at(149), [])
        self.assertEqual((self.photos.calls, self.replies()), (["p1", "p1"], []))
        self.assertEqual(self.drain_at(150), [("p1", "attachment-failed")])
        self.assertEqual(self.replies(), [FETCH_FAILED])
        self.assertEqual((self.drafts(), self.interp.texts, self.box.waiting()), ([], [], 0))  # caption never read
        self.assertFalse((self.repo.media / "originals").exists())
        self.assertEqual((self.row("p1")["state"], self.row("p1")["disposition"]), ("done", "attachment-failed"))
        self.assertEqual(self.drain_at(900), [])  # a 4th drain does nothing
        self.assertEqual((len(self.photos.calls), self.replies()), (3, []))

    def test_an_empty_or_missing_fetch_result_is_a_failure(self):
        for i, short in enumerate(([], None)):
            self.conv.photos = FlakyPhotos(9, short=short)
            msg = Inbound(f"s{i}", CHAT, OWNER, "", received_at=T0.isoformat(), attachments=1)
            self.assertRaises(AttachmentPending, self.conv.handle, msg)
            self.assertEqual(self.conv.handle(msg, last_try=True), "attachment-failed")

    def test_drain_before_next_try_keeps_later_messages_waiting_in_order(self):
        self.queue("p1", attachments=1)
        self.queue("t2", ANSWER, at=1)
        self.assertEqual(self.drain_at(0), [])
        self.queue("t3", "hours", at=5)
        self.assertEqual(self.drain_at(10), [])
        self.assertEqual((self.photos.calls, self.interp.texts), (["p1"], []))
        self.assertEqual([self.row(p)["state"] for p in ("p1", "t2", "t3")], ["pending"] * 3)
        self.assertEqual(self.drain_at(30), [("p1", "photo-draft"), ("t2", "proposed"), ("t3", "unsupported")])
        self.assertEqual(self.interp.texts, [ANSWER, "hours"])

    def test_crash_before_the_try_is_counted_costs_at_most_one_extra_attempt(self):
        self.photos = FlakyPhotos(2)
        self.queue("p1", attachments=1)
        self.queue("t2", "hours", at=1)

        @contextlib.contextmanager
        def broken_tx():
            raise RuntimeError("disk full")
            yield
        with mock.patch.object(self.box, "_tx", broken_tx):
            with self.assertRaisesRegex(RuntimeError, "disk full"):
                self.drain_at(0)
        self.assertEqual((self.row("p1")["tries"], self.row("p1")["next_try_at"], self.box.waiting()), (0, None, 0))
        self.assertEqual(self.drain_at(0), [])  # the one extra attempt; this time the try is counted
        self.assertEqual((self.row("p1")["tries"], self.row("t2")["state"]), (1, "pending"))
        self.assertEqual(self.drain_at(30), [("p1", "photo-draft"), ("t2", "unsupported")])
        self.assertEqual(self.photos.calls, ["p1"] * 3)

    def test_an_older_inbox_without_the_new_columns_opens_and_drains(self):
        db = sqlite3.connect(self.repo.state / "inbox.sqlite3")  # written before any Inbox opens the state dir
        db.executescript(OLD_INBOUND)
        db.execute("INSERT INTO meta VALUES ('start_at', ?)", (inbox_mod._iso(T0),))
        db.execute("INSERT INTO inbound(provider_id, received_at, payload, state, enqueued_at) VALUES"
                   " ('o1', ?, ?, 'pending', ?)", (inbox_mod._iso(T0), json.dumps(
                       vars(Inbound("o1", CHAT, OWNER, "hours", received_at=T0.isoformat()))), inbox_mod._iso(T0)))
        db.commit()
        db.close()
        self.assertTrue({"tries", "next_try_at"} <= {r[1] for r in self.box.db.execute("PRAGMA table_info(inbound)")})
        self.assertEqual((self.box.waiting(), self.row("o1")["tries"]), (0, 0))
        self.queue("p2", attachments=1, at=1)
        self.assertEqual(self.drain_at(0), [("o1", "unsupported")])
        self.assertEqual((self.box.waiting(), self.drain_at(30)), (1, [("p2", "photo-draft")]))

    def test_other_exceptions_propagate_with_no_try_count(self):
        self.queue("t1", "hours")
        self.queue("t2", "hours", at=1)
        with mock.patch.object(self.interp, "interpret", side_effect=RuntimeError("interpreter down")):
            for _ in range(2):  # retried at once on every drain, as before
                with self.assertRaisesRegex(RuntimeError, "interpreter down"):
                    self.drain_at(0)
        self.assertEqual((self.row("t1")["tries"], self.row("t1")["next_try_at"], self.box.waiting()), (0, None, 0))
        self.assertEqual((self.row("t2")["state"], self.photos.calls), ("pending", []))
        self.assertEqual(self.drain_at(0), [("t1", "unsupported"), ("t2", "unsupported")])

    def test_handle_without_last_try_raises_and_records_nothing(self):
        msg = Inbound("d1", CHAT, OWNER, "yes", received_at=T0.isoformat(), attachments=1)
        with self.assertRaises(AttachmentPending):
            self.conv.handle(msg)
        self.assertEqual((self.recorded("d1"), self.interp.texts, self.replies()), (False, [], []))
        self.assertEqual(self.conv.handle(msg), "unsupported")  # the redelivery is processed fresh: photo, then caption
        self.assertEqual(self.conv.handle(msg, last_try=True), "duplicate")
        self.assertEqual((self.interp.texts, len(self.drafts()), self.photos.calls), (["yes"], 1, ["d1", "d1"]))


if __name__ == "__main__":
    unittest.main()
