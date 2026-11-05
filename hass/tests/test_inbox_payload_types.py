"""RF0220-10 (H16) tests: a stored payload with wrongly typed fields is marked `unreadable` and the drain goes on.

Synthetic messages on the H05 harness; each poison row is made with a direct UPDATE on the inbox store.
Run: python3 -m unittest hass.tests.test_inbox_payload_types -v
"""

import contextlib
import io
import json
import unittest
from dataclasses import asdict
from datetime import timedelta
from unittest import mock

from hass.tests.test_conversation import T0
from hass.tests.test_inbox import InboxTestCase

STR_FIELDS = ("chat", "sender", "text", "kind", "received_at")
WRONG = (None, [], {}, 7, True)


class PayloadTypeTests(InboxTestCase):
    def queue(self, *specs):
        for i, (pid, text) in enumerate(specs):
            self.assertEqual(self.inbox.enqueue(self.msg(pid, text, T0 + timedelta(seconds=i))), "queued")

    def mutate(self, pid, **changes):
        payload = dict(json.loads(self.rows()[pid]["payload"]), **changes)
        self.inbox.db.execute("UPDATE inbound SET payload = ? WHERE provider_id = ?", (json.dumps(payload), pid))

    def row(self, pid):
        r = self.rows()[pid]
        return r["state"], r["disposition"], r["payload"]

    def test_wrong_typed_fields_are_unreadable_before_handle(self):
        cases = [(f, v) for f in STR_FIELDS + ("provider_id",) for v in WRONG]
        cases += [("from_me", v) for v in (None, 0, 1, "false")]
        cases += [("attachments", v) for v in (None, "1", [], {}, 1.0, True, False, -1)]
        for i, (field, value) in enumerate(cases):
            with self.subTest(field=field, value=value):
                bad, good = f"b{i}", f"g{i}"
                self.queue((bad, "hours"), (good, "hours"))
                self.mutate(bad, **{field: value})
                seen = []
                real = self.conv.handle
                with mock.patch.object(self.conv, "handle", side_effect=lambda m: seen.append(m.provider_id) or real(m)):
                    got = self.inbox.drain(self.conv)
                self.assertEqual(got, [(bad, "unreadable"), (good, "proposed")])
                self.assertEqual(seen, [good])
                self.assertEqual(self.row(bad), ("done", "unreadable", None))
                self.assertIsNotNone(self.rows()[bad]["done_at"])
                self.assertEqual(self.row(good), ("done", "proposed", None))

    def test_bad_attachments_cannot_stall_real_conversation(self):
        self.queue(("poison", "hours"), ("later", "status"))
        self.mutate("poison", attachments=None)
        self.assertEqual(self.inbox.drain(self.conv), [("poison", "unreadable"), ("later", "status")])
        self.assertEqual(self.row("poison"), ("done", "unreadable", None))
        self.assertEqual(self.row("later"), ("done", "status", None))
        self.assertEqual(len(self.outbox_texts()), 1)
        self.assertEqual(self.drafts(), [])
        self.assertEqual([r[0] for r in self.conv.db.execute("SELECT provider_id FROM messages")], ["later"])
        self.assertEqual(self.inbox.drain(self.conv), [])

    def test_optional_defaults_and_valid_values_survive(self):
        self.queue(("d1", "hours"), ("d2", ""), ("d3", "hours"), ("d4", "status"), ("d5", "status"))
        base = asdict(self.msg("d1", "hours", T0))
        for pid in ("d1", "d2"):  # older payloads omit the optional keys, received_at included
            self.inbox.db.execute("UPDATE inbound SET payload = ? WHERE provider_id = ?", (json.dumps(
                {k: base[k] for k in ("provider_id", "chat", "sender", "text")} | {"provider_id": pid, "text": base["text"] if pid == "d1" else ""}), pid))
        self.mutate("d3", kind="edited", attachments=0)
        self.mutate("d4", kind="reaction", attachments=3)
        self.mutate("d5", from_me=True, attachments=0)
        got = self.inbox.drain(self.conv)
        self.assertEqual([p for p, _ in got], ["d1", "d2", "d3", "d4", "d5"])
        self.assertNotIn("unreadable", [d for _, d in got])
        self.assertEqual({r["state"] for r in self.rows().values()}, {"done"})

    def test_handler_typeerror_is_not_payload_corruption(self):
        for exc in (TypeError("handler bug"), ValueError("handler bug")):
            with self.subTest(exc=type(exc).__name__):
                tag = type(exc).__name__[0]
                bad, cur, later = f"{tag}bad", f"{tag}cur", f"{tag}later"
                self.queue((bad, "hours"), (cur, "hours"), (later, "status"))
                self.mutate(bad, attachments="x")
                kept = {p: self.rows()[p]["payload"] for p in (cur, later)}
                real = self.conv.handle

                def flaky(msg, exc=exc, cur=cur):
                    if msg.provider_id == cur: raise exc
                    return real(msg)
                with mock.patch.object(self.conv, "handle", side_effect=flaky):
                    with self.assertRaisesRegex(type(exc), "^handler bug$"):
                        self.inbox.drain(self.conv)
                self.assertEqual(self.row(bad), ("done", "unreadable", None))
                for pid, payload in kept.items():
                    self.assertEqual(self.row(pid), ("pending", None, payload))
                self.assertEqual([p for p, _ in self.inbox.drain(self.conv)], [cur, later])

    def test_typed_poison_order_privacy_and_history(self):
        self.assertEqual(self.inbox.enqueue(self.msg("hist", "hours", T0 - timedelta(hours=1))), "history")
        for pid, text in (("a", "hours"), ("b", "hours"), ("c", "status")):  # same received time: provider-id order
            self.assertEqual(self.inbox.enqueue(self.msg(pid, text, T0)), "queued")
        self.mutate("b", text=["SECRET-TEXT"], attachments=None)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            got = self.inbox.drain(self.conv)
        self.assertEqual(got, [("a", "proposed"), ("b", "unreadable"), ("c", "status")])
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))
        self.assertNotIn("SECRET-TEXT", " ".join(self.outbox_texts()))
        self.assertEqual(self.row("hist"), ("history", None, None))
        self.assertEqual(self.inbox.drain(self.conv), [])
        reopened = self.open_inbox()
        self.assertEqual(reopened.drain(self.conv), [])
        self.assertEqual(self.row("b"), ("done", "unreadable", None))


if __name__ == "__main__":
    unittest.main()
