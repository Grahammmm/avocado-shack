"""AV0007-07 (H05/H17): a whole message of only thanks, a greeting or emoji never reaches the interpreter or the count.

Run: python3 -B -m unittest hass.tests.test_social_message -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.social_message import classify_social
from hass.tests.test_near_approval import NearApprovalTests, TextInterpreter
from hass.tests.test_undo import H06TestCase

HEART, AVOCADO, FAMILY = "\u2764\ufe0f", "\U0001F951", "\U0001F468\u200d\U0001F469\u200d\U0001F467\u200d\U0001F466"
FLAG_US, KEYCAP = "\U0001F1FA\U0001F1F8", "1\ufe0f\u20e3"
FLAG_ENG = "\U0001F3F4" + "".join(chr(0xE0000 + ord(c)) for c in "gbeng") + "\U000E007F"
THUMB, THUMB_SKIN, OK_HAND = "\U0001F44D", "\U0001F44D\U0001F3FD", "\U0001F44C"
CHECKS = ("\u2705", "\u2714\ufe0f", "\u2611\ufe0f")


class ClassifierTests(unittest.TestCase):
    def test_exact_social_phrases_and_real_word_fallthrough(self):
        for text in ("thanks", "Thank you!", "  GREAT,   thanks. ", "hi", "Hello?", "good\n morning!!"):
            with self.subTest(text=text):
                self.assertEqual(classify_social(text), "social")
        for text in ("thanks, make the eggs sold out", "hi change hours", "great thanks for the eggs", "hello there",
                     "", "   ", "!!!", "...", "спасибо", "bonjour", "thanks \U0001F951", "yes", "123"):
            with self.subTest(text=text):
                self.assertIsNone(classify_social(text))

    def test_emoji_units_and_nonemoji_rejection(self):
        for text in (AVOCADO, HEART, FAMILY, FLAG_US, KEYCAP, FLAG_ENG, "\U0001F469\U0001F3FD\u200d\U0001F373", "\u00a9\ufe0f"):
            with self.subTest(text=text):
                self.assertEqual(classify_social(text), "social")
        for text in ("\ufe0f", "\u200d", "\U0001F3FD", "\U000E0067", "\U0001F1FA", "\U0001F1FA\U0001F1F8\U0001F1FA",
                     AVOCADO + "\u200d", "\u200d" + AVOCADO, "1\u20e3\u20e3", "\u20e3", "#", "5", "*",
                     "\u00a9 thanks", "\u00a9 x", "\u2192", "\u03c0", "\U0001F3F4\U000E0067", "\U0001F3F4" + "\U000E0067" * 2,
                     AVOCADO + ".", "\ud800", "\U0001F600\U0001F600x"):
            with self.subTest(text=text):
                self.assertIsNone(classify_social(text))

    def test_approval_emoji_set_and_mixed_emoji_fallback(self):
        for text in (THUMB, THUMB_SKIN, OK_HAND, *CHECKS, THUMB + " " + CHECKS[0], THUMB * 3, OK_HAND + THUMB + "\u2705"):
            with self.subTest(text=text):
                self.assertEqual(classify_social(text), "near")
        for text in (THUMB + " " + AVOCADO, HEART, FLAG_US, FAMILY, THUMB + FLAG_US):
            with self.subTest(text=text):
                self.assertEqual(classify_social(text), "social")
        for text in (THUMB + " yes", "thanks " + AVOCADO, THUMB + " a1b2", "I love " + AVOCADO + " thanks"):
            with self.subTest(text=text):
                self.assertIsNone(classify_social(text))

    def test_vs16_then_skin_modifier(self):
        for text in (THUMB + "\ufe0f\U0001F3FD", OK_HAND + "\ufe0f\U0001F3FD"):
            with self.subTest(text=text):
                self.assertEqual(classify_social(text), "near")
        self.assertEqual(classify_social("\U0001F469\ufe0f\U0001F3FD\u200d\U0001F373"), "social")

    def test_long_emoji_is_linear_and_still_social(self):
        self.assertEqual(classify_social(AVOCADO * 20000), "social")
        self.assertEqual(classify_social(THUMB * 20000), "near")


def _flag(payload, end="\U000E007F"):
    return "\U0001F3F4" + "".join(chr(0xE0000 + ord(c)) for c in payload) + end


SCOT, WALES = "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F", \
    "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F"
UNKNOWN_TAGS = (_flag("!"), _flag("123"), _flag(" "), _flag("GBENG"), _flag("gb!eng"), _flag("gbxyz"), _flag("gbeng" * 2),
                _flag(""), _flag("gbeng", ""), _flag("gbeng") + "\U000E007F", _flag("gbeng") + "\U000E0067",
                _flag("gbeng") + _flag("gb!eng"), _flag("gbeng") + "x", "\U000E0067" + _flag("gbeng"),
                _flag("gbeng" + "a" * 5000))


class FlagTagTests(unittest.TestCase):
    def test_supported_subdivision_flags_are_social(self):
        for text in (FLAG_ENG, SCOT, WALES, FLAG_ENG + SCOT + " " + WALES, AVOCADO + FLAG_ENG + " " + HEART, "\U0001F3F4"):
            with self.subTest(text=text):
                self.assertEqual(classify_social(text), "social")

    def test_unknown_or_incomplete_tag_runs_fall_through(self):
        for text in UNKNOWN_TAGS + (AVOCADO + _flag("!"), "hi " + FLAG_ENG):
            with self.subTest(text=text[:12]):
                self.assertIsNone(classify_social(text))


class SocialConversationTests(H06TestCase):
    FIXED = "Nothing changed. Tell me what you'd like to change, or say help."
    def setUp(self):
        super().setUp()
        self.interp = TextInterpreter(self.interp.mapping)
        self.conv = self.open()

    proposal, approvals, usage, near, one = (getattr(NearApprovalTests, n) for n in
                                             ("proposal", "approvals", "usage", "near", "one"))

    def advance_past_expiry(self):
        self.now += timedelta(seconds=601)  # SETTINGS approvalTtlSeconds is 600

    def social(self, text, pid=None):
        drafts, usage = self.drafts(), self.usage()
        self.assertEqual(self.say(text), "social")
        self.assertEqual(self.replies(), [self.FIXED])
        self.assertEqual((self.drafts(), self.approvals(), self.commits()), (drafts, 0, 0))
        self.assertEqual((self.interp.texts, self.usage()), ([], usage))

    def test_social_has_no_call_count_draft_or_apply(self):
        draft = self.proposal()
        for text in ("thanks", "Thank you!", "hello", AVOCADO, HEART * 2, "good morning"):
            with self.subTest(text=text):
                self.social(text)
        self.assertEqual(self.drafts()[-1]["state"], "proposed")
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")  # explicit approval still works

    def test_vs16_skin_modifier_no_call_no_count(self):
        self.social("\U0001F469\ufe0f\U0001F3FD\u200d\U0001F373")
        usage = self.usage()
        self.assertEqual(self.say(THUMB + "\ufe0f\U0001F3FD"), "near-approval")
        self.replies()
        self.assertEqual((self.interp.texts, self.usage()), ([], usage))

    def test_social_while_paused(self):
        self.assertEqual(self.say("pause"), "pause")
        self.replies()
        self.social("thanks")

    def test_near_emoji_one_many_none_question_expired(self):
        self.near(THUMB, "Nothing is waiting for your yes.")
        one = self.proposal("hours")
        self.near(THUMB, self.one(one["code"]))
        self.near(CHECKS[0], self.one(one["code"]))
        two = self.proposal("desc")
        self.near(OK_HAND, f"I haven't changed anything yet. Which one do you want?\nyes {one['code']}: {one['summary']}\nyes {two['code']}: {two['summary']}")
        self.advance_past_expiry()
        self.assertEqual(self.say(THUMB), "near-approval")  # the normal sweep expires both; nothing is renewed or applied
        self.assertEqual(self.replies(), ["Nothing is waiting for your yes."])
        self.assertEqual(({d["state"] for d in self.drafts()}, self.approvals(), self.interp.texts), ({"expired"}, 0, []))

    def test_unknown_flag_reaches_interpreter_unchanged_known_flag_does_not(self):
        self.social(FLAG_ENG)
        for text in (_flag("!"), _flag("gbeng", "")):
            with self.subTest(text=text[:6]):
                self.interp.texts.clear()
                drafts = self.drafts()
                self.assertNotEqual(self.say(text), "social")
                self.replies()
                self.assertEqual(self.interp.texts, [text])
                self.assertEqual((self.approvals(), self.commits(), self.drafts()), (0, 0, drafts))

    def test_duplicate_gets_one_reply_and_mixed_words_still_interpreted(self):
        self.assertEqual(self.say("thanks", pid="dup1"), "social")
        self.assertEqual(self.say("thanks", pid="dup1"), "duplicate")
        self.assertEqual(self.replies(), [self.FIXED])
        self.say("thanks, hours")
        self.assertEqual(self.interp.texts, ["thanks, hours"])


if __name__ == "__main__":
    unittest.main()
