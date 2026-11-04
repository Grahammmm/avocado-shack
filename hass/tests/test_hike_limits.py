"""RF1939-4 tests: hike.create / update / complete / recap refuse a text over its TEXT_LIMITS limit by name.

Fixture repos only (test_hike_ops helpers). The content validator stays the backstop for hand edits.
Run: python3 -B -m unittest hass.tests.test_hike_limits -v
"""

import unittest
from datetime import datetime, timedelta, timezone

from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

AFTER_START = datetime(2026, 12, 5, 12, 0, tzinfo=timezone(timedelta(hours=-8)))
ASTRAL = "\U0001F33F"  # one code point, two UTF-16 units


def long_reply(field, limit):
    return f"{field} is longer than {limit} characters"


class HikeLimitTests(HikeTestCase):
    def reason(self, repo, op):
        return self.assertRejected(repo, "refused", op)["reason"]

    def test_create_names_the_field_and_limit_and_drafts_nothing(self):
        repo = self.repo()
        self.assertEqual(self.reason(repo, ("hike.create", {**HIKE, "title": "a" * 81})), long_reply("title", 80))
        self.assertEqual(repo.community()["events"], [])

    def test_create_at_each_limit_is_drafted(self):
        repo = self.repo()
        text = {"title": 80, "meetingPoint": 160, "bring": 400, "description": 800}
        repo.run(("hike.create", {**HIKE, **{f: "a" * n for f, n in text.items()}}))
        (event,) = repo.community()["events"]
        self.assertEqual({f: len(event[f]) for f in text}, text)

    def test_create_over_each_other_limit_is_refused_by_name(self):
        repo = self.repo()
        for field, limit in (("meetingPoint", 160), ("description", 800), ("bring", 400), ("accessNote", 400)):
            with self.subTest(field=field):
                self.assertEqual(self.reason(repo, ("hike.create", {**HIKE, field: "a" * (limit + 1)})),
                                 long_reply(field, limit))

    def test_update_refuses_and_leaves_the_stored_event_alone(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        stored = repo.event()
        self.assertEqual(self.reason(repo, ("hike.update", {"id": HIKE_ID, "meetingPoint": "a" * 161})),
                         long_reply("meetingPoint", 160))
        self.assertEqual(repo.event(), stored)
        repo.run(("hike.update", {"id": HIKE_ID, "meetingPoint": "a" * 160}))

    def test_update_with_two_over_long_fields_names_the_first_in_frozen_order(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        both = {"id": HIKE_ID, "description": "a" * 801, "title": "a" * 81, "meetingPoint": "a" * 161}
        self.assertEqual(self.reason(repo, ("hike.update", both)), long_reply("title", 80))
        del both["title"]
        self.assertEqual(self.reason(repo, ("hike.update", both)), long_reply("meetingPoint", 160))

    def test_complete_with_a_long_recap_leaves_the_hike_scheduled(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.now = AFTER_START
        self.assertEqual(self.reason(repo, ("hike.complete", {"id": HIKE_ID, "recap": "a" * 2001})),
                         long_reply("recap", 2000))
        self.assertEqual(repo.event()["status"], "scheduled")

    def test_recap_on_a_completed_hike_is_refused_and_keeps_the_old_recap(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.now = AFTER_START
        repo.run(("hike.complete", {"id": HIKE_ID, "recap": "Good walk"}))
        self.assertEqual(self.reason(repo, ("hike.recap", {"id": HIKE_ID, "recap": "a" * 2001})),
                         long_reply("recap", 2000))
        self.assertEqual(repo.event()["recap"], "Good walk")
        repo.run(("hike.recap", {"id": HIKE_ID, "recap": "a" * 2000}))

    def test_limits_count_code_points_not_utf16_units(self):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "bring": ASTRAL * 400}))
        self.assertEqual(self.reason(repo, ("hike.create", {**HIKE, "title": "Other", "bring": ASTRAL * 401})),
                         long_reply("bring", 400))

    def test_non_string_arguments_still_fail_the_argument_check(self):
        repo = self.repo()
        for op in (("hike.create", {**HIKE, "title": 5}), ("hike.update", {"id": HIKE_ID, "bring": ["a" * 999]}),
                   ("hike.recap", {"id": HIKE_ID, "recap": 7})):
            with self.subTest(op=op[0]):
                self.assertRejected(repo, "invalid", op)


if __name__ == "__main__":
    unittest.main()
