"""HASS-OWNERS-2 (review round 1): the SECOND owner's real transport, end to end with synthetic parts.

An in-process host (real relay store and HTTP handler), the real Mac forwarder, and a fake loopback BlueBubbles recording what it is
asked to send. Checks: the forwarder config takes `ownerChats` (and refuses bad shapes, a duplicate, a group chat, an ownerChat that is
not one of them, a gChat that is one of them); the second owner's message is accepted, posted and tapped back in THEIR chat; the catch-up
poll reads every owner chat with its own cursor; a reply and a preview picture for the second owner are actually sent to their chat;
G's separate gChat stays text only and is never an owner chat; the configured ownerChat stays the main one wherever it sits in
ownerChats; a failing second chat does not hold back the first; a retained draft is never approved by another person (see also
test_owners_two). No real Mac, number or message. Run: python3 -B -m unittest hass.tests.test_owners_transport -v
"""
import json
import unittest

from hass import bridge, bridge_attach, host, relay
from hass.tests import test_attach as ta
from hass.tests import test_fast_ack as tf
from hass.tests import test_forwarder as ft
from hass.tests import test_host as ht
from hass.tests.test_bridge import OWNER_CHAT
from mac import hass_forwarder as fwd

SECOND = "iMessage;-;second@example.invalid"
SECOND_ADDR = "second@example.invalid"
G_CHAT = "iMessage;-;g@example.invalid"
THIRD = "iMessage;-;third@example.invalid"


class ConfigTests(ft.ForwarderCase):
    def load(self, **change):
        self.config.write_text(json.dumps({**self.cfg, **change}))
        return fwd.load_config(self.config)

    def test_a_second_owner_chat_loads_and_the_main_chat_comes_first(self):
        cfg = self.load(ownerChats=[SECOND, OWNER_CHAT])
        self.assertEqual(fwd.owner_chats(cfg), (OWNER_CHAT, SECOND))  # ownerChat is the main one wherever it sits in the list

    def test_without_ownerChats_it_is_the_one_chat_as_before(self):
        self.assertEqual(fwd.owner_chats(self.load()), (OWNER_CHAT,))

    def test_bad_ownerChats_are_refused(self):
        for bad in ("", [], [OWNER_CHAT, OWNER_CHAT], [OWNER_CHAT, {}], [OWNER_CHAT, []], [OWNER_CHAT, 5], [OWNER_CHAT, "iMessage;+;group"],
                    [OWNER_CHAT, "plain"], [SECOND], [OWNER_CHAT] + [f"iMessage;-;a{n}@example.invalid" for n in range(8)], None):
            with self.subTest(bad=bad), self.assertRaises(ValueError): self.load(ownerChats=bad)

    def test_gChat_may_not_be_an_owner_chat(self):
        with self.assertRaises(ValueError): self.load(ownerChats=[OWNER_CHAT, SECOND], gChat=SECOND)
        self.assertEqual(self.load(ownerChats=[OWNER_CHAT, SECOND], gChat=G_CHAT)["gChat"], G_CHAT)


class TwoOwners(ft.ForwarderCase):
    def setUp(self):
        super().setUp()
        self.cfg = {**self.cfg, "ownerChats": [OWNER_CHAT, SECOND], "gChat": G_CHAT}
        self.f = fwd.Forwarder(self.cfg, self.spool, lambda: self.now, self.transport, self.sender)

    def test_a_message_in_the_second_owner_chat_is_accepted_and_posted_there(self):
        self.enqueue("s1", chats=[{"guid": SECOND}], handle={"address": SECOND_ADDR}, text="hours")
        self.f.deliver()
        self.assertEqual([(e["body"]["chat"], e["body"]["sender"]) for e in self.posts], [(SECOND, SECOND_ADDR)])

    def test_an_unlisted_chat_is_still_dropped(self):
        self.enqueue("t1", chats=[{"guid": THIRD}], handle={"address": "third@example.invalid"})
        self.f.deliver()
        self.assertEqual((self.posts, self.spool.status()["dropped_events"]), ([], 1))

    def test_a_forwarder_without_ownerChats_still_drops_the_second_chat(self):
        plain = fwd.Forwarder({k: v for k, v in self.cfg.items() if k != "ownerChats"}, self.spool, lambda: self.now, self.transport, self.sender)
        self.message("s2", chats=[{"guid": SECOND}], handle={"address": SECOND_ADDR})
        self.spool.doorbell({"type": "new-message", "data": {"guid": "s2"}}, self.now)
        plain.fetch()
        self.assertEqual((self.pending(), self.spool.status()["dropped_events"]), (0, 1))

    def test_catch_up_asks_every_owner_chat_with_its_own_cursor(self):
        asked, rows = [], {OWNER_CHAT: [], SECOND: []}
        real = self.transport

        def transport(url, body=None):
            if "/query" not in url: return real(url, body)
            asked.append((body["chatGuid"], body["after"]))
            return {"data": rows[body["chatGuid"]]}
        self.f.transport = transport
        self.f.catch_up()
        start = int(self.spool.get("start_ms"))
        self.assertEqual(asked, [(OWNER_CHAT, start), (SECOND, start)])
        later = self.message("late", chats=[{"guid": SECOND}], handle={"address": SECOND_ADDR})
        later["dateCreated"] = start + 5000
        rows[SECOND] = [later]
        asked.clear()
        self.now += 20
        self.f.catch_up()
        self.assertEqual(self.pending(), 1)  # the second owner's message was found by the poll
        rows[SECOND] = []
        asked.clear()
        self.now += 20
        self.f.catch_up()
        self.assertEqual(asked, [(OWNER_CHAT, start), (SECOND, start + 5000)])  # each chat's cursor is its own: the second moved on, the main did not
        self.assertEqual(int(self.spool.get("last_seen_ms")), start)

    def test_one_failing_owner_chat_does_not_stop_the_others(self):
        real = self.transport

        def transport(url, body=None):
            if "/query" in url and body["chatGuid"] == OWNER_CHAT: raise bridge.BridgeError("transport-error")
            return real(url, body)
        self.f.transport = transport
        later = self.message("late", chats=[{"guid": SECOND}], handle={"address": SECOND_ADDR})
        later["dateCreated"] = int(self.spool.get("start_ms")) + 5000
        self.query = [later]
        with self.assertRaises(bridge.BridgeError): self.f.catch_up()
        self.assertEqual(self.pending(), 1)

    def test_replies_to_the_second_owner_are_sent_and_acked_and_other_chats_still_refused(self):
        self.items = [{"id": 1, "chat": SECOND, "text": "for the second owner", "pictures": 0},
                      {"id": 2, "chat": THIRD, "text": "refuse", "pictures": 0},
                      {"id": 3, "chat": OWNER_CHAT, "text": "for Mike", "pictures": 0},
                      {"id": 4, "chat": G_CHAT, "text": "for G", "pictures": 0}]
        self.f.pull()
        self.assertEqual([c[:2] for c in self.sender.calls], [(SECOND, "for the second owner"), (OWNER_CHAT, "for Mike"), (G_CHAT, "for G")])
        self.assertEqual(self.acks, [1, 3, 4])

    def test_a_picture_for_g_chat_is_never_sent_and_a_failed_second_chat_does_not_hold_back_the_first(self):
        real = self.sender.send

        def send(chat, text, attachments=()):
            if chat == SECOND: raise bridge.BridgeError("transport-error")
            real(chat, text, attachments)
        self.sender.send = send
        self.items = [{"id": 1, "chat": G_CHAT, "text": "with a picture", "pictures": 1},
                      {"id": 2, "chat": SECOND, "text": "for the second owner", "pictures": 0},
                      {"id": 3, "chat": OWNER_CHAT, "text": "for Mike", "pictures": 0}]
        self.f.pull()
        self.assertEqual([c[:2] for c in self.sender.calls], [(OWNER_CHAT, "for Mike")])
        self.assertEqual(self.acks, [3])  # the second owner's reply is kept to be tried again, not given up; G's picture row is never sent

    def test_the_main_chat_failing_still_stops_the_pull_unacked(self):
        self.sender.fail = True
        self.items = [{"id": 1, "chat": OWNER_CHAT, "text": "for Mike", "pictures": 0}]
        with self.assertRaises(bridge.BridgeError): self.f.pull()
        self.assertEqual(self.acks, [])

    def test_the_outage_notice_goes_to_the_chat_of_the_stuck_message(self):
        self.enqueue("s3", chats=[{"guid": SECOND}], handle={"address": SECOND_ADDR})
        self.offline = True
        for seconds in (1, 10, 40, 100, 301, 601, 901):
            self.now = ft.NOW + seconds
            self.f.deliver()
        self.assertEqual([c[:2] for c in self.sender.calls], [(SECOND, fwd.NOTICE)])


class TwoOwnerTapbacks(tf.AckCase):
    def setUp(self):
        super().setUp()
        self.cfg = {**self.cfg, "ownerChats": [OWNER_CHAT, SECOND]}
        self.f = self.restart()
        self.f.reactor = self.reactor

    def test_each_owner_message_is_tapped_back_in_its_own_chat(self):
        self.enqueue("m1")
        self.enqueue("s1", chats=[{"guid": SECOND}], handle={"address": SECOND_ADDR})
        self.f.ack()
        self.f.ack()
        self.assertEqual(sorted(self.taps()), sorted([(OWNER_CHAT, "m1", "like"), (SECOND, "s1", "like")]))
        self.assertEqual(self.sender.calls, [])

    def test_a_sender_in_the_wrong_owner_chat_gets_no_tapback(self):
        self.enqueue("x1", chats=[{"guid": SECOND}], handle={"address": "owner@example.invalid"})  # the first owner's address in the second chat
        self.f.ack()
        self.assertEqual((self.taps(), self.states()), ([], {}))

    def test_a_tapback_with_no_recorded_chat_is_skipped_with_several_owners(self):
        self.spool.db.execute("INSERT INTO ack VALUES ('orphan','pending',?,NULL)", (self.now,))
        self.f.ack()
        self.assertEqual((self.taps(), self.states()["orphan"]), ([], "no_chat"))


class TwoOwnerPictures(ta.AttachCase):
    """The host side (real relay store, real HTTP handler) and the Mac side (real forwarder, fake BlueBubbles) with two owners."""
    def setUp(self):
        super().setUp()
        self.spool.db.close()
        self.cfg = {**self.cfg, "ownerChats": [OWNER_CHAT, SECOND], "gChat": G_CHAT}
        self.relay_sender = relay.RelaySender(self.store, host.owner_chat_order({"ownerChat": OWNER_CHAT, "ownerChats": (OWNER_CHAT, SECOND)}),
                                              lambda: ht.NOW, self.shots, G_CHAT)
        self.attach = bridge_attach.BlueBubblesAttachmentSender("http://127.0.0.1:1234", self.root / "password", fwd.owner_chats(self.cfg), self.bb)
        self.start()

    def chat_of(self, event): return self.multipart(event)["chatGuid"][1].decode()  # the multipart field values come back as bytes

    def test_the_second_owners_preview_picture_is_really_sent_to_their_chat(self):
        self.queue(self.shot("p.png"), text="Here is how it looks.", chat=SECOND)
        self.f.pull()
        self.assertEqual(self.texts(), ["Here is how it looks."])
        self.assertEqual([self.chat_of(e) for e in self.pngs()], [SECOND])
        self.assertEqual(self.store.status(), {"waiting": 0, "total": 1})  # acknowledged: it will not be handed out again
        self.assertEqual(self.text.calls[0][0], SECOND)

    def test_each_owner_gets_their_own_picture_in_their_own_chat(self):
        self.queue(self.shot("a.png"), text="for the first", chat=OWNER_CHAT)
        self.queue(self.shot("b.png", ta.PNG2), text="for the second", chat=SECOND)
        self.f.pull()
        self.assertEqual(sorted((self.chat_of(e), self.multipart(e)["attachment"][1]) for e in self.pngs()),
                         sorted([(OWNER_CHAT, ta.PNG), (SECOND, ta.PNG2)]))
        self.assertEqual([c[0] for c in self.text.calls], [OWNER_CHAT, SECOND])

    def test_g_chat_never_gets_a_picture_and_the_host_refuses_to_queue_one(self):
        with self.assertRaises(relay.RelayRefused): self.queue(self.shot("g.png"), chat=G_CHAT)
        self.assertEqual(self.pngs(), [])

    def test_the_attachment_sender_refuses_a_chat_that_is_not_an_owner_chat(self):
        for chat in (G_CHAT, THIRD, "iMessage;+;group"):
            with self.subTest(chat=chat), self.assertRaises(bridge.BridgeError): self.attach.send_png(chat, ta.PNG, "hass-1-0.png")
        self.assertEqual(self.pngs(), [])

    def test_a_forwarder_not_yet_upgraded_does_not_receive_the_second_owners_row_as_text_or_picture(self):
        old = {k: v for k, v in self.cfg.items() if k != "ownerChats"}
        self.queue(self.shot("p.png"), chat=SECOND)
        self.f = fwd.Forwarder(old, self.spool, lambda: self.now.timestamp(), self.transport, self.text, bridge_attach.BlueBubblesAttachmentSender(
            "http://127.0.0.1:1234", self.root / "password", OWNER_CHAT, self.bb))
        self.f.pull()
        self.assertEqual((self.texts(), self.pngs(), self.store.status()["waiting"]), ([], [], 1))  # kept waiting, never lost, never sent to the wrong chat


class MainChatOrder(unittest.TestCase):
    def test_the_configured_ownerChat_is_the_main_one_wherever_it_sits(self):
        self.assertEqual(host.owner_chat_order({"ownerChat": OWNER_CHAT}), (OWNER_CHAT,))
        self.assertEqual(host.owner_chat_order({"ownerChat": OWNER_CHAT, "ownerChats": (SECOND, OWNER_CHAT)}), (OWNER_CHAT, SECOND))
        self.assertEqual(relay.RelaySender(None, host.owner_chat_order({"ownerChat": OWNER_CHAT, "ownerChats": (SECOND, OWNER_CHAT)}),
                                           lambda: 0).owner_chat, OWNER_CHAT)

    def test_by_default_every_owner_chat_may_get_pictures_and_g_chat_never(self):
        sender = relay.RelaySender(None, (OWNER_CHAT, SECOND), lambda: 0, None, G_CHAT)
        self.assertEqual(sender.picture_chats, (OWNER_CHAT, SECOND))
        self.assertNotIn(G_CHAT, sender.picture_chats)


if __name__ == "__main__":
    unittest.main()
