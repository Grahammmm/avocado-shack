"""HASS-POS-2 (build-ahead): the till-view commands for Mike and G (hass/clover/pos_chat.py), called directly with fixture messages and a
fixture TillDesk. Not wired into chat/conversation yet. Synthetic data only; sockets are patched; no runner, interpreter or token is touched.
Run: python3 -B -m unittest hass.tests.test_clover_pos_chat
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import voice
from hass.clover import chat, pos_chat
from hass.conversation import Inbound
from hass.tests.test_clover_chat import BLOCK
from hass.tests.test_clover_cli import T0
from hass.tests.test_clover_pos import NOTE, PosCase, put_inputs

MIKE, MIKE_CHAT = "+15555550101", "iMessage;-;+15555550101"
G, G_CHAT = "+15555550102", "iMessage;-;+15555550102"
SETTINGS = {"ownerKeys": frozenset({"+15555550101"}), "gKeys": frozenset({"+15555550102"}), "gChat": G_CHAT}
OWNER_CHATS = (MIKE_CHAT,)
Q = voice.quote
SUMMARY = ("Till at 12:00 pm: 6 items, 2 sold out, 0 running low, 1 with no count. Website: 2 linked, stock words waiting: not available yet. "
           "Count drops today: 3 items, 38 units.")
PRICE = f"{Q('Hass avocado')}: $1.50 each, 40 in the till (as of 12:00 pm)."
TODAY = f"Biggest count drops today: {Q('Eggs, dozen')} 14, {Q('Sunshine olive oil')} 14, {Q('Hass avocado')} 10 {NOTE}"
WEEK = f"Biggest count drops this week: {Q('Sunshine olive oil')} 19, {Q('Eggs, dozen')} 14, {Q('Hass avocado')} 10 {NOTE}"
SITE_START = "Website vs till. Till items without a site link: "


def msg(sender=MIKE, chat_id=MIKE_CHAT, text="till summary", **over):
    return Inbound(**{"provider_id": "p1", "chat": chat_id, "sender": sender, "text": text, **over})


class ParseTests(unittest.TestCase):
    def test_fixed_patterns_only(self):
        for text, want in (("Till summary", ("till_summary", None)), ("  what sold today?  ", ("sold_today", None)),
                           ("What sold this week.", ("sold_week", None)), ("website vs till", ("website_vs_till", None)),
                           ("website versus till!", ("website_vs_till", None)), ("price of honey", ("price_of", "honey")),
                           ("What's the price of Wildflower  Honey?", ("price_of", "wildflower honey"))):
            self.assertEqual(pos_chat.parse(text), want, text)
        for text in ("", "price of", "till summary please", "what sold today\nand more", "price of " + "x" * 200,
                     "how many honey", "change the price of honey to 5", None, 5):
            self.assertIsNone(pos_chat.parse(text), repr(text))
        self.assertEqual(pos_chat.INTENTS, ("till_summary", "price_of", "sold_today", "sold_week", "website_vs_till"))


class AllowedTests(unittest.TestCase):
    def ok(self, m, role):
        return pos_chat.allowed(m, SETTINGS, OWNER_CHATS, role=role)

    def test_mike_and_g_each_only_in_their_own_chat(self):
        self.assertTrue(self.ok(msg(), "owner"))
        self.assertTrue(self.ok(msg(G, G_CHAT), "g"))
        self.assertFalse(self.ok(msg(G, G_CHAT), "owner"))
        self.assertFalse(self.ok(msg(MIKE, MIKE_CHAT), "g"))
        self.assertFalse(self.ok(msg(G, MIKE_CHAT), "g"))     # G's number in Mike's chat
        self.assertFalse(self.ok(msg(MIKE, G_CHAT), "g"))     # Mike's number in G's chat
        self.assertFalse(pos_chat.allowed(msg(G, G_CHAT), SETTINGS, (G_CHAT,), role="g"))   # gChat must not be an owner chat

    def test_chat_keys_pick_the_owner_of_that_chat(self):
        settings = {**SETTINGS, "chatKeys": {MIKE_CHAT: frozenset({"+15555550103"})}}
        self.assertFalse(pos_chat.allowed(msg(), settings, OWNER_CHATS, role="owner"))
        self.assertTrue(pos_chat.allowed(msg("+15555550103"), settings, OWNER_CHATS, role="owner"))

    def test_nobody_else_gets_a_reply(self):
        for role, chat_id, sender in (("owner", MIKE_CHAT, MIKE), ("g", G_CHAT, G)):
            for bad in (msg("+15555550199", chat_id), msg(sender, "iMessage;-;+15555550199"), msg(sender, "iMessage;+;chat123"),
                        msg(sender, "iMessage;+;" + chat_id), msg(sender, chat_id, kind="edited"), msg(sender, chat_id, attachments=1),
                        msg(sender, chat_id, from_me=True), msg(None, chat_id), msg("not a number", chat_id)):
                self.assertFalse(self.ok(bad, role), (role, bad))
        self.assertFalse(self.ok(msg(), "stranger"))
        self.assertFalse(pos_chat.allowed(msg(G, G_CHAT), {"ownerKeys": SETTINGS["ownerKeys"]}, OWNER_CHATS, role="g"))   # no G configured


class AnswerTests(PosCase):
    def setUp(self):
        super().setUp()
        self.wt = Path(tempfile.mkdtemp())
        put_inputs(self.state, self.wt)
        self.desk = chat.TillDesk(str(self.state), BLOCK)
        spies = [mock.patch(f"hass.interpreter_local.{n}", side_effect=AssertionError(n)) for n in ("urllib_transport", "check_url")]
        spies += [mock.patch(f"subprocess.{n}", side_effect=AssertionError(n)) for n in ("Popen", "run")]
        self.spies = [p.start() for p in spies]
        self.addCleanup(mock.patch.stopall)

    def serve(self, sender, chat_id, role, text, desk=None):
        m = msg(sender, chat_id, text)
        intent = pos_chat.parse(m.text)
        if intent is None or not pos_chat.allowed(m, SETTINGS, OWNER_CHATS, role=role):
            return None
        return pos_chat.answer(intent, desk=desk or self.desk, now=T0, worktree=self.wt)

    def test_replies_word_for_word_for_mike_and_for_g(self):
        for who in (("owner", MIKE, MIKE_CHAT), ("g", G, G_CHAT)):
            role, sender, chat_id = who
            for text, want in (("till summary", SUMMARY), ("price of hass avocado", PRICE), ("what sold today", TODAY), ("what sold this week", WEEK)):
                self.assertEqual(self.serve(sender, chat_id, role, text), want, (role, text))
            site = self.serve(sender, chat_id, role, "website vs till")
            self.assertTrue(site.startswith(SITE_START + Q("Hass avocado (FAKEITEM00002)")), site)
            self.assertTrue(site.endswith(f"Stock word disagreements: {Q('Eggs, dozen (eggs): site yes; till 0')}."), site)
        self.assertEqual(self.serve(MIKE, MIKE_CHAT, "owner", "price of unicorn"), "I can't find anything like that in the till.")
        self.assertIsNone(self.serve(G, MIKE_CHAT, "g", "till summary"))
        self.assertIsNone(self.serve(MIKE, MIKE_CHAT, "owner", "hello"))

    def test_both_drops_replies_say_count_drops_not_exact_sales(self):
        for text in ("what sold today", "what sold this week"):
            self.assertIn("count drops, not exact sales", self.serve(MIKE, MIKE_CHAT, "owner", text))
        early = chat.TillDesk(str(self.state), BLOCK, read=lambda s, i: (self.snapshot, True))
        with mock.patch("hass.clover.cache.history", return_value=[]):
            for text in ("what sold today", "what sold this week"):
                self.assertIn("count drops, not exact sales", pos_chat.answer(pos_chat.parse(text), desk=early, now=T0, worktree=self.wt))

    def test_no_snapshot_gives_the_existing_never_read_and_down_lines(self):
        for reachable, want in ((True, chat.NEVER_READ), (False, chat.DOWN_NO_DATA)):
            desk = chat.TillDesk(str(self.state), BLOCK, read=lambda s, i, r=reachable: (None, r))
            for text in ("till summary", "price of honey", "what sold today", "website vs till"):
                self.assertEqual(pos_chat.answer(pos_chat.parse(text), desk=desk, now=T0, worktree=self.wt), want)

    def test_missing_website_inputs_give_the_plain_failure_line(self):
        for text in ("till summary", "website vs till"):
            self.assertEqual(pos_chat.answer(pos_chat.parse(text), desk=self.desk, now=T0, worktree=self.wt / "none"), pos_chat.COMPARE_FAILED)

    def test_no_runner_interpreter_or_network_was_touched(self):
        self.serve(MIKE, MIKE_CHAT, "owner", "till summary")
        self.assertFalse(any(spy.called for spy in self.spies))
        self.assertFalse(any(m.called for m in self.net))


class WaitingLineTests(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp())
        self.path = self.state / "clover" / "reports" / "site-stock-totals.json"
        self.path.parent.mkdir(parents=True)

    def put(self, data, mtime=1794844800):   # 2026-11-17 08:00 Pacific
        self.path.write_text(data if isinstance(data, str) else json.dumps(data))
        os.utime(self.path, (mtime, mtime))

    def test_line_from_the_totals_file(self):
        self.put(dict(pending=3, parked=0, oldestPendingAge=5400, lastReason="publish-refused", batchesLeft=1))
        self.assertEqual(pos_chat.waiting_line(self.state), "3 stock words waiting for the website since 6:30 am (publish-refused)")
        self.put(dict(pending=1, parked=0, oldestPendingAge=0, lastReason="", batchesLeft=1))
        self.assertEqual(pos_chat.waiting_line(self.state), "1 stock words waiting for the website since 8:00 am")

    def test_absent_corrupt_zero_or_odd_files_give_none(self):
        self.assertIsNone(pos_chat.waiting_line(self.state / "nowhere"))
        self.assertIsNone(pos_chat.waiting_line(self.state))
        for data in (dict(pending=0, oldestPendingAge=0, lastReason=""), "{not json", "[]", "null", dict(oldestPendingAge=5),
                     dict(pending="3", oldestPendingAge=5), dict(pending=True, oldestPendingAge=5), dict(pending=-1, oldestPendingAge=5),
                     dict(pending=2, oldestPendingAge="x"), dict(pending=2, oldestPendingAge=1e999), dict(pending=2, oldestPendingAge=5, lastReason=7)):
            self.put(data)
            self.assertIsNone(pos_chat.waiting_line(self.state), data)


if __name__ == "__main__":
    unittest.main()
