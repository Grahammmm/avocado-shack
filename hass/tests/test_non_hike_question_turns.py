"""AV2007-13 (QA1-07 part 1): while a non-hike question is open, only an answer is taken as its answer.
A malformed coded yes, another topic and a bare no each leave the question's context intact or drop it plainly.
Run: python3 -m unittest hass.tests.test_non_hike_question_turns -v
"""
import unittest
from datetime import timedelta

from hass import conversation
from hass.chat.commands import parse_unknown_code
from hass.tests.test_conversation import ConversationTestCase

DROPPED = "Okay, I've dropped that question"


class QuestionTurnTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.asked = []
        outer = self

        class Recording(conversation.FixtureInterpreter):
            def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
                outer.asked.append((text, recent))
                return super().interpret(text, pending)

        self.interp = Recording({**self.interp.mapping, "whats on special": {"unsupported": "Nothing is on special."}})
        self.conv = self.open()
        self.assertEqual(self.say("when?"), "question")
        self.replies()
        self.calls = len(self.asked)

    def say(self, text, **kw):
        self.now += timedelta(seconds=1)  # each message has its own received time
        return super().say(text, **kw)

    def question_open(self):
        return self.conv._recent_question(self.now) is not None

    def test_unknown_code_is_refused_and_the_question_stays_open(self):
        self.assertEqual(self.say("yes 9z9z"), "no-target")
        self.assertIn("I don't have a change with that code.", self.replies()[0])
        self.assertEqual(len(self.asked), self.calls)  # no model call
        self.assertEqual(self.commits(), 0)
        self.assertTrue(self.question_open())
        self.say("hours")
        self.assertEqual(self.asked[-1][1], {"question": "Which day should change?", "earlier": ["when?"]})

    def test_other_topic_is_its_own_message_and_the_question_stays_open(self):
        self.assertEqual(self.say("whats on special"), "unsupported")
        self.assertEqual(self.replies(), ["Nothing is on special."])
        self.assertEqual(self.asked[-1], ("whats on special", None))  # none of the question's context
        self.assertTrue(self.question_open())
        self.say("hours")
        self.assertEqual(self.asked[-1][1], {"question": "Which day should change?", "earlier": ["when?"]})

    def test_bare_no_drops_the_question(self):
        self.assertEqual(self.say("no"), "cancelled")
        self.assertEqual(self.replies(), [DROPPED])
        self.assertFalse(self.question_open())
        self.assertEqual(self.say("no"), "no-target")  # nothing left to drop
        self.assertEqual(self.replies(), ["Nothing is waiting for your yes."])

    def test_no_with_an_unknown_code_does_not_drop_the_question(self):
        self.assertEqual(self.say("no 9z9z"), "no-target")
        self.assertTrue(self.question_open())
        self.assertEqual(self.say("no abcd"), "no-target")
        self.assertTrue(self.question_open())

    def test_the_hold_does_not_renew_the_question(self):
        self.now += timedelta(minutes=20)
        self.say("yes 9z9z")
        self.now += timedelta(minutes=11)
        self.say("hours")
        self.assertIsNone(self.asked[-1][1])

    def test_a_different_message_in_between_still_drops_the_context(self):
        self.say("yes 9z9z")
        self.say("status")
        self.say("hours")
        self.assertIsNone(self.asked[-1][1])

    def test_plain_words_and_valid_codes_are_not_unknown_codes(self):
        for text in ("yes please", "no thanks", "yes a1b2", "yes 9z9z?", "yes 9z9z today", "yes"):
            self.assertIsNone(parse_unknown_code(text), text)
        self.assertEqual(parse_unknown_code("Yes 9Z9Z."), "9z9z")


if __name__ == "__main__":
    unittest.main()
