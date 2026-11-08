"""RF2030-7 tests: an interpreter answer with more than MAX_OPS changes becomes one plain owner question.

The count is checked right after the empty check, before shapes, repeats, op/field kinds and the revises code, so
nothing reaches the editor and no draft is kept. Exactly MAX_OPS changes still pass.
Run: python3 -m unittest hass.tests.test_interpret_check_count -v
"""

import copy
import unittest
from unittest import mock

from hass import conversation, editor, interpret_check, interpreter_prompt
from hass.ops import load_registry
from hass.tests.test_conversation import ConversationTestCase

REGISTRY = load_registry()


def hides(n):
    return [{"op": "product.hide", "args": {"id": f"p{i}"}} for i in range(1, n + 1)]


def too_many(n):
    return {"question": f"That is {n} changes in one message; I can take at most 20 at a time. "
                        "Please send them in smaller groups."}


def ask(ops, revises=None, pending=()):
    return interpret_check.check({"ops": ops, "revises": revises}, REGISTRY, pending)


class CountTests(unittest.TestCase):
    def test_twenty_valid_ops_pass_unchanged(self):
        result = {"ops": hides(20), "revises": None}
        before = copy.deepcopy(result)
        self.assertIs(interpret_check.check(result, REGISTRY, ()), result)
        self.assertEqual(result, before)

    def test_twenty_one_valid_ops_ask_to_split(self):
        self.assertEqual(ask(hides(21)), too_many(21))
        self.assertEqual(ask(hides(40)), too_many(40))

    def test_count_is_checked_before_shape_repeat_and_kind(self):
        ops = hides(21)
        ops[2] = {"op": "product.hide"}  # malformed change 3
        self.assertEqual(ask(ops), too_many(21))
        self.assertEqual(ask(hides(20) + [{"op": "product.hide", "args": {"id": "p1"}}]), too_many(21))  # repeat
        self.assertEqual(ask(hides(20) + [{"op": "product.colour", "args": {"id": "p9"}}]), too_many(21))  # unknown
        self.assertEqual(ask(hides(20) + [{"op": 7, "args": []}]), too_many(21))

    def test_count_wins_over_a_revises_code_not_waiting(self):
        self.assertEqual(ask(hides(25), revises="dead"), too_many(25))
        self.assertEqual(ask(hides(25), revises="beef", pending={"beef"}), too_many(25))

    def test_under_the_limit_other_questions_unchanged(self):
        self.assertEqual(ask(hides(20), revises="dead"),
                         {"question": "I can't find that change any more. Could you tell me the change again?"})
        self.assertIn("did not find a change", ask([])["question"])

    def test_prompt_limit_matches_editor_limit(self):
        self.assertEqual(interpreter_prompt.MAX_OPS, editor.MAX_OPS)
        self.assertIs(interpret_check.MAX_OPS, editor.MAX_OPS)
        self.assertEqual(editor.MAX_OPS, 20)

    def test_question_and_unsupported_pass_through(self):
        for passthrough in ({"question": "Which day?"}, {"unsupported": "Sorry."}):
            self.assertIs(interpret_check.check(passthrough, REGISTRY, ()), passthrough)


class ConversationCountTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def test_twenty_one_ops_reply_the_count_question_and_draft_nothing(self):
        self.interp.mapping["long list"] = {"ops": hides(21), "revises": None}
        with mock.patch.object(self.editor, "prepare", wraps=self.editor.prepare) as prepare:
            self.assertEqual(self.say("long list"), "question")
        prepare.assert_not_called()
        self.assertEqual(self.replies(), [too_many(21)["question"]])
        self.assertEqual((self.drafts(), sorted((self.repo.state / "drafts").glob("*.json"))), ([], []))
        disposition = self.conv.db.execute("SELECT disposition FROM messages WHERE provider_id = ?",
                                           (f"m{self.n}",)).fetchone()[0]
        self.assertEqual(disposition, "question")
        self.assertEqual(self.commits(), 0)

    def test_twenty_ops_still_reach_the_editor(self):
        self.interp.mapping["twenty"] = {"ops": hides(20), "revises": None}
        with mock.patch.object(self.editor, "prepare", wraps=self.editor.prepare) as prepare:
            self.say("twenty")
        prepare.assert_called_once()
        self.assertFalse(any("smaller groups" in r for r in self.replies()))


if __name__ == "__main__":
    unittest.main()
