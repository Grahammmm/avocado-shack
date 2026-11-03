"""FAV-06 (H13): one home-page hero image slot (``store.set_home_image``, hass/ops/home.py).

The photo is installed by ``photos.install`` exactly as ``product.set_photo`` (test_set_photo.PhotoRepo: a temp Git
repo with a real assets/products folder and a private media root). Capture tests run the real loopback preview and
Chromium; they are skipped when PLAYWRIGHT_MODULE is unset.
Run: python3 -m unittest hass.tests.test_store_home_image -v
"""

import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from hass import media, preview, sitegen
from hass.content_model import REPO_ROOT, load_content, validate_store
from hass.ops.photos import ALT_REPLY
from hass.tests.test_editor import git
from hass.tests.test_media_web import exif, jpeg
from hass.tests.test_set_photo import ASSETS, FIXTURES, PhotoRepo, _req, _settings

SET, REVERT, INDEX = "store.set_home_image", "history.revert", "storefront-mockup/index.html"
ALT = "Crates of ripe avocados by the front door"
DEFAULT_IMG = '<img class="hero-image" src="assets/store.jpg" alt="Produce and pantry shelves inside Avocado Shack in Morro Bay">'
STORE = load_content().store


def _home(sha, alt=ALT):
    return (SET, {"photo": sha, "imageAlt": alt})


class HomeImageTestCase(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.jpg = self.repo.store((FIXTURES / "pixel.jpg").read_bytes())

    def site_path(self, sha, ext="jpg"):
        return f"assets/products/photo-{sha[:16]}.{ext}"

    def store_record(self):
        return json.loads(self.repo.read("hass/content/store.json"))

    def page(self):
        return self.repo.read(INDEX).decode("utf-8")

    def rejected(self, result_name, *ops):
        head, drafts, store = self.repo.head(), self.repo.drafts(), self.store_record()
        result = self.repo.prepare(_req(*ops))
        self.assertEqual(result["result"], result_name, result)
        self.assertEqual((self.repo.head(), self.repo.drafts(), self.repo.status()), (head, drafts, ""))
        self.assertEqual(self.store_record(), store)
        return result


class HomeImageOpTests(HomeImageTestCase):
    def test_no_home_image_renders_todays_page_byte_for_byte(self):
        self.assertNotIn("homeImage", STORE)
        self.assertEqual(sitegen.main(["--check"]), 0)
        page = sitegen.render(load_content())[INDEX]
        self.assertEqual(page, (REPO_ROOT / INDEX).read_bytes())
        self.assertEqual(page.decode("utf-8").count('class="hero-image"'), 1)
        self.assertIn(DEFAULT_IMG, page.decode("utf-8"))

    def test_set_queues_one_metadata_free_copy_and_the_hero_points_at_it(self):
        original = jpeg(exif("II", 1))  # fake GPS in the original (test_media_web)
        self.assertIn(b"GPS", original)
        gps = self.repo.store(original)
        self.repo.run(_home(gps))
        path = self.site_path(gps)
        self.assertEqual(self.store_record()["homeImage"], {"image": path, "imageAlt": ALT})
        self.assertEqual([f for f in self.repo.committed() if f.startswith(ASSETS)], ["storefront-mockup/" + path])
        data = (self.repo.wt / "storefront-mockup" / path).read_bytes()
        self.assertEqual(data, Path(media.web_copy(self.repo.media, gps)["path"]).read_bytes())
        for gone in (b"Exif", b"GPS"):
            self.assertNotIn(gone, data)
        self.assertIn(f'<img class="hero-image" src="{path}" alt="{ALT}">', self.page())
        self.assertNotIn(DEFAULT_IMG, self.page())
        self.assertEqual(self.page().count('class="hero-image"'), 1)
        self.assertEqual(self.repo.status(), "")

    def test_undo_removes_the_image_and_keeps_the_committed_file(self):
        original, before = self.repo.read(INDEX), self.store_record()
        change = self.repo.run(_home(self.jpg))
        self.repo.run((REVERT, {"changeId": change["change_id"]}))
        self.assertNotIn("homeImage", self.store_record())
        self.assertEqual(self.store_record(), before)
        self.assertEqual(self.repo.read(INDEX), original)
        self.assertTrue((self.repo.wt / "storefront-mockup" / self.site_path(self.jpg)).is_file())
        self.assertEqual(self.repo.status(), "")

    def test_alt_photo_id_and_media_store_refusals_match_set_photo(self):
        result = self.rejected("needs-details", (SET, {"photo": self.jpg}))
        self.assertEqual(result["missing"], ["imageAlt"])
        cases = {"file-name alt": (_home(self.jpg, "IMG_1234.jpg"), ALT_REPLY),
                 "placeholder alt": (_home(self.jpg, "photo"), ALT_REPLY),
                 "unknown photo": (_home("0" * 64), media.REPLIES["not-found"]),
                 "not hex": (_home("not-a-photo"), "photo must be a stored photo id")}
        for name, (op, reason) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.rejected("refused", op)["reason"], reason)
        _settings(self.repo)
        self.assertEqual(self.rejected("refused", _home(self.jpg))["reason"], "photo store is not configured")
        self.assertFalse((self.repo.wt / "storefront-mockup" / self.site_path(self.jpg)).exists())

    def test_same_photo_and_alt_refused_new_alt_accepted(self):
        self.repo.run(_home(self.jpg))
        result = self.rejected("refused", _home(self.jpg))
        self.assertEqual(result["reason"], "the home page already shows that photo with that imageAlt")
        self.repo.run(_home(self.jpg, "Michael stacking avocados"))
        self.assertEqual(self.store_record()["homeImage"],
                         {"image": self.site_path(self.jpg), "imageAlt": "Michael stacking avocados"})
        self.assertNotIn(ASSETS + "photo-" + self.jpg[:16] + ".jpg", self.repo.committed())

    def test_quote_and_ampersand_alt_render_attribute_escaped(self):
        self.repo.run(_home(self.jpg, 'Crate of "Hass" avocados & lemons'))
        self.assertIn('alt="Crate of &quot;Hass&quot; avocados &amp; lemons">', self.page())


class ValidatorTests(unittest.TestCase):
    def problems(self, home):
        store = copy.deepcopy(STORE)
        store["homeImage"] = home
        problems = []
        validate_store(problems, store)
        return problems

    def test_home_image_rules(self):
        good = {"image": "assets/products/photo-0123456789abcdef.jpg", "imageAlt": ALT}
        self.assertEqual(self.problems(good), [])
        bad = ["x", {"image": good["image"]}, {**good, "extra": 1}, {**good, "imageAlt": "ab"},
               {**good, "imageAlt": "<b>Crate</b>"}, {**good, "image": "assets/store.jpg"},
               {**good, "image": "assets/products/photo-product-001.webp"},
               {**good, "image": "assets/products/photo-0123456789abcdef.svg"},
               {**good, "image": "https://example.com/photo-0123456789abcdef.jpg"}]
        for home in bad:
            with self.subTest(home=home):
                problems = self.problems(home)
                self.assertTrue(problems)
                self.assertTrue(all(p.startswith("store.homeImage") for p in problems), problems)


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class HomeImageCaptureTests(HomeImageTestCase):
    def setUp(self):  # as test_store_story.StoryCaptureTests: the full site in the throwaway repo
        super().setUp()
        wt = self.repo.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-s", "-m", "full site")
        self.old_index = self.repo.read(INDEX)
        holder = tempfile.TemporaryDirectory(prefix="hass-fav06-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"
        self.target = preview.target_for(self.repo.run(_home(self.jpg))["records"][0])

    def capture(self, files=None, viewports=("phone",)):
        return preview.Previewer(self.repo.wt, viewports=viewports).capture(files or {}, self.target, self.out)

    def test_home_image_is_shown_on_phone_and_desktop(self):
        self.assertEqual(self.target["homeImage"], self.site_path(self.jpg))
        result = self.capture(viewports=preview.VIEWPORTS)
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        for prefix in ("", "desktop:"):
            self.assertIs(result["checks"][prefix + "homeImageShown"], True)

    def test_old_page_with_new_target_fails(self):
        result = self.capture({INDEX: self.old_index})
        self.assertIs(result["checks"]["homeImageShown"], False)
        self.assertEqual((result["ok"], result["error"]), (False, "check failed: homeImageShown"))


if __name__ == "__main__":
    unittest.main()
