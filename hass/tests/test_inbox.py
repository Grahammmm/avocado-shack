"""H16 tests: durable inbound queue with a recorded start point.

Each test uses the H05 harness (throwaway repo, linked writer worktree, 0700 state dir, fixture interpreter, injected
clock) and an Inbox in the same state dir. Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import os
import re
import stat
import unittest
from datetime import timedelta
from unittest import mock

from hass import inbox as inbox_mod
from hass.bridge import EnvelopeError, seal, unseal
from hass.conversation import Inbound
from hass.tests.test_conversation import CHAT, OWNER, T0, ConversationTestCase, _ops
from hass.tests.test_editor import DESC


class InboxTestCase(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.inbox = self.open_inbox(T0.isoformat())

    def open_inbox(self, start_at=None):
        box = inbox_mod.Inbox(str(self.repo.state), start_at, clock=lambda: self.now)
        self.addCleanup(box.close)
        return box

    def msg(self, pid, text, at):
        return Inbound(pid, CHAT, OWNER, text, False, "new", at.isoformat())

    def rows(self):
        return {r["provider_id"]: dict(r) for r in self.inbox.db.execute("SELECT * FROM inbound")}

    def outbox_texts(self):
        return [r["text"] for r in self.conv.db.execute("SELECT text FROM outbox ORDER BY id")]


class StartPointTests(InboxTestCase):
    def test_first_open_needs_a_start_point_and_it_never_moves(self):
        other = self.repo.state.parent / "state2"
        other.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "^start point required$"):
            inbox_mod.Inbox(str(other))
        recorded = inbox_mod._iso(T0)
        with self.assertRaisesRegex(ValueError, f"^start point already recorded as {re.escape(recorded)}$"):
            self.open_inbox((T0 + timedelta(seconds=1)).isoformat())
        with self.assertRaisesRegex(ValueError, "start point already recorded"):
            self.open_inbox((T0 - timedelta(days=1)).isoformat())
        self.assertEqual(self.open_inbox().start_at, T0)  # None reuses the recorded value
        self.assertEqual(self.open_inbox(T0.astimezone(inbox_mod.timezone(timedelta(hours=-8))).isoformat())
                         .start_at, T0)  # the same instant in another offset is not a move
        with self.assertRaisesRegex(ValueError, "start_at must be a timezone-aware"):
            inbox_mod.Inbox(str(other), "2026-11-02T17:00")
        self.assertEqual(self.inbox.db.execute("SELECT value FROM meta").fetchall()[0][0], recorded)

    def test_message_before_the_start_is_history_and_never_a_command(self):
        before, after = T0 - timedelta(seconds=1), T0 + timedelta(seconds=1)
        self.assertEqual(self.inbox.enqueue(self.msg("old", "hours", before)), "history")
        self.assertEqual(self.inbox.drain(self.conv), [])
        self.assertEqual((self.outbox_texts(), self.drafts()), ([], []))
        self.assertEqual(self.inbox.state("old"), "history")
        self.assertEqual(self.inbox.enqueue(self.msg("old", "hours", after)), "duplicate")  # no later promotion
        self.assertEqual(self.inbox.enqueue(self.msg("new", "hours", after)), "queued")
        self.assertEqual(self.inbox.drain(self.conv), [("new", "proposed")])
        self.assertEqual(len(self.drafts()), 1)
        self.assertEqual(self.inbox.enqueue(self.msg("edge", "desc", T0)), "queued")  # exactly the start counts


class OrderTests(InboxTestCase):
    def test_drain_in_received_order_with_provider_id_tie_break(self):
        t1, t2, t3 = (T0 + timedelta(seconds=s) for s in (10, 20, 30))
        offset = inbox_mod.timezone(timedelta(hours=-8))
        for word in ("one", "two", "three"):  # three independent drafts whose order is visible in the store
            self.interp.mapping[word] = _ops((DESC, {"id": "photo-product-001", "description": f"Batch {word}."}))
        for pid, text, at in (("c3", "three", t3), ("a1", "one", t1.astimezone(offset)), ("b2", "two", t2)):
            self.assertEqual(self.inbox.enqueue(self.msg(pid, text, at)), "queued")
        self.assertEqual([pid for pid, _ in self.inbox.drain(self.conv)], ["a1", "b2", "c3"])
        self.assertEqual([json.loads(d["ops_json"])[0]["args"]["description"] for d in self.drafts()],
                         ["Batch one.", "Batch two.", "Batch three."])
        for pid in ("z9", "y8"):  # same received_at: provider_id decides
            self.inbox.enqueue(self.msg(pid, "status", t3))
        self.assertEqual([pid for pid, _ in self.inbox.drain(self.conv)], ["y8", "z9"])


class CrashTests(InboxTestCase):
    def test_crash_between_handle_and_mark_redelivers_as_duplicate(self):
        self.inbox.enqueue(self.msg("p1", "hours", T0))
        self.assertEqual(self.inbox.drain(self.conv), [("p1", "proposed")])
        self.inbox.enqueue(self.msg("p2", "yes", T0 + timedelta(seconds=5)))
        with mock.patch.object(self.inbox, "_mark", side_effect=RuntimeError("crash before mark")):
            with self.assertRaisesRegex(RuntimeError, "crash before mark"):
                self.inbox.drain(self.conv)
        self.assertEqual(self.inbox.state("p2"), "pending")
        self.assertEqual(self.commits(), 1)
        self.inbox = self.open_inbox()  # a restart: fresh Inbox and Conversation over the same state
        self.conv = self.open()
        self.assertEqual(self.inbox.drain(self.conv), [("p2", "duplicate")])
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.editor.applies, 1)
        texts = self.outbox_texts()
        self.assertEqual(len([t for t in texts if t.startswith("Saved:")]), 1, texts)
        self.assertEqual(len(texts), 2)  # one proposal, one result reply
        self.assertEqual((self.rows()["p2"]["state"], self.rows()["p2"]["disposition"]), ("done", "duplicate"))

    def test_exception_in_handle_stops_the_drain_and_a_later_drain_continues(self):
        for i, text in enumerate(("hours", "desc", "status")):
            self.inbox.enqueue(self.msg(f"q{i}", text, T0 + timedelta(seconds=i)))
        real, calls = self.conv.handle, []

        def flaky(msg):
            calls.append(msg.provider_id)
            if msg.provider_id == "q1" and calls.count("q1") == 1: raise RuntimeError("interpreter down")
            return real(msg)
        with mock.patch.object(self.conv, "handle", side_effect=flaky):
            with self.assertRaisesRegex(RuntimeError, "interpreter down"):
                self.inbox.drain(self.conv)
            self.assertEqual([self.inbox.state(p) for p in ("q0", "q1", "q2")], ["done", "pending", "pending"])
            self.assertEqual(calls, ["q0", "q1"])
            self.assertEqual([p for p, _ in self.inbox.drain(self.conv)], ["q1", "q2"])
        self.assertEqual({r["state"] for r in self.rows().values()}, {"done"})
        self.assertEqual(self.inbox.drain(self.conv), [])  # each message is handled once


class InputTests(InboxTestCase):
    def test_duplicate_and_malformed_received_at(self):
        self.assertEqual(self.inbox.enqueue(self.msg("d1", "hours", T0)), "queued")
        self.assertEqual(self.inbox.enqueue(self.msg("d1", "desc", T0 + timedelta(seconds=9))), "duplicate")
        self.assertEqual(self.rows()["d1"]["received_at"], inbox_mod._iso(T0))
        for bad in ("", "2026-10-30T09:00", "not a date", None):
            with self.subTest(received_at=bad):
                with self.assertRaisesRegex(ValueError, "received_at must be a timezone-aware"):
                    self.inbox.enqueue(Inbound("bad", CHAT, OWNER, "hours", received_at=bad))
        self.assertEqual(set(self.rows()), {"d1"})


class PrivacyTests(InboxTestCase):
    def test_payloads_are_erased_and_the_store_is_private(self):
        self.inbox.enqueue(self.msg("h1", "hours", T0 - timedelta(hours=1)))
        self.inbox.enqueue(self.msg("n1", "hours", T0))
        self.assertIsNotNone(self.rows()["n1"]["payload"])  # stored before processing
        self.inbox.drain(self.conv)
        rows = self.rows()
        self.assertEqual({p: (r["state"], r["payload"]) for p, r in rows.items()},
                         {"h1": ("history", None), "n1": ("done", None)})
        mode = stat.S_IMODE(os.stat(self.repo.state / "inbox.sqlite3").st_mode)
        self.assertEqual(mode, 0o600)


class NonceTests(InboxTestCase):
    def test_nonces_persist_across_reopen(self):
        seen = self.inbox.seen()
        self.assertNotIn("ab" * 16, seen)
        seen.add("ab" * 16)
        seen.add("ab" * 16)  # idempotent
        self.assertIn("ab" * 16, self.open_inbox().seen())

    def test_replayed_envelope_is_refused_after_reopen(self):
        key, nonce, now = b"k" * 32, "cd" * 16, T0.timestamp()
        msg = self.msg("e1", "hours", T0)
        envelope = seal(msg, key, nonce=nonce, now=now)
        self.assertEqual(unseal(envelope, key, now=now, seen=self.inbox.seen()), msg)
        self.inbox.close()
        reopened = self.open_inbox()  # a restart: only the recorded nonce remembers the envelope
        with self.assertRaises(EnvelopeError) as caught:
            unseal(envelope, key, now=now + 1, seen=reopened.seen())
        self.assertEqual(caught.exception.code, "replay")
        other = seal(msg, b"x" * 32, nonce="ef" * 16, now=now)  # a refused envelope records no nonce
        self.assertRaises(EnvelopeError, unseal, other, key, now=now, seen=reopened.seen())
        self.assertNotIn("ef" * 16, reopened.seen())


if __name__ == "__main__":
    unittest.main()
