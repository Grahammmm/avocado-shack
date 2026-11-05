"""AV1222-02 (H06): a proposal preview of a product.set_photo draft shows a photo that is not stored in the site yet.

render_draft hands back the queued photo bytes; the Previewer lays them into its own assets folder (never through
the linked one), so the changed-image check passes before apply. Browser test skips without PLAYWRIGHT_MODULE.
"""

import os
import shutil
import unittest
from pathlib import Path

from hass import editor, preview
from hass.content_model import REPO_ROOT
from hass.tests.test_catalog_ops import _req
from hass.tests.test_editor import git
from hass.tests.test_set_photo import ASSETS, FIXTURES, PID, _photo, PhotoRepo


class NewPhotoPreview(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        wt = self.repo.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "full site")
        self.sha = self.repo.store((FIXTURES / "pixel.jpg").read_bytes())
        self.target_path = f"{ASSETS}photo-{self.sha[:16]}.jpg"
        draft = self.repo.prepare(_req(_photo(PID, self.sha)))
        self.assertEqual(draft["result"], "ok", draft)
        self.draft = draft["draft"]
        self.rendered = editor.render_draft(self.draft["change_id"], state=str(self.repo.state))
        self.assertEqual(self.rendered["result"], "ok", self.rendered)

    def test_render_draft_returns_the_new_photo_only(self):
        self.assertEqual(sorted(self.rendered["assets"]), [self.target_path])
        self.assertFalse((self.repo.wt / self.target_path).exists())  # a draft writes nothing

    def test_copy_holds_the_photo_and_the_worktree_stays_untouched(self):
        status = self.repo.status()
        previewer = preview.Previewer(self.repo.wt)
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            site = previewer._copy_site(Path(raw), self.rendered["files"], self.rendered["assets"])
            copied = site / "assets" / "products" / Path(self.target_path).name
            self.assertTrue(copied.is_file() and not copied.is_symlink())
            self.assertEqual(copied.read_bytes(), self.rendered["assets"][self.target_path])
            self.assertTrue((site / "assets" / "products" / "photo-product-002.webp").is_symlink())  # others stay linked
            self.assertTrue((site / "assets" / "logo.png").exists())
        self.assertFalse((self.repo.wt / self.target_path).exists())
        self.assertEqual(self.repo.status(), status)

    def test_bad_asset_keys_are_refused(self):
        previewer = preview.Previewer(self.repo.wt)
        out = self.repo.state / "screenshots" / "bad.png"
        for key in ("storefront-mockup/assets/x.png", "storefront-mockup/assets/products/../x.png",
                    "assets/products/x.jpg", "storefront-mockup/assets/products/sub/x.jpg"):
            with self.subTest(key=key):
                result = previewer.capture({}, {"kind": "product"}, out, assets={key: b"x"})
                self.assertFalse(result["ok"])
                self.assertIn("ValueError", result["error"])


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class NewPhotoBrowser(NewPhotoPreview):
    def test_changed_image_loads_in_the_isolated_preview(self):
        record = self.draft["records"][0]
        target = preview.target_for(record, store=self.rendered["store"])
        self.assertEqual(target["image"], f"assets/products/photo-{self.sha[:16]}.jpg")
        previewer = preview.Previewer(self.repo.wt, os.environ)
        out = self.repo.state / "screenshots" / "new-photo.png"
        result = previewer.capture(self.rendered["files"], target, out, assets=self.rendered["assets"])
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["checks"]["imageShown"] and result["checks"]["desktop:imageShown"], result)
        without = previewer.capture(self.rendered["files"], target, out)  # the old behaviour: image missing
        self.assertFalse(without["checks"]["imageShown"], without)
        self.assertFalse((self.repo.wt / self.target_path).exists())


if __name__ == "__main__":
    unittest.main()
