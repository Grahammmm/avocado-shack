"""RF1300-12: lookup folds accents, typographic apostrophes/dashes and spacing (real content read-only)."""

from __future__ import annotations

import unittest

from hass.content_model import Content, load_content
from hass.ops.catalog import lookup


def _ids_named(content, *names):
    return sorted(p["id"] for p in content.products if p["name"] in names)


def _synthetic(*names):
    products = [{"id": f"p-{i:02d}", "name": n, "brand": "Plain", "status": "active"} for i, n in enumerate(names)]
    return Content(products=products, makers={}, community={}, store={})


class LookupFoldRealContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = load_content()

    def one(self, *names):
        ids = _ids_named(self.content, *names)
        self.assertEqual(len(ids), 1, names)
        return ids[0]

    def test_apostrophes_find_both_lions_mane_products(self):
        expected = _ids_named(self.content, "Lion\u2019s mane mushrooms", "Dried lion\u2019s mane mushrooms")
        self.assertEqual(len(expected), 2)
        for query in ("lion's mane", "lions mane", "LION\u2019S MANE", "  lion's   mane "):
            with self.subTest(query=query):
                got = lookup(self.content, "product", query)
                self.assertNotIn("match", got)
                self.assertEqual([c["id"] for c in got["candidates"]], expected)
                self.assertTrue(all("\u2019" in c["name"] for c in got["candidates"]))

    def test_accents(self):
        self.assertEqual(lookup(self.content, "product", "jalapenos"), {"match": self.one("Jalape\u00f1os")})
        self.assertEqual(lookup(self.content, "product", "chevre"), {"match": self.one("Ch\u00e8vre")})
        chips = self.one("Monta\u00f1a de Oro Sea Salt tortilla chips")
        self.assertEqual(lookup(self.content, "product", "montana de oro"), {"match": chips})

    def test_maker_key_returned_unchanged(self):
        for query in ("avas", "ava's", "AVA\u2019S"):
            with self.subTest(query=query):
                self.assertEqual(lookup(self.content, "maker", query), {"match": "Ava\u2019s"})

    def test_brand_and_display_brand(self):
        by_brand = sorted(p["id"] for p in self.content.products
                          if "Ava\u2019s" in (p.get("brand"), p.get("displayBrand")))
        self.assertTrue(by_brand)
        got = lookup(self.content, "product", "ava's")
        ids = [got["match"]] if "match" in got else [c["id"] for c in got["candidates"]]
        self.assertEqual(ids, by_brand[:10])

    def test_nothing_to_fold(self):
        for query in ("zzz", "\u2019", "  '  ", None, 7, ["lion's mane"]):
            with self.subTest(query=query):
                self.assertEqual(lookup(self.content, "product", query), {"candidates": []})
                self.assertEqual(lookup(self.content, "maker", query), {"candidates": []})

    def test_unknown_kind_still_refused(self):
        with self.assertRaises(ValueError):
            lookup(self.content, "hike", "lion's mane")


class LookupFoldSynthetic(unittest.TestCase):
    def test_typographic_dash(self):
        content = _synthetic("Half\u2011and\u2011half", "Halfway bread")
        self.assertEqual(lookup(content, "product", "half-and-half"), {"match": "p-00"})
        self.assertEqual(lookup(content, "product", "half\u2014and\u2013half"), {"match": "p-00"})
        self.assertEqual(lookup(content, "product", "half and half"), {"candidates": []})

    def test_curly_quotes_fold_to_straight(self):
        content = _synthetic("\u201cHouse\u201d blend", "House salad")
        self.assertEqual(lookup(content, "product", '"house" blend'), {"match": "p-00"})

    def test_original_text_returned(self):
        content = _synthetic("Cr\u00e8me fra\u00eeche", "Cr\u00e8me br\u00fbl\u00e9e")
        got = lookup(content, "product", "CREME")
        self.assertEqual([c["name"] for c in got["candidates"]], ["Cr\u00e8me fra\u00eeche", "Cr\u00e8me br\u00fbl\u00e9e"])

    def test_cap_and_order_unchanged(self):
        content = _synthetic(*[f"Jalape\u00f1o batch {n}" for n in range(12)])
        content.products.reverse()
        got = lookup(content, "product", "jalapeno")
        ids = [c["id"] for c in got["candidates"]]
        self.assertEqual(ids, [f"p-{i:02d}" for i in range(10)])


if __name__ == "__main__":
    unittest.main()
