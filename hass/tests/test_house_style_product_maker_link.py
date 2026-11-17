"""check_product: a nontext producerKey fails the hard 'maker link' check instead of raising TypeError."""
from __future__ import annotations

import copy
import unittest
from unittest import mock

from hass import house_style as hs

SPEC = hs.load_spec()
MAKERS = {"maker-a": {}}
GOOD = {"id": "photo-product-001", "name": "Pantry beans", "brand": "Bean Co", "category": "pantry",
        "image": "assets/products/photo-product-001.webp", "description": "x", "producerKey": "maker-a",
        "displayBrand": "Bean Co", "status": "active"}
CHECK = "maker link"


def link(out):
    return [c for c in out["checks"] if c["name"] == CHECK][0]


class MakerLinkTests(unittest.TestCase):
    def test_json_nontext_maker_keys_hard_fail_without_exception(self):
        for key in ([], {}, ["maker-a"], {"name": "maker-a"}, True, False, 0, 1, 1.5):
            with self.subTest(key=key):
                out = hs.check_product(dict(GOOD, producerKey=key), MAKERS, SPEC)
                self.assertFalse(out["pass"])
                self.assertIn(CHECK, out["hard_failures"])
                c = link(out)
                self.assertEqual((c["ok"], c["hard"], c["weight"]), (False, True, 3))
                self.assertEqual(len(out["checks"]), 8)

    def test_none_existing_and_unknown_string_keys_keep_results(self):
        self.assertTrue(link(hs.check_product(dict(GOOD, producerKey=None, brand="Bean Co"), MAKERS, SPEC))["ok"])
        ok = hs.check_product(GOOD, MAKERS, SPEC)
        self.assertTrue(ok["pass"])
        self.assertEqual(ok["score"], 100)
        self.assertEqual(link(ok), {"name": CHECK, "ok": True, "detail": "maker-a", "weight": 3, "hard": True})
        for key in ("", "Missing Mill", "MAKER-A"):
            with self.subTest(key=key):
                out = hs.check_product(dict(GOOD, producerKey=key), MAKERS, SPEC)
                self.assertFalse(link(out)["ok"])
                self.assertIn(CHECK, out["hard_failures"])

    def test_nontext_key_cannot_match_nonstring_mapping_key(self):
        for key in (1, True, 2.5):
            with self.subTest(key=key):
                out = hs.check_product(dict(GOOD, producerKey=key), {1: {}, 2.5: {}}, SPEC)
                self.assertFalse(link(out)["ok"])
                self.assertFalse(out["pass"])

    def test_missing_key_retains_fields_failure(self):
        rec = dict(GOOD)
        del rec["producerKey"]
        out = hs.check_product(rec, MAKERS, SPEC)
        self.assertFalse(out["pass"])
        self.assertIn("fields", out["hard_failures"])

    def test_checker_is_pure_and_other_failures_survive(self):
        rec = dict(GOOD, producerKey=["maker-a"], image="nope.png", name="")
        before, makers_before = copy.deepcopy(rec), copy.deepcopy(MAKERS)
        with mock.patch("builtins.open", side_effect=AssertionError("file io")):
            a = hs.check_product(rec, MAKERS, SPEC)
            b = hs.check_product(rec, MAKERS, SPEC)
        self.assertEqual(a, b)
        self.assertEqual(rec, before)
        self.assertEqual(MAKERS, makers_before)
        for name in (CHECK, "picture path", "name and brand text"):
            self.assertIn(name, a["hard_failures"])


if __name__ == "__main__":
    unittest.main()
