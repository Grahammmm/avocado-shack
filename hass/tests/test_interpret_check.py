"""NB-AV-01 tests: interpreter output checked against the ops registry before the editor sees it.

The pure check runs against the production registry; the conversation tests reuse the H05 fixture conversation
(ConversationTestCase) with the production registry or the test-only fixture ops.
Run: python3 -m unittest hass.tests.test_interpret_check -v
"""

import unittest

from hass import conversation, interpret_check
from hass.ops import load_registry
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, _req

REGISTRY = load_registry()
AGAIN = interpret_check.AGAIN


def ask(ops, revises=None, pending=()):
    return interpret_check.check({"ops": ops, "revises": revises}, REGISTRY, pending)


def call(op, **args):
    return {"op": op, "args": args}


class CheckTests(unittest.TestCase):
    def assertAsks(self, out, *parts):
        self.assertEqual(set(out), {"question"}, out)
        for part in parts: self.assertIn(part, out["question"])

    def test_valid_result_is_returned_unchanged(self):
        result = {"ops": [call("hike.update", id="h1", capacity=10, rsvpEnabled=True)], "revises": "beef"}
        self.assertIs(interpret_check.check(result, REGISTRY, {"beef"}), result)
        for passthrough in ({"question": "Which day?"}, {"unsupported": "Sorry."}):
            self.assertIs(interpret_check.check(passthrough, REGISTRY, ()), passthrough)

    def test_unknown_op_and_unknown_argument_are_named(self):
        self.assertEqual(ask([call("product.colour", id="p1")]), {"question": (
            f'I could not turn that into a change I know (unknown change type "product.colour"). {AGAIN}')})
        self.assertAsks(ask([call("product.edit", id="p1", colour="green")]), '"product.edit.colour"', AGAIN)
        # a later call is checked too: the first problem wins, in call order
        self.assertAsks(ask([call("product.edit", id="p1"), call("hike.nope")]), '"hike.nope"')

    def test_wrong_kind_names_the_field(self):
        cases = [(call("hike.update", id="h1", capacity="ten"), "hike.update.capacity should be a whole number"),
                 (call("hike.update", id="h1", capacity=True), "hike.update.capacity should be a whole number"),
                 (call("hike.update", id="h1", capacity=2.5), "hike.update.capacity should be a whole number"),
                 (call("hike.update", id="h1", rsvpEnabled="yes"), "hike.update.rsvpEnabled should be a yes/no"),
                 (call("hike.update", id="h1", rsvpEnabled=1), "hike.update.rsvpEnabled should be a yes/no"),
                 (call("store.set_hours", hours="9-5 daily"), "store.set_hours.hours should be a list of text"),
                 (call("store.set_hours", hours=["9-5", 7]), "store.set_hours.hours should be a list of text"),
                 (call("product.edit", id=7), "product.edit.id should be text"),
                 (call("product.edit", id="p1", producerKey=None), "product.edit.producerKey should be text")]
        for bad, text in cases:
            with self.subTest(bad=bad):
                self.assertEqual(ask([bad]), {"question": f"{text}. {AGAIN}"})
        self.assertIsNot(ask([call("hike.update", id="h1", capacity=0, rsvpEnabled=False)]).get("ops"), None)

    def test_revises_must_name_a_waiting_draft(self):
        ops = [call("store.set_hours", hours=["9-5"])]
        self.assertEqual(ask(ops, "beef"), {"question": "I could not find draft beef waiting; reply with the change again."})
        self.assertAsks(ask(ops, "beef", {"cafe", "beefcafe"}), "draft beef waiting")
        self.assertIn("ops", ask(ops, "beef", {"beef"}))
        self.assertIn("ops", ask(ops, None, ()))

    def test_empty_ops_and_bad_call_shapes(self):
        self.assertEqual(ask([]), {"question": "I did not find a change in that message. What would you like to change?"})
        for bad in ({"op": "product.edit", "args": {"id": "p1"}, "why": "owner asked"}, {"op": "product.edit"},
                    {"op": 3, "args": {}}, {"op": "product.edit", "args": ["id"]}, "product.edit", None):
            with self.subTest(bad=bad):
                self.assertEqual(ask([call("product.edit", id="p1"), bad]),
                                 {"question": f"I could not read change 2 of that message. {AGAIN}"})

    def test_long_name_with_control_characters_is_cut_and_cleaned(self):
        name = "x" * 250 + "\n\r\t\x1b\x7f\x85" + "y" * 244
        for out in (ask([call(name)]), ask([call("product.edit", **{name: "v"})]),
                    ask([call("store.set_hours", hours=["ok"])], revises=name)):
            text = out["question"]
            self.assertLessEqual(len(text), 200, text)
            self.assertFalse(any(ord(c) < 32 or 127 <= ord(c) < 160 for c in text), repr(text))
            self.assertIn("xxx...", text)


class ProductionConversationTests(ConversationTestCase):
    """The production registry (editor registry None), as the live conversation runs."""

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def asked(self, text, mapping):
        self.interp.mapping[text] = mapping
        self.assertEqual(self.say(text), "question")
        [reply] = self.replies()
        disposition = self.conv.db.execute("SELECT disposition FROM messages WHERE provider_id = ?",
                                           (f"m{self.n}",)).fetchone()[0]
        self.assertEqual(disposition, "question")
        self.assertEqual((self.drafts(), sorted((self.repo.state / "drafts").glob("*.json"))), ([], []))
        return reply

    def test_registry_problems_ask_before_any_draft(self):
        self.assertIn('"product.colour"', self.asked("colour", _ops(("product.colour", {"id": "photo-product-001"}))))
        self.assertIn('"product.edit.colour"', self.asked("edit", _ops(("product.edit", {"id": "photo-product-001",
                                                                                         "colour": "green"}))))
        self.assertIn("hike.update.capacity should be a whole number",
                      self.asked("cap", _ops(("hike.update", {"id": "h1", "capacity": "ten"}))))
        self.assertIn("did not find a change", self.asked("empty", {"ops": [], "revises": None}))
        self.assertIn("draft beef waiting", self.asked("rev", {**_ops(("product.edit", {"id": "photo-product-001",
                                                                                        "name": "Hass"})),
                                                               "revises": "beef"}))
        self.assertEqual(self.commits(), 0)

    def test_value_problems_still_reach_the_editor(self):
        self.interp.mapping["maker"] = _ops(("product.edit", {"id": "photo-product-001", "producerKey": "no-such-maker"}))
        self.assertEqual(self.say("maker"), "not-drafted")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Not drafted: "), reply)
        self.assertIn("producerKey", reply)


class FixtureConversationTests(ConversationTestCase):
    def test_waiting_needs_details_code_still_fills(self):
        self.interp.mapping["start"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}
        self.assertEqual(self.say("start"), "needs-details")
        self.replies()
        [pending] = self.drafts()
        self.interp.mapping["stale"] = {**_ops((HOURS, {"hours": ["Daily 8am–7pm"]})), "revises": "beef"}
        self.assertEqual(self.say("stale"), "question")
        self.assertEqual(self.replies(), ["I could not find draft beef waiting; reply with the change again."])
        self.interp.mapping["done"] = {**_ops((HOURS, {"hours": ["Daily 8am–7pm"]})), "revises": pending["code"]}
        self.assertEqual(self.say("done"), "proposed")
        self.replies()
        [filled] = self.drafts()
        self.assertEqual((filled["row_id"], filled["code"], filled["state"]), (pending["row_id"], pending["code"],
                                                                               "proposed"))

    def test_test_registry_is_the_one_checked(self):
        self.interp.mapping["prod"] = _ops(("product.edit", {"id": "photo-product-001", "name": "Hass"}))
        self.assertEqual(self.say("prod"), "question")
        self.assertIn('"product.edit"', self.replies()[0])


if __name__ == "__main__":
    unittest.main()
