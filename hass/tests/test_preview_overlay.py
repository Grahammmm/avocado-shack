"""H06 preview overlay (RF1210-5): generated files never write through the assets link or any other link.

Fixture worktree via git; no node or Chromium needed. Run: python3 -B -m unittest hass.tests.test_preview_overlay -v
"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from hass import preview

LOGO = b"\x89PNG fixture logo"


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="overlay-test-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.wt = self.base / "wt"
        (self.wt / "storefront-mockup" / "assets").mkdir(parents=True)
        (self.wt / "storefront-mockup" / "index.html").write_bytes(b"<p>tracked</p>")
        (self.wt / "storefront-mockup" / "assets" / "logo.png").write_bytes(LOGO)
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "fixture"]):
            subprocess.run(["git", "-C", str(self.wt), *args], check=True, capture_output=True)
        self.before = tree(self.wt)
        self.tmp = self.base / "copy"
        self.tmp.mkdir()
        self.previewer = preview.Previewer(self.wt, env={})

    def assertWorktreeUnchanged(self):
        self.assertEqual(tree(self.wt), self.before)
        self.assertEqual(sorted(os.listdir(self.wt / "storefront-mockup" / "assets")), ["logo.png"])

    def assertRefused(self, files, reason):
        with self.assertRaises(ValueError) as caught:
            self.previewer._copy_site(self.tmp, files)
        self.assertIn(reason, str(caught.exception))
        self.assertWorktreeUnchanged()

    def test_assets_write_refused(self):
        self.assertRefused({"storefront-mockup/assets/x.png": b"evil"}, "inside the linked assets folder")
        self.assertEqual(list(self.wt.rglob("x.png")), [])
        self.assertEqual(list(self.base.rglob("x.png")), [])

    def test_spelling_variants_refused(self):
        for key in ("storefront-mockup/./assets/x.png", "storefront-mockup//assets/x.png",
                    "storefront-mockup/assets/sub/x.png"):
            with self.subTest(key=key), tempfile.TemporaryDirectory(dir=self.base) as raw:
                self.tmp = Path(raw)
                self.assertRefused({key: b"evil"}, "inside the linked assets folder")
                self.assertEqual(list(self.base.rglob("x.png")), [])

    def test_link_itself_refused(self):
        self.assertRefused({"storefront-mockup/assets": b"evil"}, "inside the linked assets folder")
        link = self.tmp / "storefront-mockup" / "assets"
        self.assertTrue(link.is_symlink())
        self.assertEqual((link / "logo.png").read_bytes(), LOGO)

    def test_outside_site_rule_unchanged(self):
        for key in ("storefront-mockup", "storefront-mockup/", "other/x.html", "/storefront-mockup/x.html",
                    "storefront-mockup/../x.html"):
            with self.subTest(key=key), tempfile.TemporaryDirectory(dir=self.base) as raw:
                self.tmp = Path(raw)
                self.assertRefused({key: b"x"}, "preview file outside the site")

    def test_planted_link_elsewhere_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.tmp / "storefront-mockup").mkdir()
        (self.tmp / "storefront-mockup" / "data").symlink_to(outside, target_is_directory=True)
        for key in ("storefront-mockup/data/p.json", "storefront-mockup/data/new/p.json"):
            with self.subTest(key=key), self.assertRaises(ValueError) as caught:
                preview._write_overlay(self.tmp, {key: b"{}"})
            self.assertIn("preview file resolves outside the copy", str(caught.exception))
        self.assertEqual(os.listdir(outside), [])

    def test_final_link_never_followed(self):
        site = self.tmp / "storefront-mockup"
        site.mkdir()
        (site / "real.html").write_bytes(b"real")
        (site / "page.html").symlink_to(site / "real.html")
        outside = self.base / "secret.txt"
        outside.write_bytes(b"secret")
        (site / "leak.html").symlink_to(outside)
        with self.assertRaises(ValueError):
            preview._write_overlay(self.tmp, {"storefront-mockup/leak.html": b"x"})
        with self.assertRaises(OSError):
            preview._write_overlay(self.tmp, {"storefront-mockup/page.html": b"x"})
        self.assertEqual((site / "real.html").read_bytes(), b"real")
        self.assertEqual(outside.read_bytes(), b"secret")

    def test_all_or_nothing(self):
        self.assertRefused({"storefront-mockup/good.html": b"good", "storefront-mockup/assets/x.png": b"evil"},
                           "inside the linked assets folder")
        self.assertFalse((self.tmp / "storefront-mockup" / "good.html").exists())
        with self.assertRaises(ValueError):
            preview._write_overlay(self.tmp, {"storefront-mockup/new/a.html": b"a", "other/b.html": b"b"})
        self.assertFalse((self.tmp / "storefront-mockup" / "new").exists())

    def test_normal_overlay_written_0600(self):
        files = {"storefront-mockup/index.html": b"<p>generated</p>",
                 "storefront-mockup/products/p1/index.html": b"<p>product</p>"}
        site = self.previewer._copy_site(self.tmp, files)
        self.assertEqual(site, self.tmp / "storefront-mockup")
        for rel, data in files.items():
            self.assertEqual((self.tmp / rel).read_bytes(), data)
            self.assertEqual(stat.S_IMODE((self.tmp / rel).stat().st_mode), 0o600)
        self.assertTrue((site / "assets").is_symlink())
        self.assertWorktreeUnchanged()

    def test_capture_turns_refusal_into_result(self):
        out = self.base / "shot.png"
        result = self.previewer.capture({"storefront-mockup/assets/x.png": b"evil"}, {"kind": "store"}, out)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["png"])
        self.assertTrue(result["error"].startswith("ValueError: preview file inside the linked assets folder"))
        self.assertIsNone(self.previewer.last_server)
        self.assertFalse(out.exists())
        self.assertWorktreeUnchanged()


if __name__ == "__main__":
    unittest.main()
