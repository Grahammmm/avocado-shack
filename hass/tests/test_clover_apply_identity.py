"""Synthetic till only: an existing-item change is bound to the approved item id."""
import json

from hass.clover import drafts as d
from hass.clover.apply import ApplyEngine
from hass.clover.client import Response
from hass.tests import test_clover_apply as base  # module import: the base class is not collected here

ITEM = 'FAKEITEM00001'


class WrongIdTill(base.Till):
    """Answers GET /items/<ITEM> with another item's id once `wrong_after_gets` GETs of it were served."""

    def __init__(self):
        super().__init__()
        self.wrong_after_gets, self.item_gets = None, 0

    def __call__(self, req):
        response = super().__call__(req)
        if req.method == 'GET' and req.url.split('?')[0].endswith('/items/' + ITEM):
            self.item_gets += 1
            if self.wrong_after_gets is not None and self.item_gets > self.wrong_after_gets:
                body = json.loads(response.body)
                body['id'] = 'ITEMB'
                return Response(200, {}, json.dumps(body).encode())
        return response


class IdentityTests(base.ApplyTests):

    def setUp(self):
        super().setUp()
        self.till = WrongIdTill()
        self.engine = self.make()

    def status(self, code):
        with self.engine.journal.locked() as db:
            return tuple(db.execute('SELECT status,result FROM changes WHERE code=?', (code,)).fetchone())

    def test_wrong_preflight_item_id_refuses_before_write(self):
        code = self.offer(d.build_set_price(self.item(), 100, self.cfg))
        self.till.wrong_after_gets = 0
        with self.assertRaises(d.DraftRefused):
            self.yes(code)
        self.assertFalse(self.writes())
        self.assertEqual(self.status(code), ('failed', 'null'))

    def test_wrong_readback_id_is_not_applied(self):
        code = self.offer(d.build_set_price(self.item(), 100, self.cfg))
        self.till.wrong_after_gets = 1  # preflight correct, readback returns ITEMB with the desired values
        self.assertEqual(self.yes(code), 'failed')
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.status(code), ('failed', 'null'))
        self.assertNotIn('ITEMB', self.status(code)[1])

    def test_recovery_wrong_id_stays_uncertain_without_replay(self):
        code = self.offer(d.build_set_price(self.item(), 100, self.cfg))
        self.till.crash = True
        with self.assertRaises(KeyboardInterrupt):
            self.yes(code)
        self.till.crash = False
        self.till.wrong_after_gets = self.till.item_gets
        before = len(self.writes())
        self.engine = self.make()
        self.engine.recover()
        self.engine.recover()
        self.assertEqual(len(self.writes()), before)
        self.assertEqual(self.status(code), ('uncertain', 'null'))

    def test_matches_checks_existing_identity_and_healthy_control(self):
        draft = d.build_set_price(self.item(), 100, self.cfg)
        entry = draft.to_dict()
        raw = {**self.till.items[ITEM], 'price': 100}
        self.assertTrue(ApplyEngine._matches(entry, raw))
        self.assertFalse(ApplyEngine._matches(entry, {**raw, 'id': 'ITEMB'}))
        code = self.offer(draft)
        self.assertEqual(self.yes(code), 'applied')
        self.assertEqual(json.loads(self.status(code)[1])['result_item_id'], ITEM)


for _name in [n for n in dir(base.ApplyTests) if n.startswith('test_') and n not in IdentityTests.__dict__]:
    setattr(IdentityTests, _name, None)  # inherited base tests run in their own module only
