"""RF1750-4 tests: "did my change work?" never reads an install time without a zone in the host's zone.

Each case runs under two host zones (TZ=UTC and TZ=Asia/Tokyo, via time.tzset where available) and must give the same text.
Run: python3 -B -m unittest hass.tests.test_owner_answers_when
"""
import os
import time
import unittest
from datetime import datetime

from hass import owner_answers as answers
from hass.tests.test_owner_answers import INTERNAL, NOW

HOST_ZONES = ("UTC", "Asia/Tokyo")
CHANGE = {"state": "applied", "summary": "Hours"}


def said(installed_at, now=NOW):
    return answers.did_it_work(CHANGE, {"state": "installed", "installed_at": installed_at}, now)


class WhenInHostZonesTests(unittest.TestCase):
    def setUp(self):
        if not hasattr(time, "tzset"): self.skipTest("time.tzset unavailable: the host zone cannot be switched")
        self._tz = os.environ.get("TZ")

    def tearDown(self):
        if self._tz is None: os.environ.pop("TZ", None)
        else: os.environ["TZ"] = self._tz
        time.tzset()

    def each_zone(self, installed_at, expected, now=NOW):
        for zone in HOST_ZONES:
            with self.subTest(host_zone=zone, installed_at=installed_at):
                os.environ["TZ"] = zone
                time.tzset()
                answer = said(installed_at, now)
                self.assertEqual(answer, f"Done. Hours is on the website now (checked {expected}).")
                self.assertIsNone(INTERNAL.search(answer), answer)

    def test_zone_less_time_is_unknown_on_every_host(self):
        self.each_zone("2026-11-02T09:05", "at an unknown time")
        self.each_zone("2026-11-02T17:05:00", "at an unknown time")
        self.each_zone("2026-11-02", "at an unknown time")  # a bare date has no zone either

    def test_zoned_time_today_is_the_same_text_on_every_host(self):
        self.each_zone("2026-11-02T17:05:00+00:00", "today 09:05")
        self.each_zone("2026-11-03T02:05:00+09:00", "today 09:05")  # same instant written in another zone

    def test_zoned_time_on_another_day_and_across_fall_back(self):
        self.each_zone("2026-11-01T17:05:00+00:00", "Sun Nov 1 09:05")
        self.each_zone("2026-11-01T09:30:00+00:00", "Sun Nov 1 01:30")  # second 01:30 (PST), after fall-back
        self.each_zone("2026-11-01T08:30:00+00:00", "Sun Nov 1 01:30")  # first 01:30 (PDT), before fall-back

    def test_unreadable_install_times_are_unknown(self):
        for bad in (None, "", "yesterday", 5, 5.5, ["2026-11-02T17:05:00+00:00"]):
            self.each_zone(bad, "at an unknown time")

    def test_naive_now_is_compared_as_utc_never_the_host_zone(self):
        # As UTC this is Tue Nov 3 00:30 Pacific (not the install day); read in Tokyo it would be Mon Nov 2 15:30.
        naive_now = datetime(2026, 11, 3, 8, 30)
        self.each_zone("2026-11-02T17:05:00+00:00", "Mon Nov 2 09:05", now=naive_now)
        # As UTC this is Mon Nov 2 23:00 Pacific: still the install day.
        self.each_zone("2026-11-02T17:05:00+00:00", "today 09:05", now=datetime(2026, 11, 3, 7, 0))
        self.each_zone("2026-11-02T09:05", "at an unknown time", now=naive_now)


if __name__ == "__main__":
    unittest.main()
