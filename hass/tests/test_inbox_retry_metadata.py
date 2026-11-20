"""Exercise retry metadata at the durable inbox boundary with a fixture handler."""

import unittest
from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from hass.conversation import AttachmentPending, Inbound
from hass.inbox import Inbox


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FixtureHandler:
    photos = SimpleNamespace(retry_seconds=270)

    def __init__(self, available):
        self.available = available
        self.calls = []

    def handle(self, msg, *, last_try=False):
        self.calls.append((msg.provider_id, last_try))
        if msg.attachments and not self.available:
            if not last_try:
                raise AttachmentPending()
            return "attachment-failed"
        return "handled"


class InboxRetryMetadataTests(unittest.TestCase):
    def setUp(self):
        self.now = T0
        state = self.enterContext(TemporaryDirectory())
        self.box = Inbox(state, T0.isoformat(), clock=lambda: self.now)
        self.addCleanup(self.box.close)
        for offset, (pid, attachments) in enumerate((("photo", 1), ("later", 0))):
            received = (T0 + timedelta(seconds=offset)).isoformat()
            self.assertEqual(self.box.enqueue(Inbound(pid, "fixture-chat", "fixture-sender", "",
                                                       received_at=received, attachments=attachments)), "queued")

    def damage_timestamp(self):
        self.box.db.execute("UPDATE inbound SET enqueued_at = ? WHERE provider_id = ?",
                            ("not-a-time", "photo"))

    def drain_at(self, handler, seconds):
        self.now = T0 + timedelta(seconds=seconds)
        return self.box.drain(handler)

    def test_damaged_timestamp_does_not_stall_fetchable_photo_or_later_text(self):
        # Parsing retry metadata must not prevent dispatch of a readable payload.
        self.damage_timestamp()
        handler = FixtureHandler(available=True)
        self.assertEqual(self.box.drain(handler), [("photo", "handled"), ("later", "handled")])
        self.assertEqual(handler.calls, [("photo", False), ("later", False)])
        self.assertEqual([self.box.state(pid) for pid in ("photo", "later")], ["done", "done"])

    def test_damaged_timestamp_uses_the_attempt_limit(self):
        # An unavailable photo must neither give up early nor retry indefinitely.
        self.damage_timestamp()
        handler = FixtureHandler(available=False)
        for seconds in (0, 30, 149):
            self.assertEqual(self.drain_at(handler, seconds), [])
            self.assertEqual(self.box.state("later"), "pending")
        self.assertEqual(handler.calls, [("photo", False)] * 2)
        self.assertEqual(self.drain_at(handler, 150), [("photo", "attachment-failed"), ("later", "handled")])
        self.assertEqual(handler.calls, [("photo", False)] * 2 + [("photo", True), ("later", False)])

    def test_valid_timestamp_uses_lifetime_instead_of_attempt_limit(self):
        # A valid lifetime can keep a photo pending past the fallback count.
        handler = FixtureHandler(available=False)
        for seconds in (0, 30, 150):
            self.assertEqual(self.drain_at(handler, seconds), [])
        self.assertEqual(handler.calls, [("photo", False)] * 3)
        self.assertEqual(self.drain_at(handler, 270), [("photo", "attachment-failed"), ("later", "handled")])
        self.assertEqual(handler.calls, [("photo", False)] * 3 + [("photo", True), ("later", False)])

    def test_handler_value_error_is_not_swallowed_as_a_timestamp_error(self):
        self.damage_timestamp()
        handler = FixtureHandler(available=True)
        with patch.object(handler, "handle", side_effect=ValueError("fixture handler error")) as handle:
            with self.assertRaisesRegex(ValueError, "^fixture handler error$"):
                self.box.drain(handler)
            self.assertEqual(handle.call_count, 1)
        self.assertEqual(self.box.waiting(), 0)
        self.assertEqual([self.box.state(pid) for pid in ("photo", "later")], ["pending", "pending"])
