"""AVB-15 tests: re-sending the exact text already saved for a key changes nothing (no row, same "since" date).

Same setup as test_memory_chat (temp Git repo, private state dir, injected clock, fixture interpreter).
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import unittest
from datetime import timedelta

from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

SAME = "Already saved hours: 9-5; nothing changed."


class MemoryUnchangedTests(StoreMixin, ConversationTestCase):
    def chat(self, text, disposition, reply=None, **kw):
        self.assertEqual(self.say(text, **kw), disposition)
        replies = self.replies()
        if reply is not None: self.assertEqual(replies, [reply])
        return replies

    def rows(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM memory ORDER BY id")]

    def test_same_text_writes_nothing_and_keeps_since_date(self):
        self.chat("remember hours: 9-5", "memory-saved", pid="u1")
        [first] = self.rows()
        self.now = self.now + timedelta(days=3)
        self.chat("remember hours: 9-5", "memory-unchanged", SAME, pid="u2")
        self.assertEqual(self.rows(), [first])  # one active row, nothing superseded, original created_at kept
        self.assertEqual(self.disposition("u2"), "memory-unchanged")  # the message is still recorded
        self.chat("memory", "memory-list", "Saved (1):\nhours: 9-5 (fact, since 2026-11-02)")
        self.assertFalse(self.conv.db.in_transaction)

    def test_different_text_is_still_an_update(self):
        self.chat("remember hours: 9-5", "memory-saved")
        self.chat("remember hours: 9-6", "memory-updated", "Updated hours (was: 9-5). Send forget hours to remove it.")
        self.assertEqual([(r["value"], r["superseded_at"] is None) for r in self.rows()], [("9-5", False), ("9-6", True)])

    def test_case_and_spacing_differences_are_updates(self):
        self.chat("remember hours: Open 9-5", "memory-saved")
        self.chat("remember hours: open 9-5", "memory-updated")
        self.chat("remember hours: open  9-5", "memory-updated")
        self.assertEqual(len(self.rows()), 3)

    def test_after_forget_the_same_text_is_a_new_save(self):
        self.chat("remember hours: 9-5", "memory-saved")
        self.chat("forget hours", "memory-forgot")
        self.chat("remember hours: 9-5", "memory-saved", "Saved hours: 9-5. Send forget hours to remove it.")
        self.assertEqual([(r["value"], r["forgotten_at"] is None) for r in self.rows()], [("", False), ("9-5", True)])

    def test_validation_comes_first(self):
        self.chat("remember hours: 9-5", "memory-saved")
        self.chat("remember Bad Key: 9-5", "memory-invalid", "Not saved: key must be 1–64 of a-z 0-9 . -.")
        self.chat("remember alias.x: 9-5", "memory-invalid", "Not saved: send alias <name>: <id> to save an alias.")
        self.assertEqual(len(self.rows()), 1)

    def test_alias_path_unchanged(self):
        self.chat("alias green jam: photo-product-001", "memory-saved")
        [reply] = self.chat("alias green jam: photo-product-001", "memory-updated")
        self.assertTrue(reply.startswith("Updated alias green jam (was: product:photo-product-001)"), reply)
        self.assertEqual(len(self.rows()), 2)


if __name__ == "__main__":
    unittest.main()
