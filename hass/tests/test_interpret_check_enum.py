"""AV0222-02: an enum value the op does not allow is asked about in site words before the editor.

Run: python3 -m unittest hass.tests.test_interpret_check_enum -v
"""

import unittest

from hass import interpret_check
from hass.content_model import AVAILABILITY, CATEGORIES
from hass.ops import Arg, Op, load_registry
from hass.tests.test_conversation import ConversationTestCase, _ops

REGISTRY = load_registry()
AGAIN = interpret_check.AGAIN
SHELVES = "There is no {} shelf. Which shelf: Fruit, Vegetables, Dairy & cheese, Eggs, Meat, Pantry, Drinks & coffee, Bread or Flowers?"
AVAIL = "Should it say Available today, Limited or Sold out?"
HOURS = {"op": "store.set_hours", "args": {"hours": ["Daily 8am"]}}


def ask(ops, registry=REGISTRY, revises=None, pending=()):
    return interpret_check.check({"ops": ops, "revises": revises}, registry, pending)


def call(op, **args):
    return {"op": op, "args": args}


def custom(choices):
    return {"x.pick": Op("x.pick", {"colour": Arg("enum", choices=choices)}, lambda *a: None)}


class EnumCheckTests(unittest.TestCase):
    def test_invalid_canonical_enums_use_exact_site_questions(self):
        for op in ("product.add", "product.edit"):
            args = {"name": "Jam", "category": "snacks"} if op == "product.add" else {"id": "p1", "category": "snacks"}
            ops = [call(op, **args)]
            self.assertEqual(ask(ops), {"question": SHELVES.format("snacks")})
            self.assertEqual(ops, [call(op, **args)])
        self.assertEqual(ask([call("product.set_availability", id="p1", available="maybe")]), {"question": AVAIL})
        for cat in CATEGORIES:
            r = {"ops": [call("product.edit", id="p1", category=cat)], "revises": None}
            self.assertIs(interpret_check.check(r, REGISTRY, ()), r)
        for av in AVAILABILITY:
            r = {"ops": [call("product.set_availability", id="p1", available=av)], "revises": None}
            self.assertIs(interpret_check.check(r, REGISTRY, ()), r)

    def test_enum_membership_uses_supplied_choices(self):
        r = {"ops": [call("x.pick", colour="red")], "revises": None}
        self.assertIs(interpret_check.check(r, custom(("red", "blue")), ()), r)
        self.assertEqual(ask([call("x.pick", colour="green")], custom(("red", "blue"))),
                         {"question": f"For a detail, I can use: red, blue. {AGAIN}"})
        for none in ((), None):
            self.assertEqual(ask([call("x.pick", colour="red")], custom(none)),
                             {"question": f"x.pick.colour has no available choices. {AGAIN}"})
        narrowed = dict(REGISTRY)
        narrowed["product.edit"] = Op("product.edit", {"category": Arg("enum", choices=("fruit", "eggs"))}, lambda *a: None)
        q = ask([call("product.edit", category="meat")], narrowed)["question"]
        self.assertEqual(q, f"product.edit.category should be one of: fruit, eggs. {AGAIN}")
        self.assertNotIn("Flowers", q)

    def test_enum_types_and_no_normalization(self):
        for bad in (None, True, 3, ["fruit"]):
            self.assertEqual(ask([call("product.edit", id="p1", category=bad)]),
                             {"question": f"I need the shelf as words. {AGAIN}"})
        for bad in ("Fruit", " fruit", "fruit ", ""):
            q = ask([call("product.edit", id="p1", category=bad)])["question"]
            self.assertTrue(q.startswith("There is no "), q)
        self.assertIn("ops", ask([call("product.edit", id="p1", name="Hass")]))

    def test_shelf_echo_is_clean_and_bounded(self):
        q = ask([call("product.edit", id="p1", category="sn\x00a\u200bck\u2028s")])["question"]
        self.assertEqual(q, SHELVES.format("snacks"))
        self.assertEqual(ask([call("product.edit", id="p1", category="\u200b\x01")])["question"], SHELVES.format("(unnamed)"))
        q = ask([call("product.edit", id="p1", category="x" * 100)])["question"]
        self.assertEqual(q, SHELVES.format("x" * 37 + "..."))
        self.assertEqual(ask([call("product.set_availability", id="p1", available="secret\x00")])["question"], AVAIL)

    def test_ordering_and_atomic_mixed_calls(self):
        bad = call("product.edit", id="p1", category="snacks")
        for ops in ([bad, HOURS], [HOURS, bad], [HOURS, bad, call("hike.update", id="h1")]):
            self.assertEqual(ask(ops), {"question": SHELVES.format("snacks")})
        self.assertEqual(ask([bad, call("product.set_availability", id="p1", available="maybe")]),
                         {"question": SHELVES.format("snacks")})
        self.assertIn("are the same", ask([bad, bad])["question"])
        self.assertIn("unknown field", ask([call("product.edit", id="p1", colour="x"), bad])["question"])
        self.assertIn("draft beef waiting", ask([call("product.edit", id="p1", name="Hass")], revises="beef")["question"])
        self.assertEqual(ask([bad], revises="beef"), {"question": SHELVES.format("snacks")})  # fields before revises
        self.assertEqual(ask([bad, call("history.revert", change="chg-000000000000")])["question"],
                         interpret_check.UNDO_GUIDANCE)


class EnumConversationTests(ConversationTestCase):
    def test_enum_question_never_prepares_or_changes_pending(self):
        from unittest import mock
        self.editor = __import__("hass.conversation", fromlist=["Editor"]).Editor(self.repo.state)
        self.conv = self.open()
        self.interp.mapping["bad"] = _ops(("product.edit", {"id": "photo-product-001", "category": "snacks"}))
        with mock.patch.object(self.editor, "prepare", wraps=self.editor.prepare) as spy:
            self.assertEqual(self.say("bad"), "question")
            self.assertEqual(self.replies(), [SHELVES.format("snacks")])
            self.assertEqual(spy.call_count, 0)
        self.assertEqual((self.drafts(), self.commits()), ([], 0))
        self.interp.mapping["set hours"] = _ops(("store.set_hours", {"hours": ["Daily 8am–7pm"]}))
        self.assertEqual(self.say("set hours"), "proposed")
        self.replies()
        [before] = self.drafts()
        self.interp.mapping["bad2"] = _ops(("product.set_availability", {"id": "photo-product-001", "available": "maybe"}))
        self.assertEqual(self.say("bad2"), "question")
        self.assertEqual(self.replies(), [AVAIL])
        self.assertEqual(self.drafts(), [before])
        self.assertEqual(self.commits(), 0)


if __name__ == "__main__":
    unittest.main()
