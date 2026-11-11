"""check_product: name/brand text follows the content validator (blank, markup, control, length, non-string)."""
from __future__ import annotations

import copy
import unittest

from hass import house_style as hs
from hass.content_model import FORBIDDEN_TEXT, TEXT_LIMITS, _text

SPEC = hs.load_spec()
MAKERS = {"maker-a": {}}
GOOD = {"id": "photo-product-001", "name": "Pantry beans", "brand": "Bean Co", "category": "pantry",
        "image": "assets/products/photo-product-001.webp", "description": "x", "producerKey": "maker-a",
        "displayBrand": "Bean Co", "status": "active"}
CHECK = "name and brand text"


def product(**kw):
    rec = dict(GOOD, **kw)
    if "brand" in kw and "displayBrand" not in kw:
        rec["displayBrand"] = kw["brand"]
    return rec


def last(out):
    return out["checks"][-1]


class ProductTextTests(unittest.TestCase):
    def setUp(self):
        self.assertIn(GOOD["category"], hs.CATEGORIES)
        base = hs.check_product(GOOD, MAKERS, SPEC)
        self.assertTrue(base["pass"], base)
        self.assertEqual(base["score"], 100)

    def assert_hard_fail(self, rec):
        out = hs.check_product(rec, MAKERS, SPEC)
        self.assertFalse(out["pass"], out)
        self.assertIn(CHECK, out["hard_failures"])
        c = last(out)
        self.assertEqual((c["name"], c["ok"], c["hard"], c["weight"], c["detail"]),
                         (CHECK, False, True, 1, "invalid name or brand"))
        return out

    def test_blank_names_and_brands_hard_fail(self):
        for field in ("name", "brand"):
            for value in ("", "   "):
                with self.subTest(field=field, value=value):
                    self.assert_hard_fail(product(**{field: value}))

    def test_forbidden_and_control_text_uses_existing_policy(self):
        values = [f"A{bad}B" for bad in FORBIDDEN_TEXT] + ["Beans\x00", "Be\u200bans", " Beans", "Beans "]
        for field in ("name", "brand"):
            for value in values:
                with self.subTest(field=field, value=value):
                    problems = []
                    _text(problems, field, value, limit=TEXT_LIMITS["product"][field])
                    self.assertTrue(problems)
                    self.assert_hard_fail(product(**{field: value}))

    def test_nonstring_name_and_brand_return_failed_check(self):
        for field in ("name", "brand"):
            for value in (None, True, 7, ["x"], {"a": 1}):
                with self.subTest(field=field, value=value):
                    out = self.assert_hard_fail(product(**{field: value}))
                    self.assertEqual(out["checks"][0]["name"], "fields")

    def test_name_and_brand_length_boundaries_are_hard(self):
        for field, limit in (("name", 80), ("brand", 60)):
            with self.subTest(field=field, case="at limit"):
                out = hs.check_product(product(**{field: "a" * limit}), MAKERS, SPEC)
                self.assertTrue(out["pass"], out)
                self.assertTrue(last(out)["ok"])
            with self.subTest(field=field, case="over limit"):
                self.assert_hard_fail(product(**{field: "a" * (limit + 1)}))

    def test_valid_unicode_digit_names_keep_scores_and_other_checks(self):
        for rec in (product(name="Crème brûlée 2 pack", brand="Café № 5"),
                    product(name="Beans 400", brand="Producer not identified", displayBrand="From the market", producerKey=None)):
            with self.subTest(name=rec["name"]):
                out = hs.check_product(rec, MAKERS, SPEC)
                self.assertTrue(out["pass"], out)
                self.assertEqual(out["score"], 100)
                self.assertEqual(out["hard_failures"], [])
                self.assertEqual((last(out)["name"], last(out)["ok"], last(out)["detail"]), (CHECK, True, "ok"))
                self.assertEqual(len(out["checks"]), 8)

    def test_input_is_not_mutated_and_missing_fields_still_fail(self):
        rec = product(name="  ")
        before = copy.deepcopy(rec)
        first = hs.check_product(rec, MAKERS, SPEC)
        self.assertEqual(rec, before)
        self.assertEqual(first, hs.check_product(rec, MAKERS, SPEC))
        missing = {k: v for k, v in GOOD.items() if k not in ("name", "brand")}
        out = hs.check_product(missing, MAKERS, SPEC)
        self.assertFalse(out["pass"])
        self.assertIn("fields", out["hard_failures"])
        self.assertIn(CHECK, out["hard_failures"])
        self.assertNotIn("name", missing)


if __name__ == "__main__":
    unittest.main()
