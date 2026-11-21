"""Synthetic SQLite fixtures for export with a BLOB in a TEXT cell."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hass import transcript


class TranscriptExportBlobTests(unittest.TestCase):
    def test_blob_stops_export_without_discarding_prior_lines_or_changing_store(self):
        # SQLite accepts bytes in a TEXT cell; json.dumps used to raise TypeError.
        valid_text = 'fixture caf\u00e9'
        for valid_prefix in (False, True):
            with self.subTest(valid_prefix=valid_prefix), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / transcript.NAME
                texts = (valid_text, b'fixture blob') if valid_prefix else (b'fixture blob',)
                with contextlib.closing(sqlite3.connect(path)) as db, db:
                    db.executescript(transcript.SCHEMA)
                    db.executemany(
                        "INSERT INTO events(utc,chat,sender,direction,kind,text,attachments,disposition) "
                        "VALUES('2026-01-01T00:00:00+00:00','c','s','in','text',?,'[]','ok')",
                        ((text,) for text in texts),
                    )
                path.chmod(0o600)
                before = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)

                code, out, err = self.run_cli(root, 'export', '--since', '2026-01-01')
                self.assertEqual(code, 1)
                self.assertTrue(err == 'transcript-unavailable\n', 'expected only the fixed error')
                if valid_prefix:
                    self.assertEqual(len(out.splitlines()), 1)
                    self.assertTrue(out.endswith('\n'))
                    row = json.loads(out)
                    self.assertEqual(row['id'], 1)
                    self.assertTrue(row['text'] == valid_text, 'expected the valid fixture text')
                    self.assertEqual(row['attachments'], [])
                else:
                    self.assertFalse(out, 'the bad first row must not be emitted')

                code, out, err = self.run_cli(root, 'stats')
                self.assertEqual(code, 0)
                self.assertFalse(err)
                self.assertEqual(json.loads(out)['count'], len(texts))
                after = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                self.assertTrue(before == after, 'export and stats must leave the database unchanged')

    @staticmethod
    def run_cli(root, command, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = transcript.main([command, '--state', str(root), *args])
        return code, out.getvalue(), err.getvalue()
