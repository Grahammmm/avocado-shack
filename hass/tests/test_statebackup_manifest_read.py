"""RF1920-3 (H19/H20): statebackup reads MANIFEST.json, media sidecars and config.json only as regular files up to a cap.

A FIFO named MANIFEST.json used to block open() forever (verify, list, diff, restore, drill hung), and a manifest or
sidecar nested 100 000 deep raised RecursionError. Each command here must answer within 5 s with no traceback.
Backups are made with statebackup.create on test_statebackup's throwaway repo (no live state).
"""

import contextlib, hashlib, io, json, os, shutil, signal, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import editor, media, statebackup
from hass.tests.test_media import AT, JPEG, PNG
from hass.tests.test_editor import git
from hass.tests.test_statebackup import STAMP, BackupTestCase

BAD = f"{statebackup.MANIFEST} missing or invalid"
DEEP = b"[" * 100000

class Hung(Exception):  # not an OSError: a blocked open() must never pass as "missing or invalid"
    pass

@contextlib.contextmanager
def within(seconds=5):
    def late(*_): raise Hung(f"statebackup did not return within {seconds} s")
    old = signal.signal(signal.SIGALRM, late)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)

@unittest.skipUnless(hasattr(signal, "setitimer"), "needs SIGALRM timers")
class ManifestReadTests(BackupTestCase):
    def make(self, minute=0, **kw):
        made = statebackup.create(str(self.repo.state), str(self.bk), now=STAMP + timedelta(minutes=minute), **kw)
        self.assertEqual(made["result"], "ok", made)
        return Path(made["backup"])

    def cli(self, *argv):  # (exit code, JSON lines): in process, under the 5 s alarm, nothing on stderr
        out, err = io.StringIO(), io.StringIO()
        with within(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = statebackup.main([str(a) for a in argv])
        self.assertEqual(err.getvalue(), "")
        return code, [json.loads(line) for line in out.getvalue().splitlines()]

    def rehash(self, backup, rel, data):  # a tamperer who also fixes the manifest digest
        (backup / rel).write_bytes(data)
        doc = json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))
        doc["files"][rel] = hashlib.sha256(data).hexdigest()
        (backup / statebackup.MANIFEST).write_text(json.dumps(doc, indent=2, sort_keys=True), "utf-8")

    def assert_invalid(self, backup, good):  # every read-only command, plus restore and drill, refuses promptly
        names, new = sorted(os.listdir(self.tmp)), self.tmp / "restored"
        self.assertEqual(self.cli("verify", backup), (1, [{"result": "corrupt", "problems": [BAD]}]))
        code, rows = self.cli("list", "--out", self.bk)
        self.assertEqual(code, 0)
        self.assertIn({"backup": backup.name, "createdAt": None, "files": None, "complete": False,
                       "problem": "manifest invalid", "contentCommit": None}, rows)
        self.assertEqual(self.cli("diff", backup, good), (1, [{"result": "corrupt", "problems": [f"OLD: {BAD}"]}]))
        self.assertEqual(self.cli("diff", good, backup), (1, [{"result": "corrupt", "problems": [f"NEW: {BAD}"]}]))
        self.assertEqual(self.cli("restore", backup, "--into", new, "--worktree", self.drill_wt),
                         (1, [{"result": "corrupt", "problems": [BAD]}]))
        self.assertEqual(self.cli("drill", backup, "--into", new, "--worktree", self.drill_wt),
                         (1, [{"result": "corrupt", "step": "verify", "problems": [BAD]}]))
        self.assertEqual(sorted(os.listdir(self.tmp)), names)  # no restore dir, no .restore- temp dir

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs os.mkfifo")
    def test_a_fifo_manifest_never_hangs_any_command(self):
        backup, good = self.make(), self.make(minute=1)
        (backup / statebackup.MANIFEST).unlink()
        os.mkfifo(backup / statebackup.MANIFEST, 0o600)
        self.assert_invalid(backup, good)

    def test_a_symlink_or_folder_manifest_is_missing_or_invalid(self):
        backup, good = self.make(), self.make(minute=1)
        manifest, copy = backup / statebackup.MANIFEST, self.tmp / "manifest-copy.json"
        shutil.copyfile(manifest, copy)
        manifest.unlink()
        manifest.symlink_to(copy)  # a valid manifest, reached only through a link: never followed
        self.assert_invalid(backup, good)
        manifest.unlink()
        manifest.mkdir(mode=0o700)
        self.assert_invalid(backup, good)

    def test_a_too_deep_manifest_is_invalid_not_a_recursion_error(self):
        backup, good = self.make(), self.make(minute=1)
        (backup / statebackup.MANIFEST).write_bytes(DEEP)
        self.assert_invalid(backup, good)
        (backup / statebackup.MANIFEST).write_bytes(b'{"files": ' * 100000)
        self.assert_invalid(backup, good)

    def test_the_manifest_cap_is_8_mib(self):
        backup, good = self.make(), self.make(minute=1)
        text = (backup / statebackup.MANIFEST).read_bytes()
        files = len(json.loads(text)["files"])
        (backup / statebackup.MANIFEST).write_bytes(text + b" " * (statebackup.MANIFEST_MAX - len(text)))
        self.assertEqual(self.cli("verify", backup), (0, [{"result": "ok", "files": files}]))  # exactly 8 MiB: read
        (backup / statebackup.MANIFEST).write_bytes(text + b" " * (statebackup.MANIFEST_MAX + 1 - len(text)))
        self.assertEqual(statebackup.MANIFEST_MAX, 8 * 1024 * 1024)
        self.assert_invalid(backup, good)

    def test_the_config_cap_matches_editor_one_mib(self):
        backup = self.make()
        cfg = json.loads((backup / statebackup.CONFIG).read_bytes())
        data = json.dumps(cfg).encode("utf-8")
        self.rehash(backup, statebackup.CONFIG, data + b" " * (editor.MAX_CONFIG - len(data)))
        self.assertEqual(self.cli("verify", backup)[1][0]["result"], "ok")
        self.rehash(backup, statebackup.CONFIG, data + b" " * (editor.MAX_CONFIG + 1 - len(data)))
        self.assertEqual(editor.MAX_CONFIG, 1024 * 1024)
        problem = {"result": "corrupt", "problems": ["config: not a JSON object with a worktree"]}
        self.assertEqual(self.cli("verify", backup), (1, [problem]))
        names = sorted(os.listdir(self.tmp))
        self.assertEqual(self.cli("restore", backup, "--into", self.tmp / "restored", "--worktree", self.drill_wt),
                         (1, [problem]))
        self.assertFalse(os.path.lexists(self.tmp / "restored"))
        self.assertEqual(sorted(os.listdir(self.tmp)), names)  # no staging output either

    def test_a_too_deep_or_too_big_sidecar_is_a_sidecar_mismatch(self):
        root = self.tmp / "media"
        root.mkdir(mode=0o700)
        sha = [media.store_original(root, data, received_at=AT, source="fixture")["sha256"] for data in (JPEG, PNG)][0]
        backup = self.make(media=str(root))
        prefix = f"{statebackup.ORIG}{sha[:2]}/{sha}."
        [orig] = [rel for rel in self.files(backup) if rel.startswith(prefix) and not rel.endswith(".json")]
        side = prefix + "json"
        good = json.loads((backup / side).read_bytes())
        self.assertEqual(self.cli("verify", backup)[1][0]["result"], "ok")
        big = json.dumps(good).encode("utf-8")
        big += b" " * (statebackup.SMALL_MAX + 1 - len(big))  # still names the right sha256, but over the cap
        for data in (DEEP, b'{"sha256": ' * 100000, big):
            with self.subTest(data=data[:12]):
                self.rehash(backup, side, data)
                (backup / statebackup.CONFIG).write_bytes(b"{}")  # another problem: still listed beside it
                self.assertEqual(self.cli("verify", backup), (1, [{"result": "corrupt", "problems": [
                    "hash mismatch: config.json", f"sidecar mismatch: {orig}"]}]))

    def test_a_good_backup_is_unchanged_and_create_never_uses_the_capped_read(self):
        with mock.patch.object(statebackup, "_read_small", side_effect=AssertionError("create used _read_small")):
            made = statebackup.create(str(self.repo.state), str(self.bk), now=STAMP)
        backup = Path(made["backup"])
        self.assertEqual(made, {"result": "ok", "backup": str(backup), "files": len(self.files(backup)),
                                "contentCommit": git(self.repo.wt, "rev-parse", "HEAD"), "contentBundle": True})
        self.assertEqual(self.cli("verify", backup), (0, [{"result": "ok", "files": len(self.files(backup))}]))
        with mock.patch.object(statebackup, "_read", side_effect=AssertionError("manifest read uncapped")):
            self.assertIsNotNone(statebackup._manifest(backup))
            self.assertTrue(statebackup._config_ok(backup / statebackup.CONFIG))
