"""H20 tests: `statebackup.py list --out DIR` names every hass-state-* entry, complete or not, and writes nothing.

Complete backups come from the real create() on the test_statebackup fixture state; all dirs are under the temp dir.
"""

import json, os, shutil, subprocess, sys, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import statebackup
from hass.tests.test_editor import git
from hass.tests.test_statebackup import SCRIPT, STAMP, BackupTestCase, tree

KEYS = ["backup", "createdAt", "files", "complete", "problem", "contentCommit"]
REFUSED = {"result": "refused", "problems": ["--out must be a folder, not a link"]}

def row(name, problem):
    return {"backup": name, "createdAt": None, "files": None, "complete": False, "problem": problem,
            "contentCommit": None}

def stamps(root):  # path -> mtime of root and everything below it (lstat: a link is never followed)
    return {str(p): os.lstat(p).st_mtime_ns for p in [root, *root.rglob("*")]}

class ListTests(BackupTestCase):
    def cli(self, out):  # (exit code, parsed lines, raw stdout); never a traceback
        run = subprocess.run([sys.executable, str(SCRIPT), "list", "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(run.stderr, "")
        return run.returncode, [json.loads(line) for line in run.stdout.splitlines()], run.stdout

    def make(self, when):
        made = statebackup.create(str(self.repo.state), str(self.bk), now=when)
        self.assertEqual(made["result"], "ok", made)
        return Path(made["backup"])

    def copy(self, good, name, manifest=None):  # a copy of a good backup, its MANIFEST.json replaced if given
        shutil.copytree(good, dest := self.bk / name)
        if manifest is not None: (dest / statebackup.MANIFEST).write_text(manifest, "utf-8")
        return dest

    def test_two_complete_backups_newest_first(self):
        old, new = self.make(STAMP), self.make(later := STAMP + timedelta(hours=1))
        def done(path, when):
            count = len(json.loads((path / statebackup.MANIFEST).read_text("utf-8"))["files"])
            return dict(zip(KEYS, (path.name, when.isoformat(), count, True, None,
                                       git(self.repo.wt, "rev-parse", "HEAD"))))
        code, rows, _ = self.cli(self.bk)
        self.assertEqual((code, rows), (0, [done(new, later), done(old, STAMP)]))
        self.assertEqual([list(r) for r in rows], [KEYS, KEYS])
        self.assertGreater(rows[0]["files"], 0)
        self.assertEqual(statebackup.list_backups(str(self.bk)), rows)

    def test_incomplete_entries_are_named_and_other_names_ignored(self):
        good = self.make(STAMP)
        (self.bk / "hass-state-20261103T000000Z").mkdir(mode=0o700)  # interrupted: no MANIFEST.json
        shutil.copy(good / statebackup.CONFIG, self.bk / "hass-state-20261103T000000Z")
        self.copy(good, "hass-state-20261104T000000Z", "{not json")
        doc = json.loads((good / statebackup.MANIFEST).read_text("utf-8"))
        self.copy(good, "hass-state-20261105T000000Z", json.dumps({**doc, "schemaVersion": 2}))
        linked = self.copy(good, "hass-state-20261106T000000Z")  # MANIFEST.json is a link to a good one
        (linked / statebackup.MANIFEST).unlink()
        (linked / statebackup.MANIFEST).symlink_to(good / statebackup.MANIFEST)
        shut = self.copy(good, "hass-state-20261107T000000Z")  # a folder the user cannot search
        os.chmod(shut, 0)
        self.addCleanup(os.chmod, shut, 0o700)
        (self.bk / "hass-state-20261108T000000Z").write_bytes(b"not a backup")
        (self.bk / "notes.txt").write_text("unrelated", "utf-8")
        for name in ("hass-state-latest", "hass-state-20261109T000000Z.tmp", "xhass-state-20261109T000000Z",
                     "hass-state-20261109T000000", "hass-state-2026110T000000Z"):
            (self.bk / name).mkdir()
        code, rows, _ = self.cli(self.bk)
        self.assertEqual(code, 0)
        self.assertEqual(rows[:-1], [row("hass-state-20261108T000000Z", "not a folder"),
                                     row("hass-state-20261107T000000Z", "manifest invalid"),
                                     row("hass-state-20261106T000000Z", "manifest invalid"),
                                     row("hass-state-20261105T000000Z", "manifest invalid"),
                                     row("hass-state-20261104T000000Z", "manifest invalid"),
                                     row("hass-state-20261103T000000Z", "no manifest (interrupted)")])
        self.assertEqual((rows[-1]["backup"], rows[-1]["complete"], rows[-1]["problem"]), (good.name, True, None))

    def test_symlinked_entry_is_never_followed(self):
        good = self.make(STAMP)
        shutil.copytree(good, target := self.tmp / "elsewhere")  # a valid backup behind the link, unreadable
        os.chmod(target, 0)
        self.addCleanup(os.chmod, target, 0o700)
        (self.bk / (name := "hass-state-20261110T000000Z")).symlink_to(target, target_is_directory=True)
        with mock.patch.object(statebackup, "_manifest", wraps=statebackup._manifest) as read:
            rows = statebackup.list_backups(str(self.bk))
        self.assertEqual(rows[0], row(name, "symlink"))
        self.assertEqual([Path(c.args[0]).name for c in read.call_args_list], [good.name])  # the link never read
        self.assertEqual(self.cli(self.bk)[1], rows)

    def test_out_link_missing_or_file_is_refused(self):
        self.make(STAMP)
        (link := self.tmp / "bk-link").symlink_to(self.bk, target_is_directory=True)
        (plain := self.tmp / "plain").write_bytes(b"")
        before = tree(self.bk)
        for out in (link, f"{link}/", f"{link}//", f"{link}/.", f"{link}/./", self.tmp / "missing", plain):
            code, rows, raw = self.cli(out)
            self.assertEqual((code, raw), (2, json.dumps(REFUSED) + "\n"), out)  # only the refusal, no listing
            self.assertEqual(statebackup.list_backups(str(out)), REFUSED)
        self.assertEqual((tree(self.bk), os.path.exists(self.tmp / "missing")), (before, False))
        (empty := self.tmp / "empty").mkdir()
        self.assertEqual(self.cli(empty), (0, [], ""))  # no backups: no lines, exit 0
        self.assertEqual([(c, len(r)) for c, r, _ in (self.cli(f"{self.bk}/"), self.cli(f"{self.bk}/."))], [(0, 1)] * 2)

    def test_list_writes_nothing_and_hashes_nothing(self):
        good = self.make(STAMP)
        (self.bk / "hass-state-20261103T000000Z").mkdir(mode=0o700)
        self.copy(good, "hass-state-20261104T000000Z", "{not json")
        (self.bk / "notes.txt").write_text("keep", "utf-8")
        before = (tree(self.bk), stamps(self.bk))
        self.assertEqual([r["problem"] for r in self.cli(self.bk)[1]],
                         ["manifest invalid", "no manifest (interrupted)", None])
        with mock.patch.object(statebackup.hashlib, "sha256", side_effect=AssertionError("list hashed content")):
            self.assertEqual(len(statebackup.list_backups(str(self.bk))), 3)
        self.assertEqual((tree(self.bk), stamps(self.bk)), before)

if __name__ == "__main__":
    unittest.main()
