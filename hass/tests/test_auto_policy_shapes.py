"""RF0140-1 acceptance: the H23 policy fails closed on malformed input and never raises."""

import unittest

from hass.auto_policy import ELIGIBLE, check_opt_in, qualifies

ALL = list(ELIGIBLE)
AVAIL = {"op": "product.set_availability", "args": {"id": "photo-product-001", "available": "yes"}}
UNREADABLE = (False, "draft unreadable")


def _sel(**args):
    return {"op": "store.confirm_selection", "args": args}


def _ids(n, start=0):
    return [f"photo-product-{i:03d}" for i in range(start, start + n)]


class DraftShapeTest(unittest.TestCase):
    def test_draft_not_a_list_is_unreadable(self):
        for ops in (None, AVAIL, {"op": "x"}, "product.set_availability", "", 1, 0):
            with self.subTest(ops=ops):
                self.assertEqual(qualifies(ops, ALL, False), UNREADABLE)

    def test_tuple_draft_still_works(self):
        self.assertEqual(qualifies((AVAIL,), ALL, False), (True, "opted in"))
        self.assertEqual(qualifies((), ALL, False), (False, "no change"))


class OptInShapeTest(unittest.TestCase):
    def test_opt_in_not_a_list_of_names_is_unreadable(self):
        bad = ("product.set_availability,store.confirm_selection", "product.set_availability", None,
               {"product.set_availability": True}, [1], ["product.set_availability", None], 5)
        for opted_in in bad:
            with self.subTest(opted_in=opted_in):
                self.assertEqual(qualifies([AVAIL], opted_in, False), (False, "opt-in list unreadable"))
                self.assertEqual(qualifies([_sel()], opted_in, False), (False, "opt-in list unreadable"))

    def test_set_frozenset_tuple_still_qualify(self):
        for opted_in in (set(ALL), frozenset(ALL), tuple(ALL), ["product.set_availability"]):
            with self.subTest(opted_in=opted_in):
                self.assertEqual(qualifies([AVAIL], opted_in, False), (True, "opted in"))
        self.assertEqual(qualifies([AVAIL], frozenset(["store.confirm_selection"]), False), (False, "not opted in"))


class PauseShapeTest(unittest.TestCase):
    def test_only_false_lets_the_rules_run(self):
        for paused in (None, 0, "false", "", 1, True, [], "no"):
            with self.subTest(paused=paused):
                self.assertEqual(qualifies([AVAIL], ALL, paused), (False, "changes are paused"))
        self.assertEqual(qualifies([AVAIL], ALL, False), (True, "opted in"))

    def test_pause_wins_over_every_malformed_input(self):
        self.assertEqual(qualifies(None, "x", True), (False, "changes are paused"))
        self.assertEqual(qualifies({"op": 1}, None, None), (False, "changes are paused"))
        self.assertEqual(qualifies([_sel(yes="pid")], [1], 0), (False, "changes are paused"))

    def test_draft_checked_before_opt_in(self):
        self.assertEqual(qualifies(None, "x", False), UNREADABLE)


class SelectionShapeTest(unittest.TestCase):
    def test_misshaped_selection_is_unreadable(self):
        drafts = [{"op": "store.confirm_selection", "args": a} for a in (None, [], "yes", 3)]
        drafts.append({"op": "store.confirm_selection"})
        drafts += [_sel(yes="pid"), _sel(no=["a", 3]), _sel(limited=None), _sel(yes={"a": 1}),
                   _sel(yes=["a"], limited=[["b"]]), _sel(yes=_ids(30), no="x")]
        for call in drafts:
            with self.subTest(call=call):
                self.assertEqual(qualifies([call], ALL, False), UNREADABLE)

    def test_product_cap_unchanged(self):
        ok = _sel(yes=_ids(10), limited=tuple(_ids(7, 10)), no=_ids(3, 17))
        self.assertEqual(qualifies([ok], ALL, False), (True, "opted in"))
        over = _sel(yes=_ids(10), limited=_ids(7, 10), no=_ids(4, 17))
        self.assertEqual(qualifies([over], ALL, False), (False, "too many products at once"))
        self.assertEqual(qualifies([_sel(yes=_ids(20), other=5)], ALL, False), (True, "opted in"))
        self.assertEqual(qualifies([_sel()], ALL, False), (True, "opted in"))

    def test_selection_not_opted_in_is_not_inspected(self):
        self.assertEqual(qualifies([_sel(yes="pid")], ["product.set_availability"], False), (False, "not opted in"))


class CheckOptInShapeTest(unittest.TestCase):
    def test_non_list_gives_one_problem(self):
        for names in ("product.set_availability", None, set(ALL), {"a": 1}, 7, b"x"):
            with self.subTest(names=names):
                self.assertEqual(check_opt_in(names), ["opt-in list is not a list"])

    def test_lists_and_tuples_report_as_before(self):
        self.assertEqual(check_opt_in(tuple(ALL)), [])
        problems = check_opt_in(("product.hide", "store.confirm_selection", "store.confirm_selection", None))
        self.assertEqual(problems, ["product.hide cannot be automatic", "store.confirm_selection is listed twice",
                                    "None is not a name"])


if __name__ == "__main__":
    unittest.main()
