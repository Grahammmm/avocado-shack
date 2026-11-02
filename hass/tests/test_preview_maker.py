"""AV2022-10 tests (H06): a maker change's preview check finds a product card naming that maker and checks its
"Based in" line and maker name (``makerName``/``makerPlace``); a hidden maker must be on no card (``makerHidden``).

Target tests are pure. Capture tests run the real loopback preview server and Chromium against a CatalogRepo writer
worktree holding the full tracked site; they are skipped when PLAYWRIGHT_MODULE is unset (as in test_preview).
Run: python3 -m unittest hass.tests.test_preview_maker -v
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from hass import preview
from hass.content_model import REPO_ROOT
from hass.tests.test_catalog_ops import CatalogTestCase, _req
from hass.tests.test_editor import git

TEMPLETON = "Templeton, California"
CATALOG, PRODUCERS = "storefront-mockup/catalog-products.js", "storefront-mockup/producers.js"
QUOTED, ODD_NAME = 'Etto "Pasta"', 'Etto "Pasta" <b>Paso</b>'


def _maker_record(draft):
    (record,) = [r for r in draft["records"] if r["collection"] == "makers"]
    return record


class MakerTargetTests(CatalogTestCase):
    def test_edit_place_carries_key_name_new_place_not_hidden(self):
        draft = self.repo().prepare(_req(("maker.edit", {"key": "Etto", "place": TEMPLETON})))["draft"]
        self.assertEqual(preview.target_for(_maker_record(draft)),
                         {"kind": "maker", "key": "Etto", "name": "Etto", "place": TEMPLETON, "hidden": False})

    def test_hide_sets_hidden_and_restore_clears_it(self):
        repo = self.repo()
        (pid,) = [p["id"] for p in repo.products() if p.get("producerKey") == "AG Berries" and p["status"] == "active"]
        repo.run(("product.hide", {"id": pid}))
        hidden = preview.target_for(_maker_record(repo.run(("maker.hide", {"key": "AG Berries"}))))
        self.assertEqual((hidden["key"], hidden["hidden"]), ("AG Berries", True))
        self.assertEqual(preview.target_for(_maker_record(repo.run(("maker.restore", {"key": "AG Berries"}))))["hidden"],
                         False)

    def test_missing_after_gives_empty_strings(self):
        for after in (None, {}, {"name": None, "place": None}):
            with self.subTest(after=after):
                self.assertEqual(preview.target_for({"collection": "makers", "key": "m-1", "after": after}),
                                 {"kind": "maker", "key": "m-1", "name": "", "place": "", "hidden": False})


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class MakerCaptureTests(CatalogTestCase):
    def setUp(self):
        self.r = repo = self.repo()
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (repo.wt / rel).exists():
                (repo.wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, repo.wt / rel)
        git(repo.wt, "add", "-A")
        git(repo.wt, "commit", "-q", "-m", "full site")
        self.old = {rel: repo.read(rel) for rel in (CATALOG, PRODUCERS)}
        holder = tempfile.TemporaryDirectory(prefix="hass-av2022-10-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"

    def change(self, *ops):
        return preview.target_for(_maker_record(self.r.run(*ops)))

    def capture(self, target, files=None):
        return preview.Previewer(self.r.wt, viewports=("phone",)).capture(files or {}, target, self.out)

    def maker_checks(self, result):
        return {k: v for k, v in result["checks"].items() if k.startswith("maker")}

    def test_new_place_is_found_on_the_card(self):
        result = self.capture(self.change(("maker.edit", {"key": "Etto", "place": TEMPLETON})))
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        self.assertEqual(self.maker_checks(result), {"makerName": True, "makerPlace": True})

    def test_site_still_showing_old_place_is_not_verified(self):
        target = self.change(("maker.edit", {"key": "Etto", "place": TEMPLETON}))
        result = self.capture(target, {PRODUCERS: self.old[PRODUCERS]})
        self.assertEqual(self.maker_checks(result), {"makerName": True, "makerPlace": False})
        self.assertEqual((result["ok"], result["error"]), (False, "check failed: makerPlace"))

    def test_hidden_maker_is_on_no_card_and_a_stale_site_fails(self):
        (pid,) = [p["id"] for p in self.r.products() if p.get("producerKey") == "AG Berries" and p["status"] == "active"]
        self.r.run(("product.hide", {"id": pid}))
        target = self.change(("maker.hide", {"key": "AG Berries"}))
        result = self.capture(target)
        self.assertEqual((result["ok"], self.maker_checks(result)), (True, {"makerHidden": True}), result)
        stale = self.capture(target, self.old)
        self.assertEqual(self.maker_checks(stale), {"makerHidden": False})
        self.assertEqual((stale["ok"], stale["error"]), (False, "check failed: makerHidden"))

    def test_new_maker_without_products_adds_no_maker_check(self):
        target = self.change(("maker.add", {"key": "Test Farm", "name": "Test Farm", "place": TEMPLETON,
                                            "story": "A new farm.", "url": "https://example.com/farm"}))
        self.assertEqual((target["hidden"], target["place"]), (False, TEMPLETON))
        result = self.capture(target)
        self.assertEqual(self.maker_checks(result), {})
        self.assertEqual((result["ok"], result["checks"]["noPageErrors"]), (True, True), result)

    def test_name_with_quote_and_angle_brackets_is_matched_as_text(self):
        target = self.change(("maker.edit", {"key": "Etto", "name": QUOTED}))
        self.assertEqual(target["name"], QUOTED)
        self.assertMakerChecks(self.capture(target), {"makerName": True, "makerPlace": True})
        # The editor refuses '<' in a name, so a writer-side producers.js fixture carries it onto the cards.
        new = self.r.read(PRODUCERS)
        odd = new.replace(json.dumps(QUOTED).encode(), json.dumps(ODD_NAME).encode())
        self.assertNotEqual(odd, new)
        self.assertMakerChecks(self.capture({**target, "name": ODD_NAME}, {PRODUCERS: odd}),
                               {"makerName": True, "makerPlace": True})
        self.assertMakerChecks(self.capture({**target, "name": "Etto"}), {})  # old name on no card: exact text only

    def assertMakerChecks(self, result, expected):
        self.assertEqual((result["ok"], result["checks"].get("noPageErrors")), (True, True), result)
        self.assertEqual(self.maker_checks(result), expected)


if __name__ == "__main__":
    unittest.main()
