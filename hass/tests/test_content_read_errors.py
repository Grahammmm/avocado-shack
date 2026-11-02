"""RF0110-2: a content file that is not UTF-8 or nests too deeply is a ContentError naming the file."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from hass import migration_check
from hass.content_model import REPO_ROOT, ContentError, _read_json, load_content


class ReadJsonErrorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, data: bytes, name: str = "x.json") -> Path:
        path = self.dir / name
        path.write_bytes(data)
        return path

    def test_non_utf8_byte_is_named_content_error_without_file_text(self):
        path = self.write(b'{"name": "secret\xffvalue"}')
        with self.assertRaises(ContentError) as ctx:
            _read_json(path)
        self.assertEqual(ctx.exception.problems, ["x.json: not UTF-8 text"])
        text = str(ctx.exception)
        self.assertNotIn("\\xff", text)
        self.assertNotIn("\xff", text)
        self.assertNotIn("secret", text)

    def test_deep_nesting_is_named_content_error(self):
        limit = sys.getrecursionlimit()
        path = self.write(b"[" * 100000 + b"]" * 100000)
        with self.assertRaises(ContentError) as ctx:
            _read_json(path)
        self.assertEqual(ctx.exception.problems, ["x.json: JSON nested too deeply"])
        self.assertEqual(sys.getrecursionlimit(), limit)

    def test_truncated_json_message_unchanged(self):
        path = self.write(b'{\n  "a": [1,\n')
        with self.assertRaises(ContentError) as ctx:
            _read_json(path)
        self.assertEqual(len(ctx.exception.problems), 1)
        self.assertRegex(ctx.exception.problems[0], r"^x\.json: invalid JSON at line \d+$")

    def test_utf8_bom_still_invalid_json_at_line_1(self):
        path = self.write(b'\xef\xbb\xbf{"a": 1}')
        with self.assertRaises(ContentError) as ctx:
            _read_json(path)
        self.assertEqual(ctx.exception.problems, ["x.json: invalid JSON at line 1"])

    def test_valid_file_loads(self):
        self.assertEqual(_read_json(self.write('{"a": ["é", 1]}'.encode("utf-8"))), {"a": ["é", 1]})

    def test_missing_file_stays_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            _read_json(self.dir / "missing.json")


class CallerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.content = self.root / "hass" / "content"
        shutil.copytree(REPO_ROOT / "hass" / "content", self.content)
        (self.content / "store.json").write_bytes(b'{"name": "\xff"}')

    def test_load_content_names_store_json(self):
        with self.assertRaises(ContentError) as ctx:
            load_content(self.content)
        self.assertEqual(ctx.exception.problems, ["store.json: not UTF-8 text"])

    def test_migration_check_reports_content_invalid(self):
        failures, report = migration_check.run_checks(self.root)
        self.assertEqual(failures, ["content invalid: store.json: not UTF-8 text"])
        self.assertEqual(report, {})
