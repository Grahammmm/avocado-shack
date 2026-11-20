"""Offline contracts for the staged editor boundary."""
import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hass import editor, sandbox, sandbox_editor
from hass.npp.validate import dom_problem
from hass.tests import fixture_ops
from hass.tests.test_editor import HOURS, NEW_HOURS
from hass.tests.test_photo_new_product import ADD
from hass.tests.test_set_photo import FIXTURES, PhotoRepo, git


def snapshot(root):
    return {str(p.relative_to(root)): ('link', p.readlink()) if p.is_symlink() else
            ('file', hashlib.sha256(p.read_bytes()).hexdigest()) if p.is_file() else ('dir',)
            for p in root.rglob('*')}


class CandidateTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state, self.wt = Path(tmp.name) / 'state', Path(tmp.name) / 'writer'
        self.state.mkdir(mode=0o700)
        (self.state / 'config.json').write_text(json.dumps({'worktree': str(self.wt)}))
        for rel in editor.REVISION_PATHS:
            path = self.wt / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((editor.REPO_ROOT / rel).read_bytes())
        (self.wt / 'storefront-mockup').symlink_to(editor.REPO_ROOT / 'storefront-mockup')
        self.ops = [{'op': HOURS, 'args': {'hours': NEW_HOURS}}]
        self.kw = {'state': self.state, 'registry': fixture_ops.registry()}

    def candidate(self, **kwargs):
        out = editor.candidate({'ops': self.ops}, **self.kw, **kwargs)
        self.assertEqual(out['result'], 'ok', out)
        return out['draft']

    def persist(self, draft):
        return editor.persist_candidate(draft, state=self.state)

    def draft_path(self, draft):
        return self.state / 'drafts' / (draft['change_id'] + '.json')

    def test_interruption_between_candidate_and_persist_leaves_no_draft(self):
        # A capture exception must not expose an eagerly persisted approval.
        def stop_after_render(render):
            self.assertEqual(render['result'], 'ok', render)
            raise RuntimeError('capture interrupted')

        before = snapshot(self.state), snapshot(self.wt)
        with self.assertRaisesRegex(RuntimeError, 'capture interrupted'):
            draft = self.candidate()
            stop_after_render(editor.render_candidate(draft, **self.kw))
            self.persist(draft)
        self.assertEqual((snapshot(self.state), snapshot(self.wt)), before)

    def test_persist_keeps_exact_candidate_without_recompute_or_rewrite(self):
        # Re-running compute, substituting a draft, or changing its timestamp on retry is a regression.
        draft = self.candidate()
        with patch.object(editor, '_compute', side_effect=AssertionError('persist recomputed content')):
            self.assertEqual(self.persist(draft), {'result': 'ok', 'draft': draft})
            path = self.draft_path(draft)
            self.assertEqual(json.loads(path.read_bytes()), draft)
            before = path.stat().st_mtime_ns
            self.assertEqual(self.persist(draft), {'result': 'ok', 'draft': draft})
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_stale_base_tampered_seed_and_wrong_id_are_refused_without_writes(self):
        # Every hashed field is binding; even the untouched original is stale on a new base.
        draft = self.candidate(environment={'env': 'sandbox'})
        cases = {
            'ops': [{'op': HOURS, 'args': {'hours': ['Closed Sunday']}}],
            'assets': {}, 'environment': {'env': 'live'}, 'hash_attempt': 1,
            'change_id': 'chg-000000000000',
        }
        before = snapshot(self.state)
        for field, value in cases.items():
            with self.subTest(field=field):
                self.assertEqual(self.persist({**draft, field: value}), {'result': 'stale'})
                self.assertEqual(snapshot(self.state), before)
        path = self.wt / editor.REVISION_PATHS[0]
        path.write_bytes(path.read_bytes() + b'\n')
        self.assertEqual(self.persist(draft), {'result': 'stale'})
        self.assertEqual(snapshot(self.state), before)

    def test_persist_refuses_a_spent_id_or_conflicting_draft_and_retries_get_a_new_id(self):
        draft = self.candidate()
        wrong = self.draft_path(draft)
        wrong.parent.mkdir()
        wrong.write_text(json.dumps({**draft, 'draft_hash': 'sha256:other'}))
        before = snapshot(self.state)
        self.assertEqual(self.persist(draft), {'result': 'stale'})
        self.assertEqual(snapshot(self.state), before)
        wrong.unlink()
        change = self.state / 'changes' / wrong.name
        change.parent.mkdir()
        change.write_text('{"state": "failed"}')
        before = snapshot(self.state)
        self.assertEqual(self.persist(draft), {'result': 'stale'})
        self.assertEqual(snapshot(self.state), before)
        retry = self.candidate()
        self.assertNotEqual(retry['change_id'], draft['change_id'])
        self.assertEqual(self.persist(retry), {'result': 'ok', 'draft': retry})
        self.assertFalse(wrong.exists())
        # A same-hash unbound retry from an older editor has no attempt field.
        legacy = {key: value for key, value in retry.items() if key != 'hash_attempt'}
        self.draft_path(retry).write_text(json.dumps(legacy))
        before = snapshot(self.state)
        self.assertEqual(editor.prepare({'ops': self.ops}, **self.kw), {'result': 'ok', 'draft': legacy})
        self.assertEqual(snapshot(self.state), before)

    def test_persist_refuses_while_writer_holds_lock_without_creating_a_draft(self):
        draft = self.candidate()
        with editor._writer_lock(self.state) as held:
            self.assertTrue(held)
            before = snapshot(self.state)
            self.assertEqual(self.persist(draft), {'result': 'busy'})
            self.assertEqual(snapshot(self.state), before)

    def test_persist_refuses_a_drafts_directory_link_into_the_worktree(self):
        draft = self.candidate()
        (self.state / 'drafts').symlink_to(self.wt, target_is_directory=True)
        before = snapshot(self.state), snapshot(self.wt)
        self.assertEqual(self.persist(draft), {'result': 'stale'})
        self.assertEqual((snapshot(self.state), snapshot(self.wt)), before)

    def test_sandbox_gate_refuses_all_stages_after_switch_off(self):
        # A previously resolved binding is not authority to render or persist after an off switch.
        mode: dict = {'approvals': 'private'}
        gate = sandbox.Gate(lambda: mode, lambda: {('site', 'sandbox'): str(self.wt)})

        def no_live():
            self.fail('staging must not construct a live editor')

        ed = sandbox_editor.SiteEditor(self.state, gate, no_live, registry=self.kw['registry'])
        before = snapshot(self.state), snapshot(self.wt)
        out = ed.candidate(self.ops)
        self.assertEqual(out['result'], 'ok', out)
        draft = out['draft']
        self.assertEqual(draft['environment']['env'], 'sandbox')
        self.assertEqual(ed.render_candidate(draft)['result'], 'ok')
        mode['off'] = ['site']
        for call, arg in ((ed.candidate, self.ops), (ed.render_candidate, draft), (ed.persist_candidate, draft)):
            with self.subTest(stage=call.__name__):
                self.assertEqual(call(arg)['result'], 'refused')
                self.assertEqual((snapshot(self.state), snapshot(self.wt)), before)
        mode.pop('off')
        self.assertEqual(ed.persist_candidate(draft)['draft'], draft)
        self.assertEqual(ed.prepare(self.ops)['draft'], draft)


class PhotoCandidateTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        sha = self.repo.store((FIXTURES / 'pixel.jpg').read_bytes())
        self.request = {'ops': [{'op': 'product.add', 'args': {**ADD, 'photo': sha}}]}

    def candidate(self):
        out = editor.candidate(self.request, state=self.repo.state)
        self.assertEqual(out['result'], 'ok', out)
        return out['draft']

    def test_photo_candidate_and_render_write_no_editor_state_or_worktree_before_late_refusal(self):
        # Exercise real photo compute, not a mock that cannot leave a draft or site image.
        before = snapshot(self.repo.state), snapshot(self.repo.wt)
        draft = self.candidate()
        self.assertEqual((snapshot(self.repo.state), snapshot(self.repo.wt)), before)
        self.assertEqual(editor.render_draft(draft['change_id'], state=self.repo.state)['result'], 'not-found')
        rendered = editor.render_candidate(draft, state=self.repo.state)
        self.assertEqual(rendered['result'], 'ok', rendered)
        self.assertTrue(rendered['assets'])
        self.assertEqual((snapshot(self.repo.state), snapshot(self.repo.wt)), before)
        # The fixture capture includes a forbidden private amount. The real DOM
        # verdict rejects it after a successful editor render, before persistence.
        name = ADD['name']
        problem = dom_problem([name, '$7.00 each', 'Cost $3'], 1, '7.00 each', name, private={3, 300})
        if problem is None:
            editor.persist_candidate(draft, state=self.repo.state)
        self.assertEqual(problem, 'card-number')
        self.assertEqual((snapshot(self.repo.state), snapshot(self.repo.wt)), before)

    def test_edited_photo_asset_map_is_refused_and_apply_rechecks_reused_photo_output(self):
        # Persist binds queued output hashes; only apply knows whether site output still matches.
        queued = self.candidate()
        [[asset, digest]] = queued['assets'].items()
        tampered = deepcopy(queued)
        tampered['assets'][asset] = 'sha256:' + '0' * 64
        before = snapshot(self.repo.state), snapshot(self.repo.wt)
        self.assertEqual(editor.persist_candidate(tampered, state=self.repo.state), {'result': 'stale'})
        self.assertEqual((snapshot(self.repo.state), snapshot(self.repo.wt)), before)
        rendered = editor.render_candidate(queued, state=self.repo.state)
        site_path = 'storefront-mockup/' + asset
        photo = rendered['assets'][site_path]
        self.assertEqual('sha256:' + hashlib.sha256(photo).hexdigest(), digest)
        path = self.repo.wt / site_path
        path.write_bytes(photo)
        git(self.repo.wt, 'add', '--', site_path)
        git(self.repo.wt, 'commit', '-qm', 'seed reusable photo')
        reused = self.candidate()
        self.assertNotIn('assets', reused)
        self.assertEqual(editor.persist_candidate(reused, state=self.repo.state)['draft'], reused)
        git(self.repo.wt, 'rm', '--', site_path)
        git(self.repo.wt, 'commit', '-qm', 'remove reusable photo')
        before = snapshot(self.repo.wt), self.repo.head()
        out = editor.apply(reused['change_id'], reused['draft_hash'], state=self.repo.state)
        self.assertEqual(out['result'], 'stale', out)
        self.assertEqual((snapshot(self.repo.wt), self.repo.head()), before)
        self.assertFalse((self.repo.state / 'journal').exists())
