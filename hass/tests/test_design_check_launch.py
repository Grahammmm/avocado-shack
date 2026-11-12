"""RF0010-10 (H24): Git launch failures return the design-check usage result, never a traceback."""

from __future__ import annotations

import contextlib
import errno
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass import design_check, design_preview

SCRIPT = Path(__file__).resolve().parents[1] / "design_check.py"
CSS = "storefront-mockup/style.css"
SENTINEL = "/secret-sentinel/path"
ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME="t",
           GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
real_run = subprocess.run


def make_repo(root: Path, outside: bool = False) -> None:
    def git(*args):
        real_run(["git", *args], cwd=root, env=ENV, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    (root / CSS).parent.mkdir(parents=True)
    (root / CSS).write_text("a\n")
    git("add", "-A")
    git("commit", "-q", "-m", "one")
    (root / CSS).write_text("b\n")
    if outside:
        (root / "other.py").write_text("x\n")
    git("add", "-A")
    git("commit", "-q", "-m", "two")


def failing_after(allowed: int, exc: OSError):
    calls = []

    def run(cmd, *a, **kw):
        calls.append(cmd[2])
        if len(calls) > allowed:
            raise exc
        return real_run(cmd, *a, **kw)
    return run, calls


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        old = os.getcwd()
        self.addCleanup(os.chdir, old)

    def run_main(self, run, module=design_check, argv=("--base", "HEAD~1", "--head", "HEAD")):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(design_check.subprocess, "run", run), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = module.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_missing_git_cli_is_one_usage_json_line(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        env = dict(os.environ, PATH=str(empty))
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT), "--base", "HEAD", "--head", "HEAD"],
                              cwd=self.tmp.name, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, '{"result": "usage"}\n')
        self.assertEqual(proc.stderr, "design_check: not inside a git work tree\n")
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), ["empty", "repo"])

    def test_git_launch_oserror_matrix_is_sanitized(self):
        excs = [FileNotFoundError(errno.ENOENT, "boom " + SENTINEL, SENTINEL), PermissionError(errno.EACCES, "x", SENTINEL),
                NotADirectoryError(errno.ENOTDIR, "x", SENTINEL), OSError(errno.E2BIG, "Argument list too long")]
        for exc in excs:
            for empty_ok in (False, True):
                with self.subTest(exc=type(exc).__name__, empty_ok=empty_ok), \
                        mock.patch.object(design_check.subprocess, "run", side_effect=exc):
                    with self.assertRaises(design_check.Usage) as ctx:
                        design_check.git("merge-base", SENTINEL, empty_ok=empty_ok)
                    self.assertEqual(str(ctx.exception), "git merge-base failed")
                    self.assertIsNone(ctx.exception.__cause__)
                    self.assertTrue(ctx.exception.__suppress_context__)

    def test_main_stops_after_each_failed_git_stage(self):
        make_repo(self.root)
        os.chdir(self.root)
        names = ["rev-parse", "rev-parse", "rev-parse", "merge-base", "diff", "ls-tree"]
        for allowed in range(len(names)):
            with self.subTest(failing_stage=names[allowed], allowed=allowed):
                run, calls = failing_after(allowed, FileNotFoundError(errno.ENOENT, SENTINEL, SENTINEL))
                code, out, err = self.run_main(run)
                self.assertEqual((code, out), (2, '{"result": "usage"}\n'))
                self.assertNotIn(SENTINEL, err)
                self.assertEqual(len(calls), allowed + 1)
        code, out, _ = self.run_main(real_run)
        self.assertEqual((code, json.loads(out)["result"]), (0, "ok"))
        # ordinary bad ref stays the old nonzero-exit usage
        code, out, err = self.run_main(real_run, argv=("--base", "nope", "--head", "HEAD"))
        self.assertEqual((code, out, err), (2, '{"result": "usage"}\n', "design_check: git rev-parse failed\n"))

    def test_preview_scope_launch_failure_makes_no_output(self):
        make_repo(self.root)
        os.chdir(self.root)
        out_dir = Path(self.tmp.name) / "previews"
        run, _ = failing_after(0, FileNotFoundError(errno.ENOENT, SENTINEL, SENTINEL))
        with mock.patch.object(design_preview, "Previewer") as previewer:
            code, out, err = self.run_main(run, module=design_preview, argv=(
                "--base", "HEAD~1", "--head", "HEAD", "--out", str(out_dir)))
        self.assertEqual((code, out), (2, '{"result": "usage"}\n'))
        self.assertNotIn(SENTINEL, err)
        previewer.assert_not_called()
        self.assertFalse(out_dir.exists())

    def test_valid_equal_refs_css_and_outside_controls_remain(self):
        make_repo(self.root, outside=True)
        os.chdir(self.root)
        code, out, _ = self.run_main(real_run, argv=("--base", "HEAD", "--head", "HEAD"))
        self.assertEqual((code, json.loads(out)), (0, {"result": "ok", "changed": 0, "outside": []}))
        code, out, _ = self.run_main(real_run)
        self.assertEqual((code, json.loads(out)), (1, {"result": "outside", "changed": 2, "outside": ["A other.py"]}))
        code, out, _ = self.run_main(real_run, argv=("--base", "HEAD~1", "--head", "HEAD~1"))
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
