"""SKILLS-FW-2: the Skills block of the interpreter prompt. Offline. The pinned snapshot is test_interpreter_prompt's."""

import dataclasses
import unittest

from hass.interpreter_prompt import PROMPT_MAX_BYTES, build
from hass.skills import model
from hass.skills.prompt import CONTRACT, skills_section
from hass.tests.test_interpreter_prompt import FIXTURE, TEST_REGISTRY, tiny_content


def _skill(name, label="do a thing", n_examples=10):
    return model.Skill(
        name=name, label=label, summary=f"{label} for the owner, with a longer sentence about what it changes.",
        triggers=tuple(model.Trigger(f"{label} example number {i} please") for i in range(n_examples)),
        slots=(model.Slot("what", "text", True, ask="Which one?"), model.Slot("when", "day", False)),
        rules=(), plan=lambda s, c: [], edits=(), side_effects=(), preview="none", approval="owner-yes",
        live_class="chat-live", undo=model.Undo("revert", "none"), refuse=(), cases="hass/tests/fixtures/skills/x/y.jsonl",
        version=1)


def _registry(count):
    return model.Registry({s.name: s for s in (_skill(f"grp{i // 4}.act{i}", f"do thing {i}") for i in range(count))})


class SkillsBlockTests(unittest.TestCase):
    def test_no_skills_is_byte_identical_to_the_pinned_prompt(self):
        pinned = FIXTURE.read_text("utf-8")
        content = tiny_content()
        self.assertEqual(build(TEST_REGISTRY, content), pinned)
        for skills in (None, model.Registry({}), ()):
            self.assertEqual(build(TEST_REGISTRY, content, skills), pinned)
        retired = model.Registry({"a.b": dataclasses.replace(_skill("a.b"), status="retired")})
        self.assertEqual(build(TEST_REGISTRY, content, retired), pinned)

    def test_skills_are_appended_last_and_leave_the_rest_alone(self):
        pinned = FIXTURE.read_text("utf-8")
        prompt = build(TEST_REGISTRY, tiny_content(), _registry(3))
        self.assertTrue(prompt.startswith(pinned.rstrip("\n")))
        tail = prompt[len(pinned.rstrip("\n")):]
        self.assertTrue(tail.lstrip("\n").startswith("Skills."))
        self.assertTrue(prompt.endswith("\n"))

    def test_the_contract_names_every_reply_shape(self):
        for shape in ('"skill"', '"calls"', '"none"', "revises"):
            self.assertIn(shape, CONTRACT)

    def test_candidates_get_full_detail_the_rest_one_line(self):
        reg = _registry(6)
        text = skills_section(reg, [("grp0.act2", 4.0)])
        self.assertIn("Likely skills for this message:", text)
        self.assertIn("slots: what: text, required; when: day, optional", text)
        self.assertEqual(text.count("e.g."), 1)
        self.assertIn("- grp0.act0 - do thing 0\n", text)
        self.assertEqual(text.count("do thing 0 example number 0"), 0)

    def test_deterministic_and_unknown_candidates_change_nothing(self):
        reg = _registry(8)
        self.assertEqual(skills_section(reg, ["grp1.act5"]), skills_section(reg, ["grp1.act5"]))
        self.assertEqual(skills_section(list(reg.skills.values()), ["grp1.act5"]), skills_section(reg, ["grp1.act5"]))
        self.assertEqual(skills_section(reg, ["nope.nope"]), skills_section(reg, []))

    def test_thirty_two_skills_stay_under_the_prompt_cap(self):
        reg = _registry(32)
        top = [(n, 3.0) for n in list(reg.skills)[:3]]
        section = skills_section(reg, top)
        self.assertLessEqual(len(section.encode("utf-8")), model.MAX_PROMPT_BYTES)
        for name in reg.skills:
            self.assertIn(name, section)
        prompt = build(TEST_REGISTRY, tiny_content(), reg, top)
        self.assertLess(len(prompt.encode("utf-8")), 64 * 1024)
        self.assertLessEqual(len(prompt.encode("utf-8")), PROMPT_MAX_BYTES + model.MAX_PROMPT_BYTES + 2)

    def test_an_oversized_block_drops_detail_first_then_catalog_lines(self):
        reg = _registry(400)
        section = skills_section(reg, [(n, 1.0) for n in list(reg.skills)[:3]])
        self.assertLessEqual(len(section.encode("utf-8")), model.MAX_PROMPT_BYTES)
        self.assertTrue("more skills" in section)
        self.assertTrue(section.startswith("Skills."))


if __name__ == "__main__":
    unittest.main()
