"""NB-AV-07 (H22) tests: optional interpreterDailyCap counts interpreter calls per local day.

Over the cap the next change request gets one DAILY_LIMIT reply, no draft and no interpreter call; commands, approvals,
undo and memory still work and never count. Same H05/H06 setup (temp Git repo, private state dir, injected clock).
Run: python3 -m unittest hass.tests.test_interpreter_cap -v
"""

import unittest
from datetime import datetime, timezone

from hass import conversation
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_undo import H06TestCase

SORRY = conversation.UNREADABLE["unsupported"]


class CountingInterpreter(conversation.FixtureInterpreter):
    """FixtureInterpreter that counts calls; the text "boom" raises and "junk" returns an unreadable result."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.calls = 0

    def interpret(self, text, pending, **kw):
        self.calls += 1
        if text == "boom": raise RuntimeError("simulated interpreter failure")
        return {"bogus": 1} if text == "junk" else super().interpret(text, pending)


class CapTestCase(H06TestCase):
    CAP = 2

    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "interpreterDailyCap": self.CAP} if self.CAP else SETTINGS)
        self.interp = CountingInterpreter(self.interp.mapping)
        self.conv = self.open()

    def tables(self):
        return {r[0] for r in self.conv.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def status(self):
        self.replies()  # earlier replies are checked where they matter
        self.assertEqual(self.say("status"), "status")
        [reply] = self.replies()
        return reply.splitlines()

    def limited(self, text="hours", pid=None):
        drafts = len(self.drafts())
        self.assertEqual(self.say(text, pid=pid), "daily-limit")
        self.assertEqual(self.replies(), [conversation.DAILY_LIMIT])
        self.assertEqual(len(self.drafts()), drafts)


class CapTests(CapTestCase):
    def test_third_text_gets_one_limit_reply_and_no_draft(self):
        self.propose("hours")
        self.propose("desc")
        self.limited("desc2")
        self.limited("status please")  # command-like wording is still a change request: no bypass
        self.assertEqual(self.interp.calls, 2)
        self.assertEqual(self.status()[:2], ["Everything is ready.", "I'm close to the number of new requests I can read today."])
        self.conv = self.open()  # restart keeps the count
        self.limited("hours")
        self.assertEqual(self.interp.calls, 2)

    def test_commands_approval_undo_and_memory_still_work_over_the_cap(self):
        hours, _ = self.propose("hours")
        self.propose("desc")
        self.limited()
        self.assertEqual(self.say(f"yes {hours['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        self.replies()
        self.assertEqual(self.say("undo"), "proposed")
        self.assertTrue(self.replies()[0].startswith("To undo that, I'd change it back:"))
        self.assertEqual(self.say("remember parking: back lot"), "memory-saved")
        self.assertEqual(self.say("history"), "history")
        self.assertEqual(self.say("no"), "no-target")  # two drafts wait (desc and the undo): Hass asks which
        self.replies()
        self.assertEqual(self.status()[1], "I'm close to the number of new requests I can read today.")
        self.assertEqual(tuple(self.conv.db.execute("SELECT day, calls FROM usage").fetchone()), ("2026-11-02", 2))
        self.assertEqual(self.interp.calls, 2)
        self.limited("desc2")

    def test_next_local_day_counts_from_zero(self):
        self.propose("hours")
        self.propose("desc")
        self.now = datetime(2026, 11, 3, 7, 59, tzinfo=timezone.utc)  # UTC date is the 3rd; local is 2 Nov 23:59 PST
        self.limited("desc2")
        self.now = datetime(2026, 11, 3, 8, 1, tzinfo=timezone.utc)  # 00:01 PST on 3 Nov: a new local day
        self.assertEqual(self.status()[1], "Nothing is waiting for your yes.")
        self.assertEqual(self.say("when?"), "question")
        self.replies()
        self.assertEqual((self.interp.calls, self.status()[1]), (3, "Nothing is waiting for your yes."))
        rows = [tuple(r) for r in self.conv.db.execute("SELECT day, calls FROM usage ORDER BY day")]
        self.assertEqual(rows, [("2026-11-02", 2), ("2026-11-03", 1)])  # old day kept

    def test_failed_and_unreadable_calls_still_count(self):
        self.assertEqual(self.say("boom"), "unsupported")
        self.assertEqual(self.replies(), [SORRY])
        self.assertEqual(self.say("junk"), "unsupported")
        self.assertEqual(self.replies(), [SORRY])
        self.limited("hours")
        self.assertEqual((self.interp.calls, self.drafts()), (2, []))

    def test_duplicate_delivery_never_counts_twice(self):
        self.assertEqual(self.say("when?", pid="d1"), "question")
        self.assertEqual(self.say("when?", pid="d1"), "duplicate")
        self.assertEqual(self.say("hours", pid="d1"), "duplicate")
        self.assertEqual((self.interp.calls, self.status()[1]), (1, "Nothing is waiting for your yes."))
        self.propose("hours")
        self.limited(pid="d2")
        self.assertEqual(self.say("desc", pid="d2"), "duplicate")  # a redelivered limited message stays limited
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.interp.calls, 2)


class NoCapTests(CapTestCase):
    CAP = None

    def test_absent_or_null_cap_changes_nothing(self):
        for settings in (SETTINGS, {**SETTINGS, "interpreterDailyCap": None}):
            with self.subTest(settings=settings):
                self.set_settings(settings)
                self.conv = self.open()
                self.assertIsNone(self.conv.settings["interpreterDailyCap"])
                for text in ("when?", "when?", "when?"):
                    self.assertEqual(self.say(text), "question")
                self.assertNotIn("usage", self.tables())
                self.assertFalse([ln for ln in self.status() if ln.startswith("Interpreter")])
        with self.assertRaises(RuntimeError):  # no cap: a raising interpreter behaves as before
            self.say("boom")
        self.assertNotIn("usage", self.tables())

    def test_invalid_cap_refuses_to_start(self):
        for bad in (0, -1, True, "5", 10001, 2.0):
            with self.subTest(cap=bad):
                self.set_settings({**SETTINGS, "interpreterDailyCap": bad})
                with self.assertRaisesRegex(conversation.ConfigError, "interpreterDailyCap must be an integer 1-10000"):
                    self.open()
        for good in (1, 10000):
            self.set_settings({**SETTINGS, "interpreterDailyCap": good})
            self.assertEqual(self.open().settings["interpreterDailyCap"], good)


if __name__ == "__main__":
    unittest.main()
