"""H20 tests: `statebackup create` builds the backup in a dot-named partial dir and renames it in last, so a failed or
interrupted run leaves no hass-state-<stamp> folder (and no partial). test_statebackup fixtures; temp dirs only."""

import contextlib, errno, hashlib, io, json, os, shutil  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import health, statebackup
from hass.tests.test_editor import git
from hass.tests.test_statebackup import STAMP, BackupTestCase, tree

NAME = f"hass-state-{STAMP.strftime('%Y%m%dT%H%M%SZ')}"
REAL_SNAPSHOT, REAL_COPY, REAL_REPLACE = statebackup._snapshot, statebackup._copy, os.replace
REAL_PUBLISH = statebackup._rename_noreplace

class AtomicCreateTests(BackupTestCase):
    def setUp(self):
        super().setUp()
        self.apply("kumquat desc")
        self.apply("kumquat hours")
        self.assertGreaterEqual(len(os.listdir(self.repo.state / "drafts")), 2)
        self.final = self.bk / NAME

    def make(self):
        return statebackup.create(str(self.repo.state), str(self.bk), now=STAMP)

    def cli(self):  # main(): one JSON line and the exit code; never a traceback
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = statebackup.main(["create", "--state", str(self.repo.state), "--out", str(self.bk)])
        [line] = out.getvalue().splitlines()
        return code, json.loads(line)

    def cli_at_stamp(self):  # main() with its clock fixed at STAMP
        with mock.patch.object(statebackup, "datetime", wraps=statebackup.datetime) as clock:
            clock.now.return_value = STAMP
            return self.cli()

    def assert_nothing_left(self, keep=()):
        self.assertEqual(sorted(os.listdir(self.bk)), sorted(keep))

    def fails_cleanly(self, patch):
        with patch:
            code, out = self.cli()
        self.assertEqual((code, out["result"]), (1, "error"), out)
        self.assert_nothing_left()
        with patch, self.assertRaises(OSError):  # in process, the fixed stamp: the same folder stays free
            self.make()
        self.assert_nothing_left()
        made = self.make()  # retry with the same `now`
        self.assertEqual((made["result"], made["backup"]), ("ok", str(self.final)), made)
        self.assertEqual(statebackup.verify(made["backup"])["result"], "ok")

    def test_happy_path_is_todays_backup_and_leaves_no_partial(self):
        made = self.make()
        self.assertEqual((made["result"], made["backup"]), ("ok", str(self.final)), made)
        self.assertEqual(statebackup.verify(str(self.final)), {"result": "ok", "files": made["files"]})
        self.assert_nothing_left([NAME])
        files = statebackup._scan(self.repo.state)[0]
        listed = sorted(rel for rel, digest in tree(self.final).items() if digest is not None)
        self.assertEqual(listed, sorted(files + [statebackup.MANIFEST]))
        hashes = {rel: hashlib.sha256((self.final / rel).read_bytes()).hexdigest() for rel in files}
        cfg = json.loads((self.repo.state / "config.json").read_text("utf-8"))
        doc = {"schemaVersion": 1, "createdAt": STAMP.isoformat(), "worktree": cfg["worktree"], "files": hashes,
               "contentCommit": git(self.repo.wt, "rev-parse", "HEAD")}
        self.assertEqual((self.final / statebackup.MANIFEST).read_bytes(),
                         json.dumps(doc, indent=2, sort_keys=True).encode("utf-8"))  # main's manifest bytes
        self.assertEqual(os.stat(self.final).st_mode & 0o777, 0o700)

    def test_snapshot_failure_leaves_nothing(self):
        def snap(src, dst):
            if src.name == statebackup.DB: raise OSError(errno.EIO, "snapshot failed")
            return REAL_SNAPSHOT(src, dst)
        self.fails_cleanly(mock.patch.object(statebackup, "_snapshot", side_effect=snap))

    def test_copy_failure_on_the_second_draft_leaves_nothing(self):
        seen = []
        def copy(src, dst):
            if src.parent.name == "drafts" and len(seen) == 1:
                seen.clear()  # fail once per run: the second draft of this run
                raise OSError(errno.ENOSPC, "No space left on device")
            if src.parent.name == "drafts": seen.append(src)
            return REAL_COPY(src, dst)
        self.fails_cleanly(mock.patch.object(statebackup, "_copy", side_effect=copy))

    def test_manifest_write_failure_leaves_nothing(self):
        def replace(src, dst, *args, **kw):
            if Path(dst).name == statebackup.MANIFEST: raise OSError(errno.EIO, "manifest write failed")
            return REAL_REPLACE(src, dst, *args, **kw)
        self.fails_cleanly(mock.patch.object(statebackup.os, "replace", side_effect=replace))

    def test_interrupt_mid_copy_leaves_nothing(self):  # cancelled: ^C during the build
        with mock.patch.object(statebackup, "_copy", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.make()
        self.assert_nothing_left()
        self.assertEqual(self.make()["result"], "ok")

    def test_existing_final_dir_or_link_is_exists_and_untouched(self):
        self.final.mkdir(mode=0o700)
        (self.final / "keep").write_bytes(b"older")
        before = tree(self.bk)
        self.assertEqual(self.make(), {"result": "exists", "backup": str(self.final)})
        self.assertEqual(tree(self.bk), before)
        shutil.rmtree(self.final)
        self.final.symlink_to(self.tmp / "nowhere")  # a dangling link is not a free stamp either
        self.assertEqual(self.make()["result"], "exists")
        self.assertEqual(tree(self.bk), {NAME: "->" + str(self.tmp / "nowhere")})

    def test_final_dir_appearing_inside_the_rename_is_untouched(self):
        for keep in (b"theirs", b""):  # full, then empty: os.rename would silently replace an empty dir
            def rename(src, dst):  # it appears inside the publish step, after any check, just before the kernel rename
                self.final.mkdir(mode=0o700)
                if keep: (self.final / "keep").write_bytes(keep)
                return REAL_PUBLISH(src, dst)
            with self.subTest(full=bool(keep)), mock.patch.object(statebackup, "_rename_noreplace", side_effect=rename):
                code, out = self.cli_at_stamp()
                self.assertEqual((code, out["result"]), (1, "error"), out)
                want = {NAME: None, f"{NAME}/keep": hashlib.sha256(keep).hexdigest()} if keep else {NAME: None}
                self.assertEqual(tree(self.bk), want)  # theirs untouched, our partial removed
                shutil.rmtree(self.final)

    def test_empty_final_dir_appearing_during_the_build_is_not_replaced(self):
        def copy(src, dst):  # an empty folder would be silently replaced by os.rename; the no-replace rename refuses it
            os.makedirs(self.final, mode=0o700, exist_ok=True)
            return REAL_COPY(src, dst)
        with mock.patch.object(statebackup, "_copy", side_effect=copy), self.assertRaises(FileExistsError):
            self.make()
        self.assertEqual(tree(self.bk), {NAME: None})

    def test_stale_partial_of_another_run_is_never_removed(self):
        stale = self.bk / f".{NAME}.partial-{os.getpid()}"  # a killed run whose pid was reused
        stale.mkdir(mode=0o700)
        (stale / "half").write_bytes(b"x")
        with self.assertRaises(FileExistsError):
            self.make()
        self.assertEqual(tree(self.bk), {stale.name: None, f"{stale.name}/half": hashlib.sha256(b"x").hexdigest()})

    def test_health_and_list_see_no_backup_after_a_failed_create(self):
        with mock.patch.object(statebackup, "_snapshot", side_effect=OSError(errno.EIO, "x")), \
                self.assertRaises(OSError):
            self.make()
        problems = health.check(str(self.repo.state), backups=str(self.bk), now=STAMP)[0]
        self.assertIn({"check": "backup-age", "detail": "no complete backup"}, problems)
        self.assertEqual(statebackup.list_backups(str(self.bk)), [])
