"""Offline bundle coverage: real till engine + fake transport, and real bare-repo releases."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


from hass.clover import bundle as b, drafts as d
from hass.clover.apply import ApplyEngine
from hass.clover.chat import SITE_NOT_YET
from hass.clover.client import CloverWriteClient
from hass.clover.config import from_settings
from hass.clover.credential import Token
from hass.clover.mapper import parse_item
from hass.conversation import sender_key
from hass.tests import test_clover_apply as till_fixture
from hass.tests.test_clover_client import NoNetwork, FAKE_TOKEN
from hass.tests.test_conversation import OWNER, CHAT, SETTINGS



class Crash(BaseException): pass


class Site:
    def __init__(self):
        self.settings = {**SETTINGS, 'ownerKeys': frozenset({sender_key(OWNER)})}
        self.conv = SimpleNamespace(_paused=lambda: self.paused)
        self.paused = self.stop = self.refuse = False
        self.version, self.calls, self.drafts, self.live = 0, [], {}, set()

    def stopped(self): return self.stop

    def prepare(self, ops):
        cid = 'chg-' + str(len(self.drafts))
        self.drafts[cid] = (self.version, ops)
        return {'result': 'ok', 'draft': {'change_id': cid, 'draft_hash': 'fixture-hash'}}

    def apply(self, cid, digest, chat):
        self.calls.append((cid, digest, chat))
        if self.refuse or self.drafts[cid][0] != self.version: return {'result': 'stale'}
        self.live.add(cid)
        self.version += 1
        return {'result': 'applied'}

    def went_live(self, cid): return cid in self.live


class BothTests(NoNetwork):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.cfg = from_settings({'environment': 'sandbox', 'merchantId': 'FAKEMERCH0001', 'tokenFile': '/fixture/read',
                                  'writeTokenFile': '/fixture/write', 'writes': True, 'liveApproved': True,
                                  'categoryMap': {'pantry': 'Pantry'}})
        self.till = till_fixture.Till()
        token = mock.patch('hass.clover.apply.load_write_token', return_value=Token(FAKE_TOKEN))
        self.token = token.start()
        self.addCleanup(token.stop)
        self.engine = ApplyEngine(self.state, self.cfg,
            lambda token: CloverWriteClient('FAKEMERCH0001', token, self.transport, min_interval=0), mike=(OWNER, CHAT), clock=lambda: 1000)
        self.site, self.links, self.journal = Site(), [], b.BundleJournal(self.state)
        self.ops = [{'op': 'product.edit', 'args': {'id': 'photo-product-001', 'description': 'Fresh fruit.'}}]

    def transport(self, req):
        result = self.till(req)
        if req.method == 'POST' and req.url.endswith('/items'):
            self.till.items['NEWITEM']['itemStock'] = {'quantity': 0, 'modifiedTime': 1}
        return result

    def draft(self):
        return d.build_set_price(parse_item(self.till.items['FAKEITEM00001']), 1400, self.cfg)

    def create(self):
        draft = d.build_create_item('Synthetic honey', 1250, 'pantry', [], self.cfg, categories=[('CAT', 'Pantry')])
        return replace(draft, after={**draft.after, 'stock': '12'},
                       lines=tuple(x for x in draft.lines if not x.startswith('  Count:')) + ('  Count: 12',))

    def propose(self, draft=None, **kw):
        return b.propose(**dict(site_ops=self.ops, till_draft=draft or self.draft(), link=None, sender=OWNER, chat=CHAT,
                               journal=self.journal, engine=self.engine, site=self.site) | kw)

    def yes(self, code, **kw):
        return b.apply(code, **dict(sender=OWNER, chat=CHAT, journal=self.journal, engine=self.engine, site=self.site,
                                   link_writer=lambda *row: self.links.append(row), now=1001) | kw)

    def restart(self):
        self.journal = b.BundleJournal(self.state)
        return b.reconcile(journal=self.journal, engine=self.engine, site=self.site, now=1002)

    def writes(self): return [r for r in self.till.seen if r.method != 'GET']

    def test_one_code_all_parts_and_one_yes(self):
        self.ops = [{'op': name, 'args': args} for name, args in [
            ('maker.add', {'key': 'Synthetic'}), ('product.add', {'name': 'Synthetic honey'}),
            ('product.set_photo', {'id': 'photo-product-175', 'photo': 'fixture'}),
            ('product.set_availability', {'id': 'photo-product-175', 'available': 'yes'})]]
        draft = self.create()
        code, text = self.propose(draft, link={'product_id': 'photo-product-175', 'sku': draft.after['sku']})
        self.assertIn('yes ' + code, text)
        row = self.journal.get(code)
        self.assertEqual(len(row['bundle']['site_ops']), 4)
        self.assertIn('The website shows no prices', text)
        self.assertEqual(self.yes(code)[0], 'done')
        self.assertTrue(self.engine._matches(draft.to_dict(), self.till.items['NEWITEM']))
        self.assertEqual(self.links, [('photo-product-175', 'NEWITEM', draft.after['sku'])])
        self.assertEqual(len(self.writes()), 3)
        self.assertEqual(len(self.site.calls), 1)
        self.assertEqual(self.journal.get(code)['site'], 'live')
        self.yes(code)
        self.assertEqual(len(self.writes()), 3)
        self.assertEqual(set(self.journal.get(code)['notifications']), {'owner', 'operator'})
        self.assertEqual(self.journal.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.journal.path.parent.stat().st_mode & 0o777, 0o700)
        with self.journal.db() as db: self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'delete')

    def test_create_count_failure_partial_undo_and_create_failure_no_site(self):
        code, _ = self.propose(self.create())
        self.till.mismatch = True  # A creates normally; B's real engine read-back fails.
        self.assertEqual(self.yes(code)[0], 'partial')
        self.till.mismatch = False
        self.assertFalse(self.site.calls)
        self.assertFalse(self.links)
        count = len(self.writes())
        self.restart(); self.yes(code)
        self.assertEqual(self.journal.get(code)['state'], 'partial')
        self.assertEqual(len(self.writes()), count)
        undo, _ = b.undo(code, sender=OWNER, chat=CHAT, journal=self.journal, engine=self.engine, site=self.site)
        self.assertEqual(self.yes(undo)[0], 'done')
        self.assertTrue(self.till.items['NEWITEM']['hidden'])
        self.assertEqual(self.journal.get(code)['state'], 'undone')
        self.assertFalse(self.site.calls)
        code, _ = self.propose(self.create())
        count = len(self.writes())
        self.assertEqual(self.yes(code)[0], 'failed')  # SKU collision refuses A before its first write.
        self.assertEqual(len(self.writes()), count)
        self.assertFalse(self.site.calls)

    def test_create_count_crash_reconciles_each_engine_step_without_replay(self):
        for point in ('after-create', 'during-count', 'after-count'):
            with self.subTest(point=point):
                fixture = BothTests('runTest'); fixture.setUp(); self.addCleanup(fixture.doCleanups)
                code, _ = fixture.propose(fixture.create())
                original = fixture.engine.handle
                def crash(text, **kw):
                    if text != 'yes ' + code and point == 'during-count': fixture.till.crash = True
                    result = original(text, **kw)
                    if (text == 'yes ' + code) == (point == 'after-create'): raise Crash()
                    return result
                with mock.patch.object(fixture.engine, 'handle', side_effect=crash), self.assertRaises((Crash, KeyboardInterrupt)):
                    fixture.yes(code)
                count = len(fixture.writes())
                expected = 'split' if point == 'after-count' else 'partial'
                fixture.restart(); fixture.restart()
                self.assertEqual(fixture.journal.get(code)['state'], expected)
                fixture.yes(code)
                # A confirmed B may continue the website only on the explicit second yes.
                self.assertEqual(fixture.journal.get(code)['state'], 'done' if point == 'after-count' else expected)
                self.assertEqual(len(fixture.writes()), count)
                self.assertEqual(set(fixture.journal.get(code)['notifications']), {'owner', 'operator'})

    def test_undo_keeps_newer_till_but_still_reverts_site(self):
        code, _ = self.propose()
        self.assertEqual(self.yes(code)[0], 'done')
        self.till.items['FAKEITEM00001']['modifiedTime'] += 1
        undo, _ = b.undo(code, sender=OWNER, chat=CHAT, journal=self.journal, engine=self.engine, site=self.site)
        count = len(self.writes())
        state, text = self.yes(undo)
        self.assertEqual(state, 'done')
        self.assertIn('the till was not changed', text)
        self.assertEqual(len(self.writes()), count)
        self.assertEqual(len(self.site.calls), 2)

    def test_failure_uncertainty_and_retry_never_repeat_till(self):
        code, _ = self.propose()
        self.till.mismatch = True
        self.assertEqual(self.yes(code)[0], 'failed')
        self.assertFalse(self.site.calls)
        self.till.mismatch = False
        code, _ = self.propose()
        self.site.refuse = True
        state, text = self.yes(code)
        self.assertEqual(state, 'split')
        self.assertIn(SITE_NOT_YET, text)
        self.assertIn('retry', text)
        count = len(self.writes())
        self.restart()
        self.site.refuse = False
        self.assertEqual(self.yes(code)[0], 'done')
        self.assertEqual(len(self.writes()), count)
        code, _ = self.propose(d.build_set_price(parse_item(self.till.items['FAKEITEM00001']), 1500, self.cfg))
        self.till.lose = True
        self.assertEqual(self.yes(code)[0], 'till-uncertain')
        count = len(self.writes())
        self.restart(); self.yes(code)
        self.assertEqual(len(self.writes()), count)
        self.assertEqual(self.journal.get(code)['till'], 'uncertain')

    def test_read_only_gates_identity_expiry_hash_and_no_runner(self):
        with mock.patch('subprocess.run') as runner, mock.patch('hass.clover.apply.load_write_token', side_effect=AssertionError('token read')):
            for disabled in ({'writes': False}, {'write_token_file': ''}):
                self.engine.config = replace(self.cfg, **disabled)
                code, text = self.propose()
                self.assertIn("I can't add it to the till yet", text)
                self.assertIsNone(self.journal.get(code)['bundle']['till'])
                self.assertEqual(self.yes(code)[0], 'done')
            runner.assert_not_called()
        self.engine.config = self.cfg
        for kwargs in ({'sender': 'stranger'}, {'chat': 'iMessage;+;group'}):
            with self.assertRaises(d.DraftRefused): self.propose(**kwargs)
        code, _ = self.propose()
        for kwargs in ({'sender': 'stranger'}, {'chat': 'other'}, {'now': 1700}):
            with self.assertRaises(d.DraftRefused): self.yes(code, **kwargs)
        for attr in ('paused', 'stop'):
            setattr(self.site, attr, True)
            with self.assertRaises(d.DraftRefused): self.yes(code)
            setattr(self.site, attr, False)
        with mock.patch('subprocess.run') as runner:
            self.assertEqual(self.yes(code)[0], 'done')
            runner.assert_not_called()
        code, _ = self.propose(d.build_set_price(parse_item(self.till.items['FAKEITEM00001']), 1500, self.cfg))
        changed = self.journal.get(code)['bundle']; changed['site_ops'][0]['args']['description'] = 'Other'
        self.journal.advance(code, 'proposed', bundle=changed)
        with self.assertRaises(d.DraftRefused): self.yes(code)
        self.engine.handle('stop changes', sender=OWNER, chat=CHAT)
        with self.assertRaises(d.DraftRefused): self.propose()

    def test_crash_after_till_before_site_step_visible_split(self):
        code, _ = self.propose()
        with mock.patch.object(b, '_site_apply', side_effect=Crash), self.assertRaises(Crash): self.yes(code)
        self.assertEqual(self.journal.get(code)['state'], 'link-written')
        count = len(self.writes())
        self.restart()
        self.assertEqual(self.journal.get(code)['state'], 'split')
        self.assertEqual(set(self.journal.get(code)['notifications']), {'owner', 'operator'})
        self.assertFalse(self.site.calls)
        self.assertEqual(len(self.writes()), count)

    def test_crash_inside_till_never_resends(self):
        code, _ = self.propose()
        self.till.crash = True
        with self.assertRaises(KeyboardInterrupt): self.yes(code)
        count = len(self.writes())
        self.restart(); self.restart(); self.yes(code)
        self.assertEqual(self.journal.get(code)['state'], 'till-uncertain')
        self.assertEqual(len(self.writes()), count)

    def test_crash_stale_site_keeps_newer_word(self):
        code, _ = self.propose()
        self.site.version += 1
        with mock.patch.object(self.site, 'apply', side_effect=Crash), self.assertRaises(Crash): self.yes(code)
        count = len(self.writes())
        self.restart(); self.yes(code)
        self.assertEqual(self.journal.get(code)['state'], 'split')
        self.assertEqual(self.site.version, 1)
        self.assertFalse(self.site.live)
        self.assertEqual(len(self.writes()), count)

    def test_crash_after_site_push_is_done_only_on_reconcile(self):
        code, _ = self.propose()
        apply = self.site.apply
        def pushed(*args): apply(*args); raise Crash()
        with mock.patch.object(self.site, 'apply', side_effect=pushed), self.assertRaises(Crash): self.yes(code)
        self.assertEqual(self.journal.get(code)['state'], 'site-intent')
        self.assertFalse(self.journal.get(code)['notifications'])
        count = len(self.writes())
        self.restart(); self.restart(); self.yes(code)
        self.assertEqual(self.journal.get(code)['state'], 'done')
        self.assertEqual(len(self.site.calls), 1)
        self.assertEqual(len(self.writes()), count)


class RealReleaseTests(NoNetwork):
    def test_real_live_apply_and_undo_without_baseline_divergence(self):
        from hass.tests import test_live_add as add_fixture
        release = add_fixture.LiveAddEndToEnd('runTest')
        release.setUp()
        self.addCleanup(release.doCleanups)
        till = BothTests('runTest'); till.setUp(); self.addCleanup(till.doCleanups)
        till.site = release.live
        pid = 'photo-product-' + str(max(int(p['id'].rsplit('-', 1)[1]) for p in json.loads(
            (release.repo.wt / 'hass/content/products.json').read_text())['products']) + 1)
        till.ops = [add_fixture.maker_op(), add_fixture.product_op(release.sha)]
        draft = till.create()
        code, _ = till.propose(draft, link={'product_id': pid, 'sku': draft.after['sku']})
        self.assertEqual(till.yes(code)[0], 'done')
        self.assertEqual(release.push_calls, 1)
        self.assertTrue(release.live.went_live(till.journal.get(code)['change_id']))
        self.assertIn(b'Quince jam', release.site_file('catalog-products.js'))
        release.settle()
        undo, _ = b.undo(code, sender=OWNER, chat=CHAT, journal=till.journal, engine=till.engine, site=till.site)
        self.assertFalse(till.till.items['NEWITEM']['hidden'])
        self.assertEqual(till.yes(undo)[0], 'done')
        self.assertTrue(till.till.items['NEWITEM']['hidden'])
        self.assertEqual(till.till.items['NEWITEM']['itemStock']['quantity'], 12)  # Hide, never erase the count.
        self.assertEqual(till.journal.get(code)['state'], 'undone')
        products = json.loads((release.repo.wt / 'hass/content/products.json').read_text())['products']
        self.assertEqual(next(p for p in products if p['id'] == pid)['status'], 'hidden')
        makers = json.loads((release.repo.wt / 'hass/content/makers.json').read_text())['makers']
        self.assertTrue(makers[add_fixture.KEY]['hidden'])


if __name__ == '__main__': unittest.main()
