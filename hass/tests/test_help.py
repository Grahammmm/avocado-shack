"""AV1537-03 (H17/H25): `help` replies HELP_TEXT, a short list of every owner command, kept in step with the parsers.
The verb set is test_commands_doc.parser_verbs() (imported, never copied). Run: python3 -B -m unittest hass.tests.test_help
"""

import re
import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_commands_doc import parser_verbs, verb
from hass.tests.test_conversation import GROUP, STRANGER, T0, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS

LINES = conversation.HELP_TEXT.splitlines()


def examples():
    """(leading word, example) for each command line: the quoted text at the end of the line."""
    return [(ln.split()[0], m[1]) for ln in LINES[1:] if (m := re.search(r'"([^"]+)"$', ln))]


class HelpTextTests(unittest.TestCase):
    def test_every_parser_verb_has_a_line_and_its_example_parses_back(self):
        pairs = examples()
        self.assertEqual(len(pairs), len(LINES) - 1, "a command line has no quoted example")
        for word, example in pairs:
            with self.subTest(example=example):
                self.assertEqual(example.split()[0], word)  # the example belongs to its own line
                self.assertIsNotNone(verb(example))
        self.assertEqual({verb(ex) for _, ex in pairs}, parser_verbs())  # incl. alias and help; no extra verb
        self.assertEqual(len({verb(ex) for _, ex in pairs}), len(pairs) - 1)  # one line per verb; AV1222-11: post has two (product, hike)

    def test_limits_and_plain_text(self):
        self.assertLessEqual(len(LINES), 21)  # AV1222-13: + the hidden line; AV1222-11: + the post hike line; AV1222-10: + the cost line; AV0022-08: + the show line; AV1322-05: + the report line; AV1322-07: + the post line; AV1102-12: + the margin line
        for line in LINES:
            self.assertLessEqual(len(line), 70, line)
            self.assertFalse(set(line) & set("*_`#"), line)  # plain text, no markdown
        self.assertIsNone(verb(re.search(r'"([^"]+)"', LINES[0])[1]))  # the plain-words example is a change
        self.assertIn('"Stop showing the eggs as sold out"', LINES[0])  # AV1622-05

    def test_help_wordings_parse_and_lookalikes_do_not(self):
        for text in ("help", "Help!", "commands.", "?", " HELP ", "Commands!"):
            self.assertEqual(conversation.parse_command(text), ("help", None), text)
        for text in ("help me with avocados", "help a1b2", "??", "what?", "help?", "command"):
            self.assertIsNone(verb(text), text)


class HelpConversationTests(ConversationTestCase):
    def state(self):
        db = self.conv.db
        has_control = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'control'").fetchone()
        return (self.drafts(), db.execute("SELECT * FROM approvals").fetchall(), self.commits(), self.editor.applies,
                db.execute("SELECT * FROM control").fetchall() if has_control else [])

    def test_help_replies_the_list_and_changes_nothing(self):
        for text in ("help", "Help!", "commands.", "?"):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "help")
                self.assertEqual(self.replies(), [conversation.HELP_TEXT])
        self.assertEqual((self.say("help", pid="m1"), self.replies()), ("duplicate", []))  # a resent help: no reply
        self.assertEqual(self.state(), ([], [], 0, 0, []))

    def test_help_sentence_goes_to_the_interpreter(self):
        self.interp.mapping["help me with avocados"] = _ops((HOURS, {"hours": NEW_HOURS}))
        self.assertEqual(self.say("help me with avocados"), "proposed")
        self.assertNotEqual(self.replies(), [conversation.HELP_TEXT])

    def test_help_does_not_expire_a_lapsed_proposal(self):
        draft, _reply = self.propose("hours")
        self.now = T0 + timedelta(seconds=601)  # lapsed; no other message has swept it yet
        before = self.state()
        self.assertEqual(self.say("help"), "help")
        self.assertEqual((self.replies(), self.state()), ([conversation.HELP_TEXT], before))
        self.assertEqual(self.drafts()[0]["state"], "proposed")
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_help_while_paused_writes_no_approval_or_control_row(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        before = self.state()
        self.assertEqual(self.say("Help!"), "help")
        self.assertEqual((self.replies(), self.state()), ([conversation.HELP_TEXT], before))
        self.assertEqual((self.drafts()[0]["state"], self.editor.applies), ("proposed", 0))

    def test_stranger_or_group_help_is_ignored_without_a_reply(self):
        self.assertEqual(self.say("help", sender=STRANGER), "ignored")
        self.assertEqual(self.say("help", chat=GROUP), "ignored")
        self.assertEqual(self.replies(), [])
