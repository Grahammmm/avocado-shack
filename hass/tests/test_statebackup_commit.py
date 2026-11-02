"""AVB-16 tests: a backup's MANIFEST.json records the writer worktree's content commit (`contentCommit`, optional).

Temp git repo + temp state dir from test_statebackup; nothing live. Old manifests (no key) stay valid.
"""

import json, os  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import statebackup
from hass.tests.test_editor import git
from hass.tests.test_statebackup import STAMP, BackupTestCase

BAD = f"{statebackup.MANIFEST} missing or invalid"

class ContentCommitTests(BackupTestCase):
    def make(self, minute=0):
        made = statebackup.create(str(self.repo.state), str(self.bk), now=STAMP + timedelta(minutes=minute))
        self.assertEqual(made["result"], "ok", made)
        return Path(made["backup"]), made

    def doc(self, backup):
        return json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))

    def edit(self, backup, **changes):  # hand-edit the manifest (it carries no digest of itself)
        doc = self.doc(backup)
        for key, value in changes.items():
            if value is KeyError: doc.pop(key, None)
            else: doc[key] = value
        (backup / statebackup.MANIFEST).write_text(json.dumps(doc, indent=2, sort_keys=True), "utf-8")

    def row(self, backup):
        [row] = [r for r in statebackup.list_backups(str(self.bk)) if r["backup"] == backup.name]
        return row

    def test_manifest_and_result_carry_the_writer_head_and_verify_is_ok(self):
        backup, made = self.make()
        head = git(self.repo.wt, "rev-parse", "HEAD")
        self.assertRegex(head, r"[0-9a-f]{40}")
        self.assertEqual((self.doc(backup)["contentCommit"], made["contentCommit"]), (head, head))
        self.assertEqual(statebackup.verify(str(backup)), {"result": "ok", "files": made["files"]})
        self.assertEqual(self.row(backup)["contentCommit"], head)

    def head_is(self, value):  # only `rev-parse HEAD` answers differently; every other git call is real
        real = statebackup.editor._out
        def out(wt, *args):
            if args != ("rev-parse", "HEAD"): return real(wt, *args)
            if isinstance(value, Exception): raise value
            return value
        return mock.patch.object(statebackup.editor, "_out", side_effect=out)

    def test_a_failing_git_call_still_backs_up_without_the_key(self):
        cases = [("empty output", ""), ("not 40 hex", "HEAD"), ("upper case", "A" * 40), ("git missing", OSError("no git"))]
        for minute, (name, value) in enumerate(cases):
            with self.subTest(name):
                with self.head_is(value):
                    backup, made = self.make(minute=minute)
                self.assertNotIn("contentCommit", self.doc(backup))
                self.assertIsNone(made["contentCommit"])
                self.assertEqual(statebackup.verify(str(backup))["result"], "ok")
                self.assertIsNone(self.row(backup)["contentCommit"])

    def test_a_malformed_recorded_commit_makes_the_manifest_invalid(self):
        backup, _ = self.make()
        good = git(self.repo.wt, "rev-parse", "HEAD")
        for bad in ("xyz", good[:39], good + "0", good.upper(), "", 123, None, [good]):
            with self.subTest(bad=bad):
                self.edit(backup, contentCommit=bad)
                self.assertEqual(statebackup.verify(str(backup)), {"result": "corrupt", "problems": [BAD]})
                row = self.row(backup)
                self.assertEqual((row["complete"], row["problem"], row["contentCommit"]),
                                 (False, "manifest invalid", None))

    def test_an_old_manifest_without_the_key_stays_valid(self):
        old, _ = self.make()
        new, _ = self.make(minute=1)
        self.edit(old, contentCommit=KeyError)
        self.assertEqual(statebackup.verify(str(old))["result"], "ok")
        row = self.row(old)
        self.assertEqual((row["complete"], row["contentCommit"]), (True, None))
        for pair in ((old, new), (new, old)):
            self.assertIsNone(statebackup.diff(*map(str, pair))["content_commit_changed"])

    def test_diff_reports_whether_the_content_commit_changed(self):
        first, _ = self.make()
        same, _ = self.make(minute=1)
        git(self.repo.wt, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "--allow-empty",
            "-q", "-m", "next")
        later, made = self.make(minute=2)
        self.assertEqual(made["contentCommit"], git(self.repo.wt, "rev-parse", "HEAD"))
        self.assertIs(statebackup.diff(str(first), str(same))["content_commit_changed"], False)
        self.assertIs(statebackup.diff(str(same), str(later))["content_commit_changed"], True)
        self.assertIs(statebackup.diff(str(later), str(first))["content_commit_changed"], True)

    def test_git_runs_with_optional_locks_off_and_the_env_is_restored(self):
        seen, real = [], statebackup.editor._out
        def spy(wt, *args):
            if args == ("rev-parse", "HEAD"): seen.append(os.environ.get("GIT_OPTIONAL_LOCKS"))
            return real(wt, *args)
        for before in (None, "1"):
            with mock.patch.dict(os.environ, {} if before is None else {"GIT_OPTIONAL_LOCKS": before}):
                if before is None: os.environ.pop("GIT_OPTIONAL_LOCKS", None)
                with mock.patch.object(statebackup.editor, "_out", side_effect=spy):
                    self.make(minute=30 if before is None else 31)
                self.assertEqual(os.environ.get("GIT_OPTIONAL_LOCKS"), before)
        self.assertEqual(seen, ["0", "0"])

    def test_drill_carries_the_commit_and_runs_no_git_write(self):
        backup, made = self.make()
        head, status = git(self.repo.wt, "rev-parse", "HEAD"), git(self.repo.wt, "status", "--porcelain")
        heads = {wt: git(wt, "rev-parse", "HEAD") for wt in (self.repo.main, self.drill_wt)}
        got = statebackup.drill(str(backup), str(self.tmp / "restored"), str(self.drill_wt))
        self.assertEqual(got["contentCommit"], head, got)
        self.assertEqual(statebackup.restore(str(backup), str(self.tmp / "again"), str(self.drill_wt))["contentCommit"], head)
        self.assertEqual((git(self.repo.wt, "rev-parse", "HEAD"), git(self.repo.wt, "status", "--porcelain")), (head, status))
        self.assertEqual({wt: git(wt, "rev-parse", "HEAD") for wt in heads}, heads)
        self.edit(backup, contentCommit=KeyError)  # an old backup drills with a null commit
        self.assertIsNone(statebackup.drill(str(backup), str(self.tmp / "third"), str(self.drill_wt))["contentCommit"])
