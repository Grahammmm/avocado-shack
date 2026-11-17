"""RF1751-10: malformed recorded-reply containers are a named bad-row, never a traceback (synthetic rows only).

Run: python3 -B -m unittest hass.tests.test_testkit_reply_shapes -q
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass.skills import testkit
from hass.skills.testkit import FIXTURES, load_skill_module, run_case_row, run_file, skill_for

TOY = FIXTURES / "_selftest" / "toy.py"
PLAN = {"id": "healthy-plan", "plan": True, "skill": "toy.describe",
        "slots": {"product": "photo-product-001", "description": "Creamy flesh and a little lime."},
        "expect_ops": [{"op": "product.edit", "args": {"id": "photo-product-001", "description": "Creamy flesh and a little lime."}}]}


def case(**kw):
    base = {"id": "r", "kind": "clean", "texts": ["change the shop text"], "replies": [{"question": "Which one?"}],
            "expect": {"disposition": "question"}}
    return {**base, **kw}


def bad_replies():
    return {
        "null replies": case(replies=None), "number replies": case(replies=3), "text replies": case(replies="x"),
        "object replies": case(replies={"a": 1}),
        "null reply": case(replies=[None]), "list reply": case(replies=[[]]), "scalar reply": case(replies=[5]),
        "null calls": case(replies=[{"calls": None}]), "scalar calls": case(replies=[{"calls": 4}]),
        "object calls": case(replies=[{"calls": {"skill": "toy.hours"}}]), "scalar call": case(replies=[{"calls": [None]}]),
        "list skill": case(replies=[{"skill": ["toy.hours"]}]), "dict skill": case(replies=[{"skill": {}}]),
        "bool skill": case(replies=[{"skill": True}]), "number skill": case(replies=[{"skill": 7}]),
        "list call skill": case(replies=[{"calls": [{"skill": ["x"]}]}]),
    }


class DirectRows(unittest.TestCase):
    skills = {s.name: s for s in load_skill_module(TOY)}

    def test_malformed_containers_are_bad_row_before_scratch(self):
        for name, row in bad_replies().items():
            with self.subTest(name), mock.patch.object(testkit, "Scratch", side_effect=AssertionError("scratch built")):
                res = run_case_row(row, self.skills)
                self.assertEqual(res.codes, ["bad-row"])
                self.assertIn("replies", res.problems[0][1])

    def test_detail_names_the_field_without_the_value(self):
        res = run_case_row(case(replies=[{"skill": ["secret-value"]}]), self.skills)
        self.assertIn("replies[0].skill", res.problems[0][1])
        self.assertNotIn("secret-value", res.problems[0][1])

    def test_valid_reply_forms_survive(self):
        for replies in ([{"question": "Which one?"}], [{}], [{"skill": None, "question": "Which one?"}],
                        [{"calls": [], "question": "Which one?"}]):
            with self.subTest(replies=replies):
                self.assertNotIn("bad-row", run_case_row(case(replies=replies), self.skills).codes)
        unsupported = case(replies=[{"unsupported": "no"}], expect={"disposition": "unsupported"})
        self.assertNotIn("bad-row", run_case_row(unsupported, self.skills).codes)

    def test_inference_skips_malformed_rows(self):
        rows = [case(replies=None), case(replies=[{"skill": ["x"]}]), case(replies=[{"skill": "toy.hours"}])]
        skills = list(self.skills.values())
        self.assertEqual(skill_for(skills, "unknown.jsonl", rows).name, "toy.hours")
        self.assertIsNone(skill_for(skills, "unknown.jsonl", rows[:2]))
        self.assertEqual(skill_for(skills, "toy.describe.jsonl", rows).name, "toy.describe")


class FileAndCli(unittest.TestCase):
    skills = load_skill_module(TOY)

    def write(self, directory, name, rows):
        path = Path(directory) / name
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return path

    def test_file_reports_then_continues(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("toy.describe.jsonl", "unknown-name.jsonl"):
                path = self.write(d, name, [case(replies=None), case(id="calls", replies=[{"calls": None}]), PLAN])
                results = run_file(path, self.skills)
                self.assertEqual([r.codes for r in results], [["bad-row"], ["bad-row"], []])
                self.assertEqual(results[-1].id, "healthy-plan")

    def test_cli_exit_one_without_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, "unknown-name.jsonl", [case(replies=[{"skill": ["x"]}]), PLAN])
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = testkit.main(["run", str(path), "--skills", str(TOY)])
            self.assertEqual(code, 1)
            self.assertIn("FAIL  r", out.getvalue())
            self.assertIn("[bad-row]", out.getvalue())
            self.assertIn("PASS  healthy-plan", out.getvalue())
            self.assertIn("1 passed, 1 failed", out.getvalue())
            self.assertEqual(err.getvalue(), "")

    def test_row_filter_still_selects(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, "unknown-name.jsonl", [case(replies=None), PLAN])
            results = run_file(path, self.skills, only=["healthy-plan"])
            self.assertEqual([(r.id, r.codes) for r in results], [("healthy-plan", [])])


if __name__ == "__main__":
    unittest.main()
