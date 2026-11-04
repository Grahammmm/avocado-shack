"""RF0910-7 (H24): design_check reads the whole change from any folder, whatever diff.relative says."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from hass import design_check
from hass.tests import test_design_check as base


class RelativeTests(unittest.TestCase):
    # reuse the throwaway-repo helpers by import, without re-running DesignCheckTests' own cases
    setUp, git, write, commit, change = (getattr(base.DesignCheckTests, n) for n in (
        "setUp", "git", "write", "commit", "change"))

    def run_from(self, folder, *argv, env=base.ENV):
        argv = argv or ("--base", "main~1", "--head", "HEAD")
        proc = subprocess.run([sys.executable, str(base.SCRIPT), *argv], cwd=folder, env=env,
                              capture_output=True, text=True)
        self.assertEqual(len(proc.stdout.splitlines()), 1, proc.stdout)
        return proc.returncode, json.loads(proc.stdout), proc.stderr

    def test_relative_config_in_subfolder_still_sees_outside_change(self):
        self.write("hass/x.py", "x\n")
        self.commit("add x")
        self.change("storefront-mockup/style.css", "hass/x.py")
        self.git("config", "diff.relative", "true")
        # the config really hides hass/x.py from a plain diff run in the subfolder
        plain = subprocess.run(["git", "diff", "--name-only", "main~1", "HEAD"], cwd=self.repo / "storefront-mockup",
                               env=base.ENV, check=True, capture_output=True, text=True).stdout.split()
        self.assertEqual(plain, ["style.css"])
        self.assertEqual(self.run_from(self.repo / "storefront-mockup")[:2],
                         (1, {"result": "outside", "changed": 2, "outside": ["M hass/x.py"]}))

    def test_subfolder_without_config_matches_top_level(self):
        self.write("hass/x.py", "x\n")
        self.commit("add x")
        self.change("storefront-mockup/style.css", "hass/x.py", "hass/templates/index.html")
        top = self.run_from(self.repo)
        self.assertEqual(top[:2], (1, {"result": "outside", "changed": 3, "outside": [
            "M hass/x.py", "unpaired hass/templates/index.html"]}))
        for folder in ("hass", "hass/templates", "storefront-mockup"):
            with self.subTest(folder=folder):
                self.assertEqual(self.run_from(self.repo / folder), top)

    def test_design_only_head_from_subfolder_with_relative_is_ok(self):
        self.change("hass/templates/index.html", "storefront-mockup/index.html")
        self.git("config", "diff.relative", "true")
        for folder in ("hass", "storefront-mockup", "hass/templates"):
            with self.subTest(folder=folder):
                self.assertEqual(self.run_from(self.repo / folder),
                                 (0, {"result": "ok", "changed": 2, "outside": []}, ""))

    def test_not_a_work_tree_is_usage(self):
        with tempfile.TemporaryDirectory() as plain:
            env = dict(base.ENV, GIT_CEILING_DIRECTORIES=os.path.dirname(os.path.realpath(plain)))
            for argv in ((), ("--base", "nope", "--head", "HEAD")):
                with self.subTest(argv=argv):
                    self.assertEqual(self.run_from(plain, *argv, env=env),
                                     (2, {"result": "usage"}, "design_check: not inside a git work tree\n"))
        # inside the .git directory there is no work tree either
        code, out, err = self.run_from(self.repo / ".git")
        self.assertEqual((code, out, err), (2, {"result": "usage"}, "design_check: not inside a git work tree\n"))

    def test_empty_toplevel_is_usage(self):
        with mock.patch.object(design_check.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, b"\n", b"")):
            with self.assertRaises(design_check.Usage) as caught:
                design_check.toplevel()
        self.assertEqual(str(caught.exception), "not inside a git work tree")

    def test_every_git_call_runs_at_top_with_only_optional_locks_added(self):
        self.change("storefront-mockup/style.css")
        calls, real = [], subprocess.run

        def spy(cmd, **kw):
            calls.append((cmd, kw))
            return real(cmd, **kw)

        clean = {k: v for k, v in base.ENV.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.repo / "storefront-mockup")
        with mock.patch.dict(os.environ, clean, clear=True), mock.patch("sys.stdout"), \
                mock.patch.object(design_check.subprocess, "run", side_effect=spy):
            self.assertEqual(design_check.main(["--base", "main~1", "--head", "HEAD"]), 0)
            expected_env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
        self.assertEqual([c[2:4] for c, _ in calls], [["rev-parse", "--show-toplevel"], ["rev-parse", "--verify"],
                                                       ["rev-parse", "--verify"], ["merge-base", calls[3][0][3]],
                                                       ["diff", "--no-relative"], ["ls-tree", "-r"]])
        self.assertEqual([kw["cwd"] for _, kw in calls], [None] + [str(self.repo.resolve())] * 5)
        for _, kw in calls:
            self.assertEqual(kw["env"], expected_env)
            self.assertFalse({"GIT_DIR", "GIT_WORK_TREE"} & set(kw["env"]))


if __name__ == "__main__":
    unittest.main()
