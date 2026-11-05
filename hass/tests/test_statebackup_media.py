"""H20 tests: `statebackup.py create --media` / `verify` / `restore --media-into` carry the H10 photo originals.
test_statebackup fixtures plus a private 0700 media root filled via media.store_original with the 1x1 fixture pixels."""

import hashlib, json, os, stat, subprocess, sys  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import media, statebackup
from hass.editor import UnsafeState
from hass.tests.test_media import AT, JPEG, PNG
from hass.tests.test_statebackup import SCRIPT, STAMP, BackupTestCase, tree

def mode(path): return stat.S_IMODE(os.lstat(path).st_mode)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class MediaBackupTests(BackupTestCase):
    def setUp(self):
        super().setUp()
        self.media = self.tmp / "media"
        self.media.mkdir(mode=0o700)
        self.jsha = [media.store_original(self.media, data, received_at=AT, source="fixture")["sha256"]
                     for data in (JPEG, PNG)][0]
        self.aa, self.wrong = self.jsha[:2], "00" if not self.jsha.startswith("00") else "ff"

    def make(self, root=None, minute=0):
        return statebackup.create(str(self.repo.state), str(self.bk), now=STAMP + timedelta(minutes=minute),
                                  media=str(self.media if root is None else root))

    def rel(self, ext, aa=None): return f"media/originals/{aa or self.aa}/{self.jsha}.{ext}"

    def relist(self, backup, aa=None, **files):  # a tamperer who also fixes the manifest hashes
        doc = json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))
        doc["files"].update({self.rel(ext, aa): digest for ext, digest in files.items()})
        (backup / statebackup.MANIFEST).write_text(json.dumps(doc), "utf-8")
        return statebackup.verify(str(backup)).get("problems", [])

    def restore(self, backup, media_into=None, into="restored"):
        return statebackup.restore(str(backup), str(self.tmp / into), str(self.drill_wt),
                                   media_into=None if media_into is None else str(media_into))

    def test_round_trip_restores_a_byte_identical_private_root(self):  # through the CLI
        def cli(*args):
            run = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            return json.loads(run.stdout)
        self.apply("kumquat desc")
        source = tree(self.media)
        made = cli("create", "--state", self.repo.state, "--out", self.bk, "--media", self.media)
        self.assertEqual((made["result"], made["media"]), ("ok", 2), made)
        backup = Path(made["backup"])
        doc = json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))
        self.assertEqual(doc["media"], {"originals": 2})
        self.assertIn(self.rel("json"), doc["files"])
        self.assertEqual(cli("verify", backup)["result"], "ok")
        got = cli("restore", backup, "--into", self.tmp / "restored", "--worktree", self.drill_wt,
                  "--media-into", new := self.tmp / "media2")
        self.assertEqual((got["result"], got["mediaRestored"], got["media"]), ("ok", True, 2), got)
        self.assertEqual((tree(new), tree(self.media)), (source, source))  # the source root is never written
        self.assertFalse((self.tmp / "restored" / "media").exists())
        for dirpath, dirs, names in os.walk(new):
            self.assertEqual(mode(dirpath), 0o700, dirpath)
            for name in names: self.assertEqual(mode(Path(dirpath, name)), 0o600, name)
        self.assertTrue(media.store_original(new, JPEG, received_at=AT, source="fixture")["duplicate"])

    def test_without_media_nothing_changes(self):
        made = statebackup.create(str(self.repo.state), str(self.bk))
        self.assertNotIn("media", made)
        backup = Path(made["backup"])
        doc = json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))
        self.assertEqual(set(doc), {"schemaVersion", "createdAt", "worktree", "files", "contentCommit"})
        self.assertFalse((backup / "media").exists() or any(rel.startswith("media") for rel in doc["files"]))
        self.assertEqual(self.restore(backup, self.tmp / "media2"), {"result": "refused",
                                                                     "problems": ["no media in backup"]})
        self.assertFalse((self.tmp / "media2").exists() or (self.tmp / "restored").exists())
        self.assertNotIn("mediaRestored", self.restore(backup))

    def test_empty_store_backs_up_no_media_dir(self):
        (empty := self.tmp / "empty").mkdir(mode=0o700)
        for minute in (0, 1):
            if minute: (empty / "originals").mkdir(mode=0o700)
            made = self.make(empty, minute)
            self.assertEqual((made["result"], made["media"]), ("ok", 0), made)
            self.assertFalse((Path(made["backup"]) / "media").exists())
            self.assertEqual(statebackup.verify(made["backup"])["result"], "ok")

    def test_strays_symlinks_odd_names_and_wrong_dirs_are_refused(self):
        folder, link = self.media / "originals" / self.aa, f"{self.aa}{'0' * 62}.jpg"
        (folder / ".tmp-k2j4").write_bytes(b"partial")
        (folder / "notes.txt").write_bytes(b"x")
        os.symlink(folder / f"{self.jsha}.jpg", folder / link)
        (self.media / "originals" / self.wrong).mkdir(mode=0o700)
        (self.media / "originals" / self.wrong / f"{self.jsha}.jpg").write_bytes(JPEG)
        (self.media / "web").mkdir(mode=0o700)
        made = self.make()
        self.assertEqual(made, {"result": "refused", "problems": sorted([
            f"unknown entry: media/originals/{self.aa}/{name}" for name in (".tmp-k2j4", "notes.txt")] + [
            f"symlink: media/originals/{self.aa}/{link}", f"unknown entry: {self.rel('jpg', self.wrong)}",
            "unknown media entry: web"])})
        self.assertEqual(os.listdir(self.bk), [])

    def test_unsettled_pairs_write_nothing(self):
        side, orig = (self.media / self.rel(ext)[6:] for ext in ("json", "jpg"))
        kept = side.read_bytes()
        side.unlink()
        self.assertEqual(self.make(), {"result": "unsettled", "problems": [f"unsettled media: {self.jsha[:12]}"]})
        side.write_bytes(kept)
        orig.unlink()  # a sidecar without its original
        self.assertEqual(self.make()["problems"], [f"unsettled media: {self.jsha[:12]}"])
        self.assertEqual(os.listdir(self.bk), [])

    def test_tampered_backups_are_named_by_verify_and_not_restored(self):
        backup = Path(self.make()["backup"])
        flipped = bytearray(JPEG)
        flipped[-3] ^= 1
        (backup / self.rel("jpg")).write_bytes(bytes(flipped))
        self.assertEqual(self.relist(backup, jpg=sha(backup / self.rel("jpg"))),
                         [f"content mismatch: {self.rel('jpg')}"])
        self.assertEqual(self.restore(backup, self.tmp / "media2")["result"], "corrupt")
        self.assertFalse((self.tmp / "media2").exists() or (self.tmp / "restored").exists())
        (backup / self.rel("jpg")).write_bytes(JPEG)
        (backup / self.rel("json")).write_text(json.dumps({"sha256": "0" * 64}), "utf-8")
        self.assertEqual(self.relist(backup, jpg=self.jsha, json=sha(backup / self.rel("json"))),
                         [f"sidecar mismatch: {self.rel('jpg')}"])
        (backup / self.rel("json")).write_bytes((self.media / self.rel("json")[6:]).read_bytes())
        self.assertEqual(self.relist(backup, json=sha(backup / self.rel("json"))), [])
        (backup / "media" / "originals" / self.wrong).mkdir(mode=0o700)
        (backup / self.rel("jpg", self.wrong)).write_bytes(JPEG)
        os.chmod(backup / self.rel("jpg", self.wrong), 0o600)
        self.assertEqual(statebackup.verify(str(backup))["problems"], [f"unlisted: {self.rel('jpg', self.wrong)}"])
        self.assertEqual(self.relist(backup, aa=self.wrong, jpg=self.jsha), ["MANIFEST.json missing or invalid"])

    def test_orphan_sidecar_and_media_count_are_checked_both_ways(self):  # RETURN t_68f64a9f
        backup = Path(self.make()["backup"])
        manifest = backup / statebackup.MANIFEST
        def edit(drop=(), originals=2):  # a tamperer who deletes files and their manifest entries
            doc = json.loads(manifest.read_text("utf-8"))
            for ext in drop:
                doc["files"].pop(self.rel(ext))
                (backup / self.rel(ext)).unlink(missing_ok=True)
            doc["media"] = {"originals": originals}
            manifest.write_text(json.dumps(doc), "utf-8")
            return statebackup.verify(str(backup)).get("problems", [])
        self.assertEqual(edit(["jpg"]), [f"unpaired: {self.rel('json')}", "media count mismatch"])
        self.assertEqual(edit(originals=1), [f"unpaired: {self.rel('json')}"])  # the count alone cannot excuse it
        self.assertEqual(self.restore(backup, self.tmp / "media2")["result"], "corrupt")
        self.assertFalse((self.tmp / "media2").exists() or (self.tmp / "restored").exists())
        self.assertEqual(edit(["json"], originals=2), ["media count mismatch"])  # both gone, count still 2
        for bad in (0, "1", True, None):
            with self.subTest(originals=bad): self.assertEqual(edit(originals=bad), ["media count mismatch"])
        self.assertEqual(edit(originals=1), [])
        got = self.restore(backup, self.tmp / "media2")
        self.assertEqual((got["result"], got["media"]), ("ok", 1), got)
        self.assertEqual(len([n for _, _, names in os.walk(self.tmp / "media2") for n in names]), 2)

    def test_unsafe_media_dirs_raise_and_exit_2(self):
        (link := self.tmp / "link").symlink_to(self.media)
        (loose := self.tmp / "loose").mkdir(mode=0o700)
        os.chmod(loose, 0o755)
        (in_repo := self.repo.main / "photos").mkdir(mode=0o700)
        (in_out := self.bk / "photos").mkdir(mode=0o700)
        for bad in (link, loose, in_repo, in_out, self.tmp / "absent"):
            with self.subTest(bad=bad.name), self.assertRaises(UnsafeState): self.make(bad)
        run = subprocess.run([sys.executable, str(SCRIPT), "create", "--state", str(self.repo.state), "--out",
                              str(self.bk), "--media", str(link)], capture_output=True, text=True)
        self.assertEqual((run.returncode, json.loads(run.stdout)["result"]), (2, "unsafe-state"), run.stderr)
        self.assertEqual(os.listdir(self.bk), ["photos"])

    def test_restore_choices(self):
        backup = Path(self.make()["backup"])
        got = self.restore(backup)
        self.assertEqual((got["result"], got["mediaRestored"], got["media"]), ("ok", False, 2), got)
        (taken := self.tmp / "taken").mkdir(mode=0o700)
        (taken / "keep").write_bytes(b"k")
        kept = tree(taken)
        self.assertEqual(self.restore(backup, taken, "r2")["problems"],
                         ["media restore dir already exists; left untouched"])
        self.assertEqual((tree(taken), (self.tmp / "r2").exists()), (kept, False))
        for unsafe in (backup / "m", self.tmp / "r3" / "m", self.repo.main / "m"):
            with self.subTest(unsafe=str(unsafe)), self.assertRaises(UnsafeState): self.restore(backup, unsafe, "r3")
        real_copy, real_rename, names = statebackup._copy, statebackup._rename_noreplace, sorted(os.listdir(self.tmp))
        def copy(src, dst):  # the media copy fails
            if "originals" in str(dst): raise OSError(28, "No space left on device")
            real_copy(src, dst)
        def rename(src, dst):  # the state rename, or the media rename after it, fails
            if str(dst) == fail: raise OSError(28, "No space left on device")
            real_rename(src, dst)
        for owner, name, fake, fail in ((statebackup, "_copy", copy, ""), (statebackup, "_rename_noreplace", rename, str(self.tmp / "r4")),
                                        (statebackup, "_rename_noreplace", rename, str(self.tmp / "m4"))):
            with self.subTest(fail=fail or name), mock.patch.object(owner, name, side_effect=fake), \
                    self.assertRaises(OSError):
                self.restore(backup, self.tmp / "m4", "r4")
            self.assertEqual(sorted(os.listdir(self.tmp)), names)
