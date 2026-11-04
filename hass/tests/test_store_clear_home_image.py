"""AV1422-12 (H13): ``store.clear_home_image`` puts the shop's own photo back on the home page (hass/ops/home.py).

Same throwaway-repo fixture as test_store_home_image (PhotoRepo). Capture tests need PLAYWRIGHT_MODULE.
Run: python3 -m unittest hass.tests.test_store_clear_home_image -v
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from hass import preview
from hass.content_model import REPO_ROOT
from hass.tests.test_editor import git
from hass.tests.test_set_photo import _req
from hass.tests.test_store_home_image import ALT, DEFAULT_IMG, INDEX, REVERT, HomeImageTestCase, _home

CLEAR, STORY = "store.clear_home_image", "store.set_story"
NEW_STORY = "Michael stocks the shelves with fruit from growers he knows by name."
REFUSAL = "the home page already shows the shop’s own photo"


class ClearHomeImageTests(HomeImageTestCase):
    def photo_file(self):
        return self.repo.wt / "storefront-mockup" / self.site_path(self.jpg)

    def test_clear_removes_the_photo_and_the_page_is_byte_identical_to_the_no_photo_page(self):
        original = self.repo.read(INDEX)
        before = self.store_record()
        self.repo.run(_home(self.jpg))
        self.assertNotIn(DEFAULT_IMG, self.page())
        self.repo.run((CLEAR, {}))
        self.assertNotIn("homeImage", self.store_record())
        self.assertEqual(self.store_record(), before)
        self.assertEqual(self.repo.read(INDEX), original)
        self.assertIn(DEFAULT_IMG, self.page())
        self.assertTrue(self.photo_file().is_file())  # the committed file is kept
        self.assertEqual(self.repo.status(), "")

    def test_refused_when_no_home_photo_and_nothing_is_written(self):
        self.assertEqual(self.rejected("refused", (CLEAR, {}))["reason"], REFUSAL)

    def test_refused_again_after_a_clear(self):
        self.repo.run(_home(self.jpg))
        self.repo.run((CLEAR, {}))
        self.assertEqual(self.rejected("refused", (CLEAR, {}))["reason"], REFUSAL)

    def test_works_after_a_later_store_change(self):
        self.repo.run(_home(self.jpg))
        self.repo.run((STORY, {"text": NEW_STORY}))
        self.repo.run((CLEAR, {}))
        store = self.store_record()
        self.assertNotIn("homeImage", store)
        self.assertEqual(store["story"], NEW_STORY)
        self.assertIn(DEFAULT_IMG, self.page())

    def test_undo_of_the_clear_restores_the_owners_photo_and_the_file_is_still_there(self):
        self.repo.run(_home(self.jpg))
        photo = self.store_record()["homeImage"]
        page = self.repo.read(INDEX)
        clear = self.repo.run((CLEAR, {}))
        self.repo.run((REVERT, {"changeId": clear["change_id"]}))
        self.assertEqual(self.store_record()["homeImage"], photo)
        self.assertEqual(photo, {"image": self.site_path(self.jpg), "imageAlt": ALT})
        self.assertEqual(self.repo.read(INDEX), page)
        self.assertTrue(self.photo_file().is_file())
        self.assertEqual(self.repo.status(), "")

    def test_an_argument_is_invalid_and_nothing_is_written(self):
        self.repo.run(_home(self.jpg))
        head, store = self.repo.head(), self.store_record()
        result = self.repo.prepare(_req((CLEAR, {"photo": self.jpg})))
        self.assertEqual(result["result"], "invalid", result)
        self.assertEqual((self.repo.head(), self.repo.status(), self.store_record()), (head, "", store))

    def test_preview_target_expects_the_default_hero_only_after_a_clear(self):
        self.repo.run(_home(self.jpg))
        cleared = preview.target_for(self.repo.run((CLEAR, {}))["records"][0])
        self.assertIs(cleared["homeImageCleared"], True)
        self.assertIsNone(cleared["homeImage"])
        story = preview.target_for(self.repo.run((STORY, {"text": NEW_STORY}))["records"][0])
        self.assertNotIn("homeImageCleared", story)
        self.assertNotIn("homeImageCleared", preview.target_for(self.repo.run(_home(self.jpg))["records"][0]))


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class ClearHomeImageCaptureTests(HomeImageTestCase):
    def setUp(self):  # as test_store_home_image.HomeImageCaptureTests: the full site in the throwaway repo
        super().setUp()
        wt = self.repo.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-s", "-m", "full site")
        self.repo.run(_home(self.jpg))
        self.photo_index = self.repo.read(INDEX)
        holder = tempfile.TemporaryDirectory(prefix="hass-av1422-12-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"
        self.target = preview.target_for(self.repo.run((CLEAR, {}))["records"][0])

    def capture(self, files=None):
        return preview.Previewer(self.repo.wt, viewports=("phone",)).capture(files or {}, self.target, self.out)

    def test_default_hero_is_shown_after_the_clear(self):
        result = self.capture()
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        self.assertIs(result["checks"]["homeImageCleared"], True)

    def test_page_still_showing_the_photo_fails(self):
        result = self.capture({INDEX: self.photo_index})
        self.assertIs(result["checks"]["homeImageCleared"], False)
        self.assertEqual((result["ok"], result["error"]), (False, "check failed: homeImageCleared"))


if __name__ == "__main__":
    unittest.main()
