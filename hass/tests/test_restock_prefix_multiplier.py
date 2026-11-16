"""RF2345-21: stock.restock refuses prefix multiplication-sign counts (x40 / ×40 / × 40) like the ASCII control.

Synthetic plan and Chat fixtures only: recorded interpreter replies, a throwaway repository, no model, socket or live state.
Run: python3 -B -m unittest hass.tests.test_restock_prefix_multiplier -q
"""
from __future__ import annotations

import unittest

from hass.skills import restock as rs
from hass.tests import test_skills_restock as base

HONEY, EGGS, EGGS_NAME = base.HONEY, base.EGGS, base.EGGS_NAME
DAY = {"item": HONEY, "day": "2026-11-12"}
PREFIX = ("×40 honey Friday", "× 40 honey Friday", "restock ×40 honey Friday", "restock × 40 honey Friday",
          "restock\n×40 honey Friday", "restock (×40) honey Friday", "restock, ×40 honey Friday")
CONTROLS = ("x40 honey Friday", "X 40 honey Friday", "restock x40 honey", "40× honey Friday", "restock 40 jars honey Friday")
NOT_COUNTS = ("restock honey Thursday", "in 2 weeks", "the 14th", "10 am", "11/14", "restock × honey Thursday")



class Predicate(unittest.TestCase):
    def test_prefix_multiplier_matches_and_refuses(self):
        for text in PREFIX + CONTROLS:
            with self.subTest(text=text):
                self.assertTrue(rs.QUANTITY.search(text))
                self.assertEqual(base.refusal(DAY, text).reply, rs.COUNTS_REFUSED)

    def test_new_branch_needs_a_clean_boundary(self):
        for text in ("a×40", "v×40", "_×40", "restock ×40a honey", "restock ×40_ honey"):
            with self.subTest(text=text):
                self.assertIsNone(rs.QUANTITY.search(text))
        for text in NOT_COUNTS:
            with self.subTest(text=text):
                self.assertIsNone(rs.QUANTITY.search(text))
                self.assertEqual(rs.STOCK_RESTOCK.plan(dict(DAY), base.ctx(text)), base.set_op(HONEY, "2026-11-12"))

    def test_missing_slot_clear_and_precedence(self):
        text = "restock ×40 honey"
        self.assertEqual(rs.question("day", {}, base.ctx(text)), rs.COUNTS + " " + rs.ASK_DAY)
        self.assertEqual(rs.question("item", {}, base.ctx(text)), rs.COUNTS + " " + rs.ASK_ITEM)
        self.assertEqual(base.refusal({"item": HONEY, "clear": True}, "never mind the ×40 honey restock").reply, rs.COUNTS_REFUSED)


class RealDispatch(unittest.TestCase):
    def open(self):
        chat = base.Chat()
        self.addCleanup(chat.close)
        return chat

    def test_prefix_multiplier_refused_without_draft(self):
        for text in ("restock ×40 eggs Thursday", "restock × 40 eggs Thursday"):
            with self.subTest(text=text):
                chat = self.open()
                d, r = chat.say(text, reply={"item": EGGS_NAME, "day": "Thursday"})
                self.assertEqual((d, r), ("refused", rs.COUNTS_REFUSED))
                self.assertEqual((chat.drafts(), chat.head(), chat.product(EGGS).get("restock_on")), ([], chat.base, None))

    def test_plain_date_request_still_proposes(self):
        chat = self.open()
        d, _ = chat.say("restock eggs Thursday", reply={"item": EGGS_NAME, "day": "Thursday"})
        self.assertEqual(d, "proposed")
        self.assertEqual(len(chat.drafts()), 1)
        self.assertEqual(chat.head(), chat.base)


if __name__ == "__main__":
    unittest.main()
