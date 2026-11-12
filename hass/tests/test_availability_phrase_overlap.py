"""RF0854-11: 'almost out' (limited) hides only its own 'out'; independent sold-out evidence beside it stays a question.

The resolver is hass.skills.kinds.availability. Both callers (openreq.cheap_answer and dispatch.validate) are exercised
unchanged, and the production ITEM_ADD availability question runs through the real Conversation with a scripted interpreter
(no model, no network, no photo, nothing written).
Run: python3 -B -m unittest hass.tests.test_availability_phrase_overlap -v
"""
import unittest

from hass.skills import dispatch, kinds, openreq
from hass.skills.item_add import ITEM_ADD
from hass.skills.model import Slot
from hass.tests import test_skill_dispatch as sd  # module import: its TestCase classes must not be collected here
from hass.tests.test_conversation import CHAT

ASK = "Is it in stock, running low, or sold out?"
SLOT = Slot("availability", "availability", True, ask=ASK)
AMBIGUOUS = ("almost out or sold out", "sold out or almost out", "almost out and gone", "almost out or out",
             "out, almost out", "almost out; none", "almost out, almost out, unavailable", "almost out or no more")


class Resolver(unittest.TestCase):
    def test_almost_out_suppresses_only_its_own_out(self):
        for text in ("almost out", "Almost  OUT!", "almost out, almost out", "almost out of stock"):
            with self.subTest(text=text):
                self.assertEqual((kinds.availability(text).status, kinds.availability(text).value), ("one", "limited"))
        for text in ("sold out", "out", "gone", "none", "unavailable", "no more", "all out", "out out"):
            with self.subTest(text=text):
                self.assertEqual((kinds.availability(text).status, kinds.availability(text).value), ("one", "no"))
        for text, value in (("yes", "yes"), ("limited", "limited"), ("no", "no"), ("back in stock", "yes"), ("running low", "limited")):
            with self.subTest(text=text):
                self.assertEqual(kinds.availability(text).value, value)
        self.assertEqual(kinds.availability("not almost out").status, "none")  # negation still asks

    def test_independent_sold_out_evidence_remains_ambiguous(self):
        for text in AMBIGUOUS:
            with self.subTest(text=text):
                res = kinds.availability(text)
                self.assertEqual((res.status, res.value, res.reply), ("none", None, ASK))

    def test_overlapping_aliases_do_not_create_false_conflicts(self):
        self.assertEqual(kinds.availability("low and limited").value, "limited")
        self.assertEqual(kinds.availability("sold out and gone").value, "no")
        self.assertEqual(kinds.availability("almost outside").status, "none")  # no substring match: no evidence at all
        self.assertEqual(kinds.availability("almost outside and low").value, "limited")
        for text in ("in stock but running low", "in stock but sold out", "almost out but back in stock"):
            with self.subTest(text=text):
                self.assertEqual(kinds.availability(text).status, "none")


class BothDispatchPaths(unittest.TestCase):
    def test_conflict_reaches_both_dispatch_paths(self):
        for text in ("almost out or sold out", "almost out and gone"):
            with self.subTest(text=text):
                filled = dispatch.validate(ITEM_ADD, {}, {"availability": text}, [text], None)
                self.assertNotIn("availability", filled.slots)
                self.assertEqual((filled.problem, filled.problem_slot), (ASK, "availability"))
        self.assertEqual(openreq.cheap_answer(SLOT, "almost out or sold out"), (False, None))
        self.assertEqual(openreq.cheap_answer(SLOT, "sold out or almost out"), (False, None))
        filled = dispatch.validate(ITEM_ADD, {}, {"availability": "almost out"}, ["almost out"], None)
        self.assertEqual((filled.slots.get("availability"), filled.problem), ("limited", None))
        self.assertEqual(openreq.cheap_answer(SLOT, "almost out"), (True, "limited"))


class ItemAddCase(sd.SkillCase):
    SKILLS = (ITEM_ADD,)

    def ask_availability(self):
        self.conv.requests.put(CHAT, "seed", self.now, texts=["add a new product"], skill="item.add", slots={},
                               asked_slot="availability", question=ASK)


class ItemAddRequest(ItemAddCase):
    def test_item_add_keeps_asking_instead_of_storing_an_ambiguous_word(self):
        for text in ("almost out or sold out", "sold out or almost out"):
            with self.subTest(text=text):
                self.interp.mapping.clear()
                self.script(text, {"question": ASK})
                self.ask_availability()
                before = len(self.asked)
                self.assertEqual(self.say(text), "question")
                self.assertEqual(len(self.asked) - before, 1)  # the cheap path declined: the interpreter was asked once
                self.assertNotIn("availability", self.live()["slots"])
                self.assertEqual((self.live()["state"], self.live()["question"]), ("open", ASK))
                self.assertEqual(self.replies(), [ASK])
                self.assertEqual(self.drafts(), [])
                self.nothing_written()

    def test_item_add_still_reads_plain_almost_out_without_the_model(self):
        self.ask_availability()
        before = len(self.asked)
        self.assertEqual(self.say("almost out"), "question")
        self.assertEqual(len(self.asked), before)
        self.assertEqual(self.live()["slots"].get("availability"), "limited")
        self.assertNotEqual(self.live()["asked_slot"], "availability")
        self.nothing_written()


if __name__ == "__main__":
    unittest.main()
