"""RF1150-9 tests: product/maker add and rename refuse a name another record already has (H03, H12).

Temp CatalogRepo repos only (see test_catalog_ops); nothing touches the checkout, the live service or its database.
Run: python3 -m unittest hass.tests.test_catalog_dupes -v
"""

import unittest

from hass.tests.test_catalog_ops import NEW, CatalogTestCase

FIRST = "photo-product-175"  # id the first product.add mints on the fixture content
FARM = {"key": "Test Farm", "name": "Test Farm", "place": "Somewhere, California", "story": "Grows things.",
        "url": "https://example.com/about"}


class ProductDuplicateTests(CatalogTestCase):
    def refused(self, repo, *ops):
        return self.assertRejected(repo, "refused", *ops)["reason"]

    def test_repeat_add_and_case_spacing(self):
        repo = self.repo()
        repo.run(("product.add", NEW))
        self.assertEqual(repo.products()[-1]["id"], FIRST)
        for name, brand in ((NEW["name"], NEW["brand"]), ("test  QUINCE", "test   orchard"), ("TEST QUINCE", "test orchard")):
            with self.subTest(name=name, brand=brand):
                reason = self.refused(repo, ("product.add", {**NEW, "name": name, "brand": brand}))
                self.assertEqual(reason, f"{FIRST} already has this name and brand; edit it instead")
        # Edge spaces are rejected by argument checks before the op runs; nothing is drafted either way.
        self.assertRejected(repo, "invalid", ("product.add", {**NEW, "name": "  test QUINCE "}))
        self.assertEqual(sum(p["name"] == NEW["name"] for p in repo.products()), 1)

    def test_hidden_and_held(self):
        repo = self.repo()
        repo.run(("product.add", NEW))
        repo.run(("product.hide", {"id": FIRST}))
        self.assertEqual(self.refused(repo, ("product.add", NEW)),
                         f"{FIRST} has this name and brand and is hidden; restore it instead")
        reason = self.refused(repo, ("product.add", {**NEW, "name": "raw milk WHITE cheddar", "brand": "sierra nevada"}))
        self.assertEqual(reason, "photo-product-040 has this name and brand and is held; "
                                 "it needs review of the recorded concern")
        for leak in ("Graziers", "recall", "sierranevadacheese.com"):
            self.assertNotIn(leak, reason)

    def test_same_name_other_brand_is_drafted(self):
        repo = self.repo()
        repo.run(("product.add", NEW))
        repo.run(("product.add", {**NEW, "brand": "Other Orchard", "displayBrand": "Other Orchard"}))
        self.assertEqual([p["brand"] for p in repo.products() if p["name"] == NEW["name"]],
                         ["Test Orchard", "Other Orchard"])

    def test_edit_collision(self):
        repo = self.repo()
        repo.run(("product.add", NEW), ("product.add", {**NEW, "brand": "Other Orchard"}),
                 ("product.add", {**NEW, "name": "Test medlar"}))
        other = "photo-product-176"
        cases = (("rename", {"id": "photo-product-001", "name": "test  quince", "brand": "TEST ORCHARD"}),
                 ("brand only", {"id": other, "brand": "test orchard"}),
                 ("name only", {"id": "photo-product-177", "name": "test Quince"}))
        for label, args in cases:
            with self.subTest(label):
                self.assertEqual(self.refused(repo, ("product.edit", args)), f"{FIRST} already has this name and brand")
        repo.run(("product.edit", {"id": "photo-product-001", "description": "Still its own product."}))
        repo.run(("product.edit", {"id": FIRST, "name": "TEST  QUINCE"}))  # own name, other case: not a duplicate
        repo.run(("product.edit", {"id": other, "name": "Test medlar"}))
        names = {p["id"]: p["name"] for p in repo.products()}
        self.assertEqual((names[FIRST], names[other]), ("TEST  QUINCE", "Test medlar"))

    def test_held_twin_is_named_on_edit_without_hold_text(self):
        repo = self.repo()
        reason = self.refused(repo, ("product.edit", {"id": "photo-product-001", "name": "Raw milk white cheddar",
                                                      "brand": "Sierra Nevada"}))
        self.assertEqual(reason, "photo-product-040 already has this name and brand")


class MakerDuplicateTests(CatalogTestCase):
    def refused(self, repo, *ops):
        return self.assertRejected(repo, "refused", *ops)["reason"]

    def test_add_with_existing_name(self):
        repo = self.repo()
        for name in ("Etto", "ETTO", "etto"):
            with self.subTest(name=name):
                reason = self.refused(repo, ("maker.add", {**FARM, "key": "Etto Two", "name": name}))
                self.assertEqual(reason, "maker Etto already has this name; edit it instead")
        self.assertEqual(self.refused(repo, ("maker.add", {**FARM, "key": "Etto"})), "maker Etto already exists")
        repo.run(("maker.add", FARM))
        repo.run(("maker.hide", {"key": "Test Farm"}))
        reason = self.refused(repo, ("maker.add", {**FARM, "key": "Test Farm 2", "name": "test   FARM"}))
        self.assertEqual(reason, "maker Test Farm already has this name; restore it instead")
        self.assertNotIn("Test Farm 2", repo.makers())

    def test_edit_rename(self):
        repo = self.repo()
        other = next(k for k, m in repo.makers().items() if k != "Etto" and m["name"] != "Etto")
        reason = self.refused(repo, ("maker.edit", {"key": other, "name": "eTTo"}))
        self.assertEqual(reason, "maker Etto already has this name")
        repo.run(("maker.add", FARM), ("maker.hide", {"key": "Test Farm"}))
        self.assertEqual(self.refused(repo, ("maker.edit", {"key": "Etto", "name": "Test Farm"})),
                         "maker Test Farm already has this name")
        repo.run(("maker.edit", {"key": "Etto", "name": "ETTO"}))  # own name, other case
        repo.run(("maker.edit", {"key": other, "name": "Brand New Maker Name"}))
        repo.run(("maker.edit", {"key": "Etto", "story": "Slow-dried pasta."}))
        self.assertEqual((repo.makers()["Etto"]["name"], repo.makers()[other]["name"]), ("ETTO", "Brand New Maker Name"))


if __name__ == "__main__":
    unittest.main()
