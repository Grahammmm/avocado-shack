"""RF2325-5: the shop.hours and shop.contact too-long replies say "N characters or fewer", matching the limits they allow.

Run: python3 -B -m unittest hass.tests.test_shop_length_replies -v
"""

import unittest

from hass.content_model import MAX_ADDRESS_PART, MAX_HOURS_LINE
from hass.skills import shop


def stop_of(plan, slots):
    with unittest.TestCase().assertRaises(shop.SkillStop) as cm:
        plan(slots, None)
    return cm.exception


class HoursLineLength(unittest.TestCase):
    def test_a_line_at_the_limit_is_accepted(self):
        line = "Monday " + "x" * (MAX_HOURS_LINE - len("Monday "))
        self.assertEqual(len(line), MAX_HOURS_LINE)
        self.assertEqual(shop.plan_hours({"hours": [line]}, None)[0]["op"], "store.set_hours")

    def test_one_over_gets_the_or_fewer_reply(self):
        stop = stop_of(shop.plan_hours, {"hours": ["Monday " + "x" * (MAX_HOURS_LINE + 1 - len("Monday "))]})
        self.assertEqual(stop.reply, shop.HOURS_LINE_LONG.format(i=1))
        self.assertIn(f"{MAX_HOURS_LINE} characters or fewer", stop.reply)
        self.assertNotIn("under", stop.reply)
        self.assertEqual(stop.kind, "question")


class AddressLength(unittest.TestCase):
    def test_street_and_town_at_the_limit_plan_set_address(self):
        for slots in ({"street_address": "s" * MAX_ADDRESS_PART}, {"town": "t" * MAX_ADDRESS_PART}):
            ops = shop.plan_contact(slots, None)
            self.assertEqual([o["op"] for o in ops], ["store.set_address"])

    def test_one_over_gets_the_or_fewer_question(self):
        for key in ("street_address", "town"):
            stop = stop_of(shop.plan_contact, {key: "s" * (MAX_ADDRESS_PART + 1)})
            self.assertEqual(stop.reply, shop.ADDRESS_LONG)
            self.assertIn(f"{MAX_ADDRESS_PART} characters or fewer", stop.reply)
            self.assertEqual(stop.kind, "question")

    def test_spaces_collapse_before_the_length_is_counted(self):
        street = "   ".join(["s" * 8] * 9)  # 88 raw characters, 80 once the spaces collapse
        self.assertGreater(len(street), MAX_ADDRESS_PART)
        self.assertEqual(len(" ".join(street.split())), MAX_ADDRESS_PART)
        self.assertEqual([o["op"] for o in shop.plan_contact({"street_address": street}, None)], ["store.set_address"])

    def test_too_long_wins_over_the_price_rule(self):
        stop = stop_of(shop.plan_contact, {"street_address": "$" * (MAX_ADDRESS_PART + 1)})
        self.assertEqual(stop.reply, shop.ADDRESS_LONG)


if __name__ == "__main__":
    unittest.main()
