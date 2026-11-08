"""SKILLS-TK-1 level 3: the case runner of the skill test kit, and the proof that the kit itself works.

Generic part: every non-plan row of every cases file under hass/tests/fixtures/skills/<group>/ runs through the real
Conversation, Editor, sitegen and claims on a scratch writer worktree (group cards add only fixture files).
Self-test part: the toy skills and rows in fixtures/skills/_selftest: the good rows pass, and each deliberately broken
row (a skill that writes before approval, a wrong diff, an undo that leaves a trace nobody declared, ...) FAILS for
exactly its stated reason.
Run: python3 -B -m unittest hass.tests.test_skills_cases -v
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass.content_model import REPO_ROOT
from hass.skills import testkit
from hass.skills.testkit import (FIXTURES, discover, json_diff, judge_selftest, declared_covers, load_skill_module,
                                 plain_words_problems, registry_skills, run_case_row, run_file)

TOY = FIXTURES / "_selftest" / "toy.py"
CLI = REPO_ROOT / "hass" / "skills" / "testkit.py"
REQUIRED_BREAKS = {"write-before-yes", "wrong-diff", "undo-not-identical", "residue-undeclared", "edit-undeclared", "jargon"}


class RealSkillCases(unittest.TestCase):
    def test_every_case_row_of_every_skill_passes(self):
        skills, rows = registry_skills(), 0
        for path in discover():
            for result in run_file(path, skills):
                if result.plan: continue
                rows += 1
                with self.subTest(file=path.name, row=result.id):
                    self.assertEqual(result.problems, [])
        print(f"\ncase rows run against real skills: {rows}")


class KitProvesItself(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_file(FIXTURES / "_selftest" / "toy.jsonl", load_skill_module(TOY), selftest=True)

    def test_each_row_does_what_it_says(self):
        for result, ok, want in judge_selftest(self.results):
            with self.subTest(row=result.id, must_fail=want):
                self.assertTrue(ok, result.problems)

    def test_the_good_rows_pass_and_cover_every_row_kind(self):
        good = [r for r in self.results if not r.row.get("must_fail") and not r.plan]
        self.assertTrue(all(r.ok for r in good))
        self.assertEqual({r.kind for r in good}, {"clean", "vague", "multi", "refuse", "turns"})

    def test_each_break_fails_for_its_own_reason_only(self):
        broken = {r.row["must_fail"]: r for r in self.results if r.row.get("must_fail") and not r.plan}
        self.assertEqual(set(broken), REQUIRED_BREAKS)
        for code, result in broken.items():
            with self.subTest(code):
                self.assertEqual(sorted(set(result.codes)), [code])

    def test_a_skill_that_writes_without_approval_fails(self):
        [result] = [r for r in self.results if r.id == "bad-write-before-yes"]
        self.assertFalse(result.ok)
        self.assertEqual(result.codes, ["write-before-yes"])
        self.assertIn("no yes was sent", result.problems[0][1])

    def test_a_declared_residue_is_accepted_and_an_undeclared_one_is_not(self):
        by_id = {r.id: r for r in self.results}
        self.assertTrue(by_id["residue-declared"].ok)
        self.assertEqual(by_id["residue-declared"].facts["undo"], "residue")
        self.assertEqual(by_id["clean-describe"].facts["undo"], "identical")
        self.assertEqual(by_id["bad-residue-undeclared"].codes, ["residue-undeclared"])

    def test_preview_request_and_skills_are_recorded(self):
        by_id = {r.id: r for r in self.results}
        self.assertEqual(by_id["clean-describe"].facts["preview"], "product")
        self.assertEqual(by_id["refuse-price"].facts["disposition"], "unsupported")
        self.assertEqual(by_id["multi-two-skills-one-draft"].facts["diff"], 2)


class RowRules(unittest.TestCase):
    skills = {s.name: s for s in load_skill_module(TOY)}

    def row(self, **kw):
        base = {"id": "r", "kind": "clean", "texts": ["change the shop text"], "replies": [{"question": "Which one?"}],
                "expect": {"disposition": "question"}}
        return {**base, **kw}

    def test_malformed_rows_are_refused_before_anything_runs(self):
        for name, row in {
            "unknown field": self.row(surprise=1),
            "unknown expect field": self.row(expect={"disposition": "question", "colour": "red"}),
            "bad kind": self.row(kind="weird"),
            "reply count": self.row(replies=[]),
            "same text twice": self.row(texts=["a", "a"], replies=[{}, {}]),
            "fault outside the self-test": self.row(fault="write-on-prepare"),
            "must_fail outside the self-test": self.row(must_fail="wrong-diff"),
        }.items():
            with self.subTest(name):
                self.assertEqual(run_case_row(row, self.skills).codes, ["bad-row"])

    def test_a_row_for_another_skill_version_is_stale(self):
        row = self.row(version=2, replies=[{"skill": "toy.describe", "slots": {}}])
        self.assertEqual(run_case_row(row, self.skills, self.skills["toy.describe"]).codes, ["stale-row"])

    def test_wrong_expectations_are_named(self):
        r = run_case_row(self.row(expect={"disposition": "proposed", "question_contains": "banana", "skill": "toy.hours"}), self.skills)
        self.assertEqual(sorted(set(r.codes)), ["wrong-disposition", "wrong-reply", "wrong-skill"])

    def test_a_plan_that_raises_is_a_reply_not_a_crash(self):
        row = self.row(replies=[{"skill": "toy.describe", "slots": {}}], expect={"disposition": "unsupported"})
        self.assertTrue(run_case_row(row, self.skills).ok)

    def test_a_draft_row_without_a_diff_is_a_bad_row(self):
        row = self.row(replies=[{"skill": "toy.hours", "slots": {"hours": ["Closed"]}}], expect={"disposition": "proposed"})
        self.assertEqual(run_case_row(row, self.skills).codes, ["bad-row"])


class Helpers(unittest.TestCase):
    def test_plain_words(self):
        self.assertEqual(plain_words_problems("Which product do you mean, and what should the new text say?"), [])
        for bad in ("pick photo-product-001", "send the json", "op product.edit failed", "slot description is None", "chg-0123456789ab",
                    "a0b1c2d3e4f5a6b7 was it", "{'a': 1}"):
            with self.subTest(bad):
                self.assertTrue(plain_words_problems(bad), bad)
        record = "Applied and checked 3113: products photo-product-001: description\nDraft 3113:\nproducts photo-product-001: description a → b"
        self.assertEqual(plain_words_problems(record), [])  # conversation.py's own record lines are not the skill's wording
        self.assertEqual(plain_words_problems("the Hass avocado", allow=["Hass avocado"]), [])

    def test_json_diff(self):
        before = {"products": [{"id": "a", "d": "x", "n": 1}, {"id": "b", "d": "y"}], "hours": ["1", "2"], "gone": 1, "same": 2}
        after = {"products": [{"id": "a", "d": "z", "n": 1}, {"id": "b", "d": "y"}, {"id": "c"}], "hours": ["1", "3"], "new": 2, "same": 2}
        self.assertEqual(json_diff(before, after), [
            {"path": "gone", "before": 1},
            {"path": "hours", "before": ["1", "2"], "after": ["1", "3"]},
            {"path": "new", "after": 2},
            {"path": "products[a].d", "before": "x", "after": "z"},
            {"path": "products[c]", "after": {"id": "c"}}])
        self.assertEqual(json_diff({"b": 1, "a": 2}, {"a": 2, "b": 1}), [])  # key order is not a change

    def test_declared_edits(self):
        declared = [("hass/content/products.json", "products[id].available")]
        self.assertTrue(declared_covers(declared, "hass/content/products.json", "products[photo-product-001].available"))
        self.assertFalse(declared_covers(declared, "hass/content/products.json", "products[photo-product-001].description"))
        self.assertFalse(declared_covers(declared, "hass/content/store.json", "products[x].available"))
        self.assertFalse(declared_covers(declared, "hass/content/products.json", "products[x].available_on"))
        whole = [("hass/content/products.json", "products[id]")]  # a declared record covers everything under it
        self.assertTrue(declared_covers(whole, "hass/content/products.json", "products[x]"))
        self.assertTrue(declared_covers(whole, "hass/content/products.json", "products[x].image"))

    def test_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.jsonl"
            good.write_text(json.dumps({"id": "ok", "plan": True, "skill": "toy.hours", "slots": {"hours": ["Closed"]},
                                        "expect_ops": [{"op": "store.set_hours", "args": {"hours": ["Closed"]}}]}) + "\n", "utf-8")
            run = lambda *a: subprocess.run([sys.executable, "-B", str(CLI), *a], capture_output=True, text=True, cwd=REPO_ROOT)  # noqa: E731
            r = run("run", str(good), "--skills", str(TOY))
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            self.assertIn("PASS  ok", r.stdout)
            good.write_text(good.read_text("utf-8").replace('"Closed"]}}]', '"Open"]}}]'), "utf-8")
            r = run("run", str(good), "--skills", str(TOY))
            self.assertEqual(r.returncode, 1)
            self.assertIn("FAIL  ok", r.stdout)
            self.assertEqual(run("run", str(Path(tmp) / "missing.jsonl"), "--skills", str(TOY)).returncode, 2)


if __name__ == "__main__":
    unittest.main()
