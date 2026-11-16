"""RF2355-5: a home-part move that names a red/blue product is not a style request."""
import unittest

from hass.skills.front import _StyleStop, plan_sections
from hass.skills.shop import SkillStop

OPS = lambda order: [{"op": "store.set_sections", "args": {"order": order}}]


class ColourWordTests(unittest.TestCase):
    def test_product_sentences_plan(self):
        self.assertEqual(plan_sections({"order": ["why we do it"]}, {"texts": ["put why we do it first, the red peppers are in"]}),
                         OPS(["our-way", "market", "visit", "newsletter"]))
        got = plan_sections({"order": ["visit us"]}, {"texts": ["move visit us to the top, blue corn tortillas are back"]})
        self.assertEqual(got[0]["op"], "store.set_sections")
        self.assertEqual(got[0]["args"]["order"][0], "visit")

    def test_sentence_start_red_plans(self):
        got = plan_sections({"order": ["newsletter"]}, {"texts": ["Red onions are back, put the newsletter first"]})
        self.assertEqual(got[0]["args"]["order"][0], "newsletter")

    def test_real_style_asks_still_stop(self):
        for text in ("make the newsletter bigger", "make the food part red", "turn visit us blue", "put it in red",
                     "red background for the newsletter", "change the font"):
            with self.subTest(text=text), self.assertRaises(_StyleStop):
                plan_sections({"order": ["food"]}, {"texts": [text]})

    def test_red_section_slot_still_stops(self):
        with self.assertRaises(_StyleStop):
            plan_sections({"order": ["red section"]}, {"texts": ["put it first"]})


if __name__ == "__main__":
    unittest.main()
