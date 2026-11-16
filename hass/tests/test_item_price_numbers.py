"""RF0005-3: item.edit refuses single-word spelled-out prices for every number word.

Run: python3 -B -m unittest hass.tests.test_item_price_numbers -q
"""

import copy
import unittest

from hass.content_model import REPO_ROOT, load_and_validate
from hass.interpret_check import PRICE_REPLY
from hass.skills import items as it
from hass.skills.testkit import run_case_row
from hass.tests.test_skills_items import CONTENT, ROWS, SITE, SKILLS, ctx_for

PID = "photo-product-001"
SLOTS = ("name", "description", "display_brand", "image_alt")
NEW = ("thirteen", "fourteen", "sixteen", "seventeen", "eighteen", "nineteen", "sixty", "seventy", "eighty", "ninety")
OLD = ("twelve", "fifteen", "twenty", "fifty", "hundred", "5", "5.50")


class SpelledPrices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = ctx_for(load_and_validate(CONTENT, SITE))

    def plan(self, **slots):
        return it.plan_edit({"item": PID, **slots}, self.ctx)

    def refused(self, slot, text):
        with self.assertRaises(it.Refusal) as caught:
            self.plan(**{slot: text})
        self.assertEqual(caught.exception.reply, PRICE_REPLY)

    def test_every_number_word_refuses_in_every_field(self):
        for word in NEW + OLD:
            for fmt in ("{w} bucks each.", "{w} a pound.", "two for {w}.", "{w} for {w}.", "{W} BUCKS", "{w}  a  pound."):
                text = fmt.format(w=word, W=word.upper())
                for slot in SLOTS:
                    with self.subTest(text=text, slot=slot):
                        self.refused(slot, text)

    def test_non_price_prose_is_kept_byte_exact(self):
        for text in ("Thirteen varieties of pears.", "Roast for eighteen minutes.", "Sixty years of family farming.",
                     "Buckwheat noodles from Bucks County.", "Good for two for five minutes of toasting.",
                     "Sweet  and   juicy, picked  fresh."):
            with self.subTest(text=text):
                [op] = self.plan(description=text)
                self.assertEqual(op["args"]["description"], text)

    def test_control_characters_keep_the_plain_text_reply(self):
        with self.assertRaises(it.Refusal) as caught:
            self.plan(description="Thirteen\tvarieties")
        self.assertIn("plain words", caught.exception.reply)

    def test_a_price_in_one_field_gives_no_partial_operation(self):
        slots = {"item": PID, "name": "Fine pears", "description": "Thirteen bucks each."}
        before = copy.deepcopy(slots)
        with self.assertRaises(it.Refusal) as caught:
            it.plan_edit(slots, self.ctx)
        self.assertEqual(caught.exception.reply, PRICE_REPLY)
        self.assertEqual(slots, before)

    def test_recorded_row_with_a_new_word_never_reaches_a_draft(self):
        row = copy.deepcopy(next(r for r in ROWS["item.edit"] if r["id"] == "edit-20-five-bucks"))
        row["texts"] = ["the lemons description: thirteen bucks each"]
        row["replies"][0]["slots"]["description"] = "Thirteen bucks each."
        result = run_case_row(row, SKILLS, SKILLS["item.edit"])
        self.assertTrue(result.ok, result.problems)


if __name__ == "__main__":
    unittest.main()
