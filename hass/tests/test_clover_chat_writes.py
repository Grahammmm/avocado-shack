"""HASS-CLOVER-4: the owner's till changes by fixed words in the chat: a draft with a code, `yes <code>` applies it through the CLOVER-3
engine (read back and journalled), a count reaching 0 carries the website word under the same yes, and its undo restores it through the
normal site path. Synthetic till only (a stateful fake transport), a fake token file in a temp folder, sockets patched.
Run: python3 -m unittest discover -s hass/tests -p 'test_clover_chat_writes.py' -v
"""
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

from hass import cloud_codex, conversation, editor
from hass.clover import chat
from hass.clover.client import CloverWriteClient
from hass.clover.config import from_settings
from hass.content_model import shop_today
from hass.tests.test_clover_apply import Till
from hass.tests.test_clover_chat import BLOCK, seed
from hass.tests.test_clover_client import FAKE_TOKEN, NoNetwork
from hass.tests.test_conversation import CHAT, OWNER, STRANGER, ConversationTestCase

CAP = ("I have already made 20 changes to the till today, which is my daily limit. Nothing was changed. "
       "The count starts again at midnight Pacific.")


class TillWriteChat(NoNetwork, ConversationTestCase):
    def setUp(self):
        super().setUp()
        for p in (mock.patch.object(conversation.Outbox, "strict", True),
                  mock.patch.object(cloud_codex.Runner, "__call__", side_effect=AssertionError("runner called"))):
            self.runner = p.start()
        self.addCleanup(mock.patch.stopall)
        self.state = Path(self.repo.state)
        seed(self.state)
        keys = tempfile.TemporaryDirectory()
        self.addCleanup(keys.cleanup)
        os.chmod(keys.name, 0o700)
        token = Path(keys.name) / "write.token"
        token.write_text(FAKE_TOKEN)
        token.chmod(0o600)
        self.block = {**BLOCK, "writeTokenFile": str(token), "writes": True, "liveApproved": True, "categoryMap": {"pantry": "Pantry"}}
        self.till = Till()
        engine = chat.BundleEngine(self.state, from_settings(self.block),
                                   lambda t: CloverWriteClient("FAKEMERCH0001", t, self.till, min_interval=0), mike=(OWNER, CHAT))
        self.conv = self.open(conversation.Editor(str(self.state)))
        self.conv.till = self.desk = chat.TillDesk(str(self.state), self.block, engine=engine)
        self.calls, real = [], self.interp.interpret
        self.interp.interpret = lambda text, *a, **k: (self.calls.append(text), real(text, *a, **k))[1]

    def item(self, iid):
        return self.till.items[iid]

    def draft(self, text):
        self.assertEqual(self.say(text), "till-draft", text)
        reply = self.replies()[0]
        return reply, re.search(r"Reply yes ([0-9a-f]{8}) to do this", reply)[1]

    def yes(self, code):
        self.assertEqual(self.say(f"yes {code}"), "till-approved")
        return self.replies()

    def journal(self):
        with self.desk.engine.journal.locked() as db:
            return [dict(r) for r in db.execute("SELECT code, status, sender, chat FROM changes")]

    def site_word(self, pid):
        products = json.loads((self.repo.wt / "hass/content/products.json").read_text("utf-8"))["products"]
        return next(p for p in products if p["id"] == pid).get("available")

    def test_each_kind_gives_a_draft_then_one_yes_applies_and_reads_back(self):
        cases = (("received 12 Sunshine olive oil", "  Count: 12 -> 24", lambda: "Sunshine olive oil now shows 24",
                  lambda: self.item("FAKEITEM00001")["itemStock"]["quantity"] == 24),
                 ("set Hass avocado to 7", "  Count: 40 -> 7", lambda: "Hass avocado now shows 7",
                  lambda: self.item("FAKEITEM00002")["itemStock"]["quantity"] == 7),
                 ("new item: Lemon curd, 8.50, pantry", "Did you mean to add this to the till?",
                  lambda: "Lemon curd is in it, SKU " + self.item("NEWITEM")["sku"], lambda: self.item("NEWITEM")["price"] == 850),
                 ("change price of Hass avocado to 2.00", "  Price: $1.50 -> $2.00 each (+33.3%)", lambda: "Hass avocado now costs $2.00",
                  lambda: self.item("FAKEITEM00002")["price"] == 200),
                 ("hide Hass avocado on the till", "  On the till: showing -> hidden", lambda: "Hass avocado is hidden",
                  lambda: self.item("FAKEITEM00002")["hidden"] is True),
                 ("show Old honey jar on the till", "  On the till: hidden -> showing", lambda: "Old honey jar is showing",
                  lambda: self.item("FAKEITEM00004")["hidden"] is False))
        for text, line, done, applied in cases:
            with self.subTest(text=text):
                reply, code = self.draft(text)
                self.assertIn(line, reply.splitlines())
                self.assertTrue(reply.endswith(f"Reply yes {code} to do this, or no {code} to drop it. Nothing changes until you say yes."))
                out = self.yes(code)
                self.assertEqual(out, [f"Done, and I read the till back: {done()}. To put it back, say undo {code}."])
                self.assertTrue(applied())
                self.assertEqual(self.journal()[-1]["status"], "applied")
        self.assertEqual((self.calls, self.drafts(), self.runner.called), ([], [], False))   # no interpreter, runner or site draft

    def test_a_price_message_never_reaches_the_interpreter_or_the_runner_and_the_transcript_keeps_his_words(self):
        reply, code = self.draft("change price of Sunshine olive oil to 14.00")
        self.assertIn("  Price: $12.50 -> $14.00 each (+12.0%)", reply.splitlines())
        self.yes(code)
        self.assertEqual((self.calls, self.runner.called, self.item("FAKEITEM00001")["price"]), ([], False, 1400))
        with sqlite3.connect(self.state / "transcript.sqlite3") as db:
            rows = db.execute("SELECT text, disposition FROM events WHERE direction='in' ORDER BY id").fetchall()
        self.assertEqual(rows, [("change price of Sunshine olive oil to 14.00", "till-draft"), (f"yes {code}", "till-approved")])

    def test_sold_out_carries_the_site_word_under_one_yes_and_its_undo_restores_it(self):
        products = json.loads((self.repo.wt / "hass/content/products.json").read_text("utf-8"))["products"]
        pid = next(p["id"] for p in products if p.get("status", "active") == "active")
        links = self.state / "clover" / "links.json"
        links.write_text(json.dumps({pid: {"cloverId": "FAKEITEM00003", "sku": "EGG12"}}))
        links.chmod(0o600)
        shelf = editor.prepare({"ops": [{"op": "store.confirm_selection", "args": {}}]}, state=str(self.state))   # the editor's own today
        self.assertEqual(editor.apply(shelf["draft"]["change_id"], shelf["draft"]["draft_hash"], state=str(self.state))["result"], "applied")
        before = self.site_word(pid)
        reply, code = self.draft("Eggs, dozen is sold out")
        self.assertIn("Mark Eggs, dozen (SKU EGG12) as sold out?", reply)
        self.assertIn("  Count: 2 -> 0", reply.splitlines())
        self.assertRegex(reply, r"  Website: marks .+ as Sold out \(same yes; the site shows a word, never a count\)")
        out = self.yes(code)
        self.assertEqual(out[0], f"Done, and I read the till back: Eggs, dozen now shows 0. To put it back, say undo {code}.")
        self.assertEqual((self.item("FAKEITEM00003")["itemStock"]["quantity"], self.site_word(pid)), (0, "no"))
        self.assertEqual([r["state"] for r in self.drafts()], ["applied"])   # the site word went through the normal draft and apply
        self.assertEqual(self.say(f"undo {code}"), "till-undo")
        undo = self.replies()[0]
        self.assertIn("Undo: put the count of Eggs, dozen (SKU EGG12) back?", undo)
        self.assertIn("  Website:", undo)
        self.yes(re.search(r"Reply yes ([0-9a-f]{8})", undo)[1])
        self.assertEqual((self.item("FAKEITEM00003")["itemStock"]["quantity"], self.site_word(pid)), (2, before))

    def test_a_wrong_sender_or_a_group_chat_gets_no_draft(self):
        self.assertEqual(self.say("set Hass avocado to 7", sender=STRANGER, chat="chat-stranger"), "ignored")
        self.assertEqual(self.say("set Hass avocado to 7", chat="chat-fixture;+;group"), "ignored")
        self.assertEqual(self.replies(), [])
        intent = self.desk.parse("set Hass avocado to 7")
        for sender, room in ((STRANGER, CHAT), (OWNER, "chat-fixture;+;group")):
            with self.subTest(sender=sender, room=room):
                self.assertEqual(self.desk.answer(intent, self.now, sender=sender, chat=room), chat.NOT_OWNER)
        self.assertEqual(self.journal(), [])
        _, code = self.draft("set Hass avocado to 7")
        self.assertEqual(self.say(f"yes {code}", sender=STRANGER, chat="chat-stranger"), "ignored")
        self.assertEqual(self.desk.approve(code, sender=OWNER, chat="chat-fixture;+;group")[1], ())
        self.assertEqual((self.item("FAKEITEM00002")["itemStock"]["quantity"], self.journal()[0]["status"]), (40, "draft"))

    def test_the_daily_cap_reads_as_written(self):
        today = shop_today(self.now).isoformat()
        with mock.patch.object(self.desk.engine, "_day", lambda: today), self.desk.engine.journal.locked() as db:
            for n in range(20):
                db.execute("INSERT INTO changes VALUES(?,?,?,?,0,'applied',?,NULL)", (f"old{n}", '{"undo_of": null}', OWNER, CHAT, today))
        with mock.patch.object(self.desk.engine, "_day", lambda: today):
            self.assertEqual(self.say("set Hass avocado to 7"), "till-draft")
            self.assertEqual(self.replies(), [CAP])

    def test_no_drops_it_pause_holds_the_yes_and_help_lists_the_till_words(self):
        _, code = self.draft("set Hass avocado to 7")
        self.assertEqual(self.say(f"no {code}"), "till-cancelled")
        self.assertEqual(self.replies(), ["Okay, I've cancelled that. Nothing changed on the till."])
        self.assertEqual(self.journal()[0]["status"], "dropped")
        _, code = self.draft("set Hass avocado to 8")
        self.say("stop changes")
        self.replies()
        self.assertEqual(self.say(f"yes {code}"), "paused")
        self.assertEqual(self.replies(), [f"Changes are paused, so I haven't changed the till. Say resume changes, then reply yes {code}."])
        self.assertEqual(self.item("FAKEITEM00002")["itemStock"]["quantity"], 40)
        self.say("help")
        self.assertIn("Till (each needs your yes and its code): received 12 Sunshine olive oil;", self.replies()[0])
        self.say("mark the olive oil sold out")   # not exactly a till item: the website's own words, as before
        self.assertEqual(self.calls, ["mark the olive oil sold out"])
