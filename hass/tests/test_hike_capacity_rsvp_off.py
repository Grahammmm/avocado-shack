"""RF1240-5 tests: a capacity on an RSVP-off hike, and its reuse when RSVPs are turned on, are named as draft warnings
(never refusals). Fixture repos and placeholder example.invalid RSVP rows only (test_hike_ops / H06 helpers).
"""

import unittest

from hass.tests.test_conversation import _ops
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase, _req
from hass.tests.test_undo import H06TestCase

OFF = {**HIKE, "rsvpEnabled": False, "capacity": 5}
OFF_BARE = {k: v for k, v in OFF.items() if k != "capacity"}
STORED = f"{HIKE_ID}: RSVPs turned on with the stored capacity 5"


def off_warning(n):
    return f"{HIKE_ID}: RSVPs are off, so capacity {n} has no effect until RSVPs are turned on"


class CapacityRsvpOffTests(HikeTestCase):
    def hike_repo(self, args, rows=None):
        repo = self.repo()
        repo.run(("hike.create", args))
        if rows is not None:
            repo.make_db(rows)
        return repo

    def warnings(self, repo, *ops):  # a drafted request's warnings; it still applies
        draft = repo.prepare(_req(*ops))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
        return draft["draft"]["warnings"]

    def assertNoWarning(self, result, reason):
        self.assertEqual(result.get("reason", result.get("missing")), reason)
        self.assertNotIn("warnings", result)
        self.assertNotIn("RSVPs are off", str(result))
        self.assertNotIn("stored capacity", str(result))

    def test_create_rsvps_off_with_capacity_warns_and_keeps_the_event(self):
        repo = self.repo()
        self.assertEqual(self.warnings(repo, ("hike.create", OFF)), [off_warning(5)])
        event = repo.event()
        self.assertEqual((event["rsvpEnabled"], event["capacity"], event["status"]), (False, 5, "scheduled"))

    def test_create_without_the_mismatch_warns_nothing(self):
        for args in (OFF_BARE, HIKE, {**OFF_BARE, "noCapacityLimit": True}):
            with self.subTest(args=args):
                self.assertEqual(self.warnings(self.repo(), ("hike.create", args)), [])
        result = self.assertRejected(self.repo(), "refused", ("hike.create", {**OFF, "date": "2026-10-29"}))
        self.assertNoWarning(result, "start is in the past")

    def test_update_capacity_on_rsvp_off_event_warns(self):
        repo = self.hike_repo(OFF_BARE, rows=[])
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "capacity": 7})), [off_warning(7)])
        self.assertEqual(repo.event()["capacity"], 7)
        again = ("hike.update", {"id": HIKE_ID, "capacity": 9, "rsvpEnabled": False})  # already off, said again
        self.assertEqual(self.warnings(repo, again), [off_warning(9)])

    def test_turning_off_with_capacity_gives_both_warnings_in_order(self):
        repo = self.hike_repo(HIKE, rows=[(HIKE_ID, 1), (HIKE_ID, 2)])
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "rsvpEnabled": False, "capacity": 4})),
                         [f"{HIKE_ID} has 3 confirmed guests; nobody is notified automatically", off_warning(4)])
        repo = self.hike_repo(HIKE, rows=[])
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "rsvpEnabled": False, "capacity": 4})),
                         [off_warning(4)])

    def test_turning_on_reuses_the_stored_capacity_with_a_warning(self):
        for args in ({"rsvpEnabled": True}, {"rsvpEnabled": True, "noCapacityLimit": False}):
            with self.subTest(args=args):
                repo = self.hike_repo(OFF, rows=[])
                self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, **args})), [STORED])
                self.assertEqual((repo.event()["rsvpEnabled"], repo.event()["capacity"]), (True, 5))

    def test_turning_on_with_new_capacity_or_no_limit_warns_nothing(self):
        repo = self.hike_repo(OFF, rows=[])
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "capacity": 8})), [])
        self.assertEqual(repo.event()["capacity"], 8)
        repo = self.hike_repo(OFF)
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True,
                                                              "noCapacityLimit": True})), [])
        self.assertNotIn("capacity", repo.event())

    def test_already_on_or_unrelated_update_warns_nothing(self):
        repo = self.hike_repo(HIKE)
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "title": "T2"})), [])
        repo = self.hike_repo(OFF)  # stored capacity on an RSVP-off event, RSVPs stay off
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "title": "Renamed"})), [])

    def test_rejected_updates_carry_no_warning(self):
        repo = self.hike_repo(OFF_BARE)  # turning on without a stored capacity asks (RF1130-5)
        ask = self.assertRejected(repo, "needs-details", ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True}))
        self.assertNoWarning(ask, ["capacity", "noCapacityLimit"])
        repo = self.hike_repo(HIKE, rows=[(HIKE_ID, 3)])
        low = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 2}))
        self.assertNoWarning(low, "capacity 2 is below 3 confirmed guests")
        repo = self.hike_repo(OFF_BARE)  # no guest database: the capacity seat check fails closed
        unread = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 7}))
        self.assertNoWarning(unread, "guest count unavailable")
        repo = self.hike_repo(OFF)
        past = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "rsvpEnabled": True,
                                                                     "date": "2026-10-29"}))
        self.assertNoWarning(past, "start is in the past")
        self.assertEqual((repo.event()["rsvpEnabled"], repo.event()["capacity"]), (False, 5))


class ProposalCapacityWarningTests(H06TestCase):
    def test_proposal_shows_the_rsvps_off_warning(self):
        self.interp.mapping.update({"plan a quiet walk": _ops(("hike.create", OFF))})
        self.conv = self.open()
        draft, reply = self.propose("plan a quiet walk")
        self.assertIn("\nHeads up: Sign-ups are off, so the guest limit does nothing until they are turned on.\n", reply)
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual(self.drafts()[-1]["state"], "verified")


if __name__ == "__main__":
    unittest.main()
