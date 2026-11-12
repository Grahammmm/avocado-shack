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
                    design_check.merge_base("a" * 40, "b" * 40, "/top")
                self.assertEqual(str(caught.exception), msg)
        with mock.patch.object(design_check.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, b"c" * 40 + b"\n", b"")) as run:
            self.assertEqual(design_check.merge_base("a", "b", "/top"), "c" * 40)
        self.assertEqual(run.call_args.args[0], ["git", "--literal-pathspecs", "merge-base", "--all", "a", "b"])
        with mock.patch.object(design_check.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, b"c" * 40 + b"\n" + b"d" * 40 + b"\n", b"")):
            with self.assertRaises(design_check.Usage) as caught:
                design_check.merge_base("a", "b", "/top")
        self.assertEqual(str(caught.exception), "multiple merge bases between --base and --head")

    def test_pair_rule_applies_across_merge_base(self):
        self.git("checkout", "-q", "-b", "branch")
        self.change("hass/templates/index.html")
        self.git("checkout", "-q", "main")
        self.change("storefront-mockup/index.html")
        self.assertEqual(self.run_check("--base", "main", "--head", "branch"), (1, {
            "result": "outside", "changed": 1, "outside": ["unpaired hass/templates/index.html"]}))

    def crisscross(self, a_rel, b_rel):
        """Two branches change a_rel / b_rel from main; x and y merge them in opposite orders (two best bases)."""
        self.git("checkout", "-q", "-b", "a")
        self.change(a_rel)
        self.git("checkout", "-q", "-b", "b", "main")
        self.change(b_rel)
        self.git("checkout", "-q", "-b", "x", "a")
        self.git("merge", "-q", "--no-edit", "b")
        self.git("checkout", "-q", "-b", "y", "b")
        self.git("merge", "-q", "--no-edit", "a")
        bases = self.git("merge-base", "--all", "x", "y").stdout.split()
        self.assertEqual(len(bases), 2)
        return bases

    def cli(self, *argv):
        proc = subprocess.run([sys.executable, str(base.SCRIPT), *argv], cwd=self.repo, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def test_crisscross_two_best_bases_are_usage(self):
        self.crisscross("hass/sitegen.py", "storefront-mockup/style.css")
        # the old single-base choice approved or refused depending on which base git picked
        diffs = {self.git("diff", "--name-only", b, "y").stdout for b in self.git("merge-base", "--all", "x", "y").stdout.split()}
        self.assertEqual(len(diffs), 2)
        for refs in (("x", "y"), ("y", "x")):
            with self.subTest(refs=refs):
                self.assertEqual(self.cli("--base", refs[0], "--head", refs[1]), (
                    2, '{"result": "usage"}\n', "design_check: multiple merge bases between --base and --head\n"))

    def test_ambiguity_is_refused_even_when_each_diff_is_visual(self):
        self.crisscross("storefront-mockup/style.css", "storefront-mockup/hiking.css")
        self.assertEqual(self.cli("--base", "x", "--head", "y")[0], 2)

    def test_ambiguous_bases_stop_before_diff_or_tree_read(self):
        self.crisscross("hass/sitegen.py", "storefront-mockup/style.css")
        verbs = []
        real = design_check.git

        def spy(*args, **kw):
            verbs.append(args[0])
            return real(*args, **kw)
        with mock.patch.object(design_check, "git", spy), self.assertRaises(design_check.Usage):
            design_check.check(self.git("rev-parse", "x").stdout.strip(), self.git("rev-parse", "y").stdout.strip(),
                               str(self.repo))
        self.assertEqual(verbs, ["merge-base"])

    def test_preview_ambiguity_refuses_before_output_or_capture(self):
        from hass import design_preview
        self.crisscross("hass/sitegen.py", "storefront-mockup/style.css")
        out = self.repo.parent / "preview-out-not-made"
        previewer = mock.Mock()
        with mock.patch.object(design_check, "toplevel", return_value=str(self.repo)), \
                self.assertRaises(design_preview.Usage):
            design_preview.run("x", "y", str(out), previewer)
        previewer.capture.assert_not_called()
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
