"""RF1200-4 (H03) tests: product.edit warns when it removes a product's Organic badge; nothing is refused.

Fixture content only, via test_catalog_ops.CatalogRepo (throwaway Git repo, private temp state dir).
Run: python3 -m unittest hass.tests.test_catalog_badge -v
"""

from hass import conversation
from hass.ops.catalog import ORGANIC_MAKERS
from hass.tests.test_catalog_ops import NEW, CatalogTestCase, _req


class OrganicBadgeRemovalTests(CatalogTestCase):
    def setUp(self):
        self.r = self.repo()
        active = self.r.content().active_products()
        # Named "Organic ..." with a maker that is not organic: the name alone carries the badge.
        self.named = next(p for p in active if p["name"].lower().startswith("organic ")
                          and p["producerKey"] not in ORGANIC_MAKERS)
        self.straus = next(p for p in active if p["producerKey"] == "Straus" and "organic" not in p["name"].lower())
        self.straus_named = next(p for p in active if p["producerKey"] == "Straus" and "organic" in p["name"].lower())
        self.plain = next(p for p in active if "organic" not in p["name"].lower()
                          and p["producerKey"] not in ORGANIC_MAKERS)

    def warnings(self, *ops):
        head, drafts = self.r.head(), self.r.drafts()
        draft = self.r.prepare(_req(*ops))
        self.assertEqual(draft["result"], "ok", draft)  # never refused
        self.assertEqual(self.r.head(), head)  # prepare commits nothing
        self.assertEqual(len(self.r.drafts()), len(drafts) + 1)
        return draft["draft"]["warnings"]

    def removed(self, pid):
        return [f"removes Organic badge from {pid}"]

    def test_rename_away(self):
        pid = self.named["id"]
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "name": "Beet juice"})), self.removed(pid))

    def test_maker_away_and_clear_producer(self):
        pid = self.straus["id"]
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "producerKey": "Etto"})), self.removed(pid))
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "clearProducer": True})), self.removed(pid))
        # Organic maker to another organic maker keeps the badge.
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "producerKey": "Green Gold"})), [])

    def test_still_organic_by_maker_or_new_name(self):
        pid = self.straus_named["id"]
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "name": "Whole milk, Straus"})), [])
        # Name loses the word but the new maker is organic: still badged.
        pid = self.named["id"]
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "name": "Beet juice", "producerKey": "Straus"})),
                         [])
        # Maker cleared but the name still says Organic: still badged.
        self.assertEqual(self.warnings(("product.edit", {"id": self.straus_named["id"], "clearProducer": True})), [])

    def test_word_boundary_and_case(self):
        self.r.run(("product.add", {**NEW, "name": "Organic Milk"}))
        pid = self.r.products()[-1]["id"]
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "name": "Organically Grown Milk"})),
                         self.removed(pid))
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "name": "ORGANIC milk"})), [])

    def test_add_warning_unchanged_and_neutral_edit_silent(self):
        pid = self.plain["id"]
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "producerKey": "Straus"})),
                         [f"adds Organic badge to {pid}"])
        self.assertEqual(self.warnings(("product.edit", {"id": pid, "description": "Good with bread."})), [])
        self.assertEqual(self.warnings(("product.edit", {"id": self.named["id"], "description": "Cold."})), [])

    def test_multi_op_warnings_in_op_order(self):
        add = ("product.edit", {"id": self.plain["id"], "producerKey": "Straus"})
        remove = ("product.edit", {"id": self.named["id"], "name": "Beet juice"})
        self.assertEqual(self.warnings(add, remove),
                         [f"adds Organic badge to {self.plain['id']}"] + self.removed(self.named["id"]))
        self.assertEqual(self.warnings(remove, add),
                         self.removed(self.named["id"]) + [f"adds Organic badge to {self.plain['id']}"])

    def test_refused_edit_gives_no_warning(self):
        refused = self.assertRejected(self.r, "refused", ("product.edit", {
            "id": self.straus["id"], "producerKey": "Etto", "clearProducer": True}))
        self.assertNotIn("warnings", refused)

    def test_approval_text_shows_warning(self):
        pid = self.named["id"]
        draft = self.r.prepare(_req(("product.edit", {"id": pid, "name": "Beet juice"})))
        text = conversation.proposal_text("K7Q", draft["draft"], "2026-10-31T19:00:00+00:00")
        self.assertIn("\nHeads up: This takes off the Organic badge.\n", text)

    def test_maker_rename_gives_no_badge_warning(self):  # AV2137-03: only the old-brand warning, never an Organic badge one
        self.assertEqual(self.warnings(("maker.edit", {"key": "Straus", "name": "Straus Family Creamery"})),
                         ["7 active product cards of maker Straus still show Straus as their brand; ask to change them too"])
