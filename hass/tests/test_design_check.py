"""AVB-19 (H24): design_check lists every change outside the design surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import design_check

SCRIPT = Path(__file__).resolve().parents[1] / "design_check.py"
ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME="t",
           GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
FILES = design_check.DESIGN + ("storefront-mockup/shop.js", "hass/sitegen.py")


class DesignCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        for rel in FILES:
            self.write(rel, f"original {rel}\n")
        self.commit("base")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, env=ENV, check=True, capture_output=True, text=True)

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)

    def change(self, *rels):
        for rel in rels:
            self.write(rel, f"changed {rel}\n")
        self.commit("change")

    def run_check(self, *args):
        argv = args or ("--base", "main~1", "--head", "HEAD")
        proc = subprocess.run([sys.executable, str(SCRIPT), *argv], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(len(proc.stdout.splitlines()), 1, proc.stdout)
        return proc.returncode, json.loads(proc.stdout)

    def test_stylesheet_only_is_ok(self):
        self.change("storefront-mockup/style.css")
        self.assertEqual(self.run_check(), (0, {"result": "ok", "changed": 1, "outside": []}))

    def test_template_with_generated_page_is_ok(self):
        self.change("hass/templates/hike/index.html", "storefront-mockup/hike/index.html",
                    "storefront-mockup/hiking.css", "storefront-mockup/trail-explorer.css")
        self.assertEqual(self.run_check(), (0, {"result": "ok", "changed": 4, "outside": []}))

    def test_template_alone_is_unpaired(self):
        self.change("hass/templates/index.html")
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 1,
                                                "outside": ["unpaired hass/templates/index.html"]}))

    def test_generated_page_alone_is_unpaired(self):
        self.change("storefront-mockup/hike/index.html", "storefront-mockup/index.html",
                    "hass/templates/index.html")
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 3,
                                                "outside": ["unpaired storefront-mockup/hike/index.html"]}))

    def test_script_and_code_are_outside(self):
        self.change("storefront-mockup/shop.js", "hass/sitegen.py", "storefront-mockup/style.css")
        code, out = self.run_check()
        self.assertEqual((code, out), (1, {"result": "outside", "changed": 3, "outside": [
            "M hass/sitegen.py", "M storefront-mockup/shop.js"]}))

    def test_new_file_outside_surface(self):
        self.write("storefront-mockup/extra.css", "x\n")
        self.commit("add")
        self.assertEqual(self.run_check()[1]["outside"], ["A storefront-mockup/extra.css"])

    def test_symlink_replacing_stylesheet_is_outside(self):
        path = self.repo / "storefront-mockup/style.css"
        path.unlink()
        path.symlink_to("hiking.css")
        self.commit("link")
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 1,
                                                "outside": ["T storefront-mockup/style.css"]}))

    def test_new_symlink_on_design_path_is_outside(self):
        (self.repo / "storefront-mockup/style.css").unlink()
        self.commit("drop")
        (self.repo / "storefront-mockup/style.css").symlink_to("/etc/passwd")
        self.commit("link")
        self.assertEqual(self.run_check()[1]["outside"], ["A storefront-mockup/style.css"])

    def test_submodule_on_design_path_is_outside(self):
        sha = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("rm", "-q", "--cached", "storefront-mockup/hiking.css")
        self.git("update-index", "--add", "--cacheinfo", f"160000,{sha},storefront-mockup/hiking.css")
        self.git("commit", "-q", "-m", "submodule")
        self.assertEqual(self.run_check()[1]["outside"], ["T storefront-mockup/hiking.css"])

    def test_deleted_design_file_is_outside(self):
        (self.repo / "storefront-mockup/style.css").unlink()
        self.commit("delete")
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 1,
                                                "outside": ["D storefront-mockup/style.css"]}))

    def test_rename_is_delete_plus_add(self):
        self.git("mv", "storefront-mockup/hiking.css", "storefront-mockup/hike.css")
        self.commit("rename")
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 2, "outside": [
            "A storefront-mockup/hike.css", "D storefront-mockup/hiking.css"]}))

    def test_no_changes_is_ok(self):
        self.commit("empty")
        self.assertEqual(self.run_check(), (0, {"result": "ok", "changed": 0, "outside": []}))
        self.assertEqual(self.run_check("--base", "HEAD", "--head", "HEAD")[0], 0)

    def test_bad_refs_are_usage(self):
        for argv in (("--base", "nope", "--head", "HEAD"), ("--base", "main", "--head", "nope"),
                     ("--base", "--output=x", "--head", "HEAD"), ("--base=--output=x", "--head", "HEAD"),
                     ("--base", "main",), ("--base", "HEAD:hass/sitegen.py", "--head", "HEAD")):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_check(*argv), (2, {"result": "usage"}))
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), [".git", "hass", "storefront-mockup"])

    def test_usage_runs_no_further_git(self):
        calls = []

        def fake(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 1, b"", b"")

        with mock.patch.object(design_check.subprocess, "run", side_effect=fake), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            self.assertEqual(design_check.main(["--base", "--output=x", "--head", "HEAD"]), 2)
            self.assertEqual(design_check.main(["--base=--output=x", "--head", "HEAD"]), 2)
            self.assertEqual(calls, [])
            self.assertEqual(design_check.main(["--base", "nope", "--head", "HEAD"]), 2)
        self.assertEqual(calls, [["git", "--literal-pathspecs", "rev-parse", "--verify", "--quiet", "nope^{commit}"]])


if __name__ == "__main__":
    unittest.main()
