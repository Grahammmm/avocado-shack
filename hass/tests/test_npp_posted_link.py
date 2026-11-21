"""Offline S13 link coverage at the writer → generated shelf → shop.js boundary."""

import json
import re
import shutil
import subprocess
import unittest

from hass import editor, npp
from hass.content_model import SITE_DIR
from hass.npp.reply import posted
from hass.tests.test_set_photo import FIXTURES, PhotoRepo

SITE = 'storefront-mockup/'
NAME = 'Fixture Moon Quince'
GONE = 'That item is not in our catalog right now. Here is everything else.'

# Execute the scripts, not a copy of their item logic. The DOM stand-in just
# reflects inserted markup and records which article receives scroll/focus.
SHOP_RUNNER = r"""
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const [built, sources, href] = process.argv.slice(2);
const location = new URL(href);
const elements = new Map();
const element = () => ({value: '', textContent: '', options: [], hidden: false,
  append(option) { this.options.push(option); }, addEventListener() {}});
for (const selector of ['#catalog-grid', '#brand-filter', '#product-search', '#market',
                        '#catalog-count', '#catalog-sentinel', '#more-products',
                        '#clear-filters', '#dialog', '.close', '[data-policy]']) {
  elements.set(selector, element());
}
const all = {...element(), dataset: {filter: 'all'}, classList: {toggle() {}},
  setAttribute() {}};
elements.set('[data-filter="all"]', all);
elements.set('[data-filter].selected', all);
const grid = elements.get('#catalog-grid');
let focused = null, scrolled = null;
const articles = [];
Object.defineProperty(grid, 'innerHTML', {set() { articles.length = 0; }});
grid.insertAdjacentHTML = (position, html) => {
  if (position === 'beforebegin') {
    const id = html.match(/\bid="([^"]+)"/)?.[1];
    const cls = html.match(/\bclass="([^"]+)"/)?.[1];
    elements.set(id ? '#' + id : '.' + cls, {...element(), hidden: /\bhidden\b/.test(html)});
  } else if (position === 'beforeend') {
    for (const [, id] of html.matchAll(/<article\s[^>]*\bdata-product-id="([^"]+)"/g)) {
      articles.push({dataset: {productId: id}, setAttribute() {},
        scrollIntoView() { scrolled = id; }, focus() { focused = id; }});
    }
  }
};
const document = {
  readyState: 'complete', createElement: element, addEventListener() {},
  getElementById(id) { return elements.get('#' + id) ?? null; },
  querySelector(selector) { return elements.get(selector) ?? null; },
  querySelectorAll(selector) {
    if (selector === '[data-filter]') return [all];
    if (selector === '#catalog-grid article') return articles;
    return [];
  },
};
const context = vm.createContext({document, location, URLSearchParams,
  history: {replaceState(_state, _unused, url) { location.href = new URL(url, location).href; }},
  window: {addEventListener() {}}});
for (const [dir, file] of [[built, 'catalog-products.js'], [built, 'producers.js'],
                           [sources, 'script.js'], [sources, 'shop.js']]) {
  vm.runInContext(fs.readFileSync(path.join(dir, file), 'utf8'), context, {filename: file});
}
const status = document.getElementById('catalog-item-status');
console.log(JSON.stringify({cards: articles.map(a => a.dataset.productId), focused, scrolled,
  status: status && !status.hidden ? status.textContent : null}));
"""


class PostedLinkTests(unittest.TestCase):
    def _add_listing(self):
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        # Same fields as stages._candidate for a photo and price with no maker.
        draft = repo.run(('product.add', {
            'name': NAME, 'description': 'A quince with yellow skin.',
            'brand': 'Producer not identified', 'category': 'fruit',
            'photo': repo.store((FIXTURES / 'pixel.jpg').read_bytes()),
            'imageAlt': 'A quince on a plain surface', 'sellingPrice': '7.13',
        }))
        change_id = draft['change_id']
        # Use the applied change record, as Conversation.npp_posted does, not
        # a hard-coded id or an id taken from the catalog being checked.
        change = editor.show(change_id, state=str(repo.state))['change']
        [key] = [r['key'] for r in change['records'] if r['collection'] == 'products']
        _, _, replies = npp.assets()
        line = posted(replies, key)
        self.assertTrue(line.startswith('Posted: '))
        url = line.split()[1]
        self.assertEqual(url, f'https://theavocadoman.com/?item={key}#market')
        return repo, change_id, key, url

    def _node22(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('NOT-RUN: Node 22 is not installed')
        result = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.startswith('v22.'):
            self.skipTest('NOT-RUN: Node 22 is required')
        return node

    def _open(self, node, repo, url):
        script = repo.state / 'posted-link.cjs'
        script.write_text(SHOP_RUNNER, encoding='utf-8')
        result = subprocess.run([node, str(script), str(repo.wt / SITE), str(SITE_DIR), url],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_c1_id_in_site(self):
        # An add could succeed while the generated market data omits its id.
        repo, _, key, _ = self._add_listing()
        self.assertEqual([(p['name'], p['category']) for p in repo.catalog() if p['id'] == key],
                         [(NAME, 'fruit')])
        page = repo.read(SITE + 'index.html').decode()
        market = re.search(r'<section\b[^>]*\bid="market"[^>]*>(.*?)</section>', page, re.S)
        if market is None:
            self.fail('generated homepage has no market section')
        self.assertIn('id="catalog-grid"', market[1])
        scripts = re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', page)
        self.assertIn('catalog-products.js', scripts)
        self.assertIn('shop.js', scripts)
        self.assertLess(scripts.index('catalog-products.js'), scripts.index('shop.js'))

    def test_c2_item_param(self):
        # A fruit is off the default packaged shelf. The linked load must
        # render and focus the exact card, not merely show a catalog grid.
        node = self._node22()
        repo, _, key, url = self._add_listing()
        self.assertNotIn(key, self._open(node, repo, url.split('?')[0] + '#market')['cards'])
        page = self._open(node, repo, url)
        self.assertIn(key, page['cards'])
        self.assertEqual((page['focused'], page['scrolled'], page['status']), (key, key, None))

    def test_c3_hidden_not_shown(self):
        # A reverted row still exists privately; leaking it to the shelf or
        # silently ignoring the old link would both break the visitor flow.
        repo, change_id, key, url = self._add_listing()
        self.assertIn(key, [p['id'] for p in repo.catalog()])
        repo.run(('history.revert', {'changeId': change_id}))
        self.assertEqual(repo.product(key)['status'], 'hidden')
        self.assertNotIn(key, [p['id'] for p in repo.catalog()])
        page = self._open(self._node22(), repo, url)
        self.assertNotIn(key, page['cards'])
        self.assertTrue(page['cards'], 'other listings should remain visible')
        self.assertEqual((page['focused'], page['scrolled'], page['status']), (None, None, GONE))
