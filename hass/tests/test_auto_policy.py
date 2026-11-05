"""H23 acceptance: the unwired opt-in policy is closed by default."""

import subprocess
import unittest
from pathlib import Path

from hass import auto_policy
from hass.auto_policy import ELIGIBLE, check_opt_in, qualifies
from hass.ops import load_registry

ROOT = Path(__file__).resolve().parents[2]
ALL = list(ELIGIBLE)


def _op(name, **args):
    return {"op": name, "args": args}


class QualifiesTest(unittest.TestCase):
    def test_one_opted_in_op_qualifies(self):
        op = _op("product.set_availability", id="photo-product-001", available="yes")
        self.assertEqual(qualifies([op], ALL, False), (True, "opted in"))

    def test_paused_wins_even_when_opted_in(self):
        self.assertEqual(qualifies([_op("product.set_availability")], ALL, True), (False, "changes are paused"))
        self.assertEqual(qualifies([], ALL, True), (False, "changes are paused"))
        self.assertEqual(qualifies([_op("product.hide"), _op("product.hide")], ALL, True),
                         (False, "changes are paused"))

    def test_not_exactly_one_change(self):
        two = [_op("product.set_availability"), _op("store.confirm_selection")]
        self.assertEqual(qualifies(two, ALL, False), (False, "more than one change"))
        self.assertEqual(qualifies([], ALL, False), (False, "no change"))

    def test_not_opted_in(self):
        op = _op("product.set_availability")
        self.assertEqual(qualifies([op], [], False), (False, "not opted in"))
        self.assertEqual(qualifies([op], ["store.confirm_selection"], False), (False, "not opted in"))

    def test_every_other_registry_op_needs_approval(self):
        names = [n for n in load_registry() if n not in ELIGIBLE]
        for name in ("history.revert", "product.hide", "hike.cancel"):
            self.assertIn(name, names)
        for name in names:
            with self.subTest(op=name):
                self.assertEqual(qualifies([_op(name)], names + ALL, False), (False, "needs approval"))
        self.assertEqual(qualifies([{"args": {}}], ALL, False), (False, "needs approval"))
        self.assertEqual(qualifies(["product.set_availability"], ALL, False), (False, "needs approval"))

    def test_eligible_are_real_registry_ops(self):
        self.assertEqual(set(ELIGIBLE) - set(load_registry()), set())

    def test_confirm_selection_product_limit(self):
        def ids(n):
            return [f"photo-product-{i:03d}" for i in range(n)]

        ok = _op("store.confirm_selection", yes=ids(10), limited=ids(7), no=ids(3))
        over = _op("store.confirm_selection", yes=ids(10), limited=ids(7), no=ids(4))
        self.assertEqual(qualifies([ok], ALL, False), (True, "opted in"))
        self.assertEqual(qualifies([over], ALL, False), (False, "too many products at once"))
        self.assertEqual(qualifies([over], [], False), (False, "not opted in"))
        self.assertEqual(qualifies([_op("store.confirm_selection")], ALL, False), (True, "opted in"))


class CheckOptInTest(unittest.TestCase):
    def test_names_each_problem(self):
        problems = check_opt_in(["product.hide", "store.confirm_selection", "store.confirm_selection", 7])
        self.assertEqual(len(problems), 3)
        self.assertTrue(any("product.hide" in p for p in problems))
        self.assertTrue(any("store.confirm_selection" in p and "twice" in p for p in problems))
        self.assertTrue(any("7" in p for p in problems))

    def test_empty_and_valid_have_no_problems(self):
        self.assertEqual(check_opt_in([]), [])
        self.assertEqual(check_opt_in(ALL), [])


class UnwiredTest(unittest.TestCase):
    def test_only_the_module_and_its_test_mention_it(self):
        out = subprocess.run(["git", "grep", "-l", "auto_policy"], cwd=ROOT, capture_output=True, text=True)
        self.assertIn(out.returncode, (0, 1))
        self.assertEqual(out.stdout.split(), ["hass/acceptance.py", "hass/tests/test_acceptance_runner.py",
                                              "hass/tests/test_auto_policy.py",
                                              "hass/tests/test_auto_policy_shapes.py",
                                              "hass/tests/test_clear_availability.py",
                                              "hass/tests/test_maker_hide_products.py"])  # no importer outside tests
        self.assertIn("UNWIRED", auto_policy.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
