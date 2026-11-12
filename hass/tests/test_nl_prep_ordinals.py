"""RF0211-12: a bare ordinal ("the 30th") resolves to the next real monthly occurrence, even past a short month.
Run: python3 -m unittest hass.tests.test_nl_prep_ordinals -v
"""

import unittest
from datetime import date

from hass import nl_prep
from hass.skills import kinds
from hass.tests.test_nl_prep import tiny


def rows(text, today):
    return nl_prep.date_hints(text, today)[0]


class BareOrdinalTests(unittest.TestCase):
    def test_bare_ordinal_skips_short_next_month(self):
        self.assertEqual(rows("the 30th", date(2026, 1, 31)),
                         [{"said": "30th", "date": "2026-03-30", "weekday": "Monday"}])
        self.assertEqual(rows("the 29th", date(2026, 1, 30)),
                         [{"said": "29th", "date": "2026-03-29", "weekday": "Sunday"}])
        hints = nl_prep.make_hinter(tiny())("lemons on the 30th", date(2026, 1, 31))
        self.assertEqual(hints["dates"], [{"said": "30th", "date": "2026-03-30", "weekday": "Monday"}])

    def test_leap_and_year_rollovers_are_real_calendar_dates(self):
        self.assertEqual(rows("the 29th", date(2028, 1, 30))[0]["date"], "2028-02-29")
        self.assertEqual(rows("the 31st", date(2026, 12, 31))[0]["date"], "2026-12-31")
        self.assertEqual(rows("the 30th", date(2026, 12, 31))[0]["date"], "2027-01-30")
        self.assertEqual(rows("the 31st", date(2026, 11, 30))[0]["date"], "2026-12-31")
        self.assertEqual(rows("the 31st", date(2026, 1, 31))[0]["date"], "2026-01-31")
        self.assertEqual(rows("the 31st", date(2026, 4, 1))[0]["date"], "2026-05-31")

    def test_ordinal_today_and_valid_next_month_keep_exact_rows(self):
        self.assertEqual(rows("the 31st", date(2026, 3, 31)), [{"said": "31st", "date": "2026-03-31", "weekday": "Tuesday"}])
        self.assertEqual(rows("the 31st", date(2026, 2, 1)), [{"said": "31st", "date": "2026-03-31", "weekday": "Tuesday"}])
        self.assertEqual(rows("the 20th", date(2026, 1, 31))[0]["date"], "2026-02-20")

    def test_named_impossible_date_is_not_bare_ordinal_rescue(self):
        today = date(2026, 1, 31)
        for text in ("February 30th", "30th February", "April 31st"):
            self.assertEqual(rows(text, today), [], text)
        self.assertEqual(rows("February 14th 2027", today)[0]["date"], "2027-02-14")

    def test_calendar_end_and_invalid_ordinals_are_local_omissions(self):
        self.assertEqual(rows("the 0th", date(2026, 1, 1)), [])
        self.assertEqual(rows("the 32nd", date(2026, 1, 1)), [])
        self.assertEqual(rows("the 5th", date.max), [])
        self.assertEqual(rows("the 31st", date.max)[0]["date"], "9999-12-31")
        hints = nl_prep.make_hinter(tiny())("lemons the 5th at 9am", date.max)
        self.assertEqual(hints["times"], [{"said": "9am", "time": "09:00"}])
        self.assertIn("products", hints)

    def test_day_resolver_receives_next_occurrence(self):
        today = date(2026, 1, 31)
        self.assertEqual(kinds.day("the 30th", today).value, "2026-03-30")
        self.assertEqual(rows("the 30th", today), rows("the 30th", today))


if __name__ == "__main__":
    unittest.main()
