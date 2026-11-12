"""RF0910-7 (H24): design_check reads the whole change from any folder, whatever diff.relative says."""

from __future__ import annotations

import json
import os
import pathlib
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


def make_repo(root, outside):
    """Two-commit synthetic repo at root (created if needed): CSS-only, or an outside .py change."""
    os.makedirs(root, exist_ok=True)

    def git(*a, **kw):
        return subprocess.run(["git", *a], cwd=root, env=base.ENV, check=True, capture_output=True, **kw)

    git("init", "-q", "-b", "main")
    for rel in ("storefront-mockup/style.css", "hass/outside.py"):
        os.makedirs(os.path.join(root, os.path.dirname(rel)), exist_ok=True)
        with open(os.path.join(root, rel), "w") as fh:
            fh.write("a\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    rel = "hass/outside.py" if outside else "storefront-mockup/style.css"
    with open(os.path.join(root, rel), "w") as fh:
        fh.write("b\n")
    git("commit", "-q", "-a", "-m", "change")
    return git


class WhitespaceRootTests(unittest.TestCase):
    run_from = RelativeTests.run_from
    SUFFIXES = {"space": " ", "tab": "\t", "lf": "\n"}

    def roots(self, outside):
        for name, suffix in self.SUFFIXES.items():
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            yield name, make_repo(os.path.join(tmp.name, "root" + suffix), outside)

    def test_toplevel_preserves_path_whitespace_before_one_record_lf(self):
        for raw, want in ((b"/r \n", "/r "), (b"/r\t\n", "/r\t"), (b"/r\r\n", "/r\r"), (b"/r\n\n", "/r\n"),
                          (b"/r\n\n\n", "/r\n\n")):
            with self.subTest(raw=raw), mock.patch.object(
                    design_check.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, raw, b"")):
                self.assertEqual(design_check.toplevel(), want)
        with mock.patch.object(design_check.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, b"", b"")):
            with self.assertRaises(design_check.Usage):
                design_check.toplevel()

    def test_whitespace_root_design_only_from_root_and_nested_folder(self):
        for name, git in self.roots(outside=False):
            root = git("rev-parse", "--show-toplevel", text=False).stdout.decode().removesuffix("\n")
            self.assertEqual(root[-1], self.SUFFIXES[name])
            for folder in (root, os.path.join(root, "hass")):
                with self.subTest(name=name, folder=folder):
                    self.assertEqual(self.run_from(folder),
                                     (0, {"result": "ok", "changed": 1, "outside": []}, ""))
                    self.assertEqual(self.run_from(folder, "--base", "HEAD", "--head", "HEAD"),
                                     (0, {"result": "ok", "changed": 0, "outside": []}, ""))

    def test_whitespace_root_outside_change_is_reported(self):
        for name, git in self.roots(outside=True):
            root = git("rev-parse", "--show-toplevel", text=False).stdout.decode().removesuffix("\n")
            for folder in (root, os.path.join(root, "storefront-mockup")):
                with self.subTest(name=name, folder=folder):
                    self.assertEqual(self.run_from(folder),
                                     (1, {"result": "outside", "changed": 1, "outside": ["M hass/outside.py"]}, ""))

    def test_trimmed_sibling_cannot_supply_a_clean_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            actual, sibling = os.path.join(tmp, "collision-root "), os.path.join(tmp, "collision-root")
            agit, sgit = make_repo(actual, outside=True), make_repo(sibling, outside=False)
            self.assertEqual(agit("diff", "--name-status", "HEAD~1", "HEAD", text=True).stdout, "M\thass/outside.py\n")

            def snap():
                return [(g("rev-parse", "HEAD", text=True).stdout, g("status", "--porcelain", text=True).stdout,
                         pathlib.Path(r, ".git", "config").read_bytes(),
                         pathlib.Path(r, "hass", "outside.py").read_bytes())
                        for g, r in ((agit, actual), (sgit, sibling))]

            before = snap()
            self.assertEqual(self.run_from(actual, "--base", "HEAD~1", "--head", "HEAD"),
                             (1, {"result": "outside", "changed": 1, "outside": ["M hass/outside.py"]}, ""))
            self.assertEqual(snap(), before)


if __name__ == "__main__":
    unittest.main()
