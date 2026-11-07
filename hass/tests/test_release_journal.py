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
