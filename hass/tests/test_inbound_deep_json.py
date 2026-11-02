"""RF1520-8 / H16 tests: deeply nested inbound JSON is refused, never a RecursionError.

The receiver answers `rejected` with the shape reason for a deeply nested envelope; the inbox drain marks a deeply
nested queued payload `unreadable` and goes on to the next message in the same drain.
Run: python3 -m unittest hass.tests.test_inbound_deep_json -v
"""

import unittest
from datetime import timedelta
from unittest import mock

from hass import receiver
from hass.tests.test_bridge import event
from hass.tests.test_conversation import T0
from hass.tests.test_inbox import InboxTestCase
from hass.tests.test_receiver import NOW, SECRET, ReceiverTestCase

DEEP = "[" * 100000
DEEP_OBJECT = '{"a":' * 100000
DEEP_ENV = "[" * receiver.MAX_ENVELOPE_BYTES  # envelope inputs stay within the 64 KiB cap so json.loads still runs
DEEP_OBJ_ENV = '{"a":' * (receiver.MAX_ENVELOPE_BYTES // 5)


class DeepEnvelopeTests(ReceiverTestCase):
    def assert_shape_rejected(self, raw):
        out = self.rx.receive(raw, secret=SECRET, now=NOW)
        self.assertEqual(out, {"result": "rejected", "draft_id": None, "reason": receiver.REJECTED["shape"],
                               "disposition": None})
        self.assertEqual((self.inbound_rows(), self.drafts(), self.reply.calls), ([], [], []))
        self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 0)

    def test_deep_array_or_object_as_str_bytes_or_bytearray_is_a_shape_rejection(self):
        for raw in (DEEP_ENV, DEEP_ENV.encode(), bytearray(DEEP_ENV.encode()), DEEP_OBJ_ENV, DEEP_OBJ_ENV.encode()):
            with self.subTest(kind=type(raw).__name__, start=raw[:2]):
                self.assert_shape_rejected(raw)

    def test_bridge_is_never_reached_for_a_deep_envelope(self):
        with mock.patch.object(receiver.bridge, "unseal", side_effect=AssertionError("unseal must not run")) as unseal:
            self.assert_shape_rejected(DEEP_ENV)
        unseal.assert_not_called()

    def test_a_good_envelope_after_a_deep_one_is_still_drafted(self):
        self.assert_shape_rejected(DEEP_ENV)
        out = self.rx.receive(self.seal(event("new-message")), secret=SECRET, now=NOW)
        self.assertEqual((out["result"], len(self.drafts())), ("drafted", 1))
        self.assertEqual(out["draft_id"], self.drafts()[0]["code"])


class DeepPayloadTests(InboxTestCase):
    def queue(self, *specs):
        for i, (pid, text) in enumerate(specs):
            self.assertEqual(self.inbox.enqueue(self.msg(pid, text, T0 + timedelta(seconds=i))), "queued")

    def corrupt(self, pid, payload):
        self.inbox.db.execute("UPDATE inbound SET payload = ? WHERE provider_id = ?", (payload, pid))

    def row(self, pid):
        r = self.rows()[pid]
        return r["state"], r["disposition"], r["payload"]

    def test_deep_payload_is_unreadable_and_the_next_message_is_handled_in_the_same_drain(self):
        self.queue(("m1", "hours"), ("m2", "hours"))
        self.corrupt("m1", DEEP)
        self.assertEqual(self.inbox.drain(self.conv), [("m1", "unreadable"), ("m2", "proposed")])
        self.assertEqual(self.row("m1"), ("done", "unreadable", None))
        self.assertEqual(self.row("m2"), ("done", "proposed", None))
        self.assertEqual((len(self.outbox_texts()), len(self.drafts())), (1, 1))  # only m2 was answered
        self.assertEqual(self.inbox.drain(self.conv), [])  # the unreadable row is never retried

    def test_deep_object_payload_in_the_middle_keeps_order_and_handle_never_sees_it(self):
        self.queue(("m0", "hours"), ("m1", "hours"), ("m2", "status"))
        self.corrupt("m1", DEEP_OBJECT)
        seen, real = [], self.conv.handle
        with mock.patch.object(self.conv, "handle", side_effect=lambda m: seen.append(m.provider_id) or real(m)):
            got = self.inbox.drain(self.conv)
        self.assertEqual([p for p, _ in got], ["m0", "m1", "m2"])
        self.assertEqual(got[1], ("m1", "unreadable"))
        self.assertEqual(seen, ["m0", "m2"])

    def test_normal_queued_messages_are_unchanged(self):
        self.queue(("m1", "hours"), ("m2", "status"))
        got = self.inbox.drain(self.conv)
        self.assertEqual([p for p, _ in got], ["m1", "m2"])
        self.assertNotIn("unreadable", [d for _, d in got])
        self.assertEqual({r["state"] for r in self.rows().values()}, {"done"})


if __name__ == "__main__":
    unittest.main()
