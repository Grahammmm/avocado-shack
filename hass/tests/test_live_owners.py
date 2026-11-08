"""HASS-LIVE-PLAN-1: two owners (Mike's chat and, with gIsOwner, G's own chat) and nobody else.

Synthetic chats, fixture editor, injected clock. Checks: a non-owner changes nothing and gets no reply; a stranger cannot read or
close an owner's open request; each owner's yes, no, undo and open request belong to that owner's chat; replies go to the chat
that asked (G's chat is text only); the default (no gIsOwner) is exactly one owner.
Run: python3 -m unittest hass.tests.test_live_owners -v
"""
import unittest

from hass import conversation as conv
from hass.ops import load_registry
from hass.tests import fixture_ops
from hass.tests.test_conversation import CHAT, GROUP, OWNER, SETTINGS, STRANGER, ConversationTestCase, _ops
from hass.tests.test_editor import DESC, HOURS, NEW_HOURS

G, GCHAT = "g@example.invalid", "chat-fixture-g"
TWO = {**SETTINGS, "gSenders": [G], "gChat": GCHAT, "gIsOwner": True}


class Scripted(conv.FixtureInterpreter):
    def __init__(self, mapping):
        super().__init__(mapping)
        self.asked = []

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        self.asked.append((text, recent))
        return super().interpret(text, pending)


class Base(ConversationTestCase):
    settings = TWO

    def setUp(self):
        super().setUp()
        self.conv.db.close()
        self.set_settings(self.settings)
        self.editor.registry = {**fixture_ops.registry(), "history.revert": load_registry()["history.revert"]}
        self.interp = Scripted({"hours": _ops((HOURS, {"hours": NEW_HOURS})),
                                "desc": _ops((DESC, {"id": "photo-product-001", "description": "Ripe and creamy."})),
                                "when?": {"question": "Which day should change?"}})
        self.conv = self.open()
        self.addCleanup(lambda: self.conv.db.close())

    def sent(self):
        """(chat, text) for every reply still unsent, then marks them sent."""
        rows = [(r["chat"], r["text"], r["attachments"]) for r in self.conv.outbox.unsent()]
        self.conv.flush(self.out)
        return rows

    def outbox_count(self):
        return self.conv.db.execute("SELECT count(*) FROM outbox").fetchone()[0]

    def asks(self):
        return [tuple(r) for r in self.conv.db.execute("SELECT provider_id, chat FROM open_asks")] \
            if self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'open_asks'").fetchone() else []


class ConfigTests(Base):
    settings = SETTINGS

    def test_g_is_not_an_owner_unless_set(self):
        self.assertNotIn("gOwner", conv.load_settings(self.repo.state))
        self.set_settings({**SETTINGS, "gSenders": [G], "gChat": GCHAT})  # problems log only: G's `hours` is ignored
        self.conv.db.close()
        self.conv = self.open()
        self.assertEqual(self.say("hours", chat=GCHAT, sender=G), "ignored")
        self.assertEqual((self.sent(), self.drafts()), ([], []))

    def test_g_owner_needs_g_numbers_and_a_bool(self):
        for extra in ({"gIsOwner": True}, {"gIsOwner": "yes", "gSenders": [G], "gChat": GCHAT},
                      {"gIsOwner": True, "gSenders": [G]}, {"gIsOwner": 1, "gSenders": [G], "gChat": GCHAT}):
            with self.subTest(extra=extra):
                self.set_settings({**SETTINGS, **extra})
                with self.assertRaises(conv.ConfigError): conv.load_settings(self.repo.state)
        self.set_settings(TWO)
        self.assertTrue(conv.load_settings(self.repo.state)["gOwner"])

    def test_g_cannot_also_be_mikes_number(self):
        self.set_settings({**TWO, "ownerSenders": [OWNER, G]})
        with self.assertRaises(conv.ConfigError): conv.load_settings(self.repo.state)


class StrangerTests(Base):
    def test_a_non_owner_changes_nothing_and_gets_no_reply(self):
        row, _ = self.propose("hours")
        before = (self.drafts(), self.commits(), self.outbox_count(), self.asks())
        cases = [dict(sender=STRANGER), dict(chat=GROUP), dict(sender=STRANGER, chat=GCHAT), dict(sender=OWNER, chat=GCHAT),
                 dict(sender=G, chat=CHAT), dict(sender=G, chat=GROUP), dict(sender="+15550000000", chat="chat-unknown")]
        for kwargs in cases:
            for text in ("yes " + row["code"], "yes", "no", "undo", "status", "show", "history", "memory", "desc", "stop changes",
                         "problems", "weekly", "report"):
                with self.subTest(case=kwargs, text=text):
                    self.assertEqual(self.say(text, **kwargs), "ignored")
        self.assertEqual((self.drafts(), self.commits(), self.outbox_count(), self.asks()), before)
        self.assertEqual(self.editor.applies, 0)

    def test_a_stranger_cannot_read_or_close_an_open_request(self):
        self.assertEqual(self.say("when?"), "question")
        self.sent()
        before_asks = self.asks()
        self.assertEqual(len(before_asks), 1)
        for text in ("no", "cancel", "yes", "when?", "Friday", "status", "show"):
            for kwargs in (dict(sender=STRANGER), dict(chat=GROUP), dict(sender=STRANGER, chat=GCHAT)):
                self.assertEqual(self.say(text, **kwargs), "ignored")
        self.assertEqual((self.asks(), self.sent(), self.interp.asked), (before_asks, [], [("when?", None)]))
        # the owner's own answer still joins the request, and reaches the interpreter with it
        self.say("Friday")
        self.assertEqual(self.interp.asked[-1][0], "Friday")
        self.assertEqual(self.interp.asked[-1][1]["earlier"], ["when?"])

    def test_a_stranger_stores_no_text(self):
        self.say("zqx stranger request", sender=STRANGER)
        self.say("zqx stranger request", chat=GCHAT, sender=STRANGER)
        stored = (self.repo.state / "conversation.sqlite3").read_bytes()
        self.assertNotIn(b"zqx", stored)


class TwoOwnerTests(Base):
    def test_each_owner_is_answered_in_their_own_chat(self):
        self.assertEqual(self.say("status"), "status")
        [(chat, _text, _a)] = self.sent()
        self.assertEqual(chat, CHAT)
        self.assertEqual(self.say("status", chat=GCHAT, sender=G), "status")
        [(chat, _text, _a)] = self.sent()
        self.assertEqual(chat, GCHAT)

    def test_g_gets_a_proposal_in_g_chat_with_no_picture_and_can_approve_it(self):
        self.assertEqual(self.say("hours", chat=GCHAT, sender=G), "proposed")
        [(chat, text, attachments)] = self.sent()
        self.assertEqual((chat, attachments), (GCHAT, "[]"))
        row = self.drafts()[-1]
        self.assertEqual((row["chat"], row["sender"]), (GCHAT, G))
        self.assertEqual(self.say("yes", chat=GCHAT, sender=G), "approved")
        self.assertEqual(self.commits(), 1)
        self.assertTrue(all(chat == GCHAT for chat, _t, _a in self.sent()))

    def test_one_owner_cannot_approve_cancel_or_name_the_others_change(self):
        mine, _ = self.propose("hours")
        for text in (f"yes {mine['code']}", "yes", f"no {mine['code']}", "no", f"show {mine['code']}", "okay", mine["code"]):
            with self.subTest(text=text):
                self.say(text, chat=GCHAT, sender=G)
                for chat, reply, _a in self.sent():
                    self.assertEqual(chat, GCHAT)
                    self.assertNotIn(mine["summary"], reply)
                self.assertEqual((self.drafts()[0]["state"], self.commits()), ("proposed", 0))
        self.say("hours", chat=GCHAT, sender=G)
        self.sent()
        theirs = self.drafts()[-1]
        self.assertNotEqual(theirs["code"], mine["code"] + "x")
        self.say(f"yes {theirs['code']}")  # Mike's yes on G's code
        self.say("no")
        self.sent()
        self.assertEqual([d["state"] for d in self.drafts()][-1], "proposed")
        self.assertEqual(self.commits(), 0)

    def test_open_requests_are_kept_apart(self):
        self.assertEqual(self.say("when?"), "question")
        self.sent()
        self.assertEqual(self.asks(), [("m1", CHAT)])
        # G's text neither sees nor closes Mike's open request
        self.say("Friday", chat=GCHAT, sender=G)
        self.assertIsNone(self.interp.asked[-1][1])
        self.say("no", chat=GCHAT, sender=G)
        self.assertEqual(self.asks(), [("m1", CHAT)])
        # G opens their own; each is kept for its own chat
        self.assertEqual(self.say("when?", chat=GCHAT, sender=G), "question")
        self.assertEqual(sorted(chat for _p, chat in self.asks()), sorted([CHAT, GCHAT]))
        self.sent()
        self.say("Friday")
        self.assertEqual(self.interp.asked[-1][1]["earlier"], ["when?"])
        self.say("Saturday", chat=GCHAT, sender=G)
        self.assertEqual(self.interp.asked[-1][1]["earlier"], ["when?"])
        self.assertEqual(self.interp.asked[-1][1]["question"], "Which day should change?")

    def test_undo_from_g_takes_back_the_last_change_in_g_chat(self):
        self.propose("hours")
        self.say("yes")
        self.sent()
        self.assertEqual(self.say("undo", chat=GCHAT, sender=G), "proposed")
        [(chat, _t, _a)] = self.sent()
        self.assertEqual(chat, GCHAT)
        self.assertEqual(self.say("yes", chat=GCHAT, sender=G), "approved")
        self.assertEqual(self.commits(), 2)

    def test_g_problems_command_still_answers_only_g(self):
        self.assertEqual(self.say("problems", chat=GCHAT, sender=G), "g-problems")
        [(chat, _t, _a)] = self.sent()
        self.assertEqual(chat, GCHAT)
        self.assertNotEqual(self.say("problems"), "g-problems")  # Mike's own message is an ordinary request
        self.assertTrue(all(chat == CHAT for chat, _t, _a in self.sent()))


class OneOwnerStillWorks(ConversationTestCase):
    """No gIsOwner: the stores gain a chat column but behave exactly as before."""

    def test_old_store_without_chat_columns_is_upgraded(self):
        self.say("when?")
        self.replies()
        self.conv.db.execute("ALTER TABLE messages DROP COLUMN chat")
        self.conv.db.execute("ALTER TABLE open_asks DROP COLUMN chat")
        self.conv.db.close()
        self.conv = self.open()
        self.assertEqual(self.say("hours"), "proposed")
        self.assertEqual([r["name"] for r in self.conv.db.execute("PRAGMA table_info(messages)") if r["name"] == "chat"], ["chat"])
        self.assertEqual(self.say("yes"), "approved")


if __name__ == "__main__":
    unittest.main()
