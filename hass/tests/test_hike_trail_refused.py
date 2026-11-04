"""RF1530-3 tests: hike.create / hike.update refuse a trailId that is not a route idea, in the op, with one reply.

Fixture repos only (test_hike_ops helpers). The content validator rule stays as the backstop for hand edits.
"""

import unittest

from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

IDEA = "idea-fiscalini-bluff"
OTHER = {**HIKE, "title": "Other hike"}


class TrailRefusedTests(HikeTestCase):
    def reason(self, repo, op):
        return self.assertRejected(repo, "refused", op)["reason"]

    def test_create_with_an_unknown_trail_is_refused_and_drafts_nothing(self):
        repo = self.repo()
        for trail in ("idea-nowhere", "preview-point-buchon"):
            with self.subTest(trail=trail):
                self.assertEqual(self.reason(repo, ("hike.create", {**HIKE, "trailId": trail})), f"unknown route idea {trail}")
        self.assertEqual(repo.community()["events"], [])

    def test_create_with_another_hikes_id_is_refused(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        self.assertEqual(self.reason(repo, ("hike.create", {**OTHER, "trailId": HIKE_ID})),
                         f"{HIKE_ID} is a hike, not a route idea")
        self.assertEqual([e["id"] for e in repo.community()["events"]], [HIKE_ID])

    def test_update_with_an_unknown_trail_or_a_hike_leaves_the_event_alone(self):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "trailId": IDEA}))
        repo.run(("hike.create", OTHER))
        stored = repo.event()
        self.assertEqual(self.reason(repo, ("hike.update", {"id": HIKE_ID, "trailId": "idea-nowhere"})),
                         "unknown route idea idea-nowhere")
        other_id = next(e["id"] for e in repo.community()["events"] if e["id"] != HIKE_ID)
        self.assertEqual(self.reason(repo, ("hike.update", {"id": HIKE_ID, "trailId": other_id})),
                         f"{other_id} is a hike, not a route idea")
        self.assertEqual(repo.event(), stored)

    def test_a_hidden_idea_keeps_its_own_reply(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE), ("route.hide", {"id": IDEA}))
        self.assertEqual(self.reason(repo, ("hike.create", {**OTHER, "trailId": IDEA})),
                         f"route idea {IDEA} is hidden; restore it first")

    def test_a_real_idea_is_still_drafted_and_a_bad_id_is_still_invalid(self):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "trailId": IDEA}))
        self.assertEqual(repo.event()["trailId"], IDEA)
        repo.run(("hike.update", {"id": HIKE_ID, "clear": ["trailId"]}))
        self.assertNotIn("trailId", repo.event())
        self.assertRejected(repo, "invalid", ("hike.create", {**OTHER, "trailId": "Not A Valid Id!"}))


if __name__ == "__main__":
    unittest.main()
