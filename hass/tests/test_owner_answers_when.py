"""RF1750-4 tests: "did my change work?" never reads an install time without a zone in the host's zone.

Each case runs under two host zones (TZ=UTC and TZ=Asia/Tokyo, via time.tzset where available) and must give the same text.
Run: python3 -B -m unittest hass.tests.test_owner_answers_when
"""
import os
import time
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from hass import owner_answers as answers, voice
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
                self.assertEqual(voice.plain(answer), f"Done. Hours is on the website now (I checked {expected}).")
                self.assertIsNone(INTERNAL.search(answer), answer)

    def test_zone_less_time_is_unknown_on_every_host(self):
        self.each_zone("2026-11-02T09:05", "at a time I can't read")
        self.each_zone("2026-11-02T17:05:00", "at a time I can't read")
        self.each_zone("2026-11-02", "at a time I can't read")  # a bare date has no zone either

    def test_zoned_time_today_is_the_same_text_on_every_host(self):
        self.each_zone("2026-11-02T17:05:00+00:00", "today at 9:05 am")
        self.each_zone("2026-11-03T02:05:00+09:00", "today at 9:05 am")  # same instant written in another zone

    def test_zoned_time_on_another_day_and_across_fall_back(self):
        self.each_zone("2026-11-01T17:05:00+00:00", "yesterday at 9:05 am")
        self.each_zone("2026-11-01T09:30:00+00:00", "yesterday at 1:30 am")  # second 01:30 (PST), after fall-back
        self.each_zone("2026-11-01T08:30:00+00:00", "yesterday at 1:30 am")  # first 01:30 (PDT), before fall-back

    def test_unreadable_install_times_are_unknown(self):
        for bad in (None, "", "yesterday", 5, 5.5, ["2026-11-02T17:05:00+00:00"]):
            self.each_zone(bad, "at a time I can't read")

    def test_year_one_utc_install_time_is_unreadable_on_every_host(self):
        self.each_zone("0001-01-01T00:00:00+00:00", "at a time I can't read")

    def test_offset_calendar_underflow_is_unreadable(self):
        install = {"state": "installed", "installed_at": "0001-01-01T00:00:00+14:00"}
        before = deepcopy((CHANGE, install))
        self.each_zone(install["installed_at"], "at a time I can't read")
        self.assertEqual(voice.plain(answers.did_it_work(CHANGE, install, NOW)),
                         "Done. Hours is on the website now (I checked at a time I can't read).")
        self.assertEqual((CHANGE, install), before)

    def test_calendar_edge_now_cannot_escape_status_reader(self):
        for now in (datetime.max.replace(tzinfo=timezone.utc),
                    datetime.max.replace(tzinfo=timezone(-timedelta(hours=14)))):
            self.each_zone("2026-11-02T17:05:00+00:00", "at a time I can't read", now=now)

    def test_extreme_future_time_keeps_existing_refusal(self):
        self.each_zone("9999-12-31T23:59:59-14:00", "at a time I can't read")
        self.each_zone("0001-01-02T12:00:00+00:00", "Tuesday, Jan 2 at 4:07 am")
        self.each_zone("2026-11-02T17:05:00+00:00", "today at 9:05 am")

    def test_extreme_time_never_upgrades_unconfirmed_or_cancelled_states(self):
        extreme = {"state": "installed", "installed_at": "0001-01-01T00:00:00+14:00"}
        cases = [({"state": state, "summary": "Hours"}, extreme) for state in
                 ("proposed", "needs-details", "approved", "failed", "rejected", "expired", "reverted")]
        cases += [(CHANGE, None), (CHANGE, {"installed_at": extreme["installed_at"]}),
                  (CHANGE, {**extreme, "state": "failed"})]
        for change, install in cases:
            with self.subTest(change=change, install=install):
                ordinary = {**install, "installed_at": "2026-11-02T17:05:00+00:00"} if install else install
                before = deepcopy((change, install))
                reply = answers.did_it_work(change, install, NOW)
                self.assertEqual(reply, answers.did_it_work(change, ordinary, NOW))
                self.assertNotIn("is on the website now", reply)
                self.assertEqual((change, install), before)

    def test_naive_now_is_compared_as_utc_never_the_host_zone(self):
        # As UTC this is Tue Nov 3 00:30 Pacific (not the install day); read in Tokyo it would be Mon Nov 2 15:30.
        naive_now = datetime(2026, 11, 3, 8, 30)
        self.each_zone("2026-11-02T17:05:00+00:00", "yesterday at 9:05 am", now=naive_now)
        # As UTC this is Mon Nov 2 23:00 Pacific: still the install day.
        self.each_zone("2026-11-02T17:05:00+00:00", "today at 9:05 am", now=datetime(2026, 11, 3, 7, 0))
        self.each_zone("2026-11-02T09:05", "at a time I can't read", now=naive_now)


if __name__ == "__main__":
    unittest.main()
