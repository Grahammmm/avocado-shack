"""RF0140-2: explicit shelf-check dates require owner approval (policy unwired)."""

import unittest
from datetime import date

from hass.auto_policy import ELIGIBLE, qualifies

ALL = list(ELIGIBLE)
DATED = (False, "dated check needs approval")


def selection(**args):
    return {"op": "store.confirm_selection", "args": args}


class DatedSelectionTest(unittest.TestCase):
    def test_date_presence_not_value_requires_approval(self):
        for value in ("2026-11-01", "", None, date.today().isoformat()):
            with self.subTest(date=value):
                self.assertEqual(qualifies([selection(date=value, yes=["a"])], ALL, False), DATED)

    def test_undated_daily_check_still_qualifies(self):
        self.assertEqual(qualifies([selection(yes=["a"])], ALL, False), (True, "opted in"))

    def test_opt_in_and_pause_take_precedence(self):
        draft = [selection(date="2026-11-01", yes=["a"])]
        self.assertEqual(qualifies(draft, [], False), (False, "not opted in"))
        self.assertEqual(qualifies(draft, ALL, True), (False, "changes are paused"))
        self.assertEqual(qualifies(draft, [], True), (False, "changes are paused"))

    def test_date_takes_precedence_over_product_cap(self):
        self.assertEqual(qualifies([selection(date=None, yes=[str(i) for i in range(21)])], ALL, False), DATED)

    def test_other_eligible_op_ignores_unexpected_date(self):
        draft = [{"op": "product.set_availability", "args": {"date": "2026-11-01"}}]
        self.assertEqual(qualifies(draft, ALL, False), (True, "opted in"))

    def test_duplicate_draft_does_not_qualify(self):
        op = selection(date="2026-11-01", yes=["a"])
        self.assertEqual(qualifies([op, op], ALL, False), (False, "more than one change"))

    def test_stale_or_future_explicit_dates_never_qualify(self):
        for value in ("1900-01-01", "9999-12-31"):
            with self.subTest(date=value):
                self.assertEqual(qualifies([selection(date=value)], ALL, False), DATED)


if __name__ == "__main__":
    unittest.main()
