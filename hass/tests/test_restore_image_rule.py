"""RF0310-6 tests: product.restore and history.revert check the image with the shared _image_file_problem rule.

A linked image file or one resolving outside the site folder is refused like a missing one; the fixture site's ``assets``
link (editor test harness) still counts as healthy. Fixtures reuse test_undo_product_restore's throwaway CatalogRepo.
Run: python3 -m unittest hass.tests.test_restore_image_rule -v
"""

import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path

from hass.content_model import SITE_DIR, load_and_validate
from hass.ops import Refused
from hass.ops.catalog import _product_restore
from hass.ops.history import _revert
from hass.tests.test_catalog_ops import CatalogTestCase
from hass.tests.test_editor import git
from hass.tests import test_undo_product_restore as upr  # module import, so its tests are not collected here too
from hass.tests.test_undo_product_restore import P2, P2_IMAGE, PRODUCTS, REVERT, hide

OTHER_IMAGE = "assets/products/photo-product-057.webp"  # another product's photo
LINKED = f"{P2} cannot be restored: image file must not be a link"
OUTSIDE = f"{P2} cannot be restored: image file is outside the site folder"
MISSING = f"{P2} cannot be restored: image file {P2_IMAGE} is missing"


class RestoreImageRuleTests(CatalogTestCase):
    refused, status = upr.UndoProductRestoreTests.refused, upr.UndoProductRestoreTests.status

    def hidden_p2(self, setup=None):
        """A repo with P2 hidden and the fixture's assets link replaced by a real folder of links (one per file)."""
        repo = self.repo()
        change = repo.run(hide(P2))
        site = repo.wt / "storefront-mockup"
        (site / "assets").unlink()
        shutil.copytree(SITE_DIR / "assets", site / "assets", copy_function=os.symlink)
        (site / P2_IMAGE).unlink()
        if setup:
            setup(site)
        git(repo.wt, "add", "-A")
        git(repo.wt, "commit", "-q", "-m", "fixture: P2 image changed")
        return repo, change

    def restore_refused(self, repo, reason):
        before = repo.read(PRODUCTS)
        result = self.assertRejected(repo, "refused", ("product.restore", {"id": P2}))
        self.assertEqual(result["reason"], reason)
        self.assertEqual(repo.read(PRODUCTS), before)
        self.assertEqual(self.status(repo, P2), "hidden")

    def both_refused(self, setup, reason):
        repo, change = self.hidden_p2(setup)
        with self.subTest(path="product.restore"):
            self.restore_refused(repo, reason)
        with self.subTest(path=REVERT):
            self.refused(repo, change, reason)
            self.assertEqual(self.status(repo, P2), "hidden")

    def test_image_linked_to_another_product_photo_is_refused(self):
        self.both_refused(lambda site: os.symlink(site / OTHER_IMAGE, site / P2_IMAGE), LINKED)

    def test_dangling_link_is_refused_as_a_link(self):
        self.both_refused(lambda site: os.symlink(site / "assets/products/no-such.webp", site / P2_IMAGE), LINKED)

    def test_missing_image_keeps_the_missing_text_on_both_paths(self):
        self.both_refused(None, MISSING)

    def test_image_under_a_linked_folder_outside_the_site_is_refused(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside)

        def setup(site):  # a real P2 file, but assets/products is a link to a folder outside the site
            shutil.copytree(site / "assets/products", outside / "products", symlinks=True)
            shutil.copyfile(SITE_DIR / P2_IMAGE, outside / P2_IMAGE.removeprefix("assets/"))
            shutil.rmtree(site / "assets/products")
            os.symlink(outside / "products", site / "assets/products")

        self.both_refused(setup, OUTSIDE)

    def test_real_image_file_restores_on_both_paths(self):
        def setup(site):  # AVB-09: the post-apply migration check wants every listing image a real file, not a link
            products = site / "assets/products"
            for link in [e for e in products.iterdir() if e.is_symlink()]:
                target = link.resolve()
                link.unlink()
                shutil.copyfile(target, link)
            shutil.copyfile(SITE_DIR / P2_IMAGE, site / P2_IMAGE)

        for path in ("product.restore", REVERT):
            with self.subTest(path=path):
                repo, change = self.hidden_p2(setup)
                repo.run((path, {"id": P2} if path == "product.restore" else {"changeId": change["change_id"]}))
                self.assertEqual(self.status(repo, P2), "active")

    def test_harness_assets_link_still_restores_on_both_paths(self):
        for path in ("product.restore", REVERT):
            with self.subTest(path=path):
                repo = self.repo()  # storefront-mockup/assets is the editor harness link to the checkout's assets
                change = repo.run(hide(P2))
                repo.run((path, {"id": P2} if path == "product.restore" else {"changeId": change["change_id"]}))
                self.assertEqual(self.status(repo, P2), "active")


class NonStringImageTests(unittest.TestCase):
    def setUp(self):
        self.content = load_and_validate()
        self.product = next(p for p in self.content.products if p["id"] == P2)
        self.product.update(status="hidden", image=None)

    def test_product_restore_with_a_non_string_image_is_refused_as_missing(self):
        for image in (None, 7, ["assets/products/x.webp"]):
            with self.subTest(image=image):
                self.product["image"] = image
                ctx = types.SimpleNamespace(site_dir=SITE_DIR, warnings=[])
                result = _product_restore(self.content, {"id": P2}, ctx)
                self.assertEqual(result, Refused(f"{P2} cannot be restored: image file {image} is missing"))
                self.assertEqual(self.product["status"], "hidden")

    def test_revert_with_a_non_string_stored_image_is_refused_as_missing(self):
        for image in (None, 7):
            with self.subTest(image=image):
                after = dict(self.product)
                before = {**after, "status": "active", "image": image}
                record = {"collection": "products", "key": P2, "before": before, "after": after}
                with tempfile.TemporaryDirectory() as state:
                    ctx = types.SimpleNamespace(change=lambda _id: {"state": "applied", "records": [record]},
                                                state_dir=state, site_dir=SITE_DIR, now=None)
                    result = _revert(self.content, {"changeId": "chg-x"}, ctx)
                self.assertEqual(result, Refused(f"{P2} cannot be restored: image file {image} is missing"))
                self.assertEqual(self.product["status"], "hidden")


if __name__ == "__main__":
    unittest.main()
