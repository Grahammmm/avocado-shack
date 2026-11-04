"""AV1422-01: a home-page photo set with ``store.set_home_image`` (``store.homeImage``) is copied by
``sitegen.py --publish``, so the published home page does not point at a missing file. Without a home photo the
published file set is unchanged. The fixture is a temp copy of the site plus a generated 1x1 photo (no real photo).
Run: python3 -B -m unittest hass.tests.test_publish_home_image -v
"""

import copy
import errno
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from hass import sitegen
from hass.content_model import REPO_ROOT, load_content
from hass.tests.test_publish import SITE_LINK

PHOTO = "assets/products/photo-0123456789abcdef.jpg"
PIXEL = (REPO_ROOT / "hass" / "tests" / "fixtures" / "media" / "pixel.jpg").read_bytes()
HERO = re.compile(r'<img class="hero-image" src="([^"]+)"')


class HomeImagePublish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls._tmp.name) / "repo"
        shutil.copytree(REPO_ROOT / "storefront-mockup", cls.repo / "storefront-mockup")
        shutil.copytree(REPO_ROOT / "hass" / "templates", cls.repo / "hass" / "templates")
        cls.photo = cls.repo / "storefront-mockup" / PHOTO
        cls.base = load_content()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.photo.write_bytes(PIXEL)
        self.addCleanup(lambda: self.photo.unlink(missing_ok=True))

    def content(self, home=True, product_image=False):
        c = copy.deepcopy(self.base)
        if home:
            c.store["homeImage"] = {"image": PHOTO, "imageAlt": "Crates of ripe avocados by the front door"}
        if product_image:
            c.active_products()[0]["image"] = PHOTO
        return c

    def test_home_photo_is_published_and_the_hero_resolves(self):
        files = sitegen.publish_files(self.content(), self.repo)
        self.assertEqual(files[PHOTO], PIXEL)
        page = files["index.html"].decode("utf-8")
        self.assertEqual(HERO.findall(page), [PHOTO])
        refs = [r for r in SITE_LINK.findall(page) if not re.match(r"[a-z]+:", r)]
        targets = {r.split("#")[0].split("?")[0].lstrip("/").removeprefix("./") for r in refs}
        targets = {{"": "index.html", "hike": "hike/index.html"}.get(t, t) for t in targets}
        self.assertIn(PHOTO, targets)
        self.assertEqual(sorted(targets - set(files)), [])

    def test_published_home_photo_has_no_exif(self):
        data = sitegen.publish_files(self.content(), self.repo)[PHOTO]
        self.assertNotIn(b"Exif\x00\x00", data)

    def test_no_home_photo_publishes_exactly_the_old_file_set(self):
        files = sitegen.publish_files(self.content(home=False), self.repo)
        expected = set(sitegen.PUBLISH_GENERATED) | set(sitegen.PUBLISH_PAGES) | {"community.json"} | set(sitegen.PUBLISH_STATIC)
        expected |= set(sitegen.PUBLISH_ASSETS) | {p["image"] for p in self.base.active_products()}
        self.assertEqual(sorted(files), sorted(expected))
        self.assertNotIn(PHOTO, files)

    def test_photo_shared_with_a_product_is_copied_once_without_error(self):
        without = sitegen.publish_files(self.content(home=False, product_image=True), self.repo)
        with_home = sitegen.publish_files(self.content(product_image=True), self.repo)
        self.assertEqual(sorted(with_home), sorted(without))
        self.assertEqual(with_home[PHOTO], PIXEL)

    def test_missing_home_photo_is_refused_and_no_folder_is_created(self):
        self.photo.unlink()
        out = Path(self._tmp.name) / "out-missing"
        with self.assertRaises(OSError) as ctx:
            sitegen.publish(self.content(), self.repo, out)
        self.assertEqual(ctx.exception.errno, errno.ENOENT)
        self.assertIn(PHOTO, str(ctx.exception))
        self.assertFalse(out.exists())

    def test_symlinked_home_photo_is_refused_and_no_folder_is_created(self):
        target = Path(self._tmp.name) / "elsewhere.jpg"
        target.write_bytes(PIXEL)
        self.photo.unlink()
        os.symlink(target, self.photo)
        out = Path(self._tmp.name) / "out-link"
        with self.assertRaises(OSError) as ctx:
            sitegen.publish(self.content(), self.repo, out)
        self.assertIn(PHOTO, str(ctx.exception))
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
