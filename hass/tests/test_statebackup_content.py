"""FAV-08 tests: restore/drill --content-into NEWDIR rebuild the content checkout from the backup's content.bundle alone
(detached at contentCommit, no remote) and run its own sitegen --check; the live (writer) checkout is never touched."""

import contextlib, io, json, os, subprocess  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import editor, media, statebackup
from hass.tests import test_statebackup_bundle as fav07
from hass.tests.test_editor import git
from hass.tests.test_media import AT, JPEG
from hass.tests.test_statebackup import STAMP, BackupTestCase

CONTENT_KEYS = {"contentRestored", "contentCheck"}

class ContentRestoreTests(BackupTestCase):
    make, out_with = fav07.ContentBundleTests.make, fav07.ContentBundleTests.out_with  # the FAV-07 bundle helpers

    def snapshot(self, wt):  # the live checkout stand-in: HEAD, status and every file's mtime (its .git file too)
        index = Path(wt, git(wt, "rev-parse", "--git-path", "index"))
        stamp, times = os.stat(index).st_mtime_ns, {str(p): os.lstat(p).st_mtime_ns for p in Path(wt).rglob("*")}
        return git(wt, "rev-parse", "HEAD"), statebackup._git_ro(wt, "status", "--porcelain"), times, stamp  # no lock

    def cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): code = statebackup.main(list(argv))
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def left(self):  # entries the restore left beside its targets (dot-named temps included)
        return sorted(os.listdir(self.tmp))

    def test_restore_and_drill_rebuild_content_from_the_bundle_alone(self):
        backup, made = self.make()
        head, before = made["contentCommit"], self.snapshot(self.repo.wt)
        new, content = self.tmp / "restored", self.tmp / "content"
        got = statebackup.restore(str(backup), str(new), str(self.drill_wt), content_into=str(content))
        self.assertEqual((got["result"], got["contentRestored"], got["contentCheck"]), ("ok", True, "ok"), got)
        self.assertEqual(git(content, "rev-parse", "HEAD"), head)
        self.assertEqual(subprocess.run(["git", "-C", str(content), "symbolic-ref", "-q", "HEAD"]).returncode, 1)
        self.assertEqual(git(content, "remote"), "")  # nothing points at the backup
        self.assertEqual(git(content, "status", "--porcelain"), "")
        for rel in editor.GENERATED_PATHS:
            self.assertEqual((content / rel).read_bytes(), (self.repo.wt / rel).read_bytes(), rel)
        drilled = statebackup.drill(str(backup), str(self.tmp / "drilled"), str(self.drill_wt),
                                    content_into=str(self.tmp / "drilled-content"))
        self.assertEqual((drilled["result"], drilled["contentRestored"], drilled["contentCheck"]), ("ok", True, "ok"),
                         drilled)
        self.assertNotIn("step", drilled)
        code, cli = self.cli("restore", str(backup), "--into", str(self.tmp / "r3"), "--worktree", str(self.drill_wt),
                             "--content-into", str(self.tmp / "c3"))
        self.assertEqual((code, cli["contentCheck"]), (0, "ok"))
        self.assertEqual(self.snapshot(self.repo.wt), before)  # live checkout: HEAD, status, mtimes, index

    def test_a_backup_without_a_bundle_is_refused_and_makes_nothing(self):
        with self.out_with({("rev-parse", "HEAD"): ""}): backup, made = self.make()  # pre-FAV-07 shape
        self.assertNotIn(statebackup.BUNDLE, json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))["files"])
        before, refused = self.left(), {"result": "refused", "problems": ["no content bundle in backup"]}
        got = statebackup.restore(str(backup), str(self.tmp / "r"), str(self.drill_wt), content_into=str(self.tmp / "c"))
        self.assertEqual(got, refused)
        self.assertEqual(statebackup.drill(str(backup), str(self.tmp / "d"), str(self.drill_wt),
                                           content_into=str(self.tmp / "c")), {**refused, "step": "restore"})
        self.assertEqual(self.left(), before)

    def test_an_existing_content_dir_or_link_is_refused_and_left_untouched(self):
        backup, _ = self.make()
        empty, link = self.tmp / "empty", self.tmp / "link"
        empty.mkdir()
        link.symlink_to(self.tmp / "nowhere")
        for target in (empty, link):
            with self.subTest(target=target.name):
                got = statebackup.restore(str(backup), str(self.tmp / "r"), str(self.drill_wt), content_into=str(target))
                self.assertEqual(got, {"result": "refused",
                                       "problems": ["content restore dir already exists; left untouched"]})
                self.assertFalse(os.path.lexists(self.tmp / "r"))
        self.assertEqual((os.listdir(empty), os.readlink(link)), ([], str(self.tmp / "nowhere")))

    def test_a_content_dir_inside_the_backup_worktrees_state_or_media_is_unsafe(self):
        backup, _ = self.make()
        before, new = self.left(), self.tmp / "r"
        for inside in (backup / "c", self.repo.wt / "c", self.drill_wt / "c", self.repo.main / "c", new / "c"):
            with self.subTest(inside=str(inside)), self.assertRaises(statebackup.UnsafeState):
                statebackup.restore(str(backup), str(new), str(self.drill_wt), content_into=str(inside))
            self.assertFalse(os.path.lexists(inside))
        code, got = self.cli("drill", str(backup), "--into", str(new), "--worktree", str(self.drill_wt),
                             "--content-into", str(self.repo.wt / "c"))
        self.assertEqual((code, got["result"]), (2, "unsafe-state"))
        self.assertEqual(self.left(), before)

    def test_drifted_generated_files_fail_the_content_check_and_keep_the_dir(self):
        rel = editor.GENERATED_PATHS[0]
        with open(self.repo.wt / rel, "a", encoding="utf-8") as fh: fh.write("\n<!-- hand edit -->\n")
        git(self.repo.wt, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qam", "drift")
        backup, made = self.make()
        content = self.tmp / "content"
        got = statebackup.restore(str(backup), str(self.tmp / "r"), str(self.drill_wt), content_into=str(content))
        self.assertEqual((got["result"], got["contentCheck"]), ("ok", "failed"), got)
        self.assertEqual(git(content, "rev-parse", "HEAD"), made["contentCommit"])  # kept for inspection
        drilled = statebackup.drill(str(backup), str(self.tmp / "d"), str(self.drill_wt),
                                    content_into=str(self.tmp / "dc"))
        self.assertEqual((drilled["result"], drilled["step"], drilled["contentCheck"]),
                         ("drill-failed", "content", "failed"))
        self.assertTrue((self.tmp / "dc" / rel).is_file())
        code, cli = self.cli("restore", str(backup), "--into", str(self.tmp / "r3"), "--worktree", str(self.drill_wt),
                             "--content-into", str(self.tmp / "c3"))
        self.assertEqual((code, cli["result"], cli["contentCheck"]), (1, "ok", "failed"))

    def test_a_failing_git_step_takes_back_the_whole_restore(self):
        backup, _ = self.make()
        real = subprocess.run
        for step in ("clone", "checkout", "remote"):
            def run(cmd, *a, step=step, **kw):
                if cmd[:1] == ["git"] and step in cmd: return subprocess.CompletedProcess(cmd, 128, "", "boom")
                return real(cmd, *a, **kw)
            before = self.left()
            with self.subTest(step=step), mock.patch.object(statebackup.subprocess, "run", side_effect=run):
                with self.assertRaisesRegex(OSError, f"git {step} failed: boom"):
                    statebackup.restore(str(backup), str(self.tmp / "r"), str(self.drill_wt),
                                        content_into=str(self.tmp / "c"))
                code, got = self.cli("drill", str(backup), "--into", str(self.tmp / "d"), "--worktree",
                                     str(self.drill_wt), "--content-into", str(self.tmp / "c"))
            self.assertEqual((code, got["result"]), (1, "error"))
            self.assertEqual(self.left(), before)  # no state, content or dot-named temp dir left

    def test_an_empty_content_dir_appearing_at_publication_is_kept_and_the_restore_taken_back(self):
        mroot = self.tmp / "media"
        mroot.mkdir(mode=0o700)
        media.store_original(mroot, JPEG, received_at=AT, source="fixture")
        made = statebackup.create(str(self.repo.state), str(self.bk), now=STAMP, media=str(mroot))
        self.assertEqual((made["result"], made["contentBundle"]), ("ok", True), made)
        new, mnew, content, real = self.tmp / "r", self.tmp / "m", self.tmp / "content", statebackup._rename_noreplace
        def publish(src, dst):  # the content dir appears after every check, just before the kernel rename
            if dst == content: content.mkdir()
            return real(src, dst)
        before = self.left()
        with mock.patch.object(statebackup, "_rename_noreplace", side_effect=publish), \
             self.assertRaises(FileExistsError):
            statebackup.restore(made["backup"], str(new), str(self.drill_wt), media_into=str(mnew),
                                content_into=str(content))
        self.assertEqual(os.listdir(content), [])  # the dir that appeared is preserved, not replaced
        self.assertEqual(self.left(), sorted(before + ["content"]))  # no state, media or dot-named temp dir left

    def test_without_content_into_results_carry_no_new_keys(self):
        backup, made = self.make()
        got = statebackup.restore(str(backup), str(self.tmp / "r"), str(self.drill_wt))
        self.assertEqual(set(got), {"result", "state", "worktree", "files", "contentCommit"})
        drilled = statebackup.drill(str(backup), str(self.tmp / "d"), str(self.drill_wt))
        self.assertEqual(drilled["result"], "ok", drilled)
        self.assertFalse(CONTENT_KEYS & set(drilled))
        self.assertFalse(os.path.lexists(self.tmp / "r" / statebackup.BUNDLE))
