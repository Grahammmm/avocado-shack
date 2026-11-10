"""RF1925-11: packing advice such as "Bring water per person" is not a price; numeric per-person fees still are.
Run: python3 -B -m unittest hass.tests.test_hike_nonprice_packing -q
"""
import unittest

from hass.skills import hikes
from hass.tests.test_skills_hikes import CASS, ctx

ADD = {"title": "Synthetic walk", "day": "2026-11-14", "clock": "09:00", "meeting_point": "the gate"}
NONPRICE = ("Bring water per person", "One snack per head", "two bottles per person", "2 liters per person", "BRING WATER PER PERSON")
PRICES = ("12 per person", "12 per head", "12.50 per person", "$5", "$ 5", "5 dollars", "10 bucks", "3 per lb", "per lb")


class NonPrice(unittest.TestCase):
    def rule(self, value, slot="bring"):
        return hikes.RULES["no-price"]({slot: value}, (), ctx(CASS))

    def test_nonmonetary_per_person_and_per_head_are_not_prices(self):
        for v in NONPRICE:
            with self.subTest(v):
                self.assertIsNone(self.rule(v))

    def test_numeric_person_fees_and_existing_price_forms_still_refuse(self):
        for v in PRICES:
            with self.subTest(v):
                self.assertEqual(self.rule(v), (hikes.R_PRICE, "price"))

    def test_nonprice_text_survives_add_and_edit_plans(self):
        for v in NONPRICE:
            with self.subTest(v):
                self.assertEqual(hikes.plan_add({**ADD, "bring": v}, ctx())[0]["args"]["bring"], v)
                self.assertEqual(hikes.plan_edit({"hike": CASS["id"], "bring": v}, ctx(CASS))[0]["args"]["bring"], v)

    def test_priced_text_still_refuses_plans(self):
        with self.assertRaises(hikes.Refusal) as cm:
            hikes.plan_add({**ADD, "bring": "Bring 12 per person"}, ctx())
        self.assertEqual(cm.exception.reply, hikes.R_PRICE)


if __name__ == "__main__":
    unittest.main()
