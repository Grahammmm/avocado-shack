"""Verify exact permission modes on a minimal synthetic backup."""

import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest

from hass import statebackup


class ExactModeTests(unittest.TestCase):
    def make_backup(self, root):
        root.chmod(0o700)
        drafts = root / "drafts"
        drafts.mkdir()
        drafts.chmod(0o700)
        config = b'{"worktree": "fixture-worktree"}\n'
        manifest = {
            "schemaVersion": 1,
            "worktree": "fixture-worktree",
            "files": {"config.json": hashlib.sha256(config).hexdigest()},
        }
        for name, data in (("config.json", config), ("MANIFEST.json", json.dumps(manifest).encode("utf-8"))):
            path = root / name
            path.write_bytes(data)
            path.chmod(0o600)

    def test_exact_private_modes_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_backup(root)
            self.assertEqual(statebackup.verify(root), {"result": "ok", "files": 1})

    def test_special_bits_are_rejected_without_repair(self):
        # These modes have the right low nine bits, so a 0o777 mask falsely accepts them.
        for rel, mode, label in (
            (".", 0o1700, "backup dir"),
            ("drafts", 0o2700, "drafts"),
            ("MANIFEST.json", 0o1600, "MANIFEST.json"),
            ("config.json", 0o4600, "config.json"),
        ):
            with self.subTest(path=rel), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_backup(root)
                path = root / rel
                path.chmod(mode)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
                verdict = statebackup.verify(root)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
                self.assertEqual(verdict, {"result": "corrupt", "problems": [f"mode: {label}"]})
