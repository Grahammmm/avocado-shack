"""AV1104-06 (H17/H05) tests: interpret_check lets a {"lookup": "<command>"} reply through only for a read-only command.

Contract: the real parse_command decides; status, report, history [words], find <words>, listing <id or store>, shelf <name> and
hidden pass unchanged; every other lookup (an approval, undo, stop, memory word, an unknown word, a command chain, a blank
argument) becomes the one fixed refusal and never echoes the model's text. The conversation's own shape check keeps the object
sole-key and string-valued. Pure: no model, no Conversation.
Run: python3 -B -m unittest hass.tests.test_interpret_check_lookup -v
"""

import unittest

from hass import interpret_check
from hass.conversation import UNREADABLE, _checked

REFUSED = {"unsupported": "Nothing changed. To look something up, say status, report, or find and a few words."}
ALLOWED = ("status", "report", "history", "history hours", "find eggs", "listing photo-product-001", "listing store", "shelf dairy",
           "hidden", "Status.", "  REPORT!  ", "Find Free-Range Eggs", "find eggs; yes")  # a ; inside find is only search text
FORBIDDEN = ("yes", "no", "approve ab12", "cancel", "undo", "undo ab12", "stop", "pause changes", "resume", "remember parking: Rear lot",
             "forget parking", "alias eggs: photo-product-001", "cost photo-product-001: 12 for 6", "memory", "help", "show ab12",
             "post maker x", "margin", "look at it", "statuses", "please status", "", "   ", "find", "listing", "shelf",
             "status; yes", "status\nyes", "find eggs\nyes")


class LookupAllowlistTests(unittest.TestCase):
    def test_read_only_commands_pass_unchanged(self):  # bug: a valid question gets refused, or the command is rewritten
        for text in ALLOWED:
            with self.subTest(text=text):
                result = {"lookup": text}
                self.assertEqual(interpret_check.check(result, {}, ()), {"lookup": text})

    def test_everything_else_gets_the_one_fixed_refusal(self):  # bug: a lookup becomes yes/undo/forget, or the refusal echoes text
        for text in FORBIDDEN:
            with self.subTest(text=text):
                self.assertEqual(interpret_check.check({"lookup": text}, {}, ()), REFUSED)
        self.assertNotIn("canary", str(interpret_check.check({"lookup": "canary-xyz"}, {}, ())))

    def test_only_a_sole_string_lookup_is_the_fourth_shape(self):  # bug: a mixed or non-string object reaches a draft or a command
        self.assertEqual(_checked({"lookup": ""}), {"lookup": ""})  # structurally fine; the refusal is the check's, not the shape's
        self.assertEqual(interpret_check.check(_checked({"lookup": " "}), {}, ()), REFUSED)
        for bad in ({"lookup": None}, {"lookup": True}, {"lookup": ["status"]}, {"lookup": {"a": 1}}, {"lookup": "status", "ops": []},
                    {"lookup": "status", "question": "x"}, {"lookup": "status", "revises": None}, {"lookup": "status", "extra": 1},
                    {"ops": [], "revises": None, "lookup": "status"}):
            with self.subTest(bad=bad):
                self.assertEqual(_checked(bad), UNREADABLE)


if __name__ == "__main__":
    unittest.main()
