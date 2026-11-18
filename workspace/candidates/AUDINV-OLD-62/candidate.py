#!/usr/bin/env python3
"""Local-only OLD-62 recovery probe. No apply, live mode, provider or service operations."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.dont_write_bytecode = True
PACKAGE = Path(__file__).absolute().parent
if any(p.is_symlink() for p in (PACKAGE, *PACKAGE.parents)):
    raise ValueError('symlinked package root')
ROOT = PACKAGE.parents[2]
WORKSPACE = ROOT.parent
OBSERVED = {}
MISSING = ['live_reboot_sleep', 'support_agreement', 'ownership_handover', 'attended_owner_usability',
           'production_ambiguous_transport_dedup']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate key')
        obj[key] = value
    return obj


def local(name):
    p = Path(name)
    if p.is_absolute() or not p.parts or any(x in ('.', '..') for x in p.parts):
        raise ValueError('package-relative path required')
    p = PACKAGE / p
    if any(x.is_symlink() for x in (p, *p.parents)) or not p.resolve().is_relative_to(PACKAGE):
        raise ValueError('unsafe package path')
    return p


def decode(text):
    obj = json.loads(text, object_pairs_hook=unique)
    if not isinstance(obj, dict) or type(obj.get('schema_version')) is not int or obj['schema_version'] != 1:
        raise ValueError('schema_version must be 1')
    return obj


def read(name):
    return decode(local(name).read_text())


def fixture():
    f = read('fixtures.json')
    if set(f) != {'schema_version', 'id', 'at', 'photo_hex', 'expected'} or f['id'] != 'synthetic-old62':
        raise ValueError('fixture identity')
    if datetime.fromisoformat(f['at']).utcoffset() is None:
        raise ValueError('aware timestamp required')
    if not re.fullmatch(r'[0-9a-f]+', f['photo_hex']) or len(f['photo_hex']) % 2:
        raise ValueError('photo encoding')
    if not isinstance(f['expected'], dict) or not f['expected']:
        raise ValueError('expectations missing')
    return f


def bindings():
    bases = read('BASES.json')
    if set(bases) != {'schema_version', 'main', 'candidate_only', 'installed', 'apply_authorized', 'helpers'}:
        raise ValueError('base schema')
    if (bases['candidate_only'], bases['installed'], bases['apply_authorized']) != (True, False, False):
        raise ValueError('candidate boundary')
    if not re.fullmatch(r'[0-9a-f]{40}', bases['main']):
        raise ValueError('main identity')
    for name, digest in bases['helpers'].items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or p.parts[0] != 'hass' or p.suffix != '.py':
            raise ValueError('helper path')
        target = ROOT / p
        if any(x.is_symlink() for x in (target, *target.parents)) or sha(target) != digest:
            raise ValueError('stale helper')
    return {**bases['helpers'], **{str((PACKAGE / n).relative_to(ROOT)): sha(local(n))
            for n in ('candidate.py', 'fixtures.json', 'BASES.json', 'README.md')}}


def helpers():
    bindings()  # verify unchanged source before import; no copied production controller
    sys.path.insert(0, str(ROOT))
    from hass import editor, inbox, media, conversation
    from hass.skills import openreq
    loaded = {str(Path(m.__file__).relative_to(ROOT)) for m in list(sys.modules.values())
              if getattr(m, '__file__', None) and Path(m.__file__).is_relative_to(ROOT / 'hass')}
    if not loaded.issubset(read('BASES.json')['helpers']):
        raise ValueError('unbound helper closure')
    return editor, inbox, media, conversation, openreq


class Interrupted(BaseException):
    pass


class Stub:
    def __init__(self, boundary):
        self.boundary, self.attempted, self.accepted = boundary, 0, 0

    def send(self, chat, text, attachments):
        if chat != 'fixture-owner' or attachments:
            raise ValueError('nonfixture transport identity')
        self.attempted += 1
        if self.boundary == 'before_accept':
            raise TimeoutError('fixture interruption')
        self.accepted += 1
        if self.boundary == 'after_accept':
            raise TimeoutError('fixture acceptance response lost')


@contextlib.contextmanager
def fence(home):
    """Deny network/process control, non-git children and out-of-fixture Python writes.

    Git is allowed only with -C inside the fresh fixture. Its children inherit an
    empty synthetic HOME and no global/system config. No shell or hooks supplied.
    """
    events = []
    def denied(*args, **kwargs):
        events.append('disallowed')
        raise AssertionError('disallowed I/O')
    real_open = os.open
    def in_fixture(path):
        if not Path(path).resolve().is_relative_to(home):
            denied()
    def file_opener(original):
        def opened(path, mode='r', *args, **kwargs):
            if not isinstance(path, int) and any(c in mode for c in 'wax+'):
                in_fixture(path)
            return original(path, mode, *args, **kwargs)
        return opened
    import builtins
    real_connect = sqlite3.connect
    def connect(path, *args, **kwargs):
        in_fixture(path)
        return real_connect(path, *args, **kwargs)
    def checked_open(path, flags, *args, **kwargs):
        if not isinstance(path, int) and (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
            if not Path(path).resolve().is_relative_to(home):
                return denied()
        return real_open(path, flags, *args, **kwargs)
    real_popen = subprocess.Popen
    def git_only(argv, *args, **kwargs):
        if not isinstance(argv, list) or argv[:2] != ['git', '-C'] or not Path(argv[2]).resolve().is_relative_to(home):
            return denied()
        env = dict(os.environ, HOME=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                   GIT_AUTHOR_NAME='synthetic', GIT_AUTHOR_EMAIL='synthetic@example.invalid',
                   GIT_COMMITTER_NAME='synthetic', GIT_COMMITTER_EMAIL='synthetic@example.invalid')
        kwargs['env'] = env
        return real_popen(argv, *args, **kwargs)
    import socket
    with mock.patch('socket.socket', denied), mock.patch('socket.create_connection', denied), \
         mock.patch('builtins.open', file_opener(builtins.open)), mock.patch('io.open', file_opener(io.open)), \
         mock.patch('sqlite3.connect', connect), \
         mock.patch('os.kill', denied), mock.patch('os.killpg', denied), \
         mock.patch('os.system', denied), mock.patch('os.open', checked_open), \
         mock.patch('subprocess.Popen', git_only):
        yield events


class Scenario:
    def __init__(self, home):
        self.home, self.f = home, fixture()
        self.ed, self.inmod, self.media, self.conv, self.reqmod = helpers()
        self.now = datetime.fromisoformat(self.f['at'])
        self.main, self.wt, self.state = (home / n for n in ('main', 'writer', 'state'))
        self.main.mkdir()
        for name in set(self.ed.OWNED_PATHS + self.ed.REVISION_PATHS):
            p = self.main / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'{"synthetic":"old"}\n' if name.endswith('.json') else b'synthetic old\n')
        self.git(self.main, 'init', '-q', '-b', 'main')
        self.git(self.main, 'config', 'user.name', 'synthetic')
        self.git(self.main, 'config', 'user.email', 'synthetic@example.invalid')
        self.git(self.main, '-c', 'maintenance.auto=false', 'add', '.')
        self.git(self.main, '-c', 'maintenance.auto=false', 'commit', '-qs', '-m', 'synthetic base')
        self.git(self.main, 'worktree', 'add', '-qb', 'fixture/content', str(self.wt))
        self.state.mkdir(mode=0o700)
        initialized = self.ed.init(str(self.state), str(self.wt))
        if initialized['result'] != 'ok':
            raise AssertionError(initialized)
        self.cid = 'chg-123456789abc'

    def git(self, wt, *args):
        return subprocess.run(['git', '-C', str(wt), *args], capture_output=True, text=True,
                              check=True, timeout=15).stdout.strip()

    def db(self):
        from hass.memory import private_db
        db = sqlite3.connect(private_db(self.state, 'conversation.sqlite3'), isolation_level=None)
        db.row_factory = sqlite3.Row
        db.executescript(self.conv.SCHEMA)
        return db

    def journal(self, committed):
        base = self.git(self.wt, 'rev-parse', 'HEAD')
        self.ed._write_json(self.state / 'drafts' / (self.cid + '.json'),
                            {'base': self.ed.content_revision(self.wt), 'records': [], 'generated': []})
        self.ed._write_json(self.state / 'journal' / (self.cid + '.json'),
                            {'phase': 'writing', 'base_commit': base, 'paths': ['hass/content/store.json']})
        self.ed.sitegen.write_files({'hass/content/store.json': b'{"synthetic":"new"}\n'}, self.wt)
        if committed:
            self.git(self.wt, 'add', '.')
            self.git(self.wt, '-c', 'maintenance.auto=false', 'commit', '-qs', '-m', 'hass content: ' + self.cid)
        # New API call reloads config, HEAD, journal and draft from disk (no cached writer).
        recovered = self.ed.recover(state=str(self.state), now=self.now)
        if recovered['result'] != 'ok':
            raise AssertionError(recovered)
        record = json.loads((self.state / 'changes' / (self.cid + '.json')).read_text())
        return record['state'], json.loads((self.wt / 'hass/content/store.json').read_text())['synthetic']


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='old62-', dir=WORKSPACE.resolve())
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.guard = self.enterContext(fence(self.home))
        self.s = Scenario(self.home)

    def record(self, key, value):
        self.assertEqual(value, self.s.f['expected'][key])
        OBSERVED[key] = value

    def test_content_media_assistant_and_release_identity_survive_fixture_recreation(self):
        s = self.s
        self.assertEqual(s.journal(True), ('applied', 'new'))
        self.record('after_commit', 'PASS')
        photo = bytes.fromhex(s.f['photo_hex'])
        first = s.media.store_original(self.home / 'media', photo, received_at=s.f['at'], source='synthetic')
        sidecar = Path(first['path']).with_suffix('.json').read_bytes()
        again = s.media.store_original(self.home / 'media', photo, received_at=s.f['at'], source='synthetic')
        self.assertTrue(again['duplicate'])
        self.assertEqual(Path(again['path']).read_bytes(), photo)
        self.assertEqual(Path(again['path']).with_suffix('.json').read_bytes(), sidecar)
        # Interrupt between durable original bytes and sidecar, then recreate the store call.
        other = self.home / 'interrupted-media'
        write_new = s.media._write_new
        def interrupted(final, data, created=None):
            if final.suffix == '.json':
                raise Interrupted()
            return write_new(final, data, created)
        with mock.patch.object(s.media, '_write_new', interrupted):
            with self.assertRaises(Interrupted):
                s.media.store_original(other, photo, received_at=s.f['at'], source='synthetic')
        repaired = s.media.store_original(other, photo, received_at=s.f['at'], source='synthetic')
        self.assertTrue(repaired['duplicate'])
        self.assertEqual(Path(repaired['path']).with_suffix('.json').read_bytes(), sidecar)
        db = s.db()
        req = s.reqmod.OpenRequests(db)
        req.put('fixture-owner', 'synthetic-1', s.now, texts=['Synthetic question'], skill='fixture')
        s.conv.Outbox(db, lambda: s.now).add('fixture-owner', 'Which day?')
        before = dict(req.get('fixture-owner', s.now))
        db.close()
        db = s.db()
        self.addCleanup(db.close)
        self.assertEqual(s.reqmod.OpenRequests(db).get('fixture-owner', s.now), before)
        self.assertEqual(len(s.conv.Outbox(db, lambda: s.now).unsent()), 1)
        inbox = s.inmod.Inbox(str(s.state), s.f['at'], lambda: s.now)
        msg = s.conv.Inbound('synthetic-1', 'fixture-owner', 'synthetic@example.invalid', 'question',
                             False, 'new', s.f['at'])
        self.assertEqual(inbox.enqueue(msg), 'queued')
        inbox.close()
        inbox = s.inmod.Inbox(str(s.state), clock=lambda: s.now)
        self.addCleanup(inbox.close)
        self.assertEqual(inbox.enqueue(msg), 'duplicate')
        self.assertEqual(inbox.state(msg.provider_id), 'pending')
        pointer = self.home / 'served-release.json'
        s.ed._write_json(pointer, {'revision': s.ed.content_revision(s.wt), 'phase': 'released'})
        self.assertEqual(json.loads(pointer.read_text())['revision'], s.ed.content_revision(s.wt))
        for conn in (db, inbox.db):
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.record('identity', 'PASS')

    def test_interrupt_before_and_after_durable_commit_never_tears_state(self):
        self.assertEqual(self.s.journal(False), ('failed', 'old'))
        self.assertFalse(list((self.s.state / 'journal').glob('*.json')))
        self.assertEqual(self.s.ed.recover(state=str(self.s.state))['recovered'], [])
        self.record('before_commit', 'PASS')


    def test_ambiguous_stub_acceptance_suppresses_duplicate_send(self):
        for boundary, accepted in [('before_accept', 0), ('after_accept', 1)]:
            with self.subTest(boundary=boundary):
                db = self.s.db()
                box = self.s.conv.Outbox(db, lambda: self.s.now)
                box.add('fixture-owner', 'Which day?')
                stub = Stub(boundary)
                with self.assertRaises(TimeoutError):
                    box.flush(stub)
                db.close()
                db = self.s.db()
                box = self.s.conv.Outbox(db, lambda: self.s.now)
                self.assertTrue(box.unsent())
                # Candidate deliberately stops: a pending row cannot prove non-acceptance.
                self.assertEqual((stub.attempted, stub.accepted), (1, accepted))
                if boundary == 'after_accept':
                    stub.boundary = 'success'
                    box.flush(stub)  # synthetic negative control: demonstrate real helper's retry gap
                    self.assertEqual((stub.attempted, stub.accepted), (2, 2))
                    self.record('forced_retry', {'status': 'FAIL', 'attempted': 2, 'accepted': 2})
                db.execute('DELETE FROM outbox')
                db.close()
                self.record(boundary, {'status': 'HOLD', 'attempted': 1, 'accepted': accepted})

    def test_incomplete_release_is_paused_or_held_not_healthy(self):
        p = self.home / 'served-release.json'
        self.s.ed._write_json(p, {'revision': 'synthetic-old', 'phase': 'released'})
        old = p.read_bytes()
        with mock.patch.object(self.s.ed.sitegen.os, 'replace', side_effect=Interrupted):
            with self.assertRaises(Interrupted):
                self.s.ed._write_json(p, {'revision': 'synthetic-new', 'phase': 'switching'})
        self.assertEqual(p.read_bytes(), old)
        self.s.ed._write_json(p, {'revision': 'synthetic-new', 'phase': 'switching'})
        self.assertEqual(json.loads(p.read_text())['phase'], 'switching')
        self.record('incomplete_release', 'HOLD')  # fixture policy only, no runtime_release import

    def test_cancelled_expired_stale_and_interrupted_assistant_transaction(self):
        s = self.s
        db = s.db()
        req = s.reqmod.OpenRequests(db)
        req.put('fixture-owner', 'synthetic-1', s.now, texts=['Synthetic'], skill='fixture')
        db.execute('BEGIN IMMEDIATE')
        req.close_live('fixture-owner', s.now, 'cancelled')
        db.close()  # process-object recreation rolls back an uncommitted cancellation
        db = s.db()
        self.addCleanup(db.close)
        req = s.reqmod.OpenRequests(db)
        self.assertIsNotNone(req.get('fixture-owner', s.now))
        req.close_live('fixture-owner', s.now, 'cancelled')
        self.assertIsNone(req.get('fixture-owner', s.now))
        req.put('fixture-owner', 'synthetic-2', s.now, texts=['Synthetic'], skill='fixture')
        self.assertIsNone(req.get('fixture-owner', s.now + timedelta(minutes=31)))
        self.assertIsNone(req.by_provider('fixture-owner', 'stale-provider', s.now))
        self.record('assistant_negative_paths', 'PASS')

    def test_no_existing_process_service_or_real_transport_is_touched(self):
        self.assertEqual(self.guard, [])
        self.assertNotIn('hass.runtime_release', sys.modules)
        self.record('isolation', 'PASS')

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        for text in ('{}', '{"schema_version":2}', '{"schema_version":1,"schema_version":1}'):
            with self.assertRaises(ValueError):
                decode(text)
        f = fixture()
        for key, bad in [('id', 'real'), ('at', '2026-11-15'), ('photo_hex', 'xx'), ('extra', True)]:
            with mock.patch.dict(globals(), read=lambda name: {**f, key: bad}):
                with self.assertRaises(ValueError):
                    fixture()
        for name in ('../RESULT.md', '/etc/passwd', '/home/user/.local/share/avocado-shack'):
            with mock.patch.object(Path, 'open', side_effect=AssertionError('opened before admission')):
                with self.assertRaises(ValueError):
                    local(name)
        # No package mutation: exercise a temporary symlink under an independently bound package root.
        link = self.home / 'link'
        link.symlink_to('/etc/passwd')
        with mock.patch.dict(globals(), PACKAGE=self.home):
            with self.assertRaises(ValueError):
                local('link')
        self.assertEqual(self.guard, [])
        self.record('schema_paths', 'PASS')
        receipt = dict(schema_version=1, sources_sha256='a' * 64, status='CANDIDATE_ONLY / REVIEW_REQUIRED',
                       installed=False, observed=fixture()['expected'],
                       unverified={n: 'UNVERIFIED' for n in MISSING}, tests=dict(run=7, failures=0, errors=0))
        validate_receipt(receipt, 'a' * 64)
        for key, bad in [('installed', True), ('status', 'HEALTHY'), ('tests', dict(run=0)),
                         ('unverified', {}), ('observed', {}), ('sources_sha256', 'b' * 64)]:
            with self.subTest(false_claim=key), self.assertRaises(ValueError):
                validate_receipt({**receipt, key: bad}, 'a' * 64)


def check(result, sources):
    src = read(sources)
    if set(src) != {'schema_version', 'captured_at', 'bindings', 'missing', 'citations'}:
        raise ValueError('source schema')
    if datetime.fromisoformat(src['captured_at']).utcoffset() is None or src['bindings'] != bindings():
        raise ValueError('source timestamp or bindings')
    if src['missing'] != MISSING or not src['citations']:
        raise ValueError('missing coverage')
    text = local(result).read_text()
    match = re.fullmatch(r'.*<!-- OLD62_RECEIPT\n(.*?)\nOLD62_RECEIPT -->\n', text, re.S)
    if not match:
        raise ValueError('receipt absent')
    validate_receipt(decode(match[1]), sha(local(sources)))
    print('CHECK PASS: schema=1; 10 boundaries; 7 local tests; known retry FAIL and HOLD retained; 5 UNVERIFIED; NOT_INSTALLED')


def validate_receipt(rec, source_digest):
    if set(rec) != {'schema_version', 'sources_sha256', 'status', 'installed', 'observed', 'unverified', 'tests'}:
        raise ValueError('receipt schema')
    if (rec['schema_version'] != 1 or rec['sources_sha256'] != source_digest or rec['status'] != 'CANDIDATE_ONLY / REVIEW_REQUIRED'
            or rec['installed'] is not False or rec['observed'] != fixture()['expected']
            or rec['unverified'] != {n: 'UNVERIFIED' for n in MISSING}
            or rec['tests'] != {'run': 7, 'failures': 0, 'errors': 0}):
        raise ValueError('false success, counts or source bindings')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--self-test', action='store_true')
    group.add_argument('--check')
    ap.add_argument('--sources')
    args = ap.parse_args()
    try:
        if args.self_test:
            if args.sources:
                ap.error('--sources requires --check')
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests)
            result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
            print('OBSERVED ' + json.dumps(OBSERVED, sort_keys=True))
            return 0 if result.wasSuccessful() and OBSERVED == fixture()['expected'] else 1
        if not args.sources:
            ap.error('--check requires --sources')
        check(args.check, args.sources)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('REFUSED: ' + type(exc).__name__)
        return 1


if __name__ == '__main__':
    sys.exit(main())
