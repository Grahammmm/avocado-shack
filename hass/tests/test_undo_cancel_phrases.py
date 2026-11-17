"""AV0222-07 (H06/H17): common undo and cancel phrases act as a bare undo / bare no, without the interpreter.

Run: python3 -B -m unittest hass.tests.test_undo_cancel_phrases -v
"""

import unittest

from hass import conversation as conv
from hass.tests.test_undo import H06TestCase


class ParserTests(unittest.TestCase):
    def test_exact_phrase_case_outer_space_and_final_punctuation(self):
        for phrase in conv.UNDO_PHRASES:
            for text in (phrase, phrase.upper(), f"  {phrase.title()} ", phrase + ".", phrase + "!!", phrase + "!."):
                self.assertEqual(conv.parse_command(text), ("undo", None), text)
        for phrase in conv.CANCEL_PHRASES:
            for text in (phrase, phrase.upper(), f"  {phrase.title()} ", phrase + ".", phrase + "!!", phrase + ".!"):
                self.assertEqual(conv.parse_keyword(text), ("reject", None), text)
        self.assertEqual(conv.parse_command("undo A1B2!"), ("undo", "a1b2"))
        self.assertEqual(conv.parse_keyword("no A1B2"), ("reject", "a1b2"))

    def test_phrase_lookalikes_are_not_new_commands(self):
        for phrase in conv.UNDO_PHRASES:
            for text in (phrase + " a1b2", phrase + " now", phrase + "?", phrase + ",", phrase.replace(" ", "  "),
                         phrase.replace(" ", "\t"), phrase.replace(" ", "\n"), "so " + phrase):
                self.assertIsNone(conv.parse_command(text), text)
        for phrase in conv.CANCEL_PHRASES:
            for text in (phrase + " a1b2", phrase + " the eggs", phrase + "?", phrase + ",", phrase.replace(" ", "  "),
                         phrase.replace(" ", "\t"), phrase.replace(" ", "\n"), "oh " + phrase):
                if text != phrase: self.assertIsNone(conv.parse_keyword(text), text)  # "nevermind" has no space to change
        self.assertEqual(conv.parse_memory("forget it"), ("forget", "it", None))
        for text in ("forget it", "stop", "no thanks", "thanks"):
            self.assertIsNone(conv.parse_keyword(text), text)


class AliasFlowTests(H06TestCase):
    def test_each_undo_phrase_drafts_like_bare_undo(self):
        self.apply("desc2")
        for phrase in conv.UNDO_PHRASES:
            with self.subTest(phrase):
                calls = len(self.interp.calls) if hasattr(self.interp, "calls") else None
                self.assertEqual(self.say(phrase), "proposed")
                row = self.drafts()[-1]
                self.assertIn("history.revert", row["ops_json"])
                if calls is not None: self.assertEqual(len(self.interp.calls), calls)
                self.assertEqual(self.say("no"), "rejected")  # nothing applied before a yes

    def test_undo_phrase_with_nothing_applied_matches_bare_undo(self):
        self.assertEqual(self.say("undo"), "no-target")
        canonical = self.replies()
        self.assertEqual(self.say("undo that"), "no-target")
        self.assertEqual(self.replies(), canonical)

    def test_each_cancel_phrase_rejects_one_waiting_draft(self):
        for phrase in conv.CANCEL_PHRASES:
            with self.subTest(phrase):
                self.replies()
                draft, _ = self.propose("desc2")
                self.assertEqual(self.say(phrase), "rejected")
                self.assertEqual([d["state"] for d in self.drafts() if d["row_id"] == draft["row_id"]], ["rejected"])
                self.assertEqual(self.say(phrase), "no-target")


if __name__ == "__main__":
    unittest.main()
