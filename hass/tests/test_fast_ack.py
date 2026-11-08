"""HASS-FAST-1 tests: the 👀 ack on the Mac forwarder (one per owner message, never a stranger / group / echo / edit /
old message, never while paused or unknown, never blocks), the host `state` op, and the read-only stage log.
Synthetic only: fake BlueBubbles, fake sender, loopback sockets on port 0, temp dirs. No Mac, no real message.
Run: python3 -B -m unittest hass.tests.test_fast_ack"""
import contextlib, io, json, os, sqlite3, tempfile, threading, unittest  # noqa: E401
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
        self.order = []
        self.sender.send = self._send
        self.host_ok()

    def _send(self, chat, text, attachments=()):
        if self.sender.fail: raise bridge.BridgeError("transport-error")
        self.sender.calls.append((chat, text, attachments))
        self.order.append("ack" if text == EYES else "reply")

    def host_ok(self, paused=False): self.f.paused, self.f.paused_at = paused, self.now

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
        self.host_ok()
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
        restarted.paused, restarted.paused_at = False, self.now
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
        restarted.paused, restarted.paused_at = False, self.now
        restarted.ack()
        restarted.ack()
        self.assertEqual(len(self.eyes()), 1)

    def test_two_messages_two_acks(self):
        self.enqueue("a")
        self.enqueue("b")
        self.f.ack()
        self.assertEqual(len(self.eyes()), 2)


class NotWhenPausedOrUnknown(AckCase):
    def test_no_host_answer_yet_waits_then_drops(self):
        self.f.paused = None
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual((self.sender.calls, self.states()), ([], {"m1": "pending"}))
        self.f.paused, self.f.paused_at = False, self.now  # the host answers in time: sent
        self.f.ack()
        self.assertEqual(len(self.eyes()), 1)

    def test_a_host_answer_older_than_the_ttl_is_no_answer(self):
        self.enqueue("m1")
        self.now += fwd.STATE_TTL + 1
        self.spool.db.execute("UPDATE ack SET created_at=?", (self.now,))
        self.f.ack()
        self.assertEqual(self.sender.calls, [])

    def test_paused_host_means_no_ack_at_all(self):
        self.host_ok(paused=True)
        self.enqueue("m1")
        self.f.ack()
        self.assertEqual((self.sender.calls, self.states()), ([], {"m1": "paused"}))
        self.host_ok(paused=False)
        self.f.ack()
        self.assertEqual(self.sender.calls, [])  # the closed row is not reopened

    def test_the_owners_own_pause_command_holds_the_ack_before_the_host_has_read_it(self):
        for text in ("stop changes", "pause", "Pause changes.", "stop"):
            with self.subTest(text=text):
                self.sender.calls.clear()
                self.now += fwd.PAUSE_HOLD + 1
                self.host_ok()
                self.enqueue("c" + text[:3] + str(self.now), text=text)
                self.enqueue("after" + str(self.now))
                self.f.ack()
                self.assertEqual(self.sender.calls, [])
        self.now += fwd.PAUSE_HOLD + 1
        self.host_ok()
        self.enqueue("later")
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
        self.assertEqual((self.sender.calls, self.states(), self.pending()), ([], {"m1": "off"}, 1))

    def test_state_poll_reads_the_host_answer_and_failures_leave_it_unknown(self):
        self.f.paused = None
        with mock.patch.object(self.f, "control", return_value={"op": "state", "paused": False}):
            self.f.state()
        self.assertEqual((self.f.paused, self.f.paused_at), (False, self.now))
        self.f.paused = None
        for bad in (bridge.BridgeError("transport-error"), ValueError("relay-op"), KeyError("paused"),
                    bridge.EnvelopeError("mac")):
            with mock.patch.object(self.f, "control", side_effect=bad):
                self.f.state()
            self.assertIsNone(self.f.paused)
        with mock.patch.object(self.f, "control", return_value={"op": "state", "paused": "no"}):
            self.f.state()
        self.assertIsNone(self.f.paused)


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
        self.f.paused = None
        self.cycle_control = lambda body, expected, big=False: (
            {"op": "state", "paused": False} if body["op"] == "state" else {"op": "replies", "items": []})
        orig = self.transport

        def transport(url, body=None):
            if url.endswith("/v1/inbound"): self.order.append("post")
            return orig(url, body)
        self.f.transport = transport

    def test_one_cycle_fetches_acks_then_posts_in_that_order(self):
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
        self.f.state()
        self.f.ack()
        self.f.deliver()
        self.work.cycle()
        self.f.pull()

    def test_owner_message_is_seen_first_then_answered_and_the_log_shows_every_stage(self):
        self.f.state()
        self.assertFalse(self.f.paused)
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
        self.f.state()
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
        self.now += timedelta(seconds=fwd.PAUSE_HOLD + 1)
        self.owner_text("p", "stop changes")
        self.go()                                   # the pause command is read by the host in this step
        self.f.state()
        self.assertTrue(self.f.paused)
        self.now += timedelta(seconds=fwd.PAUSE_HOLD + 1)
        before = self.sent.count(EYES)
        self.owner_text("b", "status")
        self.go()
        self.assertEqual(self.sent.count(EYES), before)  # paused: seen by nobody, still answered
        self.assertTrue(any("paused" in s.lower() for s in self.sent))
        self.owner_text("r", "resume changes")
        self.go()
        self.f.state()
        self.assertFalse(self.f.paused)
        self.now += timedelta(seconds=1)
        self.owner_text("c", "status")
        self.go()
        self.assertEqual(self.sent.count(EYES), before + 1)
        self.owner_text("c", "status")              # the same message again (webhook, catch-up, replay)
        self.go()
        self.assertEqual(self.sent.count(EYES), before + 1)

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
