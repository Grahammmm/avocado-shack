"""H16 tests: a queued message whose payload cannot be decoded is marked `unreadable` and the drain goes on.

Synthetic messages on the H05 harness; each poison row is made with a direct UPDATE on the inbox store.
Run: python3 -m unittest hass.tests.test_inbox_unreadable -v
"""

import json
import unittest
from dataclasses import asdict
from datetime import timedelta
from unittest import mock

from hass.tests.test_conversation import T0
from hass.tests.test_inbox import InboxTestCase


class UnreadableTests(InboxTestCase):
    def queue(self, *specs):
        for i, (pid, text) in enumerate(specs):
            self.assertEqual(self.inbox.enqueue(self.msg(pid, text, T0 + timedelta(seconds=i))), "queued")

    def corrupt(self, pid, payload):
        self.inbox.db.execute("UPDATE inbound SET payload = ? WHERE provider_id = ?", (payload, pid))

    def row(self, pid):
        r = self.rows()[pid]
        return r["state"], r["disposition"], r["payload"]

    def test_poison_first_good_second_and_a_redrain_does_not_retry(self):
        self.queue(("m1", "hours"), ("m2", "hours"))
        self.corrupt("m1", "not json")
        self.assertEqual(self.inbox.drain(self.conv), [("m1", "unreadable"), ("m2", "proposed")])
        self.assertEqual(self.row("m1"), ("done", "unreadable", None))
        self.assertEqual(self.row("m2"), ("done", "proposed", None))
        self.assertEqual(len(self.outbox_texts()), 1)  # only m2 was answered
        self.assertEqual(len(self.drafts()), 1)
        self.assertEqual({r["state"] for r in self.rows().values()}, {"done"})
        self.assertEqual(self.inbox.drain(self.conv), [])  # the unreadable row is never retried
        self.assertEqual(self.row("m1"), ("done", "unreadable", None))

    def test_each_decode_failure_is_unreadable(self):
        good = asdict(self.msg("p0", "hours", T0))
        bad = {"null": None, "list": "[]", "missing": json.dumps({"provider_id": "p1"}),
               "extra": json.dumps(dict(good, provider_id="p3", extra=1)), "scalar": "7", "empty": ""}
        self.queue(*((f"p{i}", "hours") for i in range(len(bad))))
        for i, payload in enumerate(bad.values()):
            self.corrupt(f"p{i}", payload)
        handle = mock.Mock(side_effect=AssertionError("handle must not see an unreadable payload"))
        with mock.patch.object(self.conv, "handle", handle):
            got = self.inbox.drain(self.conv)
        self.assertEqual(got, [(f"p{i}", "unreadable") for i in range(len(bad))])
        handle.assert_not_called()
        for i, name in enumerate(bad):
            with self.subTest(payload=name):
                self.assertEqual(self.row(f"p{i}"), ("done", "unreadable", None))
        self.assertEqual((self.outbox_texts(), self.drafts()), ([], []))

    def test_payload_naming_another_message_is_unreadable_and_leaves_that_row_alone(self):
        self.queue(("a1", "hours"), ("b2", "hours"))
        b2_payload = self.rows()["b2"]["payload"]
        self.corrupt("a1", b2_payload)  # a1's row now carries b2's message
        with mock.patch.object(self.conv, "handle", side_effect=RuntimeError("stop")):
            with self.assertRaisesRegex(RuntimeError, "^stop$"):
                self.inbox.drain(self.conv)
        self.assertEqual(self.row("a1"), ("done", "unreadable", None))
        self.assertEqual(self.row("b2"), ("pending", None, b2_payload))  # untouched by a1's verdict
        self.corrupt("b2", json.dumps(dict(json.loads(b2_payload), provider_id="ghost")))  # names no stored row
        self.assertEqual(self.inbox.drain(self.conv), [("b2", "unreadable")])
        self.assertNotIn("ghost", self.rows())
        self.assertEqual(self.outbox_texts(), [])

    def test_handler_exception_still_propagates_and_later_rows_stay_pending(self):
        self.queue(("m1", "hours"), ("m2", "hours"), ("m3", "status"))
        self.corrupt("m1", "{broken")
        kept = {p: self.rows()[p]["payload"] for p in ("m2", "m3")}
        real = self.conv.handle

        def flaky(msg):
            if msg.provider_id == "m2": raise RuntimeError("interpreter down")
            return real(msg)
        with mock.patch.object(self.conv, "handle", side_effect=flaky):
            with self.assertRaisesRegex(RuntimeError, "interpreter down"):
                self.inbox.drain(self.conv)
        self.assertEqual(self.row("m1"), ("done", "unreadable", None))
        for pid, payload in kept.items():
            self.assertEqual(self.row(pid), ("pending", None, payload))
        self.assertEqual([p for p, _ in self.inbox.drain(self.conv)], ["m2", "m3"])  # next drain resumes at m2

    def test_order_is_kept_around_an_unreadable_message(self):
        self.queue(("m0", "hours"), ("m1", "hours"), ("m2", "status"))
        self.corrupt("m1", "[1, 2]")
        seen = []
        real = self.conv.handle
        with mock.patch.object(self.conv, "handle", side_effect=lambda m: seen.append(m.provider_id) or real(m)):
            got = self.inbox.drain(self.conv)
        self.assertEqual([p for p, _ in got], ["m0", "m1", "m2"])
        self.assertEqual(got[1], ("m1", "unreadable"))
        self.assertNotIn("unreadable", (got[0][1], got[2][1]))
        self.assertEqual(seen, ["m0", "m2"])

    def test_history_row_with_null_payload_is_never_selected(self):
        self.assertEqual(self.inbox.enqueue(self.msg("h1", "hours", T0 - timedelta(hours=1))), "history")
        self.queue(("m1", "hours"))
        self.corrupt("m1", None)
        self.assertEqual(self.inbox.drain(self.conv), [("m1", "unreadable")])
        h1 = self.rows()["h1"]
        self.assertEqual((h1["state"], h1["disposition"], h1["payload"], h1["done_at"]), ("history", None, None, None))
        self.assertEqual(self.inbox.drain(self.conv), [])


if __name__ == "__main__":
    unittest.main()
