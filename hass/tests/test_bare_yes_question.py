"""AV1737-05 (H17): a bare `yes` while only needs-details questions wait repeats each question with its code.

A question is never approved: no approval row, no state move, nothing applied. A waiting proposal still wins.
Run: python3 -B -m unittest hass.tests.test_bare_yes_question -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests import test_needs_details_expiry as h16
from hass.tests.test_conversation import T0


class BareYesQuestionTests(h16.NeedsDetailsExpiryTests):
    def still(self, row):
        return f"I still need an answer from you first. {row['summary']}"

    def assert_nothing_applied(self):
        approvals = self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        self.assertEqual((approvals, self.commits(), self.editor.applies), (0, 0, 0))

    def test_bare_yes_and_its_synonyms_repeat_the_only_question(self):
        q = self.ask()
        for text in ("yes", "Yes!", "approve", "APPROVED."):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "no-target")
                self.assertEqual(self.replies(), [self.still(q)])
        self.assertEqual(self.state(q)["state"], "needs-details")
        dispositions = [r[0] for r in self.conv.db.execute("SELECT disposition FROM messages ORDER BY rowid")]
        self.assertEqual(dispositions[-4:], ["no-target"] * 4)
        self.assert_nothing_applied()

    def test_two_questions_are_listed_oldest_first_and_neither_is_approved(self):
        q1 = self.ask()
        q2 = self.ask_at(self.now + timedelta(seconds=5))["row"]
        self.assertNotEqual(q1["code"], q2["code"])
        self.assertEqual(self.say("yes"), "no-target")
        [reply] = self.replies()
        self.assertEqual(reply.splitlines(), [self.still(q1), self.still(q2)])
        self.assertEqual((self.state(q1)["state"], self.state(q2)["state"]), ("needs-details", "needs-details"))
        self.assert_nothing_applied()

    def test_a_waiting_proposal_is_still_approved_and_the_question_is_untouched(self):
        q = self.ask()
        draft, _reply = self.propose("desc")
        self.assertEqual(self.say("yes"), "approved")
        [reply] = self.replies()
        self.assertTrue(reply.startswith(f"Saved: {draft['summary']}"), reply)
        self.assertNotIn(q["code"], reply)
        self.assertEqual(self.state(q)["state"], "needs-details")
        self.assertEqual(self.say("yes"), "no-target")  # now only the question waits
        self.assertEqual(self.replies(), [self.still(q)])

    def test_an_expired_question_is_not_repeated(self):
        q = self.ask()
        self.now = T0 + h16.TTL + timedelta(seconds=1)
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), ["That change timed out today at 9:10 am, so nothing changed. Tell me again if you still want it."])
        self.assertEqual(self.state(q)["state"], "expired")
        self.assertEqual(self.say("yes"), "no-target")  # already swept: nothing is waiting
        self.assertEqual(self.replies(), [conversation.NOTHING])
        self.assert_nothing_applied()

    def test_nothing_waiting_or_a_cancelled_question_keeps_nothing(self):
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), [conversation.NOTHING])
        self.ask()
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), [conversation.NOTHING])
        self.assert_nothing_applied()

    def test_paused_bare_yes_still_repeats_the_question(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        q = self.ask()
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.replies(), [self.still(q)])
        self.assertEqual(self.state(q)["state"], "needs-details")
        self.assert_nothing_applied()


# Reuse the H16 helpers only; the inherited H16 tests already run in their own module (None is not collected).
for _name in [n for n in vars(h16.NeedsDetailsExpiryTests) if n.startswith("test_")]:
    setattr(BareYesQuestionTests, _name, None)

if __name__ == "__main__":
    unittest.main()
