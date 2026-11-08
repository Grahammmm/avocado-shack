"""AV0022-06 (H16): a yes/no sent before its draft expired but handled later (service down, queued) still counts.

Expiry is judged at the message's received_at, capped at now; only for a keyword reply without an attachment. Every
other message, the approval row and apply stay on the handling clock. Same H05 setup (temp Git repo, injected clock).
Run: python3 -m unittest hass.tests.test_late_yes -v
"""

import unittest
from datetime import timedelta

from hass import conversation
from hass.tests.test_conversation import CHAT, OWNER, T0, ConversationTestCase
from hass.tests.test_editor import DESC, _req

EXPIRES = T0 + timedelta(seconds=600)  # SETTINGS approvalTtlSeconds is 600: the draft expires 09:10 PST
LATE = T0 + timedelta(minutes=40)  # the service handles the queued reply at 09:40 PST
LATE_HEAD = "Sorry for the wait. This answers your message from today at 9:09 am:\n"  # AV0022-10: a reply sent over 15 min after the message


class LateYesTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.conv = self.open()
        self.base = self.count()
        self.draft, _reply = self.propose("hours")
        self.expired_reply = "That change timed out today at 9:10 am, so nothing changed. Tell me again if you still want it."

    def late(self, text, received_at, now=LATE, attachments=0):
        self.now, self.n = now, self.n + 1
        msg = conversation.Inbound(f"m{self.n}", CHAT, OWNER, text, False, "new", received_at, attachments)
        return self.conv.handle(msg)

    def approvals(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM approvals")]

    def state(self):
        return self.drafts()[0]["state"]

    def assert_expired(self, received_at, text="yes", head=""):
        self.assertEqual(self.late(text, received_at), "no-target")
        self.assertEqual(self.replies(), [head + self.expired_reply])
        self.assertEqual((self.state(), self.approvals(), self.commits()), ("expired", [], 0))

    def test_yes_sent_in_time_and_handled_late_approves_on_the_handling_clock(self):
        self.assertEqual(self.late("yes", (EXPIRES - timedelta(seconds=1)).isoformat()), "approved")
        [reply] = self.replies()
        self.assertTrue(reply.startswith(LATE_HEAD + f"Saved: {self.draft['summary']}"), reply)
        self.assertEqual((self.state(), self.commits()), ("applied", 1))
        [row] = self.approvals()
        self.assertEqual((row["approved_at"], row["expires_at"]), (conversation._iso(LATE), self.draft["expires_at"]))

    def test_named_code_sent_in_time_also_approves(self):
        self.assertEqual(self.late(f"yes {self.draft['code']}", (EXPIRES - timedelta(seconds=1)).isoformat()), "approved")
        self.replies()
        self.assertEqual((self.state(), self.commits()), ("applied", 1))

    def test_yes_sent_exactly_at_expiry_is_expired(self):
        self.assert_expired(EXPIRES.isoformat(), head="Sorry for the wait. This answers your message from today at 9:10 am:\n")

    def test_received_at_in_the_future_is_judged_at_now(self):
        self.assert_expired((LATE + timedelta(minutes=20)).isoformat())

    def test_empty_naive_or_bad_received_at_is_judged_at_now(self):
        self.assert_expired("")
        for value in ("2026-11-02T17:09:00", "not a time", "2026-11-02 09:09 PST"):
            with self.subTest(received_at=value):
                self.assertEqual(self.late(f"yes {self.draft['code']}", value), "no-target")
                self.assertEqual(self.replies(), [self.expired_reply])
                self.assertEqual((self.approvals(), self.commits()), ([], 0))

    def test_no_sent_in_time_and_handled_late_cancels(self):
        self.assertEqual(self.late("no", (EXPIRES - timedelta(seconds=1)).isoformat()), "rejected")
        self.assertEqual(self.replies(), [LATE_HEAD + "Okay, I've cancelled that. Nothing changed."])
        self.assertEqual((self.state(), self.drafts()[0]["reason"], self.commits()), ("rejected", "owner", 0))

    def test_text_correction_sent_in_time_is_still_swept_at_now(self):
        self.assertEqual(self.late("desc", (EXPIRES - timedelta(seconds=1)).isoformat()), "proposed")
        self.replies()
        self.assertEqual([d["state"] for d in self.drafts()], ["expired", "proposed"])
        self.assertEqual(self.late("yes", (LATE + timedelta(seconds=1)).isoformat(), now=LATE + timedelta(seconds=1)),
                         "approved")  # the new draft, not the expired one
        self.replies()
        self.assertEqual([d["state"] for d in self.drafts()], ["expired", "applied"])

    def test_photo_caption_yes_is_not_judged_early(self):
        self.assertEqual(self.late("yes", (EXPIRES - timedelta(seconds=1)).isoformat(), attachments=1),
                         "attachment-unsupported")
        self.replies()
        self.assertEqual(self.late("status", LATE.isoformat()), "status")  # read-only: no sweep, nothing approved
        self.replies()
        self.assertEqual(self.approvals(), [])
        self.assert_expired(LATE.isoformat())  # a plain yes sent now is judged now

    def test_late_yes_while_paused_gets_the_paused_reply_and_is_not_swept(self):
        self.now = T0 + timedelta(minutes=5)
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        code = self.draft["code"]
        self.assertEqual(self.late("yes", (EXPIRES - timedelta(seconds=1)).isoformat()), "paused")
        self.assertEqual(self.replies(), [LATE_HEAD + f"Changes are paused, so I haven't saved that. Say resume changes, then reply yes {code}."])
        self.assertEqual((self.state(), self.approvals(), self.commits()), ("proposed", [], 0))
        self.assertEqual(self.late("resume changes", LATE.isoformat()), "resume")  # the next message sweeps it
        self.replies()
        self.assertEqual(self.state(), "expired")

    def test_late_yes_for_a_draft_whose_site_changed_redrafts(self):
        other = self.repo.prepare(_req((DESC, {"id": "photo-product-001", "description": "Picked this week."})))
        self.assertEqual(self.repo.apply(other["draft"])["result"], "applied")
        self.base = self.count()
        self.assertEqual(self.late("yes", (EXPIRES - timedelta(seconds=1)).isoformat()), "approved")
        [reply] = self.replies()
        stale, new = self.drafts()
        self.assertEqual((stale["state"], stale["reason"], self.commits()), ("rejected", "stale", 0))
        self.assertEqual(new["state"], "proposed")
        self.assertTrue(reply.startswith(LATE_HEAD + "The website changed while that was waiting, so I've written it up again. Please look it over:\n"))


if __name__ == "__main__":
    unittest.main()
