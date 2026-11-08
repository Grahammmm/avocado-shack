"""AV0222-03: prices and markup in interpreter text arguments get a plain owner reply before the editor.

Run: python3 -m unittest hass.tests.test_interpret_check_prices -v
"""

import unittest

from hass import interpret_check
from hass.content_model import FORBIDDEN_TEXT
from hass.interpreter_prompt import RULES
from hass.ops import load_registry
from hass.tests.test_interpret_check import ProductionConversationTests, ask, call
from hass.tests.test_conversation import _ops

PRICE = interpret_check.PRICE_REPLY
PLAIN = interpret_check.PLAIN_TEXT_REPLY
EDIT = "photo-product-001"


class CheckPriceTests(unittest.TestCase):
    def test_exact_replies(self):
        self.assertEqual(PRICE, "The website doesn't show prices, so I haven't made any change. Could you send it without the price?")
        self.assertEqual(PLAIN, "The website only accepts plain text, so nothing was drafted. "
                                "Send the change without HTML or template marks.")

    def test_dollar_in_text_args_is_the_price_reply(self):
        for op in (call("product.edit", id=EDIT, description="Avocados 2 for $3"),
                   call("product.edit", id=EDIT, name="$5 avocado"),
                   call("store.set_story", text="Everything $1"),
                   call("hike.create", title="Hike $10", date="2026-12-05", time="09:00", meetingPoint="Park")):
            out = ask([op])
            self.assertEqual(out, {"question": PRICE}, op)
            self.assertNotIn("$", out["question"].replace("The website", ""))

    def test_markup_marks_have_the_plain_reply(self):
        for bad in ("<b>", "a > b", "{{x", "x}}", "<b>{{x}}</b>"):
            self.assertEqual(ask([call("product.edit", id=EDIT, description=bad)]), {"question": PLAIN}, bad)

    def test_dollar_wins_over_markup_in_the_same_string(self):
        self.assertEqual(ask([call("product.edit", id=EDIT, description="<b>$3</b>")]), {"question": PRICE})

    def test_text_list_items_in_order(self):
        self.assertEqual(ask([call("hike.update", id="h1", clear=["fine", "cost $4", "<x>"])]), {"question": PRICE})
        self.assertEqual(ask([call("hike.update", id="h1", clear=["fine", "<x>", "$4"])]), {"question": PLAIN})

    def test_later_unsafe_op_blocks_the_whole_request(self):
        out = ask([call("product.edit", id=EDIT, name="Fine"), call("product.edit", id=EDIT, description="$3")])
        self.assertEqual(out, {"question": PRICE})

    def test_safe_results_and_non_text_kinds_pass_unchanged(self):
        result = {"ops": [call("product.edit", id=EDIT, description="Avocados, 2 for 3 - sweet"),
                          call("hike.update", id="h1", clear=["a", "b"])], "revises": None}
        self.assertIs(interpret_check.check(result, load_registry(), ()), result)
        question = {"question": "Which one? $"}
        self.assertIs(interpret_check.check(question, load_registry(), ()), question)

    def test_earlier_errors_keep_precedence(self):
        self.assertIn("unknown field", ask([call("product.edit", id=EDIT, colour="$1", description="$3")])["question"])
        self.assertIn("should be a list of text", ask([call("hike.update", id="h1", clear="$1")])["question"])
        self.assertIn("did not find a change", ask([])["question"])

    def test_forbidden_text_policy_unchanged(self):
        self.assertEqual(FORBIDDEN_TEXT, ("<", ">", "$", "{{", "}}"))


class ConversationPriceTests(ProductionConversationTests):
    def test_no_prepare_and_price_only_fixture(self):
        before = self.commits()
        reply = self.asked("price", _ops(("product.edit", {"id": EDIT, "description": "Avocados $3"})))
        self.assertIn(PRICE, reply)
        self.assertEqual(self.commits(), before)
        self.interp.mapping["priceonly"] = {"unsupported": PRICE}
        self.assertEqual(self.say("priceonly"), "unsupported")
        self.assertEqual(self.drafts(), [])

    def test_editor_validation_stays_strict(self):
        from hass.ops import Arg, _check_value
        problems = []
        _check_value(problems, "description", Arg("text"), "Avocados $3", {}, None)
        self.assertEqual(problems, ["description: contains forbidden text '$'"])


class PromptRuleTests(unittest.TestCase):
    def test_rule_present_once_after_never_guess(self):
        hits = [i for i, r in enumerate(RULES) if "The website shows no prices" in r]
        self.assertEqual(len(hits), 1)
        self.assertIn("Never guess dates", RULES[hits[0] - 1])
        self.assertIn(PRICE, RULES[hits[0]])
        self.assertIn("Never write a price into any field", RULES[hits[0]])


if __name__ == "__main__":
    unittest.main()
