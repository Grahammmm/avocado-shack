"""AV2137-02 tests: hike.update changing where or when guests meet (meetingPoint/meetingAddress, meetTime) or the
route (trailId) on a scheduled RSVP hike warns how many confirmed guests are not told; never a refusal.
Fixture repos and placeholder example.invalid RSVP rows only (test_hike_ops / H06 helpers); nobody is notified.
Run: python3 -B -m unittest hass.tests.test_hike_meeting_warning
"""

import sqlite3
import unittest
from unittest import mock

from hass import editor
from hass.ops import hikes
from hass.tests.test_conversation import SETTINGS, _ops
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, SCHEMA, HikeTestCase, _req
from hass.tests.test_undo import H06TestCase

ROUTE, ROUTE2 = "idea-point-buchon", "idea-cass-hill"
UNAVAILABLE = f"{HIKE_ID} guest count unavailable; check RSVPs before approving"
THREE_OFF = f"{HIKE_ID} has 3 confirmed guests; nobody is notified automatically"
MOVED = f"{HIKE_ID} moves to 2026-12-05 10:30 Pacific; 3 confirmed guests are not told automatically"
ROWS = [(HIKE_ID, 1), (HIKE_ID, 2), ("hike-2026-12-06-other", 4)]  # 3 seats here; the other event never counts


def told(group, n=3):
    return f"{HIKE_ID}: the {group} changes; {n} confirmed guest{'s are' if n != 1 else ' is'} not told automatically"


PLACE, TIME, ROUTE_LINE = told("meeting place"), told("meet time"), told("route")


def update(**args):
    return ("hike.update", {"id": HIKE_ID, **args})


class MeetingWarningTests(HikeTestCase):
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

    def seats_spy(self):
        spy = mock.patch.object(hikes, "_seats", wraps=hikes._seats)
        self.addCleanup(spy.stop)
        return spy.start()

    def test_meeting_fields_warn_seat_totals(self):
        cases = (({"meetingPoint": "New trailhead"}, [PLACE]), ({"meetingAddress": "34 Example Road"}, [PLACE]),
                 ({"meetTime": "08:30"}, [TIME]), ({"trailId": ROUTE}, [ROUTE_LINE]),
                 ({"meetingPoint": "New trailhead", "meetingAddress": "34 Example Road"}, [PLACE]),  # one place line
                 ({"meetTime": "08:30", "meetingAddress": "34 Example Road"}, [PLACE, TIME]),
                 ({"trailId": ROUTE, "meetTime": "08:30", "meetingPoint": "New trailhead"}, [PLACE, TIME, ROUTE_LINE]))
        for args, expected in cases:
            with self.subTest(args=args):
                repo = self.hike_repo(ROWS)
                self.assertEqual(self.warnings(repo, update(**args)), expected)
                self.assertEqual({k: repo.event()[k] for k in args}, args)
        one = self.hike_repo([(HIKE_ID, 1)])
        self.assertEqual(self.warnings(one, update(meetTime="08:30")),
                         [f"{HIKE_ID}: the meet time changes; 1 confirmed guest is not told automatically"])

    def test_route_set_replace_clear_and_optional_clear(self):
        repo = self.hike_repo(ROWS, trailId=ROUTE, meetingAddress="33 Example Road", meetTime="08:00")
        self.assertEqual(self.warnings(repo, update(trailId=ROUTE2)), [ROUTE_LINE])
        self.assertEqual(self.warnings(repo, update(clear=["trailId"])), [ROUTE_LINE])
        self.assertNotIn("trailId", repo.event())
        self.assertEqual(self.warnings(repo, update(clear=["meetingAddress", "meetTime"])), [PLACE, TIME])
        spy = self.seats_spy()
        silent = (update(title="Renamed 1", clear=["trailId", "meetingAddress"]),  # already absent
                  update(title="Renamed 2", meetingPoint="Test   trailhead  lot"))  # spacing only
        for ops in silent:
            with self.subTest(ops=ops):
                self.assertEqual(self.warnings(repo, ops), [])
        repo.run(update(trailId=ROUTE))
        spy.reset_mock()
        self.assertEqual(self.warnings(repo, update(title="Renamed 4", trailId=ROUTE)), [])  # the same route
        spy.assert_not_called()

    def test_unavailable_is_warning_not_refusal(self):
        def unset(repo): pass

        def missing_file(repo): repo.use_db(str(repo.db.parent / "absent.sqlite3"))

        def no_table(repo):
            sqlite3.connect(repo.db).close()
            repo.use_db(str(repo.db))

        def bad_row(party):  # a loose schema lets a bad party size in; good rows elsewhere cannot mask it
            def setup(repo):
                db = sqlite3.connect(repo.db)
                db.execute("CREATE TABLE rsvps (event_id TEXT, email TEXT, name TEXT, party_size, created_at TEXT)")
                db.executemany("INSERT INTO rsvps VALUES(?,?,?,?,?)", [
                    (HIKE_ID, "a@example.invalid", "A", 2, "t"), (HIKE_ID, "b@example.invalid", "B", party, "t"),
                    ("hike-2026-12-06-other", "c@example.invalid", "C", 3, "t")])
                db.commit()
                db.close()
                repo.use_db(str(repo.db))
            return setup

        cases = [("unset", unset), ("missing file", missing_file), ("missing table", no_table)]
        cases += [(f"party {party!r}", bad_row(party)) for party in (None, "two", 0, -1, 1.5)]
        for name, setup in cases:
            with self.subTest(name):
                repo = self.hike_repo()
                setup(repo)
                before = repo.db.read_bytes() if repo.db.exists() else None
                draft = repo.prepare(_req(update(meetingPoint="New trailhead", meetTime="08:30")))
                self.assertEqual((draft["result"], draft["draft"]["warnings"]), ("ok", [UNAVAILABLE]))
                self.assertEqual(repo.event()["meetingPoint"], "Test trailhead lot")  # nothing before approval
                self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
                self.assertEqual(repo.event()["meetingPoint"], "New trailhead")
                self.assertEqual(repo.db.read_bytes() if repo.db.exists() else None, before)

    def test_zero_off_and_invalid_are_silent(self):
        for rows in ([], [("hike-2026-12-06-other", 2)]):
            with self.subTest(rows=rows):
                self.assertEqual(self.warnings(self.hike_repo(rows), update(meetingPoint="New trailhead")), [])
        off = self.hike_repo(ROWS, rsvpEnabled=False)
        spy = self.seats_spy()
        self.assertEqual(self.warnings(off, update(meetingPoint="New trailhead", trailId=ROUTE)), [])
        spy.assert_not_called()
        on = self.warnings(off, update(rsvpEnabled=True, noCapacityLimit=True, meetTime="08:30"))  # off -> on
        self.assertEqual(on, [])
        repo = self.hike_repo(ROWS)
        spy.reset_mock()
        refused = ((update(trailId="idea-none"), "unknown route idea idea-none"),
                   (update(meetTime="08:30", clear=["meetTime"]), "meetTime cannot be set and cleared together"),
                   (("hike.update", {"id": "hike-none", "meetTime": "08:30"}), None))
        for op, reason in refused:
            with self.subTest(op=op):
                result = repo.prepare(_req(op))
                self.assertNotEqual(result["result"], "ok", result)
                if reason:
                    self.assertEqual(result["reason"], reason)
                self.assertNotIn("warnings", result)
        spy.assert_not_called()
        repo.run(("hike.cancel", {"id": HIKE_ID}))
        spy.reset_mock()
        self.assertEqual(repo.prepare(_req(update(meetTime="08:30")))["result"], "refused")
        spy.assert_not_called()

    def test_combined_move_details_off_precedence(self):
        repo = self.hike_repo(ROWS)
        self.assertEqual(self.warnings(repo, update(time="10:30", meetingPoint="New", meetTime="10:00", trailId=ROUTE)),
                         [MOVED, PLACE, TIME, ROUTE_LINE])
        repo = self.hike_repo(ROWS)
        self.assertEqual(self.warnings(repo, update(time="10:30", meetingPoint="New", rsvpEnabled=False)), [THREE_OFF])
        repo = self.hike_repo()
        repo.use_db(str(repo.db.parent / "absent.sqlite3"))
        self.assertEqual(self.warnings(repo, update(time="10:30", meetingPoint="New", meetTime="10:00")), [UNAVAILABLE])


class ProposalMeetingWarningTests(H06TestCase):
    def setUp(self):
        super().setUp()
        draft = editor.prepare(_req(("hike.create", HIKE)), state=str(self.repo.state), now=NOW)
        editor.apply(draft["draft"]["change_id"], draft["draft"]["draft_hash"], state=str(self.repo.state), now=NOW)
        self.db = self.repo.state.parent / "rsvps.sqlite3"
        db = sqlite3.connect(self.db)
        db.execute(SCHEMA)
        for n, party in enumerate((1, 2), 1):
            db.execute("INSERT INTO rsvps(event_id,email,name,party_size,created_at) VALUES(?,?,?,?,?)",
                       (HIKE_ID, f"walker{n}@example.invalid", f"Walker Name {n}", party, "2026-10-30T00:00:00Z"))
        db.commit()
        db.close()
        self.set_settings({**SETTINGS, "guestCountsDb": str(self.db)})
        self.interp.mapping.update({"change the meeting": _ops(update(meetingPoint="New trailhead", meetTime="08:30",
                                                                      trailId=ROUTE))})
        self.conv = self.open()

    def test_proposal_and_show_keep_specific_plain_warning(self):
        draft, reply = self.propose("change the meeting")
        lines = [f"Heads up: The {g} changes. 3 guests have signed up, and nobody is told automatically."
                 for g in ("meeting place", "meet time", "route")]
        self.assertIn("\n" + "\n".join(lines), reply)
        self.assertEqual(self.say(f"show {draft['code']}"), "show")
        [shown] = self.replies()
        for text in (reply, shown):
            self.assertIn(lines[0], text)
            for secret in ("walker", "Walker Name", "example.invalid", HIKE_ID, "double-check"):
                self.assertNotIn(secret, text)
        self.assertEqual(self.drafts()[-1]["state"], "proposed")  # nothing applied before yes
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertNotIn("walker", " ".join(row["text"] for row in self.sent()).lower())
        self.assertEqual(self.drafts()[-1]["state"], "verified")

    def test_unknown_count_prose(self):
        self.set_settings({**SETTINGS, "guestCountsDb": str(self.db.parent / "absent.sqlite3")})
        self.conv = self.open()
        _draft, reply = self.propose("change the meeting")
        self.assertEqual(reply.count("Heads up:"), 1)
        self.assertIn("Heads up: I can't see how many guests have signed up. Please check before you say yes.", reply)


if __name__ == "__main__":
    unittest.main()
