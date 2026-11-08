"""RF1240-4 tests: hike.update moving an RSVP'd hike warns how many confirmed guests are not told. Fixture repos
and placeholder example.invalid RSVP rows only (test_hike_ops / H06 helpers); nobody is notified.
"""

import sqlite3
import unittest
from unittest import mock

from hass import editor
from hass.ops import hikes
from hass.tests.test_conversation import SETTINGS, _ops
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, SCHEMA, HikeTestCase, _req
from hass.tests.test_undo import H06TestCase

MOVE = ("hike.update", {"id": HIKE_ID, "time": "10:30"})
MOVED = f"{HIKE_ID} moves to 2026-12-05 10:30 Pacific; 3 confirmed guests are not told automatically"
UNAVAILABLE = f"{HIKE_ID} guest count unavailable; check RSVPs before approving"
THREE_OFF = f"{HIKE_ID} has 3 confirmed guests; nobody is notified automatically"


class MoveWarningTests(HikeTestCase):
    def hike_repo(self, rows=None, **extra):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, **extra}))
        if rows is not None:
            repo.make_db(rows)
        return repo

    def warnings(self, repo, *ops):
        """Warnings of a drafted request, then apply it: the warning never stops the change."""
        draft = repo.prepare(_req(*ops))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
        return draft["draft"]["warnings"]

    def unread(self, repo):  # an absent database: opening it would give the unavailable warning
        repo.use_db(str(repo.db.parent / "absent.sqlite3"))
        spy = mock.patch.object(hikes, "guest_counts", wraps=hikes.guest_counts)
        self.addCleanup(spy.stop)
        return spy.start()

    def test_move_counts_seats_and_still_moves(self):
        repo = self.hike_repo([(HIKE_ID, 1), (HIKE_ID, 2), ("hike-2026-12-06-other", 4)])
        self.assertEqual(self.warnings(repo, MOVE), [MOVED])
        self.assertEqual(repo.event()["startsAt"], "2026-12-05T10:30:00-08:00")

    def test_one_seat_is_singular_and_no_rsvps_warn_nothing(self):
        repo = self.hike_repo([(HIKE_ID, 1)])
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, "date": "2026-12-12"})),
                         [f"{HIKE_ID} moves to 2026-12-12 09:00 Pacific; 1 confirmed guest is not told automatically"])
        for rows in ([], [("hike-2026-12-06-other", 2)]):  # no RSVPs, or only for another event
            with self.subTest(rows=rows):
                self.assertEqual(self.warnings(self.hike_repo(rows), MOVE), [])

    def test_same_date_and_time_never_opens_the_database(self):
        repo = self.hike_repo()
        spy = self.unread(repo)
        same = ({"date": "2026-12-05"}, {"time": "09:00"}, {"date": "2026-12-05", "time": "09:00"}, {})
        for n, args in enumerate(same):
            args["title"] = f"Same start {n}"  # {} is title only; a request changing nothing is refused anyway
            with self.subTest(args=args):
                self.assertEqual(self.warnings(repo, ("hike.update", {"id": HIKE_ID, **args})), [])
        spy.assert_not_called()
        self.assertEqual(repo.event()["startsAt"], "2026-12-05T09:00:00-08:00")

    def test_dst_shows_the_local_clock_given(self):
        eid = "hike-2026-10-31-test-hike"  # created in PDT (-07:00), moved past the November change
        repo = self.hike_repo([(eid, 2)], date="2026-10-31")
        self.assertEqual(self.warnings(repo, ("hike.update", {"id": eid, "date": "2026-11-02", "time": "08:00"})),
                         [f"{eid} moves to 2026-11-02 08:00 Pacific; 2 confirmed guests are not told automatically"])
        self.assertEqual(repo.event(eid)["startsAt"], "2026-11-02T08:00:00-08:00")

    def test_unknown_count_still_drafts_with_a_warning(self):
        def unset(repo): pass

        def missing_file(repo): repo.use_db(str(repo.db.parent / "absent.sqlite3"))

        def no_table(repo):
            sqlite3.connect(repo.db).close()
            repo.use_db(str(repo.db))

        for name, setup in (("unset", unset), ("unreadable", missing_file), ("missing table", no_table)):
            with self.subTest(name):
                repo = self.hike_repo()
                setup(repo)
                self.assertEqual(self.warnings(repo, MOVE), [UNAVAILABLE])
                self.assertEqual(repo.event()["startsAt"], "2026-12-05T10:30:00-08:00")

    def test_rsvps_off_never_opens_the_database(self):
        repo = self.hike_repo(rsvpEnabled=False)
        spy = self.unread(repo)
        self.assertEqual(self.warnings(repo, MOVE), [])
        spy.assert_not_called()

    def test_move_and_rsvps_off_warn_once(self):
        repo = self.hike_repo([(HIKE_ID, 1), (HIKE_ID, 2)])
        self.assertEqual(self.warnings(repo, (MOVE[0], {**MOVE[1], "rsvpEnabled": False})), [THREE_OFF])
        self.assertEqual((repo.event()["startsAt"], repo.event()["rsvpEnabled"]), ("2026-12-05T10:30:00-08:00", False))

    def test_refused_or_needs_details_move_warns_nothing(self):
        repo = self.hike_repo([(HIKE_ID, 1), (HIKE_ID, 2)])
        with mock.patch.object(hikes, "guest_counts", wraps=hikes.guest_counts) as spy:
            past = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "date": "2026-10-29"}))
            self.assertEqual(past["reason"], "start is in the past")
            twice = self.assertRejected(repo, "needs-details",
                                        ("hike.update", {"id": HIKE_ID, "date": "2026-11-01", "time": "01:30"}))
            self.assertEqual(twice["missing"], ["time"])
        spy.assert_not_called()
        self.assertEqual(repo.event()["startsAt"], "2026-12-05T09:00:00-08:00")


class ProposalMoveWarningTests(H06TestCase):
    def setUp(self):
        super().setUp()
        draft = editor.prepare(_req(("hike.create", HIKE)), state=str(self.repo.state), now=NOW)
        editor.apply(draft["draft"]["change_id"], draft["draft"]["draft_hash"], state=str(self.repo.state), now=NOW)
        path = self.repo.state.parent / "rsvps.sqlite3"
        db = sqlite3.connect(path)
        db.execute(SCHEMA)
        for n, party in enumerate((1, 2), 1):
            db.execute("INSERT INTO rsvps(event_id,email,name,party_size,created_at) VALUES(?,?,?,?,?)",
                       (HIKE_ID, f"walker{n}@example.invalid", f"Walker Name {n}", party, "2026-10-30T00:00:00Z"))
        db.commit()
        db.close()
        self.set_settings({**SETTINGS, "guestCountsDb": str(path)})
        self.interp.mapping.update({"move the hike": _ops(MOVE)})
        self.conv = self.open()

    def test_proposal_shows_the_warning_and_no_guest_details(self):
        draft, reply = self.propose("move the hike")
        self.assertIn("\nHeads up: 3 guests have signed up for the old time, and nobody is told automatically.\n", reply)
        for secret in ("walker", "Walker Name", "example.invalid"):
            self.assertNotIn(secret, reply)
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertNotIn("walker", " ".join(row["text"] for row in self.sent()).lower())
        self.assertEqual(self.drafts()[-1]["state"], "verified")


if __name__ == "__main__":
    unittest.main()
