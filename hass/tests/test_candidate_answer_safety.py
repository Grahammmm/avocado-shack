"""Whole-answer choices and the real conversation's interpreter fallback (offline fixtures)."""
import json
import unittest
from datetime import timedelta

from hass.skills import openreq
from hass.skills.model import Slot
from hass.tests import test_skill_dispatch as fixtures

ASK = {"ids": ["photo-product-015", "photo-product-122"],
       "names": ["Sourdough bread", "Rye bread"]}
PRODUCT = Slot("product", "product_ref", True)
REJECTED = ("not 2", "not the first one", "1 or 2", "neither 1 nor 2", "2 maybe")


class CandidateParserTests(unittest.TestCase):
    def test_rejected_and_competing_numbers_do_not_choose(self):
        for text in REJECTED:
            with self.subTest(text=text):
                self.assertIsNone(openreq.pick_candidate(text, ASK))
                self.assertEqual(openreq.cheap_answer(PRODUCT, text, ask=ASK), (False, None))

    def test_whole_answer_numeric_choices_preserve_index_binding(self):
        ask = {"ids": [f"item-{n}" for n in range(1, 11)],
               "names": [f"Candidate {n}" for n in range(1, 11)]}
        for ordinal, n in openreq.ORDINALS.items():
            for choice in (str(n), ordinal):
                for prefix in ("", "the "):
                    for suffix in ("", " one", " please", " one please"):
                        for punctuation in ("", ".", "!", "?", ",", ";", ":"):
                            text = f"  {prefix}{choice}{suffix}{punctuation}  ".upper()
                            with self.subTest(text=text):
                                self.assertEqual(openreq.pick_candidate(text, ask), f"item-{n}")
                                self.assertEqual(openreq.cheap_answer(PRODUCT, text, ask=ask),
                                                 (True, f"item-{n}"))
        for text in ("", "0", "11", "the zeroth one"):
            with self.subTest(text=text):
                self.assertIsNone(openreq.pick_candidate(text, ask))
        for ask in ({}, {"ids": ["a"], "names": []}):
            self.assertIsNone(openreq.pick_candidate("1", ask))
        for text, expected in (("the rye one", ASK["ids"][1]), ("sourdough", ASK["ids"][0]),
                               ("bread", None)):
            self.assertEqual(openreq.pick_candidate(text, ASK), expected)

    def test_number_inside_other_words_is_not_an_index(self):
        for text in ("2 loaves", "buy 1", "2 then rename", "second and change", "1st", "2/1", "-2", "2.0"):
            with self.subTest(text=text):
                self.assertIsNone(openreq.pick_candidate(text, ASK))
                self.assertEqual(openreq.cheap_answer(PRODUCT, text, ask=ASK), (False, None))
        named = {"ids": ["flour", "milk"], "names": ["Type 2 flour", "Whole milk"]}
        self.assertEqual(openreq.pick_candidate("type 2 flour", named), "flour")


class CandidateConversationTests(fixtures.SkillCase):
    SKILLS = (fixtures.DESCRIBE,)

    def ask_for_bread(self):
        text = "make the bread say tasty"
        self.script(text, fixtures.skill_reply("item.describe", product="bread", description="tasty"))
        self.assertEqual(self.say(text), "question")
        self.assertTrue(self.replies()[0].startswith("Which one do you mean:"))
        self.assertEqual(self.live()["ask"]["ids"], ASK["ids"])
        self.conv.db.close()
        self.conv = self.open()  # The candidate binding must survive reopening.

    def check_rejection(self, text):
        self.ask_for_bread()
        calls = len(self.asked)
        self.script(text, {"question": "Which bread should I change?"})
        self.assertEqual(self.say(text, pid="unclear-answer"), "question")
        self.assertEqual(len(self.asked), calls + 1)
        self.assertEqual(self.replies(), ["Which bread should I change?"])
        self.assertEqual(self.drafts(), [])
        req = self.live()
        self.assertTrue(req is None or "product" not in req["slots"])
        self.nothing_written()

    def test_real_conversation_rejected_second_reaches_clarification(self):
        self.check_rejection("not 2")

    def test_real_conversation_competing_numbers_reach_clarification(self):
        self.check_rejection("1 or 2")

    def test_real_conversation_rejected_first_reaches_clarification(self):
        self.check_rejection("not the first one")

    def test_real_conversation_simple_second_choice_still_skips_model(self):
        self.ask_for_bread()
        calls = len(self.asked)
        draft, _ = self.propose("2")
        self.assertEqual(len(self.asked), calls)
        self.assertEqual(json.loads(draft["ops_json"]), [
            {"op": "product.edit", "args": {"id": ASK["ids"][1], "description": "tasty"}}])
        self.assertEqual(draft["state"], "proposed")
        self.nothing_written()

    def test_duplicate_unclear_answer_does_not_retry_or_draft(self):
        self.check_rejection("not 2")
        calls, req = len(self.asked), self.live()
        self.assertEqual(self.say("not 2", pid="unclear-answer"), "duplicate")
        self.assertEqual((len(self.asked), self.live(), self.drafts()), (calls, req, []))
        self.assertEqual(self.replies(), [])
        self.nothing_written()

    def check_closed_choice(self, expired):
        self.ask_for_bread()
        if expired:
            self.now += timedelta(minutes=openreq.TTL_MINUTES, seconds=1)
        else:
            calls = len(self.asked)
            self.assertEqual(self.say("no"), "cancelled")
            self.assertEqual(self.replies(), ["Okay, I've dropped that question"])
            self.assertEqual(len(self.asked), calls)
            self.assertIsNone(self.live())
        calls = len(self.asked)
        self.script("2", {"question": "Which product should I change?"})
        self.assertEqual(self.say("2"), "question")
        self.assertEqual(len(self.asked), calls + 1)
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_cancelled_candidate_list_cannot_supply_a_choice(self):
        self.check_closed_choice(False)

    def test_expired_candidate_list_cannot_supply_a_choice(self):
        self.check_closed_choice(True)

    def test_stale_candidate_order_is_not_reused(self):
        self.ask_for_bread()
        req = self.live()
        self.conv.requests.put(fixtures.CHAT, "reordered", self.now, request_id=req["request_id"],
                               texts=req["texts"], skill=req["skill"], slots=req["slots"],
                               asked_slot=req["asked_slot"], question=req["question"],
                               ask={"ids": ASK["ids"][::-1], "names": ASK["names"][::-1]})
        self.conv.db.close()
        self.conv = self.open()
        calls = len(self.asked)
        draft, _ = self.propose("2")
        self.assertEqual(json.loads(draft["ops_json"])[0]["args"]["id"], ASK["ids"][0])
        self.assertEqual(len(self.asked), calls)
        self.nothing_written()
