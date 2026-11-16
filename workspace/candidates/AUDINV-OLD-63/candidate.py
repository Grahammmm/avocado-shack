#!/usr/bin/env python3
"""AUDINV-OLD-63: offline-only paused restore proof; never a live restore tool."""
import argparse
import contextlib
import hashlib
import json
import io
import shutil
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SCRATCH = REPO.parent / 'old63-fixture-scratch'
HEX = re.compile(r'[0-9a-f]{64}')
COMMIT = re.compile(r'[0-9a-f]{40}')
BOUNDARY = ['CANDIDATE_ONLY', 'REVIEW_REQUIRED', 'NOT_INSTALLED']
COVERAGE = {'content': 'FIXTURE_PROVEN', 'original_media': 'FIXTURE_PROVEN',
            'web_media': 'FIXTURE_PROVEN', 'assistant_state': 'FIXTURE_PROVEN',
            'fixture_served_release': 'FIXTURE_PROVEN',
            'routine_live_backups': 'ROUTINE_BACKUPS_UNVERIFIED',
            'live_served_release': 'UNVERIFIED', 'live_paused_restore': 'HOLD_ATTENDED_OWNER'}
DENIED = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def load(path):
    return json.loads(path.read_text('utf-8'), object_pairs_hook=pairs)


def keys(doc, expected):
    if not isinstance(doc, dict) or set(doc) != set(expected):
        raise ValueError('unexpected fields')


def version(doc):
    if type(doc.get('schema_version')) is not int or doc['schema_version'] != 1:
        raise ValueError('unsupported schema')


def package_path(raw):
    p = Path(raw)
    if p.is_absolute() or not p.parts or any(x in ('.', '..') for x in p.parts):
        raise ValueError('unsafe package path')
    p = ROOT / p
    if any(x.is_symlink() for x in (p, *p.parents)) or not p.is_relative_to(ROOT):
        raise ValueError('symlink or path escape')
    return p


def stamp(raw):
    if not isinstance(raw, str):
        raise ValueError('missing timestamp')
    value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError('UTC timestamp required')
    return value


def routine(doc):
    """Compare explicit receipts to three dated 03:30 Pacific slots; no host queries."""
    keys(doc, ['schema_version', 'timer_enabled', 'start_date', 'days', 'as_of', 'receipts'])
    version(doc)
    if type(doc['timer_enabled']) is not bool or type(doc['days']) is not int or not 1 <= doc['days'] <= 31:
        raise ValueError('invalid schedule window')
    start = datetime.strptime(doc['start_date'], '%Y-%m-%d')
    as_of, used, covered = stamp(doc['as_of']), set(), set()
    slots = [(start + timedelta(days=i)).replace(hour=3, minute=30,
             tzinfo=ZoneInfo('America/Los_Angeles')).astimezone(timezone.utc) for i in range(doc['days'])]
    if not isinstance(doc['receipts'], list):
        raise ValueError('invalid receipts')
    for row in doc['receipts']:
        keys(row, ['backup_id', 'created_at', 'contentCommit', 'manifest_sha256', 'status'])
        if not isinstance(row['backup_id'], str) or not re.fullmatch(r'hass-state-[0-9]{8}T[0-9]{6}Z', row['backup_id']):
            raise ValueError('invalid backup identity')
        when = stamp(row['created_at'])
        if row['backup_id'] != when.strftime('hass-state-%Y%m%dT%H%M%SZ') or row['backup_id'] in used:
            raise ValueError('duplicate or mismatched identity')
        if not isinstance(row['contentCommit'], str) or not COMMIT.fullmatch(row['contentCommit']) or not isinstance(row['manifest_sha256'], str) or not HEX.fullmatch(row['manifest_sha256']):
            raise ValueError('invalid digest')
        if row['status'] not in ('verified', 'cancelled', 'expired', 'failed') or when > as_of:
            raise ValueError('invalid receipt status/time')
        used.add(row['backup_id'])
        for slot in slots:
            if row['status'] == 'verified' and slot <= when <= slot + timedelta(minutes=15) and when <= as_of:
                covered.add(slot)
    return {'expected': len(slots), 'covered': len(covered),
            'status': 'SUPPLIED_RECEIPTS_MATCH_SCHEDULE' if len(covered) == len(slots)
            else 'ROUTINE_BACKUPS_UNVERIFIED'}


def check(result_name, source_name):
    # Validate both paths before opening either file.
    result, source = package_path(result_name), package_path(source_name)
    sources, bases = load(source), load(package_path('BASES.json'))
    keys(sources, ['schema_version', 'captured_at', 'sources', 'schedule', 'missing_coverage'])
    version(sources)
    stamp(sources['captured_at'])
    version(bases)
    keys(bases, ['schema_version', 'inspected_main', 'candidate_only', 'installed', 'no_apply', 'source_hashes', 'package_hashes'])
    if not COMMIT.fullmatch(bases['inspected_main']) or (bases['candidate_only'], bases['installed'], bases['no_apply']) != (True, False, True):
        raise ValueError('invalid base/boundary')
    for rel, digest in bases['source_hashes'].items():
        p = Path(rel)
        if p.is_absolute() or '..' in p.parts or any(x.is_symlink() for x in (REPO / p, *(REPO / p).parents)):
            raise ValueError('unsafe source binding')
        if not HEX.fullmatch(digest) or sha(REPO / p) != digest:
            raise ValueError('source digest mismatch')
    for rel, digest in bases['package_hashes'].items():
        if sha(package_path(rel)) != digest:
            raise ValueError('package digest mismatch')
    if set(bases['package_hashes']) != {'candidate.py', 'fixtures.json', 'SOURCES.json', 'README.md'}:
        raise ValueError('incomplete package bindings')
    if not isinstance(sources['sources'], list) or len(sources['sources']) != 4:
        raise ValueError('four cited sources required')
    for row in sources['sources']:
        keys(row, ['path', 'sha256', 'locator', 'kind'])
        if row['sha256'] != bases['source_hashes'].get(row['path']) or row['kind'] != 'repository_source':
            raise ValueError('unbound source')
    if sources['missing_coverage'] != ['routine_live_backups', 'live_served_release', 'live_paused_restore']:
        raise ValueError('missing coverage must remain explicit')
    text = result.read_text('utf-8')
    matches = re.findall(r'```json\n(.*?)\n```', text, re.S)
    if len(matches) != 1:
        raise ValueError('one report schema required')
    report = json.loads(matches[0], object_pairs_hook=pairs)
    keys(report, ['schema_version', 'status', 'inspected_main', 'sources_sha256', 'bases_sha256', 'tests', 'coverage', 'routine'])
    version(report)
    if report != {'schema_version': 1, 'status': BOUNDARY, 'inspected_main': bases['inspected_main'],
                  'sources_sha256': sha(source), 'bases_sha256': sha(package_path('BASES.json')),
                  'tests': {'run': 6, 'failures': 0, 'errors': 0}, 'coverage': COVERAGE,
                  'routine': routine(sources['schedule'])}:
        raise ValueError('false success or mismatched report binding/counts')
    if report['routine']['status'] != 'ROUTINE_BACKUPS_UNVERIFIED':
        raise ValueError('no live routine-backup acceptance in this candidate')
    print('artifact-check: PASS (6 local tests; 8 coverage rows; routine/live remain UNVERIFIED/HOLD)')


def fence(event, args):
    """Write fence + network/subprocess boundary for the actual helper exercise."""
    paths = []
    if event.startswith('socket.') and event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo'):
        DENIED.append(event)
        raise PermissionError('network prohibited')
    if event == 'subprocess.Popen':
        executable, argv, cwd, _env = args
        where = Path(argv[argv.index('-C') + 1] if Path(executable).name == 'git' and '-C' in argv else cwd or os.getcwd()).resolve()
        allowed = where.is_relative_to(SCRATCH) and (Path(executable).name == 'git' or
                  (Path(executable).resolve() == Path(sys.executable).resolve() and
                   argv[1:] == ['-B', 'hass/sitegen.py', '--check']))
        if not allowed:
            DENIED.append(event)
            raise PermissionError('only fixture git and unchanged sitegen --check')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path, _mode, flags = args
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            paths = [(path, None)]
        else:
            absolute = Path(os.fsdecode(path)).absolute()
            if absolute.is_relative_to(Path.home()) and not (absolute.is_relative_to(REPO) or absolute.is_relative_to(SCRATCH) or absolute.is_relative_to(Path(sys.base_prefix))):
                DENIED.append(event)
                raise PermissionError('private host reads prohibited')
    elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod'):
        if not isinstance(args[0], int):
            paths = [(args[0], args[2] if event in ('os.mkdir', 'os.chmod') else args[1])]
    elif event in ('os.rename', 'os.link', 'os.symlink'):
        paths = [(args[1], args[2] if event == 'os.symlink' else args[3])]
        if event == 'os.rename':
            paths.append((args[0], args[2]))
    for raw, fd in paths:
        p = Path(os.fsdecode(raw))
        if not p.is_absolute():
            parent = Path(os.readlink(f'/proc/self/fd/{fd}')) if fd not in (None, -1) else Path.cwd()
            p = parent / p
        # Parent resolution catches ancestor links; unlinking a fixture link itself is safe.
        p = p.resolve() if event == 'open' else p.parent.resolve() / p.name
        if not p.is_relative_to(SCRATCH):
            DENIED.append(event)
            raise PermissionError('out-of-fixture write prohibited')


def self_test():
    if SCRATCH.is_symlink() or SCRATCH.exists():
        raise ValueError('fixture scratch must be a fresh non-symlink directory')
    if any(p.is_symlink() for p in SCRATCH.parents):
        raise ValueError('fixture scratch ancestors must not be symlinks')
    SCRATCH.mkdir(mode=0o700)
    tempfile.tempdir = str(SCRATCH.resolve())
    os.environ['TMPDIR'] = tempfile.tempdir
    sys.path.insert(0, str(REPO))
    # Resolve the write root before imports; leave all production identity guards enabled.
    sys.addaudithook(fence)
    from hass import editor, media, statebackup
    from hass.tests.test_statebackup import BackupTestCase, STAMP, tree
    from hass.tests.test_editor import git
    from hass.tests.test_media import JPEG, AT
    fixtures = load(package_path('fixtures.json'))
    keys(fixtures, ['schema_version', 'schedule_cases', 'restore_expected'])
    version(fixtures)

    class RestoreTests(BackupTestCase):
        def make(self):
            self.drill()  # real conversation/history operations, recording-only adapter
            photo = self.repo.wt / 'storefront-mockup/hike/old63-fixture.jpg'
            photo.write_bytes(JPEG)
            git(self.repo.wt, 'add', str(photo))
            git(self.repo.wt, 'commit', '-q', '-s', '-m', 'synthetic web photo')
            self.mroot = self.tmp / 'original-media'
            self.mroot.mkdir(mode=0o700)
            media.store_original(self.mroot, JPEG, received_at=AT, source='synthetic')
            self.made = statebackup.create(str(self.repo.state), str(self.bk), now=STAMP, media=str(self.mroot))
            self.assertEqual(self.made['result'], 'ok')
            self.backup_dir = Path(self.made['backup'])
            self.release = {'backup_id': self.backup_dir.name, 'revision': self.made['contentCommit'],
                            'manifest_sha256': sha(self.backup_dir / statebackup.MANIFEST)}
            self.targets = [self.tmp / x for x in ('restored', 'restored-media', 'restored-content')]
            return self.backup_dir

        def restore(self, drill=False):
            fn = statebackup.drill if drill else statebackup.restore
            return fn(str(self.backup_dir), str(self.targets[0]), str(self.drill_wt),
                      media_into=str(self.targets[1]), content_into=str(self.targets[2]), now=STAMP,
                      **({} if drill else {'paused': True}))

        def match(self, out):
            self.assertEqual(out['result'], 'ok', out)
            self.assertEqual(out['contentCheck'], 'ok')
            self.assertTrue(out['paused'])
            if self.release != {'backup_id': self.backup_dir.name, 'revision': out['contentCommit'],
                                'manifest_sha256': sha(self.backup_dir / statebackup.MANIFEST)}:
                raise ValueError('fixture release identity mismatch')
            self.assertEqual(git(self.targets[2], 'rev-parse', 'HEAD'), self.release['revision'])
            for rel in (*editor.GENERATED_PATHS, 'hass/content/store.json', 'storefront-mockup/hike/old63-fixture.jpg'):
                self.assertEqual(sha(self.targets[2] / rel), sha(self.repo.wt / rel))
            self.assertEqual(tree(self.targets[1]), tree(self.mroot))
            self.assertEqual(editor.history(state=str(self.targets[0])), editor.history(state=str(self.repo.state)))
            with contextlib.closing(sqlite3.connect(self.targets[0] / statebackup.DB)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
                self.assertEqual(db.execute("SELECT value FROM control WHERE name='paused'").fetchall(), [('1',)])
            # Pause is the only semantic DB addition: every original table/row survives.
            with contextlib.closing(sqlite3.connect(self.repo.state / statebackup.DB)) as a, contextlib.closing(sqlite3.connect(self.targets[0] / statebackup.DB)) as b:
                for (table,) in a.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='control'"):
                    self.assertEqual(a.execute(f'SELECT * FROM "{table}"').fetchall(), b.execute(f'SELECT * FROM "{table}"').fetchall())

        def test_paused_restore_matches_content_media_state_and_fixture_served_release(self):
            self.make()
            before = (tree(self.repo.state), tree(self.mroot), git(self.repo.wt, 'rev-parse', 'HEAD'))
            self.assertEqual(statebackup.verify(str(self.backup_dir))['result'], 'ok')
            self.match(self.restore(drill=True))
            self.assertEqual(before, (tree(self.repo.state), tree(self.mroot), git(self.repo.wt, 'rev-parse', 'HEAD')))
            self.assertEqual(fixtures['restore_expected'], {'paused': True, 'history': 3, 'originals': 1})
            self.assertEqual(len(editor.history(state=str(self.targets[0]))['history']), 3)
            self.assertEqual(self.made['media'], 1)
            self.assertEqual(statebackup.create(str(self.repo.state), str(self.bk), now=STAMP, media=str(self.mroot))['result'], 'exists')

        def test_corrupt_missing_bundle_or_wrong_release_identity_fails(self):
            self.make()
            bundle = self.backup_dir / statebackup.BUNDLE
            data = bundle.read_bytes()
            for corrupt in (None, b'corrupt bundle'):
                with self.subTest(corrupt=corrupt):
                    bundle.unlink() if corrupt is None else bundle.write_bytes(corrupt)
                    self.assertEqual(self.restore(drill=True)['result'], 'corrupt')
                    self.assertFalse(any(p.exists() for p in self.targets))
                    bundle.write_bytes(data)
            out = self.restore(drill=True)
            for field in ('backup_id', 'revision', 'manifest_sha256'):
                old = self.release[field]
                self.release[field] = '0' * 40
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    self.match(out)
                self.release[field] = old
            # Rehashed but wrong commit is refused by the unchanged production verifier.
            manifest = self.backup_dir / statebackup.MANIFEST
            doc = load(manifest)
            doc['contentCommit'] = '0' * 40
            manifest.write_text(json.dumps(doc))
            self.assertEqual(statebackup.verify(str(self.backup_dir))['result'], 'corrupt')

        def test_existing_destination_and_symlink_are_untouched(self):
            self.make()
            before = tree(self.backup_dir)
            for target in self.targets:
                for link in (False, True):
                    with self.subTest(target=target.name, symlink=link):
                        target.symlink_to(self.tmp / 'absent') if link else target.mkdir(mode=0o700)
                        self.assertEqual(self.restore()['result'], 'refused')
                        self.assertTrue(target.is_symlink() if link else target.is_dir())
                        self.assertEqual(tree(self.backup_dir), before)
                        self.assertFalse(any(p.exists() for p in self.targets if p != target))
                        target.unlink() if link else target.rmdir()

        def test_restore_interruption_retains_atomicity_and_pause(self):
            self.make()
            before = tree(self.backup_dir)
            real = statebackup._rename_noreplace
            for target in self.targets:
                def interrupt(src, dst):
                    if dst == self.targets[0]:
                        with contextlib.closing(sqlite3.connect(src / statebackup.DB)) as db:
                            self.assertEqual(db.execute("SELECT value FROM control WHERE name='paused'").fetchall(), [('1',)])
                    if dst == target:
                        raise InterruptedError('synthetic cancellation')
                    return real(src, dst)
                with self.subTest(target=target.name), mock.patch.object(statebackup, '_rename_noreplace', side_effect=interrupt):
                    with self.assertRaises(InterruptedError):
                        self.restore()
                self.assertFalse(any(p.exists() for p in self.targets))
                self.assertFalse(any('.restore-' in p.name for p in self.tmp.iterdir()))
                self.assertEqual(tree(self.backup_dir), before)
            self.match(self.restore(drill=True))

        def test_timer_enabled_without_dated_backup_receipt_stays_unverified(self):
            for case in fixtures['schedule_cases']:
                with self.subTest(case=case['name']):
                    if case['expected'] == 'INVALID':
                        with self.assertRaises(ValueError):
                            routine(case['input'])
                    else:
                        self.assertEqual(routine(case['input']), case['expected'])

        def test_schema_path_escape_symlink_and_side_effect_boundary(self):
            before = list(DENIED)
            for raw in ('../RESULT.md', '/etc/passwd', '../../.local/share/hass/config.json'):
                with self.assertRaises(ValueError), mock.patch.object(Path, 'read_text', side_effect=AssertionError('opened unsafe path')):
                    package_path(raw)
            with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
                old_root = globals()['ROOT']
                globals()['ROOT'] = Path(tmp)
                try:
                    (Path(tmp) / 'link').symlink_to(REPO)
                    with self.assertRaises(ValueError):
                        package_path('link/README.md')
                    for name in ('candidate.py', 'fixtures.json', 'SOURCES.json', 'README.md', 'BASES.json'):
                        shutil.copyfile(old_root / name, Path(tmp) / name)
                    bases = load(Path(tmp) / 'BASES.json')
                    sources = load(Path(tmp) / 'SOURCES.json')
                    # Synthetic checker input, not a claimed execution receipt.
                    report = {'schema_version': 1, 'status': BOUNDARY,
                              'inspected_main': bases['inspected_main'],
                              'sources_sha256': sha(Path(tmp) / 'SOURCES.json'),
                              'bases_sha256': sha(Path(tmp) / 'BASES.json'),
                              'tests': {'run': 6, 'failures': 0, 'errors': 0},
                              'coverage': dict(COVERAGE), 'routine': routine(sources['schedule'])}
                    artifact = Path(tmp) / 'RESULT.md'
                    def emit():
                        artifact.write_text('```json\n' + json.dumps(report) + '\n```\n')
                    emit()
                    with contextlib.redirect_stdout(io.StringIO()):
                        check('RESULT.md', 'SOURCES.json')
                    for field, value in (('sources_sha256', '0' * 64), ('schema_version', 2),
                                         ('tests', {'run': 0, 'failures': 0, 'errors': 0}),
                                         ('coverage', dict(COVERAGE, live_paused_restore='PROVEN'))):
                        old = report[field]
                        report[field] = value
                        emit()
                        with self.subTest(field=field), self.assertRaises(ValueError):
                            check('RESULT.md', 'SOURCES.json')
                        report[field] = old
                finally:
                    globals()['ROOT'] = old_root
            for data in ('{"schema_version":1,"schema_version":1}', '{broken'):
                with self.assertRaises(ValueError):
                    json.loads(data, object_pairs_hook=pairs)
            for bad in (0, 2, True, '1'):
                with self.assertRaises(ValueError):
                    version({'schema_version': bad})
            for args in ([], ['--apply'], ['--self-test', '--sources', 'SOURCES.json']):
                with mock.patch.object(sys, 'argv', ['candidate.py', *args]), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as exit_result:
                        main()
                    self.assertNotEqual(exit_result.exception.code, 0)
            self.assertEqual(DENIED, before, 'no attempted disallowed I/O')

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RestoreTests))
    SCRATCH.rmdir()
    print(f'fixture-boundary: {len(DENIED)} disallowed I/O attempts; no live actions')
    return 0 if result.wasSuccessful() and not DENIED else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--self-test', action='store_true')
    group.add_argument('--check')
    parser.add_argument('--sources')
    args = parser.parse_args()
    if args.self_test and args.sources or args.check and not args.sources:
        parser.error('--sources is required only with --check')
    try:
        return self_test() if args.self_test else (check(args.check, args.sources) or 0)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f'candidate: REFUSED ({exc})', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
