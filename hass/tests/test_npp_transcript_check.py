"""Offline contract tests for the private transcript checker's CLI."""

from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import transcript
from hass.npp import job
from scripts.hass import npp_transcript_check as checker


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'scripts/hass/npp_transcript_check.py'
AT = '2000-01-01T00:00:00+00:00'
FIRST, SECOND = 'abc123', 'def456'
CARD, OTHER_CARD = 'a' * 64, 'b' * 64
PRIVATE_PROVIDER = 'fixture-private-provider'
PRIVATE_CHAT = 'fixture-private-chat'
PRIVATE_SENDER = 'fixture-private-sender'
PRIVATE_TEXT = 'fixture-private-text'


class Fixture:
    def __init__(self, root):
        self.root = root
        self.state = root / 'state copy #?.sqlite3'
        self.export = root / 'events.jsonl'
        self.export.touch()
        self.sql_script(job.SCHEMA)

    def sql_script(self, sql):
        with closing(sqlite3.connect(self.state)) as db, db:
            db.executescript(sql)

    def sql(self, sql, values):
        with closing(sqlite3.connect(self.state)) as db, db:
            db.execute(sql, values)

    def add_job(self, jid=FIRST):
        self.sql('INSERT INTO npp_jobs(job_id, chat, sender, photo_sha, open_request_id, state, created_at, closed_at) '
                 'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                 (jid, PRIVATE_CHAT, PRIVATE_SENDER, 'c' * 64, 1, 'closed', AT, AT))

    def turn(self, provider=PRIVATE_PROVIDER, jid=FIRST):
        self.sql('INSERT INTO npp_turns(provider_id, job_id, kind, accepted_at) VALUES (?, ?, ?, ?)',
                 (provider, jid, 'edit', AT))

    def version(self, n, sha=CARD, delivered=True, status='superseded', jid=FIRST):
        self.sql('INSERT INTO npp_versions(job_id, n, segment_id, listing_json, listing_sha, patch_json, '
                 'card_png_sha, outbox_id, state, delivered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                 (jid, n, n, '{}', 'd' * 64, '{}', sha, n, status, AT if delivered else None))

    @staticmethod
    def event(direction, provider=None, attachments=()):
        return transcript.event(PRIVATE_CHAT, PRIVATE_SENDER, direction, 'text', PRIVATE_TEXT,
                                provider, attachments=attachments, utc=AT)

    def write_export(self, *events):
        # Exercise the real exporter rather than hand-coding the JSONL shape.
        store = self.root / 'transcript'
        store.mkdir(mode=0o700)
        source = store / transcript.NAME
        with closing(sqlite3.connect(source)) as db, db:
            db.executescript(transcript.SCHEMA)
            for event in events:
                db.execute('INSERT INTO events (' + ','.join(event) + ') VALUES ('
                           + ','.join('?' for _ in event) + ')', tuple(event.values()))
        source.chmod(0o600)
        with self.export.open('w', encoding='utf-8') as stream, redirect_stdout(stream):
            if transcript.main(['export', '--state', str(store), '--since', '2000-01-01']) != 0:
                raise AssertionError('synthetic transcript export failed')

    def args(self, *, state=None, export=None):
        return ['--state-db', str(state or self.state), '--export', str(export or self.export)]


class TranscriptCheckTests(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Fixture(Path(tmp.name).resolve())

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(CLI), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=10)

    def check_cli(self, fixture, rc, lines, *extra, **overrides):
        result = self.cli(*fixture.args(**overrides), *extra)
        self.assertEqual(result.returncode, rc, result)
        self.assertEqual(result.stdout.splitlines(), lines)
        self.assertEqual(result.stderr, '')

    def test_c1_complete(self):
        # A sent card can later be superseded; a queued card need not be sent.
        f = self.fixture()
        f.add_job()
        f.add_job(SECOND)
        f.turn()
        f.turn('fixture-second-provider', SECOND)
        f.version(1, status='superseded')
        f.version(2, OTHER_CARD, delivered=False, status='queued')
        f.version(3, 'e' * 64, status='approved', jid=SECOND)
        f.write_export(f.event('in', PRIVATE_PROVIDER), f.event('in', 'fixture-second-provider'),
                       f.event('out', attachments=(CARD, 'e' * 64)))
        self.check_cli(f, 0, ['PASS npp_transcript_check 2 jobs'])

    def test_c2_findings(self):
        # Direction mix-ups, silently deduplicating export rows, or skipping
        # sent/superseded cards each fail an independent synthetic fixture.
        cases = {
            'missing-inbound': f'FAIL missing-inbound {FIRST} 2',
            'missing-card': f'FAIL missing-card {FIRST} 7',
            'duplicate-inbound': f'FAIL duplicate-inbound {FIRST} 2',
        }
        for finding, expected in cases.items():
            with self.subTest(finding=finding):
                f = self.fixture()
                f.add_job()
                f.turn('fixture-earlier-provider')
                events = [f.event('in', 'fixture-earlier-provider')]
                if finding == 'missing-inbound':
                    f.turn()
                    events.append(f.event('out', PRIVATE_PROVIDER))
                elif finding == 'missing-card':
                    f.version(7)
                    events.append(f.event('in', attachments=(CARD,)))
                else:
                    f.turn()
                    events.append(f.event('in', PRIVATE_PROVIDER))
                f.write_export(*events)
                if finding == 'duplicate-inbound':
                    # The real store deduplicates, so simulate a repeated export line.
                    repeated = f.export.read_bytes().splitlines(keepends=True)[-1]
                    with f.export.open('ab') as stream:
                        stream.write(repeated)
                self.check_cli(f, 1, [expected, 'FAIL npp_transcript_check'])

        # More than one finding must be emitted, sorted independently of scan order.
        f = self.fixture()
        f.add_job(SECOND)
        f.add_job()
        f.turn('fixture-other-provider', SECOND)
        f.turn()
        f.version(7)
        self.check_cli(f, 1, [f'FAIL missing-card {FIRST} 7', f'FAIL missing-inbound {FIRST} 1',
                              f'FAIL missing-inbound {SECOND} 1', 'FAIL npp_transcript_check'])

    def test_c3_read_only(self):
        # WAL-mode read-only opens without an immutable guard can create sidecars.
        f = self.fixture()
        f.add_job()
        f.sql_script('PRAGMA journal_mode=WAL;')
        f.state.chmod(0o400)
        f.export.chmod(0o400)

        def snapshot():
            return (f.root.stat().st_mtime_ns,
                    {p.name: (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
                     for p in f.root.iterdir()})

        before = snapshot()
        self.check_cli(f, 0, ['PASS npp_transcript_check 1 jobs'])
        self.assertEqual(snapshot(), before)
        with patch.object(checker.sqlite3, 'connect', wraps=sqlite3.connect) as connect:
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(checker.main(f.args()), 0)
            self.assertEqual(output.getvalue().splitlines()[-1], 'PASS npp_transcript_check 1 jobs')
        self.assertTrue(connect.call_args.kwargs['uri'])
        self.assertIn('mode=ro', connect.call_args.args[0].split('?', 1)[1].split('&'))
        self.assertEqual(snapshot(), before)

        # An immutable read must refuse rather than silently miss WAL-only data.
        f.state.chmod(0o600)
        with closing(sqlite3.connect(f.state)) as writer:
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute('DELETE FROM npp_jobs')
            writer.commit()
            before = snapshot()
            self.check_cli(f, 1, ['FAIL bad-input state-db-needs-checkpoint'])
            self.assertEqual(snapshot(), before)

        tree = f.root / 'worktree'
        tree.mkdir()
        (tree / '.git').write_text('gitdir: fixture-linked-gitdir\n', encoding='utf-8')
        for flag, source in [('state', f.state), ('export', f.export)]:
            with self.subTest(path=flag):
                path_in_tree = tree / source.name
                path_in_tree.write_bytes(source.read_bytes())
                outside_link = f.root / (flag + '-alias')
                outside_link.symlink_to(path_in_tree)
                for candidate in (path_in_tree, outside_link):
                    self.check_cli(f, 1, ['FAIL bad-input git-worktree'], **{flag: candidate})

    def test_c4_bad_input(self):
        # An empty or malformed schema must not yield a vacuous PASS.
        for ddl in ('DROP TABLE npp_turns', 'ALTER TABLE npp_versions DROP COLUMN card_png_sha',
                    'ALTER TABLE npp_versions DROP COLUMN delivered_at'):
            with self.subTest(ddl=ddl):
                f = self.fixture()
                f.sql_script(ddl)
                self.check_cli(f, 1, ['FAIL bad-input state-db'])
        # One good line must not hide any bad line later in the same export.
        f = self.fixture()
        f.add_job()
        f.write_export(f.event('in', PRIVATE_PROVIDER))
        good = f.export.read_bytes()
        for bad in (b'{bad-json}', b'\xff', b'[]', b'{}', b'',
                    json.dumps({'direction': 'out', 'provider_id': None, 'attachments': '[]'}).encode(),
                    json.dumps({'direction': 'in', 'provider_id': [], 'attachments': []}).encode(),
                    json.dumps({'direction': 'unknown', 'provider_id': None, 'attachments': []}).encode()):
            with self.subTest(bad=bad):
                f.export.write_bytes(good + bad + b'\n')
                self.check_cli(f, 1, ['FAIL bad-input export'])

    def test_c5_one_job(self):
        # Filtering must exclude the other job's inbound and outbound findings.
        f = self.fixture()
        f.add_job()
        f.add_job(SECOND)
        f.turn()
        f.turn('fixture-other-provider', SECOND)
        f.version(1, jid=SECOND)
        f.write_export(f.event('in', PRIVATE_PROVIDER))
        self.check_cli(f, 0, ['PASS npp_transcript_check 1 jobs'], '--job', FIRST)
        self.check_cli(f, 1, [f'FAIL missing-card {SECOND} 1', f'FAIL missing-inbound {SECOND} 1',
                              'FAIL npp_transcript_check'], '--job', SECOND)
        self.check_cli(f, 1, ['FAIL no-job'], '--job', '000000')

    def test_c6_privacy_usage(self):
        # Parser and I/O exceptions must not echo private values, either stream.
        f = self.fixture()
        f.add_job()
        f.turn()
        f.write_export(f.event('out', PRIVATE_PROVIDER, attachments=(CARD,)))
        arg_canary = 'fixture-private-argument'

        def private(result, rc):
            self.assertEqual(result.returncode, rc, result)
            for canary in (PRIVATE_PROVIDER, PRIVATE_CHAT, PRIVATE_SENDER, PRIVATE_TEXT, CARD, arg_canary):
                self.assertNotIn(canary, result.stdout)
                self.assertNotIn(canary, result.stderr)

        result = self.cli(*f.args())
        private(result, 1)
        self.assertEqual(result.stdout.splitlines(), [f'FAIL missing-inbound {FIRST} 1', 'FAIL npp_transcript_check'])
        with f.export.open('a', encoding='utf-8') as stream:
            stream.write(PRIVATE_TEXT + '\n')
        result = self.cli(*f.args())
        private(result, 1)
        self.assertEqual(result.stdout.splitlines(), ['FAIL bad-input export'])
        result = self.cli(*f.args(state=f.root / arg_canary))
        private(result, 1)
        self.assertEqual(result.stdout.splitlines(), ['FAIL bad-input state-db'])
        for args in ([], [*f.args(), arg_canary], [*f.args(), '--job', '--' + arg_canary]):
            result = self.cli(*args)
            private(result, 2)
            self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
