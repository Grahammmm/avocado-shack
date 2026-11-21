"""S8 DOM evidence is tied to the exact card image; S7 only exempts renderer chrome."""
import unittest
from pathlib import Path

from hass import preview, sitegen
from hass.content_model import load_and_validate, shop_today
from hass.npp.validate import captured_dom, dom_problem
from hass.tests import test_preview


def _assert_fixed_label(label, role):
    # A matching string is not enough: it must be in the exact renderer element.
    nodes = ['Jam', '$7.00 each', 'Plum jam.']
    def check(fragment, price_index=1):
        return dom_problem([*nodes, fragment], price_index, '7.00 each', 'Jam',
                           allowed={'Jam', 'Plum jam.'}, required=['Jam', 'Plum jam.'])
    assert check({'text': label, 'role': role}) is None
    assert check({'text': label, 'role': None}) == 'card-copy'
    assert check({'text': label, 'role': '.food-description'}) == 'card-copy'
    assert check({'text': label, 'role': role}, price_index=2) == 'card-price'


def _assert_source_bound_maker_count_and_claim():
    # The count may equal a private quantity here, but not in any listing text.
    args = dict(price_index=1, price='7.00 each', name='Jam', allowed={'Jam'},
                maker='Oak Farm', maker_count=12, private={12})
    nodes = ['Jam', '$7.00 each', {'text': 'Visit Oak Farm ↗', 'role': '.maker-story-content > a'},
             {'text': 'See all 12 from Oak Farm', 'role': '.maker-story-content > button.text-link[data-from]'}]
    assert dom_problem(nodes, **args) is None
    assert dom_problem(nodes, **(args | {'maker_count': 13})) == 'card-copy'
    assert dom_problem(nodes, **(args | {'maker': 'Elm Farm'})) == 'card-copy'
    assert dom_problem([*nodes, 'See all 12 from Oak Farm'], **args) == 'card-number'
    badge = {'text': 'Organic', 'role': '.food-badges > span'}
    assert dom_problem([*nodes, badge], **args) == 'card-copy'
    assert dom_problem([*nodes, badge], **args, organic=True) is None
    assert dom_problem([*nodes, {'text': 'Sold out', 'role': '.availability'}], **args) == 'card-copy'


class TestFixedUI(unittest.TestCase):
    def test_fixed_label_is_not_a_listing_copy_allowlist(self):
        for label, role in [('Link to this', ':scope > .card-link'), ('New', '.food-badges > span')]:
            with self.subTest(label=label):
                _assert_fixed_label(label, role)

    def test_maker_count_exemption_and_organic_claim_are_source_bound(self):
        _assert_source_bound_maker_count_and_claim()


@unittest.skipUnless(preview.Previewer('.').env.get('PLAYWRIGHT_MODULE'), 'Playwright not installed')
class TestBrowserEvidence(test_preview.BrowserCase):
    def test_real_card_fragments_and_price_belong_to_this_png(self):
        # An older capture of the very same product must not validate a different image.
        wt = self.repo.wt
        content = load_and_validate(wt / 'hass' / 'content', wt / 'storefront-mockup')
        item = next(p for p in content.products if p['id'] == 'photo-product-001')
        today = shop_today()
        browser = preview.Previewer(wt, dict(preview.Previewer(wt).env), viewports=('phone',))

        def capture(amount):
            item.update(sellingPrice=amount, addedOn=today.isoformat())
            files = sitegen.render(content, wt / 'hass' / 'templates', today=today)
            target = preview.target_for({'collection': 'products', 'key': item['id'], 'after': item})
            result = browser.capture(files, target | {'cardOnly': True}, self.repo.state / 'screenshots' / 'evidence.png')
            assert result['ok'], result
            return result['cardEvidence'], Path(result['png']).read_bytes()

        first, first_png = capture('7.00 each')
        _, later_png = capture('8.00 each')
        nodes, index, _ = captured_dom(first, first_png, item['id'])
        assert nodes is not None and index is not None
        assert nodes[index] == {'text': '$7.00 each', 'role': None}
        assert {'text': 'Link to this', 'role': ':scope > .card-link'} in nodes
        assert {'text': 'New', 'role': '.food-badges > span'} in nodes
        assert captured_dom(first, later_png, item['id']) == (None, None, None)
