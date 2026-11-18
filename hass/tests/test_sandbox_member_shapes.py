"""RF0500-12: malformed bundle members get the gate's typed 'policy' refusal, never an incidental TypeError."""
import json
import unittest
from unittest.mock import Mock, patch

from hass import editor, sandbox, sandbox_editor
from hass.tests import fixture_ops
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_editor import HOURS, NEW_HOURS

CID = 'chg-0123456789ab'
CANARY = 'canary-secret-7f3a'
GOOD = {'pack': 'site', 'skill': 'shop.hours', 'target': 'site'}
REFUSED = {'result': 'refused', 'reason': 'sandbox target unavailable or switched off'}


def bad_values():
    return [None, False, 7, [CANARY], {'k': CANARY}]


class MemberShapeTests(unittest.TestCase):
    def setUp(self):
        self.calls = Mock(return_value={('site', 'sandbox'): 'wt-path', ('site', 'live'): 'remote'})
        self.gate = sandbox.Gate(lambda: {'approvals': 'private'}, self.calls)

    def refused(self, members):
        with self.assertRaises(sandbox.ModeError) as ctx:
            self.gate.resolve(members)
        self.assertEqual(ctx.exception.code, 'policy')
        self.assertNotIn(CANARY, str(ctx.exception))
        self.calls.assert_not_called()

    def test_resolve_rejects_wrong_container_and_member_roots(self):
        for bad in (None, [], (), 7, True, CANARY, {CANARY: 1}, [None], [7], [False], [[CANARY]],
                    [CANARY], iter([GOOD]), (m for m in [GOOD]), {GOOD['pack']}):
            with self.subTest(bad=repr(bad)[:30]):
                self.refused(bad)

    def test_resolve_rejects_wrong_field_types_before_hash_or_regex(self):
        for field in GOOD:
            for bad in bad_values() + ['']:
                with self.subTest(field=field, bad=repr(bad)[:30]):
                    member = {**GOOD, field: bad}
                    snapshot = json.dumps(member, sort_keys=True)
                    self.refused([member])
                    self.refused([GOOD, member])  # mixed bundle refuses as a whole
                    self.assertEqual(json.dumps(member, sort_keys=True), snapshot)
        for member in ({'pack': 'site', 'skill': 'shop.hours'}, {**GOOD, 'extra': 'x'},
                       {**GOOD, 'pack': 'nope'}, {**GOOD, 'target': 'nope'}, {**GOOD, 'skill': 'Bad Skill'}):
            with self.subTest(member=member):
                self.refused([member])

    def test_valid_members_preserve_binding_and_routing(self):
        other = {'pack': 'site', 'skill': 'a.b', 'target': 'site'}
        want = [other, GOOD]
        for members in ([GOOD, other], (GOOD, other)):
            given = [dict(m) for m in members]
            got = self.gate.resolve(members)
            self.assertEqual(got['members'], want)
            self.assertEqual(got['env'], 'sandbox')
            self.assertEqual(list(got['targets']), ['site'])
            self.assertEqual([dict(m) for m in members], given)


class MemberAdapterTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.mode = {'approvals': 'private'}
        self.ids = {('site', 'sandbox'): str(self.repo.wt), ('site', 'live'): 'remote-main'}
        self.factory = Mock(side_effect=AssertionError('live executor must not be constructed'))
        self.ed = sandbox_editor.SiteEditor(
            self.repo.state, sandbox.Gate(lambda: self.mode, lambda: self.ids), self.factory,
            registry=fixture_ops.registry(), clock=lambda: self.now)
        self.ed.conv = self.conv
        self.path = self.repo.state / 'drafts' / f'{CID}.json'
        self.path.parent.mkdir(exist_ok=True)

    def plant(self, members):
        draft = {'change_id': CID, 'environment': {'env': 'sandbox', 'members': members, 'targets': {}}}
        self.path.write_bytes(json.dumps(draft).encode())

    def tree(self):
        return {str(p.relative_to(self.repo.state)): p.read_bytes()
                for p in sorted(self.repo.state.rglob('*')) if p.is_file()}

    def test_reprepare_malformed_members_refuses_without_writes(self):
        cases = {'null-member': [None], 'null-skill': [{**GOOD, 'skill': None}],
                 'list-pack': [{**GOOD, 'pack': ['site']}], 'list-target': [{**GOOD, 'target': ['site']}],
                 'scalar-container': 7}
        for name, members in cases.items():
            with self.subTest(case=name):
                self.plant(members)
                before = self.tree()
                with patch.object(editor, 'prepare') as private_prepare:
                    self.assertEqual(self.ed.reprepare(CID, [{'op': HOURS, 'args': {'hours': NEW_HOURS}}]), REFUSED)
                    private_prepare.assert_not_called()
                self.assertEqual(self.tree(), before)
        self.factory.assert_not_called()

    def test_check_preserves_refusal_mapping(self):
        for members in ([None], 7, [{**GOOD, 'pack': ['site']}]):
            binding = {'env': 'sandbox', 'members': members, 'targets': {}, 'mode_gen': 0, 'off': []}
            with self.subTest(members=members):
                with self.assertRaises(sandbox.ModeError) as ctx:
                    self.ed.gate.check(binding)
                self.assertEqual(ctx.exception.code, 'env-changed')
                with self.assertRaises(sandbox.ModeError) as ctx:
                    self.ed.gate.check(binding, recorded=True)
                self.assertEqual(ctx.exception.code, 'env-gone')
                with self.assertRaises(sandbox.ModeError):
                    self.ed.gate.execute(binding, {}, {})
        self.factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
