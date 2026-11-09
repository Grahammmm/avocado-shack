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
        self.titles = []  # <h2> text per card
        self.notes = []  # first plain <p> text per card (the recorded observation)
        self._in = None
        self._ps = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'article':
            self.articles += 1
            self._ps = 0
        if self.articles:
            self.tags.append(tag)
            self.attrs.append((tag, dict(attrs), [k for k, _ in attrs]))
        if tag == 'small':
            self._in = 'small'
            self.small.append('')
        elif tag == 'h2':
            self._in = 'h2'
            self.titles.append('')
        elif tag == 'p' and self.articles:
            self._ps += 1
            if self._ps == 1:
                self._in = 'p'
                self.notes.append('')

    def handle_endtag(self, tag):
        if tag in ('small', 'h2', 'p'):
            self._in = None

    def handle_data(self, data):
        if self._in == 'small':
            self.small[-1] += data
        elif self._in == 'h2':
            self.titles[-1] += data
        elif self._in == 'p':
            self.notes[-1] += data


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


def run_copy(rows, preexisting_review=None):
    """Run a copy of the script on a synthetic manifest (list or raw text).

    Returns (proc, manifest_bytes_before, manifest_bytes_after, review_text_or_None).
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        script = work / 'build_review.py'
        shutil.copyfile(SCRIPT, script)
        before = (rows if isinstance(rows, str) else json.dumps(rows)).encode()
        (work / 'manifest.json').write_bytes(before)
        if preexisting_review is not None:
            (work / 'review.html').write_text(preexisting_review)
        proc = subprocess.run([sys.executable, '-B', str(script)], cwd=tmp, timeout=60,
                              capture_output=True, text=True)
        review = work / 'review.html'
        return (proc, before, (work / 'manifest.json').read_bytes(),
                review.read_text(encoding='utf-8') if review.exists() else None)


def render(rows):
    """Run a copy of the script on a synthetic manifest; return (parser, manifest_after, proc)."""
    parser, after, proc, _ = render_full(rows)
    return parser, after, proc


def render_full(rows):
    proc, _, after, review = run_copy(rows)
    if proc.returncode != 0:
        raise AssertionError('script failed: ' + proc.stderr)
    parser = CardParser()
    parser.feed(review)
    return parser, json.loads(after), proc, review


UNKNOWN_CATEGORY = 'Photo awaiting review'
UNKNOWN_NOTE = 'Product identity and details need owner review.'


def reviewed(name, **extra):
    return photo_row(name, observed_category='Category of ' + name,
                     visual_observation='Note about ' + name, **extra)


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
        self.assertEqual(alt, UNKNOWN_CATEGORY)

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

    def test_reordering_preserves_observations_on_each_photo(self):
        a = reviewed('A.jpg')
        b = reviewed('B.jpg')
        for rows in ([a, b], [b, a], [b], [a]):
            parser, after, _ = render(copy.deepcopy(rows))
            self.assertEqual(parser.small, [r['photo'].rsplit('/', 1)[1] for r in rows])
            self.assertEqual(parser.titles, [r['observed_category'] for r in rows])
            self.assertEqual(parser.notes, [r['visual_observation'] for r in rows])
            for got, want in zip(after, rows):
                self.assertEqual(got['observed_category'], want['observed_category'])
                self.assertEqual(got['visual_observation'], want['visual_observation'])

    def test_every_photo_is_rendered_beyond_old_table_length(self):
        for count in (0, 1, 33, 34):
            rows, dups = [], 0
            for i in range(count):
                rows.append(reviewed('item-%02d.jpg' % i))
                if i % 17 == 5:  # duplicate-only rows interleaved
                    dups += 1
                    rows.append({'source_file': '/synthetic/d%d.heic' % i, 'sha256': 'cd' * 32,
                                 'duplicate_of': '/synthetic/source/item-%02d.heic' % i})
            parser, after, proc, review = render_full(copy.deepcopy(rows))
            names = ['item-%02d.jpg' % i for i in range(count)]
            self.assertEqual(parser.articles, count)
            self.assertEqual(parser.small, names)
            self.assertEqual(parser.titles, ['Category of ' + n for n in names])
            self.assertEqual(len(after), len(rows))
            self.assertIn('%d unique photos \u00b7 %d exact duplicates linked.' % (count, dups), review)
            self.assertEqual(proc.stdout.split(' ', 1)[0], str(count))
            self.assertIn('%d photo observations saved;' % count, proc.stdout)

    def test_unknown_photo_never_borrows_known_observation(self):
        rows = [reviewed('known.jpg'),
                photo_row('missing.jpg'),
                photo_row('empty.jpg', observed_category='', visual_observation=''),
                photo_row('half.jpg', observed_category='Only category'),
                reviewed('last.jpg')]
        parser, after, _ = render(copy.deepcopy(rows))
        self.assertEqual(parser.titles, ['Category of known.jpg', UNKNOWN_CATEGORY, UNKNOWN_CATEGORY,
                                         'Only category', 'Category of last.jpg'])
        self.assertEqual(parser.notes, ['Note about known.jpg', UNKNOWN_NOTE, UNKNOWN_NOTE,
                                        UNKNOWN_NOTE, 'Note about last.jpg'])
        self.assertEqual([r['observed_category'] for r in after], parser.titles)
        self.assertEqual([r['visual_observation'] for r in after], parser.notes)

    def test_recorded_observation_markup_is_escaped(self):
        cat = '<img src=x onerror=alert(1)>&amp;"q\''
        note = '</p><script>alert(2)</script><a href="javascript:x">y</a>'
        parser, after, _ = render([photo_row('esc.jpg', observed_category=cat, visual_observation=note)])
        self.assertEqual(parser.titles, [cat])
        self.assertEqual(parser.notes, [note])
        self.assertEqual(sorted(parser.tags), sorted(['article', 'a', 'img', 'div', 'small', 'h2', 'p', 'p']))
        img = [a for t, a, _ in parser.attrs if t == 'img'][0]
        self.assertEqual(img['alt'], cat)
        self.assertEqual([k for t, _, k in parser.attrs if t == 'img'][0], ['loading', 'src', 'alt'])
        self.assertEqual(after[0]['observed_category'], cat)
        self.assertEqual(after[0]['visual_observation'], note)

    def test_nonstring_observation_refused_before_output_writes(self):
        sentinel = 'PREEXISTING REVIEW SENTINEL'
        for field in ('observed_category', 'visual_observation'):
            for bad in (None, ['x'], 7, True):
                for bad_first in (True, False):
                    good = reviewed('good.jpg')
                    broken = reviewed('bad.jpg')
                    broken[field] = bad
                    rows = [broken, good] if bad_first else [good, broken]
                    proc, before, after, review = run_copy(rows, preexisting_review=sentinel)
                    label = '%s=%r first=%s' % (field, bad, bad_first)
                    self.assertNotEqual(proc.returncode, 0, label)
                    self.assertIn(field, proc.stderr, label)
                    self.assertEqual(proc.stdout, '', label)
                    self.assertEqual(after, before, label)
                    self.assertEqual(review, sentinel, label)

    def test_checked_in_manifest_observations_and_counts_are_preserved(self):
        recorded = json.loads((SCRIPT.parent / 'manifest.json').read_text())
        parser, after, proc, review = render_full(recorded)
        photos = [r for r in recorded if 'photo' in r]
        self.assertEqual(parser.articles, len(photos))
        self.assertEqual(len(photos), 33)
        self.assertEqual(parser.titles, [r['observed_category'] for r in photos])
        self.assertEqual(parser.notes, [r['visual_observation'] for r in photos])
        self.assertEqual([r.get('observed_category') for r in after if 'photo' in r], parser.titles)
        self.assertEqual(len([r for r in after if 'duplicate_of' in r and 'photo' not in r]), 3)
        self.assertIn('33 unique photos \u00b7 3 exact duplicates linked.', review)
        self.assertEqual(proc.stdout, '33 photo observations saved; review page created; no price or stock invented.\n')


if __name__ == '__main__':
    unittest.main()
