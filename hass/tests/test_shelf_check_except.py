"""AV2007-16 tests: 'shelf check: everything's there except the watermelon' (and 'all good except X and Y', up to 5 names) drafts
today's shelf-check record plus each named product sold out in ONE code-required draft, by code; an unclear name asks which and
drafts nothing.

The real Conversation and production Editor run on the H02 throwaway shop with an injected clock; the interpreter is a scripted
stand-in that records every text it is asked (a deterministic route never asks it).
Run: python3 -B -m unittest hass.tests.test_shelf_check_except -q
"""

import json
import unittest

from hass import conversation
from hass.skills import stock
from hass.tests.test_conversation import STRANGER
from hass.tests.test_plain_shelf_check import DAY, PlainShelfCheck

QA = "shelf check: everything's there except the watermelon"
WATERMELON, FIGS, LEMONS, EGGS, ORANGES, BLUEBERRIES = (f"photo-product-{n}" for n in ("078", "097", "017", "024", "016", "058"))


class GrammarTests(unittest.TestCase):
    def test_grammar_accepts_the_forms(self):
        # Contract: the recognizer reads the owner's names in order. Bug: a dropped `the`, a lost name or a reordered list.
        for text, names in ((QA, ["watermelon"]),
                            ("all good except X and Y", ["x", "y"]),
                            ("shelf check done, all good except the figs, lemons and eggs", ["figs", "lemons", "eggs"]),
                            ("did the shelf check, everything is there except watermelon!", ["watermelon"]),
                            ("All there except lemons & the figs.", ["lemons", "figs"]),
                            ("everything\u2019s there except figs, and eggs", ["figs", "eggs"])):
            with self.subTest(text=text):
                self.assertEqual(stock.shelf_check_except(text), names)

    def test_grammar_rejects_near_misses(self):
        # Contract: anything but a plain 'all good except <names>' is left to the usual handling. Bug: a stock.set sentence,
        # a question, a count or a date word swallowed as a shelf check that marks products sold out.
        for text in ("all good", "shelf check done", "all good except?", "all good except watermelon?",
                     "everything's there except the eggs are low", "all good except 2 watermelons",
                     "all good except watermelon, back tomorrow", "not all good except watermelon", "all good except ",
                     "all good except the eggs, , figs", None, 5, b"all good except eggs"):
            with self.subTest(text=text):
                self.assertIsNone(stock.shelf_check_except(text))
        self.assertFalse(stock.plain_shelf_check("all good except watermelon"))  # the parent's recognizer stays closed to it


class ExceptCase(PlainShelfCheck):
    def products(self):
        return json.loads(self.content("products.json"))

    def ask_nothing_drafted(self, text, disposition, *parts):
        before = len(self.drafts())
        self.assertEqual(self.say(text), disposition)
        said = "\n".join(self.replies())
        for part in parts:
            self.assertIn(part, said)
        self.assertEqual((len(self.drafts()), self.asked), (before, []))
        self.assertIsNone(self.conv._open_question(self.now))
        self.nothing_written()


class ModeTests:
    def test_one_name_drafts_check_plus_sold_out_with_code(self):
        # Contract: one draft, code-required, check plus the product sold out. Bug: the check alone, a bare yes that saves, or a
        # sold-out product left behind by undo.
        before = self.products()
        draft, reply = self.propose_check(QA)
        self.assertEqual(draft["reason"], "shelf-check")
        self.assertEqual([(o["op"], o["args"]) for o in json.loads(draft["ops_json"])], [("store.confirm_selection", {"no": [WATERMELON]})])
        self.assertIn(f"Reply yes {draft['code']} to save it", reply)
        self.assertEqual(self.asked, [])
        self.assertEqual(self.say("yes"), "no-target")
        self.replies()
        self.nothing_written()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.replies()
        self.assertEqual((self.commits(), self.checked_on()), (1, DAY))
        watermelon = next(p for p in self.products()["products"] if p["id"] == WATERMELON)
        self.assertEqual((watermelon["available"], watermelon["available_on"]), ("no", DAY))
        self.assertEqual(self.say("undo"), "proposed")
        self.replies()
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.replies()
        self.assertEqual(self.products(), before)

    def test_five_names_one_draft_six_refused(self):
        # Contract: up to five names in one draft, in the owner's order; six refused by code. Bug: names dropped or a sixth drafted.
        draft, _ = self.propose_check("all good except figs, lemons, eggs, oranges and blueberries")
        self.assertEqual(json.loads(draft["ops_json"])[0]["args"], {"no": [FIGS, LEMONS, EGGS, ORANGES, BLUEBERRIES]})
        self.assertEqual(len(self.drafts()), 1)
        self.say("no")
        self.replies()
        self.assertEqual(self.say("all good except figs, lemons, eggs, oranges, blueberries and watermelon"), "not-drafted")
        self.assertEqual(self.replies(), [conversation.SHELF_CHECK_LIMIT])
        self.assertEqual((self.asked, len(self.drafts())), ([], 1))

    def test_unclear_name_asks_before_anything_is_drafted(self):
        # Contract: a name that is not exactly one active product asks and drafts nothing. Bug: the check drafted anyway, a guess
        # among the jams, or an open question row that swallows the owner's next message.
        self.ask_nothing_drafted("shelf check: all good except the jam", "question", "Which one do you mean", "Cal Poly strawberry jam")
        self.ask_nothing_drafted("all good except kumquats", "not-drafted", "I don't know a product called that")
        self.ask_nothing_drafted("all good except Raw milk white cheddar", "not-drafted", "on hold")
        draft, _ = self.propose_check("all good except the figs")  # resent with an exact name
        self.assertEqual(json.loads(draft["ops_json"])[0]["args"], {"no": [FIGS]})

    def test_one_bad_name_in_a_list_blocks_the_whole_list(self):
        # Contract: all names resolve or nothing drafts. Bug: the good name drafted alone.
        self.ask_nothing_drafted("all good except watermelon and jam", "question", "Cal Poly strawberry jam")

    def test_same_product_twice_and_already_done_today(self):
        # Contract: the plan's own refusals come back through the normal path. Bug: a doubled name saved twice, or a second
        # draft of a check already recorded today.
        self.assertEqual(self.say("all good except watermelon and the watermelon"), "refused")
        self.assertIn("twice", "\n".join(self.replies()))
        self.nothing_written()
        draft, _ = self.propose_check(QA)
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.replies()
        n = len(self.drafts())
        self.assertEqual(self.say(QA), "refused")
        self.assertEqual((self.replies(), len(self.drafts()), self.commits()), ([stock.DONE_TODAY], n, 1))

    def test_a_stranger_is_ignored(self):
        self.assertEqual(self.say(QA, sender=STRANGER), "ignored")
        self.assertEqual((self.replies(), self.drafts(), self.asked), ([], [], []))


class OpsOnlyShelfCheckExcept(ModeTests, ExceptCase):
    MODE = "ops-only"


class BothShelfCheckExcept(ModeTests, ExceptCase):
    MODE = "both"


if __name__ == "__main__":
    unittest.main()
