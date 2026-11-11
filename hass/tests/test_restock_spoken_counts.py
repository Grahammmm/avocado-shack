"""RF0035-10: stock.restock treats a spelled-out goods quantity ("two dozen eggs") like a digit one: the existing no-count reply.

Run: python3 -B -m unittest hass.tests.test_restock_spoken_counts -q
"""
from __future__ import annotations

import unittest

from hass.skills import restock as rs
from hass.tests.test_skills_restock import EGGS, EGGS_NAME, HONEY, HONEY_NAME, Chat, ctx, refusal, set_op

SPOKEN = ("restock forty jars of honey Thursday", "restock two dozen eggs Thursday", "restock two-dozen eggs Thursday",
          "twenty-one bottles of honey Thursday", "one hundred bags Thursday", "one hundred and five bags Thursday",
          "restock dozen jars of honey Thursday", "Restock FORTY Jars Thursday")
NOT_COUNTS = ("eggs back in two weeks", "restock in forty days", "restock the lemons on the 14th", "honey 2026-11-12",
              "Seven Seas honey Thursday", "forty honey Thursday", "two eggs Thursday")


class Predicate(unittest.TestCase):
    def test_spoken_goods_counts_use_digit_refusal(self):
        for text in SPOKEN:
            with self.subTest(text=text):
                self.assertEqual(refusal({"item": HONEY, "day": "2026-11-12"}, text).reply, rs.COUNTS_REFUSED)

    def test_spoken_count_missing_slots_uses_existing_one_question(self):
        for text in SPOKEN[:3]:
            with self.subTest(text=text):
                self.assertEqual(rs.question("day", {}, ctx(text)), rs.COUNTS + " " + rs.ASK_DAY)
                self.assertEqual(rs.question("item", {}, ctx(text)), rs.COUNTS + " " + rs.ASK_ITEM)
                self.assertEqual(refusal({"item": HONEY}, text).reply, rs.COUNTS + " " + rs.ASK_DAY)
                self.assertEqual(rs.notes("stock.restock", {"item": HONEY, "day": "2026-11-12"}, ctx(text)), {})

    def test_spoken_durations_dates_and_names_are_not_counts(self):
        for text in NOT_COUNTS:
            with self.subTest(text=text):
                self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": "2026-11-12"}, ctx(text)), set_op(HONEY, "2026-11-12"))
                self.assertIsNone(rs.question("day", {}, ctx(text)))

    def test_digit_decimal_multiplication_guards_unchanged(self):
        for text in ("restock 40 jars of honey", "1,200 bags", "2.5 lbs of honey", "x40", "12 x"):
            with self.subTest(text=text):
                self.assertEqual(refusal({"item": HONEY, "day": "2026-11-12"}, text).reply, rs.COUNTS_REFUSED)
        self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": "2026-11-12"}, ctx("more honey Thursday")), set_op(HONEY, "2026-11-12"))


class RealDispatch(unittest.TestCase):
    def test_real_dispatch_spoken_count_refuses_before_draft(self):
        for name, kwargs in (("single", lambda t: {"reply": {"item": EGGS_NAME, "day": "Thursday"}}),
                             ("calls", lambda t: {"calls": [{"item": EGGS_NAME, "day": "Thursday"}]})):
            for text in ("restock two dozen eggs Thursday", "restock forty jars of honey Thursday"):
                with self.subTest(shape=name, text=text):
                    chat = Chat()
                    self.addCleanup(chat.close)
                    d, r = chat.say(text, **kwargs(text))
                    self.assertEqual((d, r), ("refused", rs.COUNTS_REFUSED))
                    self.assertEqual((chat.drafts(), chat.head(), chat.product(EGGS).get("restock_on")), ([], chat.base, None))

    def test_spoken_count_missing_day_asks_once_then_refuses(self):
        chat = Chat()
        self.addCleanup(chat.close)
        d, r = chat.say("restock two dozen eggs", {"item": EGGS_NAME})
        self.assertEqual((d, r), ("question", rs.COUNTS + " " + rs.ASK_DAY))
        d, r = chat.say("Thursday", {"day": "Thursday"})
        self.assertEqual((d, r), ("refused", rs.COUNTS_REFUSED))
        self.assertEqual((chat.drafts(), chat.head()), ([], chat.base))

    def test_duration_control_still_prepares_the_date_draft(self):
        chat = Chat()
        self.addCleanup(chat.close)
        d, r = chat.say("eggs back in two weeks", {"item": EGGS_NAME, "day": "in two weeks"})
        self.assertEqual(d, "proposed")
        self.assertEqual(len(chat.drafts()), 1)
        self.assertEqual((chat.head(), chat.product(EGGS).get("restock_on")), (chat.base, None))


if __name__ == "__main__":
    unittest.main()
