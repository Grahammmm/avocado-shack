"""RF0440-13 tests: design_preview keeps Git metadata paths with embedded line feeds intact (output confinement).

Real synthetic Git fixtures (separate and linked metadata whose directory name contains an LF) live under an external
TMPDIR; only the fake Previewer is used, never a browser or server."""

import contextlib, io, os, subprocess, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import design_preview as dp
from hass.design_check import Usage
from hass.tests import test_design_preview as base

TOP = "/no-such-top/work tree"


def snapshot(*roots):
    """{path: bytes} of every file under the roots: proves a refused call wrote nothing."""
    found = {}
    for root in roots:
        for here, _dirs, names in os.walk(root):
            for name in names:
                found[os.path.join(here, name)] = Path(here, name).read_bytes()
    return found


class GitDirFixture(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory(prefix="design-git-dirs-")
        self.addCleanup(holder.cleanup)
        self.addCleanup(os.chdir, os.getcwd())
        self.tmp = Path(holder.name).resolve()
        self.meta = self.tmp / "meta\nline"
        self.work = self.tmp / "work"
        subprocess.run(["git", "init", "-q", "-b", "main", "--separate-git-dir", str(self.meta), str(self.work)],
                       env=base.GIT_ENV, check=True, capture_output=True)
        base.save(self.work, base.FILES, "root")
        base.git(self.work, "checkout", "-q", "-b", "feature")
        base.save(self.work, {"storefront-mockup/style.css": "body{color:red}"}, "feature")
        base.git(self.work, "checkout", "-q", "main")
        base.git(self.work, "worktree", "add", "-q", str(self.tmp / "linked"), "feature")
        self.linked = self.tmp / "linked"

    def main_in(self, cwd, out, base_ref="main", head_ref="feature"):
        """Run the real main(); returns (code, stdout, stderr, Previewer constructions)."""
        built, stdout, stderr = [], io.StringIO(), io.StringIO()
        os.chdir(cwd)
        with mock.patch.object(dp, "Previewer", lambda top: built.append(top) or base.FakePreviewer()), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = dp.main(["--base", base_ref, "--head", head_ref, "--out", str(out)])
        return code, stdout.getvalue(), stderr.getvalue(), built

    def assert_refused(self, cwd, out, roots):
        before = snapshot(*roots)
        code, stdout, stderr, built = self.main_in(cwd, out)
        self.assertEqual((code, stdout, stderr, built), (
            2, '{"result": "usage"}\n', "design_preview: --out is inside the repository\n", []))
        self.assertEqual(snapshot(*roots), before)

    def test_separate_gitdir_embedded_lf_refuses_descendant_output(self):
        out = self.meta / "shots"
        self.assert_refused(self.work, out, [self.work, self.meta])
        self.assertFalse(out.exists())
        self.assert_refused(self.work, self.meta, [self.work, self.meta])  # the metadata folder itself

    def test_linked_gitdir_and_common_dir_are_both_guarded(self):
        gitdir = self.meta / "worktrees" / "linked"
        self.assertTrue(gitdir.is_dir())
        self.assertEqual(base.git(self.linked, "rev-parse", "--git-common-dir"), str(self.meta))
        for guarded in (gitdir, self.meta):
            for target in (guarded / "shots", guarded / "nested"):
                with self.subTest(target=str(target)):
                    self.assert_refused(self.linked, target, [self.linked, self.meta])
                    self.assertFalse(target.exists())
            existing = guarded / "empty-out"
            existing.mkdir(mode=0o700)
            os.chmod(existing, 0o700)
            with self.subTest(existing=str(existing)):
                self.assert_refused(self.linked, existing, [self.linked, self.meta])
                self.assertEqual((os.listdir(existing), existing.stat().st_mode & 0o777), ([], 0o700))
            existing.rmdir()

    def test_metadata_queries_preserve_single_path_framing(self):
        table = [  # (git-dir raw, common-dir raw, expected) written out independently of _git_dirs
            ("/m/a\nb\n", "/m/a\nb\n", ["/m/a\nb", "/m/a\nb"]),
            ("/m/a\n\nb\n", "/m/c\r\n", ["/m/a\n\nb", "/m/c\r"]),
            ("/m/ sp\t \n", "/m/ x \n", ["/m/ sp\t ", "/m/ x "]),
            ("/m/end\n\n", "/m/other\n", ["/m/end\n", "/m/other"]),
            (".git\n", "../shared dir\n", [TOP + "/.git", "/no-such-top/shared dir"]),
            ("/m/no-newline", "/m/x\n", ["/m/no-newline", "/m/x"]),
        ]
        for git_raw, common_raw, expected in table:
            with self.subTest(git_raw=git_raw, common_raw=common_raw):
                with mock.patch.object(dp.design_check, "git", side_effect=[git_raw, common_raw]) as fake:
                    found = dp._git_dirs(TOP)
                self.assertEqual(found, [Path(p) for p in expected])
                self.assertEqual(fake.call_args_list, [mock.call("rev-parse", "--git-dir", cwd=TOP),
                                                       mock.call("rev-parse", "--git-common-dir", cwd=TOP)])

    def test_empty_or_failed_second_metadata_query_cannot_skip_guard(self):
        for first, second in (("/m/a\n", "\n"), ("/m/a\n", ""), ("\n", "/m/a\n")):
            with self.subTest(first=first, second=second):
                with mock.patch.object(dp.design_check, "git", side_effect=[first, second]):
                    with self.assertRaises(Usage) as caught:
                        dp._git_dirs(TOP)
                self.assertEqual(str(caught.exception), "git rev-parse failed")
        real = dp.design_check.git

        def second_fails(*args, **kwargs):
            if args == ("rev-parse", "--git-common-dir"):
                raise Usage("git rev-parse failed")
            return real(*args, **kwargs)

        def second_empty(*args, **kwargs):
            return "\n" if args == ("rev-parse", "--git-common-dir") else real(*args, **kwargs)

        out = self.tmp / "fresh-out"
        before = snapshot(self.work, self.meta)
        for fake in (second_fails, second_empty):
            with mock.patch.object(dp.design_check, "git", side_effect=fake):
                code, stdout, stderr, built = self.main_in(self.work, out)
            self.assertEqual((code, stdout, stderr, built),
                             (2, '{"result": "usage"}\n', "design_preview: git rev-parse failed\n", []))
            self.assertFalse(out.exists())
        self.assertEqual(snapshot(self.work, self.meta), before)

    def test_valid_external_output_and_fragment_sibling_remain_allowed(self):
        existing = self.tmp / "ext\nexisting"
        existing.mkdir(mode=0o700)
        os.chmod(existing, 0o700)
        outs = [self.tmp / "ext\nnew", existing, self.tmp / "meta", self.tmp / "meta\nline-sibling"]
        for out in outs:
            with self.subTest(out=str(out)):
                os.chdir(self.work)
                previewer = base.FakePreviewer()
                code, doc = dp.run("main", "feature", str(out), previewer)
                self.assertEqual((code, doc["result"], len(previewer.calls)), (0, "ok", 4))
                names = sorted(p.name for p in out.iterdir())
                self.assertEqual(names, sorted(f"{s}-{p}-phone{x}.png" for s in ("base", "head")
                                               for p in ("home", "hike") for x in ("", "-desktop")))
                self.assertEqual(out.stat().st_mode & 0o777, 0o700)
        plain = self.tmp / "plain"
        plain.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(plain)], env=base.GIT_ENV, check=True)
        base.save(plain, base.FILES, "root")
        base.git(plain, "checkout", "-q", "-b", "feature")
        base.save(plain, {"storefront-mockup/style.css": "body{color:red}"}, "feature")
        self.assert_refused(plain, plain / ".git" / "shots", [plain])

    def test_scope_outside_precedes_metadata_queries(self):
        base.git(self.work, "checkout", "-q", "-b", "outside", "main")
        base.save(self.work, {"README.md": "outside"}, "outside")
        out = self.meta / "shots"
        before = snapshot(self.work, self.meta)
        with mock.patch.object(dp, "_git_dirs", side_effect=AssertionError("metadata queried")):
            code, stdout, _err, built = self.main_in(self.work, out, head_ref="outside")
        self.assertEqual((code, built, '"result": "outside"' in stdout), (1, [], True))
        self.assertFalse(out.exists())
        self.assertEqual(snapshot(self.work, self.meta), before)


if __name__ == "__main__":
    unittest.main()
