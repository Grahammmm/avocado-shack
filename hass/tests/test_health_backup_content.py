"""AV1322-15 tests: health --backups adds one info entry `backup-content` when the newest complete backup it already picks
lists no content bundle (FAV-07). Temp dirs and hand-written manifests only; never the real private state."""
import contextlib, io, json, os, shutil, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import health, statebackup
from hass.tests import test_health as th

ENTRY = {"check": "backup-content", "detail": "content restores from Git only"}
HEX, NOW = "0" * 64, th.NOW


class BackupContentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.state, self.backups = self.tmp / "state", self.tmp / "backups"
        self.state.mkdir(mode=0o700)
        (self.state / "config.json").write_text(json.dumps({"worktree": str(self.tmp / "wt"), "settings": th.SETTINGS}))
        self.backups.mkdir()

    def run_health(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = health.main(["--state", str(self.state), *extra], now=NOW)
        [line] = out.getvalue().splitlines()
        return code, json.loads(line)

    def backup(self, hours, bundle, manifest=None):
        bdir = self.backups / (NOW - timedelta(hours=hours)).strftime(health.STAMP)
        bdir.mkdir()
        files = {statebackup.CONFIG: HEX} | ({statebackup.BUNDLE: HEX} if bundle else {})
        doc = {"schemaVersion": 1, "worktree": str(self.tmp / "wt"), "files": files}
        (bdir / statebackup.MANIFEST).write_text(json.dumps(doc) if manifest is None else manifest, "utf-8")
        return bdir

    def run_backups(self, *extra):
        with mock.patch.object(health.statebackup, "verify", return_value={"result": "ok", "files": 1}):
            return self.run_health("--backups", str(self.backups), *extra)

    def content(self, doc):
        return [i for i in doc["info"] if i["check"] == "backup-content"]

    def test_newest_with_bundle_has_no_entry_and_without_has_exactly_one(self):
        self.backup(2, bundle=True)
        code, doc = self.run_backups()
        self.assertEqual((code, doc["ok"], self.content(doc)), (0, True, []))
        self.backup(1, bundle=False)  # now the newest
        code, with_info = self.run_backups()
        self.assertEqual((code, with_info["ok"], with_info["problems"], with_info["notify"]), (0, True, [], False))
        self.assertEqual(self.content(with_info), [ENTRY])
        self.assertEqual(with_info["fingerprint"], doc["fingerprint"])  # info never enters the fingerprint

    def test_an_older_backup_without_bundle_never_raises_it(self):
        self.backup(20, bundle=False)
        self.backup(3, bundle=False)
        self.backup(1, bundle=True)
        self.assertEqual(self.content(self.run_backups()[1]), [])

    def test_unreadable_manifest_adds_nothing_and_backup_verify_is_unchanged(self):
        for name, manifest in (("not json", "{"), ("no files", "{}"), ("files not a dict", '{"files": []}')):
            with self.subTest(name):
                bdir = self.backup(1, bundle=False, manifest=manifest)
                code, doc = self.run_health("--backups", str(self.backups))  # the real verify
                self.assertEqual((code, doc["problems"]),
                                 (1, [{"check": "backup-verify", "detail": "1 problem(s)"}]))
                self.assertEqual(self.content(doc), [])
                os.remove(bdir / statebackup.MANIFEST)
                os.rmdir(bdir)

    def test_no_backup_or_too_old_gives_only_backup_age(self):
        self.backups.rmdir()
        code, doc = self.run_backups()
        self.assertEqual((code, doc["problems"], self.content(doc)),
                         (1, [{"check": "backup-age", "detail": "backup dir unreadable"}], []))
        self.backups.mkdir()
        self.assertEqual(self.run_backups()[1]["problems"], [{"check": "backup-age", "detail": "no complete backup"}])
        self.backup(27, bundle=False)
        code, doc = self.run_backups()
        self.assertEqual((code, doc["problems"], self.content(doc)),
                         (1, [{"check": "backup-age", "detail": "newest complete backup older than 26 h"}], []))

    def test_detail_is_the_fixed_words_without_path_or_commit(self):
        bdir = self.backup(1, bundle=False)
        doc = json.loads((bdir / statebackup.MANIFEST).read_text("utf-8"))
        (bdir / statebackup.MANIFEST).write_text(json.dumps(doc | {"contentCommit": "a" * 40}), "utf-8")
        [entry] = self.content(self.run_backups()[1])
        self.assertEqual(entry["detail"], "content restores from Git only")
        for leak in (bdir.name, str(self.backups), statebackup.MANIFEST, "a" * 40, "content.bundle"):
            self.assertNotIn(leak, json.dumps(entry))
