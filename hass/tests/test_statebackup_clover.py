"""HASS-BACKUP-CLOVER-1: the state backup carries `clover/cache.sqlite3`; any other entry in clover/ is refused."""

import contextlib, os, sqlite3  # noqa: E401
from pathlib import Path

from hass import statebackup
from hass.tests.test_statebackup import BackupTestCase

REL = statebackup.CLOVER

class CloverBackupTests(BackupTestCase):
    def make(self):
        folder = self.repo.state / "clover"
        folder.mkdir(mode=0o700)
        with contextlib.closing(sqlite3.connect(self.repo.state / REL)) as db, db:
            db.execute("CREATE TABLE item (id TEXT, name TEXT)")
            db.executemany("INSERT INTO item VALUES (?, ?)", [("A1", "synthetic one"), ("B2", "synthetic two")])
        os.chmod(self.repo.state / REL, 0o600)
        return folder

    def rows(self, path):
        with contextlib.closing(sqlite3.connect(f"{Path(path).as_uri()}?mode=ro", uri=True)) as db:
            return db.execute("SELECT id, name FROM item ORDER BY id").fetchall()

    def test_round_trip_keeps_rows_and_private_modes(self):
        self.make()
        backup = self.backup()
        self.assertIn(REL, self.files(backup))
        self.assertEqual((backup / "clover").stat().st_mode & 0o777, 0o700)
        self.assertEqual((backup / REL).stat().st_mode & 0o777, 0o600)
        self.assertEqual(statebackup.verify(str(backup))["result"], "ok")
        new = self.tmp / "restored"
        self.assertEqual(statebackup.restore(str(backup), str(new), str(self.drill_wt))["result"], "ok")
        self.assertEqual((new / "clover").stat().st_mode & 0o777, 0o700)
        self.assertEqual((new / REL).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.rows(new / REL), self.rows(self.repo.state / REL))
        self.assertEqual(self.rows(new / REL), [("A1", "synthetic one"), ("B2", "synthetic two")])

    def test_unknown_entries_in_clover_are_refused_by_name(self):
        folder = self.make()
        for name, how in (("notes.txt", lambda p: p.write_text("x")), ("cache.sqlite3-journal", lambda p: p.write_text("")),
                          ("link", lambda p: p.symlink_to(folder / "cache.sqlite3"))):
            with self.subTest(name=name):
                how(folder / name)
                made = statebackup.create(str(self.repo.state), str(self.bk))
                self.assertEqual(made["result"], "refused")
                kinds = "symlink" if name == "link" else "unknown entry"
                self.assertEqual(made["problems"], [f"{kinds}: clover/{name}"])
                (folder / name).unlink()
        self.assertEqual(statebackup.create(str(self.repo.state), str(self.bk))["result"], "ok")

    def test_clover_as_a_symlink_is_refused(self):
        (self.tmp / "elsewhere").mkdir()
        (self.repo.state / "clover").symlink_to(self.tmp / "elsewhere")
        self.assertEqual(statebackup.create(str(self.repo.state), str(self.bk))["problems"], ["symlink: clover"])

    def test_no_clover_folder_backs_up_as_before(self):
        backup = self.backup()
        self.assertFalse([rel for rel in self.files(backup) if rel.startswith("clover")])
        self.assertFalse((backup / "clover").exists())
        self.assertEqual(statebackup.verify(str(backup))["result"], "ok")
