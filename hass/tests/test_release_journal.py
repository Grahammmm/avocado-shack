"""Release durability, corrupt books and pure restart table; no network."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from hass import release_journal as r

AT = '2026-11-06T17:00:00+00:00'
A, B, C = 'a' * 40, 'b' * 40, 'c' * 40


def anchor(): return dict(anchor_site_commit=A, anchor_build_today='2026-11-06', anchor_seq=0, anchor_at=AT)


def entry(seq=1, state='intent', before=A, after=B):
    j = dict(change_id=f'chg-{seq:012x}', code='abcd', kind='change', orig=None, draft_hash='sha256:fixture',
             writer_before=A, writer_after=B, site_before=before, today='2026-11-06', seq=seq, push_attempts=[],
             state=state, notified=[], at=AT)
    if state in {'built', 'committed', 'pushing', 'pushed', 'unknown', 'live', 'unconfirmed'}:
        j.update(writer_after=B, manifest={'index.html': 'a' * 64}, site_commit=after)
    if state in {'pushing', 'pushed', 'unknown', 'live', 'unconfirmed'}: j['push_attempts'] = [AT]
    return j


def big_entry(seq, n, *args, **kw):
    """entry() with a change_id decoupled from seq, so huge seq values still pass the change_id format check."""
    return {**entry(seq, *args, **kw), 'change_id': f'chg-{n:012x}'}


class JournalTests(unittest.TestCase):
    def test_restart_table(self):
        rows = [
            ('intent', {}, ('not-applied', None)), ('intent', {'applied': True}, ('not-published', 'interrupted')),
            *[(s, {}, ('not-published', 'reset')) for s in ('applied', 'built', 'committed')],
            *[(s, {'landed': True}, ('pushed', None)) for s in ('pushing', 'unknown')],
            ('unknown', {'before_twice': True}, ('not-published', 'reset')),
            ('pushing', {}, ('unknown', None)), ('unknown', {'before_once': True}, ('unknown', None)),
            ('pushed', {'matches': True}, ('live', None)), ('pushed', {'expired': True}, ('unconfirmed', None)),
            ('unconfirmed', {'matches': True}, ('live', None)), ('unconfirmed', {}, ('unconfirmed', None)),
            ('not-published', {'matches': True}, ('not-published', None)), ('live', {}, ('live', None))]
        for state, facts, expected in rows:
            with self.subTest(state=state, facts=facts): self.assertEqual(r.decide(state, facts), expected)

    def test_derive_survives_post_push_gap_idempotently_and_counts_id_once(self):
        first, second = entry(state='pushed'), entry(2, 'live', B, C)
        first['push_attempts'] *= 3
        for _ in range(3):
            result = r.derive(anchor(), [second, first])
            self.assertEqual(result['last_site_commit'], C)
            self.assertEqual(result['last_build_today'], '2026-11-06')
            self.assertEqual([p['change_id'] for p in result['pushes']], [second['change_id'], first['change_id']])
        for state in ('pushing', 'unknown', 'not-published'):
            first['state'] = state
            result = r.derive(anchor(), [first])
            self.assertEqual(result['last_site_commit'], A)
            self.assertEqual(len(result['pushes']), 1)

    def test_fail_closed_schema_gap_and_fork(self):
        invalid = [({}, []), (anchor(), [entry(2)]), (anchor(), [entry(), entry()]),
                   (anchor(), [entry(state='pushed'), entry(2, 'pushed', A, C)]),
                   (anchor(), [entry(1, 'live', C, B)])]
        for key, value in [('seq', True), ('state', 'made-up'), ('manifest', {'../x': 'a'*64}),
                           ('push_attempts', ['yesterday']), ('notified', ['owner text']), ('writer_before', 'bad')]:
            j = entry(); j[key] = value; invalid.append((anchor(), [j]))
        for a, js in invalid:
            with self.subTest(a=a, js=js), self.assertRaises(r.BooksError): r.derive(a, js)

    def test_sparse_huge_sequence_is_books_error_without_span_allocation(self):
        for seq in (2, 10**30):
            with self.subTest(seq=seq), self.assertRaises(r.BooksError) as ctx: r.derive(anchor(), [big_entry(seq, 1)])
            self.assertEqual(str(ctx.exception), 'release-books')

    def test_books_load_rejects_sparse_sequence_from_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = r.Books(tmp)
            r.atomic(Path(tmp) / 'publish.json', anchor())
            books.write(big_entry(10**30, 1))
            files = [Path(tmp) / 'publish.json', *sorted(books.directory.iterdir())]
            before = [(p.read_bytes(), p.stat().st_mode) for p in files]
            with self.assertRaises(r.BooksError) as ctx: books.load()
            self.assertEqual(str(ctx.exception), 'release-books')
            self.assertEqual(before, [(p.read_bytes(), p.stat().st_mode) for p in files])

    def test_contiguous_tail_after_huge_anchor_is_valid(self):
        big = 10**30
        a = {**anchor(), 'anchor_seq': big}
        for tail in ([], [big_entry(big + 1, 1)], [big_entry(big + 2, 2), big_entry(big + 1, 1)]):
            with self.subTest(n=len(tail)):
                got = r.derive(a, tail)
                self.assertEqual(got['last_site_commit'], A)
                self.assertEqual(got['last_build_today'], '2026-11-06')
                self.assertEqual(got['pushes'], [])
        landed = [big_entry(big + 2, 2, 'live', B, C), big_entry(big + 1, 1, 'live', A, B)]
        got = r.derive(a, landed)
        self.assertEqual(got['last_site_commit'], C)
        self.assertEqual([p['change_id'] for p in got['pushes']], [j['change_id'] for j in landed])

    def test_sequence_gap_and_duplicate_boundaries_stay_closed(self):
        a = {**anchor(), 'anchor_seq': 5}
        for name, js in (('first gap', [entry(7)]), ('interior gap', [entry(6), entry(8)]),
                         ('tail gap beyond pre-anchor', [entry(3), entry(7)]),
                         ('duplicate', [entry(6), entry(6)]),
                         ('duplicate at anchor', [entry(5), entry(5)])):
            with self.subTest(name), self.assertRaises(r.BooksError): r.derive(a, js)
        self.assertEqual(r.derive(a, [entry(7), entry(3), entry(6)])['last_site_commit'], A)
        self.assertEqual(r.derive(a, [entry(3)])['last_site_commit'], A)
        js = [entry(7), entry(6)]
        snap = json.dumps([a, js])
        r.derive(a, js)
        self.assertEqual(snap, json.dumps([a, js]))

    def test_private_atomic_write_and_failure_prevents_next_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = r.Books(tmp)
            r.atomic(Path(tmp) / 'publish.json', anchor())
            j = entry()
            books.write(j)
            self.assertEqual((books.directory / (j['change_id'] + '.json')).stat().st_mode & 0o777, 0o600)
            self.assertEqual(books.directory.stat().st_mode & 0o777, 0o700)
            with patch.object(r.os, 'replace', side_effect=OSError('fixture')):
                with self.assertRaises(OSError): books.write(j, 'applied')
            self.assertEqual(j['state'], 'intent')
            self.assertEqual(books.journals()[0]['state'], 'intent')
            books.load()

    def test_missing_corrupt_wrong_mode_and_deleted_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = r.Books(tmp)
            path = Path(tmp) / 'publish.json'
            for data in (None, b'{', b'{}', b'{"x":1,"x":2}'):
                if data is not None: path.write_bytes(data); path.chmod(0o600)
                with self.assertRaises(r.BooksError): books.load()
            r.atomic(path, anchor())
            path.chmod(0o644)
            with self.assertRaises(r.BooksError): books.load()
            path.chmod(0o600)
            for j in (entry(), entry(2)): books.write(j)
            first = books.directory / 'chg-000000000001.json'
            first.unlink()
            with self.assertRaises(r.BooksError): books.load()
            books.write(entry())
            first.write_text('broken')
            with self.assertRaises(r.BooksError): books.load()
            books.write(entry())
            self.assertEqual(len(books.load()[1]), 2)

    def test_nonblocking_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = r.Books(tmp), r.Books(tmp)
            with a.lock() as held:
                self.assertTrue(held)
                with b.lock() as other: self.assertFalse(other)


if __name__ == '__main__': unittest.main()
