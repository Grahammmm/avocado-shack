"""Synthetic till only: stateful fake HTTP transport, no sockets and no real credentials."""
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from hass.clover import drafts as d
from hass.clover.apply import ApplyEngine, REFUSED
from hass.clover.client import CloverWriteClient, CloverRefused, Response
from hass.clover.config import from_settings, ConfigProblem
from hass.clover.credential import CredentialError
from hass.clover.mapper import parse_item
from hass.tests.test_clover_client import NoNetwork, FAKE_TOKEN, fixture


class Till:
    def __init__(self):
        self.items = {i['id']: i for i in fixture('items.json')['elements']}
        self.items['FAKEITEM00001']['itemStock'] = {'quantity': 12, 'modifiedTime': 1}
        self.seen, self.lose, self.crash, self.mismatch = [], False, False, False

    def __call__(self, req):
        self.seen.append(req)
        path = urlsplit(req.url).path.split('/FAKEMERCH0001')[1]
        if req.method == 'GET':
            result = self.items.get(path.rsplit('/', 1)[-1]) if path.startswith('/items/') else {'elements': list(self.items.values())}
            if 'filter=sku%3D' in req.url or 'filter=sku=' in req.url:
                from urllib.parse import parse_qs
                sku = parse_qs(urlsplit(req.url).query)['filter'][0].split('=', 1)[1]
                result = {'elements': [i for i in self.items.values() if i.get('sku') == sku]}
        else:
            body = json.loads(req.body)
            if path == '/items':
                result = self.items['NEWITEM'] = {**body, 'id': 'NEWITEM', 'modifiedTime': 1}
            elif path == '/category_items':
                result = self.items[body['elements'][0]['item']['id']]
                result['categories'] = {'elements': [body['elements'][0]['category']]}
            else:
                result = self.items[path.rsplit('/', 1)[-1]]
                if not self.mismatch:
                    if path.startswith('/item_stocks/'):
                        result['itemStock'] = {**body, 'modifiedTime': result['itemStock']['modifiedTime'] + 1}
                    else:
                        result.update(body)
                    result['modifiedTime'] += 1
            if self.crash:
                raise KeyboardInterrupt('simulated process death after mutation')
            if self.lose:
                raise OSError('simulated lost reply')
        return Response(200, {}, json.dumps(result).encode())


class ApplyTests(NoNetwork):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        os.chmod(self.state, 0o700)
        self.token = self.state / 'fake-write'
        self.token.write_text(FAKE_TOKEN)
        self.token.chmod(0o600)
        self.cfg = from_settings({'environment': 'sandbox', 'merchantId': 'FAKEMERCH0001', 'tokenFile': str(self.state / 'fake-read'),
                                  'writeTokenFile': str(self.token), 'writes': True, 'liveApproved': True, 'categoryMap': {'pantry': 'Pantry'}})
        self.till = Till()
        self.engine = self.make()

    def make(self, **kw):
        return ApplyEngine(self.state, self.cfg, lambda token: CloverWriteClient('FAKEMERCH0001', token, self.till, min_interval=0),
                           mike=('mike', 'private'), g=('g', 'g-private'), **kw)

    def item(self):
        return parse_item(self.till.items['FAKEITEM00001'])

    def offer(self, draft):
        return self.engine.offer(draft, sender='mike', chat='private')[0]

    def yes(self, code, **kw):
        return self.engine.handle('yes ' + code, sender='mike', chat='private', **kw)

    def writes(self):
        return [r for r in self.till.seen if r.method != 'GET']

    def test_all_kinds_round_trip_one_yes_and_allowlist(self):
        builders = [lambda: d.build_set_stock(self.item(), 7, self.cfg), lambda: d.build_received(self.item(), 3, self.cfg),
                    lambda: d.build_set_stock(self.item(), 0, self.cfg), lambda: d.build_set_price(self.item(), 100, self.cfg),
                    lambda: d.build_set_hidden(self.item(), True, self.cfg), lambda: d.build_set_hidden(self.item(), False, self.cfg),
                    lambda: d.build_create_item('Synthetic new', 500, 'pantry', [], self.cfg, categories=[('CAT', 'Pantry')])]
        for build in builders:
            draft = build()
            self.assertFalse(draft.second_confirmation)
            self.assertEqual(self.yes(self.offer(draft)), 'applied')
            target = self.till.items[draft.item_id or 'NEWITEM']
            self.assertTrue(self.engine._matches(draft.to_dict(), target))
        self.assertEqual(len(self.writes()), 8)
        for req in self.writes():
            self.assertIn(req.method, ('POST', 'PUT'))
            self.assertRegex(urlsplit(req.url).path, r'/merchants/FAKEMERCH0001/(items(?:/[A-Za-z0-9]+)?|item_stocks/[A-Za-z0-9]+|category_items)$')
        client = self.engine._client()
        for method, path in [('DELETE', '/items/X'), ('POST', '/orders'), ('PUT', '/items'), ('POST', '/items/X/../orders')]:
            with self.assertRaises(CloverRefused):
                client.write(method, path, {})
        self.assertEqual((self.state / 'clover/journal.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_stale_cap_pause_and_restart_persistence(self):
        code = self.offer(d.build_received(self.item(), 2, self.cfg))
        self.till.items[self.item().id]['itemStock']['modifiedTime'] += 1
        with self.assertRaisesRegex(d.DraftRefused, 'fresh draft'):
            self.yes(code)
        self.assertFalse(self.writes())
        self.cfg = replace(self.cfg, daily_write_cap=1)
        self.engine = self.make()
        with self.assertRaisesRegex(d.DraftRefused, 'daily limit'):
            self.offer(d.build_set_price(self.item(), 100, self.cfg))
        self.engine.handle('stop changes', sender='mike', chat='private')
        self.engine = self.make()
        with self.assertRaisesRegex(d.DraftRefused, 'paused'):
            self.offer(d.build_set_stock(self.item(), 4, self.cfg))

    def test_approval_identity_expiry_and_immutable_snapshot(self):
        draft = d.build_set_price(self.item(), 100, self.cfg)
        code = self.offer(draft)
        draft.requests[0]['json']['price'] = 999
        for text, args in [('yes', {}), ('yes ' + code, {'sender': 'stranger'}), ('yes ' + code, {'chat': 'other'}),
                           ('yes ' + code, {'group': True}), ('yes ' + code, {'edited': True}), ('yes ' + code, {'reaction': True})]:
            with self.assertRaises(d.DraftRefused):
                self.engine.handle(text, **{'sender': 'mike', 'chat': 'private', **args})
        self.assertFalse(self.writes())
        self.assertEqual(self.yes(code), 'applied')
        self.assertEqual(self.item().price_cents, 100)
        with self.assertRaises(d.DraftRefused):
            self.yes(code)
        code = self.offer(d.build_set_price(self.item(), 200, self.cfg))
        self.engine.clock = lambda: float('inf')
        with self.assertRaises(d.DraftRefused):
            self.yes(code)
        for enabled in (False, True):
            engine = self.make(g_is_owner=enabled)
            if enabled:
                self.assertTrue(engine.offer(d.build_set_price(self.item(), 200, self.cfg), sender='g', chat='g-private')[0])
            else:
                with self.assertRaises(d.DraftRefused):
                    engine.offer(d.build_set_price(self.item(), 200, self.cfg), sender='g', chat='g-private')

    def test_recovery_never_replays_even_lost_create_response(self):
        for create in (False, True):
            draft = d.build_create_item('Crash item', 500, None, [], self.cfg) if create else d.build_set_stock(self.item(), 5, self.cfg)
            code = self.offer(draft)
            self.till.crash = True
            with self.assertRaises(KeyboardInterrupt):
                self.yes(code)
            self.till.crash = False
            before = len(self.writes())
            self.engine = self.make()
            self.engine.recover()
            self.engine.recover()
            self.assertEqual(len(self.writes()), before)
            with self.engine.journal.locked() as db:
                self.assertEqual(db.execute('SELECT status FROM changes WHERE code=?', (code,)).fetchone()[0], 'applied')
            with self.assertRaises(d.DraftRefused):
                self.yes(code)

    def test_undo_cap_exemption_and_refuse_newer(self):
        code = self.offer(d.build_set_price(self.item(), 100, self.cfg))
        self.assertEqual(self.yes(code), 'applied')
        self.cfg = replace(self.cfg, daily_write_cap=1)
        self.engine = self.make()
        undo, _ = self.engine.undo(code, sender='mike', chat='private')
        self.assertEqual(self.item().price_cents, 100)
        self.assertEqual(self.yes(undo), 'applied')
        self.assertEqual(self.item().price_cents, 1250)
        with self.assertRaisesRegex(d.DraftRefused, 'newer value'):
            self.engine.undo(code, sender='mike', chat='private')

    def test_missing_gate_or_unsafe_write_file_never_writes(self):
        original = self.cfg
        for changes in ({'writes': False}, {'live_approved': False}, {'write_token_file': ''}):
            self.cfg = replace(original, **changes)
            self.engine = self.make()
            with self.assertRaisesRegex(d.DraftRefused, REFUSED):
                self.offer(d.build_set_price(self.item(), 100, self.cfg))
        self.assertFalse(self.till.seen)
        for key, value in [('writes', 'yes'), ('writeTokenFile', 'relative')]:
            with self.assertRaises(ConfigProblem):
                from_settings({'environment': 'sandbox', 'merchantId': 'FAKEMERCH0001', 'tokenFile': '/fake', key: value})
        self.cfg = replace(self.cfg, writes=True, live_approved=True, write_token_file=str(self.token))
        self.engine = self.make()
        code = self.offer(d.build_set_price(self.item(), 100, self.cfg))
        for missing in (False, True):
            self.token.unlink() if missing else self.token.chmod(0o644)
            with self.assertRaises(CredentialError):
                self.yes(code)
        self.assertFalse(self.till.seen)

    def test_apply_rechecks_cap_day_rollover_and_create_collision(self):
        self.cfg = replace(self.cfg, daily_write_cap=1)
        self.engine = self.make(clock=lambda: 1800000000)
        first = self.offer(d.build_set_price(self.item(), 100, self.cfg))
        other = self.offer(d.build_set_stock(self.item(), 5, self.cfg))
        self.assertEqual(self.yes(first), 'applied')
        with self.assertRaisesRegex(d.DraftRefused, 'daily limit'):
            self.yes(other)
        self.engine.clock = lambda: 1800086400
        draft = d.build_create_item('Synthetic collision', 500, None, [], self.cfg)
        code = self.offer(draft)
        self.till.items['CLASH'] = {'id': 'CLASH', 'name': 'Another', 'code': draft.after['sku']}
        with self.assertRaisesRegex(d.DraftRefused, 'SKU is now taken'):
            self.yes(code)
        self.assertEqual(len(self.writes()), 1)

    def test_set_sku_rechecks_other_items_sku_and_barcode(self):
        self.till.items['FAKEITEM00001']['sku'] = ''
        for field in ('sku', 'code'):
            with self.subTest(field=field):
                items = [parse_item(i) for i in self.till.items.values()]
                draft = d.build_set_sku(self.item(), items, self.cfg)
                code = self.offer(draft)
                self.till.items['CLASH'] = {'id': 'CLASH', 'name': 'Another', field: draft.after['sku'].lower(), 'hidden': True}
                with self.assertRaisesRegex(d.DraftRefused, 'SKU is now taken'):
                    self.yes(code)
                self.assertEqual(self.item().sku, '')
                self.assertFalse(self.writes())
                with self.engine.journal.locked() as db:
                    self.assertEqual(db.execute('SELECT status FROM changes WHERE code=?', (code,)).fetchone()[0], 'failed')
                del self.till.items['CLASH']

        draft = d.build_set_sku(self.item(), [parse_item(i) for i in self.till.items.values()], self.cfg)
        self.till.items[self.item().id]['code'] = draft.after['sku']
        code = self.offer(draft)
        self.assertEqual(self.yes(code), 'applied')
        undo, _ = self.engine.undo(code, sender='mike', chat='private')
        self.assertEqual(self.yes(undo), 'applied')
        self.assertEqual(self.item().sku, '')

    def test_failed_readback_and_ambiguous_write_are_not_retried(self):
        code = self.offer(d.build_set_price(self.item(), 100, self.cfg))
        self.till.mismatch = True
        self.assertEqual(self.yes(code), 'failed')
        self.till.mismatch, self.till.lose = False, True
        code = self.offer(d.build_set_price(self.item(), 100, self.cfg))
        self.assertEqual(self.yes(code), 'uncertain')
        self.assertEqual(len(self.writes()), 2)
        self.till.lose = False
        self.engine.recover()
        self.assertEqual(len(self.writes()), 2)
