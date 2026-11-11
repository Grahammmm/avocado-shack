"""AV2137-02 tests: undoing a change to a scheduled RSVP hike's meeting place, meet time or route carries the same
guest warning as the forward hike.update (fresh count, actual restored values), never a refusal; a refused undo adds
none. Fixture repos (test_hike_ops.HikeRepo) and example.invalid RSVP rows only; nobody is notified.
Run: python3 -B -m unittest hass.tests.test_undo_meeting_warning
"""

import unittest
from datetime import datetime
from unittest import mock

from hass.ops import hikes, history
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase, _req

ROUTE = "idea-point-buchon"
WALK = "hike-2026-12-05-walk-two"
UNAVAILABLE = f"{HIKE_ID} guest count unavailable; check RSVPs before approving"
NO_LIMIT = {k: v for k, v in HIKE.items() if k != "capacity"} | {"noCapacityLimit": True}


def told(group, n):
    return f"{HIKE_ID}: the {group} changes; {n} confirmed guest{'s are' if n != 1 else ' is'} not told automatically"


def update(**args):
    return ("hike.update", {"id": HIKE_ID, **args})


class UndoMeetingWarningTests(HikeTestCase):
    def undo(self, repo, change):
        """Warnings of the drafted undo, then apply it: a warning never stops the undo."""
        draft = repo.prepare(_req(("history.revert", {"changeId": change["change_id"]})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
        return draft["draft"]["warnings"]

    def fresh_db(self, repo, rows):
        repo.db.unlink(missing_ok=True)
        repo.make_db(rows)

    def test_undo_meeting_route_and_clear_warn_current_guests(self):
        cases = (({"meetingPoint": "New trailhead"}, {}, ["meeting place"]),
                 ({"meetingAddress": "34 Example Road"}, {}, ["meeting place"]),  # undo removes the added address
                 ({"meetTime": "08:30"}, {"meetTime": "08:00"}, ["meet time"]),  # undo restores the old time
                 ({"clear": ["trailId"]}, {"trailId": ROUTE}, ["route"]),  # undo puts the route back
                 ({"clear": ["meetingAddress"], "trailId": "idea-cass-hill", "time": "10:00"},
                  {"meetingAddress": "33 Example Road", "trailId": ROUTE}, ["move", "meeting place", "route"]))
        for args, extra, groups in cases:
            with self.subTest(args=args):
                repo = self.repo()
                repo.run(("hike.create", {**HIKE, **extra}))
                before = repo.event()
                repo.make_db([(HIKE_ID, 1)])
                change = repo.run(update(**args))
                self.fresh_db(repo, [(HIKE_ID, 2), (HIKE_ID, 1), ("other-event", 5)])  # the count now, not then
                moved = f"{HIKE_ID} moves to 2026-12-05 09:00 Pacific; 3 confirmed guests are not told automatically"
                self.assertEqual(self.undo(repo, change), [moved if g == "move" else told(g, 3) for g in groups])
                self.assertEqual(repo.event(), before)

    def test_undo_without_detail_change_guests_or_rsvps_is_silent(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.make_db([(HIKE_ID, 1)])
        renamed = repo.run(update(title="Renamed"))
        self.assertEqual(self.undo(repo, renamed), [])
        added = repo.run(update(title="Renamed", meetingAddress="33 Example Road"))
        self.fresh_db(repo, [("other-event", 4)])  # 0 guests for this hike now
        self.assertEqual(self.undo(repo, added), [])
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "rsvpEnabled": False}))
        repo.make_db([(HIKE_ID, 3)])
        change = repo.run(update(meetingPoint="New trailhead", trailId=ROUTE))
        with mock.patch.object(hikes, "_seats", wraps=hikes._seats) as seats:
            self.assertEqual(self.undo(repo, change), [])
        self.assertEqual(seats.call_count, 0)  # no guest count is read for a warning

    def test_undo_unreadable_count_warns_once_and_still_drafts(self):
        repo = self.repo()
        repo.run(("hike.create", NO_LIMIT))  # no capacity: undo's capacity check would refuse an unread count
        change = repo.run(update(time="10:00", meetingPoint="New trailhead", meetTime="09:30"))
        repo.use_db(str(repo.state.parent / "missing.sqlite3"))
        self.assertEqual(self.undo(repo, change), [UNAVAILABLE])
        self.assertEqual(repo.event()["meetingPoint"], "Test trailhead lot")
        self.assertNotIn("meetTime", repo.event())

    def test_refused_multi_record_undo_defers_all_warnings(self):
        def conflict(repo):
            change = repo.run(update(meetingPoint="New trailhead"))
            repo.run(update(title="Renamed"))
            return change, f"conflict: events {HIKE_ID} changed after {change['change_id']}"

        def past(repo):
            change = repo.run(update(meetingPoint="New trailhead", time="10:00"))
            repo.now = datetime.fromisoformat(repo.event()["startsAt"])
            return change, "start is in the past"

        def capacity(repo):  # the first record (Walk two's meet time) would warn; the second is refused
            repo.run(("hike.create", {**HIKE, "title": "Walk two"}))
            change = repo.run(("hike.update", {"id": WALK, "meetTime": "08:30"}), update(capacity=20))
            self.fresh_db(repo, [(WALK, 2), (HIKE_ID, 6), (HIKE_ID, 6), (HIKE_ID, 3)])
            return change, "capacity 12 is below 15 confirmed guests"

        for case in (conflict, past, capacity):
            with self.subTest(case.__name__):
                repo = self.repo()
                repo.run(("hike.create", HIKE))
                repo.make_db([(HIKE_ID, 2)])
                change, reason = case(repo)
                with mock.patch.object(history, "_meeting_warning") as meeting, \
                        mock.patch.object(history, "_move_warning") as move:
                    result = self.assertRejected(repo, "refused", ("history.revert", {"changeId": change["change_id"]}))
                self.assertEqual(result["reason"], reason)
                self.assertNotIn("warnings", result)
                self.assertEqual((meeting.call_count, move.call_count), (0, 0))


if __name__ == "__main__":
    unittest.main()
