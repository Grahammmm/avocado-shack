"""RF1939-10 tests: product, maker and same-day hike duplicate checks fold NFKC look-alikes (as route titles do).

Temp repos only (CatalogRepo / HikeRepo); stored text is never normalized.
Run: python3 -B -m unittest hass.tests.test_lookalike_twins -v
"""

from hass.tests.test_catalog_dupes import FARM
from hass.tests.test_catalog_ops import NEW, CatalogTestCase
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

EGGS = {**NEW, "name": "Eggs", "brand": "Test Orchard"}
WIDE = {"name": "\uff25\uff47\uff47\uff53", "brand": "\uff34est Orchard"}  # full-width "Eggs", "Test Orchard"
FIRST = "photo-product-175"


class LookalikeProductTests(CatalogTestCase):
    def refused(self, repo, *ops):
        return self.assertRejected(repo, "refused", *ops)["reason"]

    def test_add_lookalike_is_refused_and_distinct_names_are_drafted(self):
        repo = self.repo()
        repo.run(("product.add", EGGS))
        self.assertEqual(self.refused(repo, ("product.add", {**EGGS, **WIDE})),
                         f"{FIRST} already has this name and brand; edit it instead")
        self.assertEqual([p["id"] for p in repo.products() if p["name"] == WIDE["name"]], [])  # no draft
        repo.run(("product.add", {**EGGS, "name": "Egg"}))  # real letter differs
        repo.run(("product.add", {**EGGS, "name": "Caf\u00e9"}), ("product.add", {**EGGS, "name": "Cafe"}))  # accents stay
        self.assertEqual(sorted(p["name"] for p in repo.products() if p["name"] in ("Egg", "Caf\u00e9", "Cafe")),
                         ["Cafe", "Caf\u00e9", "Egg"])

    def test_edit_rename_to_lookalike_is_refused(self):
        repo = self.repo()
        repo.run(("product.add", EGGS), ("product.add", {**EGGS, "name": "Other"}))
        self.assertEqual(self.refused(repo, ("product.edit", {"id": "photo-product-176", **WIDE})),
                         f"{FIRST} already has this name and brand")

    def test_wide_to_plain_on_itself_is_a_change(self):
        repo = self.repo()
        repo.run(("product.add", {**EGGS, **WIDE}))
        self.assertEqual(repo.products()[-1]["name"], WIDE["name"])  # stored text is not normalized
        repo.run(("product.edit", {"id": FIRST, "name": "Eggs"}))
        self.assertEqual(repo.products()[-1]["name"], "Eggs")


class LookalikeMakerTests(CatalogTestCase):
    def test_ligature_maker_name_is_refused(self):
        repo = self.repo()
        repo.run(("maker.add", {**FARM, "key": "Fish Farm", "name": "Fish Farm"}))
        result = self.assertRejected(repo, "refused", ("maker.add", {**FARM, "key": "Other Farm", "name": "\ufb01sh farm"}))
        self.assertEqual(result["reason"], "maker Fish Farm already has this name; edit it instead")
        self.assertNotIn("Other Farm", repo.makers())


class LookalikeHikeTests(HikeTestCase):
    def test_same_day_lookalike_title_is_refused_other_day_drafted(self):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "title": "Morning walk"}))
        wide = "\uff2d\uff4f\uff52\uff4e\uff49\uff4e\uff47 walk"
        result = self.assertRejected(repo, "refused", ("hike.create", {**HIKE, "title": wide}))
        self.assertEqual(result["reason"],
                         f"{HIKE_ID.replace('test-hike', 'morning-walk')} is already scheduled with this title "
                         f"on {HIKE['date']}; update it instead")
        repo.run(("hike.create", {**HIKE, "title": wide, "date": "2026-12-06"}))
        self.assertEqual(len(repo.community()["events"]), 2)
