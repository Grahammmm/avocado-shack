"""RF0330-12: repeated object keys in the three auxiliary migration JSON files are refused (exit 2).

Every case edits raw text of a throwaway IsolatedRepo; the checkout is only read.
Run: python3 -B -m unittest hass.tests.test_migration_aux_duplicates -v
"""

import contextlib
import io
import subprocess
import sys
import unittest

from hass import migration_check
from hass.content_model import REPO_ROOT
from hass.tests import test_content

PATHS = {
    "baseline": ("hass", "content", "migration-baseline.json"),
    "held": ("storefront-mockup", "held-products.json"),
    "preview": ("storefront-mockup", "hiking-preview.json"),
}
ERR = "migration_check: io error: ValueError\n"


def _main(root):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = migration_check.main(["--repo", str(root)])
    return code, out.getvalue(), err.getvalue()


class AuxDuplicateTests(unittest.TestCase):
    def _repo(self):
        repo = test_content.IsolatedRepo()
        self.addCleanup(repo.cleanup)
        return repo.root

    def _prefixed(self, which, members):
        root = self._repo()
        path = root.joinpath(*PATHS[which])
        text = path.read_text("utf-8")
        self.assertTrue(text.lstrip().startswith("{"))
        path.write_text("{" + members + "," + text.lstrip()[1:], "utf-8")
        return root

    def test_each_auxiliary_input_rejects_repeated_root_member(self):
        for which in PATHS:
            for members in ('"zz": 1, "zz": 2', '"zz": 1, "zz": 1'):
                with self.subTest(which=which, members=members):
                    self.assertEqual(_main(self._prefixed(which, members)), (2, "", ERR))

    def test_nested_unused_and_array_objects_are_not_exempt(self):
        for first in ("null", "false", "0", '""', "{}"):
            for which in PATHS:
                with self.subTest(which=which, first=first):
                    nested = f'"zz": {{"k": {first}, "k": 1}}'
                    self.assertEqual(_main(self._prefixed(which, nested)), (2, "", ERR))
                    arr = f'"zz": [{{"k": {first}, "k": {first}}}]'
                    self.assertEqual(_main(self._prefixed(which, arr)), (2, "", ERR))

    def test_decoded_key_identity_and_independent_objects(self):
        escaped = self._prefixed("held", '"zz": 1, "z\\u007a": 2')
        self.assertEqual(_main(escaped), (2, "", ERR))
        for members in ('"zz": {"k": 1}, "yy": {"k": 2}', '"zz": 1, "ZZ": 2', '"\\u00e9": 1, "e\\u0301": 2'):
            with self.subTest(members=members):
                code, out, err = _main(self._prefixed("baseline", members))
                self.assertNotEqual(code, 2, out + err)  # decoded fine; any outcome but the refusal

    def test_duplicate_cli_is_private_and_read_only(self):
        root = self._prefixed("held", '"canary-key-xyz": "canary-val-1", "canary-key-xyz": "canary-val-2"')
        files = sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())
        before = {p: (p.read_bytes(), p.stat().st_mode) for p in files}
        proc = subprocess.run([sys.executable, "-B", "hass/migration_check.py", "--repo", str(root)],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (2, "", ERR))
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mode) for p in files})

    def test_existing_failure_precedence_and_optional_preview(self):
        root = self._prefixed("held", '"zz": 1, "zz": 2')
        baseline = root.joinpath(*PATHS["baseline"])
        baseline.write_text("[]", "utf-8")  # misshaped baseline still wins before the held read
        code, out, _ = _main(root)
        self.assertEqual((code, out), (1, "MIGRATION CHECK FAILED:\n  baseline is not an object\n"))
        root = self._repo()
        root.joinpath(*PATHS["preview"]).unlink()  # optional preview may be absent
        self.assertEqual(_main(root)[0], 0)
        root.joinpath(*PATHS["held"]).write_text("{", "utf-8")  # ordinary malformed JSON: same class of exit
        self.assertEqual(_main(root), (2, "", "migration_check: io error: JSONDecodeError\n"))

    def test_valid_reports_and_site_bytes_are_unchanged(self):
        root = self._repo()
        before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and not p.is_symlink()}
        failures, report = migration_check.run_checks(root)
        self.assertEqual(failures, [])
        self.assertEqual(list(report)[0], "baseCommit")
        self.assertEqual(_main(root)[0], 0)
        self.assertEqual(before, {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and not p.is_symlink()})


if __name__ == "__main__":
    unittest.main()
