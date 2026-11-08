"""AV1937-05 tests: hike.repeat drafts a new scheduled hike from a real hike's reusable owner text and settings.

Runs through prepare + apply of the H02 editor on the throwaway repo of test_hike_ops.HikeRepo (temp content, synthetic
titles, injected clock, fixture RSVP database); the broken-route cases call the op directly on an in-memory stub.
Run: python3 -B -m unittest hass.tests.test_hike_repeat -v
"""

import copy
import hashlib
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from hass import interpreter_prompt
from hass.content_model import SITE_DIR, load_and_validate
from hass.ops import NeedsDetails, NotFound, Refused, hikes, load_registry
from hass.tests.test_editor import git
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, HikeTestCase

SOURCE = {**HIKE, "title": "Cerro Alto loop", "meetingAddress": "3 Example Road, Testville", "distance": "5 miles",
          "difficulty": "Moderate", "duration": "3 hours", "description": "A steady climb to the ridge.",
          "meetTime": "08:45", "walkTime": "09:00", "returnTime": "12:30", "invitation": "Come along.",
          "bring": "Water and a hat.", "accessNote": "Steep in places.", "trailId": "idea-cass-hill"}
SRC_ID = "hike-2026-12-05-cerro-alto-loop"
NEW_ID = "hike-2026-12-20-cerro-alto-loop"
REPEAT = {"id": SRC_ID, "date": "2026-12-20", "time": "08:30"}
COPIED = ("title", "meetingPoint", "meetingAddress", "distance", "difficulty", "duration", "description", "meetTime",
          "walkTime", "returnTime", "invitation", "bring", "accessNote", "trailId", "rsvpEnabled", "capacity")
LATER = datetime(2026, 12, 6, 12, 0, tzinfo=timezone(timedelta(hours=-8)))  # after the source hike started


def events(repo):
    return {e["id"]: e for e in repo.community()["events"]}


class RepeatTestCase(HikeTestCase):
    def source(self, status="scheduled", **extra):
        repo = self.repo()
        repo.run(("hike.create", {**SOURCE, **extra}))
        if status == "cancelled":
            repo.run(("hike.cancel", {"id": SRC_ID}))
        elif status == "completed":
            repo.now = LATER
            repo.run(("hike.complete", {"id": SRC_ID, "recap": "A lovely day out."}))
            repo.now = NOW
        return repo

    def rejected(self, repo, result_name, args):
        return self.assertRejected(repo, result_name, ("hike.repeat", args))

    def legacy(self, repo, drop):
        """The source hike as an older file left it: some fields absent (committed in the writer worktree)."""
        path = repo.wt / "hass/content/community.json"
        doc = json.loads(path.read_text("utf-8"))
        for event in doc["events"]:
            for field in drop:
                event.pop(field, None)
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "utf-8")
        git(repo.wt, "add", "-A")
        git(repo.wt, "commit", "-q", "-m", "legacy source")


class CopyTests(RepeatTestCase):
    def test_repeat_each_real_status_copies_allowlist_only(self):
        for status in ("scheduled", "completed", "cancelled"):
            with self.subTest(status=status):
                repo = self.source(status)
                before = copy.deepcopy(events(repo)[SRC_ID])
                self.assertEqual(before["status"], status)
                draft = repo.run(("hike.repeat", REPEAT))
                new = events(repo)[NEW_ID]
                self.assertEqual(new, {"id": NEW_ID, "startsAt": "2026-12-20T08:30:00-08:00", "status": "scheduled",
                                       "timezone": "America/Los_Angeles", **{f: SOURCE[f] for f in COPIED}})
                self.assertEqual(events(repo)[SRC_ID], before)  # the source is byte-identical
                [record] = draft["records"]
                self.assertEqual((record["collection"], record["key"], record["before"]), ("events", NEW_ID, None))

    def test_nothing_is_taken_from_the_source_but_the_allowlist(self):
        repo = self.source("completed")
        repo.run(("hike.repeat", REPEAT))
        new = events(repo)[NEW_ID]
        self.assertNotIn("recap", new)
        self.assertEqual(sorted(new), sorted(["id", "startsAt", "timezone", "status", *COPIED]))
        self.assertEqual(events(repo)[SRC_ID]["recap"], "A lovely day out.")

    def test_no_limit_and_rsvps_off_settings_carry_over(self):
        repo = self.repo()
        no_limit = {k: v for k, v in SOURCE.items() if k != "capacity"}
        repo.run(("hike.create", {**no_limit, "noCapacityLimit": True}))
        self.assertNotIn("capacity", events(repo)[SRC_ID])
        repo.run(("hike.repeat", REPEAT))  # RSVPs on without a capacity stays a no-limit hike
        self.assertTrue(events(repo)[NEW_ID]["rsvpEnabled"])
        self.assertNotIn("capacity", events(repo)[NEW_ID])
        off = self.repo()
        off.run(("hike.create", {**SOURCE, "rsvpEnabled": False}))
        draft = off.prepare({"ops": [{"op": "hike.repeat", "args": REPEAT}]})
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(draft["draft"]["warnings"], [f"{NEW_ID}: RSVPs are off, so capacity 12 has no effect until RSVPs are turned on"])
        off.apply(draft["draft"])
        self.assertEqual((events(off)[NEW_ID]["rsvpEnabled"], events(off)[NEW_ID]["capacity"]), (False, 12))

    def test_a_source_without_trail_or_optional_text_copies_only_what_it_has(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.run(("hike.repeat", {"id": HIKE_ID, "date": "2026-12-20", "time": "08:30"}))
        self.assertEqual(sorted(events(repo)["hike-2026-12-20-test-hike"]),
                         sorted(["id", "title", "startsAt", "timezone", "status", "meetingPoint", "rsvpEnabled", "capacity"]))

    def test_no_guest_or_recap_copy(self):
        repo = self.source("completed")
        repo.make_db([(SRC_ID, 2), (SRC_ID, 3)])
        digest = lambda: hashlib.sha256(repo.db.read_bytes()).hexdigest()  # noqa: E731
        before = digest()
        repo.run(("hike.repeat", REPEAT))  # run() also checks club.emailConnected is still False
        self.assertEqual(digest(), before)
        self.assertNotIn("recap", events(repo)[NEW_ID])
        db = sqlite3.connect(repo.db)
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (NEW_ID,)).fetchone(), (0,))
            self.assertEqual(db.execute("SELECT SUM(party_size) FROM rsvps WHERE event_id = ?", (SRC_ID,)).fetchone(), (5,))
        finally:
            db.close()

    def test_repeat_needs_no_guest_database(self):
        repo = self.source()
        repo.use_db(str(repo.db.parent / "missing.sqlite3"))  # unreadable: a repeat never reads it
        repo.run(("hike.repeat", REPEAT))
        self.assertIn(NEW_ID, events(repo))


class ArgumentTests(RepeatTestCase):
    def test_missing_bad_extra_args_and_non_event_ids(self):
        repo = self.source()
        for drop in ("id", "date", "time"):
            with self.subTest(missing=drop):
                result = self.rejected(repo, "needs-details", {k: v for k, v in REPEAT.items() if k != drop})
                self.assertEqual(result["missing"], [drop])
        bad = {"empty id": {**REPEAT, "id": ""}, "null id": {**REPEAT, "id": None}, "id kind": {**REPEAT, "id": 5},
               "path id": {**REPEAT, "id": "../x"}, "word date": {**REPEAT, "date": "Dec 6"},
               "null date": {**REPEAT, "date": None}, "12h time": {**REPEAT, "time": "9am"},
               "null time": {**REPEAT, "time": None}, "extra title": {**REPEAT, "title": "Other"},
               "extra recap": {**REPEAT, "recap": "x"}, "extra flag": {**REPEAT, "copied": True}}
        for name, args in bad.items():
            with self.subTest(case=name):
                self.rejected(repo, "invalid", args)
        self.rejected(repo, "not-found", {**REPEAT, "id": "hike-2030-01-01-nothing"})
        self.rejected(repo, "not-found", {**REPEAT, "id": "preview-sample-hike"})  # the labelled sample is not a hike
        reason = self.rejected(repo, "refused", {**REPEAT, "id": "idea-cass-hill"})["reason"]
        self.assertEqual(reason, "idea-cass-hill is a route idea, not a real hike")
        self.assertEqual(sorted(events(repo)), [SRC_ID])

    def test_legacy_source_missing_required_details_asks(self):
        for drop, missing in ((("meetingPoint",), ["meetingPoint"]), (("rsvpEnabled",), ["rsvpEnabled"]),
                              (("meetingPoint", "rsvpEnabled"), ["meetingPoint", "rsvpEnabled"])):
            with self.subTest(drop=drop):
                repo = self.repo()
                repo.run(("hike.create", {**SOURCE, "rsvpEnabled": "meetingPoint" not in drop}))  # RSVPs on need a point
                self.legacy(repo, drop)
                result = self.rejected(repo, "needs-details", REPEAT)
                self.assertEqual(result["missing"], missing)
                self.assertIn("update that hike first", result["question"])
                self.assertEqual(sorted(events(repo)), [SRC_ID])  # no value was invented


class StartAndTwinTests(RepeatTestCase):
    def test_repeat_dst_past_far_future_and_twin(self):
        repo = self.source()
        gap = self.rejected(repo, "needs-details", {**REPEAT, "date": "2027-03-14", "time": "02:30"})
        self.assertEqual(gap["missing"], ["time"])
        self.assertIn("does not exist in Pacific time", gap["question"])
        fold = self.rejected(repo, "needs-details", {**REPEAT, "date": "2026-11-01", "time": "01:30"})
        self.assertIn("happens twice", fold["question"])
        self.assertEqual(self.rejected(repo, "refused", {**REPEAT, "date": "2026-10-29"})["reason"], "start is in the past")
        far = self.rejected(repo, "needs-details", {**REPEAT, "date": "2027-12-30"})
        self.assertEqual(far["missing"], ["date"])
        twin = self.rejected(repo, "refused", {**REPEAT, "date": "2026-12-05", "time": "14:00"})
        self.assertEqual(twin["reason"], f"{SRC_ID} is already scheduled with this title on 2026-12-05; update it instead")
        repo.run(("hike.repeat", {**REPEAT, "date": "2026-12-06"}))  # the next day is not a twin
        self.assertEqual(sorted(events(repo)), [SRC_ID, "hike-2026-12-06-cerro-alto-loop"])

    def test_repeat_twice_on_the_same_day_refuses_the_second(self):
        repo = self.source()
        repo.run(("hike.repeat", REPEAT))
        again = self.rejected(repo, "refused", {**REPEAT, "time": "10:00"})
        self.assertEqual(again["reason"], f"{NEW_ID} is already scheduled with this title on 2026-12-20; update it instead")

    def test_a_cancelled_twin_does_not_count_but_the_id_gets_a_suffix(self):
        repo = self.source("cancelled")
        repo.run(("hike.repeat", {**REPEAT, "date": "2026-12-05", "time": "14:00"}))
        self.assertEqual(sorted(events(repo)), [SRC_ID, SRC_ID + "-2"])
        self.assertEqual(events(repo)[SRC_ID + "-2"]["startsAt"], "2026-12-05T14:00:00-08:00")

    def test_a_non_twin_slug_collision_succeeds(self):
        repo = self.source()
        repo.run(("hike.create", {**HIKE, "title": "Cerro Alto loop!", "date": "2026-12-20"}))  # same slug, another title
        self.assertIn(NEW_ID, events(repo))
        repo.run(("hike.repeat", REPEAT))
        self.assertEqual(events(repo)[NEW_ID + "-2"]["title"], "Cerro Alto loop")
        self.assertEqual(events(repo)[NEW_ID]["title"], "Cerro Alto loop!")


class RouteTests(RepeatTestCase):
    def test_repeat_invalid_or_hidden_route_refuses(self):
        repo = self.source("cancelled")
        repo.run(("route.hide", {"id": "idea-cass-hill"}))  # allowed: only a cancelled hike links it
        reason = self.rejected(repo, "refused", REPEAT)["reason"]
        self.assertEqual(reason, "route idea idea-cass-hill is hidden; restore it first")
        self.assertEqual(events(repo)[SRC_ID]["trailId"], "idea-cass-hill")  # not dropped, not changed
        repo.run(("route.restore", {"id": "idea-cass-hill"}))
        repo.run(("hike.repeat", REPEAT))
        self.assertEqual(events(repo)[NEW_ID]["trailId"], "idea-cass-hill")

    def test_unknown_or_wrong_kind_trail_id_refuses_without_dropping_it(self):
        source = {"id": "hike-a", "title": "Loop", "startsAt": "2026-12-05T09:00:00-08:00", "status": "completed",
                  "timezone": "America/Los_Angeles", "meetingPoint": "Lot", "rsvpEnabled": False}
        other = {**source, "id": "hike-b", "title": "Other"}
        ctx = SimpleNamespace(now=NOW, warnings=[])
        args = {"id": "hike-a", "date": "2026-12-20", "time": "08:30"}
        for trail, reason in (("idea-gone", "unknown route idea idea-gone"), ("hike-b", "hike-b is a hike, not a route idea")):
            with self.subTest(trail=trail):
                content = SimpleNamespace(community={"events": [{**source, "trailId": trail}, other], "routeIdeas": []})
                out = hikes._hike_repeat(content, args, ctx)
                self.assertEqual(out, Refused(reason))
                self.assertEqual(len(content.community["events"]), 2)
        content = SimpleNamespace(community={"events": [source], "routeIdeas": [{"id": "idea-x"}]})
        self.assertEqual(hikes._hike_repeat(content, {**args, "id": "idea-x"}, ctx), Refused("idea-x is a route idea, not a real hike"))
        self.assertEqual(hikes._hike_repeat(content, {**args, "id": "nope"}, ctx), NotFound("nope"))
        self.assertIsInstance(hikes._hike_repeat(SimpleNamespace(community={"events": [{k: v for k, v in source.items() if k != "meetingPoint"}], "routeIdeas": []}), args, ctx), NeedsDetails)


class ApprovalAndUndoTests(RepeatTestCase):
    def test_prepare_approval_and_undo(self):
        repo = self.source()
        head, content = repo.head(), (repo.wt / "hass/content/community.json").read_bytes()
        prepared = repo.prepare({"ops": [{"op": "hike.repeat", "args": REPEAT}]})
        self.assertEqual(prepared["result"], "ok", prepared)
        self.assertEqual(repo.head(), head)  # prepare writes no content
        self.assertEqual((repo.wt / "hass/content/community.json").read_bytes(), content)
        self.assertEqual(repo.status(), "")
        applied = repo.apply(prepared["draft"])
        self.assertEqual(applied["result"], "applied", applied)
        self.assertIn("storefront-mockup/community.json", prepared["draft"]["generated"])  # the invitation is generated
        self.assertIn(NEW_ID, (repo.wt / "storefront-mockup/community.json").read_text("utf-8"))
        change_id = prepared["draft"]["change_id"]
        repo.run(("hike.update", {"id": SRC_ID, "bring": "Water, a hat and lunch."}))  # a later unrelated edit
        repo.run(("history.revert", {"changeId": change_id}))
        self.assertEqual(events(repo)[NEW_ID]["status"], "cancelled")  # cancelled, never deleted
        self.assertEqual(events(repo)[SRC_ID]["bring"], "Water, a hat and lunch.")
        self.assertEqual(events(repo)[SRC_ID]["status"], "scheduled")

    def test_undo_refuses_after_the_new_hike_was_edited(self):
        repo = self.source()
        change_id = repo.run(("hike.repeat", REPEAT))["change_id"]
        repo.run(("hike.update", {"id": NEW_ID, "bring": "Something else."}))
        result = self.assertRejected(repo, "refused", ("history.revert", {"changeId": change_id}))
        self.assertEqual(result["reason"], f"conflict: events {NEW_ID} changed after {change_id}")
        self.assertEqual(events(repo)[NEW_ID]["status"], "scheduled")

    def test_undo_is_refused_twice_and_the_slot_is_free_again(self):
        repo = self.source()
        change_id = repo.run(("hike.repeat", REPEAT))["change_id"]
        repo.run(("history.revert", {"changeId": change_id}))
        self.assertEqual(events(repo)[NEW_ID]["status"], "cancelled")
        repo.run(("hike.repeat", REPEAT))  # the cancelled repeat is no twin
        self.assertEqual(events(repo)[NEW_ID + "-2"]["status"], "scheduled")


class PromptTests(unittest.TestCase):
    def test_prompt_repeat_rule_and_signature(self):
        registry = load_registry()
        self.assertEqual(list(registry["hike.repeat"].args), ["id", "date", "time"])
        self.assertTrue(all(a.required for a in registry["hike.repeat"].args.values()))
        prompt = interpreter_prompt.build(registry, load_and_validate(SITE_DIR.parent / "hass" / "content", SITE_DIR))
        self.assertIn("hike.repeat(id: id, required; date: date, required; time: time, required)", prompt)
        rule = next(line for line in prompt.splitlines() if "hike.repeat" in line and line.startswith("- "))
        self.assertIn("repeat a listed hike", rule)
        self.assertIn("if the hike, date or time is unclear, ask", rule)
        self.assertIn("Never make the sample hike into a real hike", rule)


if __name__ == "__main__":
    unittest.main()
