"""FAV-07 tests: a backup carries content.bundle, a full git bundle of the writer worktree at contentCommit (site content
and committed web photos), listed and hashed in MANIFEST.json; verify checks its head. Temp repos only; nothing live."""

import hashlib, json, os, subprocess  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import statebackup
from hass.tests.test_editor import SITE_FILES, git
from hass.tests.test_statebackup import STAMP, BackupTestCase

BUNDLE = statebackup.BUNDLE
PHOTO = "storefront-mockup/hike/fav07-web-photo.jpg"

class ContentBundleTests(BackupTestCase):
    def setUp(self):
        super().setUp()
        (self.repo.wt / PHOTO).write_bytes(b"\xff\xd8\xff\xe0 committed web photo \x00\x01\xfe")
        git(self.repo.wt, "add", PHOTO)
        git(self.repo.wt, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "photo")

    def make(self, minute=0):
        made = statebackup.create(str(self.repo.state), str(self.bk), now=STAMP + timedelta(minutes=minute))
        self.assertEqual(made["result"], "ok", made)
        return Path(made["backup"]), made

    def doc(self, backup):
        return json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))

    def write_doc(self, backup, doc):
        (backup / statebackup.MANIFEST).write_text(json.dumps(doc, indent=2, sort_keys=True), "utf-8")

    def out_with(self, answers):  # editor._out with some git subcommands answered; every other call is real
        real = statebackup.editor._out
        def out(wt, *args):
            if args[:2] in answers:
                if isinstance(answers[args[:2]], Exception): raise answers[args[:2]]
                return answers[args[:2]]
            return real(wt, *args)
        return mock.patch.object(statebackup.editor, "_out", side_effect=out)

    def test_bundle_holds_the_head_and_the_committed_content(self):
        head = git(self.repo.wt, "rev-parse", "HEAD")
        self.assertEqual(git(self.repo.wt, "rev-list", "--count", "HEAD"), "2")
        backup, made = self.make()
        self.assertEqual((made["contentCommit"], made["contentBundle"]), (head, True))
        path = backup / BUNDLE
        self.assertEqual(os.lstat(path).st_mode & 0o777, 0o600)
        self.assertEqual(self.doc(backup)["files"][BUNDLE], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(statebackup.verify(str(backup)), {"result": "ok", "files": made["files"]})
        clone = self.tmp / "clone"
        subprocess.run(["git", "clone", "-q", str(path), str(clone)], check=True, capture_output=True)
        self.assertEqual((git(clone, "rev-parse", "HEAD"), git(clone, "rev-list", "--count", "HEAD")), (head, "2"))
        self.assertEqual(git(self.repo.wt, "status", "--porcelain"), "")  # clean: the files on disk are HEAD's
        for rel in (PHOTO, *SITE_FILES):
            self.assertEqual((clone / rel).read_bytes(), (self.repo.wt / rel).read_bytes(), rel)

    def test_an_unreadable_head_makes_no_bundle_and_verifies(self):
        for minute, (name, answer) in enumerate([("git missing", OSError("no git")), ("not a repo", "")]):
            with self.subTest(name), self.out_with({("rev-parse", "HEAD"): answer}):
                backup, made = self.make(minute)
            self.assertEqual((made["contentCommit"], made["contentBundle"]), (None, False))
            doc = self.doc(backup)
            self.assertNotIn("contentCommit", doc)
            self.assertNotIn(BUNDLE, doc["files"])
            self.assertFalse(os.path.lexists(backup / BUNDLE))
            self.assertEqual(statebackup.verify(str(backup))["result"], "ok")

    def test_a_bundle_without_the_commit_refuses_and_leaves_nothing(self):
        for answer in (f"{'0' * 40} HEAD", "", OSError("git vanished")):
            with self.subTest(answer=answer), self.out_with({("bundle", "list-heads"): answer}):
                made = statebackup.create(str(self.repo.state), str(self.bk), now=STAMP)
            self.assertEqual(made, {"result": "refused", "problems": ["content bundle does not hold contentCommit"]})
            self.assertEqual(os.listdir(self.bk), [])

    def test_changed_bundle_bytes_are_a_hash_mismatch(self):
        backup, _ = self.make()
        with open(backup / BUNDLE, "r+b") as fh:
            fh.seek(-1, os.SEEK_END)
            last = fh.read(1)
            fh.seek(-1, os.SEEK_END)
            fh.write(bytes([last[0] ^ 1]))
        self.assertEqual(statebackup.verify(str(backup)), {"result": "corrupt", "problems": [f"hash mismatch: {BUNDLE}"]})

    def test_a_valid_bundle_of_another_commit_is_refused(self):
        backup, _ = self.make()
        git(self.repo.wt, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "--allow-empty", "-q",
            "-m", "later")
        other = self.tmp / "other.bundle"
        git(self.repo.wt, "bundle", "create", str(other), "HEAD")
        (backup / BUNDLE).write_bytes(other.read_bytes())
        doc = self.doc(backup)
        doc["files"][BUNDLE] = hashlib.sha256(other.read_bytes()).hexdigest()
        self.write_doc(backup, doc)
        self.assertEqual(statebackup.verify(str(backup)),
                         {"result": "corrupt", "problems": ["content bundle: head is not contentCommit"]})
        del doc["contentCommit"]  # listed, but nothing to check it against
        self.write_doc(backup, doc)
        self.assertEqual(statebackup.verify(str(backup)),
                         {"result": "corrupt", "problems": ["content bundle without contentCommit"]})

    def test_a_symlinked_bundle_is_named_and_never_read_by_git(self):
        backup, _ = self.make()
        real = self.tmp / "real.bundle"
        os.rename(backup / BUNDLE, real)
        os.symlink(real, backup / BUNDLE)
        with self.out_with({("bundle", "list-heads"): AssertionError("git ran on the symlink")}):
            got = statebackup.verify(str(backup))
        self.assertEqual(got, {"result": "corrupt", "problems": [f"symlink: {BUNDLE}", f"missing: {BUNDLE}"]})

    def test_restore_and_drill_leave_the_bundle_out(self):
        backup, made = self.make()
        head, listed = made["contentCommit"], self.doc(backup)["files"]
        new = self.tmp / "restored"
        got = statebackup.restore(str(backup), str(new), str(self.drill_wt))
        self.assertEqual(got, {"result": "ok", "state": str(new.resolve()), "worktree": str(self.drill_wt.resolve()),
                               "files": len(listed), "contentCommit": head})
        self.assertFalse(os.path.lexists(new / BUNDLE))
        self.assertEqual({p.name for p in new.iterdir() if p.is_file()},
                         {rel for rel in listed if "/" not in rel} - {BUNDLE})
        drilled = statebackup.drill(str(backup), str(self.tmp / "drilled"), str(self.drill_wt))
        self.assertEqual((drilled["result"], drilled["contentCommit"]), ("ok", head), drilled)
        self.assertFalse(os.path.lexists(self.tmp / "drilled" / BUNDLE))

    def test_create_leaves_the_writer_worktree_untouched(self):
        status = git(self.repo.wt, "status", "--porcelain")
        os.utime(self.repo.wt / PHOTO)  # stat-dirty: a refreshing git call would rewrite the index
        index = Path(self.repo.wt, git(self.repo.wt, "rev-parse", "--git-path", "index"))
        before = (os.stat(index).st_mtime_ns, git(self.repo.wt, "rev-parse", "HEAD"))
        self.make()
        self.assertEqual((os.stat(index).st_mtime_ns, git(self.repo.wt, "rev-parse", "HEAD")), before)
        self.assertEqual(git(self.repo.wt, "status", "--porcelain"), status)
