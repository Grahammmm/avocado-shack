"""S7 fixture checks use assembled draft records and independently supplied image/DOM evidence."""
from dataclasses import replace
import unittest

from hass import claims
from hass.npp import assets, validate
from hass.npp.copy import Context, Writer
from hass.npp.private_numbers import finance


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.writer = Writer(assets())
        self.finance = finance('cost $3; sell $3 each; qty 12')
        self.ctx = Context('food', 'pantry', 'raw', 'plum jam', size_text='12 oz', source_read='Plum Jam 12 oz', private=self.finance.private)
        choice = {'name': {'template_id': 'name-item-size'}, 'story': None}
        self.copy = self.writer.write(self.ctx, lambda *_: choice)
        self.asset = 'assets/products/photo-0123456789abcdef.jpg'
        self.sha = 'a' * 64
        self.product = dict(self.copy.text, brand=claims.PLACEHOLDER, displayBrand='From the market', category='pantry',
                            image=self.asset, sellingPrice='3.00 each')
        self.draft = {'ops': [{'op': 'product.add', 'args': {'sellingPrice': '3.00 each', 'brand': claims.PLACEHOLDER,
                                                         'name': self.copy.text['name']}}],
                      'records': [{'collection': 'products', 'before': None, 'after': self.product, 'key': 'test-jam'}],
                      'assets': {self.asset: 'sha256:' + self.sha}}
        self.nodes = [self.copy.text['name'], '$3.00 each', self.copy.text['description']]
        self.kw = dict(finance=self.finance, origin=validate.ORIGIN_UNKNOWN, makers={}, live_site=True,
                       photo_sha='b' * 64, frozen_sha=self.sha, rendered_sha=self.sha, picture_read='Plum Jam 12 oz',
                       card_nodes=self.nodes, price_index=1,
                       label_words=['12 oz'])

    def verdict(self, **changes):
        return validate.listing(self.writer, self.ctx, self.copy, self.draft, **(self.kw | changes))

    def test_independent_price_and_size_pass_but_alt_gets_no_size_permit(self):
        # Case 32: banning values globally blocks legal price/size; granting by value leaks into other text.
        self.assertEqual(self.copy.text['name'], 'Plum jam 12 oz')
        self.assertNotIn('12', self.copy.text['imageAlt'])
        self.assertEqual(self.verdict().problems, ())
        for leak in ('Take twelve home.', 'Take 12 oz home.'):
            self.assertIn('card-number', self.verdict(card_nodes=[*self.nodes, leak]).problems)

    def test_price_must_be_in_exact_dom_element_once_and_picture_bound(self):
        # A string search for the total could pass duplicate/off-element prices or a different preview asset.
        self.assertIn('card-price', self.verdict(price_index=0).problems)
        for text in ('$3.00 each', 'only three dollars', '3.50'):
            self.assertIn('card-number', self.verdict(card_nodes=[*self.nodes, text]).problems)
        self.assertIn('money', self.verdict(picture_read='Plum Jam $3.00').problems)
        self.assertIn('picture-binding', self.verdict(rendered_sha='c' * 64).problems)
        self.assertIn('price-provenance', self.verdict(finance=finance('cost $3')).problems)

    def test_assembled_record_cannot_override_checked_copy_or_legacy_gates(self):
        # Valid text alone is insufficient: S7 must check the exact records that apply uses.
        self.product['description'] = 'This cures colds. It is made the old way.'
        self.product['brand'] = 'Unknown Farms'
        self.product['displayBrand'] = 'Unknown Farms'
        verdict = self.verdict()
        self.assertTrue({'listing-fields', 'brand', 'existing-claims', 'existing-identity', 'existing-live-policy'} <= set(verdict.problems))
        self.assertNotIn('colds', repr(verdict))

    def test_planted_length_hype_chatter_and_contact_are_distinct_checks(self):
        # Non-template public fields and future template revisions still need independent lint.
        for text, code in [('x' * 201, 'length'), ('The best jam. Take it home.', 'hype'),
                           ('My next delivery arrives soon. Take it home.', 'owner-chatter'),
                           ('Ask me at help@example.test. Take it home.', 'contact')]:
            with self.subTest(code=code):
                ctx = replace(self.ctx, owner_words='My next delivery arrives soon')
                self.assertEqual(validate.field_problem(self.writer, 'description', text, (), ctx), code)
