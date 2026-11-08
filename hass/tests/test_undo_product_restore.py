"""AVB-06 tests: undoing a change that makes a product active again re-checks its maker and image like product.restore.

Real-ops cases run on a throwaway CatalogRepo (see test_catalog_ops); the fixture site's ``assets`` folder is turned into
a committed folder of links so one image can be removed without touching the real checkout.
Run: python3 -m unittest hass.tests.test_undo_product_restore -v
"""

import copy
import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path

from hass.content_model import REPO_ROOT, SITE_DIR, load_and_validate
from hass.ops import Refused, Touched
from hass.ops.history import _revert
from hass.tests.test_catalog_ops import CatalogTestCase
from hass.tests.test_conversation import _ops
from hass.tests.test_editor import git
from hass.tests.test_undo import H06TestCase

REVERT, MAKER = "history.revert", "AG Berries"
P1, P2 = "photo-product-057", "photo-product-001"  # P1 is its maker's only product; P2 has no maker
MAKER_REASON = f"maker {MAKER} is hidden; restore the maker first"
P2_IMAGE = "assets/products/photo-product-001.webp"
PRODUCTS = "hass/content/products.json"


def hide(pid):
    return ("product.hide", {"id": pid})


class UndoProductRestoreTests(CatalogTestCase):
    def refused(self, repo, change, reason):
        before = repo.read(PRODUCTS)
        result = self.assertRejected(repo, "refused", (REVERT, {"changeId": change["change_id"]}))
        self.assertEqual(result["reason"], reason)
        self.assertEqual(repo.read(PRODUCTS), before)

    def status(self, repo, pid):
        return next(p for p in repo.products() if p["id"] == pid)["status"]

    def test_hidden_maker_refuses_undo_of_product_hide(self):
        repo = self.repo()
        change = repo.run(hide(P1))
        repo.run(("maker.hide", {"key": MAKER}))
        self.refused(repo, change, MAKER_REASON)
        self.assertEqual(self.status(repo, P1), "hidden")

    def test_missing_image_refuses_undo_of_product_hide(self):
        repo = self.repo()
        change = repo.run(hide(P2))
        site = repo.wt / "storefront-mockup"
        (site / "assets").unlink()  # the fixture's link to the real assets: replace by links to each file
        shutil.copytree(SITE_DIR / "assets", site / "assets", copy_function=os.symlink)
        (site / P2_IMAGE).unlink()
        git(repo.wt, "add", "-A")
        git(repo.wt, "commit", "-q", "-m", "fixture: image file removed")
        self.refused(repo, change, f"{P2} cannot be restored: image file {P2_IMAGE} is missing")
        self.assertEqual(self.status(repo, P2), "hidden")

    def test_undo_restores_when_maker_and_image_are_fine(self):
        repo = self.repo()
        change = repo.run(hide(P1))
        repo.run((REVERT, {"changeId": change["change_id"]}))
        self.assertEqual(self.status(repo, P1), "active")

    def test_one_failing_product_refuses_the_whole_undo(self):
        for first, second in ((P1, P2), (P2, P1)):  # the failing product both last and first in the change
            with self.subTest(first=first):
                repo = self.repo()
                change = repo.run(hide(first), hide(second))
                repo.run(("maker.hide", {"key": MAKER}))
                self.refused(repo, change, MAKER_REASON)
                self.assertEqual((self.status(repo, P1), self.status(repo, P2)), ("hidden", "hidden"))

    def test_undo_of_an_edit_on_an_active_product_is_not_rechecked(self):
        # a hidden maker or a missing image on an already active product is not this undo's business
        content = load_and_validate()
        content.makers[MAKER]["hidden"] = True
        before = next(copy.deepcopy(p) for p in content.products if p["id"] == P1)
        after = {**before, "description": "Edited."}
        next(p for p in content.products if p["id"] == P1).update(after)
        record = {"collection": "products", "key": P1, "before": before, "after": after}
        with tempfile.TemporaryDirectory() as empty_site:  # no image files at all
            ctx = types.SimpleNamespace(change=lambda _id: {"state": "applied", "records": [record]},
                                        state_dir=empty_site, site_dir=Path(empty_site), now=None)
            result = _revert(content, {"changeId": "chg-x"}, ctx)
        self.assertIsInstance(result, list)
        self.assertEqual(result, [Touched("products", P1, after, before)])
        self.assertNotIsInstance(result, Refused)


class ConversationUndoTests(H06TestCase):
    def test_undo_reply_carries_the_refusal_and_no_draft(self):
        self.interp.mapping.update({"hide": _ops(("product.hide", {"id": P1})),
                                    "maker": _ops(("maker.hide", {"key": MAKER}))})
        hidden = self.apply("hide")
        self.apply("maker")
        drafts, commits = len(self.drafts()), self.commits()
        self.assertEqual(self.say(f"undo {hidden['code']}"), "not-drafted")
        self.assertEqual(self.replies(), ["That one is hidden right now. Do you want me to bring it back first?"])
        self.assertEqual((len(self.drafts()), self.commits()), (drafts, commits))
        self.assertEqual(self.product(P1)["status"], "hidden")


if __name__ == "__main__":
    unittest.main()
