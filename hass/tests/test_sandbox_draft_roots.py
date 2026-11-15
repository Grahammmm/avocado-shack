"""RF0721-8: a draft file holding valid JSON that is not an object takes the adapter's unavailable-draft path."""
import json
import unittest
from unittest.mock import Mock, patch

from hass import editor, sandbox, sandbox_editor
from hass.ops import load_registry
from hass.tests import fixture_ops
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_editor import HOURS, NEW_HOURS

CID = 'chg-0123456789ab'
CANARY = 'canary-secret-7f3a'
ROOTS = {
    'null': b'null', 'empty-list': b'[]', 'canary-list': json.dumps([CANARY]).encode(),
    'empty-string': b'""', 'canary-string': json.dumps(CANARY).encode(),
    'zero': b'0', 'int': b'17', 'false': b'false', 'true': b'true',
}
GONE = {'result': 'env-gone'}
REFUSED = {'result': 'refused', 'reason': 'sandbox target unavailable or switched off'}


class DraftRootTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.mode = {'approvals': 'private'}
        self.ids = {('site', 'sandbox'): str(self.repo.wt), ('site', 'live'): 'remote-main'}
        self.factory = Mock(side_effect=AssertionError('live executor must not be constructed'))
        self.ed = sandbox_editor.SiteEditor(
            self.repo.state, sandbox.Gate(lambda: self.mode, lambda: self.ids), self.factory,
            registry={**fixture_ops.registry(), 'history.revert': load_registry()['history.revert']},
            clock=lambda: self.now)
        self.ed.conv = self.conv
        self.path = self.repo.state / 'drafts' / f'{CID}.json'
        self.path.parent.mkdir(exist_ok=True)

    def plant(self, raw):
        self.path.write_bytes(raw)

    def tree(self):
        return {str(p.relative_to(self.repo.state)): p.read_bytes()
                for p in sorted(self.repo.state.rglob('*')) if p.is_file()}

    def over_roots(self, check):
        for name, raw in ROOTS.items():
            with self.subTest(root=name):
                self.plant(raw)
                before = self.tree()
                check()
                self.assertEqual(self.tree(), before)
                self.assertEqual(self.path.read_bytes(), raw)

    def test_nonobject_roots_raise_existing_unavailable_draft_error(self):
        def check():
            with self.assertRaises(sandbox.ModeError) as ctx:
                self.ed._draft(CID)
            self.assertEqual(ctx.exception.code, 'env-gone')
            self.assertNotIn(CANARY, str(ctx.exception))
        self.over_roots(check)

    def test_check_and_apply_refuse_before_either_executor(self):
        def check():
            self.assertEqual(self.ed.check_environment(CID), GONE)
            self.assertEqual(self.ed.check_environment(CID, recorded=False), GONE)
            self.assertEqual(self.ed.check_environment(CID, recorded=True), GONE)
            self.assertEqual(self.ed.apply(CID, 'sha256:' + '0' * 64), GONE)
        with patch.object(editor, 'apply') as private_apply:
            self.over_roots(check)
            private_apply.assert_not_called()
        self.factory.assert_not_called()

    def test_reprepare_and_undo_prepare_refuse_without_repair(self):
        undo = [{'op': 'history.revert', 'args': {'changeId': CID}}]

        def check():
            self.assertEqual(self.ed.reprepare(CID, [{'op': HOURS, 'args': {'hours': NEW_HOURS}}]), REFUSED)
            self.assertEqual(self.ed.prepare(undo), {**GONE, 'reason': REFUSED['reason']})
        with patch.object(editor, 'prepare') as private_prepare:
            self.over_roots(check)
            private_prepare.assert_not_called()
        self.factory.assert_not_called()

    def test_went_live_is_false_for_wrong_root_and_never_constructs_live(self):
        self.over_roots(lambda: self.assertFalse(self.ed.went_live(CID)))
        self.factory.assert_not_called()

    def test_valid_object_and_existing_io_refusals_are_preserved(self):
        draft = self.ed.prepare([{'op': HOURS, 'args': {'hours': NEW_HOURS}}])['draft']
        cid = draft['change_id']
        self.assertEqual(self.ed._draft(cid), draft)
        self.assertIsNone(self.ed.check_environment(cid))
        missing, malformed = 'chg-aaaaaaaaaaaa', 'chg-bbbbbbbbbbbb'
        (self.repo.state / 'drafts' / f'{malformed}.json').write_text('{not json', 'utf-8')
        for bad in (missing, malformed):
            with self.assertRaises(sandbox.ModeError) as ctx:
                self.ed._draft(bad)
            self.assertEqual(ctx.exception.code, 'env-gone')
            self.assertEqual(self.ed.check_environment(bad), GONE)
            self.assertEqual(self.ed.reprepare(bad, []), REFUSED)
            self.assertFalse(self.ed.went_live(bad))
        with self.assertRaises(sandbox.ModeError):
            self.ed._draft('not-a-change-id')
        self.assertEqual(self.ed.check_environment('not-a-change-id'), GONE)
        self.assertFalse(self.ed.went_live('not-a-change-id'))
        self.assertEqual(self.ed.reprepare('not-a-change-id', []), REFUSED)


if __name__ == '__main__':
    unittest.main()
