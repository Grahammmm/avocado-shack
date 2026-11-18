"""RF1751-9: golden-plan op/args envelopes of the wrong type are named problems, never a crash or a clean lint."""

import copy
import unittest

from hass import skills
from hass.ops import load_registry
from hass.skills import model
from hass.tests.test_skills_model import _skill

GOOD = {"op": "product.hide", "args": {"id": "photo-product-001"}}


class PlanOutputShapeTests(unittest.TestCase):
    def setUp(self):
        self.ops = load_registry()
        self.skill = _skill()

    def lint(self, ops, skill=None):
        return model.lint_plan_output(skill or self.skill, ops, self.ops)

    def test_plan_op_nontext_is_a_problem(self):
        for bad in ([], {}, None, True, 5):
            with self.subTest(op=bad):
                problems = self.lint([{"op": bad, "args": {}}])
                self.assertEqual(problems, ["stock.set: plan: op 1 must be text"])

    def test_plan_args_nonobject_is_a_problem(self):
        for bad in (None, [], "x", True, 5):
            with self.subTest(args=bad):
                problems = self.lint([{"op": "product.hide", "args": bad}])
                self.assertEqual(problems, ["stock.set: plan: args of op 1 must be an object"])

    def test_public_golden_lint_reports_malformed_return(self):
        for bad in ({"op": [], "args": {}}, {"op": "product.hide", "args": None}):
            with self.subTest(bad=bad):
                s = _skill(plan=lambda sl, c, b=bad: [b])
                problems = skills.skill_lint([s], self.ops, golden={"stock.set": [{"items": ["x"]}]})
                self.assertTrue(any(": plan: " in p and "must be" in p for p in problems), problems)

    def test_valid_plan_and_empty_plan_keep_contract(self):
        self.assertEqual(self.lint([GOOD]), [])
        self.assertEqual(self.lint([]), [])

    def test_existing_envelope_count_readonly_unknown_guards_survive(self):
        self.assertTrue(self.lint([{"op": "product.hide"}]))
        self.assertTrue(self.lint([{"op": "product.hide", "args": {}, "x": 1}]))
        self.assertTrue(any("not a registered op" in p for p in self.lint([{"op": "no.such", "args": {}}])))
        self.assertTrue(any("more than" in p for p in self.lint([GOOD] * 21)))
        ro = _skill(approval="none", live_class="read-only", preview="none", edits=(), undo=model.Undo("none", "none"))
        self.assertTrue(self.lint([GOOD], ro))
        self.assertEqual(self.lint([], ro), [])

    def test_mixed_plan_and_inputs_are_not_mutated(self):
        plan = [GOOD, {"op": {}, "args": None}]
        before, reg_before = copy.deepcopy(plan), copy.deepcopy(self.ops)
        self.assertTrue(self.lint(plan))
        self.assertEqual(plan, before)
        self.assertEqual(self.ops, reg_before)


if __name__ == "__main__":
    unittest.main()
