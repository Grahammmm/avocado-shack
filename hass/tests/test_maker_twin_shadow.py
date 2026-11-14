"""RF1045-13: the maker-twin guard excludes the edited maker before it searches for another maker's name.

A maker whose display name differs from its immutable key can have that key as the first normalized match for a
proposed rename; another maker already named that must still be found, in any dictionary order.
Run: python3 -B -m unittest hass.tests.test_maker_twin_shadow -q
"""
import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from hass.content_model import Content, validate_makers
from hass.ops import OpContext, catalog
from hass.skills import makers as m

VISIBLE = "Meadow Farm is already on the site. Do you want to change it instead?"
HIDDEN = "Meadow Farm is on the site but hidden. Do you want me to bring them back instead?"
EDIT = {"maker": "Meadow Farm", "name": "Meadow Farm"}


def record(name):
    return {"name": name, "place": "Cambria, California", "story": "Small batches from a local workshop."}


def reachable(reverse=False, hidden=False):
    """Two invented makers put into the shadowing state by the real typed maker.edit operation (twice)."""
    content = Content([], {"Meadow Farm": record("Meadow Farm"), "River Farm": record("River Farm")}, {}, {})
    ops = OpContext(datetime(2026, 11, 14, tzinfo=timezone.utc), Path("."), {})
    for key, name in (("Meadow Farm", "Meadow Pantry"), ("River Farm", "Meadow Farm")):
        assert isinstance(catalog._maker_edit(content, {"key": key, "name": name}, ops), list)
    if hidden:
        content.makers["River Farm"]["hidden"] = True
    if reverse:
        content.makers = dict(reversed(list(content.makers.items())))
    return content, ops


def ctx(content):
    return SimpleNamespace(content=content)


def refused(slots, content):
    with unittest.TestCase().assertRaises(m.Refusal) as caught:
        m.plan_edit(slots, ctx(content))
    return caught.exception


class TwinShadow(unittest.TestCase):
    def test_own_key_does_not_mask_visible_name_twin(self):
        content, _ = reachable()
        before = copy.deepcopy(content)
        for call in (lambda: m.rule_maker_twin(content, "Meadow Farm", own_key="Meadow Farm"),
                     lambda: m.describe_edit(dict(EDIT), ctx(content)),
                     lambda: m.plan_edit(dict(EDIT), ctx(content))):
            with self.assertRaises(m.Refusal) as caught:
                call()
            self.assertEqual((caught.exception.kind, caught.exception.reply), ("question", VISIBLE))
        self.assertEqual(content, before)

    def test_hidden_name_twin_keeps_restore_question_in_both_orders(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                content, _ = reachable(reverse=reverse, hidden=True)
                before = copy.deepcopy(content)
                err = refused(dict(EDIT), content)
                self.assertEqual((err.kind, err.reply), ("question", HIDDEN))
                self.assertEqual(content, before)
                self.assertIs(content.makers["River Farm"]["hidden"], True)
                self.assertNotIn("hidden", content.makers["Meadow Farm"])

    def test_permutation_does_not_change_duplicate_outcome(self):
        for hidden, text in ((False, VISIBLE), (True, HIDDEN)):
            outcomes = set()
            for reverse in (False, True):
                content, _ = reachable(reverse=reverse, hidden=hidden)
                err = refused(dict(EDIT), content)
                outcomes.add((err.kind, err.reply))
            self.assertEqual(outcomes, {("question", text)})

    def test_normalized_self_key_cannot_mask_normalized_other_name(self):
        for reverse in (False, True):
            makers = {"Cafe Oneil": record("Cafe Pantry"), "River": record("Caf\u00e9 O'Neil")}
            if reverse:
                makers = dict(reversed(list(makers.items())))
            content = Content([], makers, {}, {})
            for offered in ("CAFE   ONEIL", "Caf\u00e9 O\u2019Neil"):
                with self.subTest(reverse=reverse, offered=offered):
                    err = refused({"maker": "Cafe Oneil", "name": offered}, content)
                    self.assertEqual(err.reply, "Caf\u00e9 O'Neil is already on the site. Do you want to change it instead?")

    def test_self_only_old_key_rename_remains_valid(self):
        content, _ = reachable()
        del content.makers["River Farm"]
        before = copy.deepcopy(content)
        plan = m.plan_edit(dict(EDIT), ctx(content))
        self.assertEqual(plan, [{"op": "maker.edit", "args": {"key": "Meadow Farm", "name": "Meadow Farm"}}])
        self.assertEqual(content, before)

    def test_other_field_noop_and_absent_context_controls(self):
        content, _ = reachable()
        del content.makers["River Farm"]
        # same name as now: still the unchanged reply
        self.assertEqual(refused({"maker": "Meadow Farm", "name": "Meadow Pantry"}, content).reply,
                         "Meadow Pantry already says that. I haven't changed anything.")
        # same name plus a real story edit keeps only the story
        plan = m.plan_edit({"maker": "Meadow Farm", "name": "Meadow Pantry", "story": "Jams made by hand."}, ctx(content))
        self.assertEqual(plan[0]["args"].keys(), {"key", "story"})
        # an ordinary distinct rename works
        self.assertEqual(m.plan_edit({"maker": "Meadow Farm", "name": "Hilltop Pantry"}, ctx(content)),
                         [{"op": "maker.edit", "args": {"key": "Meadow Farm", "name": "Hilltop Pantry"}}])
        # no content: nothing to compare with
        self.assertIsNone(m.rule_maker_twin(None, "Meadow Farm", own_key="Meadow Farm"))
        # add still rejects an existing normalized key or name
        full, _ = reachable()
        for name in ("meadow  FARM", "river farm"):
            with self.assertRaises(m.Refusal):
                m.describe_add({"name": name, "place": "Cambria, California"}, ctx(full))

    def test_reachable_setup_and_lower_guard_remain_real(self):
        content, ops = reachable()
        problems = []
        validate_makers(problems, content.makers)
        self.assertEqual(problems, [])
        result = catalog._maker_edit(copy.deepcopy(content), {"key": "Meadow Farm", "name": "Meadow Farm"}, ops)
        self.assertIsInstance(result, catalog.Refused)
        self.assertIn("River Farm already has this name", result.reason)

    def test_calls_are_pure_and_existing_metadata_unchanged(self):
        content, _ = reachable()
        before = copy.deepcopy(content)
        slots = dict(EDIT)
        for _ in range(2):
            self.assertEqual(refused(slots, content).reply, VISIBLE)
        self.assertEqual(content, before)
        self.assertEqual(slots, EDIT)
        self.assertEqual(m.rule_maker_twin.__name__, "rule_maker_twin")
        self.assertIn("maker-twin", {r for s in m.SKILLS if s.name == "maker.edit" for r in s.rules})


if __name__ == "__main__":
    unittest.main()
