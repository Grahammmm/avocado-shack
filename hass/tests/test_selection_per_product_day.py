"""AV1102-01 tests: each product word carries the day it was confirmed (``available_on``). The site shows the word only
when that day is the store's latest, fresh check; otherwise "Last confirmed <its own day>". morning_report counts such a
product as not confirmed. ``product.set_availability`` dates its word with today's check, or refuses.
Run: python3 -B -m unittest hass.tests.test_selection_per_product_day -v
"""

import copy
import unittest
from datetime import datetime, timedelta, timezone

from hass import morning_report, sitegen
from hass.content_model import ContentError, shop_today, validate
from hass.tests.test_catalog_ops import CatalogTestCase
from hass.tests.test_browser_freshness import browser_words
from hass.tests.test_selection_checked import CATALOG, DatedRepo

CHECK, SET = "store.confirm_selection", "product.set_availability"


class PerProductDayTests(CatalogTestCase):
    def setUp(self):
        self.r = DatedRepo()
        self.addCleanup(self.r.cleanup)
        self.today = shop_today()
        active = [p for p in self.r.products() if p["status"] == "active"]
        self.a, self.b, self.c = (p["id"] for p in active[:3])

    def at(self, day):
        self.r.now = datetime(day.year, day.month, day.day, 20, tzinfo=timezone.utc)  # midday Pacific (PST or PDT)

    def days(self, *ago):
        return [self.today - timedelta(days=n) for n in ago]

    def product(self, pid):
        return next(p for p in self.r.products() if p["id"] == pid)

    def words(self, content=None, today=None):
        files = sitegen.render(content or self.r.content(), today=today or self.today)
        return browser_words(files, today or self.today, (self.a, self.b, self.c))

    def facts(self, content=None):
        return morning_report.facts(content or self.r.content(), self.today)

    def refused(self, *ops):
        store, products = self.r.store(), self.r.products()
        reason = self.assertRejected(self.r, "refused", *ops)["reason"]
        self.assertEqual((self.r.store(), self.r.products()), (store, products))
        return reason

    def test_later_check_words_only_the_products_it_names(self):
        day1, day3 = self.days(4, 2)
        self.at(day1)
        self.r.run((CHECK, {"yes": [self.a], "no": [self.b]}))
        self.at(day3)
        self.r.run((CHECK, {"limited": [self.a]}))
        self.assertEqual((self.product(self.a)["available_on"], self.product(self.b)["available_on"]),
                         (day3.isoformat(), day1.isoformat()))
        self.assertEqual(self.words(), {self.a: "Limited", self.b: f"Last confirmed {sitegen._day_text(day1)}",
                                        self.c: None})
        facts = self.facts()
        self.assertEqual((facts["available"], facts["limited"], facts["sold_out"]), (0, 1, 0))
        self.assertEqual(facts["not_confirmed"], sum(p["status"] == "active" for p in self.r.products()) - 1)
        self.assertEqual(facts["sold_out_names"], [])  # B's day-1 "no" is not today's word

    def test_same_day_recheck_with_the_same_word_dates_it_and_is_not_refused(self):
        day1, day3 = self.days(4, 2)
        self.at(day1)
        self.r.run((CHECK, {"yes": [self.a], "no": [self.b]}))
        self.at(day3)
        self.r.run((CHECK, {"limited": [self.a]}))
        self.r.run((CHECK, {"no": [self.b]}))  # same word, older day: B is touched
        self.assertEqual(self.product(self.b)["available_on"], day3.isoformat())
        self.assertEqual(self.words()[self.b], "Sold out")
        self.assertEqual(self.facts()["sold_out"], 1)
        self.assertIn("nothing to change", self.refused((CHECK, {"no": [self.b]})))  # no word or day change
        self.assertIn("nothing to change", self.refused((CHECK, {})))

    def test_stale_check_shows_each_products_own_day(self):
        day1, day3 = self.days(4, 2)
        self.at(day1)
        self.r.run((CHECK, {"yes": [self.a], "no": [self.b]}))
        self.at(day3)
        self.r.run((CHECK, {"limited": [self.a]}))
        later = day3 + timedelta(days=sitegen.STALE_AFTER_DAYS + 1)
        self.assertEqual(self.words(today=later), {self.a: f"Last confirmed {sitegen._day_text(day3)}",
                                                   self.b: f"Last confirmed {sitegen._day_text(day1)}", self.c: None})

    def test_word_without_its_day_is_not_confirmed_and_validates(self):
        self.r.run((CHECK, {"yes": [self.a]}))
        content = copy.deepcopy(self.r.content())
        product = next(p for p in content.products if p["id"] == self.a)
        del product["available_on"]  # a hand edit
        validate(content, None)
        self.assertEqual(self.words(content)[self.a], None)
        facts = self.facts(content)
        self.assertEqual((facts["available"], facts["limited"], facts["sold_out"]), (0, 0, 0))

    def test_bad_available_on_is_a_content_problem_named_by_field(self):
        self.r.run((CHECK, {"yes": [self.a]}))
        base, where = self.r.content(), f"product {self.a}.available_on"
        tomorrow = (self.today + timedelta(days=1)).isoformat()
        for value, keep_word in (("2026-13-01", True), ("2026-10-20T09:00", True), (20261020, True), ("", True),
                                 (self.today.isoformat(), False), (tomorrow, True)):
            with self.subTest(value=value, keep_word=keep_word):
                content = copy.deepcopy(base)
                product = next(p for p in content.products if p["id"] == self.a)
                product["available_on"] = value
                if not keep_word:
                    del product["available"]
                with self.assertRaises(ContentError) as caught:
                    validate(content, None)
                self.assertEqual([p for p in caught.exception.problems if p.startswith(where)],
                                 caught.exception.problems)
                self.assertEqual(len(caught.exception.problems), 1)
        content = copy.deepcopy(base)
        del content.store["selection_checked_on"]  # a dated word with no store check at all
        with self.assertRaises(ContentError) as caught:
            validate(content, None)
        self.assertEqual(caught.exception.problems, [f"{where}: {self.today.isoformat()} is after "
                                                     "store.selection_checked_on"])

    def test_backdated_check_dates_named_products_and_never_publishes_the_day(self):
        day = self.today - timedelta(days=2)
        self.r.run((CHECK, {"date": day.isoformat(), "limited": [self.a], "no": [self.b]}))
        self.assertEqual({self.product(p).get("available_on") for p in (self.a, self.b)}, {day.isoformat()})
        self.assertNotIn("available_on", self.product(self.c))
        self.assertEqual(self.words(), {self.a: "Limited", self.b: "Sold out", self.c: None})
        self.assertNotIn(b"available_on", self.r.read(CATALOG))
        self.assertNotIn(b"available_on", sitegen.render(self.r.content(), today=self.today)[CATALOG])

    def test_hidden_and_held_products_never_counted(self):
        self.r.run((CHECK, {"yes": [self.a, self.b]}))
        self.r.run(("product.hide", {"id": self.b}))
        content = copy.deepcopy(self.r.content())
        held = next(p for p in content.products if p["status"] == "held")
        held.update(available="no", available_on=self.today.isoformat())
        validate(content, None)
        facts = self.facts(content)
        self.assertEqual((facts["available"], facts["sold_out"]), (1, 0))

    def test_set_availability_dates_its_word_with_todays_check_or_refuses(self):
        self.assertIn("check the selection first", self.refused((SET, {"id": self.a, "available": "no"})))
        self.at(self.today - timedelta(days=1))
        self.r.run((CHECK, {"yes": [self.a]}))
        self.at(self.today)
        self.assertIn("check the selection first", self.refused((SET, {"id": self.b, "available": "no"})))
        self.assertEqual(self.words()[self.a], "Available today")  # yesterday's check is still the latest
        self.r.run((CHECK, {}))
        self.r.run((SET, {"id": self.b, "available": "limited"}))
        self.assertEqual(self.product(self.b)["available_on"], self.today.isoformat())
        self.assertEqual(self.words(), {self.a: f"Last confirmed {sitegen._day_text(self.today - timedelta(days=1))}",
                                        self.b: "Limited", self.c: None})
        self.assertEqual(self.facts()["limited_names"], [self.product(self.b)["name"]])

    def test_set_availability_never_dates_a_word_after_a_backdated_check(self):
        day = self.today - timedelta(days=2)
        self.r.run((CHECK, {"date": day.isoformat(), "yes": [self.a]}))
        self.assertIn("check the selection first", self.refused((SET, {"id": self.a, "available": "no"})))
        self.assertEqual(self.product(self.a)["available_on"], day.isoformat())


if __name__ == "__main__":
    unittest.main()
