"""Synthetic private stores only: export refuses non-array attachment JSON."""
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hass import transcript

DIGEST = 'a' * 64


class AttachmentShapeTests(unittest.TestCase):
    def store(self, *attachments):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'state'
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        path = root / transcript.NAME
        with contextlib.closing(sqlite3.connect(path)) as db, db:
            db.executescript(transcript.SCHEMA)
            for i, att in enumerate(attachments):
                db.execute("INSERT INTO events(utc,chat,sender,direction,kind,text,attachments,provider_id,disposition)"
                           " VALUES(?,?,?,?,?,?,?,?,?)",
                           ('2026-01-01T00:00:00+00:00', 'c', 's', 'in', 'text', f'caf\u00e9 {i}', att, f'p{i}', 'ok'))
        path.chmod(0o600)
        return root, path

    def run_cli(self, root, command='export'):
        out, err = io.StringIO(), io.StringIO()
        args = [command, '--state', str(root)] + (['--since', '2026-01-01'] if command == 'export' else [])
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = transcript.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_nonarray_attachment_json_is_unavailable(self):
        for bad in ('{}', 'null', '17', '1.5', 'true', 'false', '"not-an-array"'):
            with self.subTest(bad=bad):
                root, _ = self.store(bad)
                self.assertEqual(self.run_cli(root), (1, '', 'transcript-unavailable\n'))

    def test_valid_attachment_arrays_still_export(self):
        root, _ = self.store('[]', json.dumps([DIGEST]))
        code, out, err = self.run_cli(root)
        self.assertEqual((code, err), (0, ''))
        self.assertEqual([r['attachments'] for r in map(json.loads, out.splitlines())], [[], [DIGEST]])

    def test_later_corrupt_row_stops_before_emitting_that_row(self):
        root, _ = self.store('[]', '{"x": 1}')
        code, out, err = self.run_cli(root)
        self.assertEqual((code, err), (1, 'transcript-unavailable\n'))
        lines = out.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])['provider_id'], 'p0')
        self.assertNotIn('"x"', out)

    def test_refusal_is_read_only_and_stats_stays_count_only(self):
        root, path = self.store('null')
        before = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        self.assertEqual(self.run_cli(root)[0], 1)
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode))
        code, out, err = self.run_cli(root, 'stats')
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out)['count'], 1)


if __name__ == '__main__':
    unittest.main()
