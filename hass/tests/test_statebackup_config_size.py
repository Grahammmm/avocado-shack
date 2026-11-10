"""RF0854-14: real backups retain configs up to the editor's byte limit."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

from hass import editor, media, statebackup
from hass.tests import test_statebackup as fixtures
from hass.tests.test_media import AT, JPEG


class ConfigSizeTests(fixtures.BackupTestCase):
    def config_bytes(self, size, *, value="fixture", substantive=False):
        cfg = editor._read_config(self.repo.state / statebackup.CONFIG)
        cfg["unknownPadding"] = value
        data = json.dumps(cfg, ensure_ascii=False).encode("utf-8")
        if substantive:
            cfg["unknownPadding"] += "x" * (size - len(data))
            data = json.dumps(cfg, ensure_ascii=False).encode("utf-8")
        else:
            data += b" " * (size - len(data))
        self.assertEqual(len(data), size)
        (self.repo.state / statebackup.CONFIG).write_bytes(data)
        self.assertEqual(editor._read_config(self.repo.state / statebackup.CONFIG), cfg)
        return data, cfg

    def make_and_verify(self, data, *, minute=0, **kwargs):
        made = statebackup.create(str(self.repo.state), str(self.bk),
                                  now=fixtures.STAMP + timedelta(minutes=minute), **kwargs)
        self.assertEqual(made["result"], "ok", made)
        backup = Path(made["backup"])
        self.assertEqual((backup / statebackup.CONFIG).read_bytes(), data)
        self.assertEqual(self.files(backup)[statebackup.CONFIG], hashlib.sha256(data).hexdigest())
        self.assertEqual(statebackup.verify(backup), {"result": "ok", "files": made["files"]})
        return backup

    def test_created_backup_above_sidecar_limit_verifies(self):
        data, _ = self.config_bytes((64 << 10) + 1)
        self.make_and_verify(data)

    def test_created_backup_at_editor_limit_verifies(self):
        for minute, value in enumerate(("ascii", "avocaté 🥑")):
            with self.subTest(value=value):
                data, _ = self.config_bytes(editor.MAX_CONFIG, value=value)
                self.make_and_verify(data, minute=minute)

    def test_restore_preserves_large_config_unknown_field(self):
        data, cfg = self.config_bytes((64 << 10) + 1, substantive=True)
        backup = self.make_and_verify(data)
        before = (fixtures.tree(self.repo.state), fixtures.tree(backup), fixtures.tree(self.repo.wt))
        into = self.tmp / "restored"
        self.assertEqual(statebackup.restore(backup, into, self.drill_wt)["result"], "ok")
        _, restored, wt = editor._load(str(into))
        self.assertEqual(restored, {**cfg, "worktree": str(self.drill_wt.resolve())})
        self.assertEqual(wt, self.drill_wt.resolve())
        self.assertEqual((fixtures.tree(self.repo.state), fixtures.tree(backup), fixtures.tree(self.repo.wt)), before)

    def test_large_config_does_not_relax_sidecar_cap(self):
        data, _ = self.config_bytes((64 << 10) + 1)
        root = self.tmp / "media"
        root.mkdir(mode=0o700)
        sha = media.store_original(root, JPEG, received_at=AT, source="fixture")["sha256"]
        backup = self.make_and_verify(data, media=str(root))
        prefix = f"{statebackup.ORIG}{sha[:2]}/{sha}."
        side = prefix + "json"
        original = next(rel for rel in self.files(backup) if rel.startswith(prefix) and not rel.endswith(".json"))
        raw = (backup / side).read_bytes()
        self.assertEqual(statebackup.SMALL_MAX, 64 << 10)
        for size, expected in ((64 << 10, "ok"), ((64 << 10) + 1, "corrupt")):
            with self.subTest(size=size):
                padded = raw + b" " * (size - len(raw))
                (backup / side).write_bytes(padded)
                manifest = backup / statebackup.MANIFEST
                doc = json.loads(manifest.read_bytes())
                doc["files"][side] = hashlib.sha256(padded).hexdigest()
                manifest.write_text(json.dumps(doc), "utf-8")
                checked = statebackup.verify(backup)
                self.assertEqual(checked["result"], expected)
                if expected == "corrupt":
                    self.assertEqual(checked["problems"], [f"sidecar mismatch: {original}"])
