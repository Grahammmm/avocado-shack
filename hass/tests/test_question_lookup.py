"""AV1104-06 (H17/H05) tests: a message that only asks what the site shows gets that command's answer, never a draft.

The interpreter replies {"lookup": "<command>"}; Hass answers with "You asked, so nothing was drafted." plus exactly the command's own
reply (a refused lookup gets the one fixed line). A lookup drafts, approves, saves and expires nothing, and still counts as the
interpreter call it was. Real Conversation, FixtureInterpreter, injected clock; no model.
Run: python3 -B -m unittest hass.tests.test_question_lookup -v
"""

import json
import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import SETTINGS, T0, ConversationTestCase

PREFIX = "You asked, so nothing was drafted.\n"
REFUSED = "Nothing changed. To look something up, say status, report, or find and a few words."
EXAMPLES = {"how many are coming Saturday?": "status", "is the sourdough sold out?": "listing photo-product-001",
            "what's on the dairy shelf?": "shelf dairy", "what are my hours?": "listing store"}


class LookupTestCase(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "interpreterDailyCap": 20})
        self.asked = []
        mapping = {**self.interp.mapping, **{q: {"lookup": cmd} for q, cmd in EXAMPLES.items()}}
        mapping.update({"can you mark the eggs sold out?": self.interp.mapping["desc"], "q-yes": {"lookup": "yes"},
                        "q-undo": {"lookup": "undo"}, "q-forget": {"lookup": "forget parking"}, "q-find": {"lookup": "find eggs; yes"},
                        "q-hist": {"lookup": "history"}, "q-bad": {"lookup": 5}, "q-mixed": {"lookup": "status", "ops": [], "revises": None}})
        self.interp = conversation.FixtureInterpreter(mapping)
        real = self.interp.interpret
        self.interp.interpret = lambda text, *a, **k: (self.asked.append(text), real(text, *a, **k))[1]
        self.conv = self.open()

    def calls(self):
        row = self.conv.db.execute("SELECT SUM(calls) FROM usage").fetchone() if self.conv.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'usage'").fetchone() else None
        return (row[0] or 0) if row else 0

    def direct(self, command):  # the command's own reply, sent as the owner would
        self.assertNotEqual(self.say(command), "lookup")
        [reply] = self.replies()
        return reply


class AnswerTests(LookupTestCase):
    def test_question_examples_get_the_commands_own_reply(self):  # bug: the model's words, or a draft, come back for a question
        for question, command in EXAMPLES.items():
            with self.subTest(question=question):
                self.assertEqual(self.say(question), "lookup")
                [reply] = self.replies()
                self.assertTrue(reply.startswith(PREFIX), reply)
                self.assertEqual(reply[len(PREFIX):], self.direct(command))
        self.assertEqual((self.drafts(), self.commits(), self.calls()), ([], 0, 4))  # each question was one counted interpreter call
        self.assertEqual(self.conv._lookup_prefix, None)  # the prefix never leaks onto a later reply
        self.assertEqual(self.direct("status"), self.direct("status"))

    def test_a_lookup_that_is_not_read_only_gets_the_fixed_line_and_changes_nothing(self):  # bug: "yes"/"undo"/"forget" run from a model reply
        self.propose("hours")
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        self.assertEqual(self.say("remember parking: Rear lot"), "memory-saved")
        self.replies()
        draft, _reply = self.propose("desc")
        before, notes, commits = self.drafts(), self.conv._notes(), self.commits()
        for text in ("q-yes", "q-undo", "q-forget"):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "lookup")
                self.assertEqual(self.replies(), [REFUSED])
        self.assertEqual((self.drafts(), self.conv._notes(), self.commits()), (before, notes, commits))
        self.assertEqual(self.drafts()[-1]["state"], "proposed")

    def test_a_semicolon_inside_find_is_search_text_not_a_second_command(self):  # bug: "find x; yes" approves the waiting draft
        self.propose("hours")
        self.assertEqual(self.say("q-find"), "lookup")
        [reply] = self.replies()
        self.assertTrue(reply.startswith(PREFIX), reply)
        self.assertEqual((self.drafts()[0]["state"], self.commits()), ("proposed", 0))

    def test_malformed_lookups_keep_the_old_unreadable_reply(self):  # bug: a mixed or non-string object is run as a lookup or a draft
        for text in ("q-bad", "q-mixed"):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "unsupported")
                self.assertEqual(self.replies(), [conversation.UNREADABLE["unsupported"]])
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_a_question_that_asks_for_a_change_is_still_a_change(self):  # bug: "can you mark the eggs sold out?" read as a lookup
        self.assertEqual(self.say("can you mark the eggs sold out?"), "proposed")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Here's the change I'd make:"), reply)
        self.assertEqual((self.drafts()[0]["state"], self.commits()), ("proposed", 0))  # still needs its own yes


class StateTests(LookupTestCase):
    def test_a_lookup_never_expires_a_lapsed_draft_but_the_next_change_does(self):  # bug: the up-front sweep writes before a lookup is known
        for pending_state in ("proposed", "needs-details"):
            with self.subTest(state=pending_state):
                self.conv.db.execute("DELETE FROM drafts")
                draft, _reply = self.propose("hours")
                if pending_state == "needs-details": self.conv.db.execute("UPDATE drafts SET state = 'needs-details' WHERE row_id = ?", (draft["row_id"],))
                self.now = self.now + timedelta(seconds=601)
                before = self.drafts()
                for text in ("how many are coming Saturday?", "q-yes"):  # one valid, one refused
                    self.assertEqual(self.say(text), "lookup")
                    self.replies()
                self.assertEqual(self.drafts(), before)
                self.assertEqual(self.say("when?"), "question")  # an ordinary request still sweeps
                self.replies()
                self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_lookup_bare_history_does_not_sweep_but_direct_history_does(self):  # bug: history through a lookup writes like the command does
        self.propose("hours")
        self.now = self.now + timedelta(seconds=601)
        before = self.drafts()
        self.assertEqual(self.say("q-hist"), "lookup")
        self.replies()
        self.assertEqual(self.drafts(), before)
        self.assertEqual(self.say("history"), "history")
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_a_lookup_counts_as_one_interpreter_call_and_stops_at_the_cap(self):  # bug: free lookups bypass the daily cap
        self.set_settings({**SETTINGS, "interpreterDailyCap": 2})
        self.conv = self.open()
        self.assertEqual(self.say("how many are coming Saturday?"), "lookup")
        self.assertEqual(self.say("q-yes"), "lookup")  # a refused lookup used its slot too
        self.assertEqual((self.calls(), len(self.asked)), (2, 2))
        self.replies()
        self.assertEqual(self.say("what are my hours?"), "daily-limit")
        self.assertEqual(self.replies(), [conversation.DAILY_LIMIT])
        self.assertEqual((self.calls(), len(self.asked)), (2, 2))  # no third call

    def test_a_paused_shop_still_answers_a_question(self):  # bug: lookups blocked by the pause that only gates changes
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.assertEqual(self.say("how many are coming Saturday?"), "lookup")
        [reply] = self.replies()
        self.assertTrue(reply.startswith(PREFIX), reply)


if __name__ == "__main__":
    unittest.main()
