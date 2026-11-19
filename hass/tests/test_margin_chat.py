"""AV1102-12 (F03): `margin <pack cost> for <units> at <margin>%` (optional `shrink <S>%`) replies margins.compute's suggested
price with every step and the suggestion-only note. Read-only: nothing stored, no interpreter call, works while paused.
Run: python3 -B -m unittest hass.tests.test_margin_chat -v
"""

import unittest

from hass import conversation, margins, voice
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

USAGE = ("Tell me what you pay for a pack (or a product with a saved cost), how many are in it and the margin you want, like margin 24 for 12 at 35%, "
         "or the shelf price to check, like margin 24 for 12 price 3.49. Add shrink 5% if some is lost, or ending .99 (or .49) to round the price up.")  # AV1352-08
NOTE = "This is only an idea. Prices are not shown on the website, and nothing changes unless you ask."


def steps(pack, units, shrink, price):  # AV1352-08: margins.check's own numbers, in the plain words chat allows
    out = margins.render(margins.check(pack, units, shrink, price))
    for name, words in (("unit_cost", "Each one costs you"), ("sellable_cost", "Each one you can sell costs you"), ("price", "Shelf price"),
                        ("margin_actual", "Your margin")):
        out = out.replace(f"{name} = ", f"{words}: ", 1)
    return out.replace("below_cost = yes: this price does not cover the cost per sellable unit", "Below cost: this price does not cover the cost per sellable unit.")


class CountingInterpreter(conversation.FixtureInterpreter):
    calls = 0

    def interpret(self, text, pending, **kw):
        CountingInterpreter.calls += 1
        return super().interpret(text, pending)


class MarginParseTests(unittest.TestCase):
    def test_margin_commands_parse_and_other_messages_do_not(self):
        self.assertEqual(conversation.parse_command("margin 24.00 for 12 at 35%"), ("margin", "24.00 for 12 at 35%"))
        self.assertEqual(conversation.parse_command("MARGIN $24 for 12 at 35% shrink 5%."), ("margin", "$24 for 12 at 35% shrink 5%"))
        self.assertEqual(conversation.parse_command("margin"), ("margin", ""))
        for text in ("what margin do jams make?", "margins 24 for 12 at 35%", "please margin 24 for 12 at 35%", "marginal"):
            self.assertIsNone(verb(text), text)


class MarginChatTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        CountingInterpreter.calls = 0
        self.interp = CountingInterpreter(self.interp.mapping)
        self.conv = self.open()
        self.interp.mapping["what margin do jams make?"] = {"question": "Which jam?"}

    def margin(self, text):
        self.assertEqual(self.say(text), "margin")
        self.assertEqual(self.disposition(f"m{self.n}"), "margin")
        [reply] = self.replies()
        return reply

    def stored(self):
        return (self.drafts(), self.tables(), self.commits(), self.approvals(), self.editor.applies,
                [tuple(r) for r in self.conv.db.execute("SELECT * FROM usage")] if "usage" in self.tables() else [])

    def test_reply_is_the_cli_arithmetic_and_ends_with_the_note(self):
        want, before = margins.say(margins.compute("24.00", "12", "0", "35")), self.stored()
        self.assertEqual(self.margin("margin 24.00 for 12 at 35%"), want)
        self.assertTrue(want.endswith(NOTE))
        self.assertIn("Charge $3.08.", want)
        self.assertEqual(self.stored(), before)
        self.assertEqual(CountingInterpreter.calls, 0)

    def test_dollar_sign_case_and_shrink_match_the_cli(self):
        want = margins.say(margins.compute("24", "12", "5", "35"))
        self.assertEqual(self.margin("MARGIN $24 for 12 at 35% shrink 5%"), want)
        self.assertEqual(self.margin("margin   24  for 12   at 35 %  shrink 5 %."), want)
        self.assertNotEqual(want, margins.say(margins.compute("24", "12", "0", "35")))

    def test_bad_numbers_are_named_by_field(self):
        before = self.stored()
        for text, want in (("margin 24.00 for 0 at 35%", "I couldn't work that out. Please check how many are in a pack: it needs to be a plain number in a sensible range."),
                           ("margin 24.001 for 12 at 35%", "I couldn't work that out. Please check the pack price:"),
                           ("margin 24 for 12 at 95%", "I couldn't work that out. Please check the margin:"),
                           ("margin 24 for 12 at 35% shrink 91%", "I couldn't work that out. Please check the shrink:"),
                           ("margin 24 for 1.5 at 35%", "I couldn't work that out. Please check how many are in a pack:"),
                           ("margin 24 for 12 at 35.555%", "I couldn't work that out. Please check the margin:")):
            with self.subTest(text=text):
                reply = self.margin(text)
                self.assertTrue(reply.startswith(want) and reply.endswith("."), reply)
                self.assertNotIn(NOTE, reply)
        self.assertEqual(self.stored(), before)
        self.assertEqual(CountingInterpreter.calls, 0)

    def test_text_not_in_the_form_gets_the_usage_without_interpreter_or_usage_row(self):
        before = self.stored()
        for text in ("margin 24 for twelve at 35%", "margin $24 for twelve at 35%", "margin +24 for twelve at 35%", "margin", "margin 24 for 12 at 35", "margin 24 for 12", "margin a1b2",
                     "margin 24 for 12 at 35% shrink", "margin 24 for 12 at 35% shrink 5% extra",
                     "margin 24 for 12 at 35% ending .50", "margin 24 for 12 at 35% ending 0.99", "margin 24 for 12 at 35% ending .00", "margin 24 for 12 at 35% ending",
                     "margin 24 for 12 at 35% ending .99 ending .99", "margin 24 for 12 at 35% ending .99 shrink 5%", "margin 24 for 12 at 35% ending .99 extra",
                     "margin 24 for 12 price 3.49 ending .99", "margin a1b2 at 35% ending abc"):
            with self.subTest(text=text):
                self.assertEqual(self.margin(text), USAGE)
        self.assertEqual(CountingInterpreter.calls, 0)
        self.assertEqual(self.stored(), before)

    def test_ending_rounds_up_and_shows_the_margin_of_the_rounded_price(self):  # AV1352-09
        before = self.stored()
        self.assertEqual(self.margin("margin 24 for 12 at 35% ending .99"), margins.say(margins.compute("24", "12", "0", "35", ".99")))
        self.assertIn("Charge $3.99.", self.margin("margin 24 for 12 at 35% ending .99"))
        self.assertIn("roughly 49.8%", self.margin("margin 24 for 12 at 35% ending .99"))
        self.assertIn("Charge $3.49.", self.margin("margin 24 for 12 at 35% ending .49"))
        self.assertEqual(self.margin("margin $24 for 12 at 35% shrink 5% ENDING .49"), margins.say(margins.compute("24", "12", "5", "35", ".49")))
        self.assertEqual(self.margin("margin 24 for 12 at 35% shrink 0% ending .99"), margins.say(margins.compute("24", "12", "0", "35", ".99")))
        self.assertEqual(self.stored(), before)
        self.assertEqual(CountingInterpreter.calls, 0)

    def test_ending_errors_keep_their_named_refusals(self):  # AV1352-09
        self.assertIn("I couldn't work that out. Please check the margin", self.margin("margin 24 for 12 at 95% ending .99"))
        self.assertIn("Please check the pack price", self.margin("margin 24.001 for 12 at 35% ending .49"))

    def test_ending_with_a_saved_cost(self):  # AV1352-09
        self.assertEqual(self.say("cost Hass avocado: 24 for 12"), "memory-saved")
        self.replies()
        got = self.margin("margin Hass avocado at 35% ending .99")
        self.assertIn("Charge $3.99.", got)
        self.assertTrue(got.startswith("For Hass avocado (photo-product-001), using the cost you gave me"), got)

    def test_saved_cost_still_accepts_a_product_name(self):
        self.assertEqual(self.say("cost Hass avocado: 24 for 12"), "memory-saved")
        self.replies()
        before = self.stored()
        reply = self.margin("margin Hass avocado at 35%")
        self.assertTrue(reply.startswith("For Hass avocado (photo-product-001), using the cost you gave me "), reply)
        self.assertTrue(reply.endswith(margins.say(margins.compute("24", "12", "0", "35"))), reply)
        self.assertEqual(self.stored(), before)
        self.assertEqual(CountingInterpreter.calls, 0)

    def test_shelf_price_replies_every_step_and_the_below_cost_line(self):  # AV1352-08
        before = self.stored()
        got = self.margin("margin 24 for 12 price 1.00")
        self.assertEqual(got, steps("24", "12", "0", "1.00"))
        for line in ("Each one costs you: 24.00 / 12 = 2.00", "Shelf price: given = 1.00", "Your margin: (1.00 - 2.00) / 1.00 = -100.0%",
                     "Below cost: this price does not cover the cost per sellable unit."):
            self.assertIn(line, got)
        ok = self.margin("MARGIN $24 for 12   PRICE $3.49 shrink 5 %.")
        self.assertEqual(ok, steps("24", "12", "5", "3.49"))
        self.assertNotIn("Below cost", ok)
        self.assertEqual(self.stored(), before)
        self.assertEqual(CountingInterpreter.calls, 0)

    def test_shelf_price_bad_or_mixed_input(self):  # AV1352-08
        before = self.stored()
        for text, want in (("margin 24 for 12 price 0", "Please check the price:"), ("margin 24 for 12 price 3.499", "Please check the price:"),
                           ("margin 24 for 12 price 3.49 shrink 95%", "Please check the shrink:")):
            with self.subTest(text=text):
                self.assertIn(want, self.margin(text))
        for text in ("margin 24 for 12 price", "margin 24 for 12 price abc", "margin 24 for 12 price 3.49 at 35%", "margin 24 for 12 at 35% price 3.49",
                     "margin 24 for 12 price 3.49 extra", "margin 24 for 12 price 3.49 shrink 5% shrink 5%", "margin a1b2 price"):
            with self.subTest(text=text):
                self.assertEqual(self.margin(text), USAGE)
        self.assertEqual(self.stored(), before)
        self.assertEqual(CountingInterpreter.calls, 0)

    def test_saved_cost_shelf_price_and_no_saved_cost(self):  # AV1352-08
        self.assertTrue(self.margin("margin Hass avocado price 3.49").startswith("I don't have a cost saved for"))
        self.assertEqual(self.say("cost Hass avocado: 24 for 12"), "memory-saved")
        self.replies()
        before = self.stored()
        reply = self.margin("margin Hass avocado price 1.00 shrink 5%")
        self.assertTrue(reply.startswith("For Hass avocado (photo-product-001), using the cost you gave me "), reply)
        self.assertTrue(reply.endswith(steps("24", "12", "5", "1.00")), reply)
        self.assertIn("Below cost: this price", reply)
        self.assertEqual(self.stored(), before)
        self.assertEqual(CountingInterpreter.calls, 0)

    def test_works_while_paused_and_writes_nothing(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        before = self.stored()
        self.assertEqual(self.margin("margin 24.00 for 12 at 35%"), margins.say(margins.compute("24.00", "12", "0", "35")))
        self.assertEqual(self.margin("margin 24 for 0 at 35%"), "I couldn't work that out. Please check how many are in a pack: it needs to be a plain number in a sensible range.")
        self.assertEqual(self.margin("margin"), USAGE)
        self.assertEqual(self.stored(), before)

    def test_a_message_that_only_contains_the_word_goes_to_the_interpreter(self):
        self.assertEqual(self.say("what margin do jams make?"), "question")
        self.assertEqual(self.replies(), ["Which jam?"])
        self.assertEqual(CountingInterpreter.calls, 1)

    def test_help_has_the_margin_line_and_its_example_runs(self):
        [line] = voice.plain(conversation.help_detail("margin")).splitlines()  # AV1052-12: the full line is in `help margin`
        self.assertLessEqual(len(line), 70)
        self.assertEqual(line, "margin Hass avocado at 35% - a price idea or a price check")  # AV1222-10: the product form
        self.assertTrue(self.margin("margin 24 for 12 at 35%").endswith(NOTE))


if __name__ == "__main__":
    unittest.main()
