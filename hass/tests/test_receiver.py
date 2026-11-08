"""SHOP-3 tests: hass/receiver.py on fixtures that stand in for the real channel (no network, no credential, no send).
Run: python3 -B -m unittest hass.tests.test_receiver"""

import copy, json, socket, tempfile, unittest, urllib.request  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import conversation, inbox as inbox_mod, receiver
from hass.tests.test_bridge import FIXTURES, OWNER_CHAT, event
from hass.tests.test_conversation import SETTINGS, T0, ConversationTestCase

SECRET = b"throwaway-test-secret-not-real-0123456789"  # test-only constant; production code never holds a key
NOW = int(T0.timestamp())  # new-message.json dateCreated
ROOT = Path(__file__).resolve().parents[2]


class RecordingReply:
    def __init__(self):
        self.calls = []

    def __call__(self, chat, text, attachments=()):
        self.calls.append((chat, text, attachments))


class ReceiverTestCase(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "ownerChat": OWNER_CHAT})
        self.conv, self.nonce = self.open(), 0
        self.reply = RecordingReply()
        self.restart(T0.isoformat())

    def restart(self, start_at=None):
        self.inbox = inbox_mod.Inbox(str(self.repo.state), start_at, clock=lambda: self.now)
        self.addCleanup(self.inbox.close)
        self.rx = receiver.Receiver(state=self.inbox, settings=self.conv, reply=self.reply)

    def seal(self, ev, now=NOW, secret=SECRET):
        self.nonce += 1
        return receiver.forward(ev, secret, nonce=f"{self.nonce:032x}", now=now)

    def event_from(self, name, **data):
        ev = copy.deepcopy(event(name))
        ev["data"].update(data)
        return ev

    def inbound_rows(self):
        return self.inbox.db.execute("SELECT provider_id, state FROM inbound ORDER BY provider_id").fetchall()

    def unsent(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL").fetchone()[0]


class DraftTests(ReceiverTestCase):
    def test_owner_message_becomes_one_draft_nothing_applied_nothing_sent(self):
        out = self.rx.receive(self.seal(event("new-message")), secret=SECRET, now=NOW)
        drafts = self.drafts()
        self.assertEqual((out["result"], len(drafts), drafts[0]["state"]), ("drafted", 1, "proposed"))
        self.assertEqual(out["draft_id"], drafts[0]["code"])
        self.assertIn("approval", out["reason"])
        self.assertEqual((self.editor.applies, self.commits(), self.reply.calls), (0, 0, []))
        self.assertEqual(self.unsent(), 1)  # the proposal reply is stored, not sent

    def test_one_call_form_and_default_reply_refuses(self):
        out = receiver.receive(self.seal(event("new-message")).encode(), state=self.inbox, settings=self.conv,
                               secret=SECRET, now=NOW)
        self.assertEqual(out["result"], "drafted")
        with self.assertRaisesRegex(receiver.NotConnected, "docs/hass/CONNECT.md"):
            self.conv.flush(receiver.Receiver(state=self.inbox, settings=self.conv))
        self.assertEqual(self.unsent(), 1)
        with self.assertRaises(receiver.NotConnected):
            receiver.not_connected(OWNER_CHAT, "hello")

    def test_message_before_the_start_point_is_history(self):
        early = self.event_from("new-message", guid="FAKE-EARLY", dateCreated=(NOW - 60) * 1000)
        out = self.rx.receive(self.seal(early, now=NOW - 60), secret=SECRET, now=NOW - 60)
        self.assertEqual((out["result"], self.drafts()), ("history", []))


class HeldApprovalTests(ReceiverTestCase):
    """Review item 1: a change then a freshly sealed owner `yes <code>` (or bare `yes`) is held, never applied."""

    def yes(self, guid, text, t):
        ev = self.event_from("new-message", guid=guid, text=text, dateCreated=t * 1000)
        return self.rx.receive(self.seal(ev, now=t), secret=SECRET, now=t)

    def test_owner_yes_after_a_change_applies_nothing_and_the_draft_still_waits(self):
        code = self.rx.receive(self.seal(event("new-message")), secret=SECRET, now=NOW)["draft_id"]
        for guid, text, t in (("FAKE-YES-CODE", f"yes {code}", NOW + 5), ("FAKE-YES-BARE", "yes", NOW + 6)):
            out = self.yes(guid, text, t)
            self.assertEqual((out["result"], out["disposition"], out["draft_id"]), ("handled", "approval-held", None))
            self.assertIn("applies nothing", out["reason"])
            self.assertEqual(([d["state"] for d in self.drafts()], self.editor.applies, self.commits()),
                             (["proposed"], 0, 0), text)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)
        self.assertEqual(self.reply.calls, [])
        held = self.conv.db.execute("SELECT text FROM outbox WHERE sent_at IS NULL ORDER BY id").fetchall()
        self.assertEqual(sum("I can't save changes yet" in r["text"] for r in held), 2)  # stored unsent
        self.assertEqual([r["state"] for r in self.inbound_rows()], ["done"] * 3)
        self.assertEqual(self.yes("FAKE-YES-CODE", f"yes {code}", NOW + 7)["result"], "duplicate")  # recorded once
        self.assertEqual(self.editor.applies, 0)

    def test_the_conversation_still_applies_when_called_directly(self):  # the hold is the receiver's, not global
        code = self.rx.receive(self.seal(event("new-message")), secret=SECRET, now=NOW)["draft_id"]
        msg = conversation.Inbound(provider_id="FAKE-DIRECT", chat=OWNER_CHAT, sender=SETTINGS["ownerSenders"][0],
                                   text=f"yes {code}", received_at=T0.isoformat())
        self.assertEqual(self.conv.handle(msg), "approved")
        self.assertEqual(self.editor.applies, 1)


class OwnDraftTests(ReceiverTestCase):
    """Review item 2: the code returned is the draft made by the received message, not the newest draft of the drain."""

    def test_earlier_incoming_message_gets_its_own_code_when_a_later_pending_message_drains_after_it(self):
        later = self.event_from("new-message", guid="FAKE-LATER", text="hours", dateCreated=(NOW + 5) * 1000)
        with mock.patch.object(self.inbox, "drain", side_effect=RuntimeError("crash before drain")):
            with self.assertRaises(RuntimeError):
                self.rx.receive(self.seal(later, now=NOW + 5), secret=SECRET, now=NOW + 5)
        self.assertEqual((self.inbox.state("FAKE-LATER"), self.drafts()), ("pending", []))
        out = self.rx.receive(self.seal(event("new-message"), now=NOW + 6), secret=SECRET, now=NOW + 6)  # earlier time
        first, second = self.drafts()  # drained in time order: the incoming message, then the pending later one
        self.assertEqual(out["result"], "drafted")
        self.assertEqual(out["draft_id"], first["code"])
        self.assertNotEqual(out["draft_id"], second["code"])
        self.assertEqual([r["state"] for r in self.inbound_rows()], ["done", "done"])


class DuplicateTests(ReceiverTestCase):
    def test_same_envelope_twice_is_a_duplicate_without_a_second_draft(self):
        raw = self.seal(event("new-message"))
        self.assertEqual(self.rx.receive(raw, secret=SECRET, now=NOW)["result"], "drafted")
        again = self.rx.receive(raw, secret=SECRET, now=NOW + 1)
        self.assertEqual((again["result"], again["draft_id"], len(self.drafts())), ("duplicate", None, 1))
        self.restart()  # the nonce store is durable: a restart still refuses the replay
        self.assertEqual(self.rx.receive(raw, secret=SECRET, now=NOW + 2)["result"], "duplicate")
        resealed = self.rx.receive(self.seal(event("new-message")), secret=SECRET, now=NOW)  # new nonce, same id
        self.assertEqual((resealed["result"], len(self.drafts())), ("duplicate", 1))


class RejectTests(ReceiverTestCase):
    def assert_rejected(self, raw, now=NOW, words=None):
        out = self.rx.receive(raw, secret=SECRET, now=now)
        self.assertEqual((out["result"], out["draft_id"]), ("rejected", None))
        if words: self.assertIn(words, out["reason"])
        self.assertEqual((self.inbound_rows(), self.drafts(), self.reply.calls), ([], [], []))
        self.assertEqual(self.inbox.db.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 0)
        return out

    def test_bad_mac_expired_future_and_malformed_are_rejected_and_nothing_is_queued(self):
        reasons = {self.assert_rejected(self.seal(event("new-message"), secret=b"x" * 32), words="signature")["reason"],
                   self.assert_rejected(self.seal(event("new-message")), now=NOW + 301, words="expired")["reason"],
                   self.assert_rejected(self.seal(event("new-message"), now=NOW + 301), words="future")["reason"]}
        self.assertEqual(len(reasons), 2)  # expired and future share the clock-window reason
        forged = json.loads(self.seal(event("new-message")))
        forged["body"]["sender"] = "stranger@example.invalid"  # rewording the body after sealing breaks the MAC
        self.assert_rejected(json.dumps(forged), words="signature")
        for bad in ("not json", b"\xff\xfe", "[]", json.dumps({**forged, "v": 2})):
            self.assert_rejected(bad)

    def test_the_secret_is_required_with_no_fallback(self):
        raw = self.seal(event("new-message"))
        with self.assertRaises(TypeError):
            self.rx.receive(raw, now=NOW)
        for secret in (None, b"", b"short"):
            with self.assertRaisesRegex(ValueError, "envelope key"):
                self.rx.receive(raw, secret=secret, now=NOW)
        self.assertEqual(self.inbound_rows(), [])


class IgnoreTests(ReceiverTestCase):
    def test_stranger_group_reaction_receipt_and_echo_make_no_draft_with_distinct_reasons(self):
        reasons = {}
        for name in ("stranger", "group-chat", "reaction", "receipt", "from-me"):
            out = self.rx.receive_event(event(name), secret=SECRET, nonce=f"{name.encode().hex():0<32}", now=NOW)
            self.assertEqual((out["result"], out["draft_id"]), ("ignored", None), name)
            reasons[name] = out["reason"]
        self.assertEqual(len(set(reasons.values())), 5, reasons)
        self.assertIn("owner", reasons["stranger"])
        self.assertIn("group", reasons["group-chat"])
        self.assertIn("receipt", reasons["receipt"])
        self.assertIn("echo", reasons["from-me"])
        self.assertEqual((self.drafts(), self.editor.applies, self.reply.calls), ([], 0, []))
        self.assertEqual(len(self.inbound_rows()), 3)  # group and receipt are dropped before sealing

    def test_stranger_in_the_owner_chat_saying_yes_approves_nothing(self):
        self.rx.receive(self.seal(event("new-message")), secret=SECRET, now=NOW)
        sneaky = self.event_from("stranger", chats=[{"guid": OWNER_CHAT}], guid="FAKE-SNEAKY")
        out = self.rx.receive(self.seal(sneaky), secret=SECRET, now=NOW)
        self.assertEqual(out["result"], "ignored")
        self.assertEqual(([d["state"] for d in self.drafts()], self.editor.applies), (["proposed"], 0))


def no_network(*_args, **_kwargs):
    raise AssertionError("network use attempted")


class AttachmentTests(ReceiverTestCase):
    def test_attachment_is_counted_and_handled_without_any_fetch(self):
        with mock.patch.object(socket, "socket", no_network), \
                mock.patch.object(socket, "create_connection", no_network), \
                mock.patch.object(urllib.request, "urlopen", no_network):
            out = self.rx.receive(self.seal(event("attachment")), secret=SECRET, now=NOW)
        self.assertEqual((out["result"], out["disposition"], out["draft_id"]),
                         ("handled", "attachment-unsupported", None))
        self.assertEqual((self.drafts(), self.reply.calls), ([], []))

    def test_a_photo_waiting_for_its_retry_is_reported_queued(self):
        media = tempfile.TemporaryDirectory(prefix="hass-media-")
        self.addCleanup(media.cleanup)
        self.set_settings({**SETTINGS, "ownerChat": OWNER_CHAT, "mediaRoot": media.name})
        photos = mock.Mock(fetch=mock.Mock(side_effect=OSError("fetch not available in fixtures")))
        self.conv = conversation.Conversation(str(self.repo.state), self.editor, self.interp, lambda: self.now,
                                              photos=photos)
        self.restart()
        out = self.rx.receive(self.seal(event("attachment")), secret=SECRET, now=NOW)
        self.assertEqual((out["result"], self.inbox.state("FAKE-0000-0000-0000-000000000006")), ("queued", "pending"))
        self.assertEqual(self.drafts(), [])


class SourceTests(unittest.TestCase):
    def test_production_module_reads_no_secret_and_opens_no_connection(self):
        text = (ROOT / "hass" / "receiver.py").read_text("utf-8")
        for banned in ("open(", "os.environ", "getenv", "subprocess", "import socket", "from socket", "import urllib",
                       "from urllib", "import os", "logging", "print(", "BlueBubblesSender("):
            self.assertNotIn(banned, text)

    def test_connect_doc_lists_what_g_must_do(self):
        doc = (ROOT / "docs" / "hass" / "CONNECT.md").read_text("utf-8")
        self.assertIn("## 1. What works now (fixtures)", doc)
        self.assertIn("## 2. What G must do to connect the channel", doc)
        self.assertLessEqual(len(doc.splitlines()), 60)
        self.assertTrue((FIXTURES / "new-message.json").is_file())


class CrashTests(ReceiverTestCase):
    def second(self):
        return self.event_from("new-message", guid="FAKE-SECOND", text="hours", dateCreated=(NOW + 5) * 1000)

    def test_crash_between_enqueue_and_drain_then_next_message_recovers_it_once(self):
        with mock.patch.object(self.inbox, "drain", side_effect=RuntimeError("crash before drain")):
            with self.assertRaisesRegex(RuntimeError, "crash before drain"):
                self.rx.receive(self.seal(event("new-message")), secret=SECRET, now=NOW)
        self.assertEqual(self.drafts(), [])
        self.conv = self.open()  # a restart: Conversation.recover() runs on open
        self.restart()
        out = self.rx.receive(self.seal(self.second()), secret=SECRET, now=NOW + 5)
        self.assertEqual(out["result"], "drafted")
        self.assertEqual(len(self.drafts()), 2)  # the earlier message drafted once, then this one
        self.assertEqual(out["draft_id"], self.drafts()[-1]["code"])
        self.assertEqual([r["state"] for r in self.inbound_rows()], ["done", "done"])

    def test_crash_after_handle_before_mark_is_not_drafted_twice(self):
        with mock.patch.object(self.inbox, "_mark", side_effect=RuntimeError("crash before mark")):
            with self.assertRaisesRegex(RuntimeError, "crash before mark"):
                self.rx.receive(self.seal(event("new-message")), secret=SECRET, now=NOW)
        self.assertEqual(len(self.drafts()), 1)
        self.conv = self.open()
        self.restart()
        self.assertEqual(self.rx.receive(self.seal(self.second()), secret=SECRET, now=NOW + 5)["result"], "drafted")
        self.assertEqual((len(self.drafts()), self.editor.applies), (2, 0))
        self.assertEqual(self.inbox.db.execute("SELECT disposition FROM inbound WHERE provider_id = ?",
                                               ("FAKE-0000-0000-0000-000000000001",)).fetchone()[0], "duplicate")


if __name__ == "__main__":
    unittest.main()
