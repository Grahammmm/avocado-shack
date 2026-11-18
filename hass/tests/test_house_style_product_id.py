"""check_product: a nontext product id is an ordinary soft failure, never a TypeError."""
from __future__ import annotations

import copy
import unittest

from hass import house_style as hs

SPEC = hs.load_spec()
MAKERS = {"maker-a": {}}
GOOD = {"id": "photo-product-001", "name": "Pantry beans", "brand": "Bean Co", "category": "pantry",
        "image": "assets/products/photo-product-001.webp", "description": "x", "producerKey": "maker-a",
        "displayBrand": "Bean Co", "status": "active"}
NAMES = ["fields", "shelf is one of the nine", "id photo-product-NNN", "displayBrand follows brand",
         "maker link", "unknown producer has no maker key", "picture path", "name and brand text"]


class Str(str):
    pass


def score(**kw):
    rec = dict(GOOD, **kw)
    before = copy.deepcopy(rec)
    out = hs.check_product(rec, MAKERS, SPEC)
    assert rec == before
    return out


class ProductIdTests(unittest.TestCase):
    def test_nontext_json_ids_return_existing_unsuccessful_soft_check(self):
        for value in (None, True, False, 7, 1.5, [], ["a"], {}, {"a": 1}, b"photo-product-001"):
            with self.subTest(id=value):
                out = score(id=value)
                self.assertEqual([c["name"] for c in out["checks"]], NAMES)
                chk = out["checks"][2]
                self.assertEqual((chk["ok"], chk["weight"], chk["hard"]), (False, 1, False))
                self.assertEqual(chk["detail"], value)
                self.assertEqual((out["score"], out["pass"]), (94, True))

    def test_missing_id_keeps_fields_failure(self):
        rec = dict(GOOD)
        del rec["id"]
        out = hs.check_product(rec, MAKERS, SPEC)
        self.assertFalse(out["checks"][0]["ok"])
        self.assertTrue(out["checks"][0]["hard"])
        self.assertEqual((out["checks"][2]["ok"], out["checks"][2]["detail"]), (False, ""))
        self.assertFalse(out["pass"])

    def test_string_ids_keep_legacy_results(self):
        good = score()
        self.assertEqual((good["score"], good["pass"], good["checks"][2]["ok"]), (100, True, True))
        for value, ok in (("photo-product-001", True), ("photo-product-1234", True), (Str("photo-product-002"), True),
                          ("photo-product-\u0661\u0662\u0663", True), ("", False), (" ", False),
                          ("photo-product-01", False), ("product-001", False), ("photo-product-001\n", False),
                          ("x photo-product-001", False)):
            with self.subTest(id=value):
                chk = score(id=value)["checks"][2]
                self.assertEqual((chk["ok"], chk["detail"]), (ok, value))

    def test_bad_id_does_not_mask_independent_hard_failure(self):
        out = score(id=None, name="", image=None)
        failed = [c["name"] for c in out["checks"] if not c["ok"] and c["hard"]]
        self.assertEqual(failed, ["picture path", "name and brand text"])
        self.assertFalse(out["pass"])


if __name__ == "__main__":
    unittest.main()
