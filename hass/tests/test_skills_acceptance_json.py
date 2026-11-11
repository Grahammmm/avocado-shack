"""RF0645-12: an expected acceptance file's schema_version must be the exact integer, like a row's (refused before any row runs)."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass.skills import acceptance_run as A

HOURS = ["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Saturday 9am–5pm · Closed Sunday"]
REFUSAL = "expected file does not follow expected schema 1"


def row(rid):
    return {"id": rid, "schema_version": 1, "tag": "primary", "skill": "shop.hours", "skill_version": 1,
            "texts": ["we're open till 7 on fridays now"], "replies": [{"skill": "shop.hours", "slots": {"hours": HOURS}}],
            "expect": {"skills": ["shop.hours"], "dispositions": ["proposed"], "expected": rid + ".json", "undo": True}}


def golden(version_text="1"):
    return ('{"schema_version": %s, "diff": [], "files": [], "assets": {}, "residue": {"content": [], "assets": {}}}' % version_text)


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "expected").mkdir()

    def write(self, rid, version_text="1"):
        (self.root / "expected" / (rid + ".json")).write_text(golden(version_text), "utf-8")

    def rows(self, *ids):
        p = self.root / "messages.jsonl"
        p.write_text("".join(json.dumps(row(i)) + "\n" for i in ids), "utf-8")
        return p


class ExpectedVersion(Case):
    def test_expected_version_requires_exact_json_integer(self):
        for text in ("true", "false", "1.0", "1e0", "0.0", "0", "2", "-1", '"1"', "null", "[1]", '{"a": 1}'):
            with self.subTest(version=text):
                self.write("row-a", text)
                with self.assertRaisesRegex(A.InputError, "row row-a: " + REFUSAL):
                    A.load_expected(self.root, row("row-a"))
        self.write("row-a", "1")
        self.assertEqual(A.load_expected(self.root, row("row-a"))["schema_version"], 1)
        (self.root / "expected" / "row-a.json").write_text('{"diff": [], "files": [], "assets": {}, "residue": {"content": [], "assets": {}}}', "utf-8")
        with self.assertRaisesRegex(A.InputError, REFUSAL):
            A.load_expected(self.root, row("row-a"))

    def test_expected_and_row_version_type_contract_matches(self):
        for value in (True, 1.0):
            bad = dict(row("row-a"), schema_version=value)
            with self.assertRaises(A.InputError):
                A.validate_row(bad)
            self.write("row-a", json.dumps(value))
            with self.assertRaises(A.InputError):
                A.load_expected(self.root, row("row-a"))

    def test_invalid_later_golden_refuses_all_execution(self):
        self.write("row-a")
        self.write("row-b", "true")
        path = self.rows("row-a", "row-b")
        before = (self.root / "expected" / "row-b.json").read_bytes()
        with mock.patch.object(A, "run_row") as run_row:
            with self.assertRaisesRegex(A.InputError, "row row-b: " + REFUSAL):
                A.run_rows(path, fixture_root=self.root)
        run_row.assert_not_called()
        self.assertEqual((self.root / "expected" / "row-b.json").read_bytes(), before)

    def test_cli_bad_expected_version_is_private_exit_two(self):
        self.write("row-a", "1.0")
        path = self.rows("row-a")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(A, "run_row") as run_row, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = A.main(["--rows", str(path)])
        run_row.assert_not_called()
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "acceptance: row row-a: " + REFUSAL + "\n")
        self.assertNotIn(str(self.root), err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_valid_integer_golden_and_existing_checks_survive(self):
        self.write("row-a")
        path = self.rows("row-a")
        sentinel = object()
        with mock.patch.object(A, "run_row", return_value=sentinel) as run_row:
            self.assertEqual(A.run_rows(path, fixture_root=self.root), [sentinel])
        run_row.assert_called_once()
        dup = ('{"schema_version": 1, "diff": [], "files": [], "assets": {}, "residue": {"content": '
               '[{"file": "a", "path": "p"}, {"file": "a", "path": "p"}], "assets": {}}}')
        (self.root / "expected" / "row-a.json").write_text(dup, "utf-8")
        with self.assertRaisesRegex(A.InputError, "names the same file and path twice"):
            A.load_expected(self.root, row("row-a"))


if __name__ == "__main__":
    unittest.main()
