"""Synthetic chat intake preserves local price provenance without retaining finance clauses."""
import unittest
from unittest.mock import patch

from hass.npp.job import Plan
from hass.tests import test_npp_job


class PriceProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.chat = test_npp_job.JobTests()
        self.addCleanup(self.chat.doCleanups)
        self.chat.setUp()
        self.chat.stages.takes_turn = lambda text, state: True

    def request(self):
        chat = self.chat
        jobs = chat.conv.npp
        assert jobs is not None
        request = jobs.request(chat.job(), chat.now)
        assert request is not None
        return request

    def test_caption_keeps_only_checked_price_span_and_private_number_screen(self):
        # Losing the span when stripping clauses makes S7 refuse an otherwise complete listing.
        chat = self.chat
        caption = 'Plum jam; sell $7 each; cost $3; qty 12'
        with patch.object(chat.conv, 'log') as log:
            self.assertEqual(chat.say(caption, photos=1), 'npp-working')
            req = self.request()
            self.assertEqual(req['texts'], ['Plum jam'])
            self.assertEqual(req['slots']['intake'], {
                'price': '7.00', 'sold_by': 'item', 'price_span': [9, 22], 'private': ['12', '3', '300'],
                'has_cost': True, 'has_qty': True,
            })
            chat.work()
        # The fake stage only uses the public price; inspect the actual downstream draft and logs.
        drafts = list((chat.repo.state / 'drafts').glob('*.json'))
        self.assertEqual(len(drafts), 1)
        for leak in ('$3', 'cost', 'qty 12'):
            self.assertNotIn(leak, drafts[0].read_text())
            self.assertNotIn(leak, str(log.mock_calls))

    def test_conflicting_caption_cannot_seed_price_and_answer_then_edit_rebind_span(self):
        # A deterministic ambiguity must not be promoted by a plausible local-reader price.
        chat = self.chat
        ambiguous = 'Plum jam; sell $7 or $8 each'
        with patch.object(chat.conv, '_read_intake', return_value={'photo_fields': {'price': '7.00'}}):
            chat.say(ambiguous, photos=1)
        self.assertIsNone(self.request()['slots']['intake']['price'])
        self.assertIsNone(self.request()['slots']['intake']['price_span'])
        self.assertEqual(self.request()['texts'], ['Plum jam'])
        with patch.object(chat.stages, 'plan', return_value=Plan(questions=(('selling_price', "What's the selling price?"),))):
            chat.work()
        self.assertEqual(chat.transport.texts, ["What's the selling price?"])

        chat.say('$7 per lb')
        first = self.request()['slots']['intake']
        self.assertEqual((first['price'], first['sold_by'], first['price_span']), ('7.00', 'pound', [0, 2]))
        chat.work()
        chat.say('actually make it $9')
        second = self.request()['slots']['intake']
        self.assertEqual((second['price'], second['sold_by'], second['price_span']), ('9.00', 'pound', [17, 19]))
        self.assertNotIn('actually make it', str(self.request()['texts']))
