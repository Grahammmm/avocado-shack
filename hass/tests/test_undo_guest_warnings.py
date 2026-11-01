"""AV1737-10 tests: undoing a hike change that cancels the hike, moves its start or turns RSVPs off carries the
forward op's guest warning; a warning never refuses, and a refused undo adds none.

Fixture repos (test_hike_ops.HikeRepo) and temp RSVP databases with example.invalid rows only; nobody is notified.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import copy
import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass.ops import OpContext, history
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, SCHEMA, HikeTestCase, _req

UNAVAILABLE = f"{HIKE_ID} guest count unavailable; check RSVPs before approving"
OFF = {k: v for k, v in HIKE.items() if k != "capacity"} | {"rsvpEnabled": False}
WALK = "hike-2026-12-05-walk-two"
EVENT = {"id": HIKE_ID, "title": "Test hike", "startsAt": "2026-12-05T09:00:00-08:00",
         "timezone": "America/Los_Angeles", "status": "scheduled", "meetingPoint": "Test trailhead lot",
         "rsvpEnabled": True, "capacity": 12}


def guests(n, eid=HIKE_ID):
    return f"{eid} has {n} confirmed guest{'s' * (n != 1)}; nobody is notified automatically"


class UndoGuestWarningTests(HikeTestCase):
    def undo(self, repo, change):
        """Warnings of the drafted undo, then apply it: a warning never stops the undo."""
        draft = repo.prepare(_req(("history.revert", {"changeId": change["change_id"]})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
        return draft["draft"]["warnings"]

    def test_undo_of_create_cancels_and_warns(self):
        repo = self.repo()
        created = repo.run(("hike.create", HIKE))
        repo.make_db([(HIKE_ID, 1), (HIKE_ID, 1), ("other-event", 4)])
        self.assertEqual(self.undo(repo, created), [guests(2)])
        self.assertEqual(repo.event()["status"], "cancelled")

    def test_undo_of_create_without_guests_or_rsvps_is_silent(self):
        for name, args, rows in (("no guests", HIKE, [("other-event", 3)]), ("rsvps off", OFF, [(HIKE_ID, 4)])):
            with self.subTest(name):
                repo = self.repo()
                created = repo.run(("hike.create", args))
                repo.make_db(rows)
                self.assertEqual(self.undo(repo, created), [])
                self.assertEqual(repo.event()["status"], "cancelled")

    def test_undo_of_a_move_names_the_old_start(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.make_db([(HIKE_ID, 1)])
        moved = repo.run(("hike.update", {"id": HIKE_ID, "time": "10:00"}))
        self.assertEqual(self.undo(repo, moved),
                         [f"{HIKE_ID} moves to 2026-12-05 09:00 Pacific; 1 confirmed guest is not told automatically"])
        self.assertEqual(repo.event()["startsAt"], "2026-12-05T09:00:00-08:00")
        renamed = repo.run(("hike.update", {"id": HIKE_ID, "title": "Renamed"}))  # no move, no cancel: silent
        self.assertEqual(self.undo(repo, renamed), [])

    def test_undo_turning_rsvps_off_warns_once(self):
        for extra in ({}, {"time": "10:00"}):
            with self.subTest(extra=extra):
                repo = self.repo()
                repo.run(("hike.create", OFF))
                repo.make_db([(HIKE_ID, 2), (HIKE_ID, 1)])
                on = repo.run(("hike.update", {"id": HIKE_ID, "rsvpEnabled": True, "capacity": 12, **extra}))
                self.assertEqual(self.undo(repo, on), [guests(3)])
                self.assertIs(repo.event()["rsvpEnabled"], False)

    def test_unreadable_count_warns_and_still_drafts(self):
        for path in ("", "missing.sqlite3"):
            with self.subTest(path=path):
                repo = self.repo()
                created = repo.run(("hike.create", HIKE))
                repo.use_db(str(repo.state.parent / path) if path else "")
                self.assertEqual(self.undo(repo, created), [UNAVAILABLE])
                self.assertEqual(repo.event()["status"], "cancelled")

    def test_two_hikes_in_one_change(self):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "title": "Walk two"}))
        repo.make_db([(HIKE_ID, 2), (WALK, 6), (WALK, 6)])
        both = repo.run(("hike.create", HIKE), ("hike.update", {"id": WALK, "capacity": 20}))
        self.assertEqual(self.undo(repo, both), [guests(2)])  # the capacity undo itself carries no warning
        cancel = repo.run(("hike.cancel", {"id": WALK}))
        self.assertEqual(self.undo(repo, cancel), [])  # undoing a cancel brings the hike back: nothing to warn

    def test_refused_undo_adds_no_warning(self):
        def conflict(repo):
            change = repo.run(("hike.update", {"id": HIKE_ID, "time": "10:00"}))
            repo.run(("hike.update", {"id": HIKE_ID, "title": "Renamed"}))
            return change, f"conflict: events {HIKE_ID} changed after {change['change_id']}"

        def past(repo):
            change = repo.run(("hike.update", {"id": HIKE_ID, "time": "10:00"}))
            repo.now = datetime.fromisoformat(repo.event()["startsAt"])
            return change, "start is in the past"

        def capacity(repo):  # first record (an added hike, cancelled by undo) would warn; the second is refused
            change = repo.run(("hike.create", {**HIKE, "title": "Walk two"}),
                              ("hike.update", {"id": HIKE_ID, "capacity": 20}))
            repo.db.unlink()
            repo.make_db([(WALK, 2), (HIKE_ID, 6), (HIKE_ID, 6), (HIKE_ID, 3)])
            return change, "capacity 12 is below 15 confirmed guests"

        for case in (conflict, past, capacity):
            with self.subTest(case.__name__):
                repo = self.repo()
                repo.run(("hike.create", HIKE))
                repo.make_db([(HIKE_ID, 2)])
                change, reason = case(repo)
                with mock.patch.object(history, "_guest_warning") as guest, \
                        mock.patch.object(history, "_move_warning") as move:
                    result = self.assertRejected(repo, "refused", ("history.revert", {"changeId": change["change_id"]}))
                self.assertEqual(result["reason"], reason)
                self.assertNotIn("warnings", result)
                self.assertEqual((guest.call_count, move.call_count), (0, 0))

    def test_product_and_maker_undos_are_silent(self):
        repo = self.repo()
        repo.make_db([(HIKE_ID, 2)])
        for op, args in (("product.edit", {"id": "photo-product-001", "description": "Buttery."}),
                         ("maker.edit", {"key": "Straus", "name": "Straus Family Creamery"})):
            with self.subTest(op=op):
                self.assertEqual(self.undo(repo, repo.run((op, args))), [])


class DirectRevertTests(HikeTestCase):
    """Records no forward op writes (a stored offset form, an un-cancelled hike) checked on ``_revert`` itself."""

    def revert(self, before, current, seats=2):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state, chg = Path(tmp.name), "chg-" + "a" * 12
        (state / "changes").mkdir()
        record = {"collection": "events", "key": HIKE_ID, "before": before, "after": current}
        (state / "changes" / f"{chg}.json").write_text(json.dumps({"state": "applied", "records": [record]}))
        db = sqlite3.connect(state / "rsvps.sqlite3")
        db.execute(SCHEMA)
        db.executemany("INSERT INTO rsvps(event_id,email,name,party_size,created_at) VALUES(?,?,?,?,?)",
                       [(HIKE_ID, f"guest{n}@example.invalid", f"Guest {n}", 1, "2026-10-30T00:00:00Z")
                        for n in range(seats)])
        db.commit()
        db.close()
        content = SimpleNamespace(products=[], makers={}, store={},
                                  community={"events": [copy.deepcopy(current)], "routeIdeas": []})
        ctx = OpContext(NOW, state, {"guestCountsDb": str(state / "rsvps.sqlite3")}, state_dir=state)
        out = history._revert(content, {"changeId": chg}, ctx)
        self.assertIsInstance(out, list, out)
        self.assertEqual(content.community["events"][0], before)
        return ctx.warnings

    def test_offset_form_only_is_not_a_move(self):
        for form in ("2026-12-05T17:00:00Z", "2026-12-05T17:00:00+00:00"):
            with self.subTest(form=form):
                self.assertEqual(self.revert({**EVENT, "startsAt": form}, EVENT), [])

    def test_restoring_cancelled_warns_once(self):
        for before in ({**EVENT, "status": "cancelled"}, {**EVENT, "status": "cancelled", "rsvpEnabled": False},
                       {**EVENT, "status": "cancelled", "startsAt": "2026-12-06T09:00:00-08:00"}):
            with self.subTest(before=before):
                self.assertEqual(self.revert(before, EVENT), [guests(2)])
        self.assertEqual(self.revert({**EVENT, "status": "cancelled"}, {**EVENT, "rsvpEnabled": False}), [])
