"""AVB-03 (H05): a yes sent before its target draft was proposed never approves it.

A reply the owner sent while the service was down may be delivered after the draft it was meant for was cancelled and a
different one proposed. The send time (received_at) is compared with the proposal time; a yes (bare or with a code) sent
earlier is answered, not applied. `no` is unchanged. Same setup as test_late_yes (temp Git repo, injected clock).
Run: python3 -m unittest hass.tests.test_yes_before_proposal -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import CHAT, OWNER, T0, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS

PROPOSED_B = T0 + timedelta(minutes=5)  # A is cancelled at 09:01 PST, B is proposed at 09:05 PST
HANDLED = T0 + timedelta(minutes=6)  # the delayed reply is handled at 09:06 PST
BEFORE_B = (PROPOSED_B - timedelta(seconds=1)).isoformat()


class YesBeforeProposalTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.a, _reply = self.propose("hours")
        self.now = T0 + timedelta(minutes=1)
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.now = PROPOSED_B
        self.b, _reply = self.propose("desc")
        self.base = self.count()

    def late(self, text, received_at, now=HANDLED):
        self.now, self.n = now, self.n + 1
        return self.conv.handle(conversation.Inbound(f"m{self.n}", CHAT, OWNER, text, False, "new", received_at))

    def approvals(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM approvals")]

    def refusal(self):
        return f"That yes was sent before {self.b['code']} was proposed; reply yes {self.b['code']} to apply it."

    def assert_refused(self, text, received_at=BEFORE_B):
        self.assertEqual(self.late(text, received_at), "no-target")
        self.assertEqual(self.replies(), [self.refusal()])
        row = self.drafts()[-1]
        self.assertEqual((row["state"], row["expires_at"], self.approvals(), self.commits(), self.editor.applies),
                         ("proposed", self.b["expires_at"], [], 0, 0))

    def test_bare_yes_sent_before_the_draft_was_proposed_is_refused(self):
        self.assert_refused("yes")

    def test_a_refused_yes_leaves_the_draft_approvable_by_a_yes_sent_after_it(self):
        self.assert_refused("yes")
        self.assertEqual(self.late(f"yes {self.b['code']}", HANDLED.isoformat(), now=HANDLED), "approved")
        self.replies()
        self.assertEqual((self.drafts()[-1]["state"], self.commits(), len(self.approvals())), ("applied", 1, 1))

    def test_a_code_does_not_override_the_send_time(self):
        self.assert_refused(f"yes {self.b['code']}")

    def test_the_cancelled_draft_code_is_not_a_way_round_it(self):
        self.assertEqual(self.late(f"yes {self.a['code']}", BEFORE_B), "no-target")
        self.assertEqual(self.replies(), [f"{self.a['code']} was cancelled (owner); nothing changed."])
        self.assertEqual((self.approvals(), self.commits(), self.editor.applies), ([], 0, 0))

    def test_yes_sent_exactly_at_the_proposal_instant_approves(self):
        self.assertEqual(self.late("yes", PROPOSED_B.isoformat()), "approved")
        self.replies()
        self.assertEqual((self.drafts()[-1]["state"], self.commits()), ("applied", 1))

    def test_yes_sent_one_second_after_the_proposal_approves(self):
        self.assertEqual(self.late("yes", (PROPOSED_B + timedelta(seconds=1)).isoformat()), "approved")

    def test_empty_received_at_is_judged_at_now_and_approves(self):
        self.assertEqual(self.late("yes", ""), "approved")
        self.replies()
        self.assertEqual((self.drafts()[-1]["state"], self.commits()), ("applied", 1))

    def test_naive_received_at_is_judged_at_now_and_approves(self):
        self.assertEqual(self.late("yes", "2026-11-02T17:04:00"), "approved")
        self.replies()
        self.assertEqual((self.drafts()[-1]["state"], self.commits()), ("applied", 1))

    def test_received_at_in_the_future_is_judged_at_now_and_approves(self):
        self.assertEqual(self.late("yes", (HANDLED + timedelta(minutes=9)).isoformat()), "approved")

    def test_no_sent_before_the_draft_was_proposed_still_cancels_it(self):
        self.assertEqual(self.late("no", BEFORE_B), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {self.b['code']}; nothing changed."])
        self.assertEqual((self.drafts()[-1]["state"], self.commits()), ("rejected", 0))

    def test_yes_sent_between_a_question_and_its_fill_is_refused(self):
        self.late("no", HANDLED.isoformat())  # close B so the question is the only open draft
        self.replies()
        self.interp.mapping["q"] = {"ops": _ops((HOURS, {}))["ops"], "revises": None}
        asked = T0 + timedelta(minutes=10)
        self.now = asked
        self.assertEqual(self.say("q"), "needs-details")
        self.replies()
        question = self.drafts()[-1]
        self.assertEqual(question["state"], "needs-details")
        self.interp.mapping["done"] = {**_ops((HOURS, {"hours": ["Daily 8am–7pm"]})), "revises": question["code"]}
        filled = asked + timedelta(minutes=3)
        self.now = filled
        self.assertEqual(self.say("done"), "proposed")
        self.replies()
        row = self.drafts()[-1]
        self.assertEqual((row["code"], row["state"]), (question["code"], "proposed"))
        sent = (asked + timedelta(minutes=1)).isoformat()  # after the question, before the fill
        self.assertEqual(self.late("yes", sent, now=filled + timedelta(minutes=1)), "no-target")
        self.assertEqual(self.replies(), [f"That yes was sent before {row['code']} was proposed; "
                                          f"reply yes {row['code']} to apply it."])
        self.assertEqual((self.drafts()[-1]["state"], self.approvals(), self.editor.applies), ("proposed", [], 0))
        self.assertEqual(self.late("yes", filled.isoformat(), now=filled + timedelta(minutes=1)), "approved")


if __name__ == "__main__":
    unittest.main()
