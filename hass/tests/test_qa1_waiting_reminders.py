"""AV2007-02 (QA1-10): `undo` and thanks name the change that still waits, with its own `no <code>`; nothing is approved or dropped.

Same H06 setup (temp Git repo, private state dir, injected clock).
Run: python3 -B -m unittest hass.tests.test_qa1_waiting_reminders -q
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_editor import HOURS, _req
from hass.tests.test_undo import H06TestCase

THUMB = "\U0001F44D"
NOTHING_SAVED = "Nothing has been saved yet."
FIXED = "Nothing changed. Tell me what you'd like to change, or say help."


class WaitingReminderTests(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping["half"] = {"ops": _req((HOURS, {}))["ops"], "revises": None}  # hours without the hours: a question stays open

    def usage(self):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'usage'").fetchone(): return []
        return [tuple(r) for r in self.conv.db.execute("SELECT day, calls FROM usage ORDER BY day")]

    def untouched(self, before, commits=0):
        self.assertEqual(self.drafts(), before)
        self.assertEqual((self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], self.commits()), (0, commits))

    def test_pending_only_undo_names_change_and_coded_no(self):
        draft, _ = self.propose("hours")
        before = self.drafts()
        self.assertEqual(self.say("undo"), "no-target")
        [reply] = self.replies()
        self.assertTrue(reply.startswith(NOTHING_SAVED), reply)
        self.assertIn(draft["summary"], reply)
        self.assertIn(f"no {draft['code']}", reply)
        self.assertNotIn("nothing to undo", reply.lower())
        self.assertNotIn("To undo that", reply)  # pending-only undo must not propose reverting a saved change
        self.untouched(before)
        self.assertEqual(self.say(f"no {draft['code']}"), "rejected")  # the explicit coded no is what drops it
        self.assertEqual(self.drafts()[-1]["state"], "rejected")

    def test_thanks_and_thumb_do_not_answer_second_yes(self):
        draft, _ = self.propose("hours")
        before, usage = self.drafts(), self.usage()
        self.interp.mapping.clear()  # a model call would now fail loudly
        for text, disposition in (("thanks", "social"), ("Thank you!", "social"), (THUMB, "near-approval")):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), disposition)
                [reply] = self.replies()
                self.assertIn(draft["summary"], reply)
                self.assertNotIn("Nothing changed", reply)
                if disposition == "social": self.assertIn(f"no {draft['code']}", reply)
                else: self.assertIn(f"yes {draft['code']}", reply)
                self.untouched(before)
        self.assertEqual(self.usage(), usage)

    def test_saved_plus_pending_undo_keeps_saved_target(self):
        saved = self.apply("desc")
        waiting, _ = self.propose("hours")
        commits = self.commits()
        self.assertEqual(self.say("undo"), "proposed")
        [reply] = self.replies()
        self.assertIn("To undo that, I'd change it back:", reply)
        self.assertIn(waiting["summary"], reply)
        self.assertIn(f"no {waiting['code']}", reply)
        rows = self.drafts()
        self.assertEqual(self.commits(), commits)  # the undo is only proposed
        self.assertEqual([r["state"] for r in rows if r["code"] in (saved["code"], waiting["code"])], ["verified", "proposed"])
        self.assertIn('"changeId": "' + saved["change_id"] + '"', rows[-1]["ops_json"])  # same history.revert target as before
        self.assertEqual(rows[-1]["state"], "proposed")

    def test_undo_with_nothing_waiting_keeps_exact_legacy_replies(self):
        self.assertEqual(self.say("undo"), "no-target")
        self.assertEqual(self.replies(), ["There's nothing to undo."])
        self.assertEqual(self.say("thanks"), "social")
        self.assertEqual(self.replies(), [FIXED])
        self.assertEqual(self.say("undo 0000"), "no-target")
        self.assertEqual(self.replies(), ["I don't have a change with that code to undo."])

    def test_coded_undo_without_target_stays_not_found_and_adds_reminder(self):
        draft, _ = self.propose("hours")
        self.assertEqual(self.say("undo 0000"), "no-target")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("I don't have a change with that code to undo."), reply)
        self.assertIn(f"no {draft['code']}", reply)
        self.assertEqual(self.drafts()[-1]["state"], "proposed")

    def test_multiple_waiting_and_needs_details_are_honest(self):
        one, _ = self.propose("hours")
        two, _ = self.propose("desc")
        self.assertEqual(self.say("thanks"), "social")
        [reply] = self.replies()
        for d in (one, two):
            self.assertIn(d["summary"], reply)
            self.assertIn(f"no {d['code']}", reply)
        self.assertLess(reply.index(one["code"]), reply.index(two["code"]))
        self.assertEqual(len([d for d in self.drafts() if d["state"] == "proposed"]), 2)

    def test_needs_details_is_not_called_ready_to_save(self):
        self.assertEqual(self.say("half"), "needs-details")
        self.replies()
        self.assertEqual(self.say("thanks"), "social")
        [reply] = self.replies()
        self.assertIn("still needs an answer", reply)
        self.assertNotIn("waiting for your yes", reply)

    def test_expired_and_closed_changes_are_not_mentioned(self):
        closed, _ = self.propose("hours")
        self.assertEqual(self.say(f"no {closed['code']}"), "rejected")
        self.replies()
        self.assertEqual(self.say("thanks"), "social")
        self.assertEqual(self.replies(), [FIXED])
        lapsing, _ = self.propose("desc")
        self.now += timedelta(seconds=601)  # SETTINGS approvalTtlSeconds is 600
        self.assertEqual(self.say("undo"), "no-target")
        self.assertEqual(self.replies(), ["There's nothing to undo."])
        self.assertEqual(self.drafts()[-1]["state"], "expired")
        self.assertEqual(self.drafts()[-1]["code"], lapsing["code"])

    def test_duplicate_delivery_gets_one_reply(self):
        self.propose("hours")
        self.assertEqual(self.say("thanks", pid="dup1"), "social")
        self.assertEqual(self.say("thanks", pid="dup1"), "duplicate")
        self.assertEqual(len(self.replies()), 1)


if __name__ == "__main__":
    unittest.main()
