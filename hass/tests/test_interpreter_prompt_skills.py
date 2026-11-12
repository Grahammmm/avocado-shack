"""SKILLS-FW-2: the Skills block of the interpreter prompt. Offline. The pinned snapshot is test_interpreter_prompt's."""

import dataclasses
import hashlib
import json
import unittest

from hass.interpreter_prompt import PROMPT_MAX_BYTES, build
from hass.ops import load_registry
from hass.skills import dispatch, load_skills, model, stock
from hass.skills.items import ITEM_HIDE
from hass.skills.prompt import CONTRACT, STOCK_ITEMS_SHAPE, _slot_text, skills_section
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

    def test_stock_items_shape_is_explained_without_changing_other_kinds(self):  # RF0814-12
        reg = load_skills()
        section = skills_section(reg, [("stock.set", 9.0), ("stock.checked", 5.0)])
        self.assertEqual(section, skills_section(reg, [("stock.set", 9.0), ("stock.checked", 5.0)]))
        self.assertLessEqual(len(section.encode("utf-8")), model.MAX_PROMPT_BYTES)
        [line] = [ln for ln in section.splitlines() if ln.startswith("  slots: items: stock_items, required (")]
        self.assertEqual(line, "  slots: items: stock_items, required" + STOCK_ITEMS_SHAPE)
        for word in ("yes", "limited", "no"):
            self.assertIn(f'"{word}"', line)
        example = json.loads(line[line.index("e.g. ") + len("e.g. "):-1])
        self.assertEqual(example, [{"product": "photo-product-001", "availability": "no"}])
        self.assertIsNone(dispatch._value_problem(stock.STOCK_SET.slots[0], example))  # the example is what the check takes
        self.assertIn("  slots: day: day, optional; in: text_list, optional; limited: text_list, optional; out: text_list, optional\n",
                      section)
        for slot in _skill("a.b").slots:
            self.assertNotIn("(", _slot_text(slot))
        self.assertEqual(_slot_text(model.Slot("items", "text_list", True)), "items: text_list, required")

    def test_a_slot_hint_is_shown_after_the_kind_and_only_when_set(self):  # AV1109-09
        slot = model.Slot("kind", "enum", True, ask="Which?", hint="exactly one of (a | b)")
        self.assertEqual(_slot_text(slot), "kind: enum, required - exactly one of (a | b)")
        self.assertEqual(_slot_text(dataclasses.replace(slot, hint="")), "kind: enum, required")


CAP = model.MAX_PROMPT_BYTES
HEADING = "Likely skills for this message:\n"


def _size(text):
    return len(text.encode("utf-8"))


def _labelled(label, name="grp0.act0", **changes):
    return dataclasses.replace(_skill(name), label=label, **changes)


def _one(label, **changes):
    skill = _labelled(label, **changes)
    return skills_section([skill], [skill.name])


class SkillsBlockCapTests(unittest.TestCase):  # RF1935-10: the cap is on the returned bytes, newline and Unicode included
    def assert_bounded(self, text):
        self.assertLessEqual(_size(text), CAP)
        self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))
        self.assertNotIn("\ufffd", text)
        self.assertEqual(text.encode("utf-8").decode("utf-8", "strict"), text)

    def test_exact_ascii_cap_includes_returned_newline(self):
        probe = _one("x")  # the three-example stage, which fits easily; its size grows one byte per label character
        self.assertEqual(probe.count("example number"), 3)
        edge = len("x") + CAP - _size(probe)  # label length whose three-example block returns exactly CAP bytes
        at_cap = _one("x" * edge)
        self.assertEqual(_size(at_cap), CAP)
        self.assertEqual(at_cap.count("example number"), 3)
        self.assert_bounded(at_cap)
        self.assertGreater(_size(at_cap), CAP - 1)
        for over in (edge + 1, edge + 2):  # one byte past: not the three-example stage, still inside the cap
            text = _one("x" * over)
            self.assert_bounded(text)
            self.assertEqual(text.count("example number"), 1)
        self.assert_bounded(_one("x" * (edge - 1)))

    def test_unicode_oversized_candidate_has_bounded_complete_fallback(self):
        control = _one("do a thing")
        self.assertIn("do a thing example number 2 please", control)
        label = "€" * 2100  # lint-admitted owner words (3 bytes each); the old character slice returned a block far over the cap
        skill = dataclasses.replace(ITEM_HIDE, label=label)
        self.assertEqual(model.lint_skill(skill, load_registry()), [])
        self.assert_bounded(skills_section([skill], [skill.name]))
        self.assertEqual(skills_section([skill], [skill.name]), CONTRACT + "\n")  # even the bare row is over the cap
        # between: the detailed entry overflows, the complete name - label row alone still fits, with no slot line
        for count in range(1500, 2100):
            label = "€" * count
            text = skills_section([dataclasses.replace(ITEM_HIDE, label=label)], ["item.hide"])
            self.assert_bounded(text)
            if "slots:" not in text:
                break
        else:
            self.fail("no row-only fallback between the detailed entry and the contract-only block")
        self.assertEqual(text, CONTRACT + "\n\n" + HEADING + f"- item.hide - {label}\n")
        self.assertGreater(_size(skills_section([dataclasses.replace(ITEM_HIDE, label="€" * (count - 1))], ["item.hide"])), CAP - 4)
        huge = _one("é" * 3500)
        self.assert_bounded(huge)
        self.assertEqual(huge, CONTRACT + "\n")
        self.assertEqual(_one("x" * 7000), CONTRACT + "\n")
        self.assertLessEqual(_size(CONTRACT) + 1, CAP)

    def test_catalog_pruning_accounts_for_newline_and_omitted_count(self):
        others = [_labelled(f"do thing {i}", f"grp{i // 4}.act{i + 1}") for i in range(270)]
        seen_widths, exact = set(), 0
        for length in range(1, 800):  # every byte offset of the candidate row crosses the trimming boundary
            top = _labelled("y" * length, "grp0.act0")
            text = skills_section([top] + others, ["grp0.act0"])
            self.assert_bounded(text)
            head, tail = text.rstrip("\n").split("Other skills:\n")
            rows = tail.split("\n")
            shown = [r for r in rows if not r.startswith("... and")]
            if len(shown) == len(others):
                continue
            omitted = rows[-1]
            self.assertEqual(omitted, f"... and {len(others) - len(shown)} more skills")
            seen_widths.add(len(str(len(others) - len(shown))))
            nxt = f"- {others[len(shown)].name} - {others[len(shown)].label}"
            more = len(others) - len(shown) - 1
            grown = _size(text) - len(omitted.encode()) + len(nxt.encode()) + 1 + (len(f"... and {more} more skills") + 1 if more else 0)
            self.assertGreater(grown, CAP)  # keeping one more catalog row would not have fit, newline counted
            exact += _size(text) == CAP
        self.assertGreaterEqual(len(seen_widths), 2)  # the omitted count changed its digit width across the sweep
        self.assertGreater(exact, 0)  # at least one length returns exactly CAP bytes, final newline included

    def test_slots_too_large_keep_only_complete_candidate_row(self):
        fat = _labelled("a plain label", slots=(model.Slot("what", "text", True, ask="Which one?", hint="h" * 7000),))
        text = skills_section([fat], [fat.name])
        self.assert_bounded(text)
        self.assertEqual(text, CONTRACT + "\n\n" + HEADING + "- grp0.act0 - a plain label\n")
        self.assertNotIn("slots:", text)
        self.assertNotIn("what: text", text)
        row_too_big = _labelled("z" * 7000, slots=fat.slots)
        self.assertEqual(skills_section([row_too_big], [row_too_big.name]), CONTRACT + "\n")
        no_candidates = skills_section([fat], [])  # nothing is detailed: the catalog row shows, never a slot line
        self.assertEqual(no_candidates.count("slots:"), 0)
        self.assert_bounded(no_candidates)

    def test_normal_and_empty_registry_bytes_unchanged(self):
        def digest(text):
            return hashlib.sha256(text.encode("utf-8")).hexdigest()

        # sha256 of the outputs of the code before RF1935-10 (the repair does not touch ordinary bytes)
        golden = {
            "reg3": (_registry(3), (), 668, "dce302d469c765c57bbd107851e395ab9a1f96d616fcb36e94a04ff89590a84b"),
            "reg3_cand": (_registry(3), ("grp0.act1",), 948, "74107bbfc0284a7bcf9412239523d09436c69c8dfa70400a1ece8000071f41b8"),
            "reg6_cand": (_registry(6), (("grp0.act2", 4.0),), 1023, "b2224371ed9ab668e31bd4153ab8d71fa1dd5041326b0701b8f60e82660d7216"),
            "reg32": (_registry(32), tuple((n, 3.0) for n in list(_registry(32).skills)[:3]), 2211,
                      "5a492859ecb9bc9069697dec13a4d52fd736a678bf085994bdd27266e992b1cc"),
            "reg400": (_registry(400), tuple((n, 1.0) for n in list(_registry(400).skills)[:3]), 6141,
                       "c387d4805a67bc86d2f2a6686452565f8e5a5d89e113ec2658c768ab643800cd"),
        }
        for key, (reg, cands, size, sha) in golden.items():
            text = skills_section(reg, cands)
            self.assertEqual((_size(text), digest(text)), (size, sha), key)
        self.assertEqual(skills_section(model.Registry({}), []), "")
        self.assertEqual(skills_section(None, []), "")
        retired = model.Registry({"a.b": dataclasses.replace(_skill("a.b"), status="retired")})
        self.assertEqual(skills_section(retired, ["a.b"]), "")
        reg = _registry(5)
        self.assertEqual(skills_section(reg, ["nope", "grp0.act1", "grp0.act1"]), skills_section(reg, ["grp0.act1"]))
        self.assert_bounded(skills_section(load_skills(), []))

    def test_integrated_builder_uses_bounded_skills_section(self):
        pinned = FIXTURE.read_text("utf-8").rstrip("\n")
        for skill in (_labelled("é" * 2100), _labelled("é" * 3500), _labelled("x" * 7000)):
            reg = model.Registry({skill.name: skill})
            block = skills_section(reg, [skill.name])
            self.assert_bounded(block)
            prompt = build(TEST_REGISTRY, tiny_content(), reg, [skill.name])
            self.assertTrue(prompt.startswith(pinned))
            self.assertTrue(prompt.endswith("\n\n" + block.rstrip("\n") + "\n"))
            self.assertEqual(prompt[len(pinned):], "\n\n" + block)
            self.assertLessEqual(_size(prompt), PROMPT_MAX_BYTES + CAP + 2)


if __name__ == "__main__":
    unittest.main()
