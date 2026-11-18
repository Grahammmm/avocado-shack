"""SKILLS-TK-1 level 2: the plan golden of the skill test kit (no model, no git, no scratch state).

Every `"plan": true` row of every cases file under hass/tests/fixtures/skills/<group>/ is run against the skill's own
plan code (none exist until the group cards add them), and the kit's own toy rows prove the plan checks.
Run: python3 -B -m unittest hass.tests.test_skills_plans -v
"""

import types
import unittest

from hass.skills import testkit
from hass.skills.testkit import FIXTURES, discover, judge_selftest, load_rows, load_skill_module, registry_skills, run_file, run_plan_row

TOY = FIXTURES / "_selftest" / "toy.py"


def _skill(plan, name="t.skill"):
    return types.SimpleNamespace(name=name, plan=plan, version=1, edits=(), preview="none", residue="none")


def _op(args=None): return {"op": "store.set_hours", "args": args or {"hours": ["Closed"]}}


def plan_row_ids(path):
    """Ids of the plan rows of one cases file, so run_file executes only those (case rows belong to test_skills_cases).

    Returns None (run every row, as before) when the file has a row this filter cannot name exactly - a non-object
    row or a plan row without an id - so a malformed file is still reported here as it always was."""
    rows = load_rows(path)
    if not all(isinstance(r, dict) for r in rows) or any(r.get("plan") and "id" not in r for r in rows):
        return None
    return [r["id"] for r in rows if r.get("plan")]


class RealSkillPlans(unittest.TestCase):
    def test_every_plan_row_of_every_skill_passes(self):
        skills, rows = registry_skills(), 0
        for path in discover():
            ids = plan_row_ids(path)
            if ids == []: continue  # no plan rows: nothing for this test to check
            for result in run_file(path, skills, only=ids):
                if not result.plan: continue
                rows += 1
                with self.subTest(file=path.name, row=result.id):
                    self.assertEqual(result.problems, [])
        print(f"\nplan rows run against real skills: {rows}")


class KitPlanRows(unittest.TestCase):
    def test_toy_plan_rows_do_what_they_say(self):
        toy = FIXTURES / "_selftest" / "toy.jsonl"
        results = [r for r in run_file(toy, load_skill_module(TOY), selftest=True, only=plan_row_ids(toy)) if r.plan]
        self.assertGreaterEqual(len(results), 4)
        for result, ok, want in judge_selftest(results):
            with self.subTest(row=result.id):
                self.assertTrue(ok, result.problems)
        self.assertEqual({r.id: r.codes for r in results if not r.ok}, {"plan-wrong-ops-must-fail": ["wrong-ops"]})

    def row(self, **kw): return {"id": "r", "plan": True, "slots": {"a": 1}, **kw}

    def test_plan_contract_is_enforced(self):
        def impure(slots, ctx):
            slots["a"] = 2  # changes what it was given
            return [_op()]

        calls = []

        def drifting(slots, ctx):
            calls.append(1)
            return [_op({"hours": [str(len(calls))]})]

        cases = {
            "an op that is not in the registry": _skill(lambda s, c: [{"op": "nope.nothing", "args": {}}]),
            "no ops at all": _skill(lambda s, c: []),
            "more than 20 ops": _skill(lambda s, c: [_op()] * 21),
            "slots changed": _skill(impure),
            "not the same twice": _skill(drifting),
            "ops that are not {op, args}": _skill(lambda s, c: [{"op": "store.set_hours"}]),
        }
        for name, skill in cases.items():
            with self.subTest(name):
                result = run_plan_row(self.row(expect_ops=[_op()]), {}, skill)
                self.assertIn("bad-plan", result.codes)

    def test_a_good_plan_passes_and_a_wrong_golden_fails(self):
        skill = _skill(lambda s, c: [_op()])
        self.assertTrue(run_plan_row(self.row(expect_ops=[_op()]), {}, skill).ok)
        self.assertEqual(run_plan_row(self.row(expect_ops=[_op({"hours": ["Open"]})]), {}, skill).codes, ["wrong-ops"])

    def test_refusals(self):
        def refuse(slots, ctx): raise ValueError("no price in the text")
        self.assertTrue(run_plan_row(self.row(expect_error="no price"), {}, _skill(refuse)).ok)
        self.assertEqual(run_plan_row(self.row(expect_error="other words"), {}, _skill(refuse)).codes, ["wrong-ops"])
        self.assertEqual(run_plan_row(self.row(expect_ops=[_op()]), {}, _skill(refuse)).codes, ["bad-plan"])
        self.assertEqual(run_plan_row(self.row(expect_error="x"), {}, _skill(lambda s, c: [_op()])).codes, ["wrong-ops"])

    def test_malformed_rows_are_named(self):
        skill = _skill(lambda s, c: [_op()])
        self.assertEqual(run_plan_row({"id": "r", "plan": True}, {}, skill).codes, ["bad-plan"])
        self.assertEqual(run_plan_row(self.row(extra=1, expect_ops=[]), {}, skill).codes, ["bad-plan"])
        self.assertEqual(run_plan_row(self.row(), {}, skill).codes, ["bad-row"])  # neither expect_ops nor expect_error
        self.assertEqual(run_plan_row(self.row(expect_ops=[_op()]), {}, None).codes, ["no-skill"])

    def test_the_toy_file_is_not_found_as_a_real_skill_file(self):
        self.assertNotIn("_selftest", {p.parent.name for p in discover()})
        self.assertTrue(load_rows(FIXTURES / "_selftest" / "toy.jsonl"))
        self.assertTrue(testkit.MAX_OPS == 20)


if __name__ == "__main__":
    unittest.main()
