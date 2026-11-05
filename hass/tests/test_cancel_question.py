"""AV1537-02 (H17): `no`/`cancel`/`reject` (bare or with a code) closes a waiting needs-details question.

The question moves to `rejected` (reason `owner`) and nothing is left to fill later; `yes` never approves a question.
Run: python3 -B -m unittest hass.tests.test_cancel_question -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests import test_needs_details_expiry as h16
from hass.tests.test_conversation import T0


class CancelQuestionTests(h16.NeedsDetailsExpiryTests):
    def approvals(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def closed(self, row):
        got = self.state(row)
        return got["state"], got["reason"]

    def assert_nothing_applied(self):
        self.assertEqual((self.approvals(), self.commits(), self.editor.applies), (0, 0, 0))

    def test_bare_no_cancels_the_only_question_and_a_later_fill_starts_fresh(self):
        q = self.ask()
        self.assertEqual(self.say("No!"), "rejected")  # wording: capitals and a trailing "!" are the same keyword
        self.assertEqual(self.replies(), [f"Cancelled {q['code']}; nothing changed."])
        self.assertEqual(self.closed(q), ("rejected", "owner"))
        self.assertEqual(self.say("no"), "no-target")  # duplicate cancel: nothing is waiting any more
        self.assertEqual(self.replies(), [conversation.NOTHING])
        self.assertEqual(self.say(f"cancel {q['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"{q['code']} was cancelled (owner); nothing changed."])
        self.assertNotIn(q["code"], self.status())
        self.assertEqual(self.answer("done", q["code"]), "proposed")  # the late fill is a new request
        self.replies()
        self.assertEqual(self.interp.pendings[-1], [])
        old, new = self.drafts()
        self.assertEqual((old["state"], old["reason"], old["replaced_by"]), ("rejected", "owner", None))
        self.assertEqual(new["state"], "proposed")
        self.assertNotEqual(new["code"], q["code"])
        self.assertEqual(self.say(f"yes {q['code']}"), "no-target")  # the cancelled question never reopens
        self.assertEqual(self.replies(), [f"{q['code']} was cancelled (owner); nothing changed."])
        self.assert_nothing_applied()

    def test_code_names_only_one_of_a_proposal_and_a_question(self):
        draft, _reply = self.propose("hours")
        q = self.ask()
        self.assertEqual(self.say(f"CANCEL {q['code']}."), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {q['code']}; nothing changed."])
        self.assertEqual((self.closed(q), self.state(draft)["state"]), (("rejected", "owner"), "proposed"))
        q2 = self.ask_at(self.now)["row"]
        self.assertEqual(self.say(f"reject {draft['code']}"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {draft['code']}; nothing changed."])
        self.assertEqual((self.closed(draft), self.state(q2)["state"]), (("rejected", "owner"), "needs-details"))
        self.assertEqual(self.say("cancel beef"), "no-target")  # an unknown code closes nothing
        self.assertEqual(self.replies(), ["No draft beef."])
        self.assertEqual(self.state(q2)["state"], "needs-details")
        self.assert_nothing_applied()

    def test_bare_no_with_a_proposal_and_a_question_asks_which(self):
        draft, _reply = self.propose("hours")
        q = self.ask()
        self.assertEqual(self.say("no"), "no-target")
        [reply] = self.replies()
        self.assertEqual(reply.splitlines(), ["Which draft do you mean?", f"{draft['code']}: {draft['summary']}",
                                              f"{q['code']}: needs details: {q['summary']}",
                                              "Reply yes <code> or no <code>."])
        self.assertEqual((self.state(draft)["state"], self.state(q)["state"]), ("proposed", "needs-details"))

    def test_yes_never_approves_a_question(self):
        q = self.ask()
        still = f"{q['code']} still needs details: {q['summary']}"
        self.assertEqual(self.say("yes"), "no-target")  # bare yes repeats the only waiting question (AV1737-05)
        self.assertEqual(self.replies(), [still])
        for text in (f"yes {q['code']}", f"Approve {q['code']}!", f"approved {q['code']}."):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "no-target")
                self.assertEqual(self.replies(), [still])
        draft, _reply = self.propose("desc")
        self.assertEqual(self.say(f"yes {q['code']}"), "no-target")  # the code names the question, not the draft
        self.assertEqual(self.replies(), [still])
        self.assertEqual((self.state(q)["state"], self.state(draft)["state"]), ("needs-details", "proposed"))
        self.assert_nothing_applied()

    def test_expired_question_is_not_cancelled(self):
        q = self.ask()
        self.now = T0 + h16.TTL + timedelta(seconds=1)
        expired = f"{q['code']} expired at 2026-11-02 09:10 PST; nothing changed."
        self.assertEqual(self.say("no"), "no-target")
        self.assertEqual(self.replies(), [expired])
        self.assertEqual(self.say("cancel"), "no-target")
        self.assertEqual(self.replies(), [conversation.NOTHING])
        self.assertEqual(self.say(f"no {q['code']}"), "no-target")
        self.assertEqual(self.replies(), [expired])
        self.assertEqual(self.state(q)["state"], "expired")

    def test_no_closes_a_question_while_paused(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        q = self.ask()
        self.assertEqual(self.say("no"), "rejected")
        self.assertEqual(self.replies(), [f"Cancelled {q['code']}; nothing changed."])
        self.assertEqual(self.closed(q), ("rejected", "owner"))
        self.assert_nothing_applied()

    def test_a_cancelled_proposal_named_later_still_asks(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.assertEqual(self.answer("done", draft["code"]), "question")  # scope: only questions start fresh
        self.assertEqual(self.replies(), [f"I could not find draft {draft['code']} waiting; reply with the change again."])
        self.assertEqual(len(self.drafts()), 1)


# Reuse the H16 helpers only; the inherited H16 tests already run in their own module (None is not collected).
for _name in [n for n in vars(h16.NeedsDetailsExpiryTests) if n.startswith("test_")]:
    setattr(CancelQuestionTests, _name, None)

if __name__ == "__main__":
    unittest.main()
