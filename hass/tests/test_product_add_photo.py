"""AV0022-02 tests: product.add takes a stored photo id (photo + imageAlt) instead of an image file.

Same PhotoRepo harness as test_set_photo (temp Git repo + linked writer worktree with a real assets/products folder and
a private media root outside the repo). No live service, no network.
"""

from pathlib import Path

from hass import editor, media
from hass.content_model import SITE_DIR
from hass.ops import photos
from hass.tests.test_catalog_ops import NEW
from hass.tests.test_editor import git
from hass.tests.test_set_photo import ALT, FIXTURES, PID, SetPhotoTestCase, _photo, _settings

NEW_ID = "photo-product-175"


def _add(**args):
    fields = {k: v for k, v in NEW.items() if k != "image"}
    return ("product.add", {**fields, **args})


class ProductAddPhotoTests(SetPhotoTestCase):
    def assertStoreUntouched(self):
        self.assertFalse((self.repo.media / "web").exists())

    def test_add_with_photo_installs_and_commits_the_web_copy(self):
        draft = self.repo.run(_add(photo=self.jpg, imageAlt=ALT))
        added = self.repo.products()[-1]
        self.assertEqual(added["id"], NEW_ID)
        self.assertEqual(list(added), ["id", "name", "brand", "category", "image", "description", "producerKey",
                                       "displayBrand", "status", "imageAlt"])
        self.assertEqual((added["image"], added["imageAlt"]), (f"assets/products/photo-{self.jpg[:16]}.jpg", ALT))
        self.assertNotIn("photo", added)
        self.assertIn(self.target(self.jpg), self.repo.committed())
        self.assertIn("hass/content/products.json", self.repo.committed())
        web = Path(media.web_copy(self.repo.media, self.jpg)["path"]).read_bytes()
        self.assertEqual((self.repo.wt / self.target(self.jpg)).read_bytes(), web)
        self.assertEqual(self.repo.status(), "")
        self.assertEqual(editor._post_checks(self.repo.wt), [])

        self.repo.run(("history.revert", {"changeId": draft["change_id"]}))
        self.assertEqual(self.repo.products()[-1]["status"], "hidden")  # undo of an addition hides it
        self.assertNotIn(NEW_ID, [p["id"] for p in self.repo.catalog()])
        self.assertEqual(self.repo.status(), "")
        self.assertTrue((self.repo.wt / self.target(self.jpg)).is_file())  # committed file stays, unreferenced

    def test_image_or_photo_rules(self):
        real = "assets/products/real-quince.webp"  # PhotoRepo links other images; image args need a real file
        (self.repo.wt / "storefront-mockup" / real).write_bytes((SITE_DIR / NEW["image"]).read_bytes())
        git(self.repo.wt, "add", "-A")
        git(self.repo.wt, "commit", "-q", "-s", "-m", "real image")
        cases = {"both": (_add(image=real, photo=self.jpg, imageAlt=ALT), "give image or photo, not both"),
                 "neither": (_add(), "product.add needs image or photo"),
                 "neither with alt": (_add(imageAlt=ALT), "product.add needs image or photo"),
                 "photo without alt": (_add(photo=self.jpg), "imageAlt is required with photo")}
        for name, (op, reason) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.rejected("refused", op)["reason"], reason)
        self.assertStoreUntouched()

    def test_bad_alt_is_refused_before_the_store_is_read(self):
        for alt in ("IMG_1234.jpg", "photo", self.jpg[:12], f"Crate {self.jpg[:12].upper()}"):
            with self.subTest(alt=alt):
                self.assertEqual(self.rejected("refused", _add(photo=self.jpg, imageAlt=alt))["reason"],
                                 photos.ALT_REPLY)
        self.assertStoreUntouched()

    def test_named_photo_refusals_write_nothing(self):
        cases = {"unknown photo": ("0" * 64, media.REPLIES["not-found"]),
                 "not hex": ("not-a-photo", "photo must be a stored photo id"),
                 "short hex": (self.jpg[:63], "photo must be a stored photo id")}
        for name, (sha, reason) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.rejected("refused", _add(photo=sha, imageAlt=ALT))["reason"], reason)
        _settings(self.repo)
        self.assertEqual(self.rejected("refused", _add(photo=self.jpg, imageAlt=ALT))["reason"],
                         "photo store is not configured")
        self.assertStoreUntouched()

    def test_twin_and_hidden_maker_are_refused_before_the_store_is_read(self):
        old = self.repo.product(PID)
        twin = ("product.add", {**_add(photo=self.jpg, imageAlt=ALT)[1], "name": old["name"], "brand": old["brand"]})
        self.assertIn(f"{PID} already has this name and brand", self.rejected("refused", twin)["reason"])
        self.repo.run(("maker.add", {"key": "Gone", "name": "Gone Farm", "place": "Nowhere", "story": "Closed.",
                                     "url": "https://example.com/"}))
        self.repo.run(("maker.hide", {"key": "Gone"}))
        hidden = _add(photo=self.jpg, imageAlt=ALT, producerKey="Gone")
        self.assertEqual(self.rejected("refused", hidden)["reason"], "maker Gone is hidden; restore the maker first")
        self.assertStoreUntouched()

    def test_same_bytes_are_reused_and_a_different_file_is_refused(self):
        self.repo.run(_photo(PID, self.jpg))
        self.repo.run(_add(photo=self.jpg, imageAlt="Another crate"))
        self.assertNotIn(self.target(self.jpg), self.repo.committed())
        self.assertEqual(self.repo.products()[-1]["image"], self.repo.product(PID)["image"])
        png = self.repo.store((FIXTURES / "pixel.png").read_bytes())
        clash = self.repo.wt / self.target(png, "png")
        clash.write_bytes(b"\x89PNG not the same photo")
        git(self.repo.wt, "add", "--", self.target(png, "png"))
        git(self.repo.wt, "commit", "-q", "-s", "-m", "clash")
        op = ("product.add", {**_add(photo=png, imageAlt=ALT)[1], "name": "Test medlar"})
        self.assertEqual(self.rejected("refused", op)["reason"], "a different photo already uses that name")
