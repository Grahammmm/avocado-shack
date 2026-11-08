"""SKILLS-ITEMADD-1 (SCOPE-3): undoing a new item that came with today's shelf check (hass/ops/history.py).

``item.add`` drafts ``product.add`` plus ``store.confirm_selection`` (D2) when today's check is not recorded yet, else
``product.add`` plus ``product.set_availability``. The undo hides the new product (never deletes it) and drops the stock
word and day the same change gave it, so the content stays valid when the shelf-check day goes back. Everything else
comes back byte for byte. Throwaway CatalogRepo (temp repo + temp state dir, fixture content only).
Run: python3 -B -m unittest hass.tests.test_undo_new_item -v
"""

import json

from hass.content_model import shop_today
from hass.tests.test_catalog_ops import NEW, CatalogTestCase
from hass.tests.test_editor import git

REVERT, CHECK, WORD = "history.revert", "store.confirm_selection", "product.set_availability"
PRODUCTS, STORE = "hass/content/products.json", "hass/content/store.json"
GENERATED = ("storefront-mockup/catalog-products.js", "storefront-mockup/index.html", "storefront-mockup/producers.js",
             "storefront-mockup/producers.json")
FIRST, SECOND = "photo-product-175", "photo-product-176"
OTHER = "photo-product-001"
SECOND_ITEM = {**NEW, "name": "Test medlar", "description": "Soft and sweet once bletted."}


class UndoNewItemTests(CatalogTestCase):
    def snapshot(self, repo):
        return {rel: repo.read(rel) for rel in (PRODUCTS, STORE, "hass/content/makers.json") + GENERATED}

    def undo(self, repo, change):
        return repo.run((REVERT, {"changeId": change["change_id"]}))

    def product(self, repo, pid):
        return next(p for p in repo.products() if p["id"] == pid)

    def assert_back_except_hidden(self, repo, before, *hidden):
        """Every file is the earlier bytes, except products.json, which only gains the hidden new products (the
        declared residue: hidden, not deleted), each without a stock word or day."""
        now = self.snapshot(repo)
        for rel in before:
            if rel != PRODUCTS:
                self.assertEqual(now[rel], before[rel], rel)
        earlier = json.loads(before[PRODUCTS])["products"]
        products = repo.products()
        self.assertEqual(products[:len(earlier)], earlier)
        extra = products[len(earlier):]
        self.assertEqual([p["id"] for p in extra], list(hidden))
        for p in extra:
            self.assertEqual(p["status"], "hidden")
            self.assertNotIn("available", p)
            self.assertNotIn("available_on", p)
        repo.content()  # the restored content validates
        self.assertEqual(git(repo.wt, "status", "--porcelain").strip(), "")

    def test_new_item_with_the_shelf_check_undoes_to_the_previous_bytes(self):
        repo = self.repo()
        self.assertNotIn("selection_checked_on", json.loads(repo.read(STORE)))
        before = self.snapshot(repo)
        added = repo.run(("product.add", NEW), (CHECK, {"yes": [FIRST]}))
        self.assertEqual(json.loads(repo.read(STORE))["selection_checked_on"], shop_today().isoformat())
        self.assertEqual(self.product(repo, FIRST)["available"], "yes")
        undo = self.undo(repo, added)
        self.assert_back_except_hidden(repo, before, FIRST)
        record = json.loads((repo.state / "changes" / f"{added['change_id']}.json").read_text("utf-8"))
        self.assertEqual(record["revertedBy"], undo["change_id"])

    def test_undo_when_the_shelf_check_was_already_today(self):
        repo = self.repo()
        repo.run((CHECK, {}))
        before = self.snapshot(repo)
        added = repo.run(("product.add", NEW), (WORD, {"id": FIRST, "available": "limited"}))
        self.assertEqual(self.product(repo, FIRST)["available_on"], shop_today().isoformat())
        self.undo(repo, added)
        self.assert_back_except_hidden(repo, before, FIRST)
        self.assertEqual(json.loads(repo.read(STORE))["selection_checked_on"], shop_today().isoformat())

    def test_two_items_added_then_undo_only_the_last(self):
        repo = self.repo()
        repo.run(("product.add", NEW), (CHECK, {"yes": [FIRST]}))
        between = self.snapshot(repo)
        second = repo.run(("product.add", SECOND_ITEM), (WORD, {"id": SECOND, "available": "no"}))
        self.undo(repo, second)
        self.assert_back_except_hidden(repo, between, SECOND)
        first = self.product(repo, FIRST)
        self.assertEqual((first["status"], first["available"], first["available_on"]),
                         ("active", "yes", shop_today().isoformat()))

    def test_undo_after_a_manual_edit(self):
        repo = self.repo()
        added = repo.run(("product.add", NEW), (CHECK, {"yes": [FIRST]}))
        # a hand edit of another product, committed in the writer worktree: undo keeps it
        data = json.loads(repo.read(PRODUCTS))
        next(p for p in data["products"] if p["id"] == OTHER)["description"] = "Edited by hand."
        (repo.wt / PRODUCTS).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
        git(repo.wt, "commit", "-q", "-am", "hand edit")
        self.undo(repo, added)
        self.assertEqual(self.product(repo, OTHER)["description"], "Edited by hand.")
        self.assertEqual(self.product(repo, FIRST)["status"], "hidden")
        self.assertNotIn("selection_checked_on", json.loads(repo.read(STORE)))
        repo.content()

    def test_undo_after_the_new_item_itself_was_edited_is_a_conflict(self):
        repo = self.repo()
        added = repo.run(("product.add", NEW), (CHECK, {"yes": [FIRST]}))
        repo.run(("product.edit", {"id": FIRST, "description": "Sweet when baked."}))
        before = self.snapshot(repo)
        result = self.assertRejected(repo, "refused", (REVERT, {"changeId": added["change_id"]}))
        self.assertEqual(result["reason"], f"conflict: products {FIRST} changed after {added['change_id']}")
        self.assertEqual(self.snapshot(repo), before)
