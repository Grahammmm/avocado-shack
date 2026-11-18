"""AV1052-11 (H24/H15): a checked design refusal is kept as the owner's dated note design.<n>; listed apart, forgettable,
never a preference. Offline, synthetic. Run: python3 -B -m unittest hass.tests.test_design_notes -v"""

import unittest

from hass import conversation, memory as memory_mod
from hass.interpreter_prompt import DESIGN_UNSUPPORTED
from hass.tests.test_conversation import SETTINGS, ConversationTestCase

KEPT = f"{DESIGN_UNSUPPORTED}. I kept it for the developer as design.{{}}."


class DesignNoteTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "interpreterDailyCap": 50})
        self.texts = ["Make the HEADER green!", "  \u00c9mile wants \U0001f951 on top", "x" * 499, "y" * 500, "z" * 501]
        mapping = {t: {"unsupported": DESIGN_UNSUPPORTED} for t in self.texts}
        mapping["what is love"] = {"unsupported": "Sorry, I can't do that yet."}
        mapping["a question"] = {"question": "Which one?"}
        self.interp = conversation.FixtureInterpreter({**self.interp.mapping, **mapping})
        self.conv = self.open()

    def rows(self):
        return self.conv.db.execute("SELECT key, value, kind, source FROM memory ORDER BY id").fetchall()

    def test_kept_with_source_and_numbered_reply(self):
        self.assertEqual(self.say(self.texts[0]), "unsupported")
        self.assertEqual(self.replies(), [KEPT.format(1)])
        [row] = self.rows()
        self.assertEqual((row["key"], row["value"], row["kind"]), ("design.1", self.texts[0], "fact"))
        self.assertTrue(row["source"].startswith("owner-stated:"))
        self.assertEqual((self.commits(), len(self.drafts())), (0, 0))

    def test_boundaries_and_truncation_notice(self):
        for t in self.texts[2:]: self.say(t)
        replies = self.replies()
        self.assertEqual(replies[:2], [KEPT.format(1), KEPT.format(2)])
        self.assertEqual(replies[2], KEPT.format(3) + " Only the first 500 characters were kept.")
        self.assertEqual([len(r["value"]) for r in self.rows()], [499, 500, 500])

    def test_other_replies_are_not_kept(self):
        for t in ("what is love", "a question"): self.say(t)
        self.assertIsNone(self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'memory'").fetchone())

    def test_numbering_never_reuses_forgotten_or_manual_keys(self):
        self.say(self.texts[0]); self.say(self.texts[1]); self.replies()
        self.assertEqual(self.say("forget design.2"), "memory-forgot")
        self.conv.memory.remember("design.8", "manual", "fact", "owner-stated:t")
        self.conv.memory.remember("design.bad", "x", "fact", "owner-stated:t")
        self.say(self.texts[3]); self.replies()
        self.assertEqual([r["key"] for r in self.rows()][-1], "design.9")
        self.assertEqual(self.say("forget design.2"), "memory-none")

    def test_unkeepable_text_claims_nothing(self):
        mapping = {"\u0007bell": {"unsupported": DESIGN_UNSUPPORTED}}
        self.interp = conversation.FixtureInterpreter({**self.interp.mapping, **mapping})
        self.conv = self.open()
        self.say("\u0007bell")
        [reply] = self.replies()
        self.assertTrue(reply.startswith(DESIGN_UNSUPPORTED + ". I couldn't keep the note"), reply)
        self.assertNotIn("I kept it", reply)
        self.assertEqual(self.rows(), [])

    def test_listing_apart_and_forget(self):
        self.say(self.texts[0]); self.conv.memory.remember("tone", "calm", "fact", "owner-stated:t"); self.replies()
        self.assertEqual(self.say("memory"), "memory-list")
        [text] = self.replies()
        notes, _, design = text.partition("Design notes (1):")
        self.assertNotIn("design.1", notes)
        self.assertRegex(design, r"- design\.1: .*Make the HEADER green! .*\(owner, since .+\)")
        self.assertEqual(self.say("forget design.1"), "memory-forgot")
        self.assertEqual(self.say("memory"), "memory-list")
        self.assertNotIn("Design notes", self.replies()[0])
        self.assertEqual(self.conv.db.execute("SELECT value FROM memory WHERE key = 'design.1'").fetchone()[0], "")

    def test_listing_without_design_rows_is_unchanged(self):
        self.say("memory")
        self.assertEqual(self.replies(), ["I'm not keeping any notes.\nI don't have any nicknames."])

    def test_listing_caps_at_twenty(self):
        mem = memory_mod.Memory.on_connection(self.conv.db, self.conv.clock)
        for i in range(21): mem.remember(f"design.{i + 1}", f"v{i}", "fact", "owner-stated:t")
        self.say("memory")
        [text] = self.replies()
        design = text.split("Design notes (21):")[1].splitlines()
        self.assertEqual(len(design), 1 + 20 + 1)
        self.assertEqual(design[-1], "And a few more.")


if __name__ == "__main__":
    unittest.main()
