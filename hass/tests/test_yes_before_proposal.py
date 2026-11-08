"""AVB-03 (H05): a yes sent before its target draft was proposed never approves it.

A reply the owner sent while the service was down may be delivered after the draft it was meant for was cancelled and a
different one proposed. The send time (received_at) is compared with the proposal time; a yes (bare or with a code) sent
earlier is answered, not applied. `no` is unchanged. Same setup as test_late_yes (temp Git repo, injected clock).
Run: python3 -m unittest hass.tests.test_yes_before_proposal -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS

PROPOSED_B = T0 + timedelta(minutes=5)  # A is cancelled at 09:01 PST, B is proposed at 09:05 PST
HANDLED = T0 + timedelta(minutes=6)  # the delayed reply is handled at 09:06 PST
BEFORE_B = (PROPOSED_B - timedelta(seconds=1)).isoformat()


class _BeforeB(ConversationTestCase):  # shared setup and helpers; no tests of its own
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

    def restart(self, ttl):
        self.conv.db.close()
        self.set_settings({**SETTINGS, "approvalTtlSeconds": ttl})
        self.conv = self.open()

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


class YesBeforeProposalTests(_BeforeB):
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
        self.assertEqual(self.replies(), ["That one was cancelled, so nothing changed."])
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
        self.assertEqual(self.replies(), ["Okay, I've cancelled that. Nothing changed."])
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
        self.assertEqual(self.replies(), [f"Your yes came before I had written that change up, so I haven't saved it. If you still want it, reply yes {row['code']}."])
        self.assertEqual((self.drafts()[-1]["state"], self.approvals(), self.editor.applies), ("proposed", [], 0))
        self.assertEqual(self.late("yes", filled.isoformat(), now=filled + timedelta(minutes=1)), "approved")


class ProposalTimeSurvivesTtlChangeTests(_BeforeB):
    """AVB-03 review fix: the proposal instant is stored (proposed_at), so a restart with another approvalTtlSeconds
    never moves it. B was proposed at 09:05 PST with ttl 600, so it expires 09:15 PST either way."""

    def test_the_proposal_instant_is_stored(self):
        self.assertEqual(self.b["proposed_at"], conversation._iso(PROPOSED_B))

    def test_a_longer_ttl_after_restart_still_refuses_a_yes_sent_before_the_draft(self):
        self.restart(3600)  # derived from expiry this would be 08:15 PST, before the yes
        self.assert_refused("yes")

    def test_a_longer_ttl_after_restart_still_refuses_a_coded_yes_sent_before_the_draft(self):
        self.restart(3600)
        self.assert_refused(f"yes {self.b['code']}")

    def test_a_shorter_ttl_after_restart_still_approves_a_yes_sent_after_the_draft(self):
        self.restart(60)  # derived from expiry this would be 09:14 PST, after the yes
        self.assertEqual(self.late("yes", (PROPOSED_B + timedelta(seconds=30)).isoformat()), "approved")
        self.replies()
        self.assertEqual((self.drafts()[-1]["state"], self.commits()), ("applied", 1))

    def test_a_filled_question_keeps_its_fill_instant_across_a_restart_with_a_longer_ttl(self):
        self.late("no", HANDLED.isoformat())  # close B so the question is the only open draft
        self.replies()
        self.interp.mapping["q"] = {"ops": _ops((HOURS, {}))["ops"], "revises": None}
        asked = T0 + timedelta(minutes=10)
        self.now = asked
        self.assertEqual(self.say("q"), "needs-details")
        self.replies()
        code = self.drafts()[-1]["code"]
        self.interp.mapping["done"] = {**_ops((HOURS, {"hours": ["Daily 8am–7pm"]})), "revises": code}
        filled = asked + timedelta(minutes=3)
        self.now = filled
        self.assertEqual(self.say("done"), "proposed")
        self.replies()
        self.assertEqual(self.drafts()[-1]["proposed_at"], conversation._iso(filled))
        self.restart(3600)
        sent = (asked + timedelta(minutes=1)).isoformat()  # after the question, before the fill
        self.assertEqual(self.late("yes", sent, now=filled + timedelta(minutes=1)), "no-target")
        self.assertEqual(self.replies(), [f"Your yes came before I had written that change up, so I haven't saved it. If you still want it, reply yes {code}."])
        self.assertEqual(self.late("yes", filled.isoformat(), now=filled + timedelta(minutes=1)), "approved")


class RowsFromBeforeTheColumnTests(_BeforeB):
    """AVB-03 review fix 2: a database from before proposed_at cannot say when an open draft was proposed (a filled
    question keeps its question's created_at), so opening it stamps open drafts with the open instant: a yes sent
    before the restart is refused (the owner re-sends it); a yes sent after it approves."""

    def upgrade(self, at, ttl=3600):
        self.conv.db.execute("ALTER TABLE drafts DROP COLUMN proposed_at")  # a database from before AVB-03's fix
        self.now = at
        self.restart(ttl)

    def test_an_open_draft_is_stamped_with_the_open_instant_and_closed_ones_are_left_empty(self):
        self.upgrade(HANDLED)
        a, b = self.drafts()[-2:]
        self.assertEqual((a["state"], a["proposed_at"]), ("rejected", None))
        self.assertEqual((b["state"], b["proposed_at"]), ("proposed", conversation._iso(HANDLED)))
        self.restart(60)  # a later restart never moves the stamp
        self.assertEqual(self.drafts()[-1]["proposed_at"], conversation._iso(HANDLED))

    def test_a_yes_sent_before_the_upgrade_is_refused_even_after_the_proposal(self):
        self.upgrade(HANDLED)
        self.assert_refused("yes")  # before B
        self.assert_refused("yes", PROPOSED_B.isoformat())  # after B, but its instant is unknown: fail closed
        self.assert_refused(f"yes {self.b['code']}", (HANDLED - timedelta(seconds=1)).isoformat())

    def test_a_yes_sent_after_the_upgrade_approves(self):
        self.upgrade(HANDLED)
        self.assertEqual(self.late("yes", HANDLED.isoformat(), now=HANDLED + timedelta(seconds=5)), "approved")
        self.replies()
        self.assertEqual((self.drafts()[-1]["state"], self.commits()), ("applied", 1))

    def test_a_filled_question_from_before_the_column_never_counts_from_its_question(self):
        # the reviewer's case: question 09:10, fill 09:13 (ttl 600), upgrade + ttl 3600, a yes sent 09:11 at 09:14
        self.late("no", HANDLED.isoformat())  # close B so the question is the only open draft
        self.replies()
        self.interp.mapping["q"] = {"ops": _ops((HOURS, {}))["ops"], "revises": None}
        asked = T0 + timedelta(minutes=10)
        self.now = asked
        self.assertEqual(self.say("q"), "needs-details")
        self.replies()
        code = self.drafts()[-1]["code"]
        self.interp.mapping["done"] = {**_ops((HOURS, {"hours": ["Daily 8am–7pm"]})), "revises": code}
        self.now = asked + timedelta(minutes=3)
        self.assertEqual(self.say("done"), "proposed")
        self.replies()
        opened = asked + timedelta(minutes=4)
        self.upgrade(opened)
        self.assertEqual(self.drafts()[-1]["proposed_at"], conversation._iso(opened))
        refusal = f"That yes was sent before {code} was proposed; reply yes {code} to apply it."
        for sent in (asked + timedelta(minutes=1), asked + timedelta(minutes=3)):  # before / at the fill: unknown
            self.assertEqual(self.late("yes", sent.isoformat(), now=opened), "no-target")
            self.assertEqual(self.replies(), [refusal])
        self.assertEqual((self.drafts()[-1]["state"], self.approvals(), self.editor.applies), ("proposed", [], 0))
        self.assertEqual(self.late("yes", opened.isoformat(), now=opened + timedelta(seconds=5)), "approved")
        self.replies()
        self.assertEqual((self.drafts()[-1]["state"], self.commits()), ("applied", 1))

    def test_an_unfilled_question_from_before_the_column_counts_from_its_fill(self):
        self.late("no", HANDLED.isoformat())
        self.replies()
        self.interp.mapping["q"] = {"ops": _ops((HOURS, {}))["ops"], "revises": None}
        asked = T0 + timedelta(minutes=10)
        self.now = asked
        self.assertEqual(self.say("q"), "needs-details")
        self.replies()
        code = self.drafts()[-1]["code"]
        self.upgrade(asked + timedelta(minutes=1))
        self.assertIsNone(self.drafts()[-1]["proposed_at"])  # a question is not stamped; its fill sets the instant
        self.interp.mapping["done"] = {**_ops((HOURS, {"hours": ["Daily 8am–7pm"]})), "revises": code}
        filled = asked + timedelta(minutes=3)
        self.now = filled
        self.assertEqual(self.say("done"), "proposed")
        self.replies()
        self.assertEqual(self.drafts()[-1]["proposed_at"], conversation._iso(filled))
        self.assertEqual(self.late("yes", (asked + timedelta(minutes=2)).isoformat(), now=filled), "no-target")
        self.replies()
        self.assertEqual(self.late("yes", filled.isoformat(), now=filled + timedelta(seconds=5)), "approved")


if __name__ == "__main__":
    unittest.main()
