"""H20 tests: `statebackup.py restore --paused` restores with changes paused (H17); fixture setup of test_statebackup."""

import contextlib, json, os, shutil, sqlite3, subprocess, sys, unittest  # noqa: E401
from datetime import timedelta
from unittest import mock

from hass import conversation, statebackup
from hass.ops import load_registry
from hass.tests import fixture_ops
from hass.tests.test_conversation import T0
from hass.tests.test_editor import git
from hass.tests.test_statebackup import SCRIPT, BackupTestCase, tree
from hass.tests.test_status_pause import gated

FIXED, ISO = T0 + timedelta(minutes=3), conversation._iso  # FIXED is 2026-11-02 09:03 PST

class PausedRestoreTests(BackupTestCase):
    def restored(self, new):  # talk to the restored state dir (bound to the drill worktree) from now on
        ed = conversation.Editor(new, {**fixture_ops.registry(), **load_registry()})
        self.conv = conversation.Conversation(str(new), ed, self.interp, lambda: self.now, self.previewer)

    def drill_commits(self): return int(git(self.drill_wt, "rev-list", "--count", "HEAD"))

    def query(self, new, sql="SELECT name, value, set_at, provider_id FROM control"):
        with contextlib.closing(sqlite3.connect(new / statebackup.DB)) as db:
            return db.execute(sql).fetchall()

    def setup_backups(self):  # (backup with a waiting draft, the same backup without conversation.sqlite3)
        self.draft = self.propose("kumquat desc")[0]
        shutil.copytree(backup := self.backup(), bare := self.bk / "bare")
        (bare / statebackup.DB).unlink()
        doc = json.loads((bare / statebackup.MANIFEST).read_text("utf-8"))
        (bare / statebackup.MANIFEST).write_text(json.dumps({**doc, "files": {
            rel: digest for rel, digest in doc["files"].items() if rel != statebackup.DB}}), "utf-8")
        self.assertEqual(statebackup.verify(str(bare))["result"], "ok")
        return backup, bare

    def test_paused_drill_gates_yes_until_resume(self):
        backup, new, base = self.setup_backups()[0], self.tmp / "restored", self.drill_commits()
        got = statebackup.restore(str(backup), str(new), str(self.drill_wt), paused=True, now=FIXED)
        self.assertEqual((got["result"], got["paused"], got["pausedSince"]), ("ok", True, ISO(FIXED)))
        self.assertEqual(self.query(new), [("paused", "1", ISO(FIXED), "statebackup-restore")])
        self.restored(new)
        self.assertEqual(self.say("status"), "status")
        self.assertEqual(self.replies()[0].splitlines()[0], "Changes: paused since 2026-11-02 09:03 PST")
        for text in (f"yes {self.draft['code']}", "yes"):
            self.assertEqual((self.say(text), self.replies()), ("paused", [gated(self.draft["code"])]), text)
            self.assertEqual((self.drill_commits(), self.drafts()[0]["state"]), (base, "proposed"))
        self.assertEqual((self.say("resume changes"), len(self.replies())), ("resume", 1))
        self.assertEqual(self.say(f"yes {self.draft['code']}"), "approved")
        self.assertEqual((self.drill_commits(), self.commits()), (base + 1, 0))  # the writer worktree never moves

    def test_already_paused_backup_keeps_its_time(self):
        self.assertEqual(self.say("pause changes", pid="p1"), "pause")
        backup, new = self.backup(), self.tmp / "restored"
        got = statebackup.restore(str(backup), str(new), str(self.drill_wt), paused=True, now=FIXED)
        self.assertEqual(got["pausedSince"], ISO(T0))
        self.assertEqual(self.query(new), [("paused", "1", ISO(T0), "p1")])  # exactly one row, the original

    def test_backup_without_store_and_default_unchanged(self):
        backup, bare = self.setup_backups()
        plain = statebackup.restore(str(bare), str(self.tmp / "plain"), str(self.drill_wt))
        self.assertEqual((plain["result"], (self.tmp / "plain" / statebackup.DB).exists()), ("ok", False))
        got = statebackup.restore(str(backup), str(self.tmp / "default"), str(self.drill_wt))
        self.assertEqual(set(got), {"result", "state", "worktree", "files", "contentCommit"})  # no paused key without the flag
        self.assertEqual((self.tmp / "default" / statebackup.DB).read_bytes(), (backup / statebackup.DB).read_bytes())
        got = statebackup.restore(str(bare), str(new := self.tmp / "restored"), str(self.drill_wt), paused=True, now=FIXED)
        self.assertEqual((got["paused"], (new / statebackup.DB).stat().st_mode & 0o777), (True, 0o600))
        self.assertEqual(self.query(new, "SELECT type, name FROM sqlite_master"),
                         [("table", "control"), ("index", "sqlite_autoindex_control_1")])  # only control
        self.restored(new)
        self.assertEqual(self.conv._paused(), ISO(FIXED))

    def test_failure_mid_pause_and_refusals_create_nothing(self):
        (backup, bare), into, real = self.setup_backups(), self.tmp / "restored", sqlite3.connect
        names = sorted(os.listdir(self.tmp))
        def connect(path, *args, **kwargs):  # only the restore temp dir's store fails
            if ".restore-" in str(path): raise sqlite3.OperationalError("disk I/O error")
            return real(path, *args, **kwargs)
        for src in (backup, bare):
            with self.subTest(src=src.name), mock.patch.object(statebackup.sqlite3, "connect", connect):
                with self.assertRaises(sqlite3.OperationalError):
                    statebackup.restore(str(src), str(into), str(self.drill_wt), paused=True)
                self.assertEqual(sorted(os.listdir(self.tmp)), names)
        shutil.copytree(backup, bad := self.bk / "bad")
        (bad / "config.json").write_text("{}", "utf-8")
        (taken := self.tmp / "taken").mkdir(mode=0o700)
        names = sorted(os.listdir(self.tmp))
        for src, dest, wt, result in ((bad, into, self.drill_wt, "corrupt"), (backup, taken, self.drill_wt, "refused"),
                                      (backup, into, self.repo.wt, "refused")):
            with self.subTest(result=result, dest=dest.name, wt=wt.name):
                plain = statebackup.restore(str(src), str(dest), str(wt))
                self.assertEqual((statebackup.restore(str(src), str(dest), str(wt), paused=True), plain["result"]),
                                 (plain, result))
                self.assertEqual((sorted(os.listdir(self.tmp)), os.listdir(taken)), (names, []))

    def test_cli_paused_restore(self):
        backup, new = self.setup_backups()[0], self.tmp / "restored"
        run = subprocess.run([sys.executable, str(SCRIPT), "restore", str(backup), "--into", str(new),
                              "--worktree", str(self.drill_wt), "--paused"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        [line] = run.stdout.splitlines()
        self.assertEqual((json.loads(line)["result"], json.loads(line)["paused"]), ("ok", True))
        for path in [new, *new.rglob("*")]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600, path)
        listed = set(self.files(backup))
        self.assertEqual(set(tree(new)), listed | {rel.split("/")[0] for rel in listed if "/" in rel})  # no journal
        bad = subprocess.run([sys.executable, str(SCRIPT), "verify", str(backup), "--paused"], capture_output=True)
        self.assertEqual(bad.returncode, 2)  # --paused belongs to restore only
