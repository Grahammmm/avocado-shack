"""Exercise the actual stage port and owner runner; no model or live sender is reachable."""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hass import preview, sandbox, sandbox_editor
from hass.npp import assets, stages, stages_for
from hass.npp.job import Work
from hass.tests import test_npp_job as job_fixture, test_preview
from hass.tests.test_editor import git


class StageTests(unittest.TestCase):
    def setUp(self):
        self.case = case = job_fixture.JobTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        gate = sandbox.Gate(lambda: {'approvals': 'private'}, lambda: {('site', 'sandbox'): str(case.repo.wt)})
        guarded = sandbox_editor.SiteEditor(case.repo.state, gate, self.deny, clock=lambda: case.now)
        self.conv = case.conv
        self.conv.editor = guarded
        self.conv.previewer = SimpleNamespace(capture=self.capture)
        self.port = stages_for(self.conv, assets())
        if self.port is None:
            self.skipTest('requires the real staged editor adapter')
        self.conv.npp.stages = self.port
        self.reading = dict(item='Wild Plum Jam', kind='food', is_product=True, brand_on_label=None,
                            category_guess='pantry', confidence=dict(item=1, category=1),
                            has_person_or_screen=False, label_words=[])
        self.port.identifier.read = lambda _: SimpleNamespace(evidence=self.reading)
        self.port.selector = None
        self.port.mapper = self.deny
        self.enterContext(patch.object(stages.research_hermes, 'run', side_effect=self.deny))
        self.enterContext(patch.object(stages.picture, 'read_text', return_value=''))
        self.enterContext(patch.object(stages.photos, '_sharpness', return_value=1))
        self.saved = []
        persist = self.port.persist

        def record(draft):
            self.saved.append(draft)
            return persist(draft)

        self.port.persist = record

    def deny(self, *_args, **_opts):
        raise AssertionError('fixture attempted external I/O')

    def capture(self, files, target, out, assets=None):
        # Synthetic phone shot only for deterministic runner tests. The full browser test below
        # uses real S8 evidence; here the contract under test is S7/Jobs ordering, not Chromium.
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(job_fixture.PNG)
        return dict(ok=True, png=str(out), cardEvidence={
            'productId': target['id'], 'pngSha256': hashlib.sha256(job_fixture.PNG).hexdigest(),
            'fragments': [{'text': text, 'role': None} for text in (target['name'], target['price'], target['description'])],
            'priceIndex': 1, 'makerCount': None,
        })

    def start_render(self, text='sell $7 each; cost $3; qty 12'):
        self.case.say(text, photos=1)
        self.case.flush()
        self.case.scheduler.run()
        self.case.flush()  # plan freezes the version
        self.case.flush()  # worker now queued but not executed
        self.assertEqual(len(self.case.scheduler.steps), 1)

    def no_draft(self):
        self.assertFalse(list((self.case.repo.state / 'drafts').glob('*.json')))
        self.assertEqual(self.conv.db.execute('SELECT count(*) FROM drafts').fetchone()[0], 0)
        self.assertFalse(self.case.transport.cards)
        self.case.assert_unpublished()

    def test_missing_price_is_exact_s3_question_not_a_draft(self):
        self.case.say('new jam', photos=1)
        self.case.work()
        self.assertEqual(self.case.transport.texts, [self.conv.npp.replies['questions']['ask_price_unit']])
        self.no_draft()

    def test_s3_duplicate_gate_uses_only_the_bound_answer(self):
        content = self.port.catalog()
        content.products.append({'name': self.reading['item'], 'status': 'active'})
        self.port.catalog = lambda: content
        self.case.say('sell $7 each', photos=1)
        self.case.work()
        self.assertEqual(self.case.transport.texts[-1], stages.missing.DUPLICATE)
        self.case.say('A jar of jam')
        self.case.work()
        self.assertIsNone(self.case.version(1))
        self.case.say('yes')
        self.case.flush()
        self.case.scheduler.run()
        self.case.flush()
        self.assertIsNotNone(self.case.version(1))
        self.no_draft()

    def test_stale_render_tickets_never_persist_even_if_worker_runs(self):
        # Each subcase gets its own scheduler/DB. A render may finish after invalidation.
        for index, reason in enumerate(('cancel', 'supersede', 'expire')):
            if index:
                self.setUp()
            with self.subTest(reason=reason):
                self.start_render()
                if reason == 'cancel':
                    self.case.say('cancel')
                elif reason == 'supersede':
                    self.case.say('make it $8')
                else:
                    self.case.now += timedelta(hours=24)
                future, _, _ = self.case.scheduler.steps[0]
                self.case.scheduler.run()
                self.assertTrue(future.result().candidate)  # prove a valid worker result, not a coincidental refusal
                self.case.flush()
                self.assertEqual(self.saved, [])
                self.no_draft()
                if reason == 'supersede':
                    self.case.work()
                    self.assertEqual(len(self.saved), 1)
                    self.assertEqual(self.saved[0]['ops'][-1]['args']['sellingPrice'], '8.00 each')

    def test_checked_current_ticket_persists_exactly_the_validated_hash(self):
        self.start_render()
        self.case.scheduler.run()
        self.no_draft()  # validation has already finished on the worker
        self.case.work()
        [draft] = self.saved
        actual = self.conv.editor.show(draft['change_id'])['draft']
        self.assertEqual(actual['draft_hash'], draft['draft_hash'])
        self.assertEqual(self.case.version(1)['draft_hash'], draft['draft_hash'])
        self.assertEqual(self.case.version(1)['state'], 'queued')

    def test_stale_base_and_late_checks_never_queue_or_leave_a_draft(self):
        for index, refusal in enumerate(('S7', 'S8', 'exception', 'stale')):
            if index:
                self.setUp()
            with self.subTest(refusal=refusal):
                self.start_render()
                if refusal == 'S7':
                    # Source and raw-picture checks pass. Only the final S7 OCR sees the private number.
                    read = self.enterContext(patch.object(stages.picture, 'read_text', side_effect=['', '', '12']))
                elif refusal == 'S8':
                    self.conv.previewer.capture = lambda *_a, **_k: {'ok': False, 'png': None}
                elif refusal == 'exception':
                    self.conv.previewer.capture = self.deny
                if refusal == 'exception':
                    # The fixture executor normally executes synchronously; deliver an exceptional future as the real executor would.
                    future, fn, args = self.case.scheduler.steps.pop(0)
                    with self.assertRaises(AssertionError) as raised:
                        fn(*args)
                    future.set_exception(raised.exception)
                else:
                    self.case.scheduler.run()
                if refusal == 'S7':
                    self.assertEqual(read.call_count, 3)

                if refusal == 'stale':
                    path = self.case.repo.wt / 'hass' / 'content' / 'store.json'
                    path.write_bytes(path.read_bytes() + b'\n')
                    git(self.case.repo.wt, 'add', str(path))
                    git(self.case.repo.wt, 'commit', '-s', '-m', 'fixture revision drift')
                    self.case.base = self.case.repo.head()
                self.case.work()
                self.assertIn(self.conv.npp.replies['guards']['render_failed'], self.case.transport.texts)
                self.assertEqual(self.case.version(1)['state'], 'superseded')
                self.assertEqual(len(self.saved), int(refusal == 'stale'))
                self.no_draft()

    def test_only_owner_stated_or_allowlisted_new_maker_can_request_research(self):
        # Prove both decision branches and the eligible URL passed across the boundary; no search or web I/O.
        work = Work('fixture', {}, None, self.case.now + timedelta(seconds=100))
        town, url = 'Oakville', 'https://example.com/'
        for state, supplied_town, supplied_url, allow, expected in (
            ('known', town, url, False, None), ('near', town, url, False, None),
            ('new', '', url, False, None), ('new', town, '', False, None),
            ('new', town, url, False, url), ('new', town, '', True, url),
        ):
            with self.subTest(state=state, town=supplied_town, url=supplied_url, allow=allow):
                self.port.sources['allowlist'] = ([{'maker': 'elm farm', 'domain': 'example.com', 'added_by': 'G', 'reviewed_in': 'fixture'}] if allow else [])
                with patch.object(stages.research_hermes, 'run', return_value=SimpleNamespace(story_facts=())) as run:
                    self.port._research(work, stages.missing.Maker(state, 'Elm Farm'), supplied_town, supplied_url, {})
                if expected is None:
                    run.assert_not_called()
                else:
                    self.assertEqual(run.call_args.kwargs['owner_url'], expected)
                    self.assertEqual(run.call_args.kwargs['web'].search('untrusted'), ())

    def test_picture_retake_never_becomes_a_candidate(self):
        self.reading['has_person_or_screen'] = True
        self.start_render()
        self.case.work()
        self.assertEqual(self.case.job()['state'], 'retake')
        self.assertEqual(self.saved, [])
        self.no_draft()

    def test_rejected_polish_uses_existing_raw_bytes(self):
        self.conv.settings.update(houseRender=True, itemIntake=True, photoPolish=True)
        with patch.object(stages.photo_polish, 'start', side_effect=self.deny), \
                patch.object(stages.photo_polish, 'enabled', return_value=True), \
                patch.object(stages.photo_polish, 'polished', return_value=None) as settled:
            req = {'attachments': [self.case.repo.store(job_fixture.JPG)]}
            self.conv.settings['mediaRoot'] = str(self.case.repo.media)
            work = Work('fixture', req, None, self.case.now + timedelta(seconds=100))
            frozen, _, _, _ = self.port._picture(work, {'photo': req['attachments'][0], 'labelWords': [],
                                                        'personOrScreen': False}, frozenset(), local=True)
            settled.assert_called_once()
            self.assertEqual(frozen.variant, 'raw')
            self.assertEqual(frozen.image_sha256, hashlib.sha256(self.port._photo(req['attachments'][0])).hexdigest())

    @unittest.skipUnless(preview.Previewer('.').env.get('PLAYWRIGHT_MODULE'), 'Playwright not installed')
    def test_known_maker_reaches_card_out_with_real_renderer_and_binding(self):
        case = self.case
        test_preview.BrowserCase.make_previewer(SimpleNamespace(repo=case.repo, env=None))
        self.conv.previewer = preview.Previewer(case.repo.wt, viewports=('phone',))
        makers = case.repo.wt / 'hass' / 'content' / 'makers.json'
        data = json.loads(makers.read_text())
        data['makers']['Elm Farm'] = {'name': 'Elm Farm', 'place': 'Oakville, California', 'url': 'https://example.com/'}
        makers.write_text(json.dumps(data))
        git(case.repo.wt, 'add', str(makers))
        git(case.repo.wt, 'commit', '-s', '-m', 'fixture maker')
        case.base = case.repo.head()
        self.start_render('made by Elm Farm; sell $7 each; cost $3; qty 12')
        case.work()
        self.assertTrue(case.transport.cards, case.transport.texts)
        self.assertEqual(self.saved[0]['records'][-1]['after']['producerKey'], 'Elm Farm')
        case.confirm(1)
        self.assertEqual(case.job()['state'], 'card_out')
        case.assert_unpublished()
