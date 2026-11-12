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

CAP = 1048576


def private_file(directory, name, data):
    path = Path(directory) / name
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(data)
    return path


def grow_after_lstat(path, extra):
    """Real lstat of path, then append extra bytes (valid JSON whitespace) before returning the captured result."""
    original = Path.lstat

    def lstat(self, *a, **kw):
        st = original(self, *a, **kw)
        if self == path:
            with open(path, 'ab') as stream: stream.write(extra)
        return st
    return patch.object(Path, 'lstat', lstat)


class ReadCapTests(unittest.TestCase):
    def test_read_refuses_growth_after_lstat_before_decode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = private_file(tmp, 'x.json', b'{"canary": 1}')
            with grow_after_lstat(path, b' ' * (CAP + 1 - 13)), patch.object(r.json, 'loads') as loads:
                with self.assertRaises(r.BooksError) as ctx: r.read(path)
            loads.assert_not_called()
            self.assertEqual(str(ctx.exception), 'release-books; run adopt if missing')
            self.assertNotIn('canary', repr(ctx.exception))

    def test_read_never_consumes_more_than_cap_plus_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = private_file(tmp, 'x.json', b'{"a": 1}')
            requests, returned = [], []
            real_fdopen, real_fstat = os.fdopen, os.fstat

            def grow_after_fstat(fd):  # growth after descriptor admission, before the read
                st = real_fstat(fd)
                with open(path, 'ab') as stream: stream.write(b' ' * (4 * CAP))
                return st

            def spy_open(fd, *a, **kw):
                stream = real_fdopen(fd, *a, **kw)
                real_read = stream.read

                class Spy:
                    def __enter__(s): return s
                    def __exit__(s, *e): stream.close()
                    def read(s, *args):
                        requests.append(args)
                        data = real_read(*args)
                        returned.append(len(data))
                        return data
                return Spy()
            with patch.object(r.os, 'fdopen', spy_open), patch.object(r.os, 'fstat', grow_after_fstat):
                with self.assertRaises(r.BooksError): r.read(path)
            self.assertTrue(requests and all(len(a) == 1 and 0 < a[0] <= CAP + 1 for a in requests))
            self.assertLessEqual(sum(returned), CAP + 1)

    def test_books_load_refuses_growing_anchor_and_journal(self):
        for target in ('anchor', 'journal'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                books = r.Books(tmp)
                r.atomic(Path(tmp) / 'publish.json', anchor())
                books.write(entry())
                path = Path(tmp) / 'publish.json' if target == 'anchor' else next(books.directory.iterdir())
                before = path.read_bytes()
                with grow_after_lstat(path, b' ' * (CAP + 1 - len(before))):
                    with self.assertRaises(r.BooksError): books.load()
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.stat().st_size, CAP + 1)

    def test_static_byte_boundary_is_inclusive(self):
        body = '{"t": "éé"}'.encode()
        with tempfile.TemporaryDirectory() as tmp:
            for size, ok in ((CAP - 1, True), (CAP, True), (CAP + 1, False)):
                with self.subTest(size=size):
                    path = private_file(tmp, f's{size}.json', body + b' ' * (size - len(body)))
                    if ok: self.assertEqual(r.read(path), {'t': 'éé'})
                    else:
                        with self.assertRaises(r.BooksError): r.read(path)

    def test_reader_decode_and_privacy_controls_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = {'a': 'é'}
            self.assertEqual(r.read(private_file(tmp, 'u8', json.dumps(good, ensure_ascii=False).encode())), good)
            self.assertEqual(r.read(private_file(tmp, 'u16', json.dumps(good).encode('utf-16'))), good)
            for i, bad in enumerate((b'{"a": 1, "a": 2}', b'[1]', b'{bad', b'', b'[' * 100000)):
                with self.subTest(bad=bad[:8]), self.assertRaises(r.BooksError): r.read(private_file(tmp, f'b{i}', bad))
            with self.assertRaises(r.BooksError): r.read(Path(tmp) / 'missing')
            wrong = private_file(tmp, 'mode', b'{}')
            wrong.chmod(0o644)
            with self.assertRaises(r.BooksError): r.read(wrong)


def swap_after_lstat(path, make):
    """Real lstat of path, then move the original aside and let make() install a replacement before returning."""
    original, fired = Path.lstat, []

    def lstat(self, *a, **kw):
        st = original(self, *a, **kw)
        if self == path and not fired:
            fired.append(1)
            os.rename(path, str(path) + '.orig')
            make()
        return st
    return patch.object(Path, 'lstat', lstat)


def wrote(path, data, mode):
    with open(path, 'wb') as stream: stream.write(data)
    os.chmod(path, mode)


class SubstitutionTests(unittest.TestCase):
    def refuses(self, path):
        with self.assertRaises(r.BooksError) as ctx: r.read(path)
        self.assertEqual(str(ctx.exception), 'release-books; run adopt if missing')
        self.assertNotIn('canary', repr(ctx.exception))

    def test_read_rejects_symlink_installed_after_lstat(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = private_file(tmp, 'x.json', b'{"a": 1}')
            foreign = Path(tmp) / 'foreign'
            wrote(foreign, b'{"canary": 1}', 0o644)
            with swap_after_lstat(path, lambda: os.symlink(foreign, path)), patch.object(r.json, 'loads') as loads:
                self.refuses(path)
            loads.assert_not_called()
            self.assertEqual(foreign.read_bytes(), b'{"canary": 1}')
            self.assertEqual(foreign.stat().st_mode & 0o777, 0o644)

    def test_read_rejects_replacement_inode_even_when_private(self):
        for mode in (0o644, 0o600):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                path = private_file(tmp, 'x.json', b'{"a": 1}')
                with swap_after_lstat(path, lambda: wrote(path, b'{"a": 1}', mode)): self.refuses(path)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(r.read(private_file(tmp, 'x.json', b'{"a": 1}')), {'a': 1})

    def test_opened_descriptor_metadata_is_rechecked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = private_file(tmp, 'x.json', b'{"a": 1}')
            original = Path.lstat

            def lstat(self, *a, **kw):
                st = original(self, *a, **kw)
                if self == path: os.chmod(path, 0o644)
                return st
            with patch.object(Path, 'lstat', lstat): self.refuses(path)
        with tempfile.TemporaryDirectory() as tmp:
            path = private_file(tmp, 'x.json', b'{"a": 1}')
            real = os.fstat

            def foreign_uid(fd):
                st = real(fd)
                return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid + 1, *tuple(st)[5:]))
            with patch.object(r.os, 'fstat', foreign_uid): self.refuses(path)

    def test_books_load_rejects_anchor_and_journal_substitution(self):
        for target in ('anchor', 'journal'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                books = r.Books(tmp)
                r.atomic(Path(tmp) / 'publish.json', anchor())
                books.write(entry())
                path = Path(tmp) / 'publish.json' if target == 'anchor' else next(books.directory.iterdir())
                body = path.read_bytes()
                with swap_after_lstat(path, lambda: wrote(path, body, 0o644)):
                    with self.assertRaises(r.BooksError): books.load()
                self.assertEqual(path.read_bytes(), body)
                self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_late_fifo_or_directory_refuses_without_blocking(self):
        makers = {'fifo': lambda p: os.mkfifo(p, 0o600), 'dir': lambda p: os.mkdir(p, 0o700)}
        for name, make in makers.items():
            with self.subTest(kind=name), tempfile.TemporaryDirectory() as tmp:
                path = private_file(tmp, 'x.json', b'{"a": 1}')
                with swap_after_lstat(path, lambda: make(path)): self.refuses(path)

    def test_descriptor_closes_on_every_reader_path(self):
        opened = []
        real_open, real_fstat = os.open, os.fstat

        def spy_open(p, *a, **kw):
            fd = real_open(p, *a, **kw)
            if a and a[0] & os.O_NOFOLLOW: opened.append(fd)
            return fd

        def closed(fd):
            with self.assertRaises(OSError): real_fstat(fd)
        with tempfile.TemporaryDirectory() as tmp, patch.object(r.os, 'open', spy_open):
            good = private_file(tmp, 'good', b'{"a": 1}')
            bad = private_file(tmp, 'bad', b'{bad')
            self.assertEqual(r.read(good), {'a': 1})
            self.refuses(bad)
            with patch.object(r.os, 'fstat', side_effect=OSError): self.refuses(good)
            with patch.object(r.os, 'fdopen', side_effect=OSError): self.refuses(good)
            swapped = private_file(tmp, 'swapped', b'{}')
            with swap_after_lstat(swapped, lambda: wrote(swapped, b'{}', 0o600)): self.refuses(swapped)
            self.assertEqual(r.read(good), {'a': 1})
        self.assertEqual(len(opened), 6)
        for fd in opened: closed(fd)

    def test_post_open_rename_cannot_redirect_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = private_file(tmp, 'x.json', b'{"a": "original"}')
            real_fdopen = os.fdopen

            def fdopen(fd, *a, **kw):
                os.rename(path, str(path) + '.orig')
                wrote(path, b'{"a": "replacement"}', 0o600)
                return real_fdopen(fd, *a, **kw)
            with patch.object(r.os, 'fdopen', fdopen): self.assertEqual(r.read(path), {'a': 'original'})


class ListingTests(unittest.TestCase):
    def refuses(self, books):
        for call in (books.journals, books.load, books.next_seq):
            with self.assertRaises(r.BooksError) as ctx: call()
            self.assertEqual(str(ctx.exception), 'release-books')
            self.assertTrue(ctx.exception.__suppress_context__)
            self.assertNotIn('canary', repr(ctx.exception))

    def make(self, tmp):
        books = r.Books(tmp)
        r.atomic(Path(tmp) / 'publish.json', anchor())
        return books

    def test_missing_release_directory_is_private_books_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = self.make(tmp)
            self.assertEqual(books.load()[1], [])
            os.rename(books.directory, Path(tmp) / 'aside')
            self.refuses(books)
            self.assertFalse(books.directory.exists())

    def test_directory_replaced_by_regular_file_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = self.make(tmp)
            os.rmdir(books.directory)
            private_file(tmp, 'releases', b'canary')
            self.refuses(books)
            self.assertEqual(books.directory.read_bytes(), b'canary')

    def test_permission_and_io_listing_failures_are_classified(self):
        for exc in (PermissionError(13, 'private-canary'), OSError(5, 'private-canary')):
            with tempfile.TemporaryDirectory() as tmp, self.subTest(exc=type(exc).__name__):
                books = self.make(tmp)
                with patch.object(Path, 'iterdir', side_effect=exc): self.refuses(books)

    def test_lazy_listing_failure_never_returns_partial_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = self.make(tmp)
            books.write(entry(1))
            first = next(books.directory.iterdir())
            def lazy(self):
                yield first
                raise OSError(5, 'private-canary')
            with patch.object(Path, 'iterdir', lazy), patch.object(r, 'read') as rd:
                self.refuses(books)
                self.assertFalse([c for c in rd.call_args_list if c.args[0].parent == books.directory])

    def test_empty_sorted_and_temporary_entries_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            books = self.make(tmp)
            self.assertEqual(books.journals(), [])
            for n in (2, 1): books.write(entry(n, 'intent'))
            private_file(books.directory, '.release-tmp', b'not json')
            self.assertEqual([j['seq'] for j in books.journals()], [1, 2])
            self.assertEqual(books.next_seq(), 3)

    def test_existing_load_alert_boundary_recognizes_listing_error(self):
        from types import SimpleNamespace
        from hass import publish_live
        with tempfile.TemporaryDirectory() as tmp:
            books = self.make(tmp)
            os.rmdir(books.directory)
            seen = []
            stand_in = SimpleNamespace(books=books, alerts=set(), alert=seen.append)
            with self.assertRaises(r.BooksError): publish_live.LiveEditor.load(stand_in)
            self.assertEqual(seen, ['release-books'])
            with patch.object(Path, 'iterdir', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt): books.journals()
            with patch.object(Path, 'iterdir', side_effect=TypeError):
                with self.assertRaises(TypeError): books.journals()


if __name__ == '__main__': unittest.main()
