"""H10 part 3 tests: product.set_photo installs a stored photo's web copy; undo restores the old image.

WriterRepo harness (temp Git repo + linked writer worktree) whose assets/products is a real folder inside the worktree
(other product images linked), and a private media root outside the repo. No live service, no network.
"""

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from hass import editor, media
from hass.content_model import REPO_ROOT, SITE_DIR
from hass.ops import Arg, Op, Touched
from hass.tests.test_catalog_ops import CatalogRepo, _req
from hass.tests.test_editor import git
from hass.tests.test_media_web import chunk, png, tiff

FIXTURES = Path(__file__).parent / "fixtures" / "media"
PID, OTHER, ALT = "photo-product-001", "photo-product-002", "Ripe avocados in a wooden crate"
ASSETS = "storefront-mockup/assets/products/"


def _settings(repo, **settings):
    cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
    editor._write_json(repo.state / "config.json", {**cfg, "settings": settings})


class PhotoRepo(CatalogRepo):
    def __init__(self):
        super().__init__()
        assets = self.wt / "storefront-mockup" / "assets"
        assets.unlink()
        (assets / "products").mkdir(parents=True)
        for entry in [*(SITE_DIR / "assets").iterdir(), *(SITE_DIR / "assets" / "products").iterdir()]:
            if entry.name != "products":
                (assets / entry.relative_to(SITE_DIR / "assets")).symlink_to(entry)
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-q", "-s", "-m", "real assets/products folder")
        self.media = Path(self._tmp.name) / "media"
        _settings(self, mediaRoot=str(self.media))

    def store(self, data):
        return media.store_original(self.media, data, received_at="2026-11-02T18:00:00+00:00", source="fixture")["sha256"]

    def product(self, pid):
        return next(p for p in self.products() if p["id"] == pid)

    def committed(self):
        return git(self.wt, "show", "--name-only", "--format=", "HEAD").splitlines()


def _photo(pid, sha, alt=ALT):
    return ("product.set_photo", {"id": pid, "photo": sha, "imageAlt": alt})


class SetPhotoTestCase(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.jpg = self.repo.store((FIXTURES / "pixel.jpg").read_bytes())

    def target(self, sha, ext="jpg"):
        return f"{ASSETS}photo-{sha[:16]}.{ext}"

    def rejected(self, result_name, *ops):
        head, drafts = self.repo.head(), self.repo.drafts()
        result = self.repo.prepare(_req(*ops))
        self.assertEqual(result["result"], result_name, result)
        self.assertEqual((self.repo.head(), self.repo.drafts(), self.repo.status()), (head, drafts, ""))
        return result


class SetPhotoTests(SetPhotoTestCase):
    def test_photo_is_installed_and_committed_with_the_change(self):
        png = self.repo.store((FIXTURES / "pixel.png").read_bytes())
        for sha, ext, pid in ((self.jpg, "jpg", PID), (png, "png", OTHER)):
            with self.subTest(ext=ext):
                draft = self.repo.run(_photo(pid, sha))
                self.assertNotIn("writes", draft)
                self.assertEqual(self.repo.product(pid)["image"], f"assets/products/photo-{sha[:16]}.{ext}")
                self.assertEqual(self.repo.product(pid)["imageAlt"], ALT)
                self.assertIn(self.target(sha, ext), self.repo.committed())
                self.assertIn("hass/content/products.json", self.repo.committed())
                web = Path(media.web_copy(self.repo.media, sha)["path"]).read_bytes()
                self.assertEqual((self.repo.wt / self.target(sha, ext)).read_bytes(), web)
                self.assertEqual(self.repo.status(), "")
                self.assertEqual(editor._post_checks(self.repo.wt), [])

    def test_undo_restores_the_old_image_and_alt(self):
        before = self.repo.product(PID)
        draft = self.repo.run(_photo(PID, self.jpg))
        self.repo.run(("history.revert", {"changeId": draft["change_id"]}))
        self.assertEqual(self.repo.product(PID), before)
        self.assertEqual(self.repo.status(), "")
        self.assertTrue((self.repo.wt / self.target(self.jpg)).is_file())  # committed file stays, unreferenced

    def test_image_alt_is_required_and_limited(self):
        result = self.rejected("needs-details", ("product.set_photo", {"id": PID, "photo": self.jpg}))
        self.assertEqual(result["missing"], ["imageAlt"])
        self.assertIn("imageAlt", result["question"])
        result = self.rejected("invalid", _photo(PID, self.jpg, "a" * 201))
        self.assertTrue(any("imageAlt: longer than 200 characters" in p for p in result["problems"]), result)

    def test_named_refusals_write_nothing(self):
        cases = {"unknown photo": (_photo(PID, "0" * 64), media.REPLIES["not-found"]),
                 "not hex": (_photo(PID, "not-a-photo"), "photo must be a stored photo id"),
                 "short hex": (_photo(PID, self.jpg[:63]), "photo must be a stored photo id")}
        for name, (op, reason) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.rejected("refused", op)["reason"], reason)
        self.assertEqual(self.rejected("not-found", _photo("no-such-product", self.jpg))["key"], "no-such-product")
        _settings(self.repo)
        self.assertEqual(self.rejected("refused", _photo(PID, self.jpg))["reason"], "photo store is not configured")
        inside = REPO_ROOT / "hass" / "media-inside-repo"
        _settings(self.repo, mediaRoot=str(inside))
        self.assertEqual(self.rejected("refused", _photo(PID, self.jpg))["reason"],
                         "photo store is unusable: media root must lie outside the repository")
        self.assertFalse(inside.exists())

    def test_sideways_photo_is_refused(self):
        sideways = self.repo.store(png(chunk(b"eXIf", tiff("MM", 8))))
        self.assertEqual(self.rejected("refused", _photo(PID, sideways))["reason"], media.REPLIES["needs-rotation"])
        self.assertFalse((self.repo.wt / self.target(sideways, "png")).exists())

    def test_same_photo_reuses_the_file_and_a_different_file_is_refused(self):
        self.repo.run(_photo(PID, self.jpg))
        self.repo.run(_photo(OTHER, self.jpg, "Another crate"))
        self.assertNotIn(self.target(self.jpg), self.repo.committed())
        self.assertEqual(self.repo.product(OTHER)["image"], self.repo.product(PID)["image"])
        result = self.repo.prepare(_req(_photo("photo-product-003", self.jpg), _photo("photo-product-004", self.jpg)))
        self.assertEqual(result["result"], "ok", result)
        png = self.repo.store((FIXTURES / "pixel.png").read_bytes())
        clash = self.repo.wt / self.target(png, "png")
        clash.write_bytes(b"\x89PNG not the same photo")
        git(self.repo.wt, "add", "--", self.target(png, "png"))
        git(self.repo.wt, "commit", "-q", "-s", "-m", "clash")
        self.assertEqual(self.rejected("refused", _photo(PID, png))["reason"], "a different photo already uses that name")

    def test_asset_path_and_folder_are_checked_by_the_editor(self):
        def bad_op(content, args, ctx):
            ctx.assets["assets/products/../../escape.jpg"] = b"x"
            return [Touched("products", PID, None, None)]
        registry = {"test.bad_asset": Op("test.bad_asset", {"id": Arg("id")}, bad_op)}
        out = editor.prepare(_req(("test.bad_asset", {"id": PID})), state=str(self.repo.state), registry=registry)
        self.assertEqual(out["result"], "refused", out)
        self.assertIn("photo path is not assets/products/<file>", out["reason"])
        linked = CatalogRepo()  # assets is a link to this checkout's own folder
        self.addCleanup(linked.cleanup)
        _settings(linked, mediaRoot=str(self.repo.media))
        out = linked.prepare(_req(_photo(PID, self.jpg)))
        self.assertEqual((out["result"], out.get("reason")), ("refused", "the site photo folder is unusable"))
        self.assertEqual((self.repo.drafts(), linked.drafts(), linked.status()), ([], [], ""))


class FailedApplyTests(SetPhotoTestCase):
    def draft(self):
        result = self.repo.prepare(_req(_photo(PID, self.jpg)))
        self.assertEqual(result["result"], "ok", result)
        return result["draft"]

    def assertCleanFailure(self, change_id, head):
        self.assertEqual((self.repo.status(), self.repo.head()), ("", head))
        self.assertFalse((self.repo.wt / self.target(self.jpg)).exists())
        record = json.loads((self.repo.state / "changes" / f"{change_id}.json").read_text("utf-8"))
        self.assertEqual(record["state"], "failed")
        self.assertEqual(self.repo.product(PID)["image"], "assets/products/photo-product-001.webp")

    def test_post_check_failure_leaves_no_photo_file(self):
        draft, head = self.draft(), self.repo.head()
        with mock.patch.object(editor, "_post_checks", return_value=["injected failure"]):
            self.assertEqual(self.repo.apply(draft)["result"], "failed")
        self.assertCleanFailure(draft["change_id"], head)
        self.assertEqual(self.repo.prepare(_req(("product.edit", {"id": PID, "description": "Buttery."})))["result"],
                         "ok")

    def test_commit_failure_unstages_the_photo_file(self):
        draft, head = self.draft(), self.repo.head()
        hook = self.repo.main / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        os.chmod(hook, 0o700)
        self.assertEqual(self.repo.apply(draft)["result"], "failed")
        self.assertCleanFailure(draft["change_id"], head)

    def test_interrupted_apply_is_recovered_without_a_stray_file(self):
        draft, head = self.draft(), self.repo.head()

        class Crash(Exception):
            pass
        with mock.patch.object(editor, "_post_checks", side_effect=Crash):
            with self.assertRaises(Crash):
                self.repo.apply(draft)
        self.assertTrue((self.repo.wt / self.target(self.jpg)).is_file())  # journal left at base with the file
        self.assertEqual(editor.recover(state=str(self.repo.state))["recovered"],
                         [{"change_id": draft["change_id"], "state": "failed"}])
        self.assertCleanFailure(draft["change_id"], head)
