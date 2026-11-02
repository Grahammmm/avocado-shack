"""RF0620-2 tests: ``store.confirm_selection`` refuses a ``date`` more than STALE_AFTER_DAYS (7) days before the shop's
today, since the site would already call such a check out of date; dates within 7 days and no ``date`` are unchanged.
Run: python3 -B -m unittest hass.tests.test_selection_backdate_window -v
"""

import unittest
from datetime import date, datetime, timedelta, timezone

from hass.content_model import shop_today
from hass.tests.test_catalog_ops import CatalogTestCase
from hass.tests.test_selection_checked import DatedRepo

OP = "store.confirm_selection"


def _old(day):
    return f"{day.isoformat()} is more than 7 days ago, so the site would already call it out of date; " \
           "check the selection today instead"


class BackdateWindowTests(CatalogTestCase):
    def setUp(self):
        self.r = DatedRepo()
        self.addCleanup(self.r.cleanup)
        self.r.now = datetime.now(timezone.utc)  # one instant for prepare and apply
        self.today = shop_today(self.r.now)
        self.a = next(p["id"] for p in self.r.products() if p["status"] == "active")

    def refused(self, args):
        store, products = self.r.store(), self.r.products()
        reason = self.assertRejected(self.r, "refused", (OP, args))["reason"]
        self.assertEqual((self.r.store(), self.r.products()), (store, products))
        return reason

    def test_seven_days_back_is_saved(self):
        day = self.today - timedelta(days=7)
        self.r.run((OP, {"date": day.isoformat()}))
        self.assertEqual(self.r.store()["selection_checked_on"], day.isoformat())

    def test_eight_days_back_is_refused_with_nothing_written(self):
        day = self.today - timedelta(days=8)
        self.assertEqual(self.refused({"date": day.isoformat()}), _old(day))
        self.assertNotIn("selection_checked_on", self.r.store())

    def test_typed_year_on_first_check_is_refused_and_marks_nothing(self):
        before = next(p for p in self.r.products() if p["id"] == self.a).get("available")
        day = self.today.replace(year=self.today.year - 1) if (self.today.month, self.today.day) != (2, 29) \
            else self.today - timedelta(days=365)
        self.assertEqual(self.refused({"date": day.isoformat()}), _old(day))
        self.assertEqual(self.refused({"date": day.isoformat(), "yes": [self.a]}), _old(day))
        self.assertEqual(next(p for p in self.r.products() if p["id"] == self.a).get("available"), before)
        self.assertNotIn("selection_checked_on", self.r.store())

    def test_tomorrow_is_still_the_future_refusal(self):
        day = self.today + timedelta(days=1)
        self.assertEqual(self.refused({"date": day.isoformat()}),
                         f"{day.isoformat()} is in the future; the selection can only be checked today or earlier")

    def test_too_old_is_checked_before_already_checked(self):
        last = self.today - timedelta(days=3)
        self.r.run((OP, {"date": last.isoformat()}))
        day = self.today - timedelta(days=10)
        self.assertEqual(self.refused({"date": day.isoformat()}), _old(day))
        self.assertEqual(self.r.store()["selection_checked_on"], last.isoformat())

    def test_no_date_is_today(self):
        self.r.run((OP, {"yes": [self.a]}))
        self.assertEqual(self.r.store()["selection_checked_on"], self.today.isoformat())
        self.assertEqual(next(p for p in self.r.products() if p["id"] == self.a)["available"], "yes")

    def test_window_counts_from_the_shop_day_near_midnight(self):
        self.r.now = datetime(2026, 1, 15, 7, 30, tzinfo=timezone.utc)  # 23:30 PST on 2026-01-14
        self.assertEqual(shop_today(self.r.now), date(2026, 1, 14))
        self.assertEqual(self.refused({"date": "2026-01-06"}), _old(date(2026, 1, 6)))
        self.r.run((OP, {"date": "2026-01-07"}))  # 8 days by the UTC date, 7 by the shop's
        self.assertEqual(self.r.store()["selection_checked_on"], "2026-01-07")


if __name__ == "__main__":
    unittest.main()
