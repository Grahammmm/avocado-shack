"""RF1058-9 (H19/H20): health.py --backups also runs statebackup.verify on the newest complete backup in the window.

Temp 0700 dirs outside the repo, backups in statebackup.create's layout (0700 dir, 0600 files, v1 MANIFEST), fixed now.
"""
import contextlib, hashlib, io, json, os, shutil, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import health, statebackup
from hass.tests.test_health import NOW, SETTINGS

class BackupVerifyHealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.bk = self.tmp / "state", self.tmp / "backups"
        for path in (self.state, self.bk): path.mkdir(mode=0o700)
        self.config(SETTINGS)

    def config(self, settings):
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": settings}))

    def backup(self, hours_ago):
        dest = self.bk / (NOW - timedelta(hours=hours_ago)).strftime(health.STAMP)
        dest.mkdir(mode=0o700)
        (dest / "config.json").write_bytes(data := (self.state / "config.json").read_bytes())
        doc = {"schemaVersion": 1, "createdAt": NOW.isoformat(), "worktree": str(self.tmp / "wt"),
               "files": {"config.json": hashlib.sha256(data).hexdigest()}}
        (dest / "MANIFEST.json").write_text(json.dumps(doc))
        for path in (dest, dest / "config.json", dest / "MANIFEST.json"):
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        self.assertEqual(statebackup.verify(dest)["result"], "ok")  # the fixture is a real good backup
        return dest

    def damage(self, dest):
        raw = bytearray((dest / "config.json").read_bytes())
        raw[0] ^= 1
        (dest / "config.json").write_bytes(bytes(raw))

    def run_health(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state), "--backups", str(self.bk), *extra], now=NOW)
        [line] = out.getvalue().splitlines()
        return code, json.loads(line)

    def tree(self):
        return {str(p): (p.read_bytes() if p.is_file() else None, p.stat().st_mtime_ns, p.stat().st_mode)
                for root in (self.state, self.bk) for p in sorted(root.rglob("*"))}

    def test_fresh_good_backup_output_unchanged(self):
        self.backup(2)
        code, doc = self.run_health()
        self.assertEqual((code, doc), (0, {"ok": True, "problems": [], "notify": False,
                                           "info": [{"check": "conversation", "detail": "no conversation yet"},
                                                    {"check": "backup-content",
                                                     "detail": "content restores from Git only"}],
                                           "fingerprint": health.fingerprint([])}))

    def test_hash_damaged_newest_gives_count_only(self):
        self.damage(self.backup(2))
        code, doc = self.run_health()
        self.assertEqual((code, doc["problems"]), (1, [{"check": "backup-verify", "detail": "1 problem(s)"}]))
        self.assertNotIn("config.json", json.dumps(doc))

    def test_mode_change_and_damaged_manifest(self):
        os.chmod(self.backup(2) / "config.json", 0o644)
        self.assertEqual(self.run_health()[1]["problems"], [{"check": "backup-verify", "detail": "1 problem(s)"}])
        (self.backup(1) / "MANIFEST.json").write_text("{}")  # newer, manifest unreadable: corrupt, not skipped
        self.assertEqual(self.run_health()[1]["problems"], [{"check": "backup-verify", "detail": "1 problem(s)"}])

    def test_only_newest_is_judged_read_only(self):
        self.backup(5)
        self.damage(self.backup(2))
        before = self.tree()
        self.assertEqual(self.run_health()[1]["problems"], [{"check": "backup-verify", "detail": "1 problem(s)"}])
        self.assertEqual(self.tree(), before)  # bytes, mtimes and modes; no file created in state or backups
        self.backup(1)  # a newer good one over the corrupt one: healthy
        self.assertEqual(self.run_health()[0], 0)

    def test_old_or_missing_backup_is_age_only_without_verify(self):
        with mock.patch.object(health.statebackup, "verify") as verify:
            self.assertEqual(self.run_health()[1]["problems"], [health._problem("backup-age", "no complete backup")])
            (self.bk / (NOW - timedelta(hours=1)).strftime(health.STAMP)).mkdir()  # no MANIFEST: incomplete
            self.assertEqual(self.run_health()[1]["problems"][0]["detail"], "no complete backup")
            verify.assert_not_called()
        self.damage(self.backup(27))
        with mock.patch.object(health.statebackup, "verify") as verify:
            self.assertEqual(self.run_health()[1]["problems"],
                             [{"check": "backup-age", "detail": "newest complete backup older than 26 h"}])
            verify.assert_not_called()
        self.assertEqual(self.run_health("--backup-hours", "28")[1]["problems"][0]["check"], "backup-verify")

    def test_verify_error_is_reported_without_traceback(self):
        self.backup(2)
        self.config({})  # a settings problem too: other checks still reported
        for exc in (OSError("boom"), sqlite3.DatabaseError("boom")):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(health.statebackup, "verify", side_effect=exc):
                with contextlib.redirect_stderr(err := io.StringIO()):
                    code, doc = self.run_health()
                self.assertEqual((code, err.getvalue()), (1, ""))
                self.assertEqual([p["check"] for p in doc["problems"]], ["settings", "backup-verify"])
                self.assertEqual(doc["problems"][1]["detail"], "verify failed")
                self.assertNotIn("boom", json.dumps(doc))

    def test_fingerprint_notifies_once(self):
        good = self.backup(2)
        seen = self.tmp / "seen"
        seen.write_text(health.fingerprint([]) + "\n")
        self.assertFalse(self.run_health("--seen", str(seen))[1]["notify"])
        self.damage(good)
        code, doc = self.run_health("--seen", str(seen))
        self.assertEqual((code, doc["notify"], doc["problems"][0]["check"]), (1, True, "backup-verify"))
        self.assertFalse(self.run_health("--seen", str(seen))[1]["notify"])
