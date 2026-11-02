"""RF0550-5 (H24): design_check judges only what the head changed since its merge base with --base."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from unittest import mock

from hass import design_check
from hass.tests import test_design_check as base


class MergeBaseTests(unittest.TestCase):
    # reuse the throwaway-repo helpers by import, without re-running DesignCheckTests' own cases
    setUp, git, write, commit, change, run_check = (getattr(base.DesignCheckTests, n) for n in (
        "setUp", "git", "write", "commit", "change", "run_check"))

    def fork(self, *branch_rels):
        """Cut `branch` from main and change `branch_rels`; then main edits sitegen.py and deletes shop.js."""
        self.git("checkout", "-q", "-b", "branch")
        self.change(*branch_rels)
        self.git("checkout", "-q", "main")
        self.write("hass/sitegen.py", "main moved on\n")
        (self.repo / "storefront-mockup/shop.js").unlink()
        self.commit("main moves on")

    def test_base_moving_on_is_not_outside(self):
        self.fork("storefront-mockup/style.css")
        self.assertEqual(self.run_check("--base", "main", "--head", "branch"),
                         (0, {"result": "ok", "changed": 1, "outside": []}))

    def test_branch_own_outside_change_is_listed_once(self):
        self.fork("storefront-mockup/style.css", "hass/sitegen.py")
        self.assertEqual(self.run_check("--base", "main", "--head", "branch"),
                         (1, {"result": "outside", "changed": 2, "outside": ["M hass/sitegen.py"]}))

    def test_linear_history_unchanged(self):
        self.change("storefront-mockup/shop.js", "hass/sitegen.py", "storefront-mockup/style.css")
        expected = (1, {"result": "outside", "changed": 3, "outside": ["M hass/sitegen.py", "M storefront-mockup/shop.js"]})
        self.assertEqual(self.run_check("--base", "main~1", "--head", "main"), expected)
        two_point = self.git("diff", "--name-status", "main~1", "main").stdout.splitlines()
        self.assertEqual(len(two_point), expected[1]["changed"])

    def test_reversed_refs_judge_main_changes_only(self):
        self.fork("storefront-mockup/style.css")
        self.assertEqual(self.run_check("--base", "branch", "--head", "main"), (1, {
            "result": "outside", "changed": 2, "outside": ["D storefront-mockup/shop.js", "M hass/sitegen.py"]}))

    def test_head_already_merged_into_base_is_ok(self):
        self.fork("storefront-mockup/style.css", "hass/sitegen.py")
        self.git("merge", "-q", "-X", "theirs", "--no-edit", "branch")
        self.assertEqual(self.run_check("--base", "main", "--head", "branch"),
                         (0, {"result": "ok", "changed": 0, "outside": []}))

    def test_no_common_history_is_usage(self):
        self.git("checkout", "-q", "--orphan", "other")
        self.change("storefront-mockup/style.css")
        for argv in (("--base", "main", "--head", "other"), ("--base", "other", "--head", "main")):
            with self.subTest(argv=argv):
                proc = subprocess.run([sys.executable, str(base.SCRIPT), *argv], cwd=self.repo,
                                      capture_output=True, text=True)
                self.assertEqual((proc.returncode, json.loads(proc.stdout)), (2, {"result": "usage"}))
                self.assertEqual(proc.stderr, "design_check: no common history between --base and --head\n")

    def test_merge_base_other_failure_is_git_failed(self):
        for code, out, msg in ((1, b"", "no common history between --base and --head"),
                               (1, b"\n", "no common history between --base and --head"),
                               (128, b"", "git merge-base failed"), (128, b"abc\n", "git merge-base failed")):
            with self.subTest(code=code, out=out), mock.patch.object(
                    design_check.subprocess, "run", return_value=subprocess.CompletedProcess([], code, out, b"")):
                with self.assertRaises(design_check.Usage) as caught:
                    design_check.merge_base("a" * 40, "b" * 40)
                self.assertEqual(str(caught.exception), msg)
        with mock.patch.object(design_check.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, b"c" * 40 + b"\n", b"")) as run:
            self.assertEqual(design_check.merge_base("a", "b"), "c" * 40)
        self.assertEqual(run.call_args.args[0], ["git", "--literal-pathspecs", "merge-base", "a", "b"])

    def test_pair_rule_applies_across_merge_base(self):
        self.git("checkout", "-q", "-b", "branch")
        self.change("hass/templates/index.html")
        self.git("checkout", "-q", "main")
        self.change("storefront-mockup/index.html")
        self.assertEqual(self.run_check("--base", "main", "--head", "branch"), (1, {
            "result": "outside", "changed": 1, "outside": ["unpaired hass/templates/index.html"]}))


if __name__ == "__main__":
    unittest.main()
