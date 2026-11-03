"""RF1740-6 tests: a missing, non-integer or non-positive RSVP party size makes that event's guest count
unavailable (fail closed), never a smaller number.

Each test builds a throwaway rsvps table in a temp dir with an untyped party_size column, so NULL, 0, -1, 2.5 and
text '2' are stored as given (placeholder example.invalid rows only). Nothing touches the real community database.
Run: python3 -m unittest hass.tests.test_hike_guest_rows -v
"""

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hass.ops import hikes
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase, _req

OTHER = "hike-2026-12-06-other"
UNAVAILABLE = f"{HIKE_ID} guest count unavailable; check RSVPs before approving"
LOOSE = """CREATE TABLE rsvps (id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, email TEXT NOT NULL,
  name TEXT NOT NULL, party_size, created_at TEXT NOT NULL)"""
BAD = {"NULL": None, "zero": 0, "negative": -1, "fraction": 2.5, "text": "2"}


def write_db(path, rows):
    db = sqlite3.connect(path)
    db.execute(LOOSE)
    for n, (event_id, party) in enumerate(rows, 1):
        db.execute("INSERT INTO rsvps(event_id,email,name,party_size,created_at) VALUES(?,?,?,?,?)",
                   (event_id, f"guest{n}@example.invalid", f"Guest {n}", party, "2026-10-30T00:00:00Z"))
    db.commit()
    db.close()
    return path


class CheckedCountTests(unittest.TestCase):
    def db(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return write_db(Path(tmp.name) / "rsvps.sqlite3", rows)

    def test_good_rows_are_summed(self):
        path = self.db([(HIKE_ID, 2), (HIKE_ID, 3), (OTHER, 4)])
        self.assertEqual(hikes.guest_counts_checked(path), ({HIKE_ID: 5, OTHER: 4}, set()))
        self.assertEqual(hikes.guest_counts(path), {HIKE_ID: 5, OTHER: 4})

    def test_one_bad_row_makes_only_its_event_unavailable(self):
        for name, party in BAD.items():
            with self.subTest(name):
                path = self.db([(HIKE_ID, 2), (HIKE_ID, party), (HIKE_ID, 3), (OTHER, 4)])
                self.assertEqual(hikes.guest_counts_checked(path), ({OTHER: 4}, {HIKE_ID}))
                self.assertEqual(hikes.guest_counts(path), {OTHER: 4})  # left out, never a smaller number

    def test_all_bad_rows_and_bad_rows_on_both_events(self):
        path = self.db([(HIKE_ID, None), (HIKE_ID, None), (OTHER, 0), (OTHER, 6)])
        self.assertEqual(hikes.guest_counts_checked(path), ({}, {HIKE_ID, OTHER}))

    def test_query_never_selects_guest_details(self):
        self.assertIsNone(re.search(r"\b(name|email)\b", hikes.GUEST_QUERY, re.I), hikes.GUEST_QUERY)
        self.assertTrue(hikes.GUEST_QUERY.lstrip().upper().startswith("SELECT "))


class BadRowOpTests(HikeTestCase):
    def hike_repo(self, rows):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.use_db(str(write_db(repo.db, rows)))
        return repo

    def test_lowering_capacity_with_a_bad_row_is_refused(self):
        for name, party in BAD.items():
            with self.subTest(name):
                repo = self.hike_repo([(HIKE_ID, 2), (HIKE_ID, party), (OTHER, 1)])
                before = repo.db.read_bytes()
                refused = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 9}))
                self.assertEqual(refused["reason"], "guest count unavailable")
                self.assertEqual((repo.event()["capacity"], repo.db.read_bytes()), (12, before))

    def test_bad_row_on_another_event_still_counts_this_one(self):
        repo = self.hike_repo([(HIKE_ID, 3), (HIKE_ID, 2), (OTHER, None)])
        refused = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 4}))
        self.assertIn("capacity 4 is below 5 confirmed guests", refused["reason"])
        repo.run(("hike.update", {"id": HIKE_ID, "capacity": 5}))
        self.assertEqual(repo.event()["capacity"], 5)

    def test_cancel_with_a_bad_row_warns_and_still_cancels(self):
        for name, party in BAD.items():
            with self.subTest(name):
                repo = self.hike_repo([(HIKE_ID, 2), (HIKE_ID, party)])
                draft = repo.prepare(_req(("hike.cancel", {"id": HIKE_ID})))
                self.assertEqual(draft["result"], "ok", draft)
                self.assertEqual(draft["draft"]["warnings"], [UNAVAILABLE])
                self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
                self.assertEqual(repo.event()["status"], "cancelled")

    def test_rsvps_off_or_same_start_never_runs_the_checked_count(self):
        repo = self.hike_repo([(HIKE_ID, None)])
        with mock.patch.object(hikes, "guest_counts_checked", wraps=hikes.guest_counts_checked) as spy:
            repo.run(("hike.update", {"id": HIKE_ID, "title": "Same start", "date": "2026-12-05"}))
            spy.assert_not_called()
            self.assertEqual(repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": False}))["warnings"], [UNAVAILABLE])
            spy.reset_mock()
            self.assertEqual(repo.run(("hike.cancel", {"id": HIKE_ID}))["warnings"], [])  # RSVPs already off
        spy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
