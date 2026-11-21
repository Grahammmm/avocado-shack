"""Synthetic-only fixture evidence for the skill rollback proof CLI."""

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from scripts.hass import install_skill_restore_proof as proof


class SkillRestoreProofTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.paths = {}
        self.roster = {}
        for key in ('builder/maintain', 'reviewer/review'):
            self.paths[key] = {}
            for kind in ('backup', 'target'):
                path = self.root / kind / key / 'SKILL.md'
                path.parent.mkdir(parents=True)
                self.paths[key][kind] = path
            self.roster[key] = {kind: str(path) for kind, path in self.paths[key].items()}
        self.present = self.paths['builder/maintain']
        self.absent = self.paths['reviewer/review']
        self.original = b'synthetic prior skill\n'
        for kind, mode in (('backup', 0o600), ('target', 0o640)):
            self.present[kind].write_bytes(self.original)
            self.present[kind].chmod(mode)
        self.prior = {
            'builder/maintain': {'sha256': hashlib.sha256(self.original).hexdigest(), 'mode': '0640'},
            'reviewer/review': 'absent',
        }
        self.roster_file = self.root / 'roster.json'
        self.prior_file = self.root / 'prior.json'
        self.write_inputs()

    def write_inputs(self):
        self.roster_file.write_text(json.dumps(self.roster), encoding='utf-8')
        self.prior_file.write_text(json.dumps(self.prior), encoding='utf-8')

    def invoke(self, phase, code, reason):
        receipt = io.StringIO()
        with contextlib.redirect_stdout(receipt):
            result = proof.main([phase, '--roster', str(self.roster_file), '--prior', str(self.prior_file)])
        output = receipt.getvalue()
        self.assertEqual(result, code, output)
        self.assertIn(reason, output)
        self.assertNotIn(str(self.root), output)
        self.assertNotIn(hashlib.sha256(self.original).hexdigest(), output)
        self.assertNotIn(self.original.decode().strip(), output)

    def test_matching_prior_states_are_read_only_in_each_phase(self):
        # A verifier must neither consult nor mutate the other phase's evidence.
        target = self.present['target']
        target.write_bytes(b'not the prior bytes')
        self.invoke('pre', 0, 'all 2 roster rows')
        self.assertEqual(target.read_bytes(), b'not the prior bytes')
        self.assertEqual(self.present['backup'].read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(self.present['backup'].stat().st_mode), 0o600)
        self.assertFalse(self.absent['backup'].exists())

        target.write_bytes(self.original)
        self.present['backup'].unlink()
        self.invoke('post', 0, 'all 2 roster rows')
        self.assertEqual(target.read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        self.assertFalse(self.absent['target'].exists())
        self.assertFalse(self.present['backup'].exists())

    def test_present_file_drift_or_loss_fails_in_either_phase(self):
        # Same-length edits defeat size checks; missing evidence must not be skipped.
        for phase, kind in (('pre', 'backup'), ('post', 'target')):
            with self.subTest(phase=phase):
                path = self.present[kind]
                path.write_bytes(self.original.upper())
                self.invoke(phase, 1, 'prior SHA-256 mismatch')
                path.unlink()
                self.invoke(phase, 1, 'expected file is missing')

    def test_restored_digest_without_prior_mode_is_insufficient(self):
        # Byte parity alone would let a permission regression pass post-restore.
        self.present['target'].chmod(0o644)
        self.invoke('post', 1, 'prior mode mismatch')

    def test_absent_rows_reject_even_dangling_links(self):
        # exists() follows a symlink and misreports a dangling entry as absent.
        for phase, kind in (('pre', 'backup'), ('post', 'target')):
            with self.subTest(phase=phase):
                path = self.absent[kind]
                path.symlink_to(self.root / 'nonexistent')
                self.invoke(phase, 1, 'expected absence, but an entry exists')
                self.assertTrue(path.is_symlink())
                path.unlink()
                path.touch()
                self.invoke(phase, 1, 'expected absence, but an entry exists')

    def test_paths_do_not_follow_links_or_read_special_entries(self):
        # Matching link contents cannot qualify as regular-file evidence, nor
        # may a redirected directory provide a false proof of absence.
        target = self.present['target']
        target.unlink()
        target.symlink_to(self.present['backup'])
        self.invoke('post', 1, 'expected a regular file')
        target.unlink()
        os.mkfifo(target)
        self.invoke('post', 1, 'expected a regular file')
        target.unlink()
        target.write_bytes(self.original)
        target.chmod(0o640)
        parent = self.absent['target'].parent
        parent.rmdir()
        self.invoke('post', 0, 'all 2 roster rows')
        parent.symlink_to(self.root / 'missing-directory')
        self.invoke('post', 1, 'unsafe or unreadable path')

    def test_manifest_must_cover_every_approved_row(self):
        # Iterating only manifest rows would silently certify a partial rollback.
        del self.prior['reviewer/review']
        self.write_inputs()
        self.invoke('pre', 1, 'complete approved roster')
        self.invoke('post', 1, 'complete approved roster')

    def test_unsafe_or_ambiguous_roster_paths_fail_before_evidence(self):
        # No normalization, double-counting, or treating a file as a directory.
        for path, reason in (
            ('relative/SKILL.md', 'canonical absolute file path'),
            (f'{self.root}/target/../elsewhere', 'canonical absolute file path'),
            (str(self.present['target']), 'duplicate file paths'),
            (f"{self.present['target']}/child", 'file paths overlap'),
        ):
            with self.subTest(reason=reason, path=path):
                self.roster['reviewer/review']['target'] = path
                self.write_inputs()
                self.invoke('pre', 1, reason)

    def test_duplicate_manifest_key_cannot_override_prior_state(self):
        # json.load normally keeps the last duplicate, hiding conflicting evidence.
        original = self.prior_file.read_text(encoding='utf-8')
        self.prior_file.write_text('{"builder/maintain":"absent",' + original[1:], encoding='utf-8')
        self.invoke('pre', 1, 'prior: invalid or unreadable JSON document')


if __name__ == '__main__':
    unittest.main()
