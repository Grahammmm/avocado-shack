"""RF1300-9 tests: a real event's startsAt offset must be Pacific time at that instant.

Each case copies the checkout content to a temporary directory, adds one synthetic event and validates it.
The checkout is only read. Run: python3 -m unittest hass.tests.test_content_starts_at -v
"""

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from hass.content_model import CONTENT_DIR, SITE_DIR, ContentError, load_content, validate
from hass.ops import hikes

EVENT = {"id": "hike-test-start", "title": "Morning walk", "timezone": "America/Los_Angeles", "status": "scheduled"}


class StartsAtOffsetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.content_dir = Path(tmp.name) / "content"
        shutil.copytree(CONTENT_DIR, self.content_dir)
        self.base = (self.content_dir / "community.json").read_text("utf-8")

    def problems(self, starts_at, extra=(), **changes):
        community = json.loads(self.base)
        community["events"].extend([*extra, {**EVENT, "startsAt": starts_at, **changes}])
        (self.content_dir / "community.json").write_text(json.dumps(community), "utf-8")
        try:
            validate(load_content(self.content_dir), SITE_DIR)
        except ContentError as exc:
            return [p for p in exc.problems if p.startswith("events[")]
        return []

    def assertOffsetRefused(self, starts_at, expect):
        problems = self.problems(starts_at)
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith("events[0].startsAt: offset "), problems)
        for part in expect:
            self.assertIn(part, problems[0])

    def test_summer_with_winter_offset(self):
        self.assertOffsetRefused("2026-07-04T09:00:00-08:00", ["offset -08:00", "on 2026-07-04", "(expected -07:00)"])
        self.assertEqual(self.problems("2026-07-04T09:00:00-08:00")[0],
                         "events[0].startsAt: offset -08:00 is not Pacific time on 2026-07-04 (expected -07:00)")

    def test_winter_with_summer_offset(self):
        self.assertOffsetRefused("2026-12-05T09:00:00-07:00", ["offset -07:00", "on 2026-12-05", "(expected -08:00)"])

    def test_utc_shown_as_plus_zero(self):
        self.assertOffsetRefused("2026-12-05T17:00:00Z", ["offset +00:00", "on 2026-12-05", "(expected -08:00)"])
        self.assertOffsetRefused("2026-12-05T17:00:00+00:00", ["offset +00:00", "(expected -08:00)"])

    def test_pacific_date_of_instant_not_written_date(self):
        # 2026-07-05 05:00 UTC is 2026-07-04 22:00 PDT: the message names the Pacific calendar date.
        self.assertOffsetRefused("2026-07-05T05:00:00Z", ["on 2026-07-04", "(expected -07:00)"])

    def test_far_offsets_refused(self):
        self.assertOffsetRefused("2026-12-05T09:00:00+05:30", ["offset +05:30", "(expected -08:00)"])
        self.assertOffsetRefused("2026-07-04T09:00:00-07:30", ["offset -07:30", "(expected -07:00)"])

    def test_correct_offsets_pass(self):
        for value in ("2026-07-04T09:00:00-07:00", "2026-12-05T09:00:00-08:00", "2026-12-05T09:00-08:00"):
            with self.subTest(startsAt=value):
                self.assertEqual(self.problems(value), [])

    def test_dst_edges(self):
        for value in ("2026-11-01T01:30:00-07:00", "2026-11-01T01:30:00-08:00", "2026-03-08T03:30:00-07:00",
                      "2026-03-08T01:30:00-08:00"):
            with self.subTest(startsAt=value):
                self.assertEqual(self.problems(value), [])
        # 03:30-08:00 is 11:30 UTC = 04:30 PDT; the offset in force then is -07:00.
        self.assertOffsetRefused("2026-03-08T03:30:00-08:00", ["offset -08:00", "on 2026-03-08", "(expected -07:00)"])
        # 01:30-07:00 on the spring-forward day is 00:30 PST (-08:00 still in force).
        self.assertOffsetRefused("2026-03-08T01:30:00-07:00", ["offset -07:00", "on 2026-03-08", "(expected -08:00)"])

    def test_wrong_timezone_field_gives_only_timezone_problem(self):
        for value in ("2026-07-04T09:00:00-08:00", "2026-12-05T17:00:00Z", "2026-12-05T09:00:00-08:00"):
            with self.subTest(startsAt=value):
                self.assertEqual(self.problems(value, timezone="UTC"),
                                 ["events[0]: timezone must be America/Los_Angeles"])
        self.assertEqual(self.problems("2026-07-04T09:00:00-08:00", timezone="america/los_angeles"),
                         ["events[0]: timezone must be America/Los_Angeles"])

    def test_format_errors_unchanged(self):
        problems = self.problems("2026-12-05T09:00:00")
        self.assertEqual(problems, ["events[0].startsAt: must be an ISO date-time with a UTC offset"])
        problems = self.problems("2026-13-45T09:00:00-08:00")
        self.assertEqual(problems, ["events[0].startsAt: not a valid ISO date-time"])

    def test_datetime_range_edge_is_a_problem_not_a_crash(self):
        # Year 1 UTC underflows when shifted to Pacific; year 9999 at -12:00 overflows the UTC conversion.
        for value in ("0001-01-01T00:00:00Z", "0001-01-01T00:00:00+05:00", "9999-12-31T23:00:00-12:00"):
            with self.subTest(startsAt=value):
                self.assertEqual(self.problems(value),
                                 [f"events[0].startsAt: {value!r} is outside the supported date range"])

    def test_one_problem_per_bad_event(self):
        ok = {**EVENT, "id": "hike-test-ok", "startsAt": "2026-07-04T09:00:00-07:00"}
        problems = self.problems("2026-07-04T09:00:00-08:00", extra=[ok])
        self.assertEqual(problems, ["events[1].startsAt: offset -08:00 is not Pacific time on 2026-07-04 "
                                    "(expected -07:00)"])

    def test_hike_create_july_output_validates(self):
        content = load_content(self.content_dir)
        ctx = SimpleNamespace(now=datetime(2026, 6, 1, 12, 0, tzinfo=timezone(timedelta(hours=-7))),
                              warnings=[], settings={})
        args = {"title": "July walk", "date": "2026-07-04", "time": "09:00", "meetingPoint": "Test trailhead lot",
                "rsvpEnabled": False}
        touched = hikes._hike_create(content, args, ctx)
        self.assertIsInstance(touched, list, touched)
        self.assertEqual(content.community["events"][-1]["startsAt"], "2026-07-04T09:00:00-07:00")
        validate(content, SITE_DIR)


if __name__ == "__main__":
    unittest.main()
