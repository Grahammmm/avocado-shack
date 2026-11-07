"""AVB-15 tests: re-sending the exact text already saved for a key changes nothing (no row, same "since" date).

Same setup as test_memory_chat (temp Git repo, private state dir, injected clock, fixture interpreter).
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import contextlib, json, sqlite3, tempfile, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path

from hass import memory
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_memory import Clock
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
        self.chat("memory", "memory-list", "Saved (1):\nhours: 9-5 (fact, since 2026-11-02)\nAliases (0):")
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
        self.chat("remember Bad_Key: 9-5", "memory-invalid", "Not saved: key must be 1–64 of a-z 0-9 . -.")
        self.chat("remember alias.x: 9-5", "memory-invalid", "Not saved: send alias <name>: <id> to save an alias.")
        self.assertEqual(len(self.rows()), 1)

    def test_alias_same_target_is_refused_and_recorded(self):  # RF1650-4: was an "Updated alias" row (AVB-15 left it)
        self.chat("alias green jam: photo-product-001", "memory-saved", pid="a1")
        self.chat("alias green jam: photo-product-001", "memory-invalid", "Not saved: already remembered.", pid="a2")
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.disposition("a2"), "memory-invalid")  # the message is recorded, not rolled back
        self.assertFalse(self.conv.db.in_transaction)

    def test_alias_new_target_still_updates(self):
        self.chat("alias green jam: photo-product-001", "memory-saved")
        self.chat("alias green jam: photo-product-002", "memory-updated")
        self.assertEqual(len(self.rows()), 2)


class StoreCorrectTests(unittest.TestCase):
    """Memory.correct with the value already active (temp state dir, no chat)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name) / "state"
        self.mem = memory.Memory(str(self.state), Clock())
        self.addCleanup(self.mem.close)
        self.mem.remember("hours.note", "Closed on Thanksgiving", "fact", "operator:seed")

    def rows(self):
        with contextlib.closing(sqlite3.connect(self.state / "conversation.sqlite3")) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM memory ORDER BY id")]

    def test_same_value_is_refused_and_nothing_changes(self):
        before = self.rows()
        with self.assertRaisesRegex(ValueError, "^already remembered$"):
            self.mem.correct("hours.note", "Closed on Thanksgiving", "operator:again")
        self.assertEqual(self.rows(), before)  # same count, created_at, superseded_at
        self.assertEqual(self.mem.get("hours.note"), "Closed on Thanksgiving")

    def test_case_or_spacing_difference_corrects(self):
        self.mem.correct("hours.note", "closed on Thanksgiving", "operator:a")
        self.mem.correct("hours.note", "closed  on Thanksgiving", "operator:b")
        self.assertEqual(len(self.rows()), 3)
        self.assertEqual(self.mem.get("hours.note"), "closed  on Thanksgiving")

    def test_no_active_row_is_key_error(self):
        with self.assertRaises(KeyError): self.mem.correct("missing", "x", "operator:a")

    def test_forgotten_key_is_key_error(self):
        self.mem.forget("hours.note")
        with self.assertRaises(KeyError): self.mem.correct("hours.note", "Closed on Thanksgiving", "operator:a")

    def test_unverified_source_is_reported_before_equality(self):
        self.mem.remember("pickup.day", "Sunday", "fact", "operator:seed")
        before = self.rows()
        with self.assertRaisesRegex(ValueError, "^unverified source$"):
            self.mem.correct("pickup.day", "Sunday", "owner-approved:chg-0000000000ff")
        self.assertEqual(self.rows(), before)

    def test_applied_change_source_same_value_is_refused(self):
        (self.state / "changes").mkdir(mode=0o700)
        (self.state / "changes" / "chg-0000000000a1.json").write_text(json.dumps({"state": "applied"}), "utf-8")
        with self.assertRaisesRegex(ValueError, "^already remembered$"):
            self.mem.correct("hours.note", "Closed on Thanksgiving", "owner-approved:chg-0000000000a1")


if __name__ == "__main__":
    unittest.main()
