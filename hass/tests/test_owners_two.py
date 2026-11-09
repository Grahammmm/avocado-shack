"""HASS-OWNERS-2: several owners (Mike and G), each in their OWN one-to-one chat (settings ownerChats).

Synthetic chats and addresses, fixture editor and previewer, injected clock. Checks: config validation; each owner is read only in
their own chat (a sender never speaks in another owner's chat); replies, pictures and approval prompts go to the chat that asked; a
yes or no only reaches a draft THIS chat made; undo and history act on the site's last change and say whose it was (a bare undo never
reaches the other owner's work); a second owner's request while a draft or a release is waiting gets a plain answer and changes
nothing; open requests, pause, the daily limit are as documented. Single-owner behaviour is covered by the existing conversation tests.
Run: python3 -B -m unittest hass.tests.test_owners_two -v
"""
import datetime as _dt
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from hass import conversation as conv
from hass import host, relay
from hass.ops import load_registry
from hass.tests import fixture_ops
from hass.tests.test_conversation import ConversationTestCase, GROUP, STRANGER, _ops
from hass.tests.test_editor import DESC, HOURS, NEW_HOURS
from hass.tests.test_undo import FakePreviewer

MIKE, GEE = "mike@example.invalid", "g@example.invalid"
MCHAT, GCHAT = f"iMessage;-;{MIKE}", f"iMessage;-;{GEE}"
THIRD = "iMessage;-;third@example.invalid"
TWO = {"ownerSenders": [MIKE, GEE], "ownerChat": MCHAT, "ownerChats": [MCHAT, GCHAT], "ownerNames": {MCHAT: "Mike", GCHAT: "G"},
       "approvalTtlSeconds": 600}


def load(settings):
    with tempfile.TemporaryDirectory() as sdir:
        with open(f"{sdir}/config.json", "w", encoding="utf-8") as fh: json.dump({"settings": settings}, fh)
        return conv.load_settings(sdir)


class ConfigTests(ConversationTestCase):
    def refused(self, **change):
        with self.assertRaises(conv.ConfigError) as ctx: load({**TWO, **change})
        return str(ctx.exception)

    def test_two_owners_load(self):
        st = load(TWO)
        self.assertEqual((st["ownerChats"], st["ownerChat"]), ((MCHAT, GCHAT), MCHAT))
        self.assertEqual(st["chatKeys"], {MCHAT: frozenset({MIKE}), GCHAT: frozenset({GEE})})
        self.assertEqual(st["ownerNames"], {MCHAT: "Mike", GCHAT: "G"})

    def test_without_ownerChats_nothing_new_appears(self):
        st = load({"ownerSenders": [MIKE], "ownerChat": MCHAT, "approvalTtlSeconds": 600})
        for key in ("ownerChats", "chatKeys", "ownerNames"): self.assertNotIn(key, st)

    def test_ownerChat_may_be_left_out_the_first_chat_is_the_main_one(self):
        without = {k: v for k, v in TWO.items() if k != "ownerChat"}
        self.assertEqual(load(without)["ownerChat"], MCHAT)

    def test_ownerChat_must_be_in_ownerChats(self):
        self.assertIn("ownerChat must be one of ownerChats", self.refused(ownerChat=THIRD))

    def test_group_chat_refused(self):
        message = self.refused(ownerChats=[MCHAT, "iMessage;+;chat123"], ownerChat=MCHAT)
        self.assertIn("ownerChats entry 2 is a group chat", message)
        self.assertNotIn("chat123", message)

    def test_address_not_in_ownerSenders_refused_and_not_echoed(self):
        message = self.refused(ownerChats=[MCHAT, THIRD])
        self.assertIn("ownerChats entry 2 is a one-to-one chat with an address that is not in ownerSenders", message)
        self.assertNotIn("third", message)

    def test_duplicate_chat_refused(self):
        self.assertIn("ownerChats has the same chat twice", self.refused(ownerChats=[MCHAT, MCHAT]))

    def test_gChat_may_not_be_an_owner_chat(self):
        self.assertIn("gChat must not be the owner chat", self.refused(gSenders=["gg@example.invalid"], gChat=GCHAT))
        ok = load({**TWO, "gSenders": ["gg@example.invalid"], "gChat": "iMessage;-;gg@example.invalid"})
        self.assertEqual(ok["gChat"], "iMessage;-;gg@example.invalid")

    def test_bad_shapes_refused(self):
        for bad in ("", [], "chat", [""], [5], [MCHAT] * 9, [f"iMessage;-;a{i}@example.invalid" for i in range(9)], ["plain-chat-id"]):
            with self.subTest(bad=bad):
                self.assertIn("ownerChats", self.refused(ownerChats=bad, ownerChat=None, ownerNames=None))

    def test_names_are_short_first_names_for_owner_chats_only(self):
        for bad in ({THIRD: "Mike"}, {MCHAT: ""}, {MCHAT: "Mike Smith"}, {MCHAT: "M1ke"}, {MCHAT: "x" * 21}, {MCHAT: 5}, ["Mike"], {MCHAT: "A;B"}):
            with self.subTest(bad=bad):
                self.assertIn("ownerNames", self.refused(ownerNames=bad))
        self.assertEqual(load({**TWO, "ownerNames": {MCHAT: "Mike"}})["ownerNames"], {MCHAT: "Mike"})
        self.assertEqual(load({k: v for k, v in TWO.items() if k != "ownerNames"})["ownerNames"], {})


class Scripted(conv.FixtureInterpreter):
    def __init__(self, mapping):
        super().__init__(mapping)
        self.asked = []

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        self.asked.append(text)
        return super().interpret(text, pending)


class Base(ConversationTestCase):
    settings = TWO

    def setUp(self):
        super().setUp()
        self.conv.db.close()
        self.set_settings(self.settings)
        self.editor.registry = {**fixture_ops.registry(), "history.revert": load_registry()["history.revert"]}
        self.previewer = FakePreviewer()
        self.interp = Scripted({"hours": _ops((HOURS, {"hours": NEW_HOURS})),
                                "desc": _ops((DESC, {"id": "photo-product-001", "description": "Ripe and creamy."})),
                                "when?": {"question": "Which day should change?"}})
        self.conv = self.open()
        self.addCleanup(lambda: self.conv.db.close())

    def open(self, ed=None):
        return conv.Conversation(str(self.repo.state), ed or self.editor, self.interp, lambda: self.now, getattr(self, "previewer", None))

    def mike(self, text, **kw): return self.say(text, chat=MCHAT, sender=MIKE, **kw)

    def gee(self, text, **kw): return self.say(text, chat=GCHAT, sender=GEE, **kw)

    def sent(self):
        """(chat, text, attachments) for every reply still unsent, then marks them sent."""
        rows = [(r["chat"], r["text"], json.loads(r["attachments"])) for r in self.conv.outbox.unsent()]
        self.conv.flush(self.out)
        return rows

    def outbox_count(self): return self.conv.db.execute("SELECT count(*) FROM outbox").fetchone()[0]

    def asks(self):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'open_requests'").fetchone(): return []
        return [tuple(r) for r in self.conv.db.execute("SELECT provider_id, owner FROM open_requests WHERE state IN ('open', 'drafted')")]

    def mike_makes_a_change(self):
        self.assertEqual(self.mike("hours"), "proposed")
        self.assertEqual(self.mike("yes"), "approved")
        self.sent()
        return self.drafts()[-1]


class ReadingTests(Base):
    def test_each_owner_is_read_in_their_own_chat_and_answered_there(self):
        self.assertEqual(self.mike("status"), "status")
        self.assertEqual([c for c, _t, _a in self.sent()], [MCHAT])
        self.assertEqual(self.gee("status"), "status")
        self.assertEqual([c for c, _t, _a in self.sent()], [GCHAT])

    def test_a_sender_in_the_other_owners_chat_is_ignored(self):
        before = (self.drafts(), self.commits(), self.outbox_count(), self.asks())
        cases = [dict(chat=GCHAT, sender=MIKE), dict(chat=MCHAT, sender=GEE), dict(chat=GCHAT, sender=STRANGER),
                 dict(chat=GROUP, sender=GEE), dict(chat=THIRD, sender=MIKE), dict(chat="iMessage;-;" + STRANGER, sender=STRANGER)]
        for kw in cases:
            for text in ("hours", "yes", "no", "undo", "status", "history", "show", "when?", "stop changes"):
                with self.subTest(case=kw, text=text):
                    self.assertEqual(self.say(text, **kw), "ignored")
        self.assertEqual((self.drafts(), self.commits(), self.outbox_count(), self.asks()), before)
        self.assertEqual(self.interp.asked, [])

    def test_each_owner_can_make_and_approve_their_own_change(self):
        self.mike_makes_a_change()
        self.assertEqual(self.gee("desc"), "proposed")
        self.assertEqual(self.gee("yes"), "approved")
        self.assertEqual(self.commits(), 2)
        self.assertEqual([(d["chat"], d["sender"]) for d in self.drafts()], [(MCHAT, MIKE), (GCHAT, GEE)])
        self.assertTrue(all(c == GCHAT for c, _t, _a in self.sent()))

    def test_plain_chat_ids_are_not_an_owner_chat_when_ownerChats_is_set(self):
        self.assertEqual(self.say("hours", chat="chat-fixture-owner"), "ignored")


class ReplyTests(Base):
    def test_proposal_and_picture_go_to_the_chat_that_asked_for_both_owners(self):
        self.assertEqual(self.mike("hours"), "proposed")
        [(chat, text, pics)] = self.sent()
        self.assertEqual(chat, MCHAT)
        self.assertEqual(len(pics), 1)
        self.assertTrue(pics[0].endswith("-proposal.png"))
        self.assertEqual(self.mike("yes"), "approved")
        self.sent()
        self.assertEqual(self.gee("desc"), "proposed")
        [(chat, text, pics)] = self.sent()
        self.assertEqual((chat, len(pics)), (GCHAT, 1))  # an owner chat gets the preview picture
        self.assertIn("yes", text)
        self.assertEqual(self.gee("yes"), "approved")
        got = self.sent()
        self.assertTrue(got and all(c == GCHAT for c, _t, _a in got))
        self.assertTrue(any(a for _c, _t, a in got))  # the checked result picture too

    def test_gchat_stays_text_only(self):
        self.set_settings({**TWO, "gSenders": ["gg@example.invalid"], "gChat": "iMessage;-;gg@example.invalid"})
        self.conv.db.close()
        self.conv = self.open()
        with self.conv._answer_to("iMessage;-;gg@example.invalid"): self.conv._reply("x", ["a.png"])
        with self.conv._answer_to(GCHAT): self.conv._reply("y", ["a.png"])
        self.assertEqual([(c, a) for c, _t, a in self.sent()], [("iMessage;-;gg@example.invalid", []), (GCHAT, ["a.png"])])

    def test_relay_accepts_each_owner_chat_and_refuses_others(self):
        class Store:
            def __init__(self): self.rows = []
            def add(self, chat, text, pictures, now, shots=()): self.rows.append((chat, text, pictures)); return len(self.rows)
            def unacked(self, chat): return 0
        store = Store()
        sender = relay.RelaySender(store, (MCHAT, GCHAT), lambda: 1, None, "iMessage;-;gg@example.invalid")
        for chat in (MCHAT, GCHAT, "iMessage;-;gg@example.invalid"): sender.send(chat, "hi")
        for chat in (THIRD, GROUP):
            with self.assertRaises(relay.RelayRefused): sender.send(chat, "hi")
        with self.assertRaises(relay.RelayRefused): sender.send("iMessage;-;gg@example.invalid", "hi", ["a.png"])
        # the Mac carries pictures only to its own chat until it is told otherwise: the other owner's text goes alone
        sender.send(MCHAT, "m", ["a.png"])
        sender.send(GCHAT, "g", ["a.png"])
        self.assertEqual(store.rows[-2:], [(MCHAT, "m", 1), (GCHAT, "g", 0)])
        both = relay.RelaySender(store, (MCHAT, GCHAT), lambda: 1, None, None, picture_chats=(MCHAT, GCHAT))
        both.send(GCHAT, "g", ["a.png"])
        self.assertEqual(store.rows[-1], (GCHAT, "g", 1))
        alone = relay.RelaySender(store, MCHAT, lambda: 1)  # one owner chat, as before
        alone.send(MCHAT, "m", ["a.png"])
        self.assertEqual(store.rows[-1], (MCHAT, "m", 1))
        with self.assertRaises(relay.RelayRefused): alone.send(GCHAT, "x")

    def test_worker_keeps_ownerChat_as_the_picture_main_chat_when_ownerChats_is_listed_in_another_order(self):
        # the first relay chat is the picture-capable one (the Mac forwarder sends pictures only to its ownerChat): ownerChat must win
        # over list order, so ownerChat=GCHAT with ownerChats=[MCHAT, GCHAT] keeps GCHAT's previews and MCHAT's picture goes text only
        class Store:
            def __init__(self): self.rows = []
            def add(self, chat, text, pictures, now, shots=()): self.rows.append((chat, text, pictures)); return len(self.rows)
            def unacked(self, chat): return 0
        for main, listed in ((GCHAT, [MCHAT, GCHAT]), (MCHAT, [GCHAT, MCHAT]), (MCHAT, [MCHAT, GCHAT]), (GCHAT, [GCHAT, MCHAT])):
            with self.subTest(main=main, listed=listed):
                settings = load({**TWO, "ownerChat": main, "ownerChats": listed})
                self.assertEqual(settings["ownerChat"], main)
                self.conv.settings = settings
                store = Store()
                with mock.patch.object(host.editor_mod, "content_revision", return_value="rev"):
                    worker = host.Worker(self.conv, SimpleNamespace(handle=lambda *a, **k: None), store, "wt", lambda: None, lambda: _dt.datetime(2026, 1, 1))
                other = GCHAT if main == MCHAT else MCHAT
                self.assertEqual(worker.sender.owner_chat, main)
                self.assertEqual(set(worker.sender.owner_chats), {MCHAT, GCHAT})
                worker.sender.send(main, "m", ["a.png"])
                worker.sender.send(other, "o", ["a.png"])
                self.assertEqual(store.rows, [(main, "m", 1), (other, "o", 0)])  # one picture dropped, only for the non-main chat

    def test_relay_ignores_a_gchat_that_is_an_owner_chat(self):
        sender = relay.RelaySender(None, (MCHAT, GCHAT), lambda: 1, None, GCHAT)
        self.assertIsNone(sender.g_chat)


class ApprovalTests(Base):
    def test_one_owner_cannot_approve_or_cancel_the_others_draft(self):
        self.assertEqual(self.mike("hours"), "proposed")
        draft = self.drafts()[-1]
        self.sent()
        for text in (f"yes {draft['code']}", f"no {draft['code']}", "yes", "no", draft["code"], f"show {draft['code']}", "okay"):
            with self.subTest(text=text):
                self.gee(text)
                for chat, reply, _a in self.sent():
                    self.assertEqual(chat, GCHAT)
                    self.assertNotIn(draft["summary"], reply)
                    self.assertNotIn(draft["code"] + "x", reply)
                self.assertEqual((self.drafts()[0]["state"], self.commits()), ("proposed", 0))
                self.assertEqual(self.editor.applies, 0)
        self.assertEqual(self.gee(f"yes {draft['code']}"), "no-target")
        [(chat, reply, _a)] = self.sent()
        self.assertIn("belongs to Mike", reply)
        self.assertIn("Nothing changed", reply)
        self.assertNotIn("Reply", reply)
        self.assertEqual(self.gee(f"no {draft['code']}"), "no-target")
        self.assertIn("belongs to Mike", self.sent()[0][1])
        self.assertEqual(self.mike(f"yes {draft['code']}"), "approved")  # the owner who made it still can
        self.assertEqual(self.commits(), 1)

    def test_an_approval_row_binds_sender_and_chat(self):
        self.mike_makes_a_change()
        [row] = self.conv.db.execute("SELECT sender, chat FROM approvals").fetchall()
        self.assertEqual((row["sender"], row["chat"]), (MIKE, MCHAT))

    def test_a_yes_sent_by_the_other_owners_sender_into_the_right_chat_is_ignored(self):
        self.assertEqual(self.mike("hours"), "proposed")
        code = self.drafts()[-1]["code"]
        self.assertEqual(self.say(f"yes {code}", chat=MCHAT, sender=GEE), "ignored")
        self.assertEqual(self.commits(), 0)

    def test_without_ownerChats_a_foreign_code_gets_the_old_answer(self):
        self.set_settings({"ownerSenders": [MIKE], "ownerChat": MCHAT, "approvalTtlSeconds": 600})
        self.conv.db.close()
        self.conv = self.open()
        self.assertEqual(self.mike("yes ab12"), "no-target")
        self.assertEqual(self.sent()[0][1], "I don't have a change with that code.")


class UndoAndHistoryTests(Base):
    def test_a_bare_undo_of_the_other_owners_change_asks_first(self):
        theirs = self.mike_makes_a_change()
        commits, states = self.commits(), [d["state"] for d in self.drafts()]
        self.assertEqual(self.gee("undo"), "undo-other")
        [(chat, reply, pics)] = self.sent()
        self.assertEqual((chat, pics), (GCHAT, []))
        self.assertIn("Mike's change", reply)
        self.assertIn("I haven't undone anything", reply)
        self.assertIn(f"undo {theirs['code']}", reply)
        self.assertEqual((self.commits(), [d["state"] for d in self.drafts()]), (commits, states))

    def test_undo_with_their_code_is_a_proposal_that_names_whose_change_it_is(self):
        theirs = self.mike_makes_a_change()
        self.assertEqual(self.gee(f"undo {theirs['code']}"), "proposed")
        [(chat, reply, _p)] = self.sent()
        self.assertEqual(chat, GCHAT)
        self.assertTrue(reply.startswith("To undo Mike's change"), reply)
        undo = self.drafts()[-1]
        self.assertEqual(undo["chat"], GCHAT)
        self.assertEqual(self.mike(f"yes {undo['code']}"), "no-target")  # Mike cannot approve G's undo either
        self.sent()
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.gee(f"yes {undo['code']}"), "approved")
        self.assertEqual(self.commits(), 2)

    def test_undo_of_your_own_last_change_is_unchanged(self):
        self.mike_makes_a_change()
        self.assertEqual(self.mike("undo"), "proposed")
        [(chat, reply, _p)] = self.sent()
        self.assertEqual(chat, MCHAT)
        self.assertTrue(reply.startswith("To undo that, I'd change it back:"), reply)

    def test_the_last_change_for_the_site_is_the_one_a_bare_undo_sees(self):
        mine = self.mike_makes_a_change()
        self.assertEqual(self.gee("desc"), "proposed")
        self.assertEqual(self.gee("yes"), "approved")
        self.sent()
        self.assertEqual(self.mike("undo"), "undo-other")  # G's newer change is the site's last one
        self.assertIn("G's change", self.sent()[0][1])
        self.assertEqual(self.gee("undo"), "proposed")  # G's own
        self.sent()
        self.assertEqual(self.mike(f"undo {mine['code']}"), "writer-busy")  # G's undo is waiting: the site has one writer
        self.assertIn("G has a change waiting", self.sent()[0][1])

    def test_nothing_to_undo_alone(self):
        self.assertEqual(self.gee("undo"), "no-target")
        self.assertEqual(self.sent()[0][1], "There's nothing to undo.")

    def test_history_says_whose_change_each_one_was(self):
        self.mike_makes_a_change()
        self.assertEqual(self.gee("desc"), "proposed")
        self.assertEqual(self.gee("yes"), "approved")
        self.sent()
        self.assertEqual(self.gee("history"), "history")
        [(chat, reply, _p)] = self.sent()
        self.assertEqual(chat, GCHAT)
        lines = reply.splitlines()[1:]
        self.assertTrue(lines[0].startswith("- Your change, "), lines)
        self.assertTrue(lines[1].startswith("- Mike's change, "), lines)
        self.assertEqual(self.mike("history"), "history")
        lines = self.sent()[0][1].splitlines()[1:]
        self.assertTrue(lines[0].startswith("- G's change, ") and lines[1].startswith("- Your change, "), lines)
        self.assertEqual(self.mike("history hours"), "history")
        self.assertTrue(self.sent()[0][1].splitlines()[1].startswith("- Your change, "))

    def test_the_default_name_is_the_owner(self):
        self.set_settings({k: v for k, v in TWO.items() if k != "ownerNames"})
        self.conv.db.close()
        self.conv = self.open()
        self.mike_makes_a_change()
        self.assertEqual(self.gee("undo"), "undo-other")
        self.assertIn("the owner's change", self.sent()[0][1])

    def test_status_names_whose_last_change_it_was_and_hides_the_others_waiting_words(self):
        theirs = self.mike_makes_a_change()
        self.assertEqual(self.gee("status"), "status")
        self.assertIn("Last change (Mike's change)", self.sent()[0][1])
        self.assertEqual(self.mike("status"), "status")
        self.assertNotIn("Mike's change", self.sent()[0][1])
        self.assertEqual(self.gee("desc"), "proposed")
        waiting = self.drafts()[-1]
        self.sent()
        self.mike("status")
        [(_c, text, _a)] = self.sent()
        self.assertIn("G has a change waiting.", text)
        self.assertNotIn(waiting["summary"], text)
        self.assertNotIn(waiting["code"], text)
        self.gee("status")
        self.assertIn(waiting["code"], self.sent()[0][1])
        self.assertIsNotNone(theirs)


class OneWriterTests(Base):
    def test_a_second_owner_gets_a_plain_answer_while_a_draft_is_waiting(self):
        self.assertEqual(self.mike("hours"), "proposed")
        self.sent()
        drafts, asked = self.drafts(), list(self.interp.asked)
        self.assertEqual(self.gee("desc"), "writer-busy")
        [(chat, reply, pics)] = self.sent()
        self.assertEqual((chat, pics), (GCHAT, []))
        self.assertTrue(reply.startswith("Mike has a change waiting, so I haven't started yours."), reply)
        self.assertEqual((self.drafts(), self.interp.asked), (drafts, asked))  # nothing drafted, no model call, nothing counted
        self.assertEqual(self.gee("hours"), "writer-busy")  # even the same words
        self.sent()
        self.assertEqual(self.mike("no"), "rejected")  # once it is cancelled the writer is free
        self.sent()
        self.assertEqual(self.gee("desc"), "proposed")

    def test_a_question_waiting_for_details_holds_the_writer_too(self):
        self.interp.mapping["half"] = _ops((HOURS, {}))
        self.assertEqual(self.mike("half"), "needs-details")
        self.sent()
        self.assertEqual(self.gee("desc"), "writer-busy")
        self.assertIn("Mike has a change waiting", self.sent()[0][1])

    def test_an_expired_draft_frees_the_writer(self):
        self.assertEqual(self.mike("hours"), "proposed")
        self.sent()
        self.now = self.now.replace(hour=self.now.hour + 1)
        self.assertEqual(self.gee("desc"), "proposed")

    def test_the_same_owner_is_not_held_by_their_own_draft(self):
        self.assertEqual(self.mike("hours"), "proposed")
        self.assertEqual(self.mike("desc"), "proposed")

    def test_an_undo_waits_too(self):
        theirs = self.mike_makes_a_change()
        self.assertEqual(self.gee("desc"), "proposed")
        self.sent()
        self.assertEqual(self.mike(f"undo {theirs['code']}"), "writer-busy")
        self.assertEqual(self.commits(), 1)

    def test_a_photo_waits_too_and_is_not_even_fetched(self):
        class Photos:
            def fetch(self, provider_id, n): raise AssertionError("fetched")
        self.set_settings({**TWO, "mediaRoot": str(self.repo.state / "media")})
        self.conv.db.close()
        self.conv = conv.Conversation(str(self.repo.state), self.editor, self.interp, lambda: self.now, self.previewer, Photos())
        self.assertEqual(self.mike("hours"), "proposed")
        self.sent()
        self.n += 1
        msg = conv.Inbound(f"m{self.n}", GCHAT, GEE, "", False, "new", self.now.isoformat(), 1)
        self.assertEqual(self.conv.handle(msg), "writer-busy")
        self.assertIn("Mike has a change waiting", self.sent()[0][1])

    def test_an_open_release_holds_the_writer_for_the_other_owner_only(self):
        self.editor.open_release = lambda: MCHAT
        self.assertEqual(self.gee("desc"), "writer-busy")
        reply = self.sent()[0][1]
        self.assertIn("Mike's change is going on the website right now, so I haven't started yours.", reply)
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.mike("hours"), "proposed")  # the asker of that release is not held by it
        self.assertEqual(self.mike("no"), "rejected")
        self.editor.open_release = lambda: None
        self.assertEqual(self.gee("when?"), "question")

    def test_an_unreadable_release_book_does_not_hold_the_writer(self):
        self.editor.open_release = lambda: None
        self.assertEqual(self.gee("desc"), "proposed")


class SharedStateTests(Base):
    def test_open_requests_are_kept_per_chat(self):
        self.assertEqual(self.mike("when?"), "question")
        self.sent()
        self.assertEqual(self.asks(), [("m1", MCHAT)])
        self.gee("Friday")
        self.gee("no")
        self.assertEqual(self.asks(), [("m1", MCHAT)])
        self.assertEqual(self.gee("when?"), "question")
        self.assertEqual(sorted(c for _p, c in self.asks()), sorted([MCHAT, GCHAT]))

    def test_pause_and_the_daily_limit_are_shared(self):
        self.set_settings({**TWO, "interpreterDailyCap": 1})
        self.conv.db.close()
        self.conv = self.open()
        self.assertEqual(self.mike("when?"), "question")
        self.assertEqual(self.gee("when?"), "daily-limit")
        self.assertEqual(self.mike("pause changes"), "pause")
        self.sent()
        self.assertEqual(self.gee("status"), "status")
        self.assertIn("paused", self.sent()[0][1])
        self.assertEqual(self.gee("resume changes"), "resume")
        self.assertIsNone(self.conv._paused())

    def test_a_paused_site_holds_back_both_owners_yes(self):
        self.assertEqual(self.mike("hours"), "proposed")
        self.assertEqual(self.gee("pause changes"), "pause")
        self.assertEqual(self.mike("yes"), "paused")
        self.assertEqual(self.commits(), 0)

    def test_a_restart_keeps_every_owners_drafts_and_chats(self):
        self.assertEqual(self.mike("hours"), "proposed")
        self.conv.db.close()
        self.conv = self.open()
        self.assertEqual(self.gee("yes"), "no-target")
        self.assertEqual(self.mike("yes"), "approved")


if __name__ == "__main__":
    unittest.main()
