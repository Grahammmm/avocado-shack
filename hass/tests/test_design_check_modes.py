"""RF0420-12 (H24): a design path whose head mode is not 100644 is outside."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass.tests.test_design_check import ENV, FILES, SCRIPT

CSS = "storefront-mockup/style.css"


class DesignCheckModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        for rel in FILES:
            self.write(rel, f"original {rel}\n")
        self.commit()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, env=ENV, check=True, capture_output=True, text=True)

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")

    def commit(self, chmod=None, rels=()):
        for rel in rels:
            self.write(rel, f"changed {rel}\n")
        self.git("add", "-A")
        for rel, flag in (chmod or {}).items():
            (self.repo / rel).chmod(0o755 if flag == "+x" else 0o644)
            self.git("update-index", f"--chmod={flag}", rel)
        self.git("commit", "-q", "--allow-empty", "-m", "c")

    def mode(self, rel):
        return self.git("ls-tree", "HEAD", "--", rel).stdout.split(" ", 1)[0]

    def run_check(self, base="HEAD~1"):
        proc = subprocess.run([sys.executable, str(SCRIPT), "--base", base, "--head", "HEAD"],
                              cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(len(proc.stdout.splitlines()), 1, proc.stdout)
        return proc.returncode, json.loads(proc.stdout)

    def test_mode_only_executable_stylesheet_is_outside(self):
        self.commit(chmod={CSS: "+x"})
        self.assertEqual(self.mode(CSS), "100755")
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 1, "outside": [f"M {CSS}"]}))

    def test_content_change_plus_executable_is_outside(self):
        self.commit(chmod={"storefront-mockup/hiking.css": "+x"}, rels=["storefront-mockup/hiking.css"])
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 1, "outside": [
            "M storefront-mockup/hiking.css"]}))

    def test_executable_generated_page_named_and_pair_rule_quiet(self):
        page = "storefront-mockup/index.html"
        self.commit(chmod={page: "+x"}, rels=["hass/templates/index.html", page])
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 2, "outside": [f"M {page}"]}))

    def test_executable_template_with_plain_page_is_outside(self):
        tpl = "hass/templates/hike/index.html"
        self.commit(chmod={tpl: "+x"}, rels=[tpl, "storefront-mockup/hike/index.html"])
        self.assertEqual(self.run_check()[1]["outside"], [f"M {tpl}"])

    def test_new_executable_design_file_is_outside(self):
        (self.repo / CSS).unlink()
        self.commit()
        self.commit(chmod={CSS: "+x"}, rels=[CSS])
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 1, "outside": [f"A {CSS}"]}))

    def test_plain_content_change_is_ok(self):
        self.commit(rels=[CSS])
        self.assertEqual(self.run_check(), (0, {"result": "ok", "changed": 1, "outside": []}))

    def test_mode_back_to_plain_with_content_change_is_ok(self):
        self.commit(chmod={CSS: "+x"})
        self.commit(chmod={CSS: "-x"}, rels=[CSS])
        self.assertEqual(self.mode(CSS), "100644")
        self.assertEqual(self.run_check(), (0, {"result": "ok", "changed": 1, "outside": []}))
        self.assertEqual(self.run_check("HEAD~2"), (0, {"result": "ok", "changed": 1, "outside": []}))

    def test_symlink_and_submodule_still_outside(self):
        (self.repo / CSS).unlink()
        (self.repo / CSS).symlink_to("hiking.css")
        self.commit()
        self.assertEqual(self.run_check()[1]["outside"], [f"T {CSS}"])
        sha = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("rm", "-q", "--cached", "storefront-mockup/hiking.css")
        self.git("update-index", "--add", "--cacheinfo", f"160000,{sha},storefront-mockup/hiking.css")
        self.git("commit", "-q", "-m", "submodule")
        self.assertEqual(self.run_check(), (1, {"result": "outside", "changed": 1,
                                                "outside": ["T storefront-mockup/hiking.css"]}))
