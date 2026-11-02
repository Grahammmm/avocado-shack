"""RF1130-5 tests: hike.update turning RSVPs on for an event without a capacity asks for capacity or noCapacityLimit.

Reuses the test_hike_ops fixture repo (throwaway Git repo, private temp state dir, placeholder RSVP rows only).
Run: python3 -m unittest hass.tests.test_hike_rsvp_on -v
"""

import unittest

from hass.ops import hikes
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

OFF = {k: v for k, v in HIKE.items() if k != "capacity"} | {"rsvpEnabled": False}


class TurnRsvpOnTests(HikeTestCase):
    def off_repo(self, **extra):
        repo = self.repo()
        repo.run(("hike.create", {**OFF, **extra}))
        return repo

    def assertAsks(self, repo, args):
        result = self.assertRejected(repo, "needs-details", ("hike.update", {"id": HIKE_ID, **args}))
        self.assertEqual(result["missing"], ["capacity", "noCapacityLimit"])
        return result

    def test_turning_on_without_capacity_asks_with_the_create_question(self):
        repo = self.off_repo()
        result = self.assertAsks(repo, {"rsvpEnabled": True})
        create = self.assertRejected(repo, "needs-details", ("hike.create", {**OFF, "rsvpEnabled": True}))
        self.assertEqual(result["question"], create["question"])
        self.assertEqual(result["question"], hikes.CAPACITY_QUESTION)
        self.assertEqual(self.assertAsks(repo, {"rsvpEnabled": True, "title": "Renamed"})["question"],
                         hikes.CAPACITY_QUESTION)
        event = repo.event()
        self.assertEqual((event["rsvpEnabled"], event["title"]), (False, "Test hike"))
        self.assertNotIn("capacity", event)

    def test_false_no_capacity_limit_counts_as_not_given(self):
        repo = self.off_repo()
        self.assertAsks(repo, {"rsvpEnabled": True, "noCapacityLimit": False})
        self.assertFalse(repo.event()["rsvpEnabled"])

    def test_turning_on_with_capacity_is_applied(self):
        repo = self.off_repo()
        repo.make_db([])
        repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "capacity": 8}))
        event = repo.event()
        self.assertEqual((event["rsvpEnabled"], event["capacity"]), (True, 8))

    def test_turning_on_with_no_capacity_limit_is_applied(self):
        repo = self.off_repo()
        repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "noCapacityLimit": True}))
        event = repo.event()
        self.assertTrue(event["rsvpEnabled"])
        self.assertNotIn("capacity", event)

    def test_both_given_keeps_the_existing_not_both_question(self):
        repo = self.off_repo()
        result = self.assertAsks(repo, {"rsvpEnabled": True, "capacity": 8, "noCapacityLimit": True})
        self.assertEqual(result["question"], "Give either a new capacity or noCapacityLimit true, not both.")

    def test_turning_on_keeps_an_existing_capacity(self):
        repo = self.off_repo(capacity=10)
        repo.make_db([])
        repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": True}))
        event = repo.event()
        self.assertEqual((event["rsvpEnabled"], event["capacity"]), (True, 10))

    def test_already_on_is_unchanged(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "title": "x"}))
        event = repo.event()
        self.assertEqual((event["rsvpEnabled"], event["capacity"], event["title"]), (True, 12, "x"))
        # Already on with no limit (no capacity key): repeating rsvpEnabled true asks nothing either.
        repo.run(("hike.create", {**OFF, "title": "Open", "rsvpEnabled": True, "noCapacityLimit": True}))
        open_id = "hike-2026-12-05-open"
        repo.run(("hike.update", {"id": open_id, "rsvpEnabled": True, "title": "Open walk"}))
        self.assertNotIn("capacity", repo.event(open_id))
        self.assertEqual(repo.event(open_id)["title"], "Open walk")

    def test_off_or_untouched_rsvps_ask_nothing(self):
        repo = self.off_repo()
        repo.run(("hike.update", {"id": HIKE_ID, "title": "Still off"}))
        repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": False, "title": "Off again"}))
        event = repo.event()
        self.assertEqual((event["rsvpEnabled"], event["title"]), (False, "Off again"))

    def test_a_later_op_in_the_same_request_does_not_bypass_the_question(self):
        repo = self.off_repo()
        self.assertRejected(repo, "needs-details", ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True}),
                            ("hike.update", {"id": HIKE_ID, "noCapacityLimit": True}))
        self.assertFalse(repo.event()["rsvpEnabled"])


if __name__ == "__main__":
    unittest.main()
