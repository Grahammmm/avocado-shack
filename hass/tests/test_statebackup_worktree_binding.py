"""RF0210-9 (H20): verify calls a backup corrupt when MANIFEST.json and its hashed config.json name different worktrees.

A correctly hashed config used to verify even when the manifest named another worktree, so restore's attended-operation
refusal (based on the manifest alone) could be bypassed. Fixtures: throwaway repo from test_statebackup, no network.
"""

import contextlib, hashlib, io, json, os  # noqa: E401
from unittest import mock

from hass import health, statebackup
from hass.tests import test_statebackup as base
from hass.tests.test_statebackup import tree

MISMATCH = "config: worktree does not match manifest"
SHAPE = "config: not a JSON object with a worktree"

class WorktreeBindingTests(base.BackupTestCase):
    def setUp(self):
        super().setUp()
        for target in ("socket.socket.connect", "socket.create_connection"):
            patcher = mock.patch(target, side_effect=AssertionError("network blocked"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def manifest(self, backup):
        return json.loads((backup / statebackup.MANIFEST).read_text("utf-8"))

    def save(self, backup, doc):
        (backup / statebackup.MANIFEST).write_text(json.dumps(doc, indent=2, sort_keys=True), "utf-8")

    def set_manifest_worktree(self, backup, worktree):
        doc = self.manifest(backup)
        doc["worktree"] = worktree
        self.save(backup, doc)

    def set_config(self, backup, data, rehash=True):
        (backup / statebackup.CONFIG).write_bytes(data)
        if rehash:
            doc = self.manifest(backup)
            doc["files"][statebackup.CONFIG] = hashlib.sha256(data).hexdigest()
            self.save(backup, doc)

    def config_worktree(self, backup):
        return json.loads((backup / statebackup.CONFIG).read_text("utf-8"))["worktree"]

    def cli(self, *argv):  # (exit code, the one JSON line), in process
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): code = statebackup.main([str(a) for a in argv])
        [line] = buf.getvalue().splitlines()
        return code, json.loads(line)

    def corrupt(self, *problems):
        return {"result": "corrupt", "problems": list(problems)}

    def test_manifest_worktree_mismatch_blocks_actual_writer(self):
        backup, new = self.backup(), self.tmp / "restored"
        writer = self.config_worktree(backup)
        self.set_manifest_worktree(backup, "/somewhere/else")
        before = (tree(self.repo.state), tree(self.repo.wt), tree(backup), sorted(os.listdir(self.tmp)))
        self.assertEqual(statebackup.verify(str(backup)), self.corrupt(MISMATCH))
        self.assertEqual(statebackup.restore(str(backup), str(new), writer), self.corrupt(MISMATCH))
        self.assertEqual((tree(self.repo.state), tree(self.repo.wt), tree(backup), sorted(os.listdir(self.tmp))), before)
        self.assertFalse(os.path.lexists(new))

    def test_rehashed_config_worktree_mismatch_is_corrupt(self):
        backup = self.backup()
        self.set_config(backup, json.dumps({"worktree": "/not/the/manifest/worktree"}).encode("utf-8"))
        self.assertEqual(statebackup.verify(str(backup)), self.corrupt(MISMATCH))

    def test_empty_manifest_worktree_against_a_valid_config_is_corrupt(self):
        backup = self.backup()
        self.set_manifest_worktree(backup, "")
        self.assertEqual(statebackup.verify(str(backup)), self.corrupt(MISMATCH))

    def test_matching_and_unrelated_config_fields_stay_valid(self):
        backup = self.backup()
        count = len(self.files(backup))
        self.assertEqual(statebackup.verify(str(backup)), {"result": "ok", "files": count})
        wt = self.config_worktree(backup)
        self.assertEqual(wt, self.manifest(backup)["worktree"])
        self.set_config(backup, json.dumps({"worktree": wt, "other": [1, None], "x": {"y": 2}}).encode("utf-8"))
        self.assertEqual(statebackup.verify(str(backup)), {"result": "ok", "files": count})

    def test_matching_worktree_without_content_commit_is_still_supported(self):
        backup = self.backup()
        doc = self.manifest(backup)
        doc.pop("contentCommit", None)
        doc["files"].pop(statebackup.BUNDLE, None)
        (backup / statebackup.BUNDLE).unlink(missing_ok=True)
        self.save(backup, doc)
        self.assertEqual(statebackup.verify(str(backup)), {"result": "ok", "files": len(doc["files"])})

    def test_equivalent_but_differently_spelled_paths_are_mismatches(self):
        backup = self.backup()
        wt = self.config_worktree(backup)
        for spelled in (wt + "/", wt + "/.", os.path.join(wt, "..", os.path.basename(wt))):
            with self.subTest(spelled=spelled):
                self.set_manifest_worktree(backup, spelled)
                self.assertEqual(statebackup.verify(str(backup)), self.corrupt(MISMATCH))

    def test_shape_and_hash_diagnostics_take_precedence(self):
        backup = self.backup()
        self.set_manifest_worktree(backup, "/somewhere/else")
        for data in (b"[1]", b'{"worktree": 5}', b'{"worktree": ""}', b"\xff\xfe", b""):
            with self.subTest(data=data):
                self.set_config(backup, data)
                self.assertEqual(statebackup.verify(str(backup)), self.corrupt(SHAPE))
        self.set_config(backup, json.dumps({"worktree": "/changed/without/rehash"}).encode("utf-8"), rehash=False)
        self.assertEqual(statebackup.verify(str(backup)), self.corrupt("hash mismatch: config.json"))

    def test_cli_restore_and_drill_stop_before_outputs(self):
        backup, new = self.backup(), self.tmp / "restored"
        self.set_manifest_worktree(backup, "/somewhere/else")
        names = sorted(os.listdir(self.tmp))
        outs = [new, self.tmp / "m", self.tmp / "c"]
        with mock.patch.object(statebackup, "_write_new", side_effect=AssertionError("restore ran")) as write, \
                mock.patch.object(health, "check", side_effect=AssertionError("health ran")) as check:
            self.assertEqual(self.cli("verify", backup), (1, self.corrupt(MISMATCH)))
            self.assertEqual(self.cli("restore", backup, "--into", new, "--worktree", self.drill_wt,
                                      "--media-into", outs[1], "--content-into", outs[2]), (1, self.corrupt(MISMATCH)))
            self.assertEqual(self.cli("drill", backup, "--into", new, "--worktree", self.drill_wt,
                                      "--media-into", outs[1], "--content-into", outs[2]),
                             (1, {"result": "corrupt", "step": "verify", "problems": [MISMATCH]}))
        write.assert_not_called()
        check.assert_not_called()
        self.assertEqual(sorted(os.listdir(self.tmp)), names)  # no target, media, content or .restore- sibling
        for out in outs: self.assertFalse(os.path.lexists(out))
