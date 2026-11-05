"""SHOP-1 tests: the catalog says when Michael last checked the selection and whether a product is available.

Freshness comes only from the owner-set ``store.selection_checked_on`` (never the generation clock); availability
words come from each product's owner-set ``available``. Ops run through ``editor.prepare`` + ``editor.apply`` on a
throwaway Git repo (test_catalog_ops.CatalogRepo); rendering is checked with an explicit generation date.
Run: python3 -B -m unittest hass.tests.test_selection_checked -v
"""

import copy
import json
import unittest
from datetime import date, datetime, timedelta, timezone

from hass import editor, sitegen
from hass.content_model import ContentError, load_and_validate, shop_today, validate
from hass.tests.test_browser_freshness import browser_words, words_of
from hass.tests.test_catalog_ops import CatalogRepo, CatalogTestCase, _req

CHECK = date(2026, 10, 20)  # a Tuesday
CATALOG, INDEX = sitegen.SITE_PREFIX + "catalog-products.js", sitegen.SITE_PREFIX + "index.html"
NOT_CHECKED = "The selection has not been checked yet."


def _catalog(files):
    return json.loads(files[CATALOG].split(b"\n", 1)[0][len(b"const catalog="):].rstrip(b";"))


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.content = copy.deepcopy(load_and_validate())
        active = self.content.active_products()
        self.ids = [p["id"] for p in active[:4]]
        for pid, value in zip(self.ids, ("yes", "limited", "no")):
            next(p for p in self.content.products if p["id"] == pid)["available"] = value  # ids[3] stays absent

    def render(self, checked, today):
        content = copy.deepcopy(self.content)
        if checked is not None:
            content.store["selection_checked_on"] = checked.isoformat()
            for p in content.products:  # AV1102-01: the words were set on that check
                p.update({"available_on": checked.isoformat()} if p["id"] in self.ids[:3] else {})
        files = sitegen.render(content, today=today)
        return files, files[INDEX].decode("utf-8"), browser_words(files, today, self.ids)

    def test_no_check_says_so_and_shows_no_words_or_clock(self):
        files, page, words = self.render(None, date(2026, 11, 3))
        # AVO-LAUNCH-1: before the first check the page says nothing about it (no pre-launch wording for visitors).
        self.assertNotIn("selection-checked", page)
        self.assertNotIn(NOT_CHECKED, page)
        self.assertEqual(set(words.values()), {None})
        for today in (date(2026, 11, 3), date(2027, 2, 14)):
            again = sitegen.render(copy.deepcopy(self.content), today=today)
            self.assertEqual(again, files, "the generation date leaked into the output")
        for stamp in ("2026-11-03", "November 3", "Tuesday, November", "2026"):
            self.assertNotIn(stamp, page)
            self.assertNotIn(stamp, files[CATALOG].decode("utf-8"))
        self.assertNotIn("Selection last checked", page)

    def test_today_three_days_and_eight_days(self):
        line = "Selection last checked by Michael on Tuesday, October 20"
        fresh = {self.ids[0]: "Available today", self.ids[1]: "Limited", self.ids[2]: "Sold out", self.ids[3]: None}
        for age in (0, 3, 7):
            with self.subTest(age=age):
                _files, page, words = self.render(CHECK, CHECK + timedelta(days=age))
                self.assertIn(f">{line}.</p>", page)
                self.assertNotIn("more than a week", page)
                self.assertEqual(words, fresh)
        _files, page, words = self.render(CHECK, CHECK + timedelta(days=8))
        self.assertIn(f">{line} (more than a week ago - call or visit to confirm).</p>", page)
        stale = "Last confirmed Tuesday, October 20"
        self.assertEqual(words, {self.ids[0]: stale, self.ids[1]: stale, self.ids[2]: stale, self.ids[3]: None})
        self.assertNotIn("Available today", _files[CATALOG].decode("utf-8"))

    def test_regenerating_is_byte_identical_and_shows_only_the_stored_date(self):
        first = self.render(CHECK, CHECK + timedelta(days=1))[0]
        self.assertEqual(self.render(CHECK, CHECK + timedelta(days=1))[0], first)
        self.assertEqual(self.render(CHECK, CHECK + timedelta(days=6))[0], first)  # no clock in the output
        text = first[INDEX].decode("utf-8") + first[CATALOG].decode("utf-8")
        self.assertNotIn("October 21", text)
        self.assertNotIn("2026-10-21", text)  # the stored check date is published; the build date never is
        self.assertNotIn("2026-10-26", text)

    def test_hidden_and_held_products_never_show_words(self):
        content = copy.deepcopy(self.content)
        content.store["selection_checked_on"] = CHECK.isoformat()
        hidden = next(p for p in content.products if p["id"] == self.ids[0])
        hidden["status"] = "hidden"
        held = next(p for p in content.products if p["status"] == "held")
        held["available"] = "yes"
        validate(content, None)
        shown = {p["id"] for p in _catalog(sitegen.render(content, today=CHECK))}
        self.assertNotIn(hidden["id"], shown)
        self.assertNotIn(held["id"], shown)

    def test_validation_refuses_future_date_and_unknown_values(self):
        content = copy.deepcopy(self.content)
        today = shop_today()
        for bad in ((today + timedelta(days=1)).isoformat(), "2026-13-01", "2026-10-20T09:00", 20261020, ""):
            with self.subTest(bad=bad):
                content.store["selection_checked_on"] = bad
                with self.assertRaises(ContentError) as caught:
                    validate(content, None)
                self.assertTrue(any(p.startswith("store.selection_checked_on") for p in caught.exception.problems))
        content.store["selection_checked_on"] = today.isoformat()
        validate(content, None)
        product = next(p for p in content.products if p["id"] == self.ids[0])
        for bad in ("Yes", "available", "", None, True, "sold out"):
            with self.subTest(bad=bad):
                product["available"] = bad
                with self.assertRaises(ContentError) as caught:
                    validate(content, None)
                self.assertEqual(caught.exception.problems,
                                 [f"product {self.ids[0]}.available: must be one of ('yes', 'limited', 'no')"])


class DatedRepo(CatalogRepo):
    now: datetime | None = None

    def prepare(self, request):
        return editor.prepare(request, state=str(self.state), now=self.now)

    def apply(self, draft):
        return editor.apply(draft["change_id"], draft["draft_hash"], state=str(self.state), now=self.now)

    def store(self):
        return json.loads(self.read("hass/content/store.json"))


class OpTests(CatalogTestCase):
    def setUp(self):
        self.r = DatedRepo()
        self.addCleanup(self.r.cleanup)
        active = [p for p in self.r.products() if p["status"] == "active"]
        self.a, self.b, self.c = (p["id"] for p in active[:3])
        self.held = next(p["id"] for p in self.r.products() if p["status"] == "held")

    def at(self, day, hour=12):
        self.r.now = datetime(day.year, day.month, day.day, hour + 8, tzinfo=timezone.utc)  # midday Pacific (PST or PDT)

    def words(self):
        return words_of(self.r.catalog(), {"selectionCheckedOn": self.r.store().get("selection_checked_on")},
                        shop_today(), (self.a, self.b, self.c))

    def test_confirm_goes_through_prepare_and_apply_only(self):
        head, store, page = self.r.head(), self.r.store(), self.r.read(INDEX)
        draft = self.r.prepare(_req(("store.confirm_selection", {"yes": [self.a], "limited": [self.b],
                                                                  "no": [self.c]})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual((self.r.head(), self.r.store(), self.r.read(INDEX)), (head, store, page))
        self.assertNotIn("selection_checked_on", store)
        self.assertEqual(self.r.apply(draft["draft"])["result"], "applied")
        today = shop_today()
        self.assertEqual(self.r.store()["selection_checked_on"], today.isoformat())
        self.assertIn(f"Selection last checked by Michael on {sitegen._day_text(today)}.",
                      self.r.read(INDEX).decode("utf-8"))
        self.assertEqual(self.words(), {self.a: "Available today", self.b: "Limited", self.c: "Sold out"})
        self.assertEqual({r["collection"] for r in draft["draft"]["records"]}, {"store", "products"})

    def test_set_availability_without_a_check_shows_nothing_then_check_shows_it(self):
        # AV1102-01 (G decision 2026-11-03, option a): with no shelf check, set_availability refuses and sets nothing.
        products = self.r.products()
        self.assertIn("check the selection first", self.assertRejected(
            self.r, "refused", ("product.set_availability", {"id": self.a, "available": "no"}))["reason"])
        self.assertEqual(self.r.products(), products)
        self.assertEqual(self.words()[self.a], None)
        self.assertNotIn("selection-checked", self.r.read(INDEX).decode("utf-8"))
        self.r.run(("store.confirm_selection", {}))
        self.r.run(("product.set_availability", {"id": self.a, "available": "no"}))
        self.assertEqual(self.words()[self.a], "Sold out")

    def test_future_out_of_order_and_repeated_checks_are_refused(self):
        today = shop_today()
        tomorrow = (today + timedelta(days=1)).isoformat()
        self.assertIn("is in the future", self.assertRejected(
            self.r, "refused", ("store.confirm_selection", {"date": tomorrow}))["reason"])
        self.r.run(("store.confirm_selection", {"date": (today - timedelta(days=1)).isoformat()}))
        reason = self.assertRejected(self.r, "refused", ("store.confirm_selection",
                                                         {"date": (today - timedelta(days=2)).isoformat()}))["reason"]
        self.assertIn("already checked on", reason)
        self.r.run(("store.confirm_selection", {}))
        self.assertEqual(self.assertRejected(self.r, "refused", ("store.confirm_selection", {}))["reason"],
                         f"the selection was already checked on {today.isoformat()}; nothing to change")
        # Same day with a new availability changes only the product, not the date.
        draft = self.r.run(("store.confirm_selection", {"limited": [self.a]}))
        self.assertEqual([r["collection"] for r in draft["records"]], ["products"])
        self.assertEqual(self.r.store()["selection_checked_on"], today.isoformat())

    def test_bad_product_lists_are_refused(self):
        self.assertIn("listed twice", self.assertRejected(
            self.r, "refused", ("store.confirm_selection", {"yes": [self.a], "no": [self.a]}))["reason"])
        self.assertRejected(self.r, "not-found", ("store.confirm_selection", {"yes": ["photo-product-999"]}))
        self.assertIn("held:", self.assertRejected(
            self.r, "refused", ("store.confirm_selection", {"yes": [self.held]}))["reason"])
        self.r.run(("product.hide", {"id": self.b}))
        self.assertIn("is hidden; restore it", self.assertRejected(
            self.r, "refused", ("store.confirm_selection", {"yes": [self.b]}))["reason"])
        self.assertNotIn("selection_checked_on", self.r.store())

    def test_repeat_inside_one_list_names_that_list(self):
        a, b = self.a, self.b
        cases = (({"yes": [a, a]}, f"{a} is listed twice in yes"), ({"no": [b, a, b]}, f"{b} is listed twice in no"),
                 ({"limited": [a, a]}, f"{a} is listed twice in limited"), ({"yes": [a], "no": [a]},
                  f"{a} is listed twice (yes and no)"), ({"yes": [a, a], "no": [a]}, f"{a} is listed twice in yes"))
        store, products = self.r.store(), self.r.products()
        for args, reason in cases:
            with self.subTest(args=args):
                self.assertEqual(self.assertRejected(self.r, "refused", ("store.confirm_selection", args))["reason"], reason)
                self.assertEqual((self.r.store(), self.r.products()), (store, products))

    def test_set_availability_refusals_and_wording_bypass(self):
        for bad in ("Yes", "available", "sold out", "maybe"):
            with self.subTest(bad=bad):
                self.assertRejected(self.r, "invalid", ("product.set_availability", {"id": self.a, "available": bad}))
        self.assertRejected(self.r, "invalid", ("store.confirm_selection", {"date": "2026-10-20T09:00"}))
        self.assertIn("held:", self.assertRejected(
            self.r, "refused", ("product.set_availability", {"id": self.held, "available": "yes"}))["reason"])
        self.r.run(("store.confirm_selection", {}))  # AV1102-01: set_availability needs today's check first
        self.r.run(("product.set_availability", {"id": self.b, "available": "yes"}))
        self.assertIn("already marked available=yes", self.assertRejected(
            self.r, "refused", ("product.set_availability", {"id": self.b, "available": "yes"}))["reason"])
        self.r.run(("product.hide", {"id": self.b}))
        self.assertIn("is hidden; restore it", self.assertRejected(
            self.r, "refused", ("product.set_availability", {"id": self.b, "available": "no"}))["reason"])
        self.assertNotIn(self.b, {p["id"] for p in self.r.catalog()})
        # Restoring a held product still needs review of the recorded concern.
        self.assertIn("held:", self.assertRejected(self.r, "refused", ("product.restore", {"id": self.held}))["reason"])

    def test_draft_approved_after_midnight_is_stale_not_back_dated(self):
        yesterday = shop_today() - timedelta(days=1)
        self.at(yesterday)
        draft = self.r.prepare(_req(("store.confirm_selection", {})))
        self.assertEqual(draft["result"], "ok", draft)
        self.at(shop_today())
        self.assertEqual(self.r.apply(draft["draft"])["result"], "stale")
        self.assertNotIn("selection_checked_on", self.r.store())


if __name__ == "__main__":
    unittest.main()
