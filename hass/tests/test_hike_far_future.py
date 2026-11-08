"""AVB-05 tests (H04): a hike start more than 400 days after now is a question ("check the year"), never a draft.

Reuses the test_hike_ops fixture repo (throwaway Git repo, private temp state dir, fixed injected clock) and the H06
fixture conversation. Run: python3 -m unittest hass.tests.test_hike_far_future -v
"""

import unittest
from datetime import datetime, timedelta, timezone

from hass.ops import hikes
from hass.tests.test_conversation import _ops
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase
from hass.tests.test_undo import H06TestCase

FAR = "2062-11-07"
PST = timezone(timedelta(hours=-8))
QUESTION = "November 7, 2062 is more than 400 days away; check the year. What date should it be?"


class FarFutureTests(HikeTestCase):
    def asks(self, repo, *ops, question=QUESTION):
        before = repo.community()
        result = self.assertRejected(repo, "needs-details", *ops)
        self.assertEqual((result["missing"], result["question"]), (["date"], question))
        self.assertEqual(repo.community(), before)
        return result

    def test_create_far_year_asks_and_drafts_nothing(self):
        self.assertEqual(hikes.MAX_AHEAD_DAYS, 400)
        repo = self.repo()
        self.asks(repo, ("hike.create", {**HIKE, "date": FAR}))
        self.assertEqual(repo.community()["events"], [])

    def test_exactly_400_days_drafts_and_one_minute_more_asks(self):
        repo = self.repo()
        repo.now = datetime(2026, 11, 15, 9, 0, tzinfo=PST)  # both ends are PST: 400 days is exactly 400 x 24 h
        repo.run(("hike.create", {**HIKE, "date": "2027-12-20", "time": "09:00"}))
        self.assertEqual(repo.event("hike-2027-12-20-test-hike")["startsAt"], "2027-12-20T09:00:00-08:00")
        self.asks(repo, ("hike.create", {**HIKE, "title": "Later", "date": "2027-12-20", "time": "09:01"}),
                  question="December 20, 2027 is more than 400 days away; check the year. What date should it be?")
        self.asks(repo, ("hike.create", {**HIKE, "title": "Next day", "date": "2027-12-21"}),
                  question="December 21, 2027 is more than 400 days away; check the year. What date should it be?")

    def test_update_to_far_date_asks_but_other_edits_are_unaffected(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        self.asks(repo, ("hike.update", {"id": HIKE_ID, "date": FAR}))
        self.asks(repo, ("hike.update", {"id": HIKE_ID, "date": FAR, "meetingPoint": "Second lot"}))
        self.assertEqual((repo.event()["startsAt"], repo.event()["meetingPoint"]),
                         ("2026-12-05T09:00:00-08:00", "Test trailhead lot"))
        repo.run(("hike.update", {"id": HIKE_ID, "meetingPoint": "Second lot"}))
        repo.run(("hike.update", {"id": HIKE_ID, "date": "2027-07-04"}))
        self.assertEqual((repo.event()["startsAt"], repo.event()["meetingPoint"]),
                         ("2027-07-04T09:00:00-07:00", "Second lot"))

    def test_later_op_in_the_same_request_does_not_bypass_the_question(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        self.asks(repo, ("hike.update", {"id": HIKE_ID, "title": "Renamed"}),
                  ("hike.update", {"id": HIKE_ID, "date": FAR}))
        self.assertEqual(repo.event()["title"], "Test hike")

    def test_dst_question_wins_over_the_far_date_question(self):
        repo = self.repo()
        gap = self.assertRejected(repo, "needs-details", ("hike.create", {**HIKE, "date": "2062-03-12", "time": "02:30"}))
        repeated = self.assertRejected(repo, "needs-details", ("hike.create", {**HIKE, "date": "2062-11-05", "time": "01:30"}))
        for result in (gap, repeated):
            self.assertEqual(result["missing"], ["time"])
            self.assertNotIn("days away", result["question"])
        self.assertIn("does not exist", gap["question"])
        self.assertIn("happens twice", repeated["question"])

    def test_past_start_is_still_refused(self):
        repo = self.repo()
        for date in ("2026-10-29", "2026-10-30"):
            refused = self.assertRejected(repo, "refused", ("hike.create", {**HIKE, "date": date, "time": "11:00"}))
            self.assertEqual(refused["reason"], "start is in the past")
        repo.run(("hike.create", HIKE))
        refused = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "date": "2026-10-29"}))
        self.assertEqual(refused["reason"], "start is in the past")


class FarFutureConversationTests(H06TestCase):
    def test_owner_text_with_a_far_year_gets_the_question_and_cannot_be_approved(self):
        self.interp.mapping["far"] = _ops(("hike.create", {**HIKE, "date": FAR}))
        self.assertEqual(self.say("far"), "needs-details")
        self.assertEqual(self.replies(), [QUESTION])
        [row] = self.drafts()
        self.assertEqual((row["state"], row["summary"]), ("needs-details", QUESTION))
        self.assertEqual(self.say("yes"), "no-target")  # a question is not a proposal: nothing to approve
        self.assertEqual((self.drafts()[0]["state"], self.commits()), ("needs-details", 0))
        self.assertEqual(self.content("community")["events"], [])


if __name__ == "__main__":
    unittest.main()
