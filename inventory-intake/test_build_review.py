"""Regression tests for the private photo review renderer.

Each test copies the production script into a temporary directory next to a
synthetic manifest and runs that copy, so the checkout is never written.
Set BUILD_REVIEW_SCRIPT to point at another copy (e.g. the pre-change file).
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote

SCRIPT = Path(os.environ.get('BUILD_REVIEW_SCRIPT') or Path(__file__).resolve().parent / 'build_review.py')


class CardParser(HTMLParser):
    """Collects every tag/attributes inside <article> plus the <small> text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.articles = 0
        self.tags = []
        self.attrs = []
        self.small = []
        self._in_small = False

    def handle_starttag(self, tag, attrs):
        if tag == 'article':
            self.articles += 1
        if self.articles:
            self.tags.append(tag)
            self.attrs.append((tag, dict(attrs), [k for k, _ in attrs]))
        if tag == 'small':
            self._in_small = True
            self.small.append('')

    def handle_endtag(self, tag):
        if tag == 'small':
            self._in_small = False

    def handle_data(self, data):
        if self._in_small:
            self.small[-1] += data


def photo_row(name, **extra):
    row = {
        'source_file': '/synthetic/source/' + name + '.heic',
        'sha256': 'ab' * 32,
        'photo': '/synthetic/inventory-intake/photos/' + name,
        'status': 'needs_review',
        'product_name': None,
    }
    row.update(extra)
    return row


def render(rows):
    """Run a copy of the script on a synthetic manifest; return (parser, manifest_before, manifest_after, proc)."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        script = work / 'build_review.py'
        shutil.copyfile(SCRIPT, script)
        (work / 'manifest.json').write_text(json.dumps(rows))
        proc = subprocess.run([sys.executable, '-B', str(script)], cwd=tmp, timeout=60,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssertionError('script failed: ' + proc.stderr)
        parser = CardParser()
        parser.feed((work / 'review.html').read_text(encoding='utf-8'))
        after = json.loads((work / 'manifest.json').read_text())
    return parser, after, proc


class BuildReviewTests(unittest.TestCase):
    def test_quote_filename_cannot_inject_attributes(self):
        name = 'fixture" onload="synthetic-marker.jpg'
        parser, _, _ = render([photo_row(name)])
        self.assertEqual(parser.articles, 1)
        self.assertEqual(parser.tags.count('a'), 1)
        self.assertEqual(parser.tags.count('img'), 1)
        enc = quote(name, safe='')
        for tag, attrs, keys in parser.attrs:
            self.assertNotIn('onload', keys)
            if tag == 'a':
                self.assertEqual(keys, ['href'])
                self.assertEqual(attrs['href'], 'photos/' + enc)
            if tag == 'img':
                self.assertEqual(keys, ['loading', 'src', 'alt'])
                self.assertEqual(attrs['src'], 'previews/' + enc)
        self.assertNotIn('"', enc)

    def test_filename_markup_is_literal_text(self):
        name = "<b>x<script>&amp;\"q'z.jpg"
        parser, _, _ = render([photo_row(name)])
        self.assertEqual(parser.small, [name])
        self.assertNotIn('b', parser.tags)
        self.assertNotIn('script', parser.tags)
        self.assertEqual(parser.tags.count('small'), 1)
        alt = [a for t, a, _ in parser.attrs if t == 'img'][0]['alt']
        self.assertEqual(alt, 'Preserves shelf')

    def test_reserved_url_characters_round_trip(self):
        name = 'a b#c?d%e+f&g.jpg'
        parser, _, _ = render([photo_row(name)])
        enc = quote(name, safe='')
        self.assertEqual(enc, 'a%20b%23c%3Fd%25e%2Bf%26g.jpg')
        href = [a for t, a, _ in parser.attrs if t == 'a'][0]['href']
        src = [a for t, a, _ in parser.attrs if t == 'img'][0]['src']
        self.assertEqual(href, 'photos/' + enc)
        self.assertEqual(src, 'previews/' + enc)
        for url in (href, src):
            self.assertNotIn('#', url)
            self.assertNotIn('?', url)
        self.assertEqual(unquote(href.split('/', 1)[1]), name)
        self.assertEqual(unquote(src.split('/', 1)[1]), name)
        self.assertEqual(parser.small, [name])

    def test_unicode_filename_and_plain_filename(self):
        uni = 'café_写真.jpg'
        plain = 'IMG_fixture.jpg'
        parser, _, proc = render([photo_row(uni), photo_row(plain)])
        hrefs = [a['href'] for t, a, _ in parser.attrs if t == 'a']
        srcs = [a['src'] for t, a, _ in parser.attrs if t == 'img']
        self.assertEqual(hrefs, ['photos/caf%C3%A9_%E5%86%99%E7%9C%9F.jpg', 'photos/IMG_fixture.jpg'])
        self.assertEqual(srcs, ['previews/caf%C3%A9_%E5%86%99%E7%9C%9F.jpg', 'previews/IMG_fixture.jpg'])
        self.assertEqual(parser.small, [uni, plain])
        self.assertNotIn('/synthetic', proc.stderr)
        self.assertEqual(proc.stderr, '')

    def test_duplicate_rows_and_metadata_are_preserved(self):
        unique = photo_row('IMG_unique.jpg', claims=[], price_minor_units=None, currency='USD')
        dup = {'source_file': '/synthetic/source/dup.heic', 'sha256': 'cd' * 32,
               'duplicate_of': '/synthetic/source/IMG_unique.heic'}
        rows = [unique, dup]
        before = copy.deepcopy(rows)
        parser, after, _ = render(rows)
        self.assertEqual(parser.articles, 1)
        self.assertEqual(len(after), 2)
        self.assertEqual(after[1], before[1])
        for key in ('source_file', 'sha256', 'photo', 'status', 'product_name', 'claims',
                    'price_minor_units', 'currency'):
            self.assertEqual(after[0][key], before[0][key])
        self.assertEqual(after[0]['publication_status'], 'private_draft')
        self.assertEqual(after[0]['shipping_eligibility'], 'unverified')
        self.assertIs(after[0]['stock_count_inferred'], False)
        self.assertEqual(parser.tags.count('img'), 1)


if __name__ == '__main__':
    unittest.main()
