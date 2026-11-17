"""AV2007-14 (QA1-07 part 2): a question asked while a draft waits survives the yes that saves the draft.

Real Conversation, fixture editor and interpreter, injected clock. Run: python3 -B -m unittest hass.tests.test_second_question -v
"""
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, owner_answers as answers, voice
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS, _req

ASK = "Which day is Thanksgiving this year: Thursday, November 26, or another date?"
NOTICE = "put a notice up: closed thanksgiving day"
LINE = "I still need your answer to this: " + ASK


class SecondQuestionTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        mapping = self.interp.mapping
        mapping[NOTICE] = {"question": ASK}
        mapping["thursday the 26th"] = _ops((HOURS, {"hours": NEW_HOURS}))
        mapping["half"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}
        self.seen = []
        real = self.interp.interpret
        self.interp.interpret = lambda text, pending, **kw: (self.seen.append((text, kw.get("recent"))), real(text, pending, **kw))[1]
        strict = mock.patch.object(conversation.Outbox, "strict", True)
        strict.start()
        self.addCleanup(strict.stop)

    def waiting_then_question(self):
        row, _ = self.propose("hours")
        self.assertEqual(self.say(NOTICE), "question")
        self.assertEqual(self.replies(), [ASK])
        return row

    def test_yes_saves_the_draft_and_repeats_the_open_question(self):
        self.waiting_then_question()
        self.assertEqual(self.say("yes"), "approved")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Saved: "), reply)
        self.assertEqual(reply.splitlines()[-1], LINE)
        self.assertEqual(self.commits(), 1)

    def test_yes_with_a_previewer_repeats_it_in_the_checked_reply(self):
        row = self.waiting_then_question()
        self.conv.previewer = object()
        with mock.patch.object(self.conv, "verify", return_value=("fixture-result.png", None)):
            self.assertEqual(self.say(f"yes {row['code']}"), "approved")
            [reply] = self.replies()
        self.assertEqual(reply.splitlines()[-1], LINE)
        self.assertEqual(reply.count("I still need your answer"), 1)

    def test_not_verified_reply_repeats_it_too(self):
        self.waiting_then_question()
        self.conv.previewer = object()
        with mock.patch.object(self.conv, "verify", return_value=(None, "private failure")):
            self.say("yes")
            [reply] = self.replies()
        self.assertEqual(reply.splitlines()[-1], LINE)
        self.assertNotIn("private failure", reply)

    def test_the_answer_after_the_yes_keeps_its_question(self):
        self.waiting_then_question()
        self.say("yes")
        self.replies()
        self.say("thursday the 26th")
        self.assertEqual(self.seen[-1], ("thursday the 26th", {"question": ASK, "earlier": [NOTICE]}))
        self.assertEqual(len([d for d in self.drafts() if d["state"] == "applied"]), 1)

    def test_status_lists_the_open_question_next_to_the_draft(self):
        self.waiting_then_question()
        self.assertEqual(self.say("status"), "status")
        text = self.replies()[0]
        self.assertIn("Waiting for your yes:", text)
        self.assertEqual(text.count(f"Waiting for your answer: {ASK}"), 1)
        self.assertLess(text.index("Waiting for your yes:"), text.index("Waiting for your answer:"))
        self.say("no")  # the bare no drops the question first
        self.replies()
        self.say("status")
        self.assertNotIn("Waiting for your answer", self.replies()[0])

    def test_status_loses_the_line_once_answered(self):
        self.waiting_then_question()
        self.say("thursday the 26th")
        self.replies()
        self.say("status")
        self.assertNotIn("Waiting for your answer", self.replies()[0])

    def test_paused_yes_approves_nothing_and_repeats_nothing(self):
        self.waiting_then_question()
        self.say("stop changes")
        self.replies()
        self.assertEqual(self.say("yes"), "paused")
        [reply] = self.replies()
        self.assertNotIn("I still need your answer", reply)
        self.assertEqual(self.commits(), 0)

    def test_no_question_no_extra_line(self):
        row, _ = self.propose("hours")
        self.say("yes")
        self.assertEqual(self.replies(), [voice.plain(answers.applied_text(row["code"], row["summary"]))])

    def test_an_expired_question_is_not_repeated(self):
        self.set_settings({**SETTINGS, "approvalTtlSeconds": 3600})
        self.conv = self.open()
        row = self.waiting_then_question()
        self.now = T0 + timedelta(minutes=31)
        self.assertEqual(self.say(f"yes {row['code']}"), "approved")
        [reply] = self.replies()
        self.assertNotIn("I still need your answer", reply)

    def test_needs_details_row_is_repeated_once(self):
        self.assertEqual(self.say("half"), "needs-details")
        asked = self.drafts()[-1]["summary"]
        self.replies()
        self.say("hours")
        self.replies()
        self.say("yes")
        [reply] = self.replies()
        self.assertEqual(reply.splitlines()[-1], "I still need your answer to this: " + asked)
        self.assertEqual(reply.count("I still need your answer"), 1)

    def test_another_owners_question_is_not_repeated(self):
        self.waiting_then_question()
        self.conv.settings["ownerSenders"] = [OWNER, "g@example.invalid"]
        self.conv.settings["ownerChats"] = (CHAT, "chat-g")
        self.conv.settings["chatKeys"] = {CHAT: frozenset({OWNER}), "chat-g": frozenset({"g@example.invalid"})}
        self.conv.settings["ownerNames"] = {CHAT: "Mike", "chat-g": "G"}
        self.say("status", chat="chat-g", sender="g@example.invalid")
        self.assertNotIn(ASK, " ".join(self.replies()))

    def test_a_pending_shelf_ask_is_not_repeated(self):
        self.waiting_then_question()
        with mock.patch.object(self.conv.requests, "get", side_effect=lambda *a, **k: {
                "state": "open", "skill": None, "pending": {"ops": []}, "attachments": [], "question": ASK}):
            self.assertIsNone(self.conv._legacy_question(self.now))

    def test_lookup_failure_keeps_the_saved_reply(self):
        row, _ = self.propose("hours")
        with mock.patch.object(self.conv.requests, "get", side_effect=ValueError("bad json")):
            self.say("yes")
        [reply] = self.replies()
        self.assertEqual(reply, voice.plain(answers.applied_text(row["code"], row["summary"])))


if __name__ == "__main__":
    unittest.main()
