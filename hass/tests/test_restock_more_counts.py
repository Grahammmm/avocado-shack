"""RF2355-4: stock.restock treats "3 more boxes", g/kgs/gal/ml and "12-pack" as counts: the existing no-count reply.

Synthetic plan fixtures only. Run: python3 -B -m unittest hass.tests.test_restock_more_counts -q
"""
from __future__ import annotations

import unittest

from hass.skills import restock as rs
from hass.tests.test_skills_restock import HONEY, ctx, refusal

COUNTS_SAID = ("3 more boxes friday", "two extra cases friday", "300 g of honey", "300g of honey", "3 KGS of honey",
               "2 gal of cider", "2 gals of cider", "250 ml of syrup", "12-pack of soda friday", "6 pack of soda friday",
               "twelve-pack of soda friday")
NOT_COUNTS = ("eggs back in 2 weeks", "honey back on the 14th", "honey back at 10 am friday", "back in 2 days", "honey 11/14",
              "40 more honey thursday", "more soon", "a few boxes", "a couple of cases")
DAY = {"item": HONEY, "day": "2026-11-12"}


class MoreCounts(unittest.TestCase):
    def test_new_counts_are_refused_with_the_no_count_reply(self):
        for text in COUNTS_SAID:
            with self.subTest(text=text):
                self.assertTrue(rs.QUANTITY.search(text))
                self.assertEqual(refusal(DAY, text).reply, rs.COUNTS_REFUSED)
                self.assertEqual(rs.question("day", {}, ctx(text)), rs.COUNTS + " " + rs.ASK_DAY)

    def test_dates_waits_and_bare_numbers_are_not_counts(self):
        for text in NOT_COUNTS:
            with self.subTest(text=text):
                self.assertIsNone(rs.QUANTITY.search(text))


if __name__ == "__main__":
    unittest.main()
