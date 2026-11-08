"""AV2022-07 (H05/H17): a whole-message casual yes (ok, yes please, go ahead, sure, ...) never approves anything.

It gets one reply naming the exact `yes <code>` to send: no approval row, no state move, no interpreter call and no
H22 usage count. Same H06 setup (temp Git repo, private state dir, injected clock).
Run: python3 -m unittest hass.tests.test_near_approval -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_editor import HOURS, _req
from hass.tests.test_undo import H06TestCase


class TextInterpreter(conversation.FixtureInterpreter):
    """FixtureInterpreter that records every text it is asked to interpret."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.texts = []

    def interpret(self, text, pending, **kw):
        self.texts.append(text)
        return super().interpret(text, pending)


class NearApprovalTests(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp = TextInterpreter({**self.interp.mapping, "half": {"ops": _req((HOURS, {}))["ops"], "revises": None}})
        self.conv = self.open()

    def proposal(self, text="hours"):
        draft, _reply = self.propose(text)
        self.interp.texts.clear()
        return draft

    def approvals(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def usage(self):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'usage'").fetchone(): return []
        return [tuple(r) for r in self.conv.db.execute("SELECT day, calls FROM usage ORDER BY day")]

    def near(self, text, reply):
        drafts, usage = self.drafts(), self.usage()
        self.assertEqual(self.say(text), "near-approval")
        self.assertEqual(self.replies(), [reply])
        self.assertEqual((self.drafts(), self.approvals(), self.commits()), (drafts, 0, 0))
        self.assertEqual((self.interp.texts, self.usage()), ([], usage))
        last = self.conv.db.execute("SELECT disposition FROM messages ORDER BY rowid DESC LIMIT 1").fetchone()[0]
        self.assertEqual(last, "near-approval")

    def one(self, code):
        return f"I haven't changed anything yet. To go ahead, reply yes {code}."

    def test_ok_with_one_proposal_names_its_yes_code(self):
        draft = self.proposal()
        self.near("OK!", self.one(draft["code"]))
        self.assertEqual(self.drafts()[-1]["state"], "proposed")

    def test_other_casual_yeses_and_a_named_code_get_the_same_reply(self):
        code = self.proposal()["code"]
        for text in ("yes please", "Go ahead.", "sure,", "okay", "Yep", "yeah!", "do it", "Sounds good.", "looks good",
                     f"ok {code}", f"Go ahead {code}!", f"  SURE {code.upper()},  "):
            with self.subTest(text=text):
                self.near(text, self.one(code))

    def test_two_proposals_are_listed_in_row_order(self):
        one, two = self.proposal("hours"), self.proposal("desc")
        self.near("ok", f"I haven't changed anything yet. Which one do you want?\nyes {one['code']}: {one['summary']}\nyes {two['code']}: {two['summary']}")
        self.near(f"ok {two['code']}", self.one(two["code"]))  # the named code picks one of them

    def test_nothing_waiting_a_question_or_a_wrong_code_gets_nothing(self):
        self.near("ok", conversation.NOTHING)
        self.assertEqual(self.say("half"), "needs-details")  # only a needs-details question waits
        self.replies()
        self.interp.texts.clear()
        self.near("go ahead", conversation.NOTHING)
        self.assertEqual(self.drafts()[-1]["state"], "needs-details")
        self.proposal()
        self.near("ok 0000", conversation.NOTHING)  # a code that is not waiting

    def test_an_expired_proposal_is_not_named(self):
        self.proposal()
        self.now += timedelta(seconds=601)  # SETTINGS approvalTtlSeconds is 600
        self.assertEqual(self.say("ok"), "near-approval")
        self.assertEqual(self.replies(), [conversation.NOTHING])
        self.assertEqual((self.drafts()[-1]["state"], self.approvals(), self.interp.texts), ("expired", 0, []))

    def test_a_longer_message_still_reaches_the_interpreter(self):
        self.proposal()
        for text in ("ok, and make the avocado description shorter", "ok ok", "sure thing", "ok go ahead"):
            with self.subTest(text=text):
                self.assertNotEqual(self.say(text), "near-approval")
                self.replies()
                self.assertEqual(self.interp.texts[-1], text)
        self.assertEqual(self.approvals(), 0)

    def test_yes_still_approves_and_a_photo_caption_is_not_a_near_approval(self):
        code = self.proposal()["code"]
        self.near("ok", self.one(code))
        self.assertEqual(self.say(f"yes {code}"), "approved")
        self.assertEqual((self.approvals(), self.commits()), (1, 1))
        self.replies()
        self.proposal("desc")
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual((self.approvals(), self.commits()), (2, 2))
        self.replies()
        self.n += 1
        photo = conversation.Inbound(f"m{self.n}", self.conv.settings["ownerChat"], self.conv.settings["ownerSenders"][0],
                                     "okay", received_at=self.now.isoformat(), attachments=1)
        self.assertEqual(self.conv.handle(photo), "attachment-unsupported")
        self.assertEqual(self.replies(), [conversation.ATTACHMENT_REPLY])
        self.assertEqual(self.interp.texts, [])

    def test_daily_cap_used_up_does_not_stop_or_count_a_near_approval(self):
        self.set_settings({**SETTINGS, "interpreterDailyCap": 1})
        self.conv = self.open()
        code = self.proposal()["code"]
        self.assertEqual(self.usage()[0][1], 1)
        self.near("ok", self.one(code))
        self.assertEqual(self.say("desc"), "daily-limit")  # the cap still applies to real requests
        self.assertEqual(self.replies(), [conversation.DAILY_LIMIT])

    def test_paused_reply_is_unchanged_and_a_later_yes_is_still_paused(self):
        code = self.proposal()["code"]
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.near("go ahead", self.one(code))
        self.assertEqual(self.say(f"yes {code}"), "paused")
        self.assertEqual(self.replies(), ["Changes are paused, so I haven't saved that. Say resume changes, then reply "
                                          f"yes {code}."])
        self.assertEqual((self.approvals(), self.drafts()[-1]["state"]), (0, "proposed"))

    def test_duplicate_delivery_of_a_near_approval_is_not_answered_twice(self):
        code = self.proposal()["code"]
        self.assertEqual(self.say("ok", pid="n1"), "near-approval")
        self.assertEqual(self.replies(), [self.one(code)])
        self.assertEqual(self.say("ok", pid="n1"), "duplicate")
        self.assertEqual((self.replies(), self.approvals()), ([], 0))


if __name__ == "__main__":
    unittest.main()
