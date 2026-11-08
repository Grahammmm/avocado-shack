"""RF1050-7 tests: two changes that differ only in spacing inside string arguments are the same change.

The repeat key folds every string (also inside lists) to single spaces; case, non-string values and the op name are
compared exactly, and the result passed on keeps the owner's original text.
Run: python3 -m unittest hass.tests.test_interpret_check_spacing -v
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
    return {"question": "Two of those changes are the same. Did you mean to change something else?"}


class SpacingRepeatTests(unittest.TestCase):
    def assertNotRepeat(self, ops):
        self.assertNotIn("are the same", ask(ops).get("question", ""))

    def test_spacing_only_variant_is_a_repeat(self):
        for op in ("product.edit", "product.update"):  # a real op and the spec's (unknown) op name
            with self.subTest(op=op):
                self.assertEqual(ask([call(op, id="p1", name="Sea Salt"), call(op, id="p1", name=" Sea  Salt ")]),
                                 same(1, 2))
        tabs = [call("product.edit", id="p1", description="From\tFallbrook.\n"), call("product.edit", id="p1",
                                                                                       description="From Fallbrook.")]
        self.assertEqual(ask(tabs), same(1, 2))
        self.assertEqual(ask([call("product.edit", id=" p1", name="Hass"), call("product.edit", id="p1", name="Hass")]),
                         same(1, 2))

    def test_case_change_is_a_real_change(self):
        self.assertNotRepeat([call("product.edit", id="p1", name="Sea Salt"), call("product.edit", id="p1", name="sea salt")])
        self.assertNotRepeat([call("product.edit", id="p1", name=" Sea  Salt "), call("product.edit", id="p1", name="SEA SALT")])

    def test_text_list_items_are_folded_but_list_shape_is_kept(self):
        self.assertEqual(ask([call("store.set_hours", hours=["a b"]), call("store.set_hours", hours=["a  b"])]), same(1, 2))
        self.assertEqual(ask([call("store.set_hours", hours=[" 9-5", "10-4 "]), call("store.set_hours", hours=["9-5", "10-4"])]),
                         same(1, 2))
        self.assertNotRepeat([call("store.set_hours", hours=["a"]), call("store.set_hours", hours=["a", "a"])])
        self.assertNotRepeat([call("store.set_hours", hours=["a b"]), call("store.set_hours", hours=["a", "b"])])
        self.assertNotRepeat([call("store.set_hours", hours=["ab"]), call("store.set_hours", hours=["a b"])])

    def test_non_string_values_are_compared_exactly(self):
        self.assertEqual(ask([call("hike.update", id="h1", capacity=10)] * 2), same(1, 2))
        self.assertNotRepeat([call("hike.update", id="h1", capacity=10), call("hike.update", id="h1", capacity="10")])
        self.assertNotRepeat([call("hike.update", id="h1", rsvpEnabled=True), call("hike.update", id="h1", rsvpEnabled=1)])
        self.assertNotRepeat([call("hike.update", id="h1", capacity=10), call("hike.update", id="h1", capacity=" 10 ")])

    def test_op_name_is_compared_exactly(self):
        self.assertNotRepeat([call("product.hide", id="p1"), call(" product.hide", id="p1")])

    def test_spacing_variant_of_unknown_op_is_still_a_repeat(self):
        self.assertEqual(ask([call("product.colour", id="p1", colour="dark green"),
                              call("product.colour", id="p1", colour="dark   green")]), same(1, 2))
        self.assertEqual(ask([call("product.edit", id="p1", colour="green "), call("product.edit", id="p1", colour="green")],
                             revises="dead"), same(1, 2))

    def test_passed_through_result_keeps_original_spacing(self):
        result = {"ops": [call("product.edit", id="p1", name="  Sea  Salt "), call("store.set_hours", hours=["9 -  5"])],
                  "revises": None}
        before = copy.deepcopy(result)
        self.assertIs(interpret_check.check(result, REGISTRY, ()), result)
        self.assertEqual(result, before)

    def test_self_containing_list_never_raises_or_repeats(self):
        loop = []
        loop.append(loop)
        out = ask([call("store.set_hours", hours=loop)] * 2)
        self.assertNotIn("are the same", out["question"])


if __name__ == "__main__":
    unittest.main()
