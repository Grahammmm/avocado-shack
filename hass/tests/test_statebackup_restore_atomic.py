"""RF1100-19 tests: state and media restore publish with the atomic no-replace rename, so a destination created
concurrently (even an empty directory) is kept, and only this call's own restore trees are taken back."""

import contextlib, io, json, os, stat  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import media, statebackup
from hass.tests import test_statebackup_bundle as fav07
from hass.tests.test_media import AT, JPEG
from hass.tests.test_statebackup import STAMP, BackupTestCase

def mode(path): return stat.S_IMODE(os.lstat(path).st_mode)

class RestoreAtomicTests(BackupTestCase):
    make = fav07.ContentBundleTests.make

    def media_backup(self):
        mroot = self.tmp / "mediasrc"
        mroot.mkdir(mode=0o700)
        media.store_original(mroot, JPEG, received_at=AT, source="fixture")
        made = statebackup.create(str(self.repo.state), str(self.bk), now=STAMP, media=str(mroot))
        self.assertEqual(made["result"], "ok", made)
        return made["backup"]

    def cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): code = statebackup.main(list(argv))
        return code, buf.getvalue()

    def left(self): return sorted(os.listdir(self.tmp))

    def collide(self, victim, populate=False):  # create `victim` just before the real kernel rename of that dst
        real, seen = statebackup._rename_noreplace, []
        def publish(src, dst):
            if Path(dst) == victim and not seen:
                seen.append(dst)
                victim.mkdir(); os.chmod(victim, 0o750)
                if populate: (victim / "foreign.txt").write_bytes(b"foreign")
            return real(src, dst)
        return mock.patch.object(statebackup, "_rename_noreplace", side_effect=publish)

    def test_state_destination_created_inside_publish_is_preserved(self):
        backup, _ = self.make()
        for populate in (False, True):
            new = self.tmp / f"r{populate}"
            before = self.left()
            with self.subTest(populate=populate), self.collide(new, populate):
                with self.assertRaises(FileExistsError):
                    statebackup.restore(str(backup), str(new), str(self.drill_wt), media_into=None)
                self.assertEqual(os.listdir(new), ["foreign.txt"] if populate else [])
                self.assertEqual(mode(new), 0o750)
                if populate: self.assertEqual((new / "foreign.txt").read_bytes(), b"foreign")
                self.assertEqual(self.left(), sorted(before + [new.name]))  # no staging tree left

    def test_media_collision_rolls_back_published_state(self):
        backup = self.media_backup()
        new, mnew = self.tmp / "r", self.tmp / "m"
        before = self.left()
        with self.collide(mnew, populate=True), self.assertRaises(FileExistsError):
            statebackup.restore(backup, str(new), str(self.drill_wt), media_into=str(mnew))
        self.assertFalse(os.path.lexists(new))  # the state this call published is taken back
        self.assertEqual(os.listdir(mnew), ["foreign.txt"])
        self.assertEqual(self.left(), sorted(before + ["m"]))
        self.assertEqual(statebackup.verify(backup)["result"], "ok")  # the backup is untouched

    def test_cli_restore_and_drill_collision_are_one_error_json(self):
        backup = self.media_backup()
        for verb in ("restore", "drill"):
            mnew = self.tmp / f"m-{verb}"
            before = self.left()
            with self.subTest(verb=verb), self.collide(mnew):
                code, out = self.cli(verb, backup, "--into", str(self.tmp / f"r-{verb}"), "--worktree",
                                     str(self.drill_wt), "--media-into", str(mnew))
                lines = out.strip().splitlines()
                self.assertEqual((code, len(lines)), (1, 1), out)
                got = json.loads(lines[0])
                self.assertEqual(got["result"], "error")
                self.assertNotIn("Traceback", out)
                self.assertEqual(os.listdir(mnew), [])
                self.assertEqual(self.left(), sorted(before + [mnew.name]))

    def test_existing_links_files_and_dirs_still_refused(self):
        backup, _ = self.make()
        (self.tmp / "dir").mkdir()
        (self.tmp / "file").write_bytes(b"x")
        os.symlink(self.tmp / "nowhere", self.tmp / "dangling")
        before = self.left()
        for name in ("dir", "file", "dangling"):
            with self.subTest(name=name):
                got = statebackup.restore(str(backup), str(self.tmp / name), str(self.drill_wt))
                self.assertEqual(got, {"result": "refused", "problems": ["restore dir already exists; left untouched"]})
        self.assertEqual(self.left(), before)
        self.assertEqual(os.listdir(self.tmp / "dir"), [])
        self.assertTrue(os.path.islink(self.tmp / "dangling"))

    def test_success_preserves_modes_pause_and_media(self):
        backup = self.media_backup()
        new, mnew = self.tmp / "r", self.tmp / "m"
        got = statebackup.restore(backup, str(new), str(self.drill_wt), paused=True, now=STAMP, media_into=str(mnew))
        self.assertEqual((got["result"], got["mediaRestored"], got["paused"]), ("ok", True, True), got)
        self.assertEqual((mode(new), mode(mnew)), (0o700, 0o700))
        self.assertEqual(mode(new / statebackup.CONFIG), 0o600)
        files = [p for p in mnew.rglob("*") if p.is_file()]
        self.assertTrue(files)
        self.assertTrue(all(mode(p) == 0o600 for p in files))
        self.assertFalse([n for n in self.left() if n.startswith(".") and "restore" in n])
