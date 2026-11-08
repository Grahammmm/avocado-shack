"""RF1130-7 tests: `status` says `RSVPs off` for an upcoming hike without RSVPs and opens the RSVP database only
when a listed hike takes RSVPs. Same setup as test_status_pause.py (fixture repo, placeholder example.invalid rows).
Run: python3 -m unittest hass.tests.test_status_rsvp_off -v
"""

import unittest
from unittest import mock

from hass import conversation
from hass.tests import test_status_pause as sp
from hass.tests.test_hike_ops import HIKE, HIKE_ID
from hass.tests.test_undo import H06TestCase

OFF = {k: v for k, v in HIKE.items() if k != "capacity"} | {"rsvpEnabled": False, "title": "Quiet hike",
                                                             "date": "2026-12-10"}
QUIET_ID = "hike-2026-12-10-quiet-hike"
QUIET = "Quiet hike, Thursday, Dec 10 at 9 am: sign-ups are off"
ON = "Test hike, Saturday, Dec 5 at 9 am: "
PAST_QUIET = ('Past quiet was yesterday at 9 am and is still listed as coming up. '
              'Tell me if it happened or was cancelled.')


class RsvpOffStatusTests(sp.StoreMixin, H06TestCase):
    hike, rsvp_db, use = sp.GuestTotalTests.hike, sp.GuestTotalTests.rsvp_db, sp.GuestTotalTests.use

    def setUp(self):
        super().setUp()
        self.hike(("hike.create", OFF))
        self.hike(("hike.create", {**OFF, "title": "Past quiet", "date": "2026-11-01"}))  # before the clock (T0)
        self.hike(("hike.create", {**OFF, "title": "Cancelled quiet", "date": "2026-11-25"}))
        self.hike(("hike.cancel", {"id": "hike-2026-11-25-cancelled-quiet"}))

    def hike_lines(self):
        return [line for line in self.status() if line.startswith(("Quiet hike, ", "Test hike, ", "Past quiet was "))]

    def unreadable(self):
        wrong = self.rsvp_db("wrong.sqlite3", [], schema="CREATE TABLE other(id INTEGER)")
        return (None, "", str(self.repo.state.parent / "missing.sqlite3"), wrong)

    def test_rsvp_off_hike_reads_rsvps_off(self):  # stale rows for the hike are not shown as confirmed
        self.use(self.rsvp_db("rsvps.sqlite3", [(QUIET_ID, 3), ("hike-2026-11-25-cancelled-quiet", 2)]))
        self.assertEqual(self.hike_lines(), [QUIET, PAST_QUIET])  # cancelled not listed; past only as passed line
        self.assertEqual([line for line in self.status() if "Past quiet" in line], [PAST_QUIET])
        text = "\n".join(self.status())
        for absent in ("confirmed", "no limit", "Cancelled quiet", "guest count unavailable"):
            self.assertNotIn(absent, text)

    def test_mixed_hikes_in_start_order(self):
        self.hike(("hike.create", HIKE))  # created last, starts first
        self.use(self.rsvp_db("rsvps.sqlite3", [(HIKE_ID, 2), (QUIET_ID, 4)]))
        self.assertEqual(self.hike_lines(), [ON + "2 guests have signed up, with room for 12", QUIET, PAST_QUIET])

    def test_only_rsvp_off_never_opens_the_database(self):
        for path in self.unreadable():
            with self.subTest(path=path), mock.patch.object(conversation.hikes, "guest_counts") as counts:
                self.use(path)
                self.assertEqual(self.hike_lines(), [QUIET, PAST_QUIET])
                counts.assert_not_called()
        self.assertFalse((self.repo.state.parent / "missing.sqlite3").exists())

    def test_rsvp_on_hike_with_unreadable_database_is_unavailable(self):
        self.hike(("hike.create", HIKE))
        for path in self.unreadable()[2:]:  # set but unreadable: opened once, count never guessed
            with self.subTest(path=path), mock.patch.object(conversation.hikes, "guest_counts",
                                                            wraps=conversation.hikes.guest_counts) as counts:
                self.use(path)
                self.assertEqual(self.hike_lines(), [ON + "I can't see how many guests have signed up", QUIET, PAST_QUIET])
                counts.assert_called_once_with(path)
        self.use(None)
        self.assertEqual(self.hike_lines(), [ON + "I can't see how many guests have signed up", QUIET, PAST_QUIET])

    def test_turning_rsvps_off_switches_the_line(self):
        self.hike(("hike.create", HIKE))
        self.hike(("hike.update", {"id": HIKE_ID, "rsvpEnabled": False}))
        self.use(self.rsvp_db("rsvps.sqlite3", [(HIKE_ID, 2)]))
        self.assertEqual(self.hike_lines(), [ON + "sign-ups are off", QUIET, PAST_QUIET])

    def test_status_changes_nothing(self):
        self.hike(("hike.create", HIKE))
        self.use(self.rsvp_db("rsvps.sqlite3", [(HIKE_ID, 2)]))
        self.propose("hours")
        content = self.repo.wt / "hass/content/community.json"
        files = lambda: sorted(p.name for p in self.repo.state.parent.iterdir())
        before = (self.drafts(), self.approvals(), self.tables(), self.commits(), content.read_bytes(), files())
        self.assertEqual(self.hike_lines(), [ON + "2 guests have signed up, with room for 12", QUIET, PAST_QUIET])
        self.assertEqual((self.drafts(), self.approvals(), self.tables(), self.commits(), content.read_bytes(),
                          files()), before)


if __name__ == "__main__":
    unittest.main()
