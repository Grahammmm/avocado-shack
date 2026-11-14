"""AVB-09: registry coverage, fail-closed metadata, real generated-file drift and help parity."""
import dataclasses
import importlib
import json
import pkgutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from hass import capabilities, skills, voice
from hass.ops import load_registry
from hass.skills import testkit
from hass.skills.model import Registry
from hass.tests.test_skills_model import _skill


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.registry = skills.load_skills()
        self.ops = load_registry()

    def test_every_registry_skill_is_in_json_page_and_help_once(self):
        data = capabilities.manifest(self.registry)
        saved = json.loads((capabilities.ROOT / capabilities.JSON_PATH).read_text())
        self.assertEqual(saved, data)
        self.assertEqual([r['name'] for r in data['skills']], sorted(self.registry.skills))
        page = capabilities.owner_page(data)
        help_text = capabilities.help_section(self.registry)
        self.assertEqual(voice.check(help_text, long_ok=True), [])
        self.assertEqual(testkit.plain_words_problems(help_text), [])
        for row in data['skills']:
            self.assertEqual(page.count(f"({row['name']})"), 1)
            lines = [line for line in help_text.splitlines() if line.startswith(row['label'] + ' - ')]
            self.assertEqual(len(lines), 1)
            self.assertIn(capabilities.APPROVAL_WORDS[row['approval_class']], lines[0])
            self.assertIn(capabilities.SANDBOX_WORDS[row['sandbox']], lines[0])
        self.assertIn('Till:\nNothing registered yet.', help_text)
        faq = next(line for line in help_text.splitlines() if line.startswith('add a questions page - '))
        self.assertIn('writes the request down, not the change', faq)

    def test_each_required_metadata_field_and_status_fails_when_absent(self):
        skill = self.registry.skills['item.hide']
        for key in ('pack', 'targets', 'approval_class', 'sandbox', 'logs', 'who', 'status'):
            with self.subTest(key=key):
                broken = dataclasses.replace(skill, **{key: None})
                problems = skills.skill_lint([broken], self.ops)
                self.assertTrue(any(f': {key}:' in p for p in problems), problems)
                with self.assertRaises(ValueError):
                    capabilities.manifest(Registry({broken.name: broken}))

    def test_cross_field_metadata_cannot_claim_a_stronger_gate_or_wrong_target(self):
        skill = self.registry.skills['item.hide']
        for over in ({'approval_class': 'A0'}, {'approval_class': 'A2'}, {'approval_class': 'A3'},
                     {'sandbox': 'preview'}, {'sandbox': 'none-needed'}, {'who': 'anyone'},
                     {'logs': ('message',)}, {'logs': ('prices',)}, {'logs': ('fields', 'fields')},
                     {'targets': ('till',)}, {'targets': ('site', 'till')}, {'targets': ('site', 'site')},
                     {'pack': 'reports'}, {'patterns': ['phrase']}):
            with self.subTest(over=over):
                self.assertTrue(skills.skill_lint([dataclasses.replace(skill, **over)], self.ops))
        ro = self.registry.skills['answer.site']
        self.assertTrue(skills.skill_lint([dataclasses.replace(ro, targets=('site',))], self.ops))
        self.assertTrue(skills.skill_lint([dataclasses.replace(ro, approval_class='A1')], self.ops))
        till = dataclasses.replace(skill, pack='till', targets=('till', 'site'))
        self.assertEqual(skills.skill_lint([till], self.ops), [])
        self.assertTrue(skills.skill_lint([dataclasses.replace(till, sandbox='preview')], self.ops))

    def test_new_and_retired_entries_flow_through_without_a_second_inventory(self):
        new = _skill(name='probe.new', label='do a new thing', status='retired',
                     cases='hass/tests/fixtures/skills/probe/probe.new.jsonl')
        reg = Registry({new.name: new})
        self.assertIsNone(reg.get(new.name))
        self.assertEqual(capabilities.manifest(reg)['skills'][0]['status'], 'retired')
        self.assertIn('do a new thing - ', capabilities.help_section(reg))
        self.assertIn('retired', capabilities.help_section(reg))
        self.assertIn('(probe.new)', capabilities.owner_page(capabilities.manifest(reg)))
        changed = dataclasses.replace(new, label='a different thing', status='active', sandbox='full')
        changed_reg = Registry({changed.name: changed})
        self.assertNotEqual(capabilities.generated_files(reg), capabilities.generated_files(changed_reg))
        self.assertIn('a different thing - ', capabilities.help_section(changed_reg))

    def test_loader_rejects_mixed_pack_exports(self):
        original = pkgutil.iter_modules
        module = types.ModuleType('hass.skills.pack_probe')
        module.SKILLS = (self.registry.skills['item.hide'], self.registry.skills['page.faq'])
        extra = pkgutil.ModuleInfo(None, 'pack_probe', False)
        with patch.dict('sys.modules', {'hass.skills.pack_probe': module}), patch.object(
                pkgutil, 'iter_modules', side_effect=lambda path: [*original(path), extra]):
            with self.assertRaisesRegex(ValueError, 'one pack'):
                skills.load_skills()

    def test_all_module_exports_are_one_pack(self):
        for info in pkgutil.iter_modules(skills.__path__):
            module = importlib.import_module('hass.skills.' + info.name)
            self.assertLessEqual(len({s.pack for s in getattr(module, 'SKILLS', ())}), 1)

    def test_check_detects_missing_and_stale_files_without_writing(self):
        files = capabilities.generated_files()
        with tempfile.TemporaryDirectory() as tmp, patch.object(capabilities, 'ROOT', Path(tmp)):
            root = Path(tmp)
            self.assertEqual(capabilities.main(['--check']), 1)
            self.assertEqual(list(root.iterdir()), [])
            for path, text in files.items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(text)
            self.assertEqual(capabilities.main(['--check']), 0)
            for path in files:
                with self.subTest(path=path):
                    target = root / path
                    target.write_text('stale\n')
                    self.assertEqual(capabilities.main(['--check']), 1)
                    self.assertEqual(target.read_text(), 'stale\n')
                    self.assertEqual(capabilities.main([]), 0)
                    self.assertEqual(target.read_text(), files[path])

    def test_checked_in_generated_files_are_fresh(self):
        self.assertEqual(capabilities.main(['--check']), 0)


if __name__ == '__main__':
    unittest.main()
