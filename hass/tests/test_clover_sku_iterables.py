"""RF1450-11: generate_sku keeps every SKU/barcode reservation when items arrive as a single-pass iterable. Synthetic items only.
Run: python3 -B -m unittest hass.tests.test_clover_sku_iterables
"""
import unittest

from hass.clover import mapper as m
from hass.clover import sku


def mk(i, name="Other", sku_="", code="", hidden=False):
    return m.CloverItem(id=f"FAKEITEM{i:04d}", name=name, sku=sku_, code=code, price_cents=500, price_type="FIXED", unit_name="", categories=(),
                        tags=(), stock=None, stock_modified=None, hidden=hidden, available=True, modified_time=1)


def forms(items):
    return {"list": list(items), "tuple": tuple(items), "iterator": iter(list(items)), "generator": (i for i in list(items))}


class OnePass:
    def __init__(self, items):
        self.items, self.calls = list(items), 0

    def __iter__(self):
        self.calls += 1
        if self.calls > 1:
            raise AssertionError("iterated twice")
        return iter(self.items)


class SinglePassSkuTests(unittest.TestCase):
    def test_single_pass_sku_collision_uses_next_number(self):
        till = [mk(1, sku_="AS-PAN-THING-01")]
        for label, src in forms(till).items():
            with self.subTest(form=label):
                self.assertEqual(sku.generate_sku("Thing", "pantry", src), "AS-PAN-THING-02")

    def test_single_pass_barcode_and_hidden_collisions_are_reserved(self):
        till = [mk(1, code="as-pan-thing-01"), mk(2, sku_="AS-PAN-THING-02", hidden=True)]
        for label, src in forms(till).items():
            with self.subTest(form=label):
                self.assertEqual(sku.generate_sku("Thing", "pantry", src), "AS-PAN-THING-03")
        self.assertEqual([i.code for i in till], ["as-pan-thing-01", ""])

    def test_single_pass_exhaustion_raises_instead_of_reissuing(self):
        till = [mk(n, name=f"Other {n}", sku_=f"AS-PAN-THING-{n:02d}") for n in range(1, 100)]
        for label, src in forms(till).items():
            with self.subTest(form=label), self.assertRaises(sku.SkuExhausted):
                sku.generate_sku("Thing", "pantry", src)

    def test_duplicate_name_selection_and_empty_iterable_preserve_controls(self):
        till = [mk(9, name="thing"), mk(3, name=" Thing "), mk(1, name="Thing", hidden=True)]
        for label, src in forms(till).items():
            with self.subTest(form=label), self.assertRaises(sku.DuplicateItem) as cm:
                sku.generate_sku("Thing", "pantry", src)
            self.assertEqual(cm.exception.item.id, "FAKEITEM0003")
        self.assertEqual(sku.generate_sku("Thing", "pantry", iter(())), "AS-PAN-THING-01")
        self.assertEqual(sku.generate_sku("Thing", "pantry", [mk(1, name="Thing", hidden=True, sku_="AS-PAN-THING-01")]), "AS-PAN-THING-02")

    def test_one_pass_source_is_not_reiterated_and_caller_order_unchanged(self):
        till = [mk(5, sku_="AS-PAN-THING-02"), mk(2, sku_="AS-PAN-THING-01")]
        before = list(till)
        src = OnePass(till)
        self.assertEqual(sku.generate_sku("Thing", "pantry", src), sku.generate_sku("Thing", "pantry", till))
        self.assertEqual(sku.generate_sku("Thing", "pantry", till), "AS-PAN-THING-03")
        self.assertEqual(src.calls, 1)
        self.assertEqual(till, before)


if __name__ == "__main__":
    unittest.main()
