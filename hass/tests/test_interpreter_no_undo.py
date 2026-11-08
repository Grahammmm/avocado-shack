"""AV0007-02 tests: the interpreter is never offered history.revert and cannot draft it; command undo still works.

Pure prompt/check tests plus fixture conversations (fake interpreter and previewer, temp Git/state repos, no model).
Run: python3 -B -m unittest hass.tests.test_interpreter_no_undo
"""

import unittest
from unittest import mock

from hass import conversation, interpret_check
from hass.editor import MAX_OPS
from hass.interpreter_prompt import build
from hass.ops import load_registry
from hass.tests.test_conversation import _ops
from hass.tests.test_editor import DESC, HOURS
from hass.tests.test_interpreter_prompt import _noop, _section, tiny_content
from hass.tests.test_undo import H06TestCase
from hass.ops import Arg, Op

GUIDE = ("To undo a change, send undo for the latest change, undo <code> for a specific change, "
         "or history to see recent changes.")
OPS_HEADER = "Operations (name(arg: kind[, required][, one of ...][, >= n]; ...)):"
REVERT = Op("history.revert", {"changeId": Arg("id")}, _noop)
OTHER = Op("history.show", {"changeId": Arg("id")}, _noop)
EDIT = Op("test.edit", {"id": Arg("id")}, _noop)
REG = {op.name: op for op in (REVERT, OTHER, EDIT)}


def call(op, **args):
    return {"op": op, "args": args}


def result(*calls, revises=None):
    return {"ops": list(calls), "revises": revises}


def edit(n=0):
    return call("test.edit", id=f"p{n}")


def rev(**args):
    return call("history.revert", **args)


class PromptTests(unittest.TestCase):
    def names(self, registry):
        lines = _section(build(registry, tiny_content()), OPS_HEADER)
        return lines if lines == ["(none)"] else [line.split("(", 1)[0] for line in lines]

    def test_operations_excludes_only_history_revert(self):
        registry = load_registry()
        snapshot = dict(registry)
        self.assertIn("history.revert", registry)
        names = self.names(registry)
        self.assertEqual(names, sorted(k for k in snapshot if k != "history.revert"))
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(registry, snapshot)

    def test_only_revert_registry_renders_none(self):
        self.assertEqual(self.names({}), ["(none)"])
        self.assertEqual(self.names({"history.revert": REVERT}), ["(none)"])
        self.assertEqual(self.names(REG), ["history.show", "test.edit"])


class CheckTests(unittest.TestCase):
    def check(self, res, pending=()):
        return interpret_check.check(res, REG, pending)

    def test_interpreter_revert_has_fixed_guidance(self):
        for args in ({"changeId": "c1"}, {"changeId": "nobody-knows"}, {"changeId": "x\"; DROP\n<b>"}, {},
                     {"changeId": "c1", "extra": 1}, {"changeId": 7}):
            with self.subTest(args=args):
                res = result(call("history.revert", **args))
                before = repr(res)
                self.assertEqual(self.check(res), {"question": GUIDE})
                self.assertEqual(repr(res), before)
        self.assertEqual(interpret_check.check(result(rev(changeId="c1")), {}, ()), {"question": GUIDE})

    def test_mixed_revert_rejects_whole_result(self):
        cases = [[rev(changeId="c"), edit(1)], [edit(1), rev(changeId="c"), edit(2)], [edit(1), rev(changeId="c")],
                 [call("nope"), rev(changeId="c")], [rev(changeId="c"), rev(changeId="c")]]
        for calls in cases:
            with self.subTest(n=len(calls)):
                self.assertEqual(self.check(result(*calls)), {"question": GUIDE})
        self.assertEqual(self.check(result(edit(1), rev(changeId="c"), revises="zzzz")), {"question": GUIDE})

    def test_count_and_shape_precede_undo(self):
        ok = [edit(n) for n in range(MAX_OPS - 1)] + [rev(changeId="c")]
        self.assertEqual(self.check(result(*ok)), {"question": GUIDE})
        too_many = self.check(result(*ok, edit(99)))["question"]
        self.assertIn(f"{MAX_OPS + 1} changes", too_many)
        self.assertNotEqual(too_many, GUIDE)
        bad = self.check(result(rev(changeId="c"), {"op": "test.edit"}))["question"]
        self.assertTrue(bad.startswith("I could not read change 2"), bad)

    def test_question_unsupported_and_normal_changes_unchanged(self):
        for res in ({"question": "q?"}, {"unsupported": "no"}):
            self.assertIs(self.check(res), res)
        fine = result(edit(1), call("history.show", changeId="c"))
        self.assertIs(self.check(fine), fine)
        for name in ("history.revert2", "history.reverted", "History.revert", "history.revert "):
            with self.subTest(name=name):
                question = self.check(result(call(name, changeId="c")))["question"]
                self.assertIn("unknown change type", question)
        self.assertEqual(self.check(result(edit(1), edit(1)))["question"].split(".")[0],
                         "Two of those changes are the same")
        self.assertIn("could not find draft", self.check(result(edit(1), revises="zzzz"))["question"])


class ConversationTests(H06TestCase):
    def test_model_undo_never_calls_prepare_or_writes_draft(self):
        hours = _ops((HOURS, {"hours": ["Mon 9-5"]}))
        revert = _ops(("history.revert", {"changeId": "abc"}))
        sibling = {"ops": revert["ops"] + hours["ops"], "revises": None}
        self.interp.mapping["undo the hours change"] = revert
        self.interp.mapping["undo and set hours"] = sibling
        with mock.patch.object(self.editor, "prepare", side_effect=AssertionError("prepare called")):
            self.assertEqual(self.say("undo the hours change"), "question")
            self.assertEqual(self.replies(), [GUIDE])
            self.assertEqual((self.drafts(), self.commits()), ([], 0))
            self.assertEqual(self.say("undo and set hours"), "question")
            self.assertEqual(self.replies(), [GUIDE])
            self.assertEqual((self.drafts(), self.commits()), ([], 0))
        draft, _ = self.propose("desc")
        with mock.patch.object(self.editor, "prepare", side_effect=AssertionError("prepare called")):
            self.assertEqual(self.say("undo the hours change"), "question")
            self.assertEqual(self.replies(), [GUIDE])
        self.assertEqual([(d["code"], d["state"]) for d in self.drafts()], [(draft["code"], "proposed")])
        self.assertEqual(self.commits(), 0)

    def test_command_undo_still_proposes_and_requires_yes(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                before = self.commits()
                a = self.apply("desc")
                self.assertEqual(self.say("history"), "history")
                self.replies()
                self.assertEqual(self.say(f"undo {a['code']}" if explicit else "undo"), "proposed")
                [reply] = self.sent()
                self.assertIn(f"Undo {a['code']}:", reply["text"])
                self.assertEqual(self.commits(), before + 1)  # nothing written by the undo proposal
                self.assertEqual(self.say("yes"), "approved")
                self.sent()
                self.assertEqual(self.commits(), before + 2)
                self.assertNotEqual(self.product("photo-product-001")["description"], "Ripe and creamy.")


if __name__ == "__main__":
    unittest.main()
