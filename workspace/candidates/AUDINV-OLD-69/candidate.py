#!/usr/bin/env python3
"""Offline policy proposal, not an adapter for the live subscription database."""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).absolute().parent
PURPOSES = ('newsletter', 'hiking')
SAFE = 'Request received.'
OWNED = ('candidate.py', 'fixtures.json', 'BASES.json', 'SOURCES.json', 'RESULT.md', 'README.md')
TEST_NAMES = (
    'test_explicit_purpose_optin_allows_only_matching_fake_delivery',
    'test_missing_consent_and_other_purpose_suppress_delivery',
    'test_revocation_after_enqueue_blocks_send_at_boundary',
    'test_unsubscribe_is_idempotent_and_blocks_future_delivery',
    'test_duplicate_send_key_invalid_token_and_no_real_transport',
    'test_schema_path_escape_symlink_and_side_effect_boundary',
)


def require(ok):
    if not ok:
        raise ValueError('invalid offline candidate input')


def stamp(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value))
    dt.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    return value


def identity(alias, purpose):
    require(isinstance(alias, str) and re.fullmatch(r'fixture-[a-z]+', alias))
    require(purpose in PURPOSES)


def package_path(name):
    p = Path(name)
    require(not p.is_absolute() and len(p.parts) == 1 and p.name in OWNED)
    path = ROOT / p
    require(not any(x.is_symlink() for x in (path, *path.parents)))
    require(path.resolve().parent == ROOT.resolve())
    return path


def pairs(items):
    out = {}
    for k, v in items:
        require(k not in out)
        out[k] = v
    return out


def decode(text):
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False))


def load(name):
    return decode(package_path(name).read_text())


def digest(name):
    return hashlib.sha256(package_path(name).read_bytes()).hexdigest()


class RecordingFakeTransport:
    def __init__(self):
        self.records = []

    def record(self, key):
        self.records.append(key)


class Policy:
    """Single-threaded, in-memory fixtures only; tokens are NOT production authentication."""
    def __init__(self, transport):
        require(type(transport) is RecordingFakeTransport)
        self.transport = transport
        self.consent, self.pending, self.tokens = {}, {}, {}
        self.sent, self.cancelled, self.events = set(), set(), []
        self.clock = ''

    def tick(self, now):
        stamp(now)
        require(now >= self.clock)
        self.clock = now

    def opt_in(self, alias, purpose, revision, now, until):
        identity(alias, purpose)
        stamp(now); stamp(until)
        require(type(revision) is int and revision > 0 and now < until)
        old = self.consent.get((alias, purpose))
        require(old is None or revision > old['revision'])
        self.tick(now)
        self.consent[alias, purpose] = dict(revision=revision, at=now, until=until, revoked=False)
        self.events.append(('opt_in', alias, purpose, revision, now))
        # Deterministic fixture capability registered here, never accepted just by its shape.
        token = hashlib.sha256(f'OFFLINE|{alias}|{purpose}|{revision}|{now}'.encode()).hexdigest()
        self.tokens[token] = (alias, purpose, revision, until)
        return token

    def allowed(self, alias, purpose, now):
        c = self.consent.get((alias, purpose))
        return c is not None and not c['revoked'] and c['at'] <= now < c['until']

    def enqueue(self, message, alias, purpose, now):
        identity(alias, purpose)
        require(isinstance(message, str) and re.fullmatch(r'message-[a-z]+', message))
        self.tick(now)
        key = (message, purpose, alias)
        if not self.allowed(alias, purpose, now) or key in self.cancelled:
            return None
        if key not in self.sent:
            self.pending.setdefault(key, self.consent[alias, purpose]['revision'])
        return key

    def cancel(self, key):
        self.cancelled.add(key)
        self.pending.pop(key, None)

    def deliver(self, key, now):
        self.tick(now)
        if key not in self.pending or key in self.sent or key in self.cancelled:
            return False
        _, purpose, alias = key
        revision = self.pending.pop(key)
        # No callbacks or I/O between this final consent check and recording.
        if not self.allowed(alias, purpose, now) or self.consent[alias, purpose]['revision'] != revision:
            return False
        self.transport.record(key)
        self.sent.add(key)
        self.events.append(('fake_delivery', *key, now))
        return True

    def unsubscribe(self, token, now):
        self.tick(now)
        ref = self.tokens.get(token) if isinstance(token, str) else None
        if ref is not None:
            alias, purpose, revision, until = ref
            c = self.consent[alias, purpose]
            if now < until and c['revision'] == revision and not c['revoked']:
                c['revoked'] = True
                self.events.append(('revoke', alias, purpose, revision, now))
        return SAFE


def fixtures():
    f = load('fixtures.json')
    require(set(f) == {'schema_version', 'alias', 'at', 'later', 'expires', 'after', 'cases'})
    require(type(f['schema_version']) is int and f['schema_version'] == 1)
    identity(f['alias'], 'newsletter')
    for k in ('at', 'later', 'expires', 'after'):
        stamp(f[k])
    require(f['at'] < f['later'] < f['expires'] < f['after'])
    expected = {'newsletter_only': 1, 'hiking_only': 1, 'missing': 0, 'other_purpose': 0,
                'revoked_pending': 0, 'unsubscribed_future': 0, 'duplicate': 1,
                'cancelled': 0, 'expired': 0, 'stale_revision': 0}
    require(f['cases'] == expected and all(type(v) is int for v in f['cases'].values()))
    return f


def validate_report(text, sources):
    require(text.count('```json\n') == 1)
    data = decode(text.split('```json\n')[1].split('\n```')[0])
    bases = load('BASES.json')
    require(set(bases) == {'schema_version', 'main', 'source_sha256', 'candidate_sha256',
                           'candidate_only', 'installed', 'no_apply'})
    require(bases['schema_version'] == 1 and re.fullmatch(r'[0-9a-f]{40}', bases['main']))
    require(bases['candidate_only'] is True and bases['installed'] is False and bases['no_apply'] is True)
    require(set(bases['candidate_sha256']) == {'candidate.py', 'fixtures.json', 'README.md'})
    require(all(digest(k) == v for k, v in bases['candidate_sha256'].items()))
    require(set(sources) == {'schema_version', 'main', 'captured_at', 'sources', 'missing'})
    require(type(sources['schema_version']) is int and sources['schema_version'] == 1)
    stamp(sources['captured_at'])
    require(sources['main'] == bases['main'])
    require(sources['missing'] == ['live_delivery', 'provider_setup', 'owner_acceptance', 'production_integration'])
    refs = sources['sources']
    require(isinstance(refs, list) and len(refs) == 3)
    paths = ['storefront-mockup/community-server.py', 'storefront-mockup/README.md', 'docs/hass/OPERATIONS.md']
    for r, path in zip(refs, paths):
        require(set(r) == {'path', 'sha256', 'lines', 'observation'})
        require(r['path'] == path and re.fullmatch(r'[0-9a-f]{64}', r['sha256']))
        require(isinstance(r['lines'], str) and re.fullmatch(r'\d+-\d+', r['lines']))
        require(isinstance(r['observation'], str) and bool(r['observation']))
    require(bases['source_sha256'] == {r['path']: r['sha256'] for r in refs})
    expected = dict(schema_version=1, status='CANDIDATE_ONLY / REVIEW_REQUIRED', installed=False,
                    main=bases['main'], sources_sha256=digest('SOURCES.json'),
                    bases_sha256=digest('BASES.json'), test_count=len(TEST_NAMES),
                    tests=list(TEST_NAMES), fixture_cases=fixtures()['cases'],
                    live_delivery='HOLD', provider_setup='UNVERIFIED', owner_acceptance='UNVERIFIED',
                    production_integration='UNVERIFIED')
    require(data == expected)
    return data


class Acceptance(unittest.TestCase):
    def setUp(self):
        self.f = fixtures()
        self.t = RecordingFakeTransport()
        self.p = Policy(self.t)
        self.a, self.n = self.f['alias'], self.f['at']

    def opt(self, purpose='newsletter', revision=1, now=None):
        return self.p.opt_in(self.a, purpose, revision, now or self.n, self.f['expires'])

    def queue(self, purpose='newsletter', message='message-one', now=None):
        return self.p.enqueue(message, self.a, purpose, now or self.n)

    def test_explicit_purpose_optin_allows_only_matching_fake_delivery(self):
        for purpose in PURPOSES:
            self.setUp(); self.opt(purpose)
            key = self.queue(purpose)
            self.assertTrue(self.p.deliver(key, self.n))
            self.assertEqual(self.t.records, [key])
            self.assertIsNone(self.queue(next(x for x in PURPOSES if x != purpose)))
            with self.assertRaises(ValueError):
                self.opt(purpose, revision=1)
            self.assertEqual(self.p.events[0], ('opt_in', self.a, purpose, 1, self.n))

    def test_missing_consent_and_other_purpose_suppress_delivery(self):
        self.assertIsNone(self.queue())
        self.assertFalse(self.p.deliver(('message-one', 'newsletter', self.a), self.n))
        self.opt('hiking')
        self.assertIsNone(self.queue())
        self.assertEqual(len(self.t.records), self.f['cases']['other_purpose'])
        key = self.queue('hiking')
        self.assertFalse(self.p.deliver(key, self.f['expires']))
        self.assertIsNone(self.queue('hiking', now=self.f['after']))
        self.assertEqual(len(self.t.records), self.f['cases']['expired'])

    def test_revocation_after_enqueue_blocks_send_at_boundary(self):
        token = self.opt(); key = self.queue()
        self.p.unsubscribe(token, self.f['later'])
        self.assertFalse(self.p.deliver(key, self.f['later']))
        self.assertEqual(len(self.t.records), self.f['cases']['revoked_pending'])
        self.opt(revision=2, now=self.f['later'])
        key = self.queue(message='message-stale', now=self.f['later'])
        self.opt(revision=3, now=self.f['later'])
        self.assertFalse(self.p.deliver(key, self.f['later']))
        self.assertEqual(len(self.t.records), self.f['cases']['stale_revision'])
        self.p.unsubscribe(token, self.f['later'])  # stale token cannot revoke revision 3
        fresh = self.queue(message='message-new', now=self.f['later'])
        self.assertTrue(self.p.deliver(fresh, self.f['later']))

    def test_unsubscribe_is_idempotent_and_blocks_future_delivery(self):
        token = self.opt(); key = self.queue()
        before = tuple(self.p.events)
        self.assertEqual(self.p.unsubscribe(token, self.n), SAFE)
        after = tuple(self.p.events)
        self.assertEqual(self.p.unsubscribe(token, self.n), SAFE)
        self.assertEqual(tuple(self.p.events), after)
        self.assertEqual(after[:len(before)], before)
        self.assertEqual(after[-1][0], 'revoke')
        self.assertFalse(self.p.deliver(key, self.n))
        self.assertIsNone(self.queue(message='message-future'))
        self.assertEqual(len(self.t.records), self.f['cases']['unsubscribed_future'])
        self.opt('hiking')
        self.assertTrue(self.p.deliver(self.queue('hiking'), self.n))

    def test_duplicate_send_key_invalid_token_and_no_real_transport(self):
        token = self.opt(); key = self.queue()
        for bad in ('forged', token[:-1], '', None, {'token': token}):
            self.assertEqual(self.p.unsubscribe(bad, self.n), SAFE)
        self.assertEqual(len(self.p.events), 1)
        self.assertEqual(self.queue(), key)
        self.assertTrue(self.p.deliver(key, self.n))
        self.assertEqual(self.queue(), key)
        self.assertFalse(self.p.deliver(key, self.n))
        self.assertEqual(len(self.t.records), self.f['cases']['duplicate'])
        cancelled = self.queue(message='message-cancelled')
        self.p.cancel(cancelled)
        self.assertFalse(self.p.deliver(cancelled, self.n))
        self.assertIsNone(self.queue(message='message-cancelled'))
        self.assertEqual(self.p.unsubscribe(token, self.f['after']), SAFE)
        self.assertEqual(len(self.p.events), 2)  # expired token adds no revoke
        class RealLooking:
            def record(self, key):
                raise AssertionError('must never call an arbitrary transport')
        with self.assertRaises(ValueError):
            Policy(RealLooking())
        self.assertFalse(hasattr(self.p, 'send'))

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        for bad in ('../RESULT.md', '/etc/passwd', '~/.ssh/id_rsa', 'absent.json'):
            with patch.object(Path, 'read_text', side_effect=AssertionError('opened before validation')):
                with self.assertRaises(ValueError):
                    load(bad)
        with patch.object(Path, 'is_symlink', return_value=True):
            with self.assertRaises(ValueError):
                package_path('RESULT.md')
        with self.assertRaises(ValueError):
            decode('{"schema_version":1,"schema_version":1}')
        for change in ({'schema_version': 2}, {'schema_version': True}, {'alias': 'person@example.com'},
                       {'at': '2026-13-01T00:00:00Z'}, {'extra': 1}):
            with patch(__name__ + '.load', return_value={**self.f, **change}):
                with self.assertRaises(ValueError):
                    fixtures()
        for args in ((self.a, 'other', 1, self.n, self.f['expires']),
                     (self.a, 'newsletter', 0, self.n, self.f['expires']),
                     (self.a, 'newsletter', 1, self.n, self.n)):
            with self.assertRaises(ValueError):
                self.p.opt_in(*args)
        self.opt()
        with self.assertRaises(ValueError):
            self.p.deliver(self.queue(), '2020-01-01T00:00:00Z')
        self.assertEqual(self.t.records, [])
        sources = load('SOURCES.json')
        report = package_path('RESULT.md').read_text()
        validate_report(report, sources)
        for old, new in (('"test_count": 6', '"test_count": 7'), ('"HOLD"', '"PASS"'),
                         (digest('SOURCES.json'), '0' * 64)):
            self.assertIn(old, report)
            with self.assertRaises(ValueError):
                validate_report(report.replace(old, new), sources)


def fence(attempts):
    """Block network/processes and all reads/writes outside the exact package."""
    def audit(event, args):
        denied = event.startswith(('socket.', 'subprocess.', 'sqlite3.')) or event in ('os.system', 'os.posix_spawn')
        if event == 'open':
            path, mode, flags = args
            if isinstance(path, (str, bytes, os.PathLike)):
                p = Path(os.fsdecode(path)).absolute()
                denied = (p.parent != ROOT or p.name not in OWNED or p.is_symlink()
                          or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
            else:
                denied = True
        if event.startswith(('os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.symlink', 'os.link')):
            denied = True
        if denied:
            attempts.append(event)
            raise PermissionError('offline boundary')
    sys.addaudithook(audit)


def main():
    ap = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--check')
    ap.add_argument('--sources')
    args = ap.parse_args()
    if not ((args.self_test and not args.check and not args.sources) or
            (not args.self_test and args.check and args.sources)):
        ap.print_usage(); return 2
    attempts = []
    # Preload strptime internals before enabling the package-only read fence.
    stamp('2026-01-01T00:00:00Z')
    try:
        package_path('candidate.py')
        fence(attempts)
        if args.self_test:
            output = io.StringIO()
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance)
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
            print(output.getvalue(), end='')
            print(f'OFFLINE: tests={result.testsRun}; disallowed_io_attempts={len(attempts)}; real_delivery=NOT_RUN')
            return 0 if result.wasSuccessful() and not attempts else 1
        validate_report(package_path(args.check).read_text(), load(args.sources))
        print('CHECK PASS: schema=1; source/hash bindings exact; tests=6; live=HOLD; review=REQUIRED')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'REFUSED: {type(exc).__name__}'); return 1


if __name__ == '__main__':
    sys.exit(main())
