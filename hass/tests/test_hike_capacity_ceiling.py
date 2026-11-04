"""RF2310-11 (H14) tests: a hike capacity above MAX_EVENT_CAPACITY (1000) is refused by content validation.

Fixture state only (test_hike_ops.HikeRepo: throwaway Git repo, temp state dir, temp SQLite guest counts).
Run: python3 -m unittest hass.tests.test_hike_capacity_ceiling -v
"""

import copy
import subprocess
import sys
import unittest

from hass.content_model import MAX_EVENT_CAPACITY, REPO_ROOT, load_content, validate_community
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

MESSAGE = "capacity must be a positive integer of at most 1000"
EVENT = {"id": "hike-2026-12-05", "title": "Morning walk", "startsAt": "2026-12-05T09:00:00-08:00",
         "timezone": "America/Los_Angeles", "status": "scheduled"}


def _problems(capacity):
    community = copy.deepcopy(load_content().community)
    community["events"].append({**EVENT, "capacity": capacity})
    problems = []
    validate_community(problems, community)
    return [p for p in problems if "capacity" in p], len(community["events"]) - 1


class ValidateCommunityTests(unittest.TestCase):
    def test_ceiling_is_1000(self):
        self.assertEqual(MAX_EVENT_CAPACITY, 1000)
        for ok in (1, 999, 1000):
            with self.subTest(capacity=ok):
                self.assertEqual(_problems(ok)[0], [])
        for bad in (1001, 10**12, 0, -1, True, False, 1000.0, "12", None):
            with self.subTest(capacity=bad):
                problems, i = _problems(bad)
                self.assertEqual(problems, [f"events[{i}]: {MESSAGE}"])
                self.assertIn("positive integer", problems[0])  # test_content.py matches this substring

    def test_committed_content_still_valid(self):
        run = subprocess.run([sys.executable, "hass/sitegen.py", "--check"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


class EditorCeilingTests(HikeTestCase):
    def changes(self, repo):
        d = repo.state / "changes"
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def assertInvalid(self, repo, *ops):
        before = (repo.head(), repo.drafts(), self.changes(repo), repo.community())
        result = self.assertRejected(repo, "invalid", *ops)
        self.assertTrue(any(p.endswith(MESSAGE) for p in result["problems"]), result)
        self.assertEqual((repo.head(), repo.drafts(), self.changes(repo), repo.community()), before)
        return result

    def test_create_above_ceiling_is_invalid_and_writes_nothing(self):
        repo = self.repo()
        self.assertInvalid(repo, ("hike.create", {**HIKE, "capacity": 15000}))
        self.assertEqual(self.changes(repo), [])
        self.assertEqual(repo.community()["events"], [])
        self.assertInvalid(repo, ("hike.create", {**HIKE, "capacity": 1001}))
        repo.run(("hike.create", {**HIKE, "capacity": 1000}))  # the ceiling itself is allowed
        self.assertEqual(repo.event()["capacity"], 1000)

    def test_create_with_rsvps_off_still_checked(self):
        repo = self.repo()
        self.assertInvalid(repo, ("hike.create", {**HIKE, "rsvpEnabled": False, "capacity": 5000}))
        self.assertEqual(repo.community()["events"], [])

    def test_bad_op_in_multi_op_request_writes_nothing(self):
        repo = self.repo()
        self.assertInvalid(repo, ("hike.create", HIKE), ("hike.create", {**HIKE, "title": "Big walk", "capacity": 2000}))
        self.assertEqual(repo.community()["events"], [])

    def test_update_above_ceiling_is_invalid_and_below_still_ok(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.make_db([(HIKE_ID, 3), (HIKE_ID, 2)])
        before = repo.db.read_bytes()
        for bad in (1001, 15000, 10**12):
            with self.subTest(capacity=bad):
                self.assertInvalid(repo, ("hike.update", {"id": HIKE_ID, "capacity": bad}))
                self.assertEqual(repo.event()["capacity"], 12)
        self.assertInvalid(repo, ("hike.update", {"id": HIKE_ID, "rsvpEnabled": False, "capacity": 5000}))
        refused = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 4}))
        self.assertIn("capacity 4 is below 5 confirmed guests", refused["reason"])  # seat check keeps its wording
        repo.run(("hike.update", {"id": HIKE_ID, "capacity": 999}))
        self.assertEqual(repo.event()["capacity"], 999)
        self.assertEqual(repo.db.read_bytes(), before)

    def test_unreadable_guest_count_still_refused_first(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        result = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 1001}))
        self.assertEqual(result["reason"], "guest count unavailable")


if __name__ == "__main__":
    unittest.main()
