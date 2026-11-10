"""H20 tests: `statebackup.py diff OLD NEW` names what changed between two backups' manifests and writes nothing.

Both backups come from the real create() on the test_statebackup fixture state with fixed clocks; dirs are temp dirs.
"""

import contextlib, json, os, shutil, sqlite3, subprocess, sys, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import media, statebackup
from hass.tests.test_editor import git
from hass.tests.test_media import AT, JPEG
from hass.tests.test_statebackup import SCRIPT, STAMP, BackupTestCase, tree
from hass.tests.test_statebackup_list import stamps

LATER = STAMP + timedelta(hours=1)
LISTS = ("added", "removed", "changed")

class DiffTests(BackupTestCase):
    def setUp(self):
        super().setUp()
        # These cases compare raw bundle hashes as well as state files. Parallel
        # delta compression can encode the same HEAD differently on each backup.
        # Keep only this synthetic repo deterministic; production diff still
        # reports every changed byte and production Git settings are untouched.
        git(self.repo.wt, "config", "pack.threads", "1")

    def cli(self, *args):  # (exit code, parsed line, raw stdout)
        run = subprocess.run([sys.executable, str(SCRIPT), "diff", *map(str, args)], capture_output=True, text=True)
        if run.returncode != 2: self.assertEqual(run.stderr, "")
        return run.returncode, json.loads(run.stdout) if run.stdout else None, run.stdout

    def make(self, when, **kw):
        made = statebackup.create(str(self.repo.state), str(self.bk), now=when, **kw)
        self.assertEqual(made["result"], "ok", made)
        return Path(made["backup"])

    def put(self, rel, data=b"{}"):
        (self.repo.state / rel).parent.mkdir(mode=0o700, exist_ok=True)
        (self.repo.state / rel).write_bytes(data)

    def db(self, sql):
        with contextlib.closing(sqlite3.connect(self.repo.state / statebackup.DB)) as db, db: db.execute(sql)

    def doc(self, backup, **edit):  # rewrite a backup's MANIFEST.json by hand
        path = backup / statebackup.MANIFEST
        doc = json.loads(path.read_text("utf-8"))
        path.write_text(json.dumps({**doc, **edit}), "utf-8")
        return doc

    def test_identical_backups_differ_in_nothing(self):
        old, new = self.make(STAMP), self.make(LATER)
        code, line, _ = self.cli(old, new)
        self.assertEqual(code, 0)
        self.assertEqual([line[k] for k in LISTS], [[], [], []])
        self.assertEqual((line["same"], line["media_added"], line["media_removed"]), (len(self.files(old)), 0, 0))
        self.assertEqual((line["older"], line["newer"], line["worktree_changed"]),
                         (STAMP.isoformat(), LATER.isoformat(), False))
        self.assertNotIn("order", line)
        self.assertEqual(statebackup.diff(str(old), str(new)), line)

    def test_added_removed_changed_and_swapped(self):
        self.put("changes/chg-gone.json")
        self.put("drafts/chg-kept.json", b'{"v": 1}')
        self.db("CREATE TABLE IF NOT EXISTS diff_probe(x)")
        old = self.make(STAMP)
        (self.repo.state / "changes/chg-gone.json").unlink()
        self.put("drafts/chg-new.json")
        self.put("screenshots/new-shot.png", b"png")
        self.db("INSERT INTO diff_probe VALUES (1)")
        new = self.make(LATER)
        code, line, _ = self.cli(old, new)
        self.assertEqual(code, 0)
        self.assertEqual([line[k] for k in LISTS], [["drafts/chg-new.json", "screenshots/new-shot.png"],
                                                    ["changes/chg-gone.json"], ["conversation.sqlite3"]])
        self.assertEqual(line["same"], len(self.files(old)) - 2)
        self.assertIn("drafts/chg-kept.json", self.files(new))
        code, back, _ = self.cli(new, old)  # swapped: still diffed, flagged reversed
        self.assertEqual((code, back["order"]), (0, "reversed"))
        self.assertEqual([back[k] for k in LISTS], [line["removed"], line["added"], line["changed"]])
        self.assertEqual((back["older"], back["newer"], back["same"]), (line["newer"], line["older"], line["same"]))

    def test_photo_originals_are_counts_only(self):
        store = self.tmp / "media"
        store.mkdir(mode=0o700)
        old = self.make(STAMP, media=str(store))  # an empty store: no originals
        media.store_original(store, JPEG, received_at=AT, source="fixture")
        new = self.make(LATER, media=str(store))
        code, line, raw = self.cli(old, new)
        self.assertEqual((code, line["media_added"], line["media_removed"]), (0, 1, 0))
        self.assertEqual([line[k] for k in LISTS], [[], [], []])
        self.assertNotIn("media/", raw)
        self.assertNotIn("originals/", raw)
        self.assertTrue(any(rel.startswith(statebackup.ORIG) for rel in self.files(new)))
        code, back, raw = self.cli(new, old)
        self.assertEqual((code, back["media_added"], back["media_removed"], back["order"]), (0, 0, 1, "reversed"))
        self.assertNotIn("media/", raw)

    def test_order_unknown_and_worktree_changed(self):
        old, new = self.make(STAMP), self.make(LATER)
        shutil.copytree(new, other := self.tmp / "other")
        self.doc(other, worktree="/elsewhere", createdAt="yesterday")
        line = statebackup.diff(str(old), str(other))
        self.assertEqual((line["result"], line["order"], line["worktree_changed"], line["newer"]),
                         ("ok", "unknown", True, "yesterday"))
        self.doc(other, createdAt=None)
        line = statebackup.diff(str(other), str(old))
        self.assertEqual((line["order"], line["older"]), ("unknown", None))
        self.doc(other, createdAt="2026-11-02T19:00:00")  # naive against aware: not comparable
        self.assertEqual(statebackup.diff(str(old), str(other))["order"], "unknown")

    def test_incomplete_link_and_hand_edited_are_corrupt(self):
        good = self.make(STAMP)
        shutil.copytree(good, partial := self.bk / ".hass-state-20261102T190000Z.partial-123")
        (partial / statebackup.MANIFEST).unlink()  # create() writes MANIFEST.json last
        missing = {"result": "corrupt", "problems": ["NEW: MANIFEST.json missing or invalid"]}
        self.assertEqual(self.cli(good, partial)[:2], (1, missing))
        shutil.copytree(good, edited := self.tmp / "edited")
        doc = self.doc(edited)
        self.doc(edited, files={**doc["files"], "notes.txt": "0" * 64})  # an unknown rel: _manifest refuses it
        self.assertIsNone(statebackup._manifest(edited))
        self.assertEqual(self.cli(edited, good)[:2], (1, {"result": "corrupt",
                                                          "problems": ["OLD: MANIFEST.json missing or invalid"]}))
        self.assertEqual(self.cli(self.tmp / "nowhere", good)[:2],
                         (1, {"result": "corrupt", "problems": ["OLD: not a backup dir"]}))
        self.assertEqual(statebackup.diff(str(edited), str(partial))["problems"],
                         ["OLD: MANIFEST.json missing or invalid", "NEW: MANIFEST.json missing or invalid"])

    def test_symlinked_old_is_never_followed(self):
        good = self.make(STAMP)
        shutil.copytree(good, target := self.tmp / "elsewhere")
        (link := self.tmp / "link").symlink_to(target, target_is_directory=True)
        refused = {"result": "corrupt", "problems": ["OLD: not a backup dir"]}
        with mock.patch.object(statebackup, "_manifest", wraps=statebackup._manifest) as read:
            for old in (link, f"{link}/", f"{link}/."):
                self.assertEqual(statebackup.diff(str(old), str(good)), refused, old)
        self.assertEqual({Path(c.args[0]) for c in read.call_args_list}, {good.absolute()})  # target never read
        os.chmod(target, 0)
        self.addCleanup(os.chmod, target, 0o700)
        self.assertEqual(self.cli(link, good)[:2], (1, refused))

    def test_one_argument_is_usage(self):
        good = self.make(STAMP)
        code, line, _ = self.cli(good)
        self.assertEqual((code, line), (2, None))

    def test_read_only_no_hash_no_sqlite(self):
        self.put("drafts/chg-a.json")
        old = self.make(STAMP)
        self.put("drafts/chg-b.json")
        new = self.make(LATER)
        before = (tree(self.bk), stamps(self.bk))
        with mock.patch.object(statebackup.hashlib, "sha256", side_effect=AssertionError("diff hashed content")), \
                mock.patch.object(statebackup.sqlite3, "connect", side_effect=AssertionError("diff opened sqlite")):
            self.assertEqual(statebackup.diff(str(old), str(new))["added"], ["drafts/chg-b.json"])
        self.assertEqual(self.cli(old, new)[0], 0)
        self.assertEqual((tree(self.bk), stamps(self.bk)), before)

if __name__ == "__main__":
    unittest.main()
