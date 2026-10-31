"""RF1150-8 (H19): health --writer names each reason editor.apply would refuse the writer worktree, read-only.

WriterRepo temp repos only (temp main repo, linked writer worktree, 0700 state dir). Never the real state or worktree.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""
import contextlib, io, json, os, shutil, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import health
from hass.tests.test_editor import WriterRepo, git
from hass.tests.test_health import NOW, SETTINGS

DIRTY, MAIN, DETACHED = ("writer worktree has uncommitted changes", "branch main is refused", "detached HEAD is refused")
NO_EMAIL, MAIN_CHECKOUT = "git user.email is not configured", "the main checkout is refused; use a linked writer worktree"
NOT_TOP, UNREADABLE = "writer worktree is not the top of a Hass Git checkout", "writer config unreadable"


class HealthWriterTest(unittest.TestCase):
    def setUp(self):
        self.repo = WriterRepo()
        self.addCleanup(self.repo.cleanup)
        self.tmp = self.repo.state.parent
        self.config({"worktree": str(self.repo.wt), "settings": SETTINGS})

    def config(self, doc):
        (self.repo.state / "config.json").write_text(doc if isinstance(doc, str) else json.dumps(doc))

    def run_health(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.repo.state), *extra], now=NOW)
        [line] = out.getvalue().splitlines()
        for path in (self.repo.state, self.repo.wt, self.repo.main, self.tmp):
            self.assertNotIn(str(path), line)  # 8: no paths
        return code, json.loads(line), line

    def writer(self, *extra):
        code, doc, _ = self.run_health("--writer", *extra)
        return code, [p["detail"] for p in doc["problems"] if p["check"] == "writer"]

    def dirty(self):
        (self.repo.wt / "hass" / "untracked.txt").write_text("x")

    def test_clean_writer_is_ok(self):
        code, doc, _ = self.run_health("--writer")
        self.assertEqual((code, doc["ok"], doc["problems"]), (0, True, []))

    def test_each_refusal_is_named(self):
        self.dirty()
        self.assertEqual(self.writer(), (1, [DIRTY]))
        (self.repo.wt / "hass" / "untracked.txt").unlink()
        git(self.repo.wt, "checkout", "-q", "--ignore-other-worktrees", "main")
        self.assertEqual(self.writer(), (1, [MAIN]))
        git(self.repo.wt, "checkout", "-q", "--detach")
        self.assertEqual(self.writer(), (1, [DETACHED]))
        git(self.repo.wt, "checkout", "-q", "hass/content")
        self.assertEqual(self.writer(), (0, []))
        git(self.repo.main, "config", "extensions.worktreeConfig", "true")
        git(self.repo.wt, "config", "--worktree", "user.email", "")
        self.assertEqual(self.writer(), (1, [NO_EMAIL]))

    def test_two_refusals_in_worktree_problems_order(self):
        git(self.repo.wt, "checkout", "-q", "--detach")
        self.dirty()
        self.assertEqual(self.writer(), (1, [DETACHED, DIRTY]))

    def test_main_checkout_and_gone_worktree(self):
        self.config({"worktree": str(self.repo.main), "settings": SETTINGS})
        self.assertEqual(self.writer(), (1, [MAIN_CHECKOUT]))
        self.config({"worktree": str(self.repo.wt), "settings": SETTINGS})
        shutil.rmtree(self.repo.wt)
        self.assertEqual(self.writer(), (1, [NOT_TOP]))

    def test_missing_or_bad_config(self):
        for doc in ("{", {"settings": SETTINGS}, {"worktree": None}, []):
            with self.subTest(doc=doc):
                self.config(doc)
                self.assertEqual(self.writer(), (1, [UNREADABLE]))
        (self.repo.state / "config.json").unlink()
        self.assertEqual(self.writer(), (1, ["state dir is not initialised; run init first"]))

    def test_read_only_index_state_and_lock(self):
        tracked = self.repo.wt / "hass" / "content" / "store.json"
        st = tracked.stat()
        os.utime(tracked, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))  # stat-dirty, same content
        index = self.repo.main / ".git" / "worktrees" / self.repo.wt.name / "index"
        before = (index.read_bytes(), index.stat().st_mtime_ns)
        listing = sorted(p.name for p in self.repo.state.rglob("*"))
        self.assertEqual(self.writer(), (0, []))
        self.assertEqual((index.read_bytes(), index.stat().st_mtime_ns), before)
        self.assertEqual(sorted(p.name for p in self.repo.state.rglob("*")), listing)
        self.assertFalse((self.repo.state / "writer.lock").exists())

    def test_optional_locks_env_restored(self):
        seen = []
        real = health.editor.worktree_problems

        def spy(wt):
            seen.append(os.environ.get("GIT_OPTIONAL_LOCKS"))
            return real(wt)
        for previous in (None, "1"):
            with self.subTest(previous=previous), mock.patch.dict(os.environ), \
                    mock.patch.object(health.editor, "worktree_problems", spy):
                os.environ.pop("GIT_OPTIONAL_LOCKS", None)
                if previous is not None: os.environ["GIT_OPTIONAL_LOCKS"] = previous
                health.check(str(self.repo.state), writer=True)
                self.assertEqual(os.environ.get("GIT_OPTIONAL_LOCKS"), previous)
        self.assertEqual(seen, ["0", "0"])
        self.config("{")
        with mock.patch.dict(os.environ):
            os.environ.pop("GIT_OPTIONAL_LOCKS", None)
            health.check(str(self.repo.state), writer=True)
            self.assertNotIn("GIT_OPTIONAL_LOCKS", os.environ)

    def test_opt_in_output_unchanged_without_flag(self):
        today = self.run_health()[2]
        self.dirty()
        git(self.repo.wt, "checkout", "-q", "--detach")
        self.assertEqual(self.run_health()[2], today)
        self.assertEqual(health.check(str(self.repo.state), now=NOW)[0], [])
        self.assertEqual(self.writer()[1], [DETACHED, DIRTY])

    def test_seen_dedupes_and_fix_changes_fingerprint(self):
        seen = str(self.tmp / "health.seen")
        self.dirty()
        first, second = self.run_health("--writer", "--seen", seen)[1], self.run_health("--writer", "--seen", seen)[1]
        self.assertEqual((first["notify"], second["notify"], first["fingerprint"]), (True, False, second["fingerprint"]))
        (self.repo.wt / "hass" / "untracked.txt").unlink()
        fixed = self.run_health("--writer", "--seen", seen)[1]
        self.assertEqual((fixed["ok"], fixed["notify"]), (True, True))
        self.assertNotEqual(fixed["fingerprint"], first["fingerprint"])


if __name__ == "__main__":
    unittest.main()
