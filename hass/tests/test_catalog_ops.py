"""H03 tests: product and maker add / edit / hide / restore ops, lookup and organic warning.

Every op runs through ``prepare`` + ``apply`` of the H02 editor on a throwaway Git repo with a linked writer worktree
and a private temp state dir (see test_editor.WriterRepo). Nothing touches the checkout, the live service or its database.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import unittest

from hass import editor, migration_check
from hass.content_model import PRODUCT_PUBLIC_FIELDS, load_and_validate
from hass.ops.catalog import lookup
from hass.tests.test_editor import WriterRepo, git

IMAGE = "assets/products/photo-product-001.webp"
NEW = {"name": "Test quince", "brand": "Test Orchard", "category": "fruit", "image": IMAGE,
       "description": "Tart until cooked, then rosy.", "displayBrand": "Test Orchard"}


def _req(*ops):
    return {"ops": [{"op": name, "args": args} for name, args in ops]}


class CatalogRepo(WriterRepo):
    """WriterRepo using the production op registry (hass.ops.catalog) instead of the test-only ops."""

    def prepare(self, request):
        return editor.prepare(request, state=str(self.state))

    def apply(self, draft):
        return editor.apply(draft["change_id"], draft["draft_hash"], state=str(self.state))

    def run(self, *ops):
        draft = self.prepare(_req(*ops))
        assert draft["result"] == "ok", draft
        result = self.apply(draft["draft"])
        assert result["result"] == "applied", result
        return draft["draft"]

    def read(self, rel):
        return (self.wt / rel).read_bytes()

    def products(self):
        return json.loads(self.read("hass/content/products.json"))["products"]

    def makers(self):
        return json.loads(self.read("hass/content/makers.json"))["makers"]

    def catalog(self):
        return json.loads(self.read("storefront-mockup/catalog-products.js")[len(b"const catalog="):].rstrip(b";\n"))

    def content(self):
        return load_and_validate(self.wt / "hass" / "content", self.wt / "storefront-mockup")


class CatalogTestCase(unittest.TestCase):
    def repo(self):
        repo = CatalogRepo()
        self.addCleanup(repo.cleanup)
        return repo

    def assertRejected(self, repo, result_name, *ops):
        head, drafts = repo.head(), repo.drafts()
        result = repo.prepare(_req(*ops))
        self.assertEqual(result["result"], result_name, result)
        self.assertEqual(repo.head(), head)
        self.assertEqual(repo.drafts(), drafts)
        return result


class ProductAddEditTests(CatalogTestCase):
    def test_add_and_edit(self):
        repo = self.repo()
        repo.run(("product.add", NEW))
        added = repo.products()[-1]
        self.assertEqual(list(added), ["id", "name", "brand", "category", "image", "description", "producerKey",
                                       "displayBrand", "status"])
        self.assertEqual((added["id"], added["status"], added["producerKey"]), ("photo-product-175", "active", None))
        self.assertEqual(len(repo.catalog()), 171)
        public = [p for p in repo.catalog() if p["id"] == "photo-product-175"][0]
        self.assertEqual(sorted(public), sorted(PRODUCT_PUBLIC_FIELDS))

        repo.run(("product.edit", {"id": "photo-product-175", "description": "Sweet when baked."}))
        edited = repo.products()[-1]
        self.assertEqual(list(edited), list(added))
        self.assertEqual({k: v for k, v in edited.items() if added[k] != v}, {"description": "Sweet when baked."})

        repo.run(("product.edit", {"id": "photo-product-175", "producerKey": "Etto"}))
        self.assertEqual(repo.products()[-1]["producerKey"], "Etto")
        repo.run(("product.edit", {"id": "photo-product-175", "clearProducer": True}))
        self.assertIsNone(repo.products()[-1]["producerKey"])

    def test_bad_arguments_are_rejected_without_a_commit(self):
        repo = self.repo()
        for field, bad in (("name", "Quince $3"), ("description", "<b>Quince</b>"), ("category", "gadgets"),
                           ("image", "assets/products/no-such-file.webp")):
            with self.subTest(field=field):
                self.assertRejected(repo, "invalid", ("product.add", {**NEW, field: bad}))
        self.assertRejected(repo, "invalid", ("product.add", {**NEW, "producerKey": "No Such Maker"}))
        self.assertRejected(repo, "needs-details", ("product.edit", {"id": "photo-product-001"}))


class HideRestoreTests(CatalogTestCase):
    def test_hide_and_restore(self):
        repo = self.repo()
        before = repo.read("storefront-mockup/catalog-products.js")
        record = [p for p in repo.products() if p["id"] == "photo-product-001"][0]
        repo.run(("product.hide", {"id": "photo-product-001"}))
        self.assertEqual(len(repo.catalog()), 169)
        hidden = [p for p in repo.products() if p["id"] == "photo-product-001"][0]
        self.assertEqual(hidden, dict(record, status="hidden"))
        self.assertTrue((repo.wt / "storefront-mockup" / record["image"]).is_file())
        self.assertEqual(migration_check.run_checks(repo.wt)[0], [])
        refused = self.assertRejected(repo, "refused", ("product.hide", {"id": "photo-product-001"}))
        self.assertIn("hidden", refused["reason"])

        repo.run(("product.restore", {"id": "photo-product-001"}))
        self.assertEqual(repo.read("storefront-mockup/catalog-products.js"), before)
        refused = self.assertRejected(repo, "refused", ("product.restore", {"id": "photo-product-001"}))
        self.assertIn("active", refused["reason"])

    def test_held_product_stays_blocked(self):
        repo = self.repo()
        for op, args in (("product.restore", {}), ("product.edit", {"name": "Cheddar"}), ("product.hide", {})):
            with self.subTest(op=op):
                result = self.assertRejected(repo, "refused", (op, {"id": "photo-product-040", **args}))
                self.assertIn("Graziers raw-milk cheese recall", result["reason"])
                self.assertIn("https://sierranevadacheese.com/", result["reason"])


class MakerTests(CatalogTestCase):
    def test_edit_hide_restore(self):
        repo = self.repo()
        products_before = repo.read("hass/content/products.json")
        repo.run(("maker.edit", {"key": "Etto", "story": "Slow-dried pasta from Paso Robles."}))
        self.assertEqual(repo.makers()["Etto"]["story"], "Slow-dried pasta from Paso Robles.")
        self.assertIn(b"Slow-dried pasta", repo.read("storefront-mockup/producers.js"))
        self.assertIn(b"Slow-dried pasta", repo.read("storefront-mockup/producers.json"))
        self.assertEqual(repo.read("hass/content/products.json"), products_before)
        self.assertNotIn("catalog-products.js", git(repo.wt, "show", "--name-only", "--format=", "HEAD"))

        counts = {}
        for p in repo.content().active_products():
            if p["producerKey"]:
                counts.setdefault(p["producerKey"], []).append(p["id"])
        key, ids = min(counts.items(), key=lambda item: len(item[1]))
        refused = self.assertRejected(repo, "refused", ("maker.hide", {"key": key}))
        self.assertTrue(all(pid in refused["reason"] for pid in ids), refused)

        generated = {n: repo.read("storefront-mockup/" + n) for n in ("producers.js", "producers.json")}
        repo.run(*[("product.hide", {"id": pid}) for pid in ids])
        repo.run(("maker.hide", {"key": key}))
        for name, data in (("producers.json", json.loads(repo.read("storefront-mockup/producers.json"))),
                           ("producers.js", json.loads(repo.read("storefront-mockup/producers.js")[len(b"const producers="):-1]))):
            self.assertNotIn(key, data, name)
            self.assertEqual(len(data), len(repo.makers()) - 1, name)
        self.assertIs(repo.makers()[key]["hidden"], True)

        repo.run(("maker.restore", {"key": key}))
        self.assertNotIn("hidden", repo.makers()[key])
        for name, data in generated.items():
            self.assertEqual(repo.read("storefront-mockup/" + name), data)

    def test_unknown_maker_is_not_found(self):
        repo = self.repo()
        for op, extra in (("maker.edit", {"story": "Updated story."}), ("maker.hide", {}), ("maker.restore", {})):
            with self.subTest(op=op):
                result = self.assertRejected(repo, "not-found", (op, {"key": "No Such Maker", **extra}))
                self.assertEqual(result["key"], "No Such Maker")
        self.assertRejected(repo, "invalid", ("product.edit", {"id": "photo-product-001", "producerKey": "No Such Maker"}))

    def test_add_requires_https(self):
        repo = self.repo()
        new = {"key": "Test Farm", "name": "Test Farm", "place": "Somewhere, California", "story": "Grows things."}
        self.assertRejected(repo, "invalid", ("maker.add", {**new, "url": "http://example.com/about"}))
        repo.run(("maker.add", {**new, "url": "https://example.com/about"}))
        self.assertEqual(repo.makers()["Test Farm"]["url"], "https://example.com/about")


class LookupAndWarningTests(CatalogTestCase):
    def test_lookup_candidates_and_match(self):
        repo = self.repo()
        head, content = repo.head(), repo.content()
        many = lookup(content, "product", "a")
        self.assertNotIn("match", many)
        self.assertEqual(len(many["candidates"]), 10)
        self.assertEqual([c["id"] for c in many["candidates"]], sorted(c["id"] for c in many["candidates"]))
        self.assertEqual(lookup(content, "product", "zzz-no-such"), {"candidates": []})
        held = lookup(content, "product", "raw milk white cheddar")
        self.assertEqual(held, {"match": "photo-product-040"})
        self.assertEqual(lookup(content, "maker", "ETTO"), {"match": "Etto"})
        self.assertEqual((repo.head(), repo.drafts()), (head, []))

    def test_organic_warning(self):
        repo = self.repo()
        plain = next(p for p in repo.content().active_products()
                     if "organic" not in p["name"].lower() and p["producerKey"] not in
                     ("Ocean Ranch", "Straus", "Green Gold", "Massa Organics"))
        draft = repo.prepare(_req(("product.edit", {"id": plain["id"], "producerKey": "Straus"})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(draft["draft"]["warnings"], [f"adds Organic badge to {plain['id']}"])


if __name__ == "__main__":
    unittest.main()
