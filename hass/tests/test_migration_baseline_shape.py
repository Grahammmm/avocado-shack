"""RF0740-2: a misshaped migration-baseline.json is a named failure (exit 1), never a traceback.

Every case edits the baseline of a throwaway IsolatedRepo; the checkout is only read.
Run: python3 -B -m unittest hass.tests.test_migration_baseline_shape -v
"""

import contextlib
import io
import json
import subprocess
import sys
import unittest

from hass import migration_check
from hass.content_model import REPO_ROOT
from hass.tests.test_content import IsolatedRepo

BASELINE = REPO_ROOT / "hass" / "content" / "migration-baseline.json"
REPORT_KEYS = [
    "baseCommit", "baselineListings", "baselineListingsPreserved", "activeProducts", "hiddenProducts",
    "heldProducts", "baselineMakers", "makers", "baselineSourceLinks", "sourceLinksPreserved",
    "catalogListings", "heldExcluded", "realEvents", "routeIdeas", "generatedFiles", "identicalToPreMigration",
]


def _main(repo):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = migration_check.main(["--repo", str(repo)])
    return code, out.getvalue(), err.getvalue()


class MisshapedBaselineTests(unittest.TestCase):
    def _repo_with(self, mutate, whole=None):
        repo = IsolatedRepo()
        self.addCleanup(repo.cleanup)
        data = json.loads(BASELINE.read_text("utf-8"))
        mutate(data)  # edits in place; `whole` replaces the entire baseline instead
        data = data if whole is None else whole
        (repo.root / "hass" / "content" / "migration-baseline.json").write_text(json.dumps(data), "utf-8")
        return repo.root

    def assertNamed(self, mutate, line):
        code, out, err = _main(self._repo_with(mutate))
        self.assertEqual(code, 1, out + err)
        self.assertEqual(out, f"MIGRATION CHECK FAILED:\n  {line}\n")
        self.assertEqual(err, "")

    def test_top_level_list_is_named_without_traceback(self):
        root = self._repo_with(lambda d: None, whole=[])
        proc = subprocess.run([sys.executable, "-B", "hass/migration_check.py", "--repo", str(root)],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(proc.stdout, "MIGRATION CHECK FAILED:\n  baseline is not an object\n")
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.stderr, "")

    def test_missing_listings(self):
        self.assertNamed(lambda d: d.pop("listings"), "baseline listings is missing or not an object")

    def test_listings_count_bool_or_text(self):
        for bad in (True, "3", None):
            with self.subTest(count=bad):
                self.assertNamed(lambda d: d["listings"].update(count=bad),
                                 "baseline listings.count is missing or not a whole number")

    def test_listings_ids_number_or_empty(self):
        for bad in (5, ""):
            with self.subTest(id=bad):
                self.assertNamed(lambda d: d["listings"]["ids"].append(bad),
                                 "baseline listings.ids is not a list of ids")
        self.assertNamed(lambda d: d["listings"].update(ids="photo-product-001"),
                         "baseline listings.ids is not a list of ids")

    def test_sources_shapes(self):
        self.assertNamed(lambda d: d["sources"].update(makerUrls=["https://example.org"]),
                         "baseline sources.makerUrls is missing or not an object of text")
        self.assertNamed(lambda d: d["sources"].pop("heldSource"),
                         "baseline sources.heldSource is missing or not text")

    def test_held_site_hashes_and_base_commit(self):
        self.assertNamed(lambda d: d["held"].pop("ids"), "baseline held.ids is missing or not a list of text")
        self.assertNamed(lambda d: d["held"].update(reason=7), "baseline held.reason is missing or not text")
        self.assertNamed(lambda d: d.update(siteFileSha256=[]),
                         "baseline siteFileSha256 is missing or not an object of text")
        self.assertNamed(lambda d: d.update(baseCommit=None), "baseline baseCommit is missing or not text")

    def test_makers_keys_not_text(self):
        self.assertNamed(lambda d: d["makers"].update(keys=[1]), "baseline makers.keys is missing or not a list of text")
        self.assertNamed(lambda d: d.update(makers=[]), "baseline makers is missing or not an object")

    def test_two_problems_report_only_the_first_in_order(self):
        def two(d):
            d.pop("baseCommit")
            d["held"]["reason"] = None
        self.assertNamed(two, "baseline held.reason is missing or not text")

    def test_real_baseline_passes_with_full_report(self):
        self.assertIsNone(migration_check._baseline_problem(json.loads(BASELINE.read_text("utf-8"))))
        code, out, err = _main(REPO_ROOT)
        self.assertEqual(code, 0, out + err)
        lines = out.splitlines()
        self.assertEqual([ln.split(":", 1)[0] for ln in lines[:-1]], REPORT_KEYS)
        self.assertEqual(lines[-1], "migration check passed")
        self.assertIn("baselineListings: 170", lines)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
