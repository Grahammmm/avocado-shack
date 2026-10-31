"""H20 prep tests: private state backup, verify and an isolated restore drill.

H06 conversation setup (temp Git repo, linked writer worktree, private 0700 state dir, fake previewer, injected clock) plus
a second linked drill worktree of the same throwaway repo; every dir lives under the test's temp dir (no live state).
"""

import hashlib, json, os, shutil, subprocess, sys, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import conversation, editor, statebackup
from hass.content_model import REPO_ROOT
from hass.ops import load_registry
from hass.tests import fixture_ops
from hass.tests.test_conversation import CHAT, OWNER
from hass.tests.test_editor import git
from hass.tests.test_undo import H06TestCase

SCRIPT = REPO_ROOT / "hass" / "statebackup.py"
PRIVATE = (OWNER, CHAT, "kumquat")  # owner sender, chat id and owner message text from the fixture
STAMP = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)

def tree(root):
    """relpath -> sha256 / symlink target / None (dir) for everything under root, symlinks never followed."""
    out = {}
    for dirpath, dirs, names in os.walk(root):
        for name in dirs + names:
            path = Path(dirpath, name)
            rel = str(path.relative_to(root))
            out[rel] = "->" + os.readlink(path) if path.is_symlink() else None if path.is_dir() else \
                hashlib.sha256(path.read_bytes()).hexdigest()
    return out

class BackupTestCase(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping.update({"kumquat desc": self.interp.mapping["desc"],
                                    "kumquat hours": self.interp.mapping["hours"]})
        self.tmp = self.repo.state.parent
        self.bk = self.tmp / "backups"
        self.bk.mkdir(mode=0o700)
        self.drill_wt = self.tmp / "drill"
        git(self.repo.main, "worktree", "add", "-q", "-b", "hass/drill", str(self.drill_wt))

    def drill(self):
        """Two changes and one undo through the conversation; returns the owner's `history` reply."""
        a = self.apply("kumquat desc")
        self.apply("kumquat hours")
        self.assertEqual(self.say(f"undo {a['code']}"), "proposed")
        self.sent()
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        self.assertEqual(self.say("history"), "history")
        return self.replies()[0]

    def backup(self):
        made = statebackup.create(str(self.repo.state), str(self.bk))
        self.assertEqual(made["result"], "ok", made)
        return Path(made["backup"])

    def files(self, backup):
        return json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))["files"]

class DrillTests(BackupTestCase):
    def test_drill_restores_into_a_new_state_dir(self):
        text, state = self.drill(), self.repo.state
        before = (tree(state), tree(self.repo.wt), self.count())
        backup = self.backup()
        self.assertTrue(backup.name.startswith("hass-state-") and backup.name.endswith("Z"), backup.name)
        self.assertEqual(statebackup.verify(str(backup))["result"], "ok")
        new = self.tmp / "restored"
        self.assertEqual(statebackup.restore(str(backup), str(new), str(self.drill_wt))["result"], "ok")
        listed = self.files(backup)
        self.assertNotIn("writer.lock", listed)
        for prefix in ("config.json", "conversation.sqlite3", "drafts/", "changes/", "screenshots/"):
            self.assertTrue(any(rel.startswith(prefix) for rel in listed), prefix)
        for rel in listed:
            if rel != "config.json":
                self.assertEqual((new / rel).read_bytes(), (backup / rel).read_bytes(), rel)
        old_cfg = json.loads((state / "config.json").read_text("utf-8"))
        self.assertEqual(json.loads((new / "config.json").read_text("utf-8")),
                         {**old_cfg, "worktree": str(self.drill_wt.resolve())})
        self.assertEqual(set(tree(new)), set(listed) | {"drafts", "changes", "screenshots"})
        for path in [new, *new.rglob("*")]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600, path)
        self.assertEqual((tree(state), tree(self.repo.wt), self.count()), before)
        old, restored = editor.history(state=str(state)), editor.history(state=str(new))
        self.assertEqual((len(old["history"]), restored), (3, old))
        for row in self.drafts():
            self.assertEqual(editor.show(row["change_id"], state=str(new)),
                             editor.show(row["change_id"], state=str(state)))
        ed = conversation.Editor(new, {**fixture_ops.registry(), **load_registry()})
        self.conv = conversation.Conversation(str(new), ed, self.interp, lambda: self.now, self.previewer)
        self.assertEqual(self.say("history"), "history")
        self.assertEqual(self.replies(), [text])

class CreateRefusalTests(BackupTestCase):
    def test_refusals_leave_out_without_a_new_entry(self):
        self.apply("kumquat desc")
        state = self.repo.state
        with editor._writer_lock(state) as held:
            self.assertTrue(held)
            self.assertEqual(statebackup.create(str(state), str(self.bk)), {"result": "busy"})
        (state / "journal").mkdir(mode=0o700, exist_ok=True)
        outside_cfg, outside_lock = self.tmp / "outside.json", self.tmp / "outside.lock"  # lock target never exists
        shutil.copy(state / "config.json", outside_cfg)
        cases = (("journal/chg-000000000000.json", None, "unsettled", None),
                 ("drafts/x.json", "/etc/hostname", "refused", "symlink: drafts/x.json"),
                 ("notes.txt", None, "refused", "unknown entry: notes.txt"),
                 ("drafts/notes.txt", None, "refused", "unknown entry: drafts/notes.txt"),
                 ("config.json", outside_cfg, "refused", "symlink: config.json"),
                 ("writer.lock", outside_lock, "refused", "symlink: writer.lock"))
        for rel, link, result, problem in cases:
            with self.subTest(rel=rel), mock.patch.object(editor, "_read", wraps=editor._read) as read:
                path, aside = state / rel, self.tmp / "aside"
                if path.exists(): path.rename(aside)
                path.symlink_to(link) if link else path.write_text("{}", "utf-8")
                got = statebackup.create(str(state), str(self.bk))
                self.assertEqual(got["result"], result, got)
                if problem: self.assertIn(problem, got["problems"])
                if rel in ("config.json", "writer.lock"):  # never read through, never created through
                    self.assertEqual((read.call_count, outside_lock.exists()), (0, False))
                self.assertEqual(os.listdir(self.bk), [])
                path.unlink()
                if aside.exists(): aside.rename(path)
        made = statebackup.create(str(state), str(self.bk), now=STAMP)
        self.assertEqual(made["result"], "ok")
        kept = tree(self.bk)
        self.assertEqual(statebackup.create(str(state), str(self.bk), now=STAMP)["result"], "exists")
        self.assertEqual(tree(self.bk), kept)

    def test_unsafe_out_dirs_exit_2(self):
        loose, owner = self.tmp / "loose", self.tmp / "owner-0500"
        for path, mode in ((loose, 0o755), (owner, 0o500)):
            path.mkdir(mode=0o700)
            os.chmod(path, mode)
        cases = {"missing": self.tmp / "missing", "mode 0755": loose, "mode 0500": owner,
                 "inside the repo": self.repo.main / "bk", "inside the writer worktree": self.repo.wt / "bk",
                 "inside the state dir": self.repo.state / "bk"}
        for name, out in cases.items():
            with self.subTest(name):
                if name != "missing" and not out.exists(): out.mkdir(mode=0o700)
                run = subprocess.run([sys.executable, str(SCRIPT), "create", "--state", str(self.repo.state),
                                      "--out", str(out)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
                self.assertEqual(json.loads(run.stdout)["result"], "unsafe-state")
                self.assertEqual(os.listdir(out) if out.exists() else None, [] if name != "missing" else None)

class VerifyTests(BackupTestCase):
    def test_damage_is_named(self):
        self.drill()
        backup = self.backup()
        files = self.files(backup)
        draft = next(rel for rel in files if rel.startswith("drafts/"))
        shot = next(rel for rel in files if rel.startswith("screenshots/"))

        def flip(b):
            data = bytearray((b / draft).read_bytes())
            data[len(data) // 2] ^= 1
            (b / draft).write_bytes(bytes(data))

        def truncate(b):
            db, manifest = b / "conversation.sqlite3", b / statebackup.MANIFEST
            db.write_bytes(db.read_bytes()[:db.stat().st_size // 2])
            doc = json.loads(manifest.read_text("utf-8"))
            doc["files"]["conversation.sqlite3"] = hashlib.sha256(db.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(doc), "utf-8")

        cases = {"changed byte": (flip, f"hash mismatch: {draft}"),
                 "deleted screenshot": (lambda b: (b / shot).unlink(), f"missing: {shot}"),
                 "extra file": (lambda b: statebackup._write_new(b / "extra.txt", b"x"), "unlisted: extra.txt"),
                 "symlink": (lambda b: (b / "drafts" / "y.json").symlink_to("/etc/hostname"), "symlink: drafts/y.json"),
                 "no manifest": (lambda b: (b / statebackup.MANIFEST).unlink(), "MANIFEST.json missing or invalid"),
                 "truncated store": (truncate, "integrity check failed: conversation.sqlite3")}
        for i, (name, (damage, problem)) in enumerate(cases.items()):
            with self.subTest(name):
                copy = self.bk / f"copy-{i}"
                shutil.copytree(backup, copy, symlinks=True)
                self.assertEqual(statebackup.verify(str(copy))["result"], "ok")
                damage(copy)
                got = statebackup.verify(str(copy))
                self.assertEqual(got["result"], "corrupt")
                self.assertIn(problem, got["problems"])
        self.assertEqual(statebackup.verify(str(backup))["result"], "ok")  # the untouched backup still verifies

class RestoreRefusalTests(BackupTestCase):
    def test_refusals_leave_into_absent_or_untouched(self):
        self.apply("kumquat desc")
        backup = self.backup()
        shutil.copytree(backup, bad := self.bk / "bad")
        (bad / statebackup.MANIFEST).unlink()
        plain, link = self.tmp / "plain", self.tmp / "writer-link"
        plain.mkdir()
        link.symlink_to(self.repo.wt, target_is_directory=True)
        into = self.tmp / "restored"
        cases = {"corrupt": (bad, self.drill_wt, "corrupt"), "recorded worktree": (backup, self.repo.wt, "refused"),
                 "recorded worktree via a symlink": (backup, link, "refused"),
                 "recorded worktree with dot segments": (backup, f"{self.repo.wt}/./", "refused"),
                 "main checkout": (backup, self.repo.main, "refused"), "plain dir": (backup, plain, "refused"),
                 "missing worktree": (backup, self.tmp / "nowhere", "refused")}
        names = sorted(os.listdir(self.tmp))
        for name, (src, wt, result) in cases.items():
            with self.subTest(name):
                got = statebackup.restore(str(src), str(into), str(wt))
                self.assertEqual(got["result"], result, got)
                if "recorded" in name: self.assertEqual(got["problems"], [statebackup.ATTENDED])
                self.assertEqual(sorted(os.listdir(self.tmp)), names)
        with self.assertRaises(editor.UnsafeState):  # a restore dir inside a worktree
            statebackup.restore(str(backup), str(self.drill_wt / "state"), str(self.drill_wt))
        empty, full, dangling = self.tmp / "empty", self.tmp / "full", self.tmp / "dangling"
        empty.mkdir(mode=0o700)
        full.mkdir(mode=0o700)
        (full / "config.json").write_text("{}", "utf-8")
        dangling.symlink_to(self.tmp / "nothing-here")
        for existing in (empty, full, dangling):
            with self.subTest(into=existing.name):
                kept = tree(existing) if existing.is_dir() else os.readlink(existing)
                got = statebackup.restore(str(backup), str(existing), str(self.drill_wt))
                self.assertEqual(got["result"], "refused")
                self.assertEqual(tree(existing) if existing.is_dir() else os.readlink(existing), kept)
        self.assertEqual(statebackup.restore(str(backup), str(into), str(self.drill_wt))["result"], "ok")
        kept = tree(into)
        self.assertEqual(statebackup.restore(str(backup), str(into), str(self.drill_wt))["result"], "refused")
        self.assertEqual(tree(into), kept)

    def test_copy_failure_leaves_no_into_and_no_temp_dir(self):
        self.apply("kumquat desc")
        backup, into = self.backup(), self.tmp / "restored"
        names = sorted(os.listdir(self.tmp))
        with mock.patch.object(statebackup, "_copy", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                statebackup.restore(str(backup), str(into), str(self.drill_wt))
        self.assertEqual(sorted(os.listdir(self.tmp)), names)

class CliTests(BackupTestCase):
    def test_cli_drill_and_exit_codes_without_private_text(self):
        self.drill()
        runs = []

        def cli(code, *args):
            run = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)
            runs.append(run)
            self.assertEqual(run.returncode, code, run.stdout + run.stderr)
            [line] = run.stdout.splitlines()
            return json.loads(line)

        backup = cli(0, "create", "--state", self.repo.state, "--out", self.bk)["backup"]
        self.assertEqual(cli(0, "verify", backup)["result"], "ok")
        new = self.tmp / "restored"
        self.assertEqual(cli(0, "restore", backup, "--into", new, "--worktree", self.drill_wt)["result"], "ok")
        self.assertEqual(editor.history(state=str(new)), editor.history(state=str(self.repo.state)))
        shutil.copytree(backup, bad := self.bk / "bad")
        (bad / "config.json").write_text("{}", "utf-8")
        self.assertEqual(cli(1, "verify", bad)["problems"], ["hash mismatch: config.json"])
        self.assertEqual(cli(1, "restore", bad, "--into", self.tmp / "again", "--worktree", self.drill_wt)["result"],
                         "corrupt")
        os.chmod(self.repo.state, 0o755)
        try:
            self.assertEqual(cli(2, "create", "--state", self.repo.state, "--out", self.bk)["result"], "unsafe-state")
        finally:
            os.chmod(self.repo.state, 0o700)
        cli(2, "create", "--state", self.tmp / "no-state", "--out", self.bk)
        self.assertFalse((self.tmp / "no-state").exists() or (self.tmp / "again").exists())
        for run in runs:
            for private in PRIVATE:
                self.assertNotIn(private, run.stdout + run.stderr)

if __name__ == "__main__":
    unittest.main()
