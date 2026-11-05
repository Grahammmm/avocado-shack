"""RF0110-2: a content file that is not UTF-8 or nests too deeply is a ContentError naming the file."""

import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from hass import migration_check, sitegen
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


DUP = "duplicate JSON object key"


class DuplicateKeyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def read(self, text: str, name: str = "x.json"):
        path = self.root / name
        path.write_text(text, "utf-8")
        return _read_json(path)

    def test_duplicate_keys_rejected_at_every_depth(self):
        cases = {
            "root": '{"a": 1, "a": 2}',
            "nested": '{"p": {"status": "hidden", "status": "active"}}',
            "in array": '[{"id": 1}, {"x": 0, "x": 0}]',
            "maker keys": '{"makers": {"k": {}, "k": {}}}',
            "first null": '{"a": null, "a": 1}',
            "first false": '{"a": false, "a": true}',
            "first zero": '{"a": 0, "a": 1}',
            "first empty": '{"a": "", "a": "b"}',
            "equal values": '{"a": 1, "a": 1}',
            "escaped spelling": '{"st": 1, "\\u0073t": 2}',
        }
        for label, text in cases.items():
            with self.subTest(label):
                with self.assertRaises(ContentError) as ctx:
                    self.read(text)
                self.assertEqual(ctx.exception.problems, [f"x.json: {DUP}"])

    def test_repeated_keys_in_separate_objects_are_valid(self):
        self.assertEqual(self.read('[{"id": 1}, {"id": 2}]'), [{"id": 1}, {"id": 2}])
        got = self.read('{"name": 1, "Name": 2, "\u00e9": "caf\u00e9", "e\u0301": 3}')
        self.assertEqual(list(got), ["name", "Name", "\u00e9", "e\u0301"])
        self.assertEqual(got["\u00e9"], "caf\u00e9")

    def test_duplicate_error_never_echoes_key_value_or_directory(self):
        sub = self.root / "private-dir-xyz"
        sub.mkdir()
        path = sub / "y.json"
        path.write_text('{"sk-secret-key": "val-secret", "sk-secret-key": "val-secret2"}', "utf-8")
        with self.assertRaises(ContentError) as ctx:
            _read_json(path)
        self.assertEqual(ctx.exception.problems, [f"y.json: {DUP}"])
        text = str(ctx.exception) + repr(ctx.exception.problems)
        for leak in ("sk-secret", "val-secret", "private-dir-xyz"):
            self.assertNotIn(leak, text)


class DuplicateCallerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "repo"
        self.content = self.root / "hass" / "content"
        shutil.copytree(REPO_ROOT / "hass" / "content", self.content)
        self.base = Path(tmp.name)

    def corrupt(self, name: str, hidden_active: bool = False):
        path = self.content / name
        text = path.read_text("utf-8")
        if hidden_active:
            text, n = re.subn(r'"status":\s*"active"', '"status": "hidden", "status": "active"', text, count=1)
            self.assertEqual(n, 1)
        else:
            text = text.replace("{", '{"zz": 1, "zz": 2,', 1)
        path.write_text(text, "utf-8")

    def test_load_content_refuses_duplicates_in_each_source_file(self):
        for name in ("products.json", "makers.json", "community.json", "store.json"):
            with self.subTest(name):
                shutil.copy(REPO_ROOT / "hass" / "content" / name, self.content / name)
                self.corrupt(name)
                with self.assertRaises(ContentError) as ctx:
                    load_content(self.content)
                self.assertEqual(ctx.exception.problems, [f"{name}: {DUP}"])
                shutil.copy(REPO_ROOT / "hass" / "content" / name, self.content / name)
        with self.subTest("hidden->active product status"):
            self.corrupt("products.json", hidden_active=True)
            with self.assertRaises(ContentError) as ctx:
                load_content(self.content)
            self.assertEqual(ctx.exception.problems, [f"products.json: {DUP}"])
        with self.subTest("store schemaVersion"):
            shutil.copy(REPO_ROOT / "hass" / "content" / "products.json", self.content / "products.json")
            path = self.content / "store.json"
            path.write_text('{"schemaVersion": 999, "schemaVersion": 1}', "utf-8")
            with self.assertRaises(ContentError) as ctx:
                load_content(self.content)
            self.assertEqual(ctx.exception.problems, [f"store.json: {DUP}"])

    def test_duplicate_content_cannot_generate_or_migrate(self):
        self.corrupt("products.json", hidden_active=True)
        sentinel = self.root / "storefront-mockup" / "index.html"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_bytes(b"sentinel")
        out = self.base / "out"
        for argv in (["--write", "--repo", str(self.root)], ["--out", str(out), "--repo", str(self.root)]):
            with self.subTest(argv[0]):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    self.assertEqual(sitegen.main(argv), 2)
                self.assertIn("content invalid:", err.getvalue())
                self.assertIn(f"products.json: {DUP}", err.getvalue())
                self.assertEqual(sentinel.read_bytes(), b"sentinel")
                self.assertFalse(out.exists())
        baseline = {"listings": {"ids": [], "count": 0}, "makers": {"keys": []},
                    "sources": {"makerUrls": {}, "routeIdeaSources": {}, "heldSource": ""},
                    "held": {"ids": [], "reason": "", "source": ""},
                    "siteFileSha256": {}, "baseCommit": "fixture"}
        (self.content / "migration-baseline.json").write_text(json.dumps(baseline), "utf-8")
        failures, report = migration_check.run_checks(self.root)
        self.assertEqual(failures, [f"content invalid: products.json: {DUP}"])
        self.assertEqual(report, {})
