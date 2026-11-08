"""SKILLS-FW-1: the skill lint (spec 2.9 level 1) on a reference skill and on one broken field at a time."""

import dataclasses
import unittest

from hass import skills
from hass.ops import load_registry
from hass.skills import model
from hass.tests.test_skills_model import _skill


class LintTests(unittest.TestCase):
    def setUp(self):
        self.ops = load_registry()

    def lint(self, **over):
        return skills.skill_lint([_skill(**over)], self.ops)

    def test_reference_skill_is_clean(self):
        self.assertEqual(self.lint(), [])

    def test_slot_kinds_are_op_kinds_plus_skill_kinds(self):
        for kind in ("id", "date", "image", "product_ref", "maker_ref", "shelf", "availability", "day", "clock", "attachment"):
            self.assertIn(kind, skills.SLOT_KINDS)

    def test_skill_is_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            _skill().name = "x.y"

    def test_each_mandatory_field_is_checked(self):
        cases = {
            "name": dict(name="Stock"), "label": dict(label="stock.set"), "summary": dict(summary="x" * 121),
            "triggers": dict(triggers=(model.Trigger("a"),)), "slots": dict(slots=(model.Slot("a", "weird", False),)),
            "rules": dict(rules=("Bad Rule",)), "plan": dict(plan=None), "edits": dict(edits=(("elsewhere.json", "x"),)),
            "side_effects": dict(side_effects=("nuke",)), "preview": dict(preview="screen"),
            "approval": dict(approval="maybe"), "live_class": dict(live_class="live"), "undo": dict(undo=None),
            "refuse": dict(refuse=("nope",)), "cases": dict(cases="tests/x.jsonl"), "version": dict(version=0),
        }
        for field, over in cases.items():
            with self.subTest(field=field):
                problems = self.lint(**over)
                self.assertTrue(any(f": {field}:" in p for p in problems), problems)

    def test_trigger_mix_and_duplicates(self):
        base = _skill().triggers
        self.assertTrue(any("needs at least one typo" in p for p in self.lint(triggers=tuple(t for t in base if t.tag != "typo"))))
        self.assertTrue(any("needs at least one multi" in p for p in self.lint(triggers=tuple(t for t in base if t.tag != "multi"))))
        dup = base + (model.Trigger("Eggs are OUT!"),)
        self.assertTrue(any("same trigger text twice" in p for p in self.lint(triggers=dup)))

    def test_trigger_text_may_not_repeat_in_two_skills(self):
        other = _skill(name="stock.other", cases="hass/tests/fixtures/skills/inventory/stock.other.jsonl")
        problems = skills.skill_lint([_skill(), other], self.ops)
        self.assertTrue(any("is also a trigger of stock.set" in p for p in problems), problems)

    def test_duplicate_skill_name_and_slot_names(self):
        self.assertTrue(any("name used twice" in p for p in skills.skill_lint([_skill(), _skill()], self.ops)))
        slots = (model.Slot("a", "text", True, ask="What?"), model.Slot("a", "text", False))
        self.assertTrue(any("unique" in p for p in self.lint(slots=slots)))

    def test_slot_rules(self):
        long_ask = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"
        self.assertTrue(any("ask of 1 to 14" in p for p in self.lint(slots=(model.Slot("a", "text", True, ask=long_ask),))))
        self.assertTrue(any("ask of 1 to 14" in p for p in self.lint(slots=(model.Slot("a", "text", True),))))
        self.assertTrue(any("never asks" in p for p in self.lint(slots=(model.Slot("a", "text", False, ask="What?"),))))
        self.assertTrue(any("another slot" in p for p in self.lint(slots=(model.Slot("a", "text", "if:zzz", ask="What?"),))))
        ok = (model.Slot("a", "bool", False), model.Slot("b", "text", "if:a", ask="What?"))
        self.assertEqual(self.lint(slots=ok), [])

    def test_attachment_slot_must_come_from_the_photo(self):
        self.assertTrue(self.lint(slots=(model.Slot("p", "attachment", True, ask="Send the photo."),)))
        self.assertEqual(self.lint(slots=(model.Slot("p", "attachment", True, ask="Send the photo.", from_attachment=True),)), [])

    def test_read_only_pairing(self):
        ro = dict(approval="none", live_class="read-only", preview="none", edits=(), undo=model.Undo("none", "none"))
        self.assertEqual(self.lint(**ro), [])
        self.assertTrue(self.lint(**{**ro, "live_class": "chat-live"}))
        self.assertTrue(self.lint(**{**ro, "edits": (("hass/content/store.json", "x"),)}))
        self.assertTrue(self.lint(**{**ro, "undo": model.Undo("revert", "none")}))
        self.assertTrue(self.lint(live_class="read-only"))
        self.assertTrue(self.lint(preview="none"))
        self.assertTrue(self.lint(edits=()))

    def test_edits_must_be_files_the_editor_writes(self):
        self.assertEqual(self.lint(edits=(("storefront-mockup/index.html", "x"), ("hass/content/community.json", "events"))), [])
        self.assertTrue(self.lint(edits=(("hass/content/secrets.json", "x"),)))

    def test_plan_output_is_checked(self):
        s = _skill()
        ok = [{"op": "product.hide", "args": {"id": "photo-product-001"}}]
        self.assertEqual(model.lint_plan_output(s, ok, self.ops), [])
        self.assertTrue(model.lint_plan_output(s, [{"op": "no.such", "args": {}}], self.ops))
        self.assertTrue(model.lint_plan_output(s, ok * 21, self.ops))
        self.assertTrue(model.lint_plan_output(s, "x", self.ops))
        ro = _skill(approval="none", live_class="read-only", preview="none", edits=(), undo=model.Undo("none", "none"))
        self.assertTrue(model.lint_plan_output(ro, ok, self.ops))

    def test_golden_plans_run_through_the_lint(self):
        bad = _skill(plan=lambda s, c: [{"op": "no.such", "args": {}}])
        problems = skills.skill_lint([bad], self.ops, golden={"stock.set": [{"items": ["x"]}]})
        self.assertTrue(any("not a registered op" in p for p in problems))
        boom = _skill(plan=lambda s, c: 1 / 0)
        self.assertTrue(any("raised ZeroDivisionError" in p for p in skills.skill_lint([boom], self.ops, golden={"stock.set": [{}]})))

    def test_case_file_checks(self):
        import json, tempfile
        from pathlib import Path
        s = _skill()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(any("is missing" in p for p in model.lint_cases(s, tmp)))
            path = Path(tmp) / s.cases
            path.parent.mkdir(parents=True)
            rows = [{"kind": "clean", "version": 1}] * 8 + [{"kind": "refuse", "version": 1}] * 2 + [{"kind": "undo", "version": 1}]
            path.write_text("\n".join(json.dumps(r) for r in rows))
            self.assertEqual(model.lint_cases(s, tmp), [])
            path.write_text("\n".join(json.dumps(r) for r in rows[:5]))
            self.assertEqual(len(model.lint_cases(s, tmp)), 3)
            path.write_text("\n".join(json.dumps({**r, "version": 2}) for r in rows))
            self.assertTrue(any("another version" in p for p in model.lint_cases(s, tmp)))


if __name__ == "__main__":
    unittest.main()
