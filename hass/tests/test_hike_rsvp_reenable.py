"""AVB-14 tests: turning RSVPs back on with the stored capacity checks it against the confirmed guests.

Reuses the test_hike_ops fixture repo (throwaway Git repo, private temp state dir, placeholder RSVP rows only).
Run: python3 -m unittest hass.tests.test_hike_rsvp_reenable -v
"""

import unittest

from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

OFF = {**HIKE, "rsvpEnabled": False, "capacity": 6}
OFF_BARE = {k: v for k, v in OFF.items() if k != "capacity"}
ON = ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True})
STORED = f"{HIKE_ID}: RSVPs turned on with the stored capacity "


class ReenableTests(HikeTestCase):
    def hike_repo(self, args=OFF, rows=None):
        repo = self.repo()
        repo.run(("hike.create", args))
        if rows is not None:
            repo.make_db(rows)
        return repo

    def refusal(self, repo, text, *ops):
        before = repo.community()
        result = self.assertRejected(repo, "refused", *ops)
        self.assertEqual(result["reason"], text)
        self.assertEqual(repo.community(), before)  # community.json unchanged on refusal

    def test_stored_capacity_below_confirmed_guests_is_refused_with_the_exact_text(self):
        repo = self.hike_repo({**OFF, "capacity": 4}, rows=[(HIKE_ID, 3), (HIKE_ID, 3)])
        self.refusal(repo, "stored capacity 4 is below 6 confirmed guests; give a new capacity or noCapacityLimit true", ON)
        self.assertFalse(repo.event()["rsvpEnabled"])

    def test_false_no_capacity_limit_does_not_bypass_the_check(self):
        repo = self.hike_repo({**OFF, "capacity": 4}, rows=[(HIKE_ID, 6)])
        self.refusal(repo, "stored capacity 4 is below 6 confirmed guests; give a new capacity or noCapacityLimit true",
                     ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "noCapacityLimit": False}))

    def test_other_changes_in_the_same_update_do_not_bypass_the_check(self):
        repo = self.hike_repo({**OFF, "capacity": 4}, rows=[(HIKE_ID, 6)])
        self.refusal(repo, "stored capacity 4 is below 6 confirmed guests; give a new capacity or noCapacityLimit true",
                     ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "title": "Renamed"}))

    def test_capacity_equal_to_confirmed_guests_is_allowed_with_todays_warning(self):
        repo = self.hike_repo(rows=[(HIKE_ID, 4), (HIKE_ID, 2)])
        draft = repo.run(ON)
        self.assertEqual(draft["warnings"], [STORED + "6"])
        self.assertEqual((repo.event()["rsvpEnabled"], repo.event()["capacity"]), (True, 6))

    def test_a_given_capacity_takes_the_unchanged_given_path(self):
        repo = self.hike_repo({**OFF, "capacity": 4}, rows=[(HIKE_ID, 6)])
        draft = repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "capacity": 8}))
        self.assertEqual(draft["warnings"], [])
        self.assertEqual((repo.event()["rsvpEnabled"], repo.event()["capacity"]), (True, 8))
        repo = self.hike_repo({**OFF, "capacity": 4}, rows=[(HIKE_ID, 6)])
        self.refusal(repo, "capacity 5 is below 6 confirmed guests",
                     ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "capacity": 5}))

    def test_no_capacity_limit_removes_the_capacity(self):
        repo = self.hike_repo({**OFF, "capacity": 4}, rows=[(HIKE_ID, 6)])
        repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "noCapacityLimit": True}))
        self.assertTrue(repo.event()["rsvpEnabled"])
        self.assertNotIn("capacity", repo.event())

    def test_unset_guest_database_refuses_and_changes_nothing(self):
        repo = self.hike_repo()
        self.refusal(repo, "guest count unavailable", ON)
        self.assertFalse(repo.event()["rsvpEnabled"])

    def test_unreadable_guest_database_refuses(self):
        repo = self.hike_repo()
        repo.use_db(str(repo.db.parent / "missing.sqlite3"))
        self.refusal(repo, "guest count unavailable", ON)

    def test_no_stored_capacity_still_asks_the_capacity_question(self):
        repo = self.hike_repo(OFF_BARE, rows=[(HIKE_ID, 6)])
        result = self.assertRejected(repo, "needs-details", ON)
        self.assertEqual(result["missing"], ["capacity", "noCapacityLimit"])

    def test_already_on_events_skip_the_check(self):
        repo = self.hike_repo(HIKE)  # no guest database: an unneeded check would refuse
        repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "title": "Same"}))
        self.assertEqual(repo.event()["title"], "Same")


if __name__ == "__main__":
    unittest.main()
