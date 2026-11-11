"""RF0740-3: a misshaped held-products.json or hiking-preview.json is a named failure (exit 1), never a traceback.

Every case edits a throwaway IsolatedRepo; the checkout is only read.
Run: python3 -B -m unittest hass.tests.test_migration_storefront_shape -v
"""

import json
import subprocess
import sys
import unittest

from hass import migration_check
from hass.content_model import REPO_ROOT
from hass.tests.test_content import IsolatedRepo
from hass.tests.test_migration_baseline_shape import REPORT_KEYS, _main

HELD = "storefront-mockup/held-products.json"
PREVIEW = "storefront-mockup/hiking-preview.json"


def _held_line(what):
    return f"{HELD} is misshaped: {what}"


def _preview_line(what):
    return f"{PREVIEW} is misshaped: {what}"


class MisshapedStorefrontTests(unittest.TestCase):
    def _repo(self, held=None, preview=None):
        """held/preview: a function editing the parsed file in place and returning the data to write."""
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        for rel, fn in ((HELD, held), (PREVIEW, preview)):
            if fn is not None:
                path = repo.root / rel
                path.write_text(json.dumps(fn(json.loads(path.read_text("utf-8")))), "utf-8")
        return repo

    def assertFails(self, root, *lines):
        code, out, err = _main(root)
        self.assertEqual(code, 1, out + err)
        report, _, failed = out.partition("MIGRATION CHECK FAILED:\n")
        self.assertEqual([ln.split(":", 1)[0] for ln in report.splitlines()], REPORT_KEYS)
        self.assertEqual(failed, "".join(f"  {ln}\n" for ln in lines))
        self.assertEqual(err, "")

    def assertPasses(self, root):
        code, out, err = _main(root)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.endswith("migration check passed\n"), out)
        self.assertEqual(err, "")

    def test_held_list_is_named_without_traceback(self):
        root = self._repo(held=lambda d: []).root
        proc = subprocess.run([sys.executable, "-B", "hass/migration_check.py", "--repo", str(root)],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertTrue(proc.stdout.endswith(f"MIGRATION CHECK FAILED:\n  {_held_line('not an object')}\n"))
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.stderr, "")

    def test_products_not_a_list_or_missing(self):
        for bad in ({"a": {"id": "x"}}, "photo-product-001", None):
            with self.subTest(products=bad):
                self.assertFails(self._repo(held=lambda d: {**d, "products": bad}).root,
                                 _held_line("products is not a list"))
        self.assertFails(self._repo(held=lambda d: {k: v for k, v in d.items() if k != "products"}).root,
                         _held_line("products is not a list"))

    def test_entry_without_text_id_is_numbered(self):
        for bad in ("x", {}, {"id": None}, {"id": 5}, {"id": ["a"]}):
            with self.subTest(entry=bad):
                self.assertFails(self._repo(held=lambda d: {**d, "products": d["products"][:1] + [bad]}).root,
                                 _held_line("products entry 2 has no text id"))

    def test_int_id_among_text_ids_is_named_not_a_sort_error(self):
        def edit(d):
            d["products"].append(dict(d["products"][0], id=5))
            return d
        self.assertFails(self._repo(held=edit).root, _held_line(f"products entry {len(self._held())+1} has no text id"))

    def test_misshaped_held_still_runs_per_held_id_checks(self):
        repo = self._repo(held=lambda d: [])
        hid = self._held()[0]["id"]

        def lose_reason(products):
            for p in products["products"] if isinstance(products, dict) else products:
                if p["id"] == hid:
                    p["hold"]["reason"] = "changed"
        repo.edit("products.json", lose_reason)
        self.assertFails(repo.root, _held_line("not an object"), f"held product {hid} lost its recorded reason/source")

    def test_preview_list_or_upcoming_not_object(self):
        self.assertFails(self._repo(preview=lambda d: []).root, _preview_line("not an object"))
        for bad in ("soon", None, ["preview-point-buchon"]):
            with self.subTest(upcoming=bad):
                self.assertFails(self._repo(preview=lambda d: {**d, "upcoming": bad}).root,
                                 _preview_line("upcoming is not an object"))

    def test_upcoming_without_id_or_absent_preview_passes(self):
        self.assertPasses(self._repo(preview=lambda d: {**d, "upcoming": {}}).root)
        self.assertPasses(self._repo(preview=lambda d: {k: v for k, v in d.items() if k != "upcoming"}).root)
        repo = self._repo()
        (repo.root / PREVIEW).unlink()
        self.assertPasses(repo.root)

    def test_both_misshaped_give_two_lines_and_full_report(self):
        root = self._repo(held=lambda d: {**d, "products": {}}, preview=lambda d: {**d, "upcoming": "soon"}).root
        self.assertFails(root, _held_line("products is not a list"), _preview_line("upcoming is not an object"))

    def test_upcoming_nontext_id_is_named_failure_not_traceback(self):
        canary = "SYNTHETIC CANARY"
        for bad in ([], {}, [canary], {"k": canary}, 42, 1.5, True, False):
            with self.subTest(id=bad):
                self.assertFails(self._repo(preview=lambda d: {**d, "upcoming": {"id": bad}}).root,
                                 _preview_line("upcoming id is not text"))
        root = self._repo(preview=lambda d: {**d, "upcoming": {"id": [canary]}}).root
        proc = subprocess.run([sys.executable, "-B", "hass/migration_check.py", "--repo", str(root)],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertTrue(proc.stdout.endswith(f"MIGRATION CHECK FAILED:\n  {_preview_line('upcoming id is not text')}\n"))
        self.assertEqual(proc.stderr, "")
        self.assertNotIn(canary, proc.stdout)

    def test_null_and_text_ids_keep_working(self):
        for ok in (None, "synthetic-sample", "", "caf\u00e9-\u2603"):
            with self.subTest(id=ok):
                self.assertPasses(self._repo(preview=lambda d: {**d, "upcoming": {"id": ok}}).root)
        self.assertEqual(migration_check._sample_ids({"upcoming": {"id": "x"}}), {"x"})
        self.assertEqual(migration_check._sample_ids({"upcoming": {"id": None}}), set())

    def test_bad_id_does_not_suppress_other_failures(self):
        root = self._repo(held=lambda d: {**d, "products": {}},
                          preview=lambda d: {**d, "upcoming": {"id": ["x"]}}).root
        self.assertFails(root, _held_line("products is not a list"), _preview_line("upcoming id is not text"))

    def test_real_files_pass(self):
        self.assertPasses(self._repo().root)
        self.assertPasses(REPO_ROOT)

    @staticmethod
    def _held():
        return json.loads((REPO_ROOT / HELD).read_text("utf-8"))["products"]


if __name__ == "__main__":
    unittest.main()
