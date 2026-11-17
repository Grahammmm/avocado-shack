"""RF1201-11 (H20): a backup whose hashed config names a worktree with an embedded NUL is corrupt, not verified.

It used to verify ok and then crash restore (ValueError resolving the recorded path). Fixtures: throwaway repo, no network.
"""

import contextlib, hashlib, io, json, os  # noqa: E401
from unittest import mock

from hass import health, statebackup
from hass.tests import test_statebackup as base
from hass.tests.test_statebackup import tree

MISMATCH = "config: worktree does not match manifest"
SHAPE = "config: not a JSON object with a worktree"

class WorktreeNulTests(base.BackupTestCase):
    def manifest(self, backup):
        return json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))

    def save(self, backup, doc):
        (backup / statebackup.MANIFEST).write_text(json.dumps(doc, indent=2, sort_keys=True), "utf-8")

    def set_manifest_worktree(self, backup, worktree):
        doc = self.manifest(backup)
        doc["worktree"] = worktree
        self.save(backup, doc)

    def set_config(self, backup, worktree, rehash=True):
        data = json.dumps({"worktree": worktree}).encode("utf-8")
        (backup / statebackup.CONFIG).write_bytes(data)
        if rehash:
            doc = self.manifest(backup)
            doc["files"][statebackup.CONFIG] = hashlib.sha256(data).hexdigest()
            self.save(backup, doc)

    def bind(self, backup, worktree):  # manifest and rehashed config name the same string
        self.set_manifest_worktree(backup, worktree)
        self.set_config(backup, worktree)

    def cli(self, *argv):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err): code = statebackup.main([str(a) for a in argv])
        [line] = buf.getvalue().splitlines()
        self.assertEqual(err.getvalue(), "")
        return code, json.loads(line)

    def corrupt(self, *problems):
        return {"result": "corrupt", "problems": list(problems)}

    def test_matching_nul_worktrees_are_corrupt(self):
        backup = self.backup()
        for wt in ("\x00/synthetic/CANARY", "/synthetic/CANARY\x00writer", "/synthetic/CANARY\x00"):
            with self.subTest(wt=wt):
                self.bind(backup, wt)
                out = statebackup.verify(str(backup))
                self.assertEqual(out, self.corrupt(SHAPE))
                self.assertNotIn("CANARY", json.dumps(out))

    def test_config_only_nul_and_manifest_only_nul(self):
        backup = self.backup()
        good = self.manifest(backup)["worktree"]
        self.set_config(backup, good + "\x00x")
        self.assertEqual(statebackup.verify(str(backup)), self.corrupt(SHAPE))
        self.assertIsNone(statebackup._config_worktree(backup / statebackup.CONFIG))
        self.assertFalse(statebackup._config_ok(backup / statebackup.CONFIG))
        self.set_config(backup, good)
        self.set_manifest_worktree(backup, good + "\x00x")
        self.assertEqual(statebackup.verify(str(backup)), self.corrupt(MISMATCH))
        self.bind(backup, good)
        self.set_config(backup, good + "\x00x", rehash=False)
        self.assertEqual(statebackup.verify(str(backup)), self.corrupt("hash mismatch: config.json"))

    def test_restore_and_drill_cli_refuse_before_any_output(self):
        backup, new = self.backup(), self.tmp / "restored"
        self.bind(backup, "/synthetic/recorded\x00writer")
        names, before = sorted(os.listdir(self.tmp)), tree(backup)
        outs = [new, self.tmp / "m", self.tmp / "c"]
        args = (backup, "--into", new, "--worktree", self.drill_wt, "--media-into", outs[1], "--content-into", outs[2])
        with mock.patch.object(statebackup, "_write_new", side_effect=AssertionError("restore ran")) as write, \
                mock.patch.object(health, "check", side_effect=AssertionError("health ran")) as check:
            self.assertEqual(self.cli("verify", backup), (1, self.corrupt(SHAPE)))
            self.assertEqual(self.cli("restore", *args), (1, self.corrupt(SHAPE)))
            self.assertEqual(self.cli("drill", *args), (1, {"result": "corrupt", "step": "verify", "problems": [SHAPE]}))
        write.assert_not_called()
        check.assert_not_called()
        self.assertEqual(sorted(os.listdir(self.tmp)), names)
        self.assertEqual(tree(backup), before)
        for out in outs: self.assertFalse(os.path.lexists(out))

    def test_valid_paths_and_healthy_restore_remain_compatible(self):
        backup, new = self.backup(), self.tmp / "restored"
        count = len(self.files(backup))
        self.assertEqual(statebackup.verify(str(backup)), {"result": "ok", "files": count})
        for wt in ("/synthetic/rec\u00e9 orded/with space", "/does/not/exist"):
            with self.subTest(wt=wt):
                self.bind(backup, wt)
                self.assertEqual(statebackup.verify(str(backup)), {"result": "ok", "files": count})
        backup2 = self.backup()
        self.assertEqual(statebackup.restore(str(backup2), str(new), str(self.drill_wt))["result"], "ok")
