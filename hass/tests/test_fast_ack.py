"""HASS-FAST-1 tests: the 👀 ack on the Mac forwarder (one per owner message, never a stranger / group / echo / edit /
old message, never while paused or unknown, never blocks), the host `state` op, and the read-only stage log.
Synthetic only: fake BlueBubbles, fake sender, loopback sockets on port 0, temp dirs. No Mac, no real message.
Run: python3 -B -m unittest hass.tests.test_fast_ack"""
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

NOW, EYES = ft.NOW, "\N{EYES}"


class AckCase(ft.ForwarderCase):
    def setUp(self):
        super().setUp()
        self.order, self.state_asked = [], 0
        self.sender.send = self._send
        self.host_ok()

    def _send(self, chat, text, attachments=()):
        if self.sender.fail: raise bridge.BridgeError("transport-error")
        self.sender.calls.append((chat, text, attachments))
        self.order.append("ack" if text == EYES else "reply")

    def host_ok(self, paused=False): self.answer = paused  # what the fake host says to the next `state` question; None: unreachable

    def transport(self, url, body=None):
        if url.endswith("/v1/relay") and relay.unseal_control(body, ft.KEY, now=self.now, seen=set())["op"] == "state":
            self.state_asked += 1
            if self.answer is None: raise bridge.BridgeError("transport-error")
            return relay.seal_control({"op": "state", "paused": self.answer}, ft.KEY, nonce=os.urandom(16).hex(), now=self.now)
        return super().transport(url, body)

    def eyes(self): return [c for c in self.sender.calls if c[1] == EYES]

    def states(self): return dict(self.spool.db.execute("SELECT provider_id,state FROM ack").fetchall())


class WhoGetsAnAck(AckCase):
    def test_owner_message_gets_one_eyes_before_the_receiver_is_involved(self):
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual(self.sender.calls, [(OWNER_CHAT, EYES, ())])
        self.assertEqual((self.posts, self.states()), ([], {"m1": "sent"}))  # nothing posted to the receiver yet
        self.f.ack()
        self.f.deliver()
        self.f.ack()
        self.assertEqual((len(self.eyes()), len(self.posts)), (1, 1))

    def test_stranger_sender_in_the_owner_chat_gets_no_ack_but_is_still_forwarded_as_before(self):
        self.enqueue("s", handle={"address": STRANGER})
        self.f.ack()
        self.assertEqual((self.sender.calls, self.states()), ([], {}))
        self.f.deliver()
        self.assertEqual([e["body"]["sender"] for e in self.posts], [STRANGER])  # the host, not the Mac, rules on strangers

    def test_other_chat_group_unknown_sender_echo_edit_and_reaction_get_no_ack(self):
        self.enqueue("other", chats=[{"guid": "iMessage;-;stranger@example.invalid"}])
        self.enqueue("group", chats=[{"guid": "iMessage;+;group"}])
        self.enqueue("echo", isFromMe=True)  # Hass's own message, including its own 👀
        self.enqueue("nohandle", handle=None)
        self.enqueue("react", associatedMessageType="love")
        self.enqueue("lookalike", handle={"address": "owner@example.invalid.evil"})
        edit = self.message("edit", dateEdited=int(self.now * 1000))
        self.spool.accept({"type": "updated-message", "data": edit}, OWNER_CHAT, self.now)
        self.f.ack()
        self.assertEqual((self.sender.calls, self.states()), ([], {}))

    def test_sender_spelling_is_compared_like_the_host_does(self):
        self.enqueue("case", handle={"address": "Owner@Example.INVALID"})
        self.f.ack()
        self.assertEqual(len(self.eyes()), 1)

    def test_attachment_only_owner_message_is_acked_too(self):
        self.enqueue("pic", text="\ufffc", attachments=[{"guid": "a1"}])
        self.f.ack()
        self.assertEqual(len(self.eyes()), 1)

    def test_a_message_found_late_by_catch_up_is_stored_but_never_acked(self):
        self.now += 600
        self.message("late")
        self.messages["late"]["dateCreated"] = int((NOW + 10) * 1000)  # sent 590 s ago, found now
        self.spool.doorbell({"type": "new-message", "data": {"guid": "late"}}, self.now)
        self.f.fetch()
        self.f.ack()
        self.assertEqual((self.sender.calls, self.pending()), ([], 1))

    def test_an_ack_that_waited_too_long_is_dropped_not_sent_late(self):
        self.enqueue("m1")
        self.now += fwd.ACK_STALE + 1
        self.f.ack()
        self.assertEqual((self.sender.calls, self.states()), ([], {"m1": "stale"}))


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
        restarted = fwd.Forwarder(self.cfg, reopened, lambda: self.now, self.transport, self.sender)
        self.spool.accept({"type": "new-message", "data": self.messages["m1"]}, OWNER_CHAT, self.now)
        reopened.accept({"type": "new-message", "data": self.messages["m1"]}, OWNER_CHAT, self.now)
        restarted.ack()
        self.assertEqual((len(self.eyes()), self.spool.db.execute("SELECT COUNT(*) FROM ack").fetchone()[0]), (1, 1))

    def test_a_crash_between_claim_and_send_never_sends_the_ack_again(self):
        self.enqueue("m1")
        self.spool.db.execute("UPDATE ack SET state='sending'")  # the process died inside the send
        self.f.ack()
        self.assertEqual(self.sender.calls, [])

    def test_a_pending_ack_survives_a_restart_and_is_sent_once(self):
        self.enqueue("m1")
        reopened = fwd.Spool(self.root, self.now)
        self.addCleanup(reopened.db.close)
        restarted = fwd.Forwarder(self.cfg, reopened, lambda: self.now, self.transport, self.sender)
        restarted.ack()
        restarted.ack()
        self.assertEqual(len(self.eyes()), 1)

    def test_two_messages_two_acks(self):
        self.enqueue("a")
        self.enqueue("b")
        self.f.ack()
        self.assertEqual(len(self.eyes()), 2)


class NotWhenPausedOrUnknown(AckCase):
    def test_no_host_answer_means_no_ack_now_and_never_a_late_one(self):
        self.host_ok(None)
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual((self.sender.calls, self.states()), ([], {"m1": "unknown"}))
        self.host_ok(False)  # the host is back a moment later: still not sent (fail closed, not late)
        self.f.ack()
        self.assertEqual(self.sender.calls, [])

    def test_the_host_is_asked_fresh_for_every_ack_nothing_is_cached(self):
        self.enqueue("a")
        self.f.ack()
        self.host_ok(True)                   # paused between two messages, with no poll in between
        self.enqueue("b")
        self.f.ack()
        self.host_ok(False)
        self.enqueue("c")
        self.f.ack()
        self.assertEqual((self.state_asked, len(self.eyes()), self.states()), (3, 2, {"a": "sent", "b": "paused", "c": "sent"}))

    def test_paused_host_means_no_ack_at_all(self):
        self.host_ok(paused=True)
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual((self.sender.calls, self.states()), ([], {"m1": "paused"}))
        self.host_ok(paused=False)
        self.f.ack()
        self.assertEqual(self.sender.calls, [])  # the closed row is not reopened

    def test_a_pause_command_stored_here_and_not_yet_handed_to_the_host_blocks_it_and_everything_after_it(self):
        asked = self.state_asked
        for text in ("stop changes", "pause", "Pause changes.", "stop", "STOP!"):
            with self.subTest(text=text):
                self.sender.calls.clear()
                self.enqueue("c" + text[:3], text=text)
                self.enqueue("after" + text[:3])
                self.f.ack()
                self.assertEqual(self.sender.calls, [])
                self.spool.db.execute("UPDATE inbound SET state='done',payload=NULL")  # handed to the host; the host's queue takes over
        self.assertEqual(self.state_asked, asked)  # all ten are stopped here, before the host is even asked

    def test_a_message_that_cannot_be_read_counts_as_a_pause_ahead(self):
        self.enqueue("a")
        self.spool.db.execute("UPDATE inbound SET payload='not json' WHERE provider_id='a'")
        self.enqueue("b")
        self.f.ack()
        self.assertEqual(self.sender.calls, [])

    def test_an_earlier_unresolved_doorbell_holds_the_ack_but_not_a_later_one(self):
        def accept(guid):
            self.spool.accept({"type": "new-message", "data": self.message(guid)}, OWNER_CHAT, self.now)
        accept("m1")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "earlier"}}, self.now - 1)  # its fetch keeps failing: content unknown
        self.f.ack()
        self.assertEqual((self.sender.calls, self.states()), ([], {"m1": "paused"}))
        self.spool.db.execute("DELETE FROM fetch")
        accept("m2")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "later"}}, self.now + 5)
        self.f.ack()
        self.assertEqual(len(self.eyes()), 1)

    def test_a_status_or_free_text_message_does_not_hold_the_ack(self):
        for text in ("status", "resume changes", "Stop showing the eggs as sold out"):
            with self.subTest(text=text):
                self.sender.calls.clear()
                self.enqueue("m" + str(len(text)), text=text)
                self.f.ack()
                self.assertEqual(len(self.eyes()), 1)

    def test_switched_off_by_config(self):
        self.f.cfg = {**self.cfg, "ack": False}
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual((self.sender.calls, self.states(), self.pending(), self.state_asked), ([], {"m1": "off"}, 1, 0))

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
        self.assertEqual((self.sender.calls, self.states()), ([], {"m1": "unknown"}))


class AckNeverBlocks(AckCase):
    def test_send_failure_is_recorded_not_retried_and_the_message_still_goes_through(self):
        self.enqueue("m1")
        self.sender.fail = True
        self.f.ack()                       # does not raise
        self.sender.fail = False
        self.f.ack()
        self.f.deliver()
        self.assertEqual((self.states(), self.sender.calls, len(self.posts)), ({"m1": "failed"}, [], 1))

    def test_any_error_type_from_the_sender_is_swallowed(self):
        self.enqueue("m1")
        self.sender.send = mock.Mock(side_effect=RuntimeError("boom"))
        self.f.ack()
        self.assertEqual(self.states(), {"m1": "failed"})

    def test_a_broken_ack_table_never_loses_the_message(self):
        self.spool.db.execute("DROP TABLE ack")
        self.enqueue("m1")
        with contextlib.redirect_stderr(io.StringIO()):
            self.f.ack()
            self.f.deliver()
        self.assertEqual(len(self.posts), 1)

    def test_the_default_ack_sender_clamps_the_blocking_time(self):
        seen = []
        with mock.patch.object(bridge, "_urllib_transport", side_effect=lambda u, b, h, t: seen.append(t) or 200):
            f = fwd.Forwarder(self.cfg, self.spool, lambda: self.now, self.transport)
            f.acker.send(OWNER_CHAT, EYES)
            f.sender.send(OWNER_CHAT, "reply")
        self.assertEqual(seen, [fwd.ACK_TIMEOUT, bridge.SEND_TIMEOUT])

    def test_the_ack_text_is_exactly_one_eyes_emoji(self):
        self.assertEqual((fwd.ACK_TEXT, len(fwd.ACK_TEXT)), (EYES, 1))


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

    def test_ackcheck_is_read_only_and_always_names_text(self):
        for info, possible in (({"private_api": False, "helper_connected": False}, False), ({"private_api": True, "helper_connected": False}, False),
                               ({"private_api": True, "helper_connected": True}, True), ({}, False)):
            with self.subTest(info=info), mock.patch.object(fwd, "request_json", return_value={"data": info}) as rj, \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(fwd.main(["ackcheck", "--config", str(self.config)]), 0)
            (url,), kwargs = rj.call_args
            self.assertTrue(url.startswith("http://127.0.0.1:1234/api/v1/server/info?password="))
            self.assertEqual(kwargs, {})  # a GET: no body
            self.assertEqual(json.loads(out.getvalue()),
                             {"ackMethod": "text", "helperConnected": bool(info.get("helper_connected")),
                              "privateApi": bool(info.get("private_api")), "tapbackPossible": possible})

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
        self.sent, self.messages = [], {}
        sender = mock.Mock()
        sender.send.side_effect = lambda chat, text, att=(): self.sent.append(text)
        self.log = stagelog.StageLog(self.root / "stages.jsonl", clock=self.t)
        self.f = fwd.Forwarder(self.cfg, self.spool, self.t, self.transport, sender, stage=self.log)
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
        self.assertEqual((self.sent, self.relay_rows()), ([EYES], []))  # 👀 out; the receiver has seen nothing yet
        self.f.deliver()
        self.assertEqual(len(self.inbound_rows()), 1)
        self.now += timedelta(seconds=1)
        self.work.cycle()
        self.f.pull()
        self.assertEqual(self.sent[0], EYES)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(len(self.drafts()), 1)  # the normal draft path is unchanged
        self.assertEqual(self.f.pull() or len(self.sent), 2)  # nothing more to send, no second 👀
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
        self.assertEqual(self.sent.count(EYES), 1)
        self.now += timedelta(seconds=1)
        self.owner_text("p", "stop changes")
        self.go()                                   # the pause command is read by the host in this step; it gets no 👀 itself
        self.assertEqual(self.sent.count(EYES), 1)
        self.assertTrue(host.paused_flag(self.repo.state))
        before = self.sent.count(EYES)
        self.owner_text("b", "status")
        self.go()
        self.assertEqual(self.sent.count(EYES), before)  # paused: seen by nobody, still answered
        self.assertTrue(any("paused" in s.lower() for s in self.sent))
        self.owner_text("r", "resume changes")
        self.go()
        self.assertFalse(host.paused_flag(self.repo.state))
        self.now += timedelta(seconds=1)
        self.owner_text("c", "status")
        self.go()
        self.assertEqual(self.sent.count(EYES), before + 1)
        self.owner_text("c", "status")              # the same message again (webhook, catch-up, replay)
        self.go()
        self.assertEqual(self.sent.count(EYES), before + 1)

    def test_pause_set_on_the_host_between_two_polls_stops_the_next_eyes_at_once(self):
        """The reviewer's case: the last answer was 'not paused', then the pause lands on the real host store, then a fresh owner
        message is accepted before anything else polls. No cached answer exists, so the host is asked again and says paused."""
        self.owner_text("a", "status")
        self.f.ack()
        self.assertEqual(self.sent, [EYES])
        self.conv.db.execute(conv_control())
        self.conv.db.execute("INSERT INTO control(name,value,set_at,provider_id) VALUES ('paused','1','2026-11-02T17:00:00+00:00','synthetic')")
        self.assertTrue(host.paused_flag(self.repo.state))
        self.owner_text("after-pause", "status")
        self.f.ack()
        self.assertEqual(self.sent, [EYES])
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
        self.assertEqual(self.sent, [EYES])        # only the 'slow' one, sent before the pause command existed
        self.assertEqual(self.spool.db.execute("SELECT state FROM ack WHERE provider_id='next'").fetchone()[0], "paused")

    def test_a_failed_state_question_means_no_eyes_even_after_an_unpaused_answer(self):
        self.owner_text("a", "status")
        self.f.ack()
        self.owner_text("b", "status")
        with mock.patch.object(self.f, "quick", side_effect=bridge.BridgeError("transport-error")):
            self.f.ack()
        self.assertEqual(self.sent, [EYES])
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
        self.assertEqual(self.sent.count(EYES), 1)

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
        self.assertEqual((self.sent, self.spool.db.execute("SELECT state FROM ack WHERE provider_id='next'").fetchone()[0]), ([], "paused"))
        self.work.cycle()
        self.assertTrue(host.paused_flag(self.repo.state))

    def test_the_move_before_the_hosts_first_read_sends_no_eyes(self): self._composed(1)
    def test_the_move_after_the_read_transaction_opens_sends_no_eyes(self): self._composed(2)
    def test_the_move_after_the_queue_is_read_sends_no_eyes(self): self._composed(3)
    def test_the_move_after_the_read_transaction_closes_sends_no_eyes(self): self._composed(4)

    def test_a_flag_that_appears_between_the_two_flag_reads_is_paused(self):
        """No queued pause at all: the flag is set by a pause that was handled elsewhere. Whenever it lands during the read
        the answer is paused, and once it is there it stays paused."""
        reached = []

        landed = []

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

        def slow(chat, text, attachments=()):
            sends.append(time.monotonic())
            time.sleep(1.2)
            raise bridge.BridgeError("transport-error")
        self.sender.send = slow
        self.start()
        self.message("m1")
        self.spool.doorbell({"type": "new-message", "data": {"guid": "m1"}}, self.now)
        started = time.monotonic()
        self.f.cycle()                                   # fetch, kick, deliver, pull in the main loop
        elapsed = time.monotonic() - started
        self.assertEqual(len(self.posts), 1)             # delivered while the ack send is still sleeping
        self.assertLess(elapsed, 0.8)
        self.assertTrue(self.until(lambda: self.states().get("m1") == "failed", 4))  # the failure is recorded, nothing retried
        self.assertEqual(len(sends), 1)

    def test_a_slow_reply_pull_does_not_delay_the_eyes_after_acceptance(self):
        self.start()
        accepted, sent = [], []
        original = self.spool.owner_arrived
        self.spool.owner_arrived = lambda *a: (accepted.append(time.monotonic()), original(*a))[1]
        plain = self.sender.send
        self.sender.send = lambda chat, text, attachments=(): (sent.append(time.monotonic()) if text == EYES else None, plain(chat, text, attachments))[1]
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
        plain = self.sender.send
        self.sender.send = lambda chat, text, attachments=(): (order.append("ack"), plain(chat, text, attachments))[1]

        def slow_query():
            time.sleep(0.8)
            order.append("catch-up-done")
        self.f.catch_up = slow_query
        self.f.cycle()
        self.assertTrue(self.until(lambda: self.eyes()))
        self.assertEqual(order, ["ack", "catch-up-done"])

    def test_the_eyes_go_out_before_the_slow_work_returns(self):
        self.start()
        self.enqueue("m1")
        order = []
        plain = self.sender.send
        self.sender.send = lambda chat, text, attachments=(): (order.append("ack"), plain(chat, text, attachments))[1]

        def slow_pull():
            time.sleep(0.6)
            order.append("pull-done")
        self.f.pull = slow_pull
        self.f.cycle()
        self.assertTrue(self.until(lambda: len(order) == 2))
        self.assertEqual(order, ["ack", "pull-done"])

    def test_two_threads_one_spool_still_one_ack_per_message(self):
        other = fwd.Spool(self.root, self.now)
        self.addCleanup(other.db.close)
        second = fwd.Forwarder(self.cfg, other, lambda: self.now, self.transport, self.sender)
        for fw in (self.f, second): fw.start_ack()
        self.addCleanup(second.stop_ack)
        self.addCleanup(self.f.stop_ack)
        for i in range(12): self.enqueue(f"m{i}")
        for fw in (self.f, second): fw.ack_kick()
        self.assertTrue(self.until(lambda: set(self.states().values()) == {"sent"} and len(self.states()) == 12))
        time.sleep(0.3)
        self.assertEqual(len(self.eyes()), 12)

    def test_heavy_main_loop_writes_and_the_ack_thread_share_the_spool_without_loss(self):
        self.start()
        for i in range(25):
            self.message(f"m{i}")
            self.spool.doorbell({"type": "new-message", "data": {"guid": f"m{i}"}}, self.now)
        for _ in range(60):
            self.f.cycle()
            if self.pending() == 0: break
        self.assertTrue(self.until(lambda: len(self.states()) == 25 and set(self.states().values()) == {"sent"}, 20))
        self.assertEqual((len(self.eyes()), len(self.posts)), (25, 25))

    def test_a_burst_is_worked_off_by_one_wake_up_not_one_tick_per_three_rows(self):
        for i in range(12): self.enqueue(f"b{i}")
        with mock.patch.object(fwd, "ACK_TICK", 60):    # the timer never fires: only the one kick wakes the thread
            self.start()
            self.f.ack_kick()
            self.assertTrue(self.until(lambda: len(self.eyes()) == 12 and set(self.states().values()) == {"sent"}, 20))

    def test_the_thread_survives_a_broken_table_and_a_raising_sender(self):
        self.start()
        self.sender.send = mock.Mock(side_effect=RuntimeError("boom"))
        self.enqueue("a")
        self.f.ack_kick()
        self.assertTrue(self.until(lambda: self.states().get("a") == "failed"))
        self.sender.send = self._send
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
        self.assertEqual(len(self.eyes()), 1)

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

    def test_read_skips_junk_lines(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "s.jsonl").write_text('{"t": 1, "stage": "a", "id": "x"}\nnot json\n[1]\n{"t": "x"}\n')
            self.assertEqual(len(stagelog.read(Path(d) / "s.jsonl")), 1)
            self.assertEqual(stagelog.read(Path(d) / "missing"), [])


if __name__ == "__main__":
    unittest.main()
