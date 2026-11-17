"""RF0005-4: stock.checked and stock.clear resolve lowercase one-word names and aliases, not invented ids.

Pure plan tests on synthetic products.
Run: python3 -B -m unittest hass.tests.test_stock_single_token_references -q
"""

import copy
import types
import unittest

from hass.skills import stock

BASIL, JAM1, JAM2, HELD, HIDDEN = "photo-product-901", "photo-product-902", "photo-product-903", "photo-product-904", "photo-product-905"
CATALOG = (
    (BASIL, "Basil", "active"), (JAM1, "Jam", "active"), (JAM2, "Jam", "active"),
    (HELD, "Sage", "held"), (HIDDEN, "Thyme", "hidden"), ("basil", "Other thing", "active"),
    ("photo-product-910", "Mint", "active"), ("photo-product-911", "Dill", "active"),
    ("photo-product-912", "Fig", "active"), ("photo-product-913", "Plum", "active"),
    ("photo-product-914", "Pear", "active"), ("photo-product-915", "Kale", "active"),
)
ALIASES = {"herb": ("product", BASIL), "fresh-herb": ("product", BASIL)}


def _ctx(no_basil_id=True, content=True):
    products = [{"id": i, "name": n, "brand": "", "status": s, "available": "limited", "available_on": "2026-11-08"}
                for i, n, s in CATALOG if not (no_basil_id and i == "basil")]
    return types.SimpleNamespace(today="2026-11-08", aliases=dict(ALIASES),
                                 content=types.SimpleNamespace(products=products, store={}, makers={}) if content else None)


def _refusal(skill, slots, ctx):
    try:
        skill.plan(slots, ctx)
    except stock.Refusal as exc:
        return exc.reply
    raise AssertionError("the plan did not refuse")


def _clear(*pids):
    return [{"op": "product.clear_availability", "args": {"id": p}} for p in pids]


class SingleTokenReferences(unittest.TestCase):
    def test_lowercase_name_alias_and_id_give_identical_ops(self):
        ctx = _ctx()
        for ref in ("basil", "Basil", "BASIL", BASIL, "herb", "fresh-herb"):
            slots = {"items": [ref]}
            before = copy.deepcopy(slots)
            self.assertEqual(stock.STOCK_CLEAR.plan(slots, ctx), _clear(BASIL), ref)
            self.assertEqual(stock.STOCK_CHECKED.plan({"in": [ref]}, ctx)[0]["args"], {"yes": [BASIL]}, ref)
            self.assertEqual(slots, before)

    def test_exact_existing_id_beats_a_name_or_alias(self):
        ctx = _ctx(no_basil_id=False)
        self.assertEqual(stock.STOCK_CLEAR.plan({"items": ["basil"]}, ctx), _clear("basil"))

    def test_ambiguous_held_hidden_and_unknown_names_refuse(self):
        ctx = _ctx()
        self.assertEqual(_refusal(stock.STOCK_CLEAR, {"items": ["jam"]}, ctx), _refusal(stock.STOCK_CLEAR, {"items": ["Jam"]}, ctx))
        self.assertIn("Which one", _refusal(stock.STOCK_CLEAR, {"items": ["jam"]}, ctx))
        self.assertTrue(_refusal(stock.STOCK_CLEAR, {"items": ["sage"]}, ctx))
        self.assertTrue(_refusal(stock.STOCK_CHECKED, {"in": ["thyme"]}, ctx))
        self.assertEqual(_refusal(stock.STOCK_CLEAR, {"items": ["Mystery thing"]}, ctx), "I don't know a product called that. What is it called on the site?")

    def test_unknown_id_passes_through_for_the_editor(self):
        for ctx in (_ctx(), _ctx(content=False)):
            self.assertEqual(stock.STOCK_CLEAR.plan({"items": ["photo-product-999"]}, ctx), _clear("photo-product-999"))
        self.assertEqual(stock.STOCK_CLEAR.plan({"items": ["basil"]}, _ctx(content=False)), _clear("basil"))
        self.assertEqual(_refusal(stock.STOCK_CLEAR, {"items": ["Basil"]}, _ctx(content=False)), stock.BAD_ITEM)

    def test_clear_dedupes_and_checked_refuses_same_identity(self):
        ctx = _ctx()
        self.assertEqual(stock.STOCK_CLEAR.plan({"items": ["basil", "Basil", BASIL, "herb"]}, ctx), _clear(BASIL))
        twice = stock.TWICE.format(name="Basil")
        self.assertEqual(_refusal(stock.STOCK_CHECKED, {"in": ["basil", "herb"]}, ctx), twice)
        self.assertEqual(_refusal(stock.STOCK_CHECKED, {"in": ["basil"], "out": ["fresh-herb"]}, ctx), twice)

    def test_caps_and_bad_members(self):
        ctx = _ctx()
        six = ["basil", "mint", "dill", "fig", "plum", "pear"]
        self.assertEqual(len(stock.STOCK_CLEAR.plan({"items": six + ["herb"]}, ctx)), 6)
        self.assertEqual(_refusal(stock.STOCK_CLEAR, {"items": six + ["kale"]}, ctx), stock.TOO_MANY.format(count=7))
        self.assertEqual(len(stock.STOCK_CHECKED.plan({"in": six + ["kale"]}, ctx)[0]["args"]["yes"]), 7)
        self.assertEqual(_refusal(stock.STOCK_CLEAR, {"items": ["basil", 3]}, ctx), stock.BAD_ITEM)


if __name__ == "__main__":
    unittest.main()
