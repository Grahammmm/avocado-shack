"""HASS-FAST-1 / HASS-TAPBACK-1 tests: the ack is ONE real tapback (BlueBubbles react call) on the owner's message and never a text
(one per owner message, never a stranger / group / echo / edit / old message, never while paused or unknown, never blocks), the host
`state` op, and the read-only stage log. Synthetic only: fake BlueBubbles, fake reactor, loopback sockets on port 0, temp dirs.
No Mac, no real message. Run: python3 -B -m unittest hass.tests.test_fast_ack"""
import contextlib, io, json, os, sqlite3, tempfile, threading, time, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import bridge, host, receiver, relay, stagelog
from hass.tests import test_forwarder as ft
from hass.tests import test_host as host_tests
from hass.tests.test_bridge import OWNER_CHAT
from hass.tests.test_conversation import OWNER, STRANGER
from mac import hass_forwarder as fwd

NOW = ft.NOW
INFO_ON = {"private_api": True, "helper_connected": True, "server_version": "1.9.9"}


class Reactor:
    """Synthetic BlueBubbles react endpoint: records (chat, guid, reaction); `fail` makes the next calls raise."""
    def __init__(self): self.calls, self.fail = [], None

    def react(self, chat, guid, reaction):
        if self.fail: raise self.fail
        self.calls.append((chat, guid, reaction))


class AckCase(ft.ForwarderCase):
    def setUp(self):
        super().setUp()
        self.order, self.state_asked, self.info, self.info_asked = [], 0, dict(INFO_ON), 0
        self.reactor = self.f.reactor = Reactor()
        self.sender.send = self._send
        self.host_ok()

    def restart(self, spool=None):
        """A new Forwarder on the same spool file (a process restart), with its own synthetic reactor sharing the call log."""
        if spool is None:
            spool = fwd.Spool(self.root, self.now)
            self.addCleanup(spool.db.close)
        again = fwd.Forwarder(self.cfg, spool, lambda: self.now, self.transport, self.sender, reactor=self.reactor)
        return again

    def _send(self, chat, text, attachments=()):
        if self.sender.fail: raise bridge.BridgeError("transport-error")
        self.sender.calls.append((chat, text, attachments))
        self.order.append("reply")

    def host_ok(self, paused=False): self.answer = paused  # what the fake host says to the next `state` question; None: unreachable

    def transport(self, url, body=None):
        if url.endswith("/v1/relay") and relay.unseal_control(body, ft.KEY, now=self.now, seen=set())["op"] == "state":
            self.state_asked += 1
            if self.answer is None: raise bridge.BridgeError("transport-error")
            return relay.seal_control({"op": "state", "paused": self.answer}, ft.KEY, nonce=os.urandom(16).hex(), now=self.now)
        if "/api/v1/server/info" in url:  # the GET-only probe: no body
            self.assertIsNone(body)
            self.info_asked += 1
            if self.info is None: raise bridge.BridgeError("transport-error")
            return {"data": self.info}
        return super().transport(url, body)

    def taps(self): return list(self.reactor.calls)

    def out(self):
        """Everything the forwarder sent to the owner chat: taps AND texts. An ack must never add a text."""
        return self.reactor.calls + self.sender.calls

    def clear(self): self.reactor.calls.clear(), self.sender.calls.clear()

    def states(self): return dict(self.spool.db.execute("SELECT provider_id,state FROM ack").fetchall())

    def probe_again(self): self.f.probe_cache = None


class WhoGetsAnAck(AckCase):
    def test_owner_message_gets_one_tapback_before_the_receiver_is_involved_and_no_text(self):
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual(self.taps(), [(OWNER_CHAT, "m1", "like")])  # the default reaction: thumbs up, on that message
        self.assertEqual((self.sender.calls, self.posts, self.states()), ([], [], {"m1": "sent"}))  # no text; nothing posted to the receiver yet
        self.f.ack()
        self.f.deliver()
        self.f.ack()
        self.assertEqual((len(self.taps()), len(self.posts), self.sender.calls), (1, 1, []))

    def test_stranger_sender_in_the_owner_chat_gets_no_ack_but_is_still_forwarded_as_before(self):
        self.enqueue("s", handle={"address": STRANGER})
        self.f.ack()
        self.assertEqual((self.out(), self.states()), ([], {}))
        self.f.deliver()
        self.assertEqual([e["body"]["sender"] for e in self.posts], [STRANGER])  # the host, not the Mac, rules on strangers

    def test_other_chat_group_unknown_sender_echo_edit_and_reaction_get_no_ack(self):
        self.enqueue("other", chats=[{"guid": "iMessage;-;stranger@example.invalid"}])
        self.enqueue("group", chats=[{"guid": "iMessage;+;group"}])
        self.enqueue("echo", isFromMe=True)  # Hass's own message
        self.enqueue("nohandle", handle=None)
        self.enqueue("react", associatedMessageType="love")
        self.enqueue("lookalike", handle={"address": "owner@example.invalid.evil"})
        edit = self.message("edit", dateEdited=int(self.now * 1000))
        self.spool.accept({"type": "updated-message", "data": edit}, OWNER_CHAT, self.now)
        self.f.ack()
        self.assertEqual((self.out(), self.states()), ([], {}))

    def test_sender_spelling_is_compared_like_the_host_does(self):
        self.enqueue("case", handle={"address": "Owner@Example.INVALID"})
        self.f.ack()
        self.assertEqual(len(self.taps()), 1)

    def test_attachment_only_owner_message_is_acked_too(self):
        self.enqueue("pic", text="\ufffc", attachments=[{"guid": "a1"}])
        self.f.ack()
        self.assertEqual(self.taps(), [(OWNER_CHAT, "pic", "like")])

    def test_a_message_found_late_by_catch_up_is_stored_but_never_acked(self):
        self.now += 600
        self.message("late")
        self.messages["late"]["dateCreated"] = int((NOW + 10) * 1000)  # sent 590 s ago, found now
        self.spool.doorbell({"type": "new-message", "data": {"guid": "late"}}, self.now)
        self.f.fetch()
        self.f.ack()
        self.assertEqual((self.out(), self.pending()), ([], 1))

    def test_an_ack_that_waited_too_long_is_dropped_not_sent_late(self):
        self.enqueue("m1")
        self.now += fwd.ACK_STALE + 1
        self.f.ack()
        self.assertEqual((self.out(), self.states()), ([], {"m1": "stale"}))


class OneAckPerMessage(AckCase):
    def test_webhook_then_catch_up_then_replay_then_restart_is_still_one_ack(self):
        self.enqueue("m1")
        self.f.ack()
        self.query = [self.messages["m1"]]
        self.f.catch_up()                          # the poll finds the same message
        self.enqueue("m1")                         # a second doorbell for it
        self.spool.accept({"type": "new-message", "data": self.messages["m1"]}, OWNER_CHAT, self.now)  # direct replay
        self.f.deliver()                           # now 'done' (payload erased)
        self.enqueue("m1")
        self.f.ack()
        reopened = fwd.Spool(self.root, self.now)
        self.addCleanup(reopened.db.close)
        restarted = self.restart(reopened)
        self.spool.accept({"type": "new-message", "data": self.messages["m1"]}, OWNER_CHAT, self.now)
        reopened.accept({"type": "new-message", "data": self.messages["m1"]}, OWNER_CHAT, self.now)
        restarted.ack()
        self.assertEqual((len(self.taps()), self.spool.db.execute("SELECT COUNT(*) FROM ack").fetchone()[0], self.sender.calls), (1, 1, []))

    def test_the_sent_mark_survives_a_restart_the_same_message_is_never_tapped_again(self):
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual(self.states(), {"m1": "sent"})
        self.spool.db.close()                      # the process ends ...
        reopened = fwd.Spool(self.root, self.now)  # ... and a new one opens the same file
        self.addCleanup(reopened.db.close)
        restarted = self.restart(reopened)
        for _ in range(2):                         # the webhook, the catch-up poll and the spool all hand it over again
            reopened.doorbell({"type": "new-message", "data": {"guid": "m1"}}, self.now)
            restarted.fetch()
            self.query = [self.messages["m1"]]
            restarted.catch_up()
            restarted.ack()
        self.assertEqual(self.taps(), [(OWNER_CHAT, "m1", "like")])
        self.assertEqual(dict(reopened.db.execute("SELECT provider_id,state FROM ack").fetchall()), {"m1": "sent"})

    def test_a_crash_between_claim_and_send_never_sends_the_ack_again(self):
        self.enqueue("m1")
        self.spool.db.execute("UPDATE ack SET state='sending'")  # the process died inside the send
        self.f.ack()
        self.assertEqual(self.out(), [])

    def test_a_pending_ack_survives_a_restart_and_is_sent_once(self):
        self.enqueue("m1")
        reopened = fwd.Spool(self.root, self.now)
        self.addCleanup(reopened.db.close)
        restarted = self.restart(reopened)
        restarted.ack()
        restarted.ack()
        self.assertEqual(len(self.taps()), 1)

    def test_two_messages_two_acks(self):
        self.enqueue("a")
        self.enqueue("b")
        self.f.ack()
        self.assertEqual(self.taps(), [(OWNER_CHAT, "a", "like"), (OWNER_CHAT, "b", "like")])


class NotWhenPausedOrUnknown(AckCase):
    def test_no_host_answer_means_no_ack_now_and_never_a_late_one(self):
        self.host_ok(None)
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual((self.out(), self.states()), ([], {"m1": "unknown"}))
        self.host_ok(False)  # the host is back a moment later: still not sent (fail closed, not late)
        self.f.ack()
        self.assertEqual(self.out(), [])

    def test_the_host_is_asked_fresh_for_every_ack_nothing_is_cached(self):
        self.enqueue("a")
        self.f.ack()
        self.host_ok(True)                   # paused between two messages, with no poll in between
        self.enqueue("b")
        self.f.ack()
        self.host_ok(False)
        self.enqueue("c")
        self.f.ack()
        self.assertEqual((self.state_asked, len(self.taps()), self.states()), (3, 2, {"a": "sent", "b": "paused", "c": "sent"}))

    def test_paused_host_means_no_ack_at_all(self):
        self.host_ok(paused=True)
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual((self.out(), self.states()), ([], {"m1": "paused"}))
        self.host_ok(paused=False)
        self.f.ack()
        self.assertEqual(self.out(), [])  # the closed row is not reopened

    def test_a_pause_command_stored_here_and_not_yet_handed_to_the_host_blocks_it_and_everything_after_it(self):
        asked = self.state_asked
        for text in ("stop changes", "pause", "Pause changes.", "stop", "STOP!"):
            with self.subTest(text=text):
                self.clear()
                self.enqueue("c" + text[:3], text=text)
                self.enqueue("after" + text[:3])
                self.f.ack()
                self.assertEqual(self.out(), [])
                self.spool.db.execute("UPDATE inbound SET state='done',payload=NULL")  # handed to the host; the host's queue takes over
        self.assertEqual(self.state_asked, asked)  # all ten are stopped here, before the host is even asked

    def test_a_message_that_cannot_be_read_counts_as_a_pause_ahead(self):
        self.enqueue("a")
        self.spool.db.execute("UPDATE inbound SET payload='not json' WHERE provider_id='a'")
        self.enqueue("b")
        self.f.ack()
        self.assertEqual(self.out(), [])

    def test_an_earlier_unresolved_doorbell_holds_the_ack_but_not_a_later_one(self):
        def accept(guid):
            self.spool.accept({"type": "new-message", "data": self.message(guid)}, OWNER_CHAT, self.now)
        accept("m1")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "earlier"}}, self.now - 1)  # its fetch keeps failing: content unknown
        self.f.ack()
        self.assertEqual((self.out(), self.states()), ([], {"m1": "paused"}))
        self.spool.db.execute("DELETE FROM fetch")
        accept("m2")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "later"}}, self.now + 5)
        self.f.ack()
        self.assertEqual(len(self.taps()), 1)

    def test_a_status_or_free_text_message_does_not_hold_the_ack(self):
        for text in ("status", "resume changes", "Stop showing the eggs as sold out"):
            with self.subTest(text=text):
                self.clear()
                self.enqueue("m" + str(len(text)), text=text)
                self.f.ack()
                self.assertEqual(len(self.taps()), 1)

    def test_switched_off_by_config(self):
        self.f.cfg = {**self.cfg, "ack": False}
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual((self.out(), self.states(), self.pending(), self.state_asked, self.info_asked), ([], {"m1": "off"}, 1, 0, 0))

    def test_host_paused_reads_the_answer_and_every_failure_is_unknown(self):
        self.assertIs(self.f.host_paused(self.spool), False)
        self.host_ok(True)
        self.assertIs(self.f.host_paused(self.spool), True)
        for bad in (bridge.BridgeError("transport-error"), ValueError("relay-op"), KeyError("paused"), bridge.EnvelopeError("mac")):
            with self.subTest(bad=bad), mock.patch.object(self.f, "control", side_effect=bad):
                self.assertIsNone(self.f.host_paused(self.spool))
        with mock.patch.object(self.f, "control", return_value={"op": "state", "paused": "no"}):
            self.assertIsNone(self.f.host_paused(self.spool))

    def test_an_older_host_that_does_not_know_the_op_means_no_ack(self):
        def old_host(url, body=None):
            if url.endswith("/v1/relay"): raise bridge.BridgeError("http-error")
            return ft.ForwarderCase.transport(self, url, body)
        self.f.transport = self.f.quick = old_host
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual((self.out(), self.states()), ([], {"m1": "unknown"}))


class NeverAText(AckCase):
    """G, 2026-11-08: "mark my message, not send me a message". Whatever goes wrong, the ack is a tapback or nothing."""

    def test_private_api_off_means_no_react_call_and_no_text(self):
        self.info = {"private_api": False, "helper_connected": False, "server_version": "1.9.9"}
        self.enqueue("m1")
        with contextlib.redirect_stderr(io.StringIO()) as err: self.f.ack()
        self.assertEqual((self.out(), self.states()), ([], {"m1": "private_api_off"}))
        self.assertIn("ack_skipped reason=private_api_off", err.getvalue())
        self.f.deliver()
        self.assertEqual(len(self.posts), 1)           # the message itself still goes through

    def test_helper_not_connected_means_no_react_call_and_no_text(self):
        self.info = {"private_api": True, "helper_connected": False}
        self.enqueue("m1")
        with contextlib.redirect_stderr(io.StringIO()) as err: self.f.ack()
        self.assertEqual((self.out(), self.states()), ([], {"m1": "helper_disconnected"}))
        self.assertIn("ack_skipped reason=helper_disconnected", err.getvalue())

    def test_a_probe_that_cannot_answer_or_answers_oddly_is_not_on(self):
        for n, info in enumerate((None, {}, {"private_api": "true", "helper_connected": True}, {"private_api": 1, "helper_connected": 1}, [])):
            with self.subTest(info=info):
                self.info = info
                self.probe_again()
                self.enqueue(f"u{n}")
                with contextlib.redirect_stderr(io.StringIO()) as err: self.f.ack()
                self.assertEqual(self.out(), [])
                self.assertEqual(self.states()[f"u{n}"], "private_api_unknown")
                self.assertIn("ack_skipped reason=private_api_unknown", err.getvalue())

    def test_the_probe_is_shared_by_a_burst_and_asked_again_after_its_ttl(self):
        for name in "abc": self.enqueue(name)
        self.f.ack()
        self.assertEqual((len(self.taps()), self.info_asked), (3, 1))
        self.now += fwd.PROBE_TTL + 1
        self.enqueue("d")
        self.f.ack()
        self.assertEqual((len(self.taps()), self.info_asked), (4, 2))

    def test_private_api_switched_on_later_is_noticed_and_off_later_is_noticed(self):
        self.info = {"private_api": False, "helper_connected": False}
        self.enqueue("a")
        with contextlib.redirect_stderr(io.StringIO()): self.f.ack()
        self.info = dict(INFO_ON)
        self.now += fwd.PROBE_TTL + 1
        self.enqueue("b")
        self.f.ack()
        self.info = {"private_api": False, "helper_connected": False}
        self.now += fwd.PROBE_TTL + 1
        self.enqueue("c")
        with contextlib.redirect_stderr(io.StringIO()): self.f.ack()
        self.assertEqual((self.taps(), self.sender.calls, self.states()), ([(OWNER_CHAT, "b", "like")], [], {"a": "private_api_off", "b": "sent", "c": "private_api_off"}))

    def test_a_react_failure_sends_nothing_else_logs_a_reason_and_never_retries(self):
        self.enqueue("m1")
        self.reactor.fail = bridge.BridgeError("http-error", 500)
        with contextlib.redirect_stderr(io.StringIO()) as err: self.f.ack()           # does not raise
        self.reactor.fail = None
        self.f.ack()
        self.f.deliver()
        self.assertEqual((self.states(), self.out(), len(self.posts)), ({"m1": "react_failed"}, [], 1))
        self.assertIn("ack_skipped reason=react_failed", err.getvalue())
        self.assertNotIn("m1", err.getvalue())         # a reason code only

    def test_any_error_type_from_the_reactor_is_swallowed_and_is_never_a_text(self):
        self.enqueue("m1")
        self.reactor.react = mock.Mock(side_effect=RuntimeError("boom"))
        with contextlib.redirect_stderr(io.StringIO()): self.f.ack()
        self.assertEqual((self.states(), self.sender.calls), ({"m1": "react_failed"}, []))

    def test_a_react_failure_does_not_block_or_delay_the_real_delivery(self):
        self.reactor.fail = bridge.BridgeError("transport-error")
        self.message("m1")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "m1"}}, self.now)
        with mock.patch.object(self.f, "control", side_effect=lambda body, expected, big=False, **kw: (
                {"op": "state", "paused": False} if body["op"] == "state" else {"op": "replies", "items": []})):
            with contextlib.redirect_stderr(io.StringIO()): self.f.cycle()
        self.assertEqual((len(self.posts), self.sender.calls, self.states()), (1, [], {"m1": "react_failed"}))
        self.items = [{"id": 7, "chat": OWNER_CHAT, "text": "the real reply", "pictures": 0}]
        self.f.pull()
        self.assertEqual((self.sender.calls, self.acks), ([(OWNER_CHAT, "the real reply", ())], [7]))  # the only text ever sent is the reply

    def test_a_broken_ack_table_never_loses_the_message(self):
        self.spool.db.execute("DROP TABLE ack")
        self.enqueue("m1")
        with contextlib.redirect_stderr(io.StringIO()):
            self.f.ack()
            self.f.deliver()
        self.assertEqual((len(self.posts), self.out()), (1, []))

    def test_a_missing_or_malformed_message_guid_means_no_call(self):
        bad = ["", " ", "has space", "new\nline", "a" * 129, "../etc/passwd", "p:0/ABC", "x;y", "-leading-dash", "q?x=1", "tab\tx", "ünï", None, 7, b"x"]
        for n, guid in enumerate(bad):
            with self.subTest(guid=guid):
                if isinstance(guid, str): self.assertFalse(fwd.valid_guid(guid))
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.f._ack_row(self.spool, guid, self.now)
                self.assertEqual(self.out(), [])
                self.assertIn("ack_skipped reason=bad_guid", err.getvalue())
        self.assertFalse(fwd.valid_guid("\ud800"))     # a lone surrogate (the spool cannot even store one)
        self.assertEqual(self.info_asked, 0)           # not even the probe: nothing about a bad guid leaves the Mac
        for guid in ("m1", "9F3A6B1C-1234-4DEF-8ABC-0123456789AB", "A" * 128): self.assertTrue(fwd.valid_guid(guid), guid)

    def test_a_message_whose_guid_is_malformed_is_still_delivered_but_gets_no_tapback(self):
        self.enqueue("bad.guid")
        with contextlib.redirect_stderr(io.StringIO()) as err: self.f.ack()
        self.f.deliver()
        self.assertEqual((self.out(), self.states(), len(self.posts), self.info_asked), ([], {"bad.guid": "bad_guid"}, 1, 0))
        self.assertIn("ack_skipped reason=bad_guid", err.getvalue())

    def test_the_reactor_refuses_bad_arguments_before_any_network_call(self):
        calls = []
        r = fwd.BlueBubblesReactor("http://127.0.0.1:1234", self.root / "password", transport=lambda *a: calls.append(a) or 200)
        for chat, guid, reaction in ((OWNER_CHAT, "", "like"), (OWNER_CHAT, "bad guid", "like"), (OWNER_CHAT, "m1", "-like"), (OWNER_CHAT, "m1", "eyes"),
                                     (OWNER_CHAT, "m1", "\N{EYES}"), (OWNER_CHAT, "m1", ""), (OWNER_CHAT, "m1", None), ("", "m1", "like"), (None, "m1", "like")):
            with self.subTest(guid=guid, reaction=reaction), self.assertRaises(ValueError): r.react(chat, guid, reaction)
        self.assertEqual(calls, [])

    def test_there_is_no_text_ack_left_in_the_code(self):
        self.assertFalse(hasattr(fwd, "ACK_TEXT"))
        self.assertNotIn("acker", fwd.Forwarder.__init__.__code__.co_varnames)
        self.assertFalse(any(hasattr(fwd.BlueBubblesReactor, name) for name in ("send", "send_text", "send_png")))
        source = Path(fwd.__file__).read_text()
        self.assertEqual([i for i, line in enumerate(source.splitlines()) if "message/text" in line], [])  # the forwarder itself never names the text endpoint
        self.assertNotIn("\N{EYES}", source.split("# HASS-TAPBACK-1", 1)[1].split("\n\n", 1)[1])         # no 👀 constant below the explanatory comment


class WireShape(AckCase):
    """The real reactor and the real probe path against a synthetic BlueBubbles transport: the exact calls."""

    def setUp(self):
        super().setUp()
        self.wire = []

        def post(url, body, headers, timeout):
            self.wire.append(("POST", url, json.loads(body), headers, timeout))
            return 200
        self.f.reactor = fwd.BlueBubblesReactor("http://127.0.0.1:1234", self.root / "password", transport=post)

    def test_one_post_to_the_react_endpoint_with_the_four_documented_fields_and_nothing_else(self):
        self.enqueue("9F3A6B1C-1234-4DEF-8ABC-0123456789AB")
        self.f.ack()
        (verb, url, body, headers, timeout), = self.wire
        self.assertEqual(verb, "POST")
        self.assertEqual(url, "http://127.0.0.1:1234/api/v1/message/react?password=synthetic-not-a-real-password")
        self.assertEqual(body, {"chatGuid": OWNER_CHAT, "selectedMessageGuid": "9F3A6B1C-1234-4DEF-8ABC-0123456789AB", "reaction": "like", "partIndex": 0})
        self.assertEqual((headers, timeout), ({"Content-Type": "application/json"}, fwd.ACK_TIMEOUT))
        self.assertEqual([p for p, _ in self.calls if p.startswith("/api/v1/") and "message/text" in p], [])
        self.assertEqual(self.sender.calls, [])

    def test_a_non_2xx_answer_or_a_transport_error_is_a_failed_react_not_a_text(self):
        for status in (400, 401, 404, 500, 302, None, "200"):
            with self.subTest(status=status):
                self.wire.clear()
                self.f.reactor.transport = lambda *a, status=status: status
                self.enqueue(f"f{status}")
                with contextlib.redirect_stderr(io.StringIO()): self.f.ack()
                self.assertEqual((self.states()[f"f{status}"], self.sender.calls), ("react_failed", []))

        def boom(*a): raise OSError("http://127.0.0.1:1234/api/v1/message/react?password=synthetic-not-a-real-password")
        self.f.reactor.transport = boom
        self.enqueue("boom")
        with contextlib.redirect_stderr(io.StringIO()) as err: self.f.ack()
        self.assertEqual(self.states()["boom"], "react_failed")
        self.assertNotIn("synthetic-not-a-real-password", err.getvalue())
        with self.assertRaises(bridge.BridgeError) as cm: self.f.reactor.react(OWNER_CHAT, "m1", "like")
        self.assertNotIn("synthetic", repr(cm.exception.args))
        self.assertIsNone(cm.exception.__cause__)

    def test_an_unreadable_password_file_is_a_failed_react_not_a_call(self):
        self.f.reactor.password_file = self.root / "missing"
        self.enqueue("m1")
        with contextlib.redirect_stderr(io.StringIO()): self.f.ack()
        self.assertEqual((self.wire, self.states(), self.sender.calls), ([], {"m1": "react_failed"}, []))

    def test_the_configured_reaction_is_what_goes_on_the_wire(self):
        self.f.cfg = {**self.cfg, "ack_reaction": "love"}
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual(self.wire[0][2]["reaction"], "love")

    def test_the_default_reactor_has_a_short_clamp_and_the_probe_a_short_timeout(self):
        seen = []
        with mock.patch.object(bridge, "_urllib_transport", side_effect=lambda u, b, h, t: seen.append(t) or 200):
            f = fwd.Forwarder(self.cfg, self.spool, lambda: self.now, self.transport, self.sender)
            f.reactor.react(OWNER_CHAT, "m1", "like")
        self.assertEqual(seen, [fwd.ACK_TIMEOUT])
        opened = []

        class Opener:
            def open(self, req, timeout=None):
                opened.append((req.get_method(), req.data, timeout))
                raise OSError("down")
        with mock.patch.object(bridge, "_OPENER", Opener()):
            f = fwd.Forwarder(self.cfg, self.spool, lambda: self.now, fwd.request_json, self.sender)
            self.assertEqual(f.tapback_blocker(), "private_api_unknown")
        self.assertEqual(opened, [("GET", None, fwd.ACK_STATE_TIMEOUT)])


class AllowlistedReaction(AckCase):
    def test_every_standard_tapback_is_allowed_and_only_those(self):
        self.assertEqual(set(fwd.TAPBACKS), {"love", "like", "dislike", "laugh", "emphasize", "question"})
        self.assertEqual(fwd.ACK_REACTION, "like")
        for n, name in enumerate(fwd.TAPBACKS):
            with self.subTest(name=name):
                self.f.cfg = {**self.cfg, "ack_reaction": name}
                self.enqueue(f"r{n}")
                self.f.ack()
        self.assertEqual([t[2] for t in self.taps()], list(fwd.TAPBACKS))

    def test_a_reaction_outside_the_allowlist_sends_nothing_even_if_it_got_past_the_config_check(self):
        for n, bad in enumerate(("-like", "eyes", "\N{EYES}", "LIKE", "", " like", None, 1, ["like"])):
            with self.subTest(bad=bad):
                self.f.cfg = {**self.cfg, "ack_reaction": bad}
                self.enqueue(f"b{n}")
                with contextlib.redirect_stderr(io.StringIO()) as err: self.f.ack()
                self.assertIn("reason=bad_reaction", err.getvalue())
        self.assertEqual((self.out(), set(self.states().values())), ([], {"bad_reaction"}))


class CycleOrderAndPolling(AckCase):
    def setUp(self):
        super().setUp()
        self.cycle_control = lambda body, expected, big=False, **kw: (
            {"op": "state", "paused": False} if body["op"] == "state" else {"op": "replies", "items": []})
        orig = self.transport

        def transport(url, body=None):
            if url.endswith("/v1/inbound"): self.order.append("post")
            return orig(url, body)
        self.f.transport = transport
        plain = self.reactor.react
        self.reactor.react = lambda chat, guid, reaction: (self.order.append("ack"), plain(chat, guid, reaction))[1]

    def test_one_cycle_fetches_acks_then_posts_in_that_order_without_a_thread(self):
        self.message("m1")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "m1"}}, self.now)
        with mock.patch.object(self.f, "control", side_effect=self.cycle_control):
            self.f.cycle()
        self.assertEqual(self.order, ["ack", "post"])

    def test_reply_pull_is_fast_for_three_minutes_after_an_owner_message_then_slow(self):
        with mock.patch.object(self.f, "control", side_effect=self.cycle_control):
            self.f.cycle()
            self.assertEqual(self.f.next_pull - self.now, fwd.PULL_SLOW)
            self.message("m1")
            self.spool.doorbell({"type": "new-message", "data": {"guid": "m1"}}, self.now)
            self.f.cycle()
            self.now += fwd.PULL_SLOW
            self.f.cycle()
            self.assertEqual(self.f.next_pull - self.now, fwd.PULL_FAST)
            self.now += fwd.FAST_WINDOW + 1
            self.f.cycle()
            self.assertEqual(self.f.next_pull - self.now, fwd.PULL_SLOW)

    def test_an_owner_message_cuts_a_slow_pull_wait_short(self):
        with mock.patch.object(self.f, "control", side_effect=self.cycle_control):
            self.f.cycle()
            slow_until = self.f.next_pull
            self.assertEqual(slow_until - self.now, fwd.PULL_SLOW)
            self.now += 1
            self.message("m1")
            self.spool.doorbell({"type": "new-message", "data": {"guid": "m1"}}, self.now)
            self.f.cycle()
            self.now += 0.5
            self.f.cycle()
            self.assertLessEqual(self.f.next_pull - self.now, fwd.PULL_FAST)
            self.assertLess(self.f.next_pull, slow_until)

    def test_a_stranger_never_speeds_up_the_pull(self):
        self.message("s", handle={"address": STRANGER})
        self.spool.doorbell({"type": "new-message", "data": {"guid": "s"}}, self.now)
        with mock.patch.object(self.f, "control", side_effect=self.cycle_control):
            self.f.cycle()
            self.now += fwd.PULL_SLOW
            self.f.cycle()
        self.assertEqual(self.f.next_pull - self.now, fwd.PULL_SLOW)


class ConfigAndCheck(ft.ForwarderCase):
    def load(self, **over):
        self.config.write_text(json.dumps({**self.cfg, **over}))
        return fwd.load_config(self.config)

    def test_ack_key_is_optional_boolean_and_closed(self):
        self.assertNotIn("ack", self.load())
        self.assertIs(self.load(ack=False)["ack"], False)
        for bad in ("no", 0, None, []):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.load(ack=bad)
        with self.assertRaises(ValueError): self.load(other=1)

    def test_ack_reaction_key_is_optional_and_checked_against_the_allowlist(self):
        self.assertNotIn("ack_reaction", self.load())            # absent: the code default 'like' applies
        for name in fwd.TAPBACKS: self.assertEqual(self.load(ack_reaction=name)["ack_reaction"], name)
        for bad in ("-like", "eyes", "\N{EYES}", "Like", "", "like ", None, 0, True, ["like"], {"like": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.load(ack_reaction=bad)

    def test_ackcheck_is_read_only_and_names_the_tapback_and_the_server_version(self):
        for info, possible in (({"private_api": False, "helper_connected": False}, False), ({"private_api": True, "helper_connected": False}, False),
                               ({"private_api": True, "helper_connected": True, "server_version": "1.9.9"}, True), ({}, False)):
            with self.subTest(info=info), mock.patch.object(fwd, "request_json", return_value={"data": info}) as rj, \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(fwd.main(["ackcheck", "--config", str(self.config)]), 0)
            (url,), kwargs = rj.call_args
            self.assertTrue(url.startswith("http://127.0.0.1:1234/api/v1/server/info?password="))
            self.assertEqual(kwargs, {})  # a GET: no body
            self.assertEqual(json.loads(out.getvalue()),
                             {"ackMethod": "tapback", "ackReaction": "like", "helperConnected": bool(info.get("helper_connected")),
                              "privateApi": bool(info.get("private_api")), "serverVersion": info.get("server_version"),
                              "supportedReactions": list(fwd.TAPBACKS), "tapbackPossible": possible})
            self.assertNotIn("synthetic-not-a-real-password", out.getvalue())

    def test_ackcheck_shows_the_configured_reaction_and_ignores_an_odd_version_string(self):
        self.load(ack_reaction="laugh")
        with mock.patch.object(fwd, "request_json", return_value={"data": {"private_api": True, "helper_connected": True, "server_version": "x y\n"}}), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(fwd.main(["ackcheck", "--config", str(self.config)]), 0)
        self.assertEqual((json.loads(out.getvalue())["ackReaction"], json.loads(out.getvalue())["serverVersion"]), ("laugh", None))

    def test_ackcheck_failure_prints_the_fixed_error_only(self):
        with mock.patch.object(fwd, "request_json", side_effect=bridge.BridgeError("transport-error")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(fwd.main(["ackcheck", "--config", str(self.config)]), 2)
        self.assertEqual(out.getvalue().strip(), '{"error": 1}')


class StateOp(unittest.TestCase):
    def test_shapes(self):
        key, kw = b"k" * 32, dict(nonce="ab" * 16, now=NOW)
        self.assertEqual(relay.unseal_control(relay.seal_control({"op": "state"}, key, **kw), key, now=NOW, seen=set()), {"op": "state"})
        for paused in (True, False):
            body = {"op": "state", "paused": paused}
            self.assertEqual(relay.unseal_control(relay.seal_control(body, key, **kw), key, now=NOW, seen=set()), body)
        for bad in ({"op": "state", "paused": 1}, {"op": "state", "paused": None}, {"op": "state", "x": 1}, {"op": "state", "paused": True, "x": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): relay.seal_control(bad, key, **kw)

    def test_old_shapes_are_unchanged(self):
        self.assertEqual(set(relay.SHAPES), {"pull", "ack", "replies", "acked", "picture", "gone", "state"})


class HostState(host_tests.HostCase):
    def serve(self, **kw):
        cfg = host.load_host(self.host_json(listen="127.0.0.1:0"), allow_port_zero=True)
        srv = host.Server(cfg, bytes.fromhex(host_tests.KEY_HEX), receiver.Receiver(state=self.inbox, settings=None), self.store, self.clock, **kw)
        srv.timeout = 5
        self.addCleanup(srv.server_close)
        return srv

    def state_call(self, srv, body=None):
        env = relay.seal_control(body or {"op": "state"}, bytes.fromhex(host_tests.KEY_HEX), nonce=os.urandom(16).hex(), now=int(self.now.timestamp()))
        status, raw = self.post(srv, "/v1/relay", json.dumps(env).encode())
        return status, (relay.unseal_control(json.loads(raw), bytes.fromhex(host_tests.KEY_HEX), now=int(self.now.timestamp()), seen=set()) if status == 200 else None)

    def test_flag_reads_the_real_store_read_only(self):
        self.assertFalse(host.paused_flag(self.repo.state))  # no control table yet: never paused
        self.conv.db.execute(conv_control())
        self.conv.db.execute("INSERT INTO control(name,value,set_at,provider_id) VALUES ('paused','1','2026-11-02T17:00:00+00:00','x')")
        self.assertTrue(host.paused_flag(self.repo.state))
        self.conv.db.execute("DELETE FROM control WHERE name='paused'")
        self.assertFalse(host.paused_flag(self.repo.state))
        before = (Path(self.repo.state) / "conversation.sqlite3").read_bytes()
        host.paused_flag(self.repo.state)
        self.assertEqual((Path(self.repo.state) / "conversation.sqlite3").read_bytes(), before)

    def test_unreadable_or_missing_store_means_paused(self):
        self.assertTrue(host.paused_flag(Path(self.hostdir) / "nowhere"))
        bad = Path(tempfile.mkdtemp(dir=self.hostdir))
        (bad / "conversation.sqlite3").write_bytes(b"not a database")
        self.assertTrue(host.paused_flag(bad))

    def test_the_state_op_answers_over_the_sealed_relay(self):
        srv = self.serve(paused=lambda: False)
        self.assertEqual(self.state_call(srv), (200, {"op": "state", "paused": False}))
        srv = self.serve(paused=lambda: True)
        self.assertEqual(self.state_call(srv), (200, {"op": "state", "paused": True}))
        srv = self.serve()  # the default answer is the safe one
        self.assertEqual(self.state_call(srv), (200, {"op": "state", "paused": True}))

    def test_an_answer_shaped_body_sent_to_the_host_is_refused(self):
        srv = self.serve(paused=lambda: False)
        env = relay.seal_control({"op": "state", "paused": True}, bytes.fromhex(host_tests.KEY_HEX), nonce=os.urandom(16).hex(), now=int(self.now.timestamp()))
        status, _ = self.post(srv, "/v1/relay", json.dumps(env).encode())
        self.assertEqual(status, 400)


def conv_control():
    from hass import conversation
    return conversation.CONTROL


class EndToEnd(host_tests.HostCase):
    """The real forwarder, the real host Server, Receiver, Worker and Conversation; only BlueBubbles and the model are fake."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.root.chmod(0o700)
        for name, data in (("key", host_tests.KEY_HEX), ("token", "ab" * 32), ("password", "synthetic")):
            (self.root / name).write_text(data)
            (self.root / name).chmod(0o600)
        cfg = host.load_host(self.host_json(listen="127.0.0.1:0"), allow_port_zero=True)
        self.work = self.worker(private=False)
        self.srv = host.Server(cfg, bytes.fromhex(host_tests.KEY_HEX), receiver.Receiver(state=self.inbox, settings=None), self.store, self.clock,
                               paused=lambda: host.paused_flag(self.repo.state))
        self.srv.timeout = 5
        self.addCleanup(self.srv.server_close)
        self.t = lambda: self.now.timestamp()
        self.cfg = dict(ownerChat=OWNER_CHAT, receiverUrl=f"http://127.0.0.1:{self.srv.server_port}", bbPort=1, bbPasswordFile=str(self.root / "password"),
                        secretFile=str(self.root / "key"), webhookTokenFile=str(self.root / "token"), spoolDir=str(self.root), webhookPort=0)
        self.spool = fwd.Spool(self.root, self.t())
        self.addCleanup(self.spool.db.close)
        self.sent, self.messages, self.tapped = [], {}, []  # texts the Mac sent; tapbacks the Mac reacted with
        sender = mock.Mock()
        sender.send.side_effect = lambda chat, text, att=(): self.sent.append(text)
        reactor = mock.Mock()
        reactor.react.side_effect = lambda chat, guid, reaction: self.tapped.append((chat, guid, reaction))
        self.log = stagelog.StageLog(self.root / "stages.jsonl", clock=self.t)
        self.f = fwd.Forwarder(self.cfg, self.spool, self.t, self.transport, sender, stage=self.log, reactor=reactor)
        self.work.stage = self.log
        self.srv.receiver.stage = self.log

    def transport(self, url, body=None):
        if url.startswith(self.cfg["receiverUrl"]):
            box = {}

            def go():
                try: box["r"] = fwd.request_json(url, body)
                except Exception as exc: box["e"] = exc  # noqa: BLE001
            thread = threading.Thread(target=go)
            thread.start()
            self.srv.handle_request()
            thread.join()
            if "e" in box: raise box["e"]
            return box["r"]
        if "/api/v1/server/info" in url: return {"data": dict(INFO_ON)}
        return {"data": self.messages[url.split("/api/v1/message/")[1].split("?")[0]]}

    def owner_text(self, guid, text, sender=OWNER):
        self.messages[guid] = {"guid": guid, "dateCreated": int(self.t() * 1000), "isFromMe": False, "handle": {"address": sender},
                               "chats": [{"guid": OWNER_CHAT}], "text": text, "attachments": []}
        self.spool.doorbell({"type": "new-message", "data": {"guid": guid}}, self.t())
        self.f.fetch()

    def go(self):
        """One Mac step and one host step, the way the services take turns."""
        self.f.ack()
        self.f.deliver()
        self.work.cycle()
        self.f.pull()

    def test_owner_message_is_seen_first_then_answered_and_the_log_shows_every_stage(self):
        self.assertIs(self.f.host_paused(self.spool), False)
        self.owner_text("m1", "hours")
        self.f.ack()
        self.assertEqual((self.sent, self.tapped, self.relay_rows()), ([], [(OWNER_CHAT, "m1", "like")], []))  # tapback out, never a text; the receiver has seen nothing yet
        self.f.deliver()
        self.assertEqual(len(self.inbound_rows()), 1)
        self.now += timedelta(seconds=1)
        self.work.cycle()
        self.f.pull()
        self.assertEqual(len(self.sent), 1)  # the reply is the only text; the tapback was not one
        self.assertEqual(len(self.drafts()), 1)  # the normal draft path is unchanged
        self.assertEqual((self.f.pull() or len(self.sent), len(self.tapped)), (1, 1))  # nothing more to send, no second tapback, no text
        rows = stagelog.table(stagelog.read(self.root / "stages.jsonl"))
        stages = [set(s) for _, s in rows]
        self.assertEqual(len(rows), 1)
        self.assertTrue({"accepted", "ack-start", "ack-end", "post-start", "post-end", "receiver-accepted", "worker-pickup", "handled",
                         "reply-queued", "reply-pulled", "bb-send-start", "bb-send-end"} <= stages[0], stages[0])

    def test_stranger_in_the_owner_chat_gets_no_ack_and_no_reply(self):
        self.owner_text("s1", "hours", sender=STRANGER)
        self.go()
        self.work.cycle()
        self.f.pull()
        self.assertEqual((self.sent, self.relay_rows(), self.drafts()), ([], [], []))
        self.assertEqual(self.conv.db.execute("SELECT disposition FROM messages").fetchall()[0][0], "ignored")  # read by the host, answered by nobody

    def test_pause_stops_the_eyes_and_resume_brings_them_back_and_a_replay_adds_none(self):
        self.owner_text("a", "status")
        self.go()
        self.assertEqual(len(self.tapped), 1)
        self.now += timedelta(seconds=1)
        self.owner_text("p", "stop changes")
        self.go()                                   # the pause command is read by the host in this step; it gets no 👀 itself
        self.assertEqual(len(self.tapped), 1)
        self.assertTrue(host.paused_flag(self.repo.state))
        before = len(self.tapped)
        self.owner_text("b", "status")
        self.go()
        self.assertEqual(len(self.tapped), before)  # paused: seen by nobody, still answered
        self.assertTrue(any("paused" in s.lower() for s in self.sent))
        self.owner_text("r", "resume changes")
        self.go()
        self.assertFalse(host.paused_flag(self.repo.state))
        self.now += timedelta(seconds=1)
        self.owner_text("c", "status")
        self.go()
        self.assertEqual(len(self.tapped), before + 1)
        self.owner_text("c", "status")              # the same message again (webhook, catch-up, replay)
        self.go()
        self.assertEqual(len(self.tapped), before + 1)

    def test_pause_set_on_the_host_between_two_polls_stops_the_next_eyes_at_once(self):
        """The reviewer's case: the last answer was 'not paused', then the pause lands on the real host store, then a fresh owner
        message is accepted before anything else polls. No cached answer exists, so the host is asked again and says paused."""
        self.owner_text("a", "status")
        self.f.ack()
        self.assertEqual((self.sent, len(self.tapped)), ([], 1))
        self.conv.db.execute(conv_control())
        self.conv.db.execute("INSERT INTO control(name,value,set_at,provider_id) VALUES ('paused','1','2026-11-02T17:00:00+00:00','synthetic')")
        self.assertTrue(host.paused_flag(self.repo.state))
        self.owner_text("after-pause", "status")
        self.f.ack()
        self.assertEqual((self.sent, len(self.tapped)), ([], 1))
        self.assertEqual(dict(self.spool.db.execute("SELECT provider_id,state FROM ack").fetchall()), {"a": "sent", "after-pause": "paused"})

    def test_a_pause_command_queued_at_the_host_behind_a_slow_interpretation_stops_the_eyes_before_it_is_read(self):
        """The owner's 'stop changes' reached the host inbox but the worker is still busy with an earlier message, so the pause
        flag is not set yet. The next owner message must still get no 👀: the host reports its unread pause command."""
        self.owner_text("slow", "please add eggs to the shelf")
        self.f.ack()
        self.f.deliver()                            # the slow message is in the host inbox, the worker never runs in this test
        self.owner_text("p", "stop changes")
        self.f.ack()
        self.f.deliver()                            # the pause command is queued at the host; its flag is NOT set
        self.assertFalse(self.conv.db.execute("SELECT name FROM sqlite_master WHERE name='control'").fetchall())  # nothing has paused yet
        self.assertTrue(host.paused_flag(self.repo.state))
        self.owner_text("next", "status")
        self.f.ack()                                # the spool no longer holds the pause command (it is done); only the host knows
        self.assertEqual((self.sent, [t[1] for t in self.tapped]), ([], ["slow"]))  # only the 'slow' one, tapped before the pause command existed
        self.assertEqual(self.spool.db.execute("SELECT state FROM ack WHERE provider_id='next'").fetchone()[0], "paused")

    def test_a_failed_state_question_means_no_eyes_even_after_an_unpaused_answer(self):
        self.owner_text("a", "status")
        self.f.ack()
        self.owner_text("b", "status")
        with mock.patch.object(self.f, "quick", side_effect=bridge.BridgeError("transport-error")):
            self.f.ack()
        self.assertEqual((self.sent, len(self.tapped)), ([], 1))
        self.assertEqual(self.spool.db.execute("SELECT state FROM ack WHERE provider_id='b'").fetchone()[0], "unknown")

    def test_the_hosts_own_replies_never_cause_an_ack(self):
        self.owner_text("a", "help")
        self.go()
        echo = {"guid": "echo1", "dateCreated": int(self.t() * 1000), "isFromMe": True, "handle": {"address": OWNER},
                "chats": [{"guid": OWNER_CHAT}], "text": "reply text", "attachments": []}
        self.messages["echo1"] = echo
        self.spool.doorbell({"type": "new-message", "data": {"guid": "echo1"}}, self.t())
        self.f.fetch()
        self.go()
        self.assertEqual(len(self.tapped), 1)

    # -- HASS-FAST-1-FIX item 2: the worker moves a pause from the inbox queue into the control flag while the host reads --
    def _requeue_pause(self, guid):
        """A fresh, unread 'stop changes' at the host and no flag: the state before the worker moves it."""
        self.conv.db.execute("DELETE FROM control WHERE name = 'paused'") if self.conv.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'control'").fetchone() else None
        self.inbox.db.execute("DELETE FROM inbound")
        self.now += timedelta(seconds=1)
        self.owner_text(guid, "stop changes")
        self.f.deliver()
        self.assertEqual(len(self.inbound_rows()), 1)

    def _worker_moves_the_pause(self, blocked):
        """The real worker reads the queued pause, commits the flag, marks the message done. With a reader holding a lock the
        worker may be unable to commit at that instant (SQLite busy): that is a legitimate outcome, not a failure."""
        try: self.work.cycle()
        except sqlite3.OperationalError:  # the worker gives up this round (a rolled-back commit) and would retry
            blocked.append(1)
            for db in (self.conv.db, self.inbox.db):
                if db.in_transaction: db.execute("ROLLBACK")

    def _after_step(self, k, action):
        """Patch the sqlite3 that hass.host uses so `action` runs once, right after the k-th statement paused_flag executes."""
        steps, fired = [0], []

        class Hooked:
            def __init__(self, db): self.db = db
            def execute(self, *args):
                try: return self.db.execute(*args)
                finally:
                    steps[0] += 1
                    if steps[0] == k: fired.append(k); action()
            def close(self): self.db.close()
        proxy = mock.Mock(wraps=sqlite3)
        proxy.connect = lambda *a, **kw: Hooked(sqlite3.connect(*a, **kw))
        proxy.Error, proxy.Row = sqlite3.Error, sqlite3.Row
        return mock.patch.object(host, "sqlite3", proxy), fired

    def test_a_pause_moved_from_the_queue_to_the_flag_between_the_reads_is_never_reported_unpaused(self):
        """The reviewer's round 2 interleaving, at every statement boundary of the host's read: queue a pause, let the real
        worker move it (flag committed, then inbox row marked done) right after step k, and ask. Never False."""
        reached, blocked = [], []
        for k in range(1, 20):
            with self.subTest(step=k):
                self._requeue_pause(f"p{k}")
                self.conv.db.execute("PRAGMA busy_timeout = 0")
                self.inbox.db.execute("PRAGMA busy_timeout = 0")
                ctx, fired = self._after_step(k, lambda: self._worker_moves_the_pause(blocked))
                with ctx: answer = host.paused_flag(self.repo.state)
                self.assertTrue(answer)
                if not fired: break
                reached.append(k)
                self.assertTrue(host.paused_flag(self.repo.state))  # and afterwards: the worker finishes, the flag says paused
                self.work.cycle()
        self.assertGreaterEqual(len(reached), 4, reached)

    def _composed(self, k):
        """Composed: real forwarder -> sealed state question -> real host Server -> host.paused_flag -> real store, with the
        real worker moving the queued pause into the flag right after statement k of the host's read. The next owner message
        gets no 👀 and is recorded as paused."""
        self._requeue_pause("cp")
        self.conv.db.execute("PRAGMA busy_timeout = 0")
        self.inbox.db.execute("PRAGMA busy_timeout = 0")
        self.owner_text("next", "status")
        ctx, fired = self._after_step(k, lambda: self._worker_moves_the_pause([]))
        with ctx: self.f.ack()
        self.assertEqual(fired, [k])
        self.assertEqual((self.sent, self.tapped, self.spool.db.execute("SELECT state FROM ack WHERE provider_id='next'").fetchone()[0]), ([], [], "paused"))
        self.work.cycle()
        self.assertTrue(host.paused_flag(self.repo.state))

    def test_the_move_before_the_hosts_first_read_sends_no_eyes(self): self._composed(1)
    def test_the_move_after_the_read_transaction_opens_sends_no_eyes(self): self._composed(2)
    def test_the_move_after_the_queue_is_read_sends_no_eyes(self): self._composed(3)
    def test_the_move_after_the_read_transaction_closes_sends_no_eyes(self): self._composed(4)

    def test_a_flag_that_appears_between_the_two_flag_reads_is_paused(self):
        """No queued pause at all: the flag is set by a pause that was handled elsewhere. Whenever it lands during the read
        the answer is paused, and once it is there it stays paused."""
        reached, landed = [], []

        def set_flag():  # a writer that finds the store locked by the reader simply lands after it
            try:
                self.conv.db.execute("INSERT OR REPLACE INTO control(name,value,set_at,provider_id) VALUES ('paused','1','2026-11-02T17:00:00+00:00','x')")
                landed.append(1)
            except sqlite3.OperationalError: pass
        for k in range(1, 20):
            with self.subTest(step=k):
                self.conv.db.execute(conv_control())
                self.conv.db.execute("DELETE FROM control WHERE name = 'paused'")
                self.conv.db.execute("PRAGMA busy_timeout = 0")
                landed.clear()
                ctx, fired = self._after_step(k, set_flag)
                with ctx: answer = host.paused_flag(self.repo.state)
                if not fired: break
                reached.append((k, answer, bool(landed)))
                if landed: self.assertTrue(host.paused_flag(self.repo.state))
        # a flag landing after the very last statement is the only place an unpaused answer is still correct (it was unpaused
        # at both reads); every earlier boundary reports paused
        self.assertTrue(all(answer for _, answer, landed_ in reached[:-1] if landed_), reached)
        self.assertGreaterEqual(len(reached), 4, reached)


class HostPauseSignal(host_tests.HostCase):
    """host.paused_flag is what the Mac's `state` question reads: the flag, an unread pause command, or 'cannot tell'."""

    def queue(self, text, pid="q1", payload=None):
        self.inbox.db.execute("INSERT INTO inbound(provider_id, received_at, payload, state, enqueued_at) VALUES (?,?,?,?,?)",
                              (pid, "2026-11-02T17:00:00+00:00", payload or json.dumps({"text": text}), "pending", "2026-11-02T17:00:00+00:00"))

    def test_an_unread_pause_command_counts_as_paused_and_other_queued_text_does_not(self):
        self.assertFalse(host.paused_flag(self.repo.state))
        self.queue("status", "s")
        self.queue("please add eggs to the shelf", "f")
        self.queue("resume changes", "r")
        self.assertFalse(host.paused_flag(self.repo.state))
        for i, text in enumerate(("stop changes", "pause", "Pause changes.", "stop", "STOP!")):
            with self.subTest(text=text):
                self.queue(text, f"p{i}")
                self.assertTrue(host.paused_flag(self.repo.state))
                self.inbox.db.execute("DELETE FROM inbound WHERE provider_id=?", (f"p{i}",))
        self.assertFalse(host.paused_flag(self.repo.state))

    def test_a_handled_pause_command_no_longer_counts_only_the_flag_does(self):
        self.queue("stop changes", "p")
        self.inbox.db.execute("UPDATE inbound SET state='done', payload=NULL")
        self.assertFalse(host.paused_flag(self.repo.state))

    def test_an_unreadable_queued_message_counts_as_paused(self):
        self.queue("", "x", payload="not json")
        self.assertTrue(host.paused_flag(self.repo.state))
        self.inbox.db.execute("DELETE FROM inbound")
        self.queue("", "y", payload=json.dumps({"other": 1}))
        self.assertTrue(host.paused_flag(self.repo.state))

    def test_an_unreadable_inbox_or_a_missing_inbox_table_means_paused(self):
        self.assertFalse(host.paused_flag(self.repo.state))
        self.inbox.db.execute("ALTER TABLE inbound RENAME TO inbound_old")
        self.assertTrue(host.paused_flag(self.repo.state))  # the queue cannot be read: unknown is paused
        self.inbox.db.execute("ALTER TABLE inbound_old RENAME TO inbound")
        self.assertFalse(host.paused_flag(self.repo.state))
        self.inbox.db.close()
        (Path(self.repo.state) / "inbox.sqlite3").write_bytes(b"not a database")
        self.assertTrue(host.paused_flag(self.repo.state))

    def test_it_stays_read_only(self):
        self.queue("stop changes")
        before = (Path(self.repo.state) / "inbox.sqlite3").stat().st_mtime_ns
        host.paused_flag(self.repo.state)
        self.assertEqual((Path(self.repo.state) / "inbox.sqlite3").stat().st_mtime_ns, before)


class ThreadedAck(AckCase):
    """The real ack thread with real (slow) waits: the 👀 and the rest of the loop never delay each other."""

    def start(self):
        self.f.start_ack()
        self.addCleanup(self.f.stop_ack)

    def until(self, test, seconds=5.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not test(): time.sleep(0.01)
        return test()

    def test_a_slow_failing_ack_send_does_not_delay_the_post_to_the_receiver(self):
        sends = []

        def slow(chat, guid, reaction):
            sends.append(time.monotonic())
            time.sleep(1.2)
            raise bridge.BridgeError("transport-error")
        self.reactor.react = slow
        self.start()
        self.message("m1")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "m1"}}, self.now)
        started = time.monotonic()
        self.f.cycle()                                   # fetch, kick, deliver, pull in the main loop
        elapsed = time.monotonic() - started
        self.assertEqual(len(self.posts), 1)             # delivered while the ack send is still sleeping
        self.assertLess(elapsed, 0.8)
        self.assertTrue(self.until(lambda: self.states().get("m1") == "react_failed", 4))  # the failure is recorded, nothing retried
        self.assertEqual(len(sends), 1)

    def test_a_slow_reply_pull_does_not_delay_the_eyes_after_acceptance(self):
        self.start()
        accepted, sent = [], []
        original = self.spool.owner_arrived
        self.spool.owner_arrived = lambda *a: (accepted.append(time.monotonic()), original(*a))[1]
        plain = self.reactor.react
        self.reactor.react = lambda chat, guid, reaction: (sent.append(time.monotonic()), plain(chat, guid, reaction))[1]
        self.query = [self.message("poll-owner")]
        self.f.pull = lambda: time.sleep(1.5)            # a reply send / picture work that takes a while
        started = time.monotonic()
        self.f.cycle()
        cycle_took = time.monotonic() - started
        self.assertTrue(self.until(lambda: sent))
        self.assertGreaterEqual(cycle_took, 1.5)         # the slow work really ran in the main loop
        self.assertLess(sent[0] - accepted[0], 0.5)      # and the 👀 did not wait for it
        self.assertEqual(self.states(), {"poll-owner": "sent"})

    def test_a_slow_catch_up_in_the_same_cycle_does_not_delay_the_eyes_of_a_message_just_fetched(self):
        self.start()
        self.message("m1")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "m1"}}, self.now)   # a webhook announced it; fetch accepts it
        order = []
        plain = self.reactor.react
        self.reactor.react = lambda chat, guid, reaction: (order.append("ack"), plain(chat, guid, reaction))[1]

        def slow_query():
            time.sleep(0.8)
            order.append("catch-up-done")
        self.f.catch_up = slow_query
        self.f.cycle()
        self.assertTrue(self.until(lambda: self.taps()))
        self.assertEqual(order, ["ack", "catch-up-done"])

    def test_the_eyes_go_out_before_the_slow_work_returns(self):
        self.start()
        self.enqueue("m1")
        order = []
        plain = self.reactor.react
        self.reactor.react = lambda chat, guid, reaction: (order.append("ack"), plain(chat, guid, reaction))[1]

        def slow_pull():
            time.sleep(0.6)
            order.append("pull-done")
        self.f.pull = slow_pull
        self.f.cycle()
        self.assertTrue(self.until(lambda: len(order) == 2))
        self.assertEqual(order, ["ack", "pull-done"])

    # -- HASS-FAST-1-FIX item 1: a burst of owner messages, sends that take real time ------------------------------------
    def real_clock(self):
        """The test clock moves with real time, starting at the fixed test time (envelopes and ack ages need a moving clock)."""
        t0, base = time.monotonic(), self.now
        self.f.clock = self.spool.clock = lambda: base + (time.monotonic() - t0)
        return self.f.clock

    def queue_acks(self, clock, names, age=0.0):
        for name in names: self.spool.db.execute("INSERT INTO ack VALUES (?,'pending',?,NULL)", (name, clock() - age))

    def record_stages(self):
        seen = []
        self.f.stage = lambda stage, ident, **kw: seen.append((stage, ident, self.f.clock(), kw))
        return seen

    def timings(self, seen, clock0):
        """{id: (attempt delay, confirmed delay)} in seconds after the row was queued."""
        created = dict(self.spool.db.execute("SELECT provider_id,created_at FROM ack").fetchall())
        starts = {i: t - created[i] for st, i, t, _ in seen if st == "ack-start"}
        ends = {i: t - created[i] for st, i, t, _ in seen if st == "ack-end"}
        return {i: (starts[i], ends.get(i)) for i in starts}

    def test_a_burst_of_four_with_0_8_s_sends_starts_every_attempt_at_once_and_confirms_each_within_the_budget(self):
        """The reviewer's round 2 case: four owner messages accepted together, every send really takes 0.8 s. One at a time the
        attempts started at 0.13 / 0.92 / 1.71 / 2.49 s and were confirmed at 0.93 / 1.72 / 2.51 / 3.29 s."""
        clock = self.real_clock()
        seen = self.record_stages()
        plain = self.reactor.react

        def slow(chat, guid, reaction):
            time.sleep(0.8)
            plain(chat, guid, reaction)
        self.reactor.react = slow
        self.start()
        self.queue_acks(clock, ["b1", "b2", "b3", "b4"])
        self.f.ack_kick()
        self.assertTrue(self.until(lambda: len(self.states()) == 4 and set(self.states().values()) == {"sent"}, 10), self.states())
        times = self.timings(seen, clock)
        self.assertEqual(len(times), 4)
        attempts = sorted(a for a, _ in times.values())
        confirmed = sorted(c for _, c in times.values())
        self.assertLess(attempts[-1], 1.0, times)                      # every attempt started at once (0.05-0.12 s here); one send after another gives 2.4 s+
        self.assertLess(attempts[-1] - attempts[0], 0.8, times)       # ... all four together (one send after another: 0.8 s apart each)
        self.assertGreaterEqual(confirmed[0], 0.8)                     # the sends really took their 0.8 s
        self.assertLess(confirmed[-1], fwd.ACK_BUDGET, times)          # and each confirmation is inside the 2 s budget
        self.assertEqual(len(self.taps()), 4)

    def slow_sender(self, seconds):
        """A BlueBubbles stand-in whose send really takes `seconds`; the returned dict holds how many sends overlapped at most."""
        box, lock, plain = {"now": 0, "peak": 0}, threading.Lock(), self.reactor.react

        def slow(chat, guid, reaction):
            with lock: box["now"] += 1; box["peak"] = max(box["peak"], box["now"])  # noqa: E702
            try: time.sleep(seconds)
            finally:
                with lock: box["now"] -= 1
            plain(chat, guid, reaction)
        self.reactor.react = slow
        return box

    def test_twelve_messages_with_0_4_s_sends_start_side_by_side_not_one_after_another(self):
        clock = self.real_clock()
        seen = self.record_stages()
        self.slow_sender(0.4)
        self.start()
        names = [f"t{i}" for i in range(12)]
        self.queue_acks(clock, names)
        self.f.ack_kick()
        self.assertTrue(self.until(lambda: len(self.states()) == 12 and set(self.states().values()) <= {"sent", "late"}, 20), self.states())
        times = self.timings(seen, clock)
        self.assertEqual(len(times), 12)
        # side by side the last attempt starts after about 0.4 s (0.41 s here); one after another it would start after 11 x 0.4 = 4.4 s.
        # On a machine under heavy load a slow row may be recorded `late`; the bound leaves room for that and still excludes a queue.
        self.assertLess(max(a for a, _ in times.values()), 2.0, sorted(times.values()))
        self.assertEqual(len(self.taps()), 12)

    def test_the_largest_burst_one_catch_up_page_can_accept_is_worked_in_parallel_one_send_each_none_dropped(self):
        """50 at once (the catch-up page size). The sends run side by side (a serial queue never overlaps two), every message is
        decided exactly once and none is dropped. How fast the 50 start depends on the machine's disk (each worker commits to the
        spool): a row that misses the budget is recorded `late`, and that is allowed here; the timing is not asserted."""
        self.assertGreaterEqual(fwd.ACK_WORKERS, fwd.CATCH_UP_PAGE)
        clock = self.real_clock()
        box = self.slow_sender(0.4)
        self.start()
        names = [f"p{i}" for i in range(fwd.CATCH_UP_PAGE)]
        self.queue_acks(clock, names)
        self.f.ack_kick()
        self.assertTrue(self.until(lambda: len(self.states()) == len(names) and set(self.states().values()) <= {"sent", "late"} and len(self.taps()) == len(names), 30), set(self.states().values()))
        time.sleep(0.3)
        self.assertEqual(len(self.taps()), len(names))   # one each, never two
        self.assertGreaterEqual(box["peak"], 4, box)  # a serial queue peaks at 1

    def test_an_ack_whose_budget_has_passed_is_sent_but_recorded_late_not_as_a_success(self):
        clock = self.real_clock()
        self.queue_acks(clock, ["old"], age=fwd.ACK_BUDGET + 1)       # waited 3 s before anything looked at it
        self.f.ack()
        self.assertEqual(self.states(), {"old": "late"})
        self.assertEqual(len(self.taps()), 1)                          # not dropped silently: it still goes out, once
        self.f.ack()
        self.assertEqual(len(self.taps()), 1)
        self.queue_acks(clock, ["slow"])
        plain = self.reactor.react
        self.reactor.react = lambda chat, guid, reaction: (time.sleep(0.5), plain(chat, guid, reaction))[1]
        with mock.patch.object(fwd, "ACK_BUDGET", 0.3):               # attempted at once, but confirmed after the budget
            self.f.ack()
        self.assertEqual(self.states(), {"old": "late", "slow": "late"})
        self.queue_acks(clock, ["ontime"])
        self.reactor.react = plain
        self.f.ack()
        self.assertEqual(self.states()["ontime"], "sent")
        self.queue_acks(clock, ["ancient"], age=fwd.ACK_STALE + 1)    # past the outer limit: recorded stale, not sent
        before = len(self.taps())
        self.f.ack()
        self.assertEqual((self.states()["ancient"], len(self.taps())), ("stale", before))

    def test_a_late_ack_is_visible_in_the_stage_log_outcome(self):
        clock = self.real_clock()
        seen = self.record_stages()
        self.queue_acks(clock, ["old"], age=fwd.ACK_BUDGET + 1)
        self.f.ack()
        self.assertEqual([(st, kw) for st, _, _, kw in seen if st == "ack-end"], [("ack-end", {"outcome": "late"})])

    def test_more_pending_acks_than_workers_are_all_still_decided_none_dropped(self):
        clock = self.real_clock()
        with mock.patch.object(fwd, "ACK_WORKERS", 2):
            self.start()
            self.queue_acks(clock, [f"w{i}" for i in range(7)])
            self.f.ack_kick()
            self.assertTrue(self.until(lambda: len(self.states()) == 7 and set(self.states().values()) <= {"sent", "late"} and len(self.taps()) == 7, 10), self.states())
        self.assertEqual(len(self.taps()), 7)

    def test_a_row_left_checking_by_a_dead_worker_is_retried_once_after_a_while_and_a_fresh_one_is_left_alone(self):
        clock = self.real_clock()
        self.spool.db.execute("INSERT INTO ack VALUES ('dead','checking',?,?)", (clock(), clock() - fwd.ACK_CLAIM_STALE - 1))
        self.spool.db.execute("INSERT INTO ack VALUES ('busy','checking',?,?)", (clock(), clock()))
        self.start()
        self.f.ack_kick()
        self.assertTrue(self.until(lambda: self.states().get("dead") == "sent"))
        time.sleep(0.3)
        self.assertEqual((self.states()["busy"], len(self.taps())), ("checking", 1))

    def test_two_threads_one_spool_still_one_ack_per_message(self):
        other = fwd.Spool(self.root, self.now)
        self.addCleanup(other.db.close)
        second = fwd.Forwarder(self.cfg, other, lambda: self.now, self.transport, self.sender, reactor=self.reactor)
        for fw in (self.f, second): fw.start_ack()
        self.addCleanup(second.stop_ack)
        self.addCleanup(self.f.stop_ack)
        for i in range(12): self.enqueue(f"m{i}")
        for fw in (self.f, second): fw.ack_kick()
        self.assertTrue(self.until(lambda: set(self.states().values()) == {"sent"} and len(self.states()) == 12))
        time.sleep(0.3)
        self.assertEqual(len(self.taps()), 12)

    def test_heavy_main_loop_writes_and_the_ack_thread_share_the_spool_without_loss(self):
        self.start()
        for i in range(25):
            self.message(f"m{i}")
            # Doorbells arrive one after another, as in life: with a fixed test clock they would all carry the ack's own time,
            # and the (intended) rule "an earlier unresolved doorbell may hide a pause command, so no 👀 yet" would then
            # randomly close some acks as `paused` depending on thread timing.
            self.spool.doorbell({"type": "new-message", "data": {"guid": f"m{i}"}}, self.now + i)
        for _ in range(60):
            self.f.cycle()
            if self.pending() == 0 and not self.spool.db.execute("SELECT 1 FROM fetch").fetchone(): break
        self.assertTrue(self.until(lambda: len(self.states()) == 25 and set(self.states().values()) == {"sent"}, 20))
        self.assertEqual((len(self.taps()), len(self.posts)), (25, 25))

    def test_a_burst_is_worked_off_by_one_wake_up_not_one_tick_per_three_rows(self):
        for i in range(12): self.enqueue(f"b{i}")
        with mock.patch.object(fwd, "ACK_TICK", 60):    # the timer never fires: only the one kick wakes the thread
            self.start()
            self.f.ack_kick()
            self.assertTrue(self.until(lambda: len(self.taps()) == 12 and set(self.states().values()) == {"sent"}, 20))

    def test_the_thread_survives_a_broken_table_and_a_raising_sender(self):
        self.start()
        real = self.reactor.react
        self.reactor.react = mock.Mock(side_effect=RuntimeError("boom"))
        self.enqueue("a")
        self.f.ack_kick()
        self.assertTrue(self.until(lambda: self.states().get("a") == "react_failed"))
        self.reactor.react = real
        self.enqueue("b")
        self.f.ack_kick()
        self.assertTrue(self.until(lambda: self.states().get("b") == "sent"))
        self.assertTrue(self.f.ack_thread.is_alive())

    def test_stop_ends_the_thread_and_start_is_idempotent(self):
        self.f.start_ack()
        first = self.f.ack_thread
        self.f.start_ack()
        self.assertIs(self.f.ack_thread, first)
        self.f.stop_ack()
        self.assertFalse(first.is_alive())
        self.assertIsNone(self.f.ack_thread)

    def test_without_a_thread_kick_runs_the_ack_inline(self):
        self.enqueue("m1")
        self.f.ack_kick()
        self.assertEqual(len(self.taps()), 1)

    def test_the_state_question_and_the_ack_send_have_their_own_short_timeouts(self):
        seen = []

        class Opener:
            def open(self, req, timeout=None):
                seen.append(timeout)
                raise OSError("down")
        with mock.patch.object(bridge, "_OPENER", Opener()):
            f = fwd.Forwarder(self.cfg, self.spool, lambda: self.now, fwd.request_json, self.sender)
            self.assertIsNone(f.host_paused(self.spool))
            with self.assertRaises(bridge.BridgeError): f.transport("http://127.0.0.1:1/x")
        self.assertEqual(seen, [fwd.ACK_STATE_TIMEOUT, 10])
        self.assertLessEqual(fwd.ACK_STATE_TIMEOUT + fwd.ACK_TIMEOUT, 2.0)  # the worst one attempt can take, state question plus send


class StageLog(unittest.TestCase):
    def test_lines_carry_only_a_time_a_stage_name_and_a_hashed_id(self):
        with tempfile.TemporaryDirectory() as d:
            log = stagelog.StageLog(Path(d) / "s.jsonl", clock=lambda: 12.3456)
            log("accepted", "SECRET-GUID-123", rid="r")
            raw = (Path(d) / "s.jsonl").read_text()
            self.assertNotIn("SECRET", raw)
            row = json.loads(raw)
            self.assertEqual((row["t"], row["stage"], row["id"], row["rid"]), (12.346, "accepted", stagelog.short("SECRET-GUID-123"), "r"))
            self.assertEqual(len(row["id"]), 12)
            self.assertEqual(oct(os.stat(Path(d) / "s.jsonl").st_mode & 0o777), "0o600")

    def test_logging_never_raises(self):
        for path in ("/nonexistent-dir/x.jsonl", "", None, "/proc/self/mem"):
            stagelog.StageLog(path)("accepted", "x")
        stagelog.StageLog("/tmp/x", clock=lambda: 1 / 0)("accepted", "x")
        stagelog.off("a", "b", c=1)

    def test_the_file_stops_growing_past_the_cap(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.jsonl"
            path.write_bytes(b"x" * (stagelog.MAX_BYTES + 1))
            stagelog.StageLog(path)("accepted", "x")
            self.assertTrue((Path(d) / "s.jsonl.1").exists())
            self.assertLess(path.stat().st_size, 200)

    def test_table_joins_the_mac_and_host_lines_through_the_reply_id(self):
        m, r = "msg", "reply"
        rows = [dict(t=100.0, stage="webhook-in", id=stagelog.short(m)), dict(t=100.1, stage="accepted", id=stagelog.short(m)),
                dict(t=100.4, stage="ack-end", id=stagelog.short(m)), dict(t=101.0, stage="worker-pickup", id=stagelog.short(m)),
                dict(t=160.0, stage="reply-queued", id=stagelog.short(m), rid=stagelog.short(r)),
                dict(t=161.0, stage="reply-pulled", id=stagelog.short(r)), dict(t=162.5, stage="bb-send-end", id=stagelog.short(r))]
        (ident, stages), = stagelog.table(rows)
        self.assertEqual(ident, stagelog.short(m))
        self.assertEqual(stages, {"webhook-in": 0.0, "accepted": 0.1, "ack-end": 0.4, "worker-pickup": 1.0, "reply-queued": 60.0,
                                  "reply-pulled": 61.0, "bb-send-end": 62.5})

    @staticmethod
    def deep_json_lines():
        # Real decoder failures at the unchanged recursion limit, not mocked exceptions.
        return ("[" * 20000 + '"REJECTED-CANARY"' + "]" * 20000,
                '{"nested":' * 20000 + '"REJECTED-CANARY"' + "}" * 20000)

    def stage_cli(self, *paths):
        import subprocess
        import sys
        return subprocess.run([sys.executable, "-B", str(Path(stagelog.__file__).resolve()),
                               *map(str, paths)], capture_output=True, text=True, timeout=10)

    def test_read_skips_overdeep_json_between_valid_rows(self):
        rows = [dict(t=1, stage="accepted", id="x"), dict(t=2, stage="handled", id="x")]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.jsonl"
            for deep in self.deep_json_lines():
                with self.subTest(kind=deep[0]):
                    with self.assertRaises(RecursionError):
                        json.loads(deep)
                    raw = (json.dumps(rows[0]) + "\nnot json\n[1]\n" + deep + "\n"
                           + json.dumps(rows[1]) + '\n{"t":"x"}\n').encode()
                    path.write_bytes(raw)
                    self.assertEqual(stagelog.read(path), rows)
                    self.assertEqual(path.read_bytes(), raw)

    def test_cli_keeps_valid_stages_around_deep_line(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.jsonl"
            for deep in self.deep_json_lines():
                with self.subTest(kind=deep[0]):
                    raw = ('{"t":1,"stage":"accepted","id":"x"}\n' + deep
                           + '\n{"t":2,"stage":"handled","id":"x"}\n').encode()
                    path.write_bytes(raw)
                    result = self.stage_cli(path)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, "x accepted=0 handled=1\n", ""))
                    self.assertEqual(path.read_bytes(), raw)

    def test_cli_merges_healthy_second_file_after_bad_first_file(self):
        with tempfile.TemporaryDirectory() as d:
            first, second = Path(d) / "first.jsonl", Path(d) / "second.jsonl"
            raw_first = ('{"t":1,"stage":"accepted","id":"x"}\n'
                         + self.deep_json_lines()[0] + "\n").encode()
            raw_second = (b'{"t":2,"stage":"handled","id":"x"}\n'
                          b'{"t":4,"stage":"reply-queued","id":"x","rid":"r"}\n'
                          b'{"t":6,"stage":"reply-pulled","id":"r"}\n')
            first.write_bytes(raw_first)
            second.write_bytes(raw_second)
            result = self.stage_cli(first, second)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (0, "x accepted=0 handled=1 reply-queued=3 reply-pulled=5\n", ""))
            self.assertEqual(first.read_bytes(), raw_first)
            self.assertEqual(second.read_bytes(), raw_second)

    def test_deep_only_log_remains_successfully_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.jsonl"
            raw = ("\n".join(self.deep_json_lines()) + "\n").encode()
            path.write_bytes(raw)
            self.assertEqual(stagelog.read(path), [])
            result = self.stage_cli(path)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(d).iterdir()), [path])

    def test_read_skips_junk_lines(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "s.jsonl").write_text('{"t": 1, "stage": "a", "id": "x"}\nnot json\n[1]\n{"t": "x"}\n')
            self.assertEqual(len(stagelog.read(Path(d) / "s.jsonl")), 1)
            self.assertEqual(stagelog.read(Path(d) / "missing"), [])


if __name__ == "__main__":
    unittest.main()
