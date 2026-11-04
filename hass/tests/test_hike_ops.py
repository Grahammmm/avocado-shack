"""H04 tests: real-hike create / update / cancel / complete ops, exact local time and capacity against guests.

Every op runs through ``prepare`` + ``apply`` of the H02 editor on a throwaway Git repo with a linked writer worktree
and a private temp state dir (see test_editor.WriterRepo), with the clock injected. The RSVP database is a temp
SQLite file with placeholder rows only. Nothing touches the checkout, the live service or the real community database.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from hass import editor
from hass.tests.test_editor import WriterRepo

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone(timedelta(hours=-7)))
HIKE = {"title": "Test hike", "date": "2026-12-05", "time": "09:00", "meetingPoint": "Test trailhead lot",
        "rsvpEnabled": True, "capacity": 12}
HIKE_ID = "hike-2026-12-05-test-hike"
SCHEMA = """CREATE TABLE rsvps (
  id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, email TEXT NOT NULL, name TEXT NOT NULL,
  party_size INTEGER NOT NULL CHECK(party_size BETWEEN 1 AND 6), created_at TEXT NOT NULL,
  UNIQUE(event_id,email))"""


def _req(*ops):
    return {"ops": [{"op": name, "args": args} for name, args in ops]}


class HikeRepo(WriterRepo):
    """WriterRepo using the production op registry (hass.ops.hikes) and an injected clock."""

    def __init__(self):
        super().__init__()
        self.now = NOW
        self.db = self.state.parent / "rsvps.sqlite3"

    def prepare(self, request):
        return editor.prepare(request, state=str(self.state), now=self.now)

    def apply(self, draft):
        return editor.apply(draft["change_id"], draft["draft_hash"], state=str(self.state), now=self.now)

    def run(self, *ops):
        draft = self.prepare(_req(*ops))
        assert draft["result"] == "ok", draft
        result = self.apply(draft["draft"])
        assert result["result"] == "applied", result
        assert self.community()["club"]["emailConnected"] is False
        return draft["draft"]

    def community(self):
        return json.loads((self.wt / "hass/content/community.json").read_text("utf-8"))

    def event(self, event_id=HIKE_ID):
        return next(e for e in self.community()["events"] if e["id"] == event_id)

    def make_db(self, rows):
        """Fixture RSVP database with the community-server schema and placeholder guests; point the settings at it."""
        db = sqlite3.connect(self.db)
        db.execute(SCHEMA)
        for n, (event_id, party) in enumerate(rows, 1):
            db.execute("INSERT INTO rsvps(event_id,email,name,party_size,created_at) VALUES(?,?,?,?,?)",
                       (event_id, f"guest{n}@example.invalid", f"Guest {n}", party, "2026-10-30T00:00:00Z"))
        db.commit()
        db.close()
        self.use_db(str(self.db))

    def use_db(self, path):
        config = json.loads((self.state / "config.json").read_text("utf-8"))
        config["settings"]["guestCountsDb"] = path
        editor._write_json(self.state / "config.json", config)


class HikeTestCase(unittest.TestCase):
    def repo(self):
        repo = HikeRepo()
        self.addCleanup(repo.cleanup)
        return repo

    def assertRejected(self, repo, result_name, *ops):
        head, drafts = repo.head(), repo.drafts()
        result = repo.prepare(_req(*ops))
        self.assertEqual(result["result"], result_name, result)
        self.assertEqual((repo.head(), repo.drafts()), (head, drafts))
        return result


class CreateTests(HikeTestCase):
    def test_create_writes_event_and_generated_json(self):
        repo = self.repo()
        self.assertEqual(repo.community()["events"], [])
        repo.run(("hike.create", HIKE))
        event = repo.event()
        self.assertEqual((event["startsAt"], event["timezone"], event["status"]),
                         ("2026-12-05T09:00:00-08:00", "America/Los_Angeles", "scheduled"))
        self.assertEqual((event["title"], event["meetingPoint"], event["rsvpEnabled"], event["capacity"]),
                         ("Test hike", "Test trailhead lot", True, 12))
        site = json.loads((repo.wt / "storefront-mockup/community.json").read_text("utf-8"))
        self.assertEqual([e["id"] for e in site["events"]], [HIKE_ID])
        repo.run(("hike.create", {**HIKE, "title": "Test-hike", "capacity": 8}))  # same slug and date: the id gets a suffix
        self.assertEqual([e["id"] for e in repo.community()["events"]], [HIKE_ID, HIKE_ID + "-2"])

    def test_missing_details_give_needs_details_and_no_draft(self):
        repo = self.repo()
        for field in ("date", "time", "meetingPoint"):
            with self.subTest(field=field):
                args = {k: v for k, v in HIKE.items() if k != field}
                result = self.assertRejected(repo, "needs-details", ("hike.create", args))
                self.assertEqual(result["missing"], [field])
        for extra in ({}, {"capacity": 12, "noCapacityLimit": True}):
            with self.subTest(extra=extra):
                args = {k: v for k, v in HIKE.items() if k != "capacity"}
                result = self.assertRejected(repo, "needs-details", ("hike.create", {**args, **extra}))
                self.assertEqual(result["missing"], ["capacity", "noCapacityLimit"])
        repo.run(("hike.create", {**{k: v for k, v in HIKE.items() if k != "capacity"}, "noCapacityLimit": True}))
        self.assertNotIn("capacity", repo.event())
        repo.run(("hike.create", {**HIKE, "title": "Walk two", "rsvpEnabled": False, "capacity": 5}))

    def test_exact_local_time(self):
        repo = self.repo()
        repeated = self.assertRejected(repo, "needs-details", ("hike.create", {**HIKE, "date": "2026-11-01", "time": "01:30"}))
        self.assertEqual(repeated["missing"], ["time"])
        self.assertIn("-07:00", repeated["question"])
        self.assertIn("-08:00", repeated["question"])
        gap = self.assertRejected(repo, "needs-details", ("hike.create", {**HIKE, "date": "2027-03-14", "time": "02:30"}))
        self.assertEqual(gap["missing"], ["time"])
        refused = self.assertRejected(repo, "refused", ("hike.create", {**HIKE, "date": "2026-10-29"}))
        self.assertEqual(refused["reason"], "start is in the past")
        repo.run(("hike.create", {**HIKE, "date": "2027-07-04"}))
        self.assertEqual(repo.event("hike-2027-07-04-test-hike")["startsAt"], "2027-07-04T09:00:00-07:00")


class CapacityTests(HikeTestCase):
    def test_capacity_never_below_confirmed_guests(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        self.assertEqual(self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 9}))["reason"],
                         "guest count unavailable")
        repo.use_db(str(repo.state.parent / "missing.sqlite3"))
        self.assertEqual(self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 9}))["reason"],
                         "guest count unavailable")
        repo.make_db([(HIKE_ID, 3), (HIKE_ID, 2), ("some-other-event", 6)])
        before = repo.db.read_bytes()
        refused = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 4}))
        self.assertIn("capacity 4 is below 5 confirmed guests", refused["reason"])
        self.assertEqual(repo.event()["capacity"], 12)
        repo.run(("hike.update", {"id": HIKE_ID, "capacity": 5}))
        self.assertEqual(repo.event()["capacity"], 5)
        repo.run(("hike.update", {"id": HIKE_ID, "noCapacityLimit": True}))
        self.assertNotIn("capacity", repo.event())
        self.assertEqual(repo.db.read_bytes(), before)


class LifecycleTests(HikeTestCase):
    def test_reschedule_keeps_id_time_and_rsvps(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.make_db([(HIKE_ID, 3), (HIKE_ID, 2)])
        before = repo.db.read_bytes()
        repo.run(("hike.update", {"id": HIKE_ID, "date": "2027-07-04"}))
        self.assertEqual(repo.event()["startsAt"], "2027-07-04T09:00:00-07:00")  # same local 09:00, summer offset
        repo.run(("hike.update", {"id": HIKE_ID, "time": "10:15", "meetingPoint": "Second lot"}))
        event = repo.event()
        self.assertEqual((event["startsAt"], event["meetingPoint"], event["capacity"]),
                         ("2027-07-04T10:15:00-07:00", "Second lot", 12))
        self.assertEqual(self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "date": "2026-10-30"}))["reason"],
                         "start is in the past")
        self.assertEqual(repo.db.read_bytes(), before)
        rows = sqlite3.connect(repo.db).execute("SELECT event_id, party_size FROM rsvps ORDER BY id").fetchall()
        self.assertEqual(rows, [(HIKE_ID, 3), (HIKE_ID, 2)])

    def test_cancel_then_nothing_more(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.run(("hike.cancel", {"id": HIKE_ID}))
        self.assertEqual(repo.event()["status"], "cancelled")
        for op, args in (("hike.update", {"title": "New name"}), ("hike.cancel", {}), ("hike.complete", {})):
            with self.subTest(op=op):
                refused = self.assertRejected(repo, "refused", (op, {"id": HIKE_ID, **args}))
                self.assertIn("cancelled", refused["reason"])
        self.assertRejected(repo, "not-found", ("hike.cancel", {"id": "hike-2026-12-05-nothing"}))

    def test_complete_only_after_start(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        self.assertIn("not started", self.assertRejected(repo, "refused", ("hike.complete", {"id": HIKE_ID, "recap": "Done."}))["reason"])
        repo.now = datetime(2026, 12, 5, 12, 0, tzinfo=timezone(timedelta(hours=-8)))
        repo.run(("hike.complete", {"id": HIKE_ID, "recap": "Twelve of us walked the loop."}))
        event = repo.event()
        self.assertEqual((event["status"], event["recap"]), ("completed", "Twelve of us walked the loop."))
        self.assertIn("completed", self.assertRejected(repo, "refused", ("hike.cancel", {"id": HIKE_ID}))["reason"])


class SamplesStayAsSamplesTests(HikeTestCase):
    def test_route_idea_is_linked_not_copied(self):
        repo = self.repo()
        idea_before = next(i for i in repo.community()["routeIdeas"] if i["id"] == "idea-fiscalini-bluff")
        repo.run(("hike.create", {**HIKE, "trailId": "idea-fiscalini-bluff"}))
        event = repo.event()
        self.assertEqual(event["trailId"], "idea-fiscalini-bluff")
        self.assertEqual(set(event), {"id", "title", "startsAt", "timezone", "status", "meetingPoint", "rsvpEnabled",
                                      "capacity", "trailId"})
        idea_after = next(i for i in repo.community()["routeIdeas"] if i["id"] == "idea-fiscalini-bluff")
        self.assertEqual(json.dumps(idea_after), json.dumps(idea_before))
        for field in ("distance", "difficulty", "description"):
            self.assertNotIn(field, event)
        self.assertRejected(repo, "invalid", ("hike.create", {**HIKE, "id": "idea-point-buchon"}))
        self.assertRejected(repo, "invalid", ("hike.create", {**HIKE, "id": "preview-point-buchon"}))
        self.assertRejected(repo, "refused", ("hike.create", {**HIKE, "title": "Other hike", "trailId": "preview-point-buchon"}))


if __name__ == "__main__":
    unittest.main()
