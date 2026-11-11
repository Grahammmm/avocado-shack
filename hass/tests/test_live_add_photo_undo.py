"""HASS-LIVE-ADD-2: a picture may go live for an existing product, and undo takes a whole new-maker item back in one revert.

* ``product.set_photo`` is a LIVE row ({id, photo, imageAlt}): a real draft for an existing product passes
  ``live_policy.check``; an extra argument (the name, the brand, anything else), a claim in the picture words, or a protected
  field change is refused. Real op, real throwaway writer repo (hass.tests.test_set_photo.PhotoRepo).
* ``maker.add`` + ``product.add`` (+ picture and a shelf check) is one change; one ``history.revert`` hides the product AND
  the maker, so neither is in producers.json any more, and nothing is deleted (the maker record stays, hidden).
Run: python3 -B -m unittest hass.tests.test_live_add_photo_undo -v
"""
import json
from pathlib import Path

from hass import editor, live_policy as policy
from hass.tests.test_catalog_ops import NEW, _req
from hass.tests.test_editor import git
from hass.tests.test_set_photo import ALT, FIXTURES, PID, SetPhotoTestCase, _photo

KEY = "Harbor Lane"
MAKER = {"key": KEY, "name": KEY, "place": "Morro Bay, California",
         "story": "Harbor Lane makes small-batch fruit jam and relish in a shared kitchen in Morro Bay."}
PRODUCERS, MAKERS, PRODUCTS = "storefront-mockup/producers.json", "hass/content/makers.json", "hass/content/products.json"
NEW_ID = "photo-product-175"


class LivePolicyForPhotos(SetPhotoTestCase):
    def draft(self, *ops):
        out = self.repo.prepare(_req(*ops))
        self.assertEqual(out["result"], "ok", out)
        return out["draft"]

    def test_a_picture_for_an_existing_product_may_go_live(self):
        draft = self.draft(_photo(PID, self.jpg))
        self.assertEqual([c["op"] for c in draft["ops"]], ["product.set_photo"])
        self.assertEqual(set(draft["ops"][0]["args"]), set(policy.LIVE["product.set_photo"]))
        self.assertEqual([(r["collection"], r["key"]) for r in draft["records"]], [("products", PID)])
        self.assertEqual(policy.check(draft), [])

    def test_the_picture_words_need_to_say_what_the_photo_shows_and_stay_claim_free(self):
        """Preparing already refuses a placeholder; the live gate refuses a claim in words that read like a real caption."""
        for claim in ("Organic avocados in a wooden crate", "Award-winning jam jars on a counter", "Farm fresh peaches grown in Paso Robles"):
            with self.subTest(alt=claim):
                reasons = policy.check(self.draft(_photo(PID, self.jpg, claim)))
                self.assertTrue(reasons, claim)

    def test_an_extra_argument_is_refused_in_plain_words(self):
        draft = self.draft(_photo(PID, self.jpg))
        for extra, value in (("name", "Another name"), ("brand", "Someone Else"), ("producerKey", "Etto"), ("image", "assets/products/x.jpg"),
                             ("description", "Soft and sweet.")):
            with self.subTest(extra=extra):
                tampered = json.loads(json.dumps(draft))
                tampered["ops"][0]["args"][extra] = value
                self.assertEqual(policy.check(tampered), [f"not live: product.set_photo.{extra}"])
                self.assertIn(policy.KEPT, policy.refusal([f"not live: product.set_photo.{extra}"]))

    def test_a_picture_that_also_changes_a_protected_field_is_refused(self):
        draft = self.draft(_photo(PID, self.jpg))
        draft["records"][0]["after"] = {**draft["records"][0]["after"], "brand": "Someone Else"}
        self.assertEqual(policy.check(draft), ["protected field: products.brand"])

    def test_a_picture_in_the_same_draft_as_a_private_change_is_still_refused(self):
        draft = self.draft(_photo(PID, self.jpg), ("product.edit", {"id": PID, "name": "New plain name"}))
        self.assertEqual(policy.check(draft), ["not live: product.edit.name"])

    def test_a_picture_for_a_new_product_is_a_photo_argument_of_the_add_not_a_second_op(self):
        """The live table judges product.add on its own row; set_photo carries only what is listed above."""
        self.assertEqual(policy.LIVE["product.set_photo"], {"id", "photo", "imageAlt"})
        self.assertNotIn("product.set_photo", policy.PRIVATE)


class UndoOfTheNewMakerBundle(SetPhotoTestCase):
    def snapshot(self, *rels):
        return {rel: self.repo.read(rel) for rel in rels}

    def bundle(self):
        return self.repo.run(
            ("maker.add", MAKER),
            ("product.add", {**{k: v for k, v in NEW.items() if k != "image"}, "name": "Harbor Lane strawberry jam", "brand": KEY,
                             "displayBrand": KEY, "producerKey": KEY, "photo": self.jpg, "imageAlt": ALT}),
            ("store.confirm_selection", {"yes": [NEW_ID]}))

    def producers(self):
        return json.loads(self.repo.read(PRODUCERS))

    def count_commits(self):
        return int(git(self.repo.wt, "rev-list", "--count", "HEAD"))

    def test_one_revert_hides_the_product_and_the_maker_and_producers_json_drops_both(self):
        before = self.snapshot(PRODUCERS)
        self.assertNotIn(KEY, self.producers())
        base = self.count_commits()
        added = self.bundle()
        self.assertEqual(self.count_commits(), base + 1)  # the whole item is one commit
        self.assertEqual([(r["collection"], r["key"]) for r in added["records"]][:2], [("makers", KEY), ("products", NEW_ID)])
        self.assertIn(KEY, self.producers())
        self.assertIn(KEY, self.repo.makers())
        self.assertEqual(next(p for p in self.repo.products() if p["id"] == NEW_ID)["status"], "active")
        self.assertIn(NEW_ID, [p["id"] for p in self.repo.catalog()])

        draft = self.repo.prepare(_req(("history.revert", {"changeId": added["change_id"]})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual([c["op"] for c in draft["draft"]["ops"]], ["history.revert"])  # one revert, not one per record
        self.assertEqual(policy.check(draft["draft"]), [])  # undo always passes the live gate
        self.assertEqual(self.repo.apply(draft["draft"])["result"], "applied")
        self.assertEqual(self.count_commits(), base + 2)  # one more commit: the undo
        self.assertEqual(git(self.repo.wt, "status", "--porcelain").strip(), "")

        product = next(p for p in self.repo.products() if p["id"] == NEW_ID)
        self.assertEqual(product["status"], "hidden")  # hidden, never deleted
        self.assertNotIn("available", product)
        self.assertNotIn("available_on", product)
        self.assertIs(self.repo.makers()[KEY]["hidden"], True)  # the maker is hidden too, its record stays
        self.assertNotIn(NEW_ID, [p["id"] for p in self.repo.catalog()])
        self.assertNotIn(KEY, self.producers())
        self.assertEqual(self.snapshot(PRODUCERS), before)  # producers.json is the earlier bytes again
        self.repo.content()  # the restored content validates
        record = json.loads((self.repo.state / "changes" / f"{added['change_id']}.json").read_text("utf-8"))
        self.assertIn("revertedBy", record)

    def test_the_picture_file_stays_and_other_products_are_untouched(self):
        others = [p for p in self.repo.products() if p["id"] != NEW_ID]
        added = self.bundle()
        photo = Path(self.repo.wt, self.target(self.jpg))
        self.assertTrue(photo.is_file())
        self.repo.run(("history.revert", {"changeId": added["change_id"]}))
        self.assertTrue(photo.is_file())  # the committed file stays, unreferenced
        self.assertEqual([p for p in self.repo.products() if p["id"] != NEW_ID], others)
        self.assertEqual(self.repo.makers()[KEY]["story"], MAKER["story"])

    def test_the_revert_is_one_change_of_its_own(self):
        added = self.bundle()
        undo = self.repo.run(("history.revert", {"changeId": added["change_id"]}))
        self.assertNotEqual(undo["change_id"], added["change_id"])
        self.assertEqual([c["op"] for c in undo["ops"]], ["history.revert"])
        touched = {(r["collection"], r["key"]) for r in undo["records"]}
        self.assertLessEqual({("makers", KEY), ("products", NEW_ID)}, touched)  # both go back in this one change

if __name__ == "__main__":
    import unittest
    unittest.main()
