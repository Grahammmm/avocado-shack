"""AV1352-05 (H17): a trailing ? works on read-only commands only; yes/no/undo/stop/resume/note writes never use it.

Run: python3 -m unittest hass.tests.test_readonly_questions -v
"""

import unittest

from hass import conversation as conv
from hass.tests.test_near_approval import TextInterpreter
from hass.tests.test_undo import H06TestCase

READ_ONLY = ("status", "history", "report", "memory", "find eggs", "show a1b2", "post photo-product-001",
             "listing photo-product-024", "hidden", "margin 24 for 12 at 35%", "help", "did it work")


class ReadOnlyQuestionTests(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp = TextInterpreter(self.interp.mapping)
        self.conv = self.open()

    def approvals(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def test_parse_matches_the_plain_command(self):
        for text in READ_ONLY:
            plain = conv.read_command(text) or conv.read_memory(text)
            self.assertIsNotNone(plain, text)
            for tail in ("?", "??", " ?", "?!", ".?", "?."):
                with self.subTest(text=text + tail):
                    self.assertEqual(conv.read_command(text + tail) or conv.read_memory(text + tail), plain)

    def test_arguments_keep_their_case_and_inner_marks(self):
        self.assertEqual(conv.read_command("find Lion's Mane?"), ("find", "Lion's Mane"))
        self.assertEqual(conv.read_command("post Case-Sensitive-ID?"), ("post", "Case-Sensitive-ID"))
        self.assertEqual(conv.read_command("find a?b?"), ("find", "a?b"))

    def test_other_commands_and_lookalikes_keep_today_reading(self):
        for text in ("undo a1b2?", "undo?", "stop changes?", "resume?", "yes a1b2?", "no?", "??", "findings?", "postscript?",
                     "status report?", "please status?"):
            with self.subTest(text=text):
                self.assertEqual(conv.read_command(text), conv.parse_command(text))
        self.assertEqual(conv.read_memory("remember k: is it open?"), ("remember", "k", "is it open?"))
        self.assertEqual(conv.read_memory("forget parking?"), ("forget", "parking?", None))
        self.assertEqual(conv.read_memory("alias jam: photo-product-001?"), ("alias", "jam", "photo-product-001?"))

    def test_questions_answer_like_the_plain_command_without_the_interpreter(self):
        for text in ("status", "history", "report", "memory", "find eggs", "show a1b2", "post photo-product-001",
                     "listing photo-product-024", "help"):
            with self.subTest(text=text):
                plain = (self.say(text, pid="p-" + text), self.replies())
                plain = (plain[0], [r.removesuffix("\n\n" + conv.SHELF_ASK) for r in plain[1]])  # HASS-SHELFCHECK-FLOW-1: the report asks that once a day
                asked = (self.say(text + "?", pid="q-" + text), self.replies())
                self.assertEqual(asked, plain)
                self.assertEqual((self.interp.texts, self.approvals()), ([], 0))

    def test_yes_no_undo_with_a_question_mark_change_nothing(self):
        draft, _reply = self.propose("hours")
        self.interp.texts.clear()
        before = self.drafts()
        for text in (f"yes {draft['code']}?", f"no {draft['code']}?", f"undo {draft['code']}?"):
            with self.subTest(text=text):
                self.say(text)
                self.replies()
                self.assertEqual((self.drafts(), self.approvals(), self.commits()), (before, 0, 0))
        self.assertEqual(self.drafts()[0]["state"], "proposed")


if __name__ == "__main__":
    unittest.main()
