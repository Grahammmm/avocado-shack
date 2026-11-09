"""HASS-CLOVER-1: a draft for each Clover write kind shows the exact change; the safety rules; undo. Nothing is ever sent.
Run: python3 -B -m unittest hass.tests.test_clover_drafts
"""
import json
import re
import unittest
from decimal import Decimal

from hass.clover import config as cfgmod
from hass.clover import drafts as d
from hass.clover import mapper as m
from hass.tests.test_clover_client import FAKE_TOKEN, fixture
from hass.tests.test_clover_mapper import item, items, product

CFG = cfgmod.from_settings({"environment": "sandbox", "merchantId": "FAKEMERCH0001", "tokenFile": "/nowhere/clover.token",
                            "categoryMap": {"pantry": "Pantry", "fruit": "Fruit"}})
CATS = [(c["id"], c["name"]) for c in fixture("categories.json")["elements"]]


def till():
    return items()


class CreateTests(unittest.TestCase):
    def test_the_owner_example_shows_every_fact_and_sends_nothing(self):
        dr = d.build_create_item("Sunshine olive oil", m.cents_from_text("12.50"), "pantry", [i for i in till().values() if i.id != "FAKEITEM00001"], CFG, categories=CATS)
        text = dr.render("a1b2")
        for needle in ("Did you mean to add this to the till?", "Item: Sunshine olive oil", "SKU: AS-PAN-SUNSHINE-OLIVE-OIL-01", "Price: $12.50 each",
                       "Category: Pantry", "Count: not counted yet", "Tax: your till's usual setting", "Nothing goes on the website.", "yes a1b2", "no a1b2"):
            self.assertIn(needle, text)
        self.assertEqual(dr.kind, "create_item")
        self.assertEqual(dr.after, {"name": "Sunshine olive oil", "sku": "AS-PAN-SUNSHINE-OLIVE-OIL-01", "price": 1250, "hidden": False})
        first, second = dr.requests
        self.assertEqual(first, {"method": "POST", "path": "/items", "json": {"name": "Sunshine olive oil", "price": 1250, "priceType": "FIXED",
                                                                                "sku": "AS-PAN-SUNSHINE-OLIVE-OIL-01", "hidden": False}})
        self.assertEqual(second["json"], {"elements": [{"category": {"id": "FAKECAT000001"}, "item": {"id": "{newItemId}"}}]})
        self.assertEqual((dr.site_ops, dr.second_confirmation, dr.warnings), ((), False, ()))

    def test_the_sku_is_the_next_free_one_and_a_duplicate_name_is_refused(self):
        dr = d.build_create_item("Sunshine olive oil 1 litre", 1250, "pantry", list(till().values()), CFG, categories=CATS)
        self.assertIn("AS-PAN-SUNSHINE-OLIVE-OIL-02", dr.render("x"))
        with self.assertRaisesRegex(d.DraftRefused, r"Sunshine olive oil is already in the till \(SKU AS-PAN-SUNSHINE-OLIVE-OIL-01\)\. Did you mean to change its price"):
            d.build_create_item("sunshine olive oil", 1250, "pantry", list(till().values()), CFG)

    def test_an_unknown_till_category_is_a_warning_not_a_guess(self):
        dr = d.build_create_item("Fresh bread", 800, "bread", list(till().values()), CFG, categories=CATS)
        self.assertEqual(len(dr.requests), 1)
        self.assertIn("Category: none", dr.render("c"))
        self.assertIn("no category called bread", dr.render("c"))
        self.assertEqual(len(d.build_create_item("Plain thing", 800, None, [], CFG).requests), 1)

    def test_bad_input_is_refused_before_a_draft_exists(self):
        for kwargs in (dict(name="", price_cents=100), dict(name="<b>", price_cents=100), dict(name="X", price_cents=0), dict(name="X", price_cents=-5),
                       dict(name="X", price_cents=CFG.max_price_cents + 1), dict(name="X", price_cents=12.5), dict(name="X", price_cents=True)):
            with self.subTest(kwargs=kwargs), self.assertRaises(m.MapError):
                d.build_create_item(kwargs["name"], kwargs["price_cents"], "pantry", [], CFG)
        with self.assertRaisesRegex(d.DraftRefused, "I know these categories"):
            d.build_create_item("X", 100, "gadgets", [], CFG)


class PriceTests(unittest.TestCase):
    def test_a_price_change_shows_old_new_and_percentage(self):
        oil = till()["FAKEITEM00001"]
        dr = d.build_set_price(oil, 1400, CFG)
        text = dr.render("b2c3")
        self.assertIn("Change the price of Sunshine olive oil (SKU AS-PAN-SUNSHINE-OLIVE-OIL-01)?", text)
        self.assertIn("Price: $12.50 -> $14.00 each (+12.0%)", text)
        self.assertEqual((dr.before, dr.after, dr.second_confirmation), ({"price": 1250}, {"price": 1400}, False))
        self.assertEqual(dr.requests, ({"method": "POST", "path": "/items/FAKEITEM00001", "json": {"price": 1400}},))

    def test_a_cheaper_price_and_a_weighed_item(self):
        dr = d.build_set_price(till()["FAKEITEM00005"], 349, CFG)
        self.assertIn("Price: $3.99 -> $3.49 per lb (-12.5%)", dr.render("x"))

    def test_a_big_move_needs_a_second_yes_up_or_down(self):
        oil = till()["FAKEITEM00001"]
        for cents in (1563, 1700, 900, 100):          # +25.04%, +36%, -28%, -92%
            with self.subTest(cents=cents):
                dr = d.build_set_price(oil, cents, CFG)
                self.assertTrue(dr.second_confirmation)
                self.assertIn("ask once more", dr.render("x"))
                self.assertRegex(dr.warnings[0], r"that is a \d+(\.\d)?% (increase|decrease)")
        for cents in (1562, 1250 - 312, 1251):        # +24.96%, -24.96%, +0.08%
            self.assertFalse(d.build_set_price(oil, cents, CFG).second_confirmation)
        strict = cfgmod.from_settings({"environment": "sandbox", "merchantId": "FAKEMERCH0001", "tokenFile": "/x", "priceConfirmPct": 5})
        self.assertTrue(d.build_set_price(oil, 1350, strict).second_confirmation)

    def test_refusals(self):
        got = till()
        with self.assertRaisesRegex(d.DraftRefused, "already \\$12.50"):
            d.build_set_price(got["FAKEITEM00001"], 1250, CFG)
        with self.assertRaisesRegex(d.DraftRefused, "priced at the register each time"):
            d.build_set_price(got["FAKEITEM00006"], 500, CFG)
        for bad in (0, -1, CFG.max_price_cents + 1, 12.5, "1400", None, True):
            with self.subTest(bad=bad), self.assertRaises(d.DraftRefused):
                d.build_set_price(got["FAKEITEM00001"], bad, CFG)

    def test_a_hidden_item_gets_a_note(self):
        self.assertIn("hidden on the till", d.build_set_price(till()["FAKEITEM00004"], 1200, CFG).render("x"))

    def test_the_arithmetic_is_whole_cents(self):
        for cents in (1, 7, 1999, 100000):
            dr = d.build_set_price(item(price_cents=500), cents, CFG) if cents != 500 else None
            self.assertTrue(all(type(v) is int for v in dr.requests[0]["json"].values()))


class StockTests(unittest.TestCase):
    def test_set_a_count_shows_before_and_after(self):
        dr = d.build_set_stock(till()["FAKEITEM00001"], 7, CFG)
        text = dr.render("c3d4")
        self.assertIn("Set the count of Sunshine olive oil (SKU AS-PAN-SUNSHINE-OLIVE-OIL-01)?", text)
        self.assertIn("Count: 12 -> 7", text)
        self.assertEqual((dr.before, dr.after), ({"stock": "12"}, {"stock": "7"}))
        self.assertEqual(dr.requests, ({"method": "PUT", "path": "/item_stocks/FAKEITEM00001", "json": {"quantity": 7}},))

    def test_received_adds_to_the_tills_count_and_shows_both_numbers(self):
        dr = d.build_received(till()["FAKEITEM00001"], 12, CFG)
        text = dr.render("d4e5")
        self.assertIn("Add stock to Sunshine olive oil", text)
        self.assertIn("Received: 12", text)
        self.assertIn("Count: 12 -> 24", text)
        self.assertEqual(dr.requests[0]["json"], {"quantity": 24})

    def test_a_weighed_item_takes_decimals_and_others_do_not(self):
        got = till()
        dr = d.build_received(got["FAKEITEM00005"], "2.25", CFG)
        self.assertIn("Count: 7.5 -> 9.75", dr.render("x"))
        self.assertEqual(dr.requests[0]["json"], {"quantity": 9.75})
        for bad in ("2.5", "0.5"):
            with self.assertRaisesRegex(d.DraftRefused, "counted in whole items"):
                d.build_set_stock(got["FAKEITEM00001"], bad, CFG)
        with self.assertRaisesRegex(d.DraftRefused, "three decimal places"):
            d.build_set_stock(got["FAKEITEM00005"], "1.0005", CFG)

    def test_sold_out_is_a_count_of_zero(self):
        dr = d.build_set_stock(till()["FAKEITEM00001"], 0, CFG)
        self.assertIn("Mark Sunshine olive oil (SKU AS-PAN-SUNSHINE-OLIVE-OIL-01) as sold out?", dr.render("x"))
        self.assertEqual(dr.requests[0]["json"], {"quantity": 0})

    def test_untracked_items_cannot_have_a_delta_but_can_start_a_count(self):
        free = till()["FAKEITEM00002"].__class__(**{**till()["FAKEITEM00002"].__dict__, "stock": None, "stock_modified": None})
        with self.assertRaisesRegex(d.DraftRefused, "not counting Hass avocado yet"):
            d.build_received(free, 12, CFG)
        dr = d.build_set_stock(free, 12, CFG)
        self.assertIn("Count: not counted -> 12", dr.render("x"))
        self.assertIn("starts the count", dr.render("x"))

    def test_bad_counts(self):
        oil = till()["FAKEITEM00001"]
        for bad in (-1, "abc", "", None, "NaN", "inf", CFG.max_stock + 1, [3]):
            with self.subTest(bad=bad), self.assertRaises(d.DraftRefused):
                d.build_set_stock(oil, bad, CFG)
        with self.assertRaisesRegex(d.DraftRefused, "already shows 12"):
            d.build_set_stock(oil, 12, CFG)
        with self.assertRaisesRegex(d.DraftRefused, "more than 0"):
            d.build_received(oil, 0, CFG)
        with self.assertRaisesRegex(d.DraftRefused, "too high"):
            d.build_received(oil, CFG.max_stock, CFG)


class SiteBundleTests(unittest.TestCase):
    """Sold out on the till marks sold out on the site through the existing op, in the same draft (one change, one yes)."""

    def test_sold_out_adds_one_site_op_and_no_count_or_price(self):
        oil, site = till()["FAKEITEM00001"], product("photo-product-170", "Sunshine olive oil", available="yes")
        dr = d.build_set_stock(oil, 0, CFG, site_product=site)
        self.assertEqual(dr.site_ops, ({"op": "product.set_availability", "args": {"id": "photo-product-170", "available": "no"}},))
        self.assertIn("Website: marks Sunshine olive oil as Sold out (same yes; the site shows a word, never a count)", dr.render("x"))
        blob = json.dumps(dr.site_ops)
        self.assertNotRegex(blob, r"\$|price|\b12\b|quantity|sku")

    def test_restocking_a_sold_out_product_marks_it_available_again(self):
        zero = item(id="Z", name="Eggs", stock=Decimal(0), stock_modified=1)
        dr = d.build_received(zero, 6, CFG, site_product=product("p", "Eggs", available="no"))
        self.assertEqual(dr.site_ops[0]["args"]["available"], "yes")
        self.assertIn("marks Eggs as Available today", dr.render("x"))

    def test_no_site_op_when_the_site_already_says_so_or_nothing_crosses_zero(self):
        oil = till()["FAKEITEM00001"]
        self.assertEqual(d.build_set_stock(oil, 0, CFG, site_product=product("p", "S", available="no")).site_ops, ())
        self.assertEqual(d.build_set_stock(oil, 7, CFG, site_product=product("p", "S", available="yes")).site_ops, ())
        self.assertEqual(d.build_set_stock(oil, 7, CFG, site_product=product("p", "S", available="limited")).site_ops, ())
        self.assertEqual(d.build_set_stock(oil, 7, CFG, site_product=product("p", "S")).site_ops, ())      # no word on the card: leave it
        self.assertEqual(d.build_set_stock(oil, 0, CFG).site_ops, ())                                      # not on the site at all
        self.assertEqual(d.build_set_stock(oil, 0, CFG, site_product=product("p", "S", status="hidden", available="yes")).site_ops, ())
        self.assertEqual(d.build_set_stock(oil, 0, CFG, site_product=product("p", "S", status="held")).site_ops, ())

    def test_a_site_word_with_no_word_yet_still_gets_sold_out(self):
        dr = d.build_set_stock(till()["FAKEITEM00001"], 0, CFG, site_product=product("p", "S"))
        self.assertEqual(dr.site_ops[0]["args"]["available"], "no")


class SkuAndHiddenTests(unittest.TestCase):
    def test_set_sku_for_an_item_without_one(self):
        got = till()
        dr = d.build_set_sku(got["FAKEITEM00002"], list(got.values()), CFG)
        self.assertIn("SKU: none -> AS-FRU-HASS-AVOCADO-01 (made up by me, the next free number)", dr.render("x"))       # its till category is Fruit
        self.assertEqual((dr.before, dr.after), ({"sku": ""}, {"sku": "AS-FRU-HASS-AVOCADO-01"}))
        self.assertEqual(dr.requests, ({"method": "POST", "path": "/items/FAKEITEM00002", "json": {"sku": "AS-FRU-HASS-AVOCADO-01"}},))
        cat = d.build_set_sku(got["FAKEITEM00002"], list(got.values()), CFG, category="dairy")
        self.assertIn("AS-DAI-HASS-AVOCADO-01", cat.render("x"))
        nocat = item(id="N", name="Plain jar")
        self.assertIn("AS-GEN-PLAIN-JAR-01", d.build_set_sku(nocat, [nocat], CFG).render("x"))
        mapped = item(id="M", name="Plum", categories=("Fruit",))
        self.assertIn("AS-FRU-PLUM-01", d.build_set_sku(mapped, [mapped], CFG).render("x"))

    def test_a_sku_that_exists_is_never_changed(self):
        for sku in ("EGG12", "AS-PAN-SUNSHINE-OLIVE-OIL-01"):
            with self.assertRaisesRegex(d.DraftRefused, "never change a SKU"):
                d.build_set_sku(item(sku=sku), [], CFG)

    def test_hide_and_show(self):
        oil = till()["FAKEITEM00001"]
        dr = d.build_set_hidden(oil, True, CFG)
        self.assertIn("Hide Sunshine olive oil (SKU AS-PAN-SUNSHINE-OLIVE-OIL-01) on the till?", dr.render("x"))
        self.assertIn("Nothing is deleted", dr.render("x"))
        self.assertEqual((dr.before, dr.after, dr.requests[0]["json"]), ({"hidden": False}, {"hidden": True}, {"hidden": True}))
        self.assertIn("Show Old honey jar", d.build_set_hidden(till()["FAKEITEM00004"], False, CFG).render("x"))
        with self.assertRaisesRegex(d.DraftRefused, "already showing"):
            d.build_set_hidden(oil, False, CFG)


class SafetyTests(unittest.TestCase):
    def all_drafts(self):
        got = till()
        oil, free = got["FAKEITEM00001"], got["FAKEITEM00006"]
        return [d.build_create_item("Brand new", 900, "pantry", list(got.values()), CFG, categories=CATS), d.build_set_price(oil, 1400, CFG),
                d.build_set_stock(oil, 7, CFG), d.build_received(oil, 3, CFG), d.build_set_sku(got["FAKEITEM00002"], list(got.values()), CFG),
                d.build_set_hidden(oil, True, CFG), d.build_set_stock(free, 3, CFG)]

    def test_there_is_no_delete_and_no_money_movement_call(self):
        for dr in self.all_drafts():
            for req in dr.requests:
                self.assertIn(req["method"], ("POST", "PUT"))
                self.assertRegex(req["path"], r"^/(items|item_stocks|category_items)(/[A-Za-z0-9]+)?$")
                self.assertNotRegex(req["path"], r"order|payment|refund|discount|customer|employee|credit|checkout|charge")
            self.assertIn(dr.kind, d.KINDS)

    def test_the_daily_cap(self):
        got = till()
        oil = got["FAKEITEM00001"]
        builders = [lambda w: d.build_create_item("N", 100, "pantry", [], CFG, writes_today=w), lambda w: d.build_set_price(oil, 1300, CFG, writes_today=w),
                    lambda w: d.build_set_stock(oil, 1, CFG, writes_today=w), lambda w: d.build_received(oil, 1, CFG, writes_today=w),
                    lambda w: d.build_set_sku(got["FAKEITEM00002"], [], CFG, writes_today=w), lambda w: d.build_set_hidden(oil, True, CFG, writes_today=w)]
        for build in builders:
            build(CFG.daily_write_cap - 1)
            with self.assertRaisesRegex(d.DraftRefused, "my daily limit"):
                build(CFG.daily_write_cap)
            with self.assertRaises(d.DraftRefused):
                build(CFG.daily_write_cap + 5)

    def test_a_draft_is_deterministic_and_changes_with_its_content(self):
        oil = till()["FAKEITEM00001"]
        a, b, c = d.build_set_price(oil, 1400, CFG), d.build_set_price(oil, 1400, CFG), d.build_set_price(oil, 1401, CFG)
        self.assertEqual((a.change_id, a.draft_hash), (b.change_id, b.draft_hash))
        self.assertNotEqual(a.draft_hash, c.draft_hash)
        self.assertRegex(a.change_id, r"^clv-[0-9a-f]{12}$")
        self.assertEqual(a.to_dict()["data_class"], "finance-local")
        self.assertEqual(json.loads(json.dumps(a.to_dict()))["after"], {"price": 1400})

    def test_a_changed_item_makes_the_draft_stale(self):
        oil = till()["FAKEITEM00001"]
        dr = d.build_set_price(oil, 1400, CFG)
        self.assertFalse(d.is_stale(dr, oil))
        self.assertTrue(d.is_stale(dr, item(**{**oil.__dict__, "modified_time": oil.modified_time + 1})))
        self.assertTrue(d.is_stale(dr, item(**{**oil.__dict__, "stock_modified": 5})))
        self.assertTrue(d.is_stale(dr, None))
        self.assertFalse(d.is_stale(d.build_create_item("N", 100, None, [], CFG), None))

    def test_no_secret_in_any_draft(self):
        for dr in self.all_drafts():
            blob = json.dumps(dr.to_dict()) + dr.render("x")
            self.assertNotIn(FAKE_TOKEN, blob)
            self.assertNotRegex(blob.lower(), r"bearer|authorization|token")

    def test_every_draft_tells_the_owner_nothing_changes_until_yes(self):
        for dr in self.all_drafts():
            self.assertRegex(dr.render("q9z8"), r"Reply yes q9z8 to do this, or no q9z8 to drop it\. Nothing changes until you say yes\.$")


class UndoTests(unittest.TestCase):
    def journal(self, dr, **extra):
        return {**dr.to_dict(), **extra}

    def test_undo_a_price_restores_the_old_one(self):
        oil = till()["FAKEITEM00001"]
        dr = d.build_set_price(oil, 1700, CFG)                        # a big move: the second yes was needed
        after = item(**{**oil.__dict__, "price_cents": 1700, "modified_time": 9})
        undo = d.build_undo(self.journal(dr), after, CFG)
        self.assertIn("Undo: put the price of Sunshine olive oil (SKU AS-PAN-SUNSHINE-OLIVE-OIL-01) back?", undo.render("u1"))
        self.assertIn("Price: $17.00 -> $12.50 each", undo.render("u1"))
        self.assertEqual((undo.requests[0]["json"], undo.second_confirmation, undo.undo_of), ({"price": 1250}, False, dr.change_id))
        self.assertEqual(undo.base, {"modifiedTime": 9, "stockModifiedTime": oil.stock_modified})

    def test_undo_a_count(self):
        oil = till()["FAKEITEM00001"]
        dr = d.build_received(oil, 12, CFG)
        after = item(**{**oil.__dict__, "stock": Decimal("24")})
        undo = d.build_undo(self.journal(dr), after, CFG)
        self.assertIn("Count: 24 -> 12", undo.render("u2"))
        self.assertEqual(undo.requests[0], {"method": "PUT", "path": "/item_stocks/FAKEITEM00001", "json": {"quantity": 12}})

    def test_undo_sold_out_on_the_till_brings_the_site_word_back_in_the_same_draft(self):
        oil, site = till()["FAKEITEM00001"], product("p", "Sunshine olive oil", available="no")      # the site now says Sold out
        dr = d.build_set_stock(oil, 0, CFG, site_product=product("p", "Sunshine olive oil", available="yes"))
        after = item(**{**oil.__dict__, "stock": Decimal("0")})
        undo = d.build_undo(self.journal(dr), after, CFG, site_product=site)
        self.assertEqual(undo.site_ops[0]["args"], {"id": "p", "available": "yes"})

    def test_undo_restores_the_original_site_word_not_a_recomputed_one(self):
        oil = item(id="O", name="Oil", sku="S1", stock=Decimal(5))
        limited, sold = product("p", "Oil", available="limited"), product("p", "Oil", available="no")
        dr = d.build_set_stock(oil, 0, CFG, site_product=limited)
        self.assertEqual(dr.before["site"], {"id": "p", "available": "limited"})
        after = item(**{**oil.__dict__, "stock": Decimal(0)})
        undo = d.build_undo(self.journal(dr), after, CFG, site_product=sold)
        self.assertEqual(undo.site_ops, ({"op": "product.set_availability", "args": {"id": "p", "available": "limited"}},))
        self.assertIn("marks Oil as Limited", undo.render("u"))

    def test_undo_of_a_restock_puts_the_site_back_to_sold_out(self):
        zero = item(id="Z", name="Eggs", stock=Decimal(0), stock_modified=1)
        dr = d.build_received(zero, 6, CFG, site_product=product("p", "Eggs", available="no"))
        after = item(**{**zero.__dict__, "stock": Decimal(6)})
        undo = d.build_undo(self.journal(dr), after, CFG, site_product=product("p", "Eggs", available="yes"))
        self.assertEqual(undo.site_ops[0]["args"], {"id": "p", "available": "no"})

    def test_undo_leaves_a_site_word_that_changed_again_and_one_that_was_never_touched(self):
        oil = item(id="O", name="Oil", sku="S1", stock=Decimal(5))
        after = item(**{**oil.__dict__, "stock": Decimal(0)})
        dr = d.build_set_stock(oil, 0, CFG, site_product=product("p", "Oil", available="limited"))
        self.assertEqual(d.build_undo(self.journal(dr), after, CFG, site_product=product("p", "Oil", available="yes")).site_ops, ())
        self.assertEqual(d.build_undo(self.journal(dr), after, CFG).site_ops, ())
        plain = d.build_set_stock(oil, 0, CFG, site_product=product("p", "Oil", available="no"))      # site already said so: no site op, none to undo
        self.assertEqual(d.build_undo(self.journal(plain), after, CFG, site_product=product("p", "Oil", available="no")).site_ops, ())

    def test_undo_a_count_that_started_the_count_is_not_possible_and_says_so(self):
        free = item(id="F", name="Plain", stock=None)
        dr = d.build_set_stock(free, 5, CFG)
        with self.assertRaisesRegex(d.DraftRefused, "never delete a count"):
            d.build_undo(self.journal(dr), item(id="F", name="Plain", stock=Decimal(5)), CFG)

    def test_undo_a_sku_a_hide_and_a_create(self):
        got = till()
        sku_dr = d.build_set_sku(got["FAKEITEM00002"], list(got.values()), CFG)
        with_sku = item(**{**got["FAKEITEM00002"].__dict__, "sku": "AS-FRU-HASS-AVOCADO-01"})
        self.assertEqual(d.build_undo(self.journal(sku_dr), with_sku, CFG).requests[0]["json"], {"sku": ""})
        hide_dr = d.build_set_hidden(got["FAKEITEM00001"], True, CFG)
        hidden = item(**{**got["FAKEITEM00001"].__dict__, "hidden": True})
        self.assertEqual(d.build_undo(self.journal(hide_dr), hidden, CFG).requests[0]["json"], {"hidden": False})
        create = d.build_create_item("Brand new", 900, "pantry", [], CFG)
        made = item(id="FAKEITEM00077", name="Brand new", sku="AS-PAN-BRAND-NEW-01")
        undo = d.build_undo(self.journal(create, result_item_id="FAKEITEM00077"), made, CFG)
        self.assertEqual((undo.kind, undo.requests), ("set_hidden", ({"method": "POST", "path": "/items/FAKEITEM00077", "json": {"hidden": True}},)))
        self.assertIn("Nothing is deleted", undo.render("u"))

    def test_undo_never_overwrites_a_newer_value(self):
        oil = till()["FAKEITEM00001"]
        for dr, newer in ((d.build_set_price(oil, 1400, CFG), item(**{**oil.__dict__, "price_cents": 1500})),
                          (d.build_set_stock(oil, 7, CFG), item(**{**oil.__dict__, "stock": Decimal("3")})),
                          (d.build_set_hidden(oil, True, CFG), oil)):
            with self.subTest(kind=dr.kind), self.assertRaisesRegex(d.DraftRefused, "changed again after that"):
                d.build_undo(self.journal(dr), newer, CFG)
        create = self.journal(d.build_create_item("Brand new", 900, "pantry", [], CFG), result_item_id="X1")
        with self.assertRaisesRegex(d.DraftRefused, "changed again"):
            d.build_undo(create, item(id="X1", hidden=True), CFG)
        with self.assertRaisesRegex(d.DraftRefused, "can't find that item"):
            d.build_undo(self.journal(d.build_set_price(oil, 1400, CFG)), None, CFG)

    def test_undo_is_not_held_back_by_the_daily_cap(self):
        oil = till()["FAKEITEM00001"]
        dr = d.build_set_price(oil, 1300, CFG)
        after = item(**{**oil.__dict__, "price_cents": 1300})
        self.assertEqual(d.build_undo(self.journal(dr), after, CFG).kind, "set_price")      # no writes_today argument exists: undo is exempt

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaisesRegex(d.DraftRefused, "do not know how to undo"):
            d.build_undo({"kind": "set_color", "change_id": "clv-x", "before": {}, "after": {}}, till()["FAKEITEM00001"], CFG)


class ConfigTests(unittest.TestCase):
    BASE = {"environment": "sandbox", "merchantId": "FAKEMERCH0001", "tokenFile": "/srv/hass/state/clover.token"}

    def test_defaults_and_overrides(self):
        c = cfgmod.from_settings(self.BASE)
        self.assertEqual((c.daily_write_cap, c.price_confirm_pct, c.max_price_cents, c.low_stock_threshold, c.max_stock, c.category_map),
                         (20, 25, 100_000, 5, 100_000, {}))
        c = cfgmod.from_settings({**self.BASE, "dailyWriteCap": 3, "priceConfirmPct": 10, "categoryMap": {"pantry": "Pantry"}})
        self.assertEqual((c.daily_write_cap, c.price_confirm_pct, c.category_map), (3, 10, {"pantry": "Pantry"}))

    def test_problems_name_fields_never_values(self):
        for raw, fields in (({**self.BASE, "extra": 1}, ["extra"]), ({k: v for k, v in self.BASE.items() if k != "merchantId"}, ["merchantId"]),
                            ({**self.BASE, "tokenFile": "relative/path"}, ["tokenFile"]), ({**self.BASE, "environment": "live"}, ["environment"]),
                            ({**self.BASE, "dailyWriteCap": 0}, ["dailyWriteCap"]), ({**self.BASE, "dailyWriteCap": True}, ["dailyWriteCap"]),
                            ({**self.BASE, "categoryMap": {"gadgets": "X"}}, ["categoryMap"]), ({**self.BASE, "merchantId": "../../x"}, ["merchantId"]),
                            ({**self.BASE, "priceConfirmPct": 1.5}, ["priceConfirmPct"])):
            with self.subTest(fields=fields), self.assertRaises(cfgmod.ConfigProblem) as ctx:
                cfgmod.from_settings(raw)
            self.assertEqual(list(ctx.exception.fields), fields)
            self.assertNotIn("srv", str(ctx.exception))
        with self.assertRaises(cfgmod.ConfigProblem):
            cfgmod.from_settings("x")

    def test_production_needs_the_go_live_flag(self):
        with self.assertRaises(cfgmod.ConfigProblem) as ctx:
            cfgmod.from_settings({**self.BASE, "environment": "production"})
        self.assertEqual(list(ctx.exception.fields), ["liveApproved"])
        self.assertEqual(cfgmod.from_settings({**self.BASE, "environment": "production", "liveApproved": True}).environment, "production")


class NoSiteMoneyTests(unittest.TestCase):
    def test_nothing_a_draft_hands_to_the_site_could_pass_as_a_price_or_a_count(self):
        # The live policy refuses price words in site changes; a bundled site op carries only a product id and one of three words.
        got = till()
        for qty in (0, 3):
            dr = d.build_set_stock(got["FAKEITEM00001"], qty, CFG, site_product=product("photo-product-170", "S", available="no" if qty else "yes"))
            for op in dr.site_ops:
                self.assertEqual(set(op["args"]), {"id", "available"})
                self.assertIn(op["args"]["available"], m.AVAILABILITY)
                self.assertRegex(op["args"]["id"], r"^photo-product-\d+$")
        self.assertTrue(re.fullmatch(r"[a-z._]+", dr.site_ops[0]["op"]))


if __name__ == "__main__":
    unittest.main()
