"""AVB-09 (H01 assets): migration check proves listing images moved.

A damaged baseline file is covered by test_migration_baseline_shape (named failure, exit 1).

Every case runs on a throwaway copy of hass/content, hass/templates and storefront-mockup; the checkout is only read.
Run: python3 -m unittest hass.tests.test_migration_assets -v
"""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from hass import migration_check
from hass.content_model import REPO_ROOT

BASELINE = "hass/content/migration-baseline.json"
SITE = "storefront-mockup"


def _run(root):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = migration_check.main(["--repo", str(root)])
    return code, out.getvalue(), err.getvalue()


class MigrationAssetsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hass-avb09-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for rel in ("hass/content", "hass/templates", SITE):
            shutil.copytree(REPO_ROOT / rel, self.root / rel, symlinks=True)
        self.products = json.loads((self.root / "hass/content/products.json").read_text("utf-8"))
        self.base = json.loads((self.root / BASELINE).read_text("utf-8"))
        rows = self.products["products"] if isinstance(self.products, dict) else self.products
        self.by_id = {p["id"]: p for p in rows}
        uses = Counter(p["image"] for p in rows)
        # Baseline listings whose image no other product shares, so one edit touches one listing.
        self.solo = [i for i in self.base["listings"]["ids"] if uses[self.by_id[i]["image"]] == 1]

    def set_status(self, pid, status, **extra):
        self.by_id[pid]["status"] = status
        self.by_id[pid].update(extra)
        (self.root / "hass/content/products.json").write_text(
            json.dumps(self.products, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def image_path(self, pid):
        return self.root / SITE / self.by_id[pid]["image"]

    def image_failures(self):
        failures, report = migration_check.run_checks(self.root)
        return [f for f in failures if "lost their image" in f], failures, report

    def test_unmodified_copy_passes_with_all_images_present(self):
        code, out, err = _run(self.root)
        self.assertEqual((code, err), (0, ""), out)
        lines = out.splitlines()
        self.assertIn("baselineImagesPresent: 170/170", lines)
        keys = [line.split(":")[0] for line in lines]
        self.assertEqual(keys.index("baselineImagesPresent"), keys.index("baselineListingsPreserved") + 1)
        self.assertEqual(lines[-1], "migration check passed")

    def test_hidden_listing_with_deleted_image_fails_by_name(self):
        pid = self.solo[0]
        self.set_status(pid, "hidden")
        self.image_path(pid).unlink()
        images, _, report = self.image_failures()
        self.assertEqual(images, [f"1 baseline listings lost their image: {[pid]}"])
        self.assertEqual(report["baselineImagesPresent"], "169/170")
        code, out, err = _run(self.root)
        self.assertEqual((code, err), (1, ""), out)
        self.assertIn(f"  1 baseline listings lost their image: {[pid]}", out.splitlines())

    def test_hidden_listing_with_image_present_is_not_an_image_failure(self):
        self.set_status(self.solo[0], "hidden")
        images, failures, report = self.image_failures()
        self.assertEqual(images, [], failures)
        self.assertEqual(report["baselineImagesPresent"], "170/170")

    def test_symlink_and_folder_count_as_missing(self):
        linked, folder = self.solo[0], self.solo[1]
        target = self.image_path(self.solo[2])
        self.image_path(linked).unlink()
        self.image_path(linked).symlink_to(target)  # active: content_model's is_file() accepts a symlink
        self.set_status(folder, "hidden")  # a folder on an active product is already content-invalid
        self.image_path(folder).unlink()
        self.image_path(folder).mkdir()
        images, _, report = self.image_failures()
        self.assertEqual(len(images), 1, images)
        named = [i for i in self.base["listings"]["ids"] if i in (linked, folder)]
        self.assertEqual(images[0], f"2 baseline listings lost their image: {named}")
        self.assertEqual(report["baselineImagesPresent"], "168/170")

    def test_held_listing_is_excluded_from_the_image_check(self):
        pid = self.solo[0]
        hold = {"reason": self.base["held"]["reason"], "source": self.base["held"]["source"]}
        self.set_status(pid, "held", hold=hold)
        self.image_path(pid).unlink()
        images, failures, report = self.image_failures()
        self.assertEqual(images, [], failures)
        self.assertIn(f"baseline listings no longer active/hidden: {[pid]}", failures)
        self.assertEqual(report["baselineImagesPresent"], "169/169")


if __name__ == "__main__":
    unittest.main()
