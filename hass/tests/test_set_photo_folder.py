"""RF1740-7: product.set_photo refuses a symlinked or non-directory site assets/ or assets/products/ folder.

Temp site and media dirs only; the op is called directly with an OpContext. No live service, no network.
"""

import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from hass import media
from hass.ops import OpContext, Refused, photos

FIXTURE = Path(__file__).parent / "fixtures" / "media" / "pixel.jpg"
PID, ALT = "photo-product-001", "Ripe avocados in a wooden crate"
REPLY = "the site photo folder is unusable"


class SetPhotoFolderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.site, self.other = self.tmp / "site", self.tmp / "other"
        self.site.mkdir()
        self.other.mkdir()
        self.sha = media.store_original(self.tmp / "media", FIXTURE.read_bytes(),
                                        received_at="2026-11-02T18:00:00+00:00", source="fixture")["sha256"]
        self.name = f"photo-{self.sha[:16]}.jpg"
        self.content = SimpleNamespace(products=[{"id": PID, "status": "active", "image": "assets/products/old.webp"}])
        self.before = copy.deepcopy(self.content.products)

    def run_op(self):
        ctx = OpContext(now=datetime.now(timezone.utc), site_dir=self.site, settings={"mediaRoot": str(self.tmp / "media")})
        args = {"id": PID, "photo": self.sha, "imageAlt": ALT}
        return ctx, photos._set_photo(self.content, args, ctx)

    def assert_refused(self):
        ctx, out = self.run_op()
        self.assertEqual((type(out), getattr(out, "reason", None)), (Refused, REPLY))
        self.assertEqual((ctx.assets, self.content.products), ({}, self.before))
        for secret in (str(self.tmp), self.sha[:16], self.name, "other"):
            self.assertNotIn(secret, out.reason)

    def test_normal_folders_set_the_photo(self):
        (self.site / "assets" / "products").mkdir(parents=True)
        ctx, out = self.run_op()
        self.assertEqual(len(out), 1, out)
        self.assertEqual(self.content.products[0]["image"], f"assets/products/{self.name}")
        self.assertEqual(list(ctx.assets), [f"assets/products/{self.name}"])

    def test_missing_folders_queue_the_asset(self):
        for make in (lambda: None, lambda: (self.site / "assets").mkdir()):
            with self.subTest(assets_exists=(self.site / "assets").exists()):
                make()
                ctx, out = self.run_op()
                self.assertEqual(len(out), 1, out)
                self.assertEqual(list(ctx.assets), [f"assets/products/{self.name}"])
                self.content.products[0]["image"] = "assets/products/old.webp"

    def test_products_symlink_with_same_named_file_is_refused(self):
        (self.site / "assets").mkdir()
        (self.other / self.name).write_bytes(Path(media.web_copy(self.tmp / "media", self.sha)["path"]).read_bytes())
        (self.site / "assets" / "products").symlink_to(self.other, target_is_directory=True)
        self.assert_refused()

    def test_products_symlink_to_empty_dir_is_refused(self):
        (self.site / "assets").mkdir()
        (self.site / "assets" / "products").symlink_to(self.other, target_is_directory=True)
        self.assert_refused()

    def test_assets_symlink_is_refused(self):
        (self.other / "products").mkdir()
        (self.site / "assets").symlink_to(self.other, target_is_directory=True)
        self.assert_refused()

    def test_products_regular_file_is_refused(self):
        (self.site / "assets").mkdir()
        (self.site / "assets" / "products").write_text("not a folder")
        self.assert_refused()

    def test_assets_regular_file_is_refused(self):
        (self.site / "assets").write_text("not a folder")
        self.assert_refused()

    def test_dangling_symlink_is_refused(self):
        (self.site / "assets").mkdir()
        (self.site / "assets" / "products").symlink_to(self.tmp / "nowhere")
        self.assert_refused()


if __name__ == "__main__":
    unittest.main()
