"""AV1222-02 (H06): a product's result check also compares the card's availability word and, after a photo change, its image.

Target tests always run; browser tests skip without PLAYWRIGHT_MODULE (like test_preview).
The expected word is sitegen.availability_label's own answer for the store and date the files were generated from.
"""

import os
import unittest
from datetime import date, timedelta

from hass import preview, sitegen
from hass.content_model import load_and_validate
from hass.tests.test_preview import BrowserCase

TODAY = date(2026, 11, 4)
CHECKED = TODAY.isoformat()
OLD, NEW = "assets/products/photo-product-001.webp", "assets/products/photo-product-016.webp"


def product(**fields):
    return {"id": "p-1", "name": "Avocados", "status": "active", "description": "Ripe.", "image": OLD, **fields}


def record(before=None, **after):
    return {"collection": "products", "key": "p-1", "before": before, "after": product(**after)}


def store(checked=CHECKED):
    return {"selection_checked_on": checked} if checked else {}


class TargetTests(unittest.TestCase):
    def test_no_store_keeps_todays_shape(self):
        self.assertEqual(preview.target_for(record(available="no", available_on=CHECKED)),
                         {"kind": "product", "id": "p-1", "name": "Avocados", "status": "active", "description": "Ripe."})

    def test_expected_word_is_the_sitegen_label(self):
        fresh = record(available="no", available_on=CHECKED)
        self.assertEqual(preview.target_for(fresh, store(), TODAY)["availability"], "Sold out")
        stale = (TODAY - timedelta(days=9)).isoformat()
        got = preview.target_for(record(available="no", available_on=stale), store(stale), TODAY)["availability"]
        self.assertTrue(got.startswith("Last confirmed "), got)
        self.assertEqual(got, sitegen.availability_label(product(available="no", available_on=stale), store(stale), TODAY))
        # a word set on an older check than the store's latest one is not current either
        older = (TODAY - timedelta(days=2)).isoformat()
        self.assertTrue(preview.target_for(record(available="yes", available_on=older), store(), TODAY)
                        ["availability"].startswith("Last confirmed "))

    def test_no_word_is_none_but_present(self):
        for rec, st in ((record(), store()), (record(available="no", available_on=CHECKED), store(None))):
            with self.subTest(rec=rec, store=st):
                self.assertIsNone(preview.target_for(rec, st, TODAY)["availability"])

    def test_hidden_product_gets_no_availability_or_image(self):
        target = preview.target_for(record({"image": OLD}, status="hidden", image=NEW, available="no"), store(), TODAY)
        self.assertEqual(sorted(target), ["description", "id", "kind", "name", "status"])

    def test_image_only_after_a_photo_change(self):
        self.assertEqual(preview.target_for(record({"image": OLD}, image=NEW))["image"], NEW)
        self.assertNotIn("image", preview.target_for(record(None), store(), TODAY))  # a new product has no 'before'
        self.assertNotIn("image", preview.target_for(record({"image": OLD}, description="x")))
        self.assertNotIn("image", preview.target_for(record({"image": OLD}, image=None)))


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class BrowserChecks(BrowserCase):
    def run_check(self, mutate, **target_extra):
        wt = self.repo.wt
        content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
        item = next(p for p in content.products if p["id"] == "photo-product-001")
        mutate(content, item)
        files = sitegen.render(content, wt / "hass" / "templates", today=TODAY)
        target = preview.target_for({"collection": "products", "key": item["id"], "after": dict(item),
                                     **target_extra.pop("rec", {})}, content.store, TODAY)
        target.update(target_extra)
        return self.previewer.capture(files, target, self.repo.state / "screenshots" / "pc.png")["checks"]

    def word(self, available, checked=CHECKED, on=CHECKED):
        def mutate(content, item):
            content.store["selection_checked_on"] = checked
            item["available"], item["available_on"] = available, on
        return mutate

    def test_current_word_passes_and_a_stale_page_word_fails(self):
        checks = self.run_check(self.word("no"))
        self.assertTrue(checks["availabilityShown"], checks)
        self.assertTrue(checks["desktop:availabilityShown"], checks)
        checks = self.run_check(self.word("no"), availability="Last confirmed Mon, Nov 2")
        self.assertFalse(checks["availabilityShown"], checks)
        old = (TODAY - timedelta(days=9)).isoformat()
        checks = self.run_check(self.word("no", old, old), availability="Sold out")
        self.assertFalse(checks["availabilityShown"], checks)

    def test_no_word_expected(self):
        def clear(content, item):
            item.pop("available", None), item.pop("available_on", None)
        self.assertTrue(self.run_check(clear)["availabilityShown"])
        self.assertFalse(self.run_check(clear, availability="Sold out")["availabilityShown"])
        self.assertFalse(self.run_check(self.word("no"), availability=None)["availabilityShown"])

    def test_hidden_product_has_only_product_shown(self):
        def hide(content, item):
            item["status"] = "hidden"
        checks = self.run_check(hide)
        self.assertEqual(checks["productShown"], True)
        self.assertNotIn("availabilityShown", checks)
        self.assertNotIn("imageShown", checks)

    def test_photo_change_checks_the_new_src(self):
        def swap(content, item):
            item["image"] = NEW
        rec = {"rec": {"before": {"image": OLD}}}
        checks = self.run_check(swap, **rec)
        self.assertTrue(checks["imageShown"] and checks["desktop:imageShown"], checks)
        checks = self.run_check(lambda c, i: None, **rec, image=NEW)  # page still shows the old src
        self.assertFalse(checks["imageShown"], checks)

    def test_description_edit_has_no_image_check(self):
        checks = self.run_check(lambda c, i: i.update(description="Buttery."), rec={"before": {"image": OLD}})
        self.assertNotIn("imageShown", checks)


if __name__ == "__main__":
    unittest.main()
