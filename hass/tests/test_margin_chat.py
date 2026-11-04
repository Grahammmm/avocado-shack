"""AV1102-12 (F03): `margin <pack cost> for <units> at <margin>%` (optional `shrink <S>%`) replies margins.compute's suggested
price with every step and the suggestion-only note. Read-only: nothing stored, no interpreter call, works while paused.
Run: python3 -B -m unittest hass.tests.test_margin_chat -v
"""

import unittest

from hass import conversation, margins
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

USAGE = 'Send: margin <pack cost> for <units> at <margin>% (optional: shrink <S>%), e.g. "margin 24.00 for 12 at 35%".'


class CountingInterpreter(conversation.FixtureInterpreter):
    calls = 0

    def interpret(self, text, pending):
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
        want, before = margins.render(margins.compute("24.00", "12", "0", "35")), self.stored()
        self.assertEqual(self.margin("margin 24.00 for 12 at 35%"), want)
        self.assertTrue(want.endswith(margins.NOTE))
        self.assertIn("suggested_price = round up to the cent", want)
        self.assertEqual(self.stored(), before)
        self.assertEqual(CountingInterpreter.calls, 0)

    def test_dollar_sign_case_and_shrink_match_the_cli(self):
        want = margins.render(margins.compute("24", "12", "5", "35"))
        self.assertEqual(self.margin("MARGIN $24 for 12 at 35% shrink 5%"), want)
        self.assertEqual(self.margin("margin   24  for 12   at 35 %  shrink 5 %."), want)
        self.assertNotEqual(want, margins.render(margins.compute("24", "12", "0", "35")))

    def test_bad_numbers_are_named_by_field(self):
        before = self.stored()
        for text, want in (("margin 24.00 for 0 at 35%", "Not calculated: units must be 1 to 10000."),
                           ("margin 24.001 for 12 at 35%", "Not calculated: pack cost"),
                           ("margin 24 for 12 at 95%", "Not calculated: margin must be 0 to 90."),
                           ("margin 24 for 12 at 35% shrink 91%", "Not calculated: shrink must be 0 to 90."),
                           ("margin 24 for 1.5 at 35%", "Not calculated: units"),
                           ("margin 24 for 12 at 35.555%", "Not calculated: margin")):
            with self.subTest(text=text):
                reply = self.margin(text)
                self.assertTrue(reply.startswith(want) and reply.endswith("."), reply)
                self.assertNotIn(margins.NOTE, reply)
        self.assertEqual(self.stored(), before)
        self.assertEqual(CountingInterpreter.calls, 0)

    def test_text_not_in_the_form_gets_the_usage_without_interpreter_or_usage_row(self):
        before = self.stored()
        for text in ("margin 24 for twelve at 35%", "margin", "margin 24 for 12 at 35", "margin 24 for 12", "margin a1b2",
                     "margin 24 for 12 at 35% shrink", "margin 24 for 12 at 35% shrink 5% extra"):
            with self.subTest(text=text):
                self.assertEqual(self.margin(text), USAGE)
        self.assertEqual(CountingInterpreter.calls, 0)
        self.assertEqual(self.stored(), before)

    def test_works_while_paused_and_writes_nothing(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        before = self.stored()
        self.assertEqual(self.margin("margin 24.00 for 12 at 35%"), margins.render(margins.compute("24.00", "12", "0", "35")))
        self.assertEqual(self.margin("margin 24 for 0 at 35%"), "Not calculated: units must be 1 to 10000.")
        self.assertEqual(self.margin("margin"), USAGE)
        self.assertEqual(self.stored(), before)

    def test_a_message_that_only_contains_the_word_goes_to_the_interpreter(self):
        self.assertEqual(self.say("what margin do jams make?"), "question")
        self.assertEqual(self.replies(), ["Which jam?"])
        self.assertEqual(CountingInterpreter.calls, 1)

    def test_help_has_the_margin_line_and_its_example_runs(self):
        [line] = [ln for ln in conversation.HELP_TEXT.splitlines() if ln.startswith("margin ")]
        self.assertLessEqual(len(line), 70)
        self.assertTrue(line.endswith('"margin 24 for 12 at 35%"'))
        self.assertTrue(self.margin("margin 24 for 12 at 35%").endswith(margins.NOTE))


if __name__ == "__main__":
    unittest.main()
