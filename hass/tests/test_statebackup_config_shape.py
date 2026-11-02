"""RF0110-1 (H20): verify calls a backup corrupt when its listed config.json is not a JSON object naming a worktree.

restore merges config.json as a dict and rewrites its `worktree`; a correctly hashed `[1]` or non-UTF-8 config used to pass
verify and crash restore/drill with a traceback. Fixtures come from test_statebackup (throwaway repo, no live state).
"""

import contextlib, hashlib, io, json, os  # noqa: E401

from hass import statebackup
from hass.tests.test_statebackup import BackupTestCase

PROBLEM = "config: not a JSON object with a worktree"
BAD = (b"[1]", b'"x"', b"null", b"{}", b'{"worktree": 5}', b'{"worktree": ""}', b'{"worktree": null}',
       b"\xff\xfe", b'{"worktree": ', b"", b"[" * 100000)

class ConfigShapeTests(BackupTestCase):
    def rewrite(self, backup, data, rehash=True):  # replace config.json; rehash: its manifest digest matches again
        (backup / statebackup.CONFIG).write_bytes(data)
        if not rehash: return
        doc = json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))
        doc["files"][statebackup.CONFIG] = hashlib.sha256(data).hexdigest()
        (backup / statebackup.MANIFEST).write_text(json.dumps(doc, indent=2, sort_keys=True), "utf-8")

    def cli(self, *argv):  # (exit code, the one JSON line), in process
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): code = statebackup.main([str(a) for a in argv])
        [line] = buf.getvalue().splitlines()
        return code, json.loads(line)

    def test_a_normal_backup_still_verifies_ok(self):
        backup = self.backup()
        self.assertEqual(statebackup.verify(str(backup)), {"result": "ok", "files": len(self.files(backup))})
        self.assertTrue(statebackup._config_ok(backup / statebackup.CONFIG))

    def test_a_hashed_config_that_is_not_an_object_with_a_worktree_is_corrupt(self):
        backup = self.backup()
        for data in BAD:
            with self.subTest(data=data[:20]):
                self.rewrite(backup, data)
                self.assertEqual(statebackup.verify(str(backup)), {"result": "corrupt", "problems": [PROBLEM]})

    def test_an_extra_key_or_odd_other_values_still_pass(self):  # only the worktree shape is checked
        backup = self.backup()
        self.rewrite(backup, json.dumps({"worktree": "/elsewhere", "other": [1, None]}).encode("utf-8"))
        self.assertEqual(statebackup.verify(str(backup))["result"], "ok")

    def test_a_config_hash_mismatch_reports_only_the_hash(self):
        backup = self.backup()
        self.rewrite(backup, b"[1]", rehash=False)
        self.assertEqual(statebackup.verify(str(backup)),
                         {"result": "corrupt", "problems": ["hash mismatch: config.json"]})

    def test_restore_stops_at_verify_makes_nothing_and_prints_one_line(self):
        backup, new = self.backup(), self.tmp / "restored"
        names = sorted(os.listdir(self.tmp))
        for data in (b"[1]", b"\xff\xfe", b'{"worktree": 5}'):
            with self.subTest(data=data):
                self.rewrite(backup, data)
                got = statebackup.restore(str(backup), str(new), str(self.drill_wt))
                self.assertEqual(got, {"result": "corrupt", "problems": [PROBLEM]})
                code, line = self.cli("restore", backup, "--into", new, "--worktree", self.drill_wt)
                self.assertEqual((code, line), (1, {"result": "corrupt", "problems": [PROBLEM]}))
                self.assertEqual(sorted(os.listdir(self.tmp)), names)  # no target, no .restore- temp dir
                self.assertFalse(os.path.lexists(new))

    def test_drill_stops_at_verify(self):
        backup, new = self.backup(), self.tmp / "restored"
        names = sorted(os.listdir(self.tmp))
        for data in (b"null", b'{"worktree": '):
            with self.subTest(data=data):
                self.rewrite(backup, data)
                expected = {"result": "corrupt", "step": "verify", "problems": [PROBLEM]}
                self.assertEqual(statebackup.drill(str(backup), str(new), str(self.drill_wt)), expected)
                code, line = self.cli("drill", backup, "--into", new, "--worktree", self.drill_wt)
                self.assertEqual((code, line), (1, expected))
                self.assertEqual(sorted(os.listdir(self.tmp)), names)
