"""H15 part 2 tests: `remember <key>: <text>`, `forget <key>` and `memory` in the owner chat.

Same setup as H05/H17 (temp Git repo, private 0700 state dir, injected clock, fixture interpreter); placeholder
example.invalid senders only. Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, memory
from hass.tests.test_conversation import GROUP, STRANGER, T0, ConversationTestCase
from hass.tests.test_status_pause import PAUSED, StoreMixin

KEY_BAD = "I couldn't save that. A note's name can only use letters, numbers, dots and dashes, and has to be short."
TEXT_BAD = "I couldn't save that. The note needs to be short, plain text."


class MemoryChatTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])

    def rows(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM memory ORDER BY id")]

    def chat(self, text, disposition, reply=None, **kw):
        self.assertEqual(self.say(text, **kw), disposition)
        replies = self.replies()
        if reply is not None: self.assertEqual(replies, [reply])
        return replies

    def test_save_list_forget_list(self):
        self.chat("memory", "memory-list", "I'm not keeping any notes.\nI don't have any nicknames.")
        self.chat("remember hours: 9-5", "memory-saved", "Saved hours: 9-5. Say forget hours to remove it.", pid="s1")
        self.now = T0 + timedelta(hours=8)  # 01:00 UTC on Nov 3 is still Nov 2 in Los Angeles
        self.chat("remember parking: Behind the barn", "memory-saved", pid="s2")
        self.chat("Memory.", "memory-list", "Notes I'm keeping:\n- hours: 9-5 (since today at 9 am)\n"
                                            "- parking: Behind the barn (since today at 5 pm)\nI don't have any nicknames.")
        self.chat("forget hours", "memory-forgot", "Okay, I've forgotten hours.")
        self.chat("Forget hours!", "memory-none", "I don't have a note called hours.")
        self.chat("forget no_such", "memory-none", "I don't have a note called no_such.")
        self.chat("forget parking", "memory-forgot")
        self.chat("memory", "memory-list", "I'm not keeping any notes.\nI don't have any nicknames.")
        for row in self.rows():  # store behaviour: text blanked, dates kept
            self.assertEqual(row["value"], "")
            self.assertTrue(row["created_at"] and row["forgotten_at"])
        self.assertEqual([r["source"] for r in self.rows()], ["owner-stated:s1", "owner-stated:s2"])
        self.assertEqual([self.disposition(p) for p in ("s1", "s2")], ["memory-saved", "memory-saved"])

    def test_forget_keeps_trailing_period_in_key(self):
        """`hours` and `hours.` are distinct valid keys; `forget hours.` removes only `hours.`."""
        self.chat("remember hours: plain", "memory-saved")
        self.chat("remember hours.: dotted", "memory-saved", "Saved hours.: dotted. Say forget hours. to remove it.")
        self.chat("forget hours.", "memory-forgot", "Okay, I've forgotten hours..")
        self.chat("memory", "memory-list", "Notes I'm keeping:\n- hours: plain (since today at 9 am)\nI don't have any nicknames.")
        self.chat("forget hours.", "memory-none", "I don't have a note called hours..")
        self.chat("forget hours!", "memory-forgot", "Okay, I've forgotten hours.")
        self.chat("memory", "memory-list", "I'm not keeping any notes.\nI don't have any nicknames.")

    def test_correct_and_case(self):
        self.chat("remember hours: 9-5", "memory-saved", pid="c1")
        self.chat("remember hours: 10-6", "memory-updated", "Updated hours. It was 9-5. Say forget hours to remove it.",
                  pid="c2")
        self.chat("Remember Hours: Closed Mondays", "memory-updated", pid="c3")
        self.chat("memory", "memory-list", "Notes I'm keeping:\n- hours: Closed Mondays (since today at 9 am)\nI don't have any nicknames.")
        self.assertEqual(memory.Memory.on_connection(self.conv.db, self.conv.clock).get("hours"), "Closed Mondays")
        self.assertEqual([(r["value"], r["source"], r["superseded_at"] is None) for r in self.rows()],
                         [("9-5", "owner-stated:c1", False), ("10-6", "owner-stated:c2", False),
                          ("Closed Mondays", "owner-stated:c3", True)])

    def test_invalid_is_not_saved(self):
        for text, reply in (("remember no spaces!: x", KEY_BAD), ("remember hours:", TEXT_BAD),
                            ("remember hours:   ", TEXT_BAD), ("remember hours: " + "x" * 501, TEXT_BAD),
                            ("remember hours: ring \x07 bell", TEXT_BAD), ("remember hours: two\nlines", TEXT_BAD),
                            ("remember to restock avocados", TEXT_BAD), ("remember hours", TEXT_BAD),
                            ("REMEMBER", KEY_BAD), ("remember " + "k" * 65 + ": x", KEY_BAD)):
            with self.subTest(text=text):
                self.chat(text, "memory-invalid", reply, pid=f"bad{len(self.out.sent)}")
        self.assertEqual(self.rows(), [])
        self.chat("remember hours: " + "x" * 500, "memory-saved")  # the limit itself is allowed

    def test_owner_gate_and_duplicate(self):
        for kw, disposition in ((dict(sender=STRANGER), "ignored"), (dict(chat=GROUP), "ignored"),
                                (dict(from_me=True), "echo"), (dict(kind="edited"), "not-read")):
            with self.subTest(**kw):
                self.chat("remember hours: 9-5", disposition, **kw)
                self.assertEqual([r["text"] for r in self.out.sent],
                                 [conversation.NOT_READ_REPLY] if disposition == "not-read" else [])
        self.assertNotIn("memory", self.tables())
        self.chat("remember hours: 9-5", "memory-saved", pid="d1")
        self.chat("remember hours: 9-5", "duplicate", pid="d1")
        self.assertEqual(self.replies(), [])
        self.assertEqual((len(self.rows()), self.disposition("d1")), (1, "memory-saved"))

    def test_no_site_effect_and_open_draft_kept(self):
        draft, _reply = self.propose("hours")
        self.calls.clear()
        for text in ("remember hours: 9-5", "remember hours: 10-6", "memory", "forget hours", "remember x y"):
            self.say(text)
        self.replies()
        self.assertEqual((self.calls, self.commits(), self.drafts()), ([], 0, [draft]))
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual((self.commits(), self.drafts()[0]["state"]), (1, "applied"))

    def test_paused_still_saves(self):
        self.chat("pause changes", "pause", PAUSED)
        self.chat("remember hours: 9-5", "memory-saved", "Saved hours: 9-5. Say forget hours to remove it.")
        self.assertEqual(self.status()[0], "Changes are paused since today at 9 am. Say resume changes when you're ready.")
        self.assertEqual(self.calls, [])

    def test_spaced_note_names_normalize_to_hyphens(self):
        """AV1352-07: spaces in a note name become -; capitals fold; the value keeps its case; invalid names refuse."""
        self.chat("remember Parking  Spot: Use the Back Lot.", "memory-saved",
                  "Saved parking-spot: Use the Back Lot.. Say forget parking-spot to remove it.")
        self.chat("remember parking spot: Use the Back Lot.", "memory-unchanged")
        self.chat("remember  parking-spot : new lot", "memory-updated")
        self.chat("forget parking spot?", "memory-none", "I don't have a note called parking-spot?.")
        self.chat("forget Parking Spot!", "memory-forgot", "Okay, I've forgotten parking-spot.")
        self.chat("forget parking spot", "memory-none", "I don't have a note called parking-spot.")
        self.assertEqual([r["value"] for r in self.rows()], ["", ""])
        self.assertEqual(self.calls, [])
        for text in ("remember back_lot spot: x", "remember a/b c: x", "remember " + "x " * 32 + "y: x"):
            self.chat(text, "memory-invalid", KEY_BAD)
        self.chat("remember " + "x" * 31 + " " + "y" * 32 + ": x", "memory-saved")  # 64 characters
        self.chat("remember parking spot: " + "z" * 501, "memory-invalid", TEXT_BAD)
        self.assertEqual(len(self.rows()), 3)

    def test_spaced_forget_dotted_and_it(self):
        self.chat("remember hours today.: dotted", "memory-saved")
        self.chat("forget hours today", "memory-none", "I don't have a note called hours-today.")
        self.chat("forget hours today.", "memory-forgot", "Okay, I've forgotten hours-today..")
        self.chat("remember it: x", "memory-saved")
        self.chat("forget it", "memory-forgot", "Okay, I've forgotten it.")
        self.assertEqual(self.calls, [])
        self.assertIsNone(conversation.parse_memory("forget it  all"))
        self.assertIsNone(conversation.parse_memory("forget two\nlines"))
        self.assertIsNone(conversation.parse_memory("forget"))
        self.chat("forget Unicode Näme", "memory-none")

    def test_look_alikes_go_to_interpreter(self):
        for text in ("please remember to restock avocados", "Remembering the hike", "forget it all",
                     "memory of the hike", "Remember."):
            with self.subTest(text=text):
                self.assertIsNone(conversation.parse_memory(text))
                self.calls.clear()
                self.chat(text, "unsupported", "Sorry, I can't do that yet.")
                self.assertEqual(self.calls, ["interpret"])
        self.assertNotIn("memory", self.tables())

    def test_one_connection_and_failed_op_rolls_back_only_itself(self):
        self.chat("remember hours: 9-5", "memory-saved")
        self.assertIs(self.conv.memory.db, self.conv.db)
        partial = []

        def half(store, *args):  # correct() has already superseded the old row when this raises
            partial.append(store._active("hours"))
            raise ValueError("simulated failure")

        with mock.patch.object(memory.Memory, "_insert", half):
            self.chat("remember hours: 10-6", "memory-invalid", "I couldn't save that. Please keep it short and plain, and try again.", pid="f1")
        self.assertEqual((partial, self.disposition("f1")), ([None], "memory-invalid"))
        self.assertEqual([(r["value"], r["superseded_at"]) for r in self.rows()], [("9-5", None)])
        self.assertFalse(self.conv.db.in_transaction)
        self.chat("remember hours: 10-6", "memory-updated")  # the connection is usable; nothing is locked
        self.conv = self.open()  # restart: rows persist, a fresh connection reads them
        self.chat("memory", "memory-list", "Notes I'm keeping:\n- hours: 10-6 (since today at 9 am)\nI don't have any nicknames.")

    def test_list_truncates_at_twenty(self):
        for i in range(23):
            self.say(f"remember k{i:02d}: v{i}")
        [reply] = self.replies()[-1:]
        self.say("memory")
        lines = self.replies()[0].splitlines()
        self.assertEqual((lines[0], lines[1], lines[20], lines[21], len(lines)),
                         ("Notes I'm keeping:", "- k00: v0 (since today at 9 am)", "- k19: v19 (since today at 9 am)",
                          "And a few more.", 23))
        self.assertEqual(lines[-1], "I don't have any nicknames.")
        self.assertEqual(reply, "Saved k22: v22. Say forget k22 to remove it.")


if __name__ == "__main__":
    unittest.main()
