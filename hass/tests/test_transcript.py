"""Synthetic transcripts only; fixture writer/previewer, no network or live state."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest import mock

from hass import conversation, statebackup, transcript
from hass.tests.test_conversation import CHAT, OWNER, STRANGER
from hass.tests.test_editor import git
from hass.tests.test_undo import H06TestCase


class TranscriptTests(H06TestCase):
    def rows(self, state=None):
        with contextlib.closing(transcript.read(state or self.repo.state)) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) | {'attachments': json.loads(r['attachments'])} for r in db.execute('SELECT * FROM events ORDER BY id')]

    def inbound(self, pid, text, **kw):
        return self.conv.handle(conversation.Inbound(pid, kw.pop('chat', CHAT), kw.pop('sender', OWNER),
                                text, received_at=self.now.isoformat(), **kw))

    def test_full_conversation_and_duplicate(self):
        raw = '  when?\n'
        self.interp.mapping[raw] = {'question': 'Which day should change?'}
        self.assertEqual(self.inbound('text', raw), 'question')
        self.assertEqual(self.inbound('photo', '\ufffc', attachments=1), 'attachment-unsupported')
        self.assertEqual(self.inbound('edit', '  edited words\n', kind='edited'), 'not-read')
        before = self.rows()
        self.assertEqual(self.inbound('text', raw), 'duplicate')
        self.assertEqual(self.rows(), before)
        self.sent()
        draft, _ = self.propose('hours')
        yes = 'yes ' + draft['code']
        self.assertEqual(self.inbound('yes', yes), 'approved')
        rows = self.rows()
        inbound = [r for r in rows if r['direction'] == 'in']
        self.assertEqual([(r['provider_id'], r['text'], r['kind'], r['disposition']) for r in inbound], [
            ('text', raw, 'text', 'question'), ('photo', '\ufffc', 'photo', 'attachment-unsupported'),
            ('edit', '  edited words\n', 'edited', 'not-read'), ('m1', 'hours', 'text', 'proposed'),
            ('yes', yes, 'text', 'approved')])
        self.assertEqual(inbound[-1]['draft_code'], draft['code'])
        outgoing = [r for r in rows if r['direction'] == 'out']
        expected = self.conv.db.execute('SELECT * FROM outbox ORDER BY id').fetchall()
        self.assertEqual(len(rows), len(expected) + 5)
        self.assertEqual([r['text'] for r in outgoing], [r['text'] for r in expected])
        for actual, source in zip(outgoing, expected):
            self.assertEqual(actual['attachments'], [hashlib.sha256(Path(p).read_bytes()).hexdigest()
                                                     for p in json.loads(source['attachments'])])
        self.assertTrue(any(r['kind'] == 'photo' and r['attachments'] for r in outgoing))
        self.assertTrue(all(r['chat'] == CHAT and r['latency_ms'] >= 0 for r in rows))
        self.assertEqual((self.repo.state / transcript.NAME).stat().st_mode & 0o777, 0o600)

    def test_ignored_g_and_exception_paths(self):
        self.inbound('stranger', 'untouched words', sender=STRANGER)
        self.inbound('g', 'private words', chat='g-fixture')
        self.inbound('tap', 'a reaction', kind='reaction')
        with mock.patch.object(self.conv, '_handle_message', side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):
                self.inbound('error', 'still recorded')
        inbound = [r for r in self.rows() if r['direction'] == 'in']
        self.assertEqual([(r['provider_id'], r['disposition']) for r in inbound],
                         [('stranger', 'ignored'), ('g', 'ignored'), ('tap', 'not-read'), ('error', 'error')])
        self.assertEqual(inbound[0]['sender'], conversation.sender_key(STRANGER))
        self.assertEqual(inbound[1]['chat'], 'g-fixture')

    def test_failure_does_not_change_reply_bytes(self):
        self.inbound('baseline', 'help')
        baseline = self.sent()
        with mock.patch.object(transcript, 'append', side_effect=OSError('fixture private text')):
            with self.assertLogs('hass.transcript', level='ERROR') as logs:
                self.inbound('failure', 'help')
        self.assertEqual(self.sent(), baseline)
        self.assertEqual(logs.output, ['ERROR:hass.transcript:ALERT transcript-write-failed'] * 2)

    def test_fetch_hashes_and_backend_are_observed_without_extra_calls(self):
        fake = mock.Mock()
        fake.fetch.return_value = [b'fixture photo bytes']
        self.conv.photos = fake
        self.interp.model = 'fixture-model'
        self.interp.last_backend = 'fixture-backend'
        with transcript.Capture(self.conv, conversation.Inbound('meta', CHAT, OWNER, 'text')) as capture:
            self.assertEqual(self.conv.photos.fetch('meta', 1), [b'fixture photo bytes'])
            self.conv.db.execute(conversation.AUDIT)
            self.conv.db.execute('INSERT INTO interpreter_audit VALUES (?, ?, ?, 0, NULL, NULL, 0)',
                                 ('meta', self.now.isoformat(), 'fixture-backend'))
            capture.result = 'question'
        fake.fetch.assert_called_once_with('meta', 1)
        self.assertIs(self.conv.photos, fake)
        [row] = self.rows()
        self.assertEqual(row['attachments'], [hashlib.sha256(b'fixture photo bytes').hexdigest()])
        self.assertEqual((row['backend'], row['model']), ('fixture-backend', 'fixture-model'))

    def test_backup_restore_and_drill(self):
        self.inbound('kept', 'help')
        before = self.rows()
        top = self.repo.state.parent
        backups = top / 'transcript-backups'
        backups.mkdir(mode=0o700)
        drill = top / 'transcript-drill'
        git(self.repo.main, 'worktree', 'add', '-q', '-b', 'transcript-drill', str(drill))
        made = statebackup.create(self.repo.state, backups)
        self.assertEqual(made['result'], 'ok', made)
        restored = top / 'transcript-restored'
        result = statebackup.drill(made['backup'], restored, drill, now=self.now)
        self.assertEqual(result['result'], 'ok', result)
        self.assertEqual(self.rows(restored), before)
        self.assertEqual((restored / transcript.NAME).stat().st_mode & 0o777, 0o600)

    def test_export_stats_read_only_and_private_refusals(self):
        self.inbound('cli', 'help')
        path = self.repo.state / transcript.NAME
        before = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        def cli(command, *args):
            return subprocess.run([sys.executable, '-B', str(Path(transcript.__file__)), command,
                                   '--state', str(self.repo.state), *args], capture_output=True, text=True)
        exported = cli('export', '--since', '2000-01-01', '--chat', CHAT)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        rows = [json.loads(s) for s in exported.stdout.splitlines()]
        self.assertEqual(rows, self.rows())
        stats = cli('stats')
        self.assertEqual(stats.returncode, 0, stats.stderr)
        self.assertEqual(sum(json.loads(s)['count'] for s in stats.stdout.splitlines()), len(rows))
        self.assertEqual(cli('export', '--since', '2000-01-01', '--chat', 'absent').stdout, '')
        self.assertEqual(cli('export', '--since', 'invalid').returncode, 2)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode), before)
        os.chmod(path, 0o644)
        self.assertEqual(cli('stats').returncode, 1)
        os.chmod(path, 0o600)
        moved = path.with_suffix('.saved')
        path.rename(moved)
        path.symlink_to(moved)
        self.assertEqual(cli('stats').returncode, 1)
        with self.assertLogs('hass.transcript', level='ERROR'):
            transcript.safe(self.repo.state, **transcript.event(CHAT, OWNER, 'in', 'text', 'not written'))
        self.assertEqual(moved.read_bytes(), before[0])


if __name__ == '__main__':
    unittest.main()
