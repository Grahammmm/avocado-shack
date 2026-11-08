"""RF1300-20 tests: "did my change work?" never says the site was checked at a time that has not happened yet.

An install time more than 5 minutes after now (FUTURE_SLACK, clock-skew allowance) reads "checked at an unknown time";
at or before now + 5 min it formats as before. Fixed synthetic clocks only; no wall-clock read.
Run: python3 -B -m unittest hass.tests.test_owner_answers_future
"""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from hass import owner_answers as answers
from hass.tests.test_owner_answers import INTERNAL

PT = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 2, 9, 5, tzinfo=PT)  # Mon 09:05 PST = 17:05Z
CHANGE = {"state": "applied", "summary": "Hours"}
UNKNOWN = "at a time I can't read"


def said(installed_at, now=NOW):
    return answers.did_it_work(CHANGE, {"state": "installed", "installed_at": installed_at}, now)


class FutureInstallTimeTests(unittest.TestCase):
    def check(self, installed_at, expected, now=NOW):
        with self.subTest(installed_at=installed_at, now=now):
            answer = said(installed_at, now)
            self.assertEqual(answer, f"Done. \ue000Hours\ue001 is on the website now (I checked {expected}).")
            self.assertIsNone(INTERNAL.search(answer), answer)

    def test_slack_is_five_minutes(self):
        self.assertEqual(answers.FUTURE_SLACK, timedelta(minutes=5))

    def test_past_time_today_is_unchanged(self):
        self.check("2026-11-02T09:00:00-08:00", "today at 9 am")
        self.check("2026-11-02T09:05:00-08:00", "today at 9:05 am")  # exactly now

    def test_within_slack_formats_beyond_it_is_unknown(self):
        self.check("2026-11-02T09:09:00-08:00", "today at 9:09 am")  # 4 min ahead
        self.check("2026-11-02T09:11:00-08:00", UNKNOWN)  # 6 min ahead

    def test_boundary_is_strictly_after_now_plus_slack(self):
        self.check("2026-11-02T09:10:00-08:00", "today at 9:10 am")  # exactly now + 5 min
        self.check("2026-11-02T09:10:00.000001-08:00", UNKNOWN)  # one microsecond later
        self.check("2026-11-02T09:10:01-08:00", UNKNOWN)

    def test_later_day_is_unknown_never_a_weekday(self):
        self.check("2026-11-03T08:00:00-08:00", UNKNOWN)  # before: "Tue Nov 3 08:00"
        self.check("2027-01-01T00:00:00-08:00", UNKNOWN)
        self.check("2026-11-01T09:05:00-08:00", "yesterday at 9:05 am")  # a past day still formats

    def test_utc_install_time_is_compared_as_the_same_instant(self):
        self.check("2026-11-02T18:05:00Z", UNKNOWN)  # one hour ahead of 09:05 PT
        self.check("2026-11-02T16:05:00Z", "today at 8:05 am")  # one hour behind
        self.check("2026-11-02T17:10:00+00:00", "today at 9:10 am")  # now + 5 min written in UTC
        self.check("2026-11-03T02:11:00+09:00", UNKNOWN)  # 6 min ahead written in Tokyo time

    def test_zone_less_now_is_read_as_utc(self):
        naive_now = datetime(2026, 11, 2, 17, 5)  # as UTC: 09:05 PT; as Pacific it would be 01:05Z next day
        self.check("2026-11-02T20:00:00+00:00", UNKNOWN, now=naive_now)  # past only if now were read as Pacific
        self.check("2026-11-02T17:30:00+00:00", UNKNOWN, now=naive_now)
        self.check("2026-11-02T17:10:00+00:00", "today at 9:10 am", now=naive_now)
        self.check("2026-11-02T17:00:00+00:00", "today at 9 am", now=naive_now)

    def test_dst_fall_back_never_widens_the_slack(self):
        # 2026-11-01 01:58 PDT (fold=0) = 08:58Z; wall-clock + 5 min would be 02:03 PST = 10:03Z (an hour too wide)
        pdt = datetime(2026, 11, 1, 1, 58, tzinfo=PT, fold=0)
        self.check("2026-11-01T09:30:00+00:00", UNKNOWN, now=pdt)  # 32 min ahead
        self.check("2026-11-01T09:03:00.000001+00:00", UNKNOWN, now=pdt)  # just past now + 5 min
        self.check("2026-11-01T09:03:00+00:00", "today at 1:03 am", now=pdt)  # exactly now + 5 min (01:03 PST)
        self.check("2026-11-01T08:50:00+00:00", "today at 1:50 am", now=pdt)  # past (01:50 PDT)
        pst = datetime(2026, 11, 1, 1, 58, tzinfo=PT, fold=1)  # second 01:58, PST = 09:58Z
        self.check("2026-11-01T09:30:00+00:00", "today at 1:30 am", now=pst)  # really in the past here
        self.check("2026-11-01T10:04:00+00:00", UNKNOWN, now=pst)  # 6 min ahead

    def test_dst_spring_forward_keeps_five_minutes(self):
        now = datetime(2026, 3, 8, 1, 58, tzinfo=PT)  # 01:58 PST = 09:58Z; 02:xx does not exist that day
        self.check("2026-03-08T10:03:00+00:00", "today at 3:03 am", now=now)  # exactly now + 5 min (03:03 PDT)
        self.check("2026-03-08T10:04:00+00:00", UNKNOWN, now=now)

    def test_zone_less_and_unreadable_install_times_stay_unknown(self):
        for bad in ("2026-11-02T09:00", "2026-11-02T09:11", "2026-11-02", "not a time", None, 5):
            self.check(bad, UNKNOWN)
        self.check("2026-11-02T09:00", UNKNOWN, now=datetime(2026, 11, 2, 17, 5))

    def test_other_answers_never_show_a_check_time(self):
        future = {"state": "installed", "installed_at": "2026-11-03T08:00:00-08:00"}
        self.assertEqual(answers.did_it_work({"state": "reverted"}, future, NOW), "That change was undone.")
        self.assertEqual(answers.did_it_work({"state": "proposed"}, future, NOW),
                         "It's waiting for your yes. Nothing has changed yet.")


if __name__ == "__main__":
    unittest.main()
