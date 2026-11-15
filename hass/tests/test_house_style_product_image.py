"""check_product: a non-text picture path is an ordinary hard failure, never a TypeError."""
from __future__ import annotations

import copy
import pathlib
import unittest
from unittest import mock

from hass import house_style as hs

SPEC = hs.load_spec()
MAKERS = {"maker-a": {}}
GOOD = {"id": "photo-product-001", "name": "Pantry beans", "brand": "Bean Co", "category": "pantry",
        "image": "assets/products/photo-product-001.webp", "description": "x", "producerKey": "maker-a",
        "displayBrand": "Bean Co", "status": "active"}
PATH = "picture path"
NAMES = ["fields", "shelf is one of the nine", "id photo-product-NNN", "displayBrand follows brand",
         "maker link", "unknown producer has no maker key", PATH, "name and brand text"]


class Str(str):
    pass


def product(**kw):
    return dict(GOOD, **kw)


def path_check(out):
    return out["checks"][6]


class ProductImageTests(unittest.TestCase):
    def test_json_nontext_image_values_hard_fail_without_exception(self):
        for value in (None, True, False, 7, 1.5, [], ["a"], {}, {"a": 1}):
            with self.subTest(image=value):
                rec = product(image=value)
                before = copy.deepcopy(rec)
                out = hs.check_product(rec, MAKERS, SPEC)
                self.assertEqual(rec, before)
                self.assertEqual(path_check(out), {"name": PATH, "ok": False, "detail": value, "weight": 2, "hard": True})
                self.assertFalse(out["pass"])
                self.assertEqual(out["hard_failures"], [PATH])
                self.assertEqual([c["name"] for c in out["checks"]], NAMES)
                self.assertEqual(out["score"], 88)

    def test_missing_empty_and_invalid_string_paths_keep_legacy_result(self):
        rec = dict(GOOD)
        del rec["image"]
        out = hs.check_product(rec, MAKERS, SPEC)
        self.assertEqual(out["hard_failures"], ["fields", PATH])
        self.assertEqual(path_check(out)["detail"], "")
        bad = ["", "   ", "/assets/products/photo-product-001.webp", "assets/products/../photo-product-001.webp",
               "assets/products/photo-product-001.png", "assets/products/photo-PRODUCT-001.webp",
               "assets/products/photo-0123456789ABCDEF.png", "assets/products/photo-0123456789abcdef.gif",
               "assets/products/photo-product-001.webp?x=1"]
        for value in bad:
            with self.subTest(image=value):
                out = hs.check_product(product(image=value), MAKERS, SPEC)
                self.assertEqual(path_check(out), {"name": PATH, "ok": False, "detail": value, "weight": 2, "hard": True})
                self.assertEqual(out["hard_failures"], [PATH])
                self.assertFalse(out["pass"])
                self.assertEqual(out["score"], 88)

    def test_catalog_and_owner_string_paths_keep_exact_good_result(self):
        for value in ("assets/products/photo-product-001.webp", "assets/products/photo-0123456789abcdef.jpg",
                      "assets/products/photo-0123456789abcdef.png",
                      Str("assets/products/photo-product-001.webp")):
            with self.subTest(image=value):
                out = hs.check_product(product(image=value), MAKERS, SPEC)
                self.assertEqual(path_check(out), {"name": PATH, "ok": True, "detail": value, "weight": 2, "hard": True})
                self.assertEqual(out["hard_failures"], [])
                self.assertTrue(out["pass"])
                self.assertEqual(out["score"], 100)
                self.assertEqual([c["name"] for c in out["checks"]], NAMES)
                self.assertEqual(out["checks"][-1], {"name": "name and brand text", "ok": True, "detail": "ok",
                                                     "weight": 1, "hard": True})

    def test_nontext_path_does_not_mask_another_existing_failure(self):
        out = hs.check_product(product(image=None, name=""), MAKERS, SPEC)
        self.assertEqual(out["hard_failures"], [PATH, "name and brand text"])
        self.assertFalse(out["pass"])
        out = hs.check_product(product(image={}, brand="   ", displayBrand="   "), MAKERS, SPEC)
        self.assertEqual(out["hard_failures"], [PATH, "name and brand text"])

    def test_picture_path_validation_is_pure_and_pillow_free(self):
        for value in (b"assets/products/photo-product-001.webp", pathlib.PurePosixPath("assets/products/photo-product-001.webp")):
            with self.subTest(image=type(value).__name__):
                rec = product(image=value)
                before = copy.deepcopy(rec)
                with mock.patch("builtins.open", side_effect=AssertionError("file opened")):
                    first = hs.check_product(rec, MAKERS, SPEC)
                    second = hs.check_product(rec, MAKERS, SPEC)
                self.assertEqual(first, second)
                self.assertEqual(rec, before)
                self.assertEqual(first["hard_failures"], [PATH])
                self.assertIs(path_check(first)["detail"], value)
        self.assertFalse(hasattr(hs, "Image"))


if __name__ == "__main__":
    unittest.main()
