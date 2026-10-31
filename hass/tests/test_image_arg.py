"""RF1230-9 (H02): the image argument kind refuses a link or a file whose resolved path leaves the site folder."""

import os, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass.content_model import SITE_DIR
from hass.ops import Arg, Op, check_args

OP = Op("t.op", {"image": Arg("image")}, lambda *a: None)
VALUE = "assets/products/x.webp"
LINK = ["t.op.image: image file must not be a link"]
OUTSIDE = ["t.op.image: image file is outside the site folder"]
MISSING = ["t.op.image: image file does not exist"]


class ImageArgTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.site = Path(tmp.name) / "site"
        self.products = self.site / "assets" / "products"
        self.products.mkdir(parents=True)
        self.outside = Path(tmp.name) / "outside"
        self.outside.mkdir()
        (self.outside / "x.webp").write_bytes(b"private")

    def check(self, value=VALUE):
        return check_args(OP, {"image": value}, {}, self.site)

    def test_regular_file_inside_passes(self):
        (self.products / "x.webp").write_bytes(b"img")
        self.assertEqual(self.check(), ([], []))
        self.assertEqual(check_args(OP, {"image": VALUE}, {}, str(self.site)), ([], []))

    def test_link_to_file_in_same_folder_refused(self):
        (self.products / "real.webp").write_bytes(b"img")
        os.symlink("real.webp", self.products / "x.webp")
        self.assertEqual(self.check(), (LINK, []))

    def test_link_to_file_outside_site_refused(self):
        os.symlink(self.outside / "x.webp", self.products / "x.webp")
        self.assertEqual(self.check(), (LINK, []))

    def test_dangling_link_is_a_link_not_missing(self):
        os.symlink(self.outside / "gone.webp", self.products / "x.webp")
        self.assertEqual(self.check(), (LINK, []))

    def test_link_chain_ending_inside_still_refused(self):
        (self.products / "real.webp").write_bytes(b"img")
        os.symlink("real.webp", self.products / "mid.webp")
        os.symlink("mid.webp", self.products / "x.webp")
        self.assertEqual(self.check(), (LINK, []))

    def test_linked_products_folder_out_of_site_refused(self):
        self.products.rmdir()
        os.symlink(self.outside, self.products)
        self.assertEqual(self.check(), (OUTSIDE, []))

    def test_linked_assets_folder_out_of_site_refused(self):
        self.products.rmdir()
        (self.site / "assets").rmdir()
        (self.outside / "products").mkdir()
        (self.outside / "products" / "x.webp").write_bytes(b"private")
        os.symlink(self.outside, self.site / "assets")
        self.assertEqual(self.check(), (OUTSIDE, []))

    def test_assets_linked_to_repo_assets_allowed_other_links_refused(self):
        """Operator amendment: only <site>/assets resolving to this checkout's tracked assets (the editor harness)."""
        real = next(p for p in sorted((SITE_DIR / "assets" / "products").iterdir()) if p.suffix == ".webp")
        value = f"assets/products/{real.name}"
        self.products.rmdir()
        os.symlink(real.parent, self.products)  # a link at assets/products, not the assets dir: refused
        self.assertEqual(self.check(value), (OUTSIDE, []))
        self.products.unlink()
        (self.site / "assets").rmdir()
        os.symlink(SITE_DIR / "assets", self.site.parent / "hop")
        os.symlink(self.site.parent / "hop", self.site / "assets")  # resolved before comparing, so a chain is allowed
        self.assertEqual(self.check(value), ([], []))
        self.assertEqual(self.check(), (MISSING, []))

    def test_linked_products_folder_inside_site_allowed(self):
        self.products.rmdir()
        (self.site / "img").mkdir()
        (self.site / "img" / "x.webp").write_bytes(b"img")
        os.symlink(self.site / "img", self.products)
        self.assertEqual(self.check(), ([], []))

    def test_site_dir_given_through_a_link_still_allowed(self):
        (self.products / "x.webp").write_bytes(b"img")
        alias = self.site.parent / "alias"
        os.symlink(self.site, alias)
        self.assertEqual(check_args(OP, {"image": VALUE}, {}, alias), ([], []))

    def test_missing_file_and_folder_named_like_file(self):
        self.assertEqual(self.check(), (MISSING, []))
        (self.products / "x.webp").mkdir()
        self.assertEqual(self.check(), (MISSING, []))

    def test_pattern_failures_unchanged_and_touch_no_filesystem(self):
        def boom(*a, **k):
            raise AssertionError("filesystem touched")
        with mock.patch.object(Path, "is_symlink", boom), mock.patch.object(Path, "is_file", boom), \
                mock.patch.object(Path, "resolve", boom):
            for value in ("assets/products/../x.webp", "assets/other/x.webp", "/etc/x.webp",
                          "assets/products/sub/x.webp", "assets/products/x.gif"):
                with self.subTest(value=value):
                    self.assertEqual(self.check(value), (["t.op.image: must be assets/products/<file>"], []))

    def test_non_string_unchanged(self):
        for value in (None, 1, ["assets/products/x.webp"], {"path": VALUE}):
            with self.subTest(value=value):
                self.assertEqual(self.check(value), (["t.op.image: must be a string (image)"], []))


if __name__ == "__main__":
    unittest.main()
