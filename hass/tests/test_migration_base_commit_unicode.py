"""RF0600-13: a migration baseline baseCommit that cannot be UTF-8 encoded is a named failure, never a traceback.

An escaped lone surrogate is valid JSON ASCII but cannot be printed on strict UTF-8 stdout.
Every case edits the baseline of a throwaway IsolatedRepo; the checkout is only read.
Run: python3 -B -m unittest hass.tests.test_migration_base_commit_unicode -v
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from hass import migration_check
from hass.content_model import REPO_ROOT
from hass.tests import test_content as _tc  # module alias: keeps IsolatedRepo's sibling TestCases undiscovered here

BASELINE = REPO_ROOT / "hass" / "content" / "migration-baseline.json"
REFUSAL = "baseline baseCommit is not UTF-8 text"
FAILED = f"MIGRATION CHECK FAILED:\n  {REFUSAL}\n"
LONE = ["\\ud800", "\\udfff", "a\\ud800", "ab\\udc00cd", "\\ud800\\ud800", "\\udc00\\ud800", "x\\ud83d", "\\ud83dx\\ude00"]


class BaseCommitUnicodeTests(unittest.TestCase):
    def _repo(self, raw_value=None, mutate=None):
        """IsolatedRepo whose baseline text has baseCommit set to raw_value (JSON-escaped text, written verbatim)."""
        repo = _tc.IsolatedRepo()
        self.addCleanup(repo.cleanup)
        data = json.loads(BASELINE.read_text("utf-8"))
        if mutate:
            mutate(data)
        data["baseCommit"] = "@@RAW@@" if raw_value is not None else data.get("baseCommit")
        text = json.dumps(data)
        if raw_value is not None:
            text = text.replace('"@@RAW@@"', '"' + raw_value + '"')
        (repo.root / "hass" / "content" / "migration-baseline.json").write_text(text, "utf-8")
        return repo.root

    def _cli(self, root):
        env = dict(os.environ, PYTHONIOENCODING="utf-8:strict")
        return subprocess.run([sys.executable, "-B", "hass/migration_check.py", "--repo", str(root)],
                              cwd=REPO_ROOT, capture_output=True, env=env, timeout=120)

    def _main_strict(self, root):
        raw, err = io.BytesIO(), io.StringIO()
        out = io.TextIOWrapper(raw, encoding="utf-8", errors="strict", newline="\n")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = migration_check.main(["--repo", str(root)])
        out.flush()
        return code, raw.getvalue(), err.getvalue()

    def test_lone_high_and_low_surrogate_base_commit_are_named_failures(self):
        for raw in LONE:
            with self.subTest(raw=raw):
                root = self._repo(raw)
                baseline = json.loads((root / "hass" / "content" / "migration-baseline.json").read_text("utf-8"))
                self.assertEqual(migration_check._baseline_problem(baseline), REFUSAL)
                self.assertEqual(migration_check.run_checks(root), ([REFUSAL], {}))
                code, out, err = self._main_strict(root)
                self.assertEqual((code, out, err), (1, FAILED.encode(), ""))
                self.assertNotIn(b"\xef\xbf\xbd", out)

    def test_cli_strict_utf8_refuses_before_report_printing(self):
        for raw in ("\\ud800", "\\udfff"):
            with self.subTest(raw=raw):
                root = self._repo(raw)
                proc = self._cli(root)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertEqual(proc.stdout, FAILED.encode())
                self.assertEqual(proc.stderr, b"")

    def test_invalid_base_commit_stops_before_content_loading(self):
        root = self._repo("\\ud800")
        (root / "hass" / "content" / "products.json").unlink()  # canonical source unavailable
        names = ("load_and_validate", "render", "stale_paths")
        before = {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}
        with mock.patch.multiple(migration_check, **{n: mock.DEFAULT for n in names}) as spies:
            code, out, err = self._main_strict(root)
        self.assertEqual((code, out, err), (1, FAILED.encode(), ""))
        for name in names:
            spies[name].assert_not_called()
        after = {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}
        self.assertEqual(before, after)

    def test_existing_shape_precedence_is_unchanged(self):
        def bad_listings(d):
            d["listings"] = []
        root = self._repo("\\ud800", mutate=bad_listings)
        self.assertEqual(self._main_strict(root), (1, b"MIGRATION CHECK FAILED:\n  baseline listings is missing or not an object\n", ""))

        def bad_held(d):
            d["held"]["reason"] = None
        root = self._repo("\\ud800", mutate=bad_held)
        self.assertEqual(self._main_strict(root), (1, b"MIGRATION CHECK FAILED:\n  baseline held.reason is missing or not text\n", ""))
        for value in (None, 5, ["x"]):
            with self.subTest(value=value):
                baseline = json.loads(BASELINE.read_text("utf-8"))
                baseline["baseCommit"] = value
                self.assertEqual(migration_check._baseline_problem(baseline), "baseline baseCommit is missing or not text")
        baseline.pop("baseCommit")
        self.assertEqual(migration_check._baseline_problem(baseline), "baseline baseCommit is missing or not text")

    def test_valid_unicode_and_escaped_pair_preserve_reports(self):
        code, ordinary, err = self._main_strict(REPO_ROOT)
        self.assertEqual((code, err), (0, ""), ordinary)
        real = json.loads(BASELINE.read_text("utf-8"))["baseCommit"]
        self.assertIn(f"baseCommit: {real}\n".encode(), ordinary)
        cases = {"synthetic-\\u00e9": "synthetic-é", "\\u6f22\\u5b57": "漢字", "emoji-\U0001f600": "emoji-\U0001f600",
                 "pair-\\ud83d\\ude00": "pair-\U0001f600"}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                root = self._repo(raw)
                code, out, err = self._main_strict(root)
                self.assertEqual((code, err), (0, ""), out)
                self.assertEqual(out, ordinary.replace(f"baseCommit: {real}".encode(), f"baseCommit: {expected}".encode(), 1))
                proc = self._cli(root)
                self.assertEqual((proc.returncode, proc.stderr, proc.stdout), (0, b"", out))

    def test_no_new_commit_identifier_or_unknown_metadata_policy(self):
        for value in ("", "not hex at all", "line\\nfeed\\u0000nul", "HEAD~3"):
            with self.subTest(value=value):
                root = self._repo(value)
                baseline = json.loads((root / "hass" / "content" / "migration-baseline.json").read_text("utf-8"))
                self.assertIsNone(migration_check._baseline_problem(baseline))
        baseline = json.loads(BASELINE.read_text("utf-8"))
        baseline["unusedMetadata"] = {"x": "\ud800"}
        self.assertIsNone(migration_check._baseline_problem(baseline))


if __name__ == "__main__":
    unittest.main()
