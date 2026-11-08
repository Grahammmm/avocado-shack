"""RF1730-3 tests: one interpreter result listing the same change twice becomes one owner question.

Same op and equal args (any key order) is a repeat; the first repeated pair is named (1-based) and nothing is drafted.
Different values for the same item, or JSON-different values (1, 1.0, true), are not repeats.
Run: python3 -m unittest hass.tests.test_interpret_check_repeat -v
"""

import copy
import unittest

from hass import interpret_check
from hass.ops import load_registry

REGISTRY = load_registry()
AGAIN = interpret_check.AGAIN


def ask(ops, revises=None, pending=()):
    return interpret_check.check({"ops": ops, "revises": revises}, REGISTRY, pending)


def call(op, **args):
    return {"op": op, "args": args}


def same(j, i):
    return {"question": f"Changes {j} and {i} in that message are the same. Did you mean to change something else? {AGAIN}"}


class RepeatTests(unittest.TestCase):
    def assertUnchanged(self, result, pending=()):
        before = copy.deepcopy(result)
        self.assertIs(interpret_check.check(result, REGISTRY, pending), result)
        self.assertEqual(result, before)

    def test_two_identical_calls_ask_once(self):
        edit = call("product.edit", id="p1", name="Hass")
        self.assertEqual(ask([edit, copy.deepcopy(edit)]), same(1, 2))
        self.assertEqual(ask([call("hike.update", id="h1", capacity=10)] * 2), same(1, 2))

    def test_key_order_in_args_does_not_matter(self):
        first = {"op": "product.edit", "args": {"id": "p1", "name": "Hass", "description": "From Fallbrook."}}
        second = {"op": "product.edit", "args": {"description": "From Fallbrook.", "name": "Hass", "id": "p1"}}
        self.assertEqual(ask([first, second]), same(1, 2))
        nested = [call("store.set_hours", hours=["9-5", "10-4"]), call("store.set_hours", hours=["9-5", "10-4"])]
        self.assertEqual(ask(nested), same(1, 2))

    def test_repeat_at_one_and_three_names_both(self):
        ops = [call("product.edit", id="p1", name="Hass"), call("product.edit", id="p2", name="Reed"),
               call("product.edit", id="p1", name="Hass")]
        self.assertEqual(ask(ops), same(1, 3))

    def test_two_repeat_pairs_give_only_the_first_pair(self):
        a, b = call("product.hide", id="p1"), call("product.hide", id="p2")
        out = ask([a, b, dict(b), dict(a)])
        self.assertEqual(out, same(2, 3))
        self.assertEqual(out["question"].count("are the same"), 1)
        self.assertEqual(ask([a, b, dict(a), dict(b)]), same(1, 3))
        self.assertEqual(ask([a, dict(a), dict(a)]), same(1, 2))  # three of one change: still one question

    def test_same_item_different_changes_pass_unchanged(self):
        self.assertUnchanged({"ops": [call("product.edit", id="p1", name="Hass"),
                                      call("product.edit", id="p1", name="Reed")], "revises": None})
        self.assertUnchanged({"ops": [call("product.edit", id="p1", name="Hass"),
                                      call("product.edit", id="p1", description="Hass")], "revises": None})
        # same args under a different op are different changes
        self.assertUnchanged({"ops": [call("product.hide", id="p1"), call("product.restore", id="p1")],
                              "revises": None})

    def test_json_different_values_are_not_repeats(self):
        for x, y in ((True, 1), (1, 1.0), (True, 1.0), (0, False), ("1", 1)):
            with self.subTest(x=x, y=y):
                out = ask([call("hike.update", id="h1", rsvpEnabled=x), call("hike.update", id="h1", rsvpEnabled=y)])
                self.assertNotIn("are the same", out.get("question", ""))
        self.assertUnchanged({"ops": [call("hike.update", id="h1", rsvpEnabled=True),
                                      call("hike.update", id="h1", rsvpEnabled=False)], "revises": None})

    def test_malformed_call_before_repeat_wins(self):
        edit = call("product.edit", id="p1", name="Hass")
        self.assertEqual(ask([edit, {"op": "product.edit"}, dict(edit)]),
                         {"question": f"I couldn't read part of that message. {AGAIN}"})
        self.assertEqual(ask([edit, dict(edit), {"op": 3, "args": {}}]),
                         {"question": f"I couldn't read part of that message. {AGAIN}"})

    def test_repeat_is_reported_before_unknown_op_field_and_code(self):
        self.assertEqual(ask([call("product.colour", id="p1")] * 2), same(1, 2))
        self.assertEqual(ask([call("product.edit", id="p1", colour="green")] * 2), same(1, 2))
        self.assertEqual(ask([call("product.edit", id="p1", name="Hass")] * 2, revises="dead"), same(1, 2))

    def test_args_that_cannot_be_compared_never_raise_or_repeat(self):
        odd = object()
        out = ask([call("product.edit", id="p1", name=odd), call("product.edit", id="p1", name=odd)])
        self.assertEqual(out, {"question": f"I need the name as words. {AGAIN}"})
        loop = {}
        loop["self"] = loop
        out = ask([call("product.edit", id="p1", name=loop)] * 2)
        self.assertNotIn("are the same", out["question"])

    def test_single_call_question_and_unsupported_pass_through(self):
        self.assertUnchanged({"ops": [call("product.edit", id="p1", name="Hass")], "revises": None})
        self.assertUnchanged({"ops": [call("store.set_hours", hours=["9-5"])], "revises": "beef"}, {"beef"})
        for passthrough in ({"question": "Which day?"}, {"unsupported": "Sorry."}):
            self.assertIs(interpret_check.check(passthrough, REGISTRY, ()), passthrough)


if __name__ == "__main__":
    unittest.main()
