"""AVB-11 offline acceptance: real private writer, fake live transports, no credentials."""

import json
import subprocess
import unittest
from datetime import timedelta
from unittest.mock import Mock, patch

from hass import editor, host, sandbox, sandbox_editor
from hass.ops import load_registry
from hass.skills import load_skills
from hass.skills import testkit, dispatch
from hass.content_model import REPO_ROOT
from hass.tests import fixture_ops
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_host import HostCase
from hass.tests import test_live_drill as drill, test_publish_live as pl
from hass.tests.test_editor import HOURS, NEW_HOURS, git


def member(pack='site', skill='shop.hours', target='site'):
    return {'pack': pack, 'skill': skill, 'target': target}


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'approvals': 'private', 'live': ['site']}
        self.ids = {(t, e): f'{t}-{e}-identity' for t in ('site', 'till', 'local') for e in ('sandbox', 'live')}
        self.gate = sandbox.Gate(lambda: self.cfg, lambda: self.ids)
        self.calls = []
        self.executors = {(*k, sandbox.identity(v)): self.recorder(k) for k, v in self.ids.items()}

    def recorder(self, key):
        def run(payload):
            self.calls.append((key, payload))
            return 'ok'
        return run

    def test_s1_whole_bundle_sandbox_site_stays_live_for_independent_changes(self):
        binding = self.gate.resolve([member(), member('till', 'till.stock', 'till')])
        self.gate.execute(binding, {'site': 'stock-word', 'till': 'count'}, self.executors)
        self.assertEqual(binding['env'], 'sandbox')
        self.assertEqual({c[0] for c in self.calls}, {('site', 'sandbox'), ('till', 'sandbox')})
        self.assertEqual(self.gate.resolve([member()])['env'], 'live')

    def test_s2_s3_switch_and_merchant_change_make_zero_calls(self):
        for change in ('mode', 'merchant', 'generation', 'off'):
            with self.subTest(change=change):
                self.setUp()
                b = self.gate.resolve([member('till', 'till.stock', 'till')])
                if change == 'mode': self.cfg['live'].append('till')
                elif change == 'merchant': self.ids['till', 'sandbox'] = 'merchant-B'
                elif change == 'generation': self.cfg['mode_gen'] = 1
                else: self.cfg['off'] = ['till.stock']
                with self.assertRaisesRegex(sandbox.ModeError, 'env-changed'):
                    self.gate.execute(b, {'till': 'write'}, self.executors)
                self.assertEqual(self.calls, [])

    def test_s4_s5_recorded_recovery_uses_sandbox_after_live_switch(self):
        b = self.gate.resolve([member(), member('till', 'till.stock', 'till')])
        self.cfg.update(live=['site', 'till'], mode_gen=1)
        self.gate.execute(b, {'site': 'finish-companion', 'till': 'undo'}, self.executors, recorded=True)
        self.assertTrue(all(key[1] == 'sandbox' for key, _ in self.calls))

    def test_s6_missing_sandbox_refuses_whole_bundle_and_no_live_fallback(self):
        b = self.gate.resolve([member(), member('till', 'till.stock', 'till')])
        del self.ids['site', 'sandbox']
        with self.assertRaisesRegex(sandbox.ModeError, 'policy'):
            self.gate.resolve(b['members'])
        with self.assertRaisesRegex(sandbox.ModeError, 'env-gone'):
            self.gate.execute(b, {'site': 'undo', 'till': 'undo'}, self.executors, recorded=True)
        self.assertEqual(self.calls, [])

    def test_all_packs_default_sandbox_and_legacy_live_does_not_enable(self):
        self.cfg = {'approvals': 'live'}
        for pack, target in [('site', 'site'), ('front', 'site'), ('till', 'till'), ('reports', 'local'), ('core', 'local')]:
            with self.subTest(pack=pack):
                b = self.gate.resolve([member(pack, f'{pack}.test', target)])
                self.gate.execute(b, {target: 'test'}, self.executors)
                self.assertEqual(b['env'], 'sandbox')
        self.assertTrue(all(key[1] == 'sandbox' for key, _ in self.calls))

    def test_malformed_policy_hold_and_missing_executor_fail_before_calls(self):
        for over in [{'live': None}, {'live': 'site'}, {'live': [True]}, {'off': 'site'}, {'off': ['bad space']},
                     {'mode_gen': True}, {'mode_gen': -1}, {'approvals': 'hold'}]:
            with self.subTest(over=over), self.assertRaises(sandbox.ModeError):
                sandbox.Gate(lambda: {**self.cfg, **over}, lambda: self.ids).resolve([member()])
        b = self.gate.resolve([member(), member('till', 'till.stock', 'till')])
        with self.assertRaises(sandbox.ModeError):
            self.gate.execute(b, {'site': 1, 'till': 1}, {})
        self.assertEqual(self.calls, [])


class SiteTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.mode = {'approvals': 'private'}
        self.ids = {('site', 'sandbox'): str(self.repo.wt), ('site', 'live'): 'remote-main'}
        self.factory = Mock(side_effect=AssertionError('live executor must not be constructed'))
        self.ed = sandbox_editor.SiteEditor(self.repo.state, sandbox.Gate(lambda: self.mode, lambda: self.ids),
                                           self.factory, registry={**fixture_ops.registry(), 'history.revert': load_registry()['history.revert']}, clock=lambda: self.now)
        self.conv.editor = self.ed
        self.ed.conv = self.conv

    def test_real_dispatch_keeps_skill_off_policy_through_fresh_approval(self):
        skills = load_skills()
        self.ed.registry = None
        self.conv.skills_mode = 'both'
        self.conv.dispatch = dispatch.Dispatcher(self.conv, skills)
        row = testkit.load_rows(REPO_ROOT / skills.get('shop.hours').cases)[0]
        self.interp.mapping[row['texts'][0]] = row['replies'][0]
        self.assertEqual(self.say(row['texts'][0]), 'proposed')
        old = self.drafts()[-1]
        self.mode['mode_gen'] = 1
        self.assertEqual(self.say('yes ' + old['code']), 'env-changed')
        fresh = self.drafts()[-1]
        binding = self.ed._draft(fresh['change_id'])['environment']
        self.assertIn('shop.hours', [m['skill'] for m in binding['members']])
        self.mode['off'] = ['shop.hours']
        self.assertEqual(self.say('yes ' + fresh['code']), 'env-changed')
        self.assertFalse(any(r['state'] == 'proposed' for r in self.drafts()))
        self.assertEqual(self.commits(), 0)
        self.factory.assert_not_called()

    def test_shelf_confirmation_cannot_resume_a_switched_off_skill(self):
        from hass.conversation import Inbound
        from hass.tests.test_conversation import CHAT, OWNER
        self.ed.registry = None
        stock = load_skills().get('stock.set')
        msg = Inbound('shelf-fixture', CHAT, OWNER, 'eggs are out', received_at=self.now.isoformat())
        # Start at the persisted shelf-question boundary; actual skill parsing is
        # covered separately, and may ask its own question before reaching here.
        with self.conv._tx():
            self.conv._ask_shelf(msg, self.now, {'ops': [
                {'op': 'product.set_availability', 'args': {'id': 'photo-product-024', 'available': 'no'}}],
                'revises': None}, [], (stock,))
            self.conv._record(msg, 'question')
        self.mode['off'] = ['stock.set']
        self.assertEqual(self.say('yes'), 'not-drafted')
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.commits(), 0)
        self.factory.assert_not_called()

    def test_real_sandbox_apply_and_undo_after_mode_switch_never_call_live(self):
        before = self.repo.head()
        d = self.ed.prepare([{'op': HOURS, 'args': {'hours': NEW_HOURS}}])['draft']
        self.assertEqual(self.ed.apply(d['change_id'], d['draft_hash'])['result'], 'applied')
        self.assertNotEqual(self.repo.head(), before)
        self.mode.update(live=['site'], mode_gen=1)
        undo = self.ed.prepare([{'op': 'history.revert', 'args': {'changeId': d['change_id']}}])['draft']
        self.assertEqual(undo['environment']['env'], 'sandbox')
        self.assertEqual(self.ed.apply(undo['change_id'], undo['draft_hash'])['result'], 'applied')
        self.factory.assert_not_called()
        self.assertEqual(editor._read(self.repo.state / 'changes' / f"{d['change_id']}.json")['environment'], d['environment'])

    def test_yes_old_code_gets_new_draft_no_approval_no_live_executor(self):
        self.say('hours')
        old = self.drafts()[0]
        self.mode.update(live=['site'], mode_gen=1)
        before = self.repo.head()
        self.assertEqual(self.say('yes ' + old['code']), 'env-changed')
        self.assertEqual(self.repo.head(), before)
        self.assertEqual(self.conv.db.execute('SELECT count(*) FROM approvals').fetchone()[0], 0)
        rows = self.drafts()
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[-1]['code'], old['code'])
        self.assertEqual(rows[0]['state'], 'rejected')
        self.factory.assert_not_called()

    def test_identity_change_same_mode_and_last_moment_switch(self):
        ops = [{'op': HOURS, 'args': {'hours': NEW_HOURS}}]
        d = self.ed.prepare(ops)['draft']
        self.ids['site', 'sandbox'] = 'different-writer'
        self.assertEqual(self.ed.apply(d['change_id'], d['draft_hash']), {'result': 'env-changed'})
        self.ids['site', 'sandbox'] = str(self.repo.wt)
        original = editor._compute
        def compute(*args, **kw):
            out = original(*args, **kw)
            self.mode['mode_gen'] = 1
            return out
        before = self.repo.head()
        with patch.object(editor, '_compute', side_effect=compute):
            self.assertEqual(self.ed.apply(d['change_id'], d['draft_hash']), {'result': 'env-changed'})
        self.assertEqual(self.repo.head(), before)
        self.factory.assert_not_called()

    def test_every_registered_skill_sandbox_binding_and_off(self):
        # Every current skill goes through the SAME host adapter. Its real contract
        # and fixture suite test the plan; here the boundary proves live isolation.
        ops = [{'op': HOURS, 'args': {'hours': NEW_HOURS}}]
        for skill in load_skills().skills.values():
            with self.subTest(skill=skill.name):
                if skill.approval != 'none':
                    d = self.ed.prepare(ops, skills=(skill,))['draft']
                    self.assertEqual(d['environment']['env'], 'sandbox')
                    self.assertIsNone(self.ed.check_environment(d['change_id']))
                    self.mode['off'] = [skill.name]
                    self.assertEqual(self.ed.check_environment(d['change_id']), {'result': 'env-changed'})
                    self.assertEqual(self.ed.reprepare(d['change_id'], ops)['result'], 'refused')
                else:
                    self.mode['off'] = [skill.name]
                self.assertFalse(self.ed.skill_allowed(skill))
                self.mode.pop('off')
        self.factory.assert_not_called()

    def test_hash_changes_with_generation_even_when_target_stays_sandbox(self):
        ops = [{'op': HOURS, 'args': {'hours': NEW_HOURS}}]
        first = self.ed.prepare(ops)['draft']
        self.mode['mode_gen'] = 1
        second = self.ed.prepare(ops)['draft']
        self.assertNotEqual(first['draft_hash'], second['draft_hash'])
        self.assertNotEqual(first['change_id'], second['change_id'])

    def test_tampering_cannot_relabel_a_sandbox_approval_as_live(self):
        d = self.ed.prepare([{'op': HOURS, 'args': {'hours': NEW_HOURS}}])['draft']
        self.mode['live'] = ['site']
        d['environment'] = self.ed.gate.resolve(d['environment']['members'])
        editor._write_json(self.repo.state / 'drafts' / f"{d['change_id']}.json", d)
        self.assertEqual(self.ed.apply(d['change_id'], d['draft_hash']), {'result': 'env-changed'})
        self.factory.assert_not_called()

    def test_missing_recorded_target_refuses_undo_and_crash_recovery(self):
        from hass.tests.test_editor import _journal
        d = self.ed.prepare([{'op': HOURS, 'args': {'hours': NEW_HOURS}}])['draft']
        _journal(self.repo, d['change_id'], self.repo.head())
        del self.ids['site', 'sandbox']
        self.assertEqual(self.ed.recover(), {'result': 'env-gone'})
        undo = self.ed.prepare([{'op': 'history.revert', 'args': {'changeId': d['change_id']}}])
        self.assertEqual(undo['result'], 'env-gone')
        self.assertTrue((self.repo.state / 'journal' / f"{d['change_id']}.json").exists())
        self.factory.assert_not_called()


class SkillIsolationTests(unittest.TestCase):
    def test_real_case_for_every_skill_uses_sandbox_adapter(self):
        skills = list(load_skills().skills.values())
        factory = Mock(side_effect=AssertionError('a sandbox skill constructed the live executor'))
        covered = set()

        def kit_editor(sc):
            class SandboxKit(sandbox_editor.SiteEditor):
                _clock = staticmethod(sc._clock)

                def __init__(self, state):
                    gate = sandbox.Gate(lambda: {'approvals': 'private'},
                                        lambda: {('site', 'sandbox'): str(sc.repo.wt)})
                    super().__init__(state, gate, factory, clock=sc._clock)

                prepare = testkit._with_clock(sandbox_editor.SiteEditor.prepare)
                apply = testkit._with_clock(sandbox_editor.SiteEditor.apply)
                render_draft = testkit._with_clock(sandbox_editor.SiteEditor.render_draft)
            return SandboxKit

        with patch.object(testkit, '_clocked_editor', kit_editor):
            for skill in skills:
                with self.subTest(skill=skill.name):
                    path = REPO_ROOT / skill.cases
                    if skill.name in ('backlog.log', 'page.faq'):
                        # These built-in read-only/refusal skills declare no on-disk
                        # cases today. Their real plan cannot yield a target write.
                        self.assertEqual(skill.plan({}, None), [])
                        self.assertEqual(skill.approval, 'none')
                        covered.add(skill.name)
                        continue
                    rows = testkit.load_rows(path)
                    cases = [r for r in rows if not r.get('plan')]
                    row = next((r for r in cases if r.get('expect', {}).get('disposition') == 'proposed'), cases[0])
                    result = testkit.run_file(path, skills, only=[row['id']])[0]
                    self.assertTrue(result.ok, (skill.name, result.codes, result.facts))
                    covered.add(skill.name)
        self.assertEqual(covered, {s.name for s in skills})
        print(f'sandbox skill coverage: {len(covered)} registered skills; {len(covered - {"backlog.log", "page.faq"})} fixture cases; 2 built-in read-only plans')
        factory.assert_not_called()


class HostModeTests(HostCase):
    def test_legacy_live_without_target_list_constructs_only_sandbox_adapter(self):
        from hass import publish_live
        cfg = host.load_host(drill.SwitchBack.live_json(self))
        with patch.object(publish_live, 'LiveEditor', side_effect=AssertionError('live executor constructed')):
            worker = host.make_worker(cfg, self.store, build=lambda: self.interp, clock=self.clock)
            self.assertNotIn('liveSite', worker.conv.settings)
            d = worker.conv.editor.prepare([{'op': 'store.set_hours', 'args': {'hours': NEW_HOURS}}])['draft']
            self.assertEqual(d['environment']['env'], 'sandbox')
            self.assertEqual(worker.conv.editor.apply(d['change_id'], d['draft_hash'])['result'], 'applied')

    def test_per_target_switch_preserves_other_target_and_bumps_generation(self):
        path = drill.SwitchBack.live_json(self)
        host.set_mode(path, 'live')
        host.set_mode(path, 'live', 'till')
        host.set_mode(path, 'sandbox', 'till')
        cfg = json.loads(path.read_text())
        self.assertEqual((cfg['live'], cfg['mode_gen']), (['site'], 3))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        host.set_mode(path, 'sandbox')
        self.assertEqual(json.loads(path.read_text())['live'], [])

    def test_invalid_host_mode_and_publish_cli_fail_closed(self):
        from hass import host, publish_live
        for over in ({'live': None}, {'live': True}, {'off': None}, {'mode_gen': '1'}):
            path = self.host_json()
            cfg = {**json.loads(path.read_text()), **over}
            self.write(path, json.dumps(cfg).encode())
            with self.subTest(over=over), self.assertRaises(host.HostConfigError):
                host.load_host(path)
        path = self.host_json(approvals='private')
        with patch.object(publish_live, 'LiveEditor') as live, patch('builtins.print'):
            self.assertEqual(publish_live.main(['baseline', '--host', str(path)]), 1)
        live.assert_not_called()


class LiveRoutingTests(pl.ReleaseCase):
    def adapter(self, mode):
        ids = {('site', 'sandbox'): str(self.repo.wt), ('site', 'live'): 'fixture-remote-main'}
        return sandbox_editor.SiteEditor(self.repo.state, sandbox.Gate(lambda: mode, lambda: ids),
                                          lambda: self.live, registry=self.live.registry, clock=lambda: self.now)

    def test_sandbox_changes_private_writer_but_not_published_commit_or_till(self):
        mode = {'approvals': 'private'}
        ed = self.adapter(mode)
        draft = ed.prepare([{'op': HOURS, 'args': {'hours': NEW_HOURS}}])['draft']
        self.assertEqual(ed.apply(draft['change_id'], draft['draft_hash'])['result'], 'applied')
        self.assertEqual(self.push_calls, 0)
        self.assertEqual(git(self.site, 'rev-parse', 'HEAD'), self.site_before)
        mode.update(live=['site'], mode_gen=1)
        undo = ed.prepare([{'op': 'history.revert', 'args': {'changeId': draft['change_id']}}])['draft']
        self.assertEqual(ed.apply(undo['change_id'], undo['draft_hash'])['result'], 'applied')
        self.assertEqual(self.push_calls, 0)

    def test_explicit_site_live_uses_existing_release_gates(self):
        ed = self.adapter({'approvals': 'live', 'live': ['site']})
        draft = ed.prepare([{'op': HOURS, 'args': {'hours': NEW_HOURS}}])['draft']
        self.assertEqual(ed.apply(draft['change_id'], draft['draft_hash'])['result'], 'applied')
        self.assertEqual(self.push_calls, 1)

    def cli_run(self, mode, ids, *argv):
        from hass import publish_live
        cfg = {**mode, 'state': str(self.repo.state), 'release': self.cfg}
        self.live.environment_guard = None
        with patch.object(host, 'load_host', return_value=cfg), patch.object(host, 'site_gate', return_value=sandbox.Gate(lambda: mode, lambda: ids)), \
             patch.object(publish_live, 'LiveEditor', return_value=self.live), patch('builtins.print') as out:
            code = publish_live.main([*argv, '--host', str(self.hostdir / 'host.json')])
        return code, json.loads(out.call_args[0][0])

    def test_cli_revert_last_publishes_bound_undo_after_bound_live_change(self):
        mode = {'approvals': 'live', 'live': ['site']}
        ids = {('site', 'sandbox'): str(self.repo.wt), ('site', 'live'): 'fixture-remote-main'}
        ed = self.adapter(mode)
        draft = ed.prepare([{'op': HOURS, 'args': {'hours': NEW_HOURS}}])['draft']
        self.assertEqual(ed.apply(draft['change_id'], draft['draft_hash'])['result'], 'applied')
        pushes = self.push_calls
        code, result = self.cli_run(mode, ids, 'revert-last')
        self.assertEqual((code, result['result']), (0, 'ok'))
        self.assertEqual(result['undid'], draft['change_id'])
        self.assertEqual(self.push_calls, pushes + 1)

    def cli_retry(self, mode, ids, cid):
        from hass import publish_live
        cfg = {**mode, 'state': str(self.repo.state), 'release': self.cfg}
        self.live.environment_guard = None
        with patch.object(host, 'load_host', return_value=cfg), patch.object(host, 'site_gate', return_value=sandbox.Gate(lambda: mode, lambda: ids)), \
             patch.object(publish_live, 'LiveEditor', return_value=self.live), patch('builtins.print') as out:
            code = publish_live.main(['retry', cid, '--host', str(self.hostdir / 'host.json')])
        return code, json.loads(out.call_args[0][0])

    def stuck_live_change(self, mode, ids):
        ed = self.adapter(mode)
        draft = ed.prepare([{'op': HOURS, 'args': {'hours': NEW_HOURS}}])['draft']
        def lose(cwd, args):
            if args[0] == 'push': raise subprocess.TimeoutExpired('git', 60)
        self.fault = lose
        ed.apply(draft['change_id'], draft['draft_hash'])
        self.live.reconcile()
        self.now += timedelta(seconds=120)
        self.live.reconcile()
        self.fault = None
        self.assertEqual(self.entry()['state'], 'not-published')
        return draft, self.entry()['change_id'], self.push_calls

    def test_cli_retry_holds_when_recorded_target_changed_or_journal_unbound(self):
        mode = {'approvals': 'live', 'live': ['site']}
        ids = {('site', 'sandbox'): str(self.repo.wt), ('site', 'live'): 'fixture-remote-main'}
        draft, cid, pushes = self.stuck_live_change(mode, ids)
        changed = {**ids, ('site', 'live'): 'another-checkout'}
        self.assertEqual(self.cli_retry(mode, changed, cid)[1]['result'], 'env-gone')
        self.assertEqual(self.push_calls, pushes)
        path = self.repo.state / 'drafts' / f"{draft['change_id']}.json"
        saved = path.read_text()
        legacy = json.loads(saved)
        del legacy['environment']
        path.write_text(json.dumps(legacy))
        self.assertEqual(self.cli_retry(mode, ids, cid)[1]['result'], 'env-gone')
        self.assertEqual(self.push_calls, pushes)
        path.write_text(saved)
        code, result = self.cli_retry(mode, ids, cid)
        self.assertEqual((code, result['result']), (0, 'ok'))
        self.assertEqual(self.push_calls, pushes + 1)


# Reuse the real bare-Git fixture, not all its already-covered inherited tests.
for _name in vars(pl.ReleaseCase):
    if _name.startswith('test_') and _name not in vars(LiveRoutingTests):
        setattr(LiveRoutingTests, _name, None)


if __name__ == '__main__':
    unittest.main()
