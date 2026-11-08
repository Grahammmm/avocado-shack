"""AV0022-13 (H13): store.set_hours refusals count lines from 1, as the owner does, and the over-limit refusal says
how many lines were sent. Throwaway writer repo (test_store_ops.StoreRepo) and the H05 fixture conversation only.
Run: python3 -m unittest hass.tests.test_store_hours_numbering -v
"""

import unittest

from hass import conversation
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_store_ops import SET_HOURS, StoreTestCase, _req

LONG = "hours line {} is longer than 60 characters"


class HoursNumberingTests(StoreTestCase):
    def refused(self, repo, hours):
        out = repo.prepare(_req((SET_HOURS, {"hours": hours})))
        self.assertEqual(out["result"], "refused", out)
        self.assertEqual(repo.drafts(), [])
        return out["reason"]

    def accepted(self, repo, hours):
        repo.run((SET_HOURS, {"hours": hours}))
        self.assertEqual(repo.store()["hours"], hours)

    def test_single_long_line_is_line_1_and_60_is_accepted(self):
        repo = self.repo()
        self.assertEqual(self.refused(repo, ["a" * 61]), LONG.format(1))
        self.accepted(repo, ["a" * 60])

    def test_first_long_line_is_named(self):
        repo = self.repo()
        self.assertEqual(self.refused(repo, ["Mon 9-5", "Tue 9-5", "c" * 61]), LONG.format(3))
        self.assertEqual(self.refused(repo, ["Mon 9-5", "b" * 61, "Wed 9-5", "d" * 70]), LONG.format(2))

    def test_count_refusal_says_how_many_were_sent_and_comes_first(self):
        repo = self.repo()
        self.assertEqual(self.refused(repo, [f"Day {n}" for n in range(8)]), "at most 7 hours lines (you sent 8)")
        nine = [f"Day {n}" for n in range(8)] + ["z" * 61]
        self.assertEqual(self.refused(repo, nine), "at most 7 hours lines (you sent 9)")
        self.accepted(repo, [f"Day {n}" for n in range(7)])

    def test_repeat_refusal_unchanged(self):
        self.assertEqual(self.refused(self.repo(), ["Closed", "closed"]), "hours lines 1 and 2 say the same thing")


class ConversationNumberingTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def test_owner_reply_counts_from_1(self):
        self.interp.mapping["hours"] = _ops((SET_HOURS, {"hours": ["a" * 61, "Closed Sunday"]}))
        self.assertEqual(self.say("hours"), "not-drafted")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("That's too long for the website. Could you make it a bit shorter?"), reply)
        self.assertEqual(self.drafts(), [])


if __name__ == "__main__":
    unittest.main()
