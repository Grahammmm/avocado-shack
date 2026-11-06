"""AV2022-11 tests (H06): a completed hike's preview check finds its title (and recap) under past hikes
(``pastShown``, ``recapShown``); a cancelled hike's check finds no RSVP button for its id (``rsvpGone``).
Target tests are pure; product, maker and store targets stay pinned by test_preview_store_address. Capture tests run
the real loopback preview server and Chromium against a HikeRepo writer worktree holding the full tracked site; they
are skipped when PLAYWRIGHT_MODULE is unset. Run: python3 -m unittest hass.tests.test_preview_hike_results -v
"""

import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from hass import preview
from hass.content_model import REPO_ROOT
from hass.tests.test_editor import git
from hass.tests.test_hike_ops import SCHEMA, HikeTestCase

DAY, LATER = "2030-06-01", "2030-06-08"  # far ahead, so a scheduled hike still has an open RSVP on the live clock
AFTER = datetime(2030, 6, 9, 12, 0, tzinfo=timezone(timedelta(hours=-7)))
BEFORE = datetime(2030, 5, 20, 12, 0, tzinfo=timezone(timedelta(hours=-7)))  # fixture clock when a hike is created
COMMUNITY, RECAP = "storefront-mockup/community.json", "Windy but clear."
ODD = 'Cass "Ridge" [loop]'
EVENT_CHECKS = ("eventShown", "pastShown", "recapShown", "rsvpGone")


def started_today():
    """A start already passed but on today's Pacific date: community.js lists a started hike only on its own Pacific
    day, so a fixed "an hour ago" falls on yesterday between 00:00 and 01:00 Pacific and the card disappears."""
    now = datetime.now(timezone.utc)
    midnight = now.astimezone(ZoneInfo("America/Los_Angeles")).replace(hour=0, minute=0, second=0, microsecond=0)
    return now - min(timedelta(hours=1), (now - midnight) / 2)


def hike(title="Cass Hill", day=DAY):
    return {"title": title, "date": day, "time": "09:00", "meetingPoint": "Test trailhead lot", "rsvpEnabled": True,
            "capacity": 12}


class HikeTargetMixin:
    def create(self, repo, title="Cass Hill", day=DAY):
        if not repo.db.exists():
            repo.make_db([])  # capacity edits count confirmed guests, so they need the (empty) guest database
        repo.now = BEFORE  # AVB-05: a start more than 400 days after the fixture clock is a question, not a draft
        return repo.run(("hike.create", hike(title, day)))["records"][0]["key"]

    def target(self, repo, op, args):
        (record,) = repo.run((op, args))["records"]
        return preview.target_for(record)


class HikeTargetTests(HikeTargetMixin, HikeTestCase):
    def test_complete_with_recap_carries_status_id_and_recap_in_order(self):
        repo = self.repo()
        hid = self.create(repo)
        repo.now = AFTER
        target = self.target(repo, "hike.complete", {"id": hid, "recap": RECAP})
        self.assertEqual(list(target), ["kind", "title", "status", "id", "recap"])
        self.assertEqual(target, {"kind": "event", "title": "Cass Hill", "status": "completed", "id": hid,
                                  "recap": RECAP})
        self.assertEqual(self.target(repo, "hike.recap", {"id": hid, "recap": "Calm."})["recap"], "Calm.")

    def test_cancel_and_complete_without_recap_give_empty_recap(self):
        repo = self.repo()
        cancelled, done = self.create(repo), self.create(repo, "Other walk")
        self.assertEqual(self.target(repo, "hike.cancel", {"id": cancelled}),
                         {"kind": "event", "title": "Cass Hill", "status": "cancelled", "id": cancelled, "recap": ""})
        repo.now = AFTER
        self.assertEqual(self.target(repo, "hike.complete", {"id": done})["recap"], "")

    def test_missing_after_or_key_gives_empty_strings(self):
        for record in ({"collection": "events", "after": None}, {"collection": "events", "key": None, "after": {}}):
            with self.subTest(record=record):
                self.assertEqual(preview.target_for(record),
                                 {"kind": "event", "title": "", "status": None, "id": "", "recap": ""})


class ScheduledTargetTests(HikeTargetMixin, HikeTestCase):  # AV1222-05: the card's date, Meet and places lines
    def test_scheduled_target_carries_record_fields(self):
        repo = self.repo()
        hid = self.create(repo)
        target = self.target(repo, "hike.update", {"id": hid, "time": "08:00", "capacity": 12})
        self.assertEqual((target["status"], target["id"], target["meetingPoint"], target["capacity"]),
                         ("scheduled", hid, "Test trailhead lot", 12))
        self.assertTrue(target["rsvpEnabled"])
        self.assertIn("T08:00", target["startsAt"].replace("Z", ""))
        self.assertEqual(target["changed"], {})

    def test_no_capacity_and_rsvps_off(self):
        repo = self.repo()
        hid = self.create(repo)
        self.assertIsNone(self.target(repo, "hike.update", {"id": hid, "noCapacityLimit": True})["capacity"])
        off = self.target(repo, "hike.update", {"id": hid, "rsvpEnabled": False})
        self.assertIs(off["rsvpEnabled"], False)

    def test_changed_lists_only_differing_card_fields(self):
        repo = self.repo()
        hid = self.create(repo)
        self.assertEqual(self.target(repo, "hike.update", {"id": hid, "meetTime": "8:30 AM"})["changed"],
                         {"meetTime": "8:30 AM"})
        self.assertEqual(self.target(repo, "hike.update", {"id": hid, "description": "Easy loop."})["changed"], {})
        self.assertEqual(self.target(repo, "hike.update", {"id": hid, "meetTime": "8:45 AM"})["changed"],
                         {"meetTime": "8:45 AM"})

    def test_cancelled_and_completed_keep_the_old_shape(self):
        repo = self.repo()
        hid, other = self.create(repo), self.create(repo, "Other walk")
        self.assertEqual(list(self.target(repo, "hike.cancel", {"id": hid})), ["kind", "title", "status", "id", "recap"])
        repo.now = AFTER
        self.assertEqual(list(self.target(repo, "hike.complete", {"id": other})),
                         ["kind", "title", "status", "id", "recap"])

    def test_non_integer_capacity_is_none(self):
        for cap in (True, "12", None):
            with self.subTest(cap=cap):
                t = preview.target_for({"collection": "events", "key": "x", "after": {
                    "title": "T", "status": "scheduled", "capacity": cap}})
                self.assertIsNone(t["capacity"])


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class HikeCaptureTests(HikeTargetMixin, HikeTestCase):
    def setUp(self):
        self.r = repo = self.repo()
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (repo.wt / rel).exists():
                (repo.wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, repo.wt / rel)
        git(repo.wt, "add", "-A")
        git(repo.wt, "commit", "-q", "-m", "full site")
        holder = tempfile.TemporaryDirectory(prefix="hass-av2022-11-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"

    def capture(self, target, files=None):
        result = preview.Previewer(self.r.wt, viewports=("phone",)).capture(files or {}, target, self.out)
        self.assertIs(result["checks"].get("noPageErrors"), True, result)
        return result

    def event_checks(self, result):
        return {k: v for k, v in result["checks"].items() if k in EVENT_CHECKS}

    def complete(self, hid, **args):
        self.r.now = AFTER
        return self.target(self.r, "hike.complete", {"id": hid, **args})

    def test_completed_with_recap_is_in_past_hikes_with_that_recap(self):
        result = self.capture(self.complete(self.create(self.r), recap=RECAP))
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        self.assertEqual(self.event_checks(result), {"pastShown": True, "recapShown": True})

    def test_edited_recap_on_a_stale_site_is_not_verified(self):
        hid = self.create(self.r)
        self.complete(hid, recap="Windy.")
        old = (self.r.wt / COMMUNITY).read_bytes()
        target = self.target(self.r, "hike.recap", {"id": hid, "recap": RECAP})
        self.assertEqual(self.event_checks(self.capture(target)), {"pastShown": True, "recapShown": True})
        stale = self.capture(target, {COMMUNITY: old})
        self.assertEqual(self.event_checks(stale), {"pastShown": True, "recapShown": False})
        self.assertEqual((stale["ok"], stale["error"]), (False, "check failed: recapShown"))

    def test_completed_without_recap_checks_past_hikes_only(self):
        hid = self.create(self.r)
        old = (self.r.wt / COMMUNITY).read_bytes()
        target = self.complete(hid)
        result = self.capture(target)
        self.assertEqual((result["ok"], self.event_checks(result)), (True, {"pastShown": True}), result)
        stale = self.capture(target, {COMMUNITY: old})  # still scheduled there: not in past hikes
        self.assertEqual((stale["ok"], self.event_checks(stale)), (False, {"pastShown": False}), stale)

    def test_cancelled_hike_has_no_rsvp_button_and_a_stale_site_fails(self):
        hid, other = self.create(self.r), self.create(self.r, "Other walk")
        old = (self.r.wt / COMMUNITY).read_bytes()
        target = self.target(self.r, "hike.cancel", {"id": hid})
        result = self.capture(target)  # "Other walk" still has its RSVP button; only this id counts
        self.assertEqual((result["ok"], self.event_checks(result)), (True, {"rsvpGone": True}), result)
        stale = self.capture(target, {COMMUNITY: old})
        self.assertEqual(self.event_checks(stale), {"rsvpGone": False})
        self.assertEqual((stale["ok"], stale["error"]), (False, "check failed: rsvpGone"))
        scheduled = self.capture({**target, "status": "scheduled", "title": "Other walk", "id": other})
        self.assertEqual(self.event_checks(scheduled), {"eventShown": True})

    def test_prefix_titles_match_the_exact_past_hike(self):
        first, second = self.create(self.r), self.create(self.r, "Cass Hill again", LATER)
        target = self.complete(first, recap="First.")
        self.complete(second, recap="Second.")  # listed above "Cass Hill" (newer), and its title contains it
        self.assertEqual(self.event_checks(self.capture(target)), {"pastShown": True, "recapShown": True})
        wrong = self.capture({**target, "recap": "Second."})
        self.assertEqual(self.event_checks(wrong), {"pastShown": True, "recapShown": False})
        miss = self.capture({**target, "title": "Cass"})  # only a prefix of both titles: no past hike
        self.assertEqual(self.event_checks(miss), {"pastShown": False, "recapShown": False})

    def test_title_with_quote_and_bracket_is_matched_as_text(self):
        done, gone = self.create(self.r, ODD), self.create(self.r, ODD + " two")
        old = (self.r.wt / COMMUNITY).read_bytes()
        target = self.target(self.r, "hike.cancel", {"id": gone})
        result = self.capture(self.complete(done, recap=RECAP))
        self.assertEqual((result["ok"], self.event_checks(result)), (True, {"pastShown": True, "recapShown": True}))
        self.assertEqual(self.event_checks(self.capture({**target, "id": ODD})), {"rsvpGone": True})
        self.assertEqual(self.event_checks(self.capture(target, {COMMUNITY: old})), {"rsvpGone": False})


    def scheduled(self, result):
        return {k: v for k, v in result["checks"].items() if k in ("eventShown", "dateShown", "meetShown",
                                                                    "placesShown", "fieldsShown")}

    def test_reschedule_checks_date_and_old_page_fails(self):
        hid = self.create(self.r)
        old = (self.r.wt / COMMUNITY).read_bytes()
        target = self.target(self.r, "hike.update", {"id": hid, "time": "08:00"})
        self.assertTrue(self.capture(target)["checks"]["dateShown"])
        stale = self.capture(target, {COMMUNITY: old})
        self.assertIs(stale["checks"]["dateShown"], False)
        self.assertFalse(stale["ok"])

    def test_meeting_point_change(self):
        hid = self.create(self.r)
        old = (self.r.wt / COMMUNITY).read_bytes()
        target = self.target(self.r, "hike.update", {"id": hid, "meetingPoint": "North gate"})
        self.assertIs(self.capture(target)["checks"]["meetShown"], True)
        self.assertIs(self.capture(target, {COMMUNITY: old})["checks"]["meetShown"], False)

    def test_places_lines(self):
        hid = self.create(self.r)
        for args, want in (({"noCapacityLimit": True}, "RSVPs open"),
                           ({"rsvpEnabled": False}, "RSVP details will be shared when confirmed."),
                           ({"rsvpEnabled": True, "capacity": 12}, "12 places available"),
                           ({"capacity": 1}, "1 place available")):
            with self.subTest(args=args):
                target = self.target(self.r, "hike.update", {"id": hid, **args})
                result = self.capture(target)
                self.assertIs(result["checks"]["placesShown"], True, result)
                wrong = self.capture({**target, "capacity": 7, "rsvpEnabled": True} if "capacity" not in args
                                     else {**target, "capacity": args["capacity"] + 1})
                self.assertIs(wrong["checks"]["placesShown"], False)

    def test_meet_time_change_is_checked_and_description_is_not(self):
        hid = self.create(self.r)
        old = (self.r.wt / COMMUNITY).read_bytes()
        target = self.target(self.r, "hike.update", {"id": hid, "meetTime": "8:15 AM"})
        self.assertIs(self.capture(target)["checks"]["fieldsShown"], True)
        self.assertIs(self.capture(target, {COMMUNITY: old})["checks"]["fieldsShown"], False)
        other = self.target(self.r, "hike.update", {"id": hid, "description": "Easy loop."})
        self.assertNotIn("fieldsShown", self.capture(other)["checks"])

    def test_cleared_field_must_be_gone(self):  # the line is absent, so only the cleared list can catch the old page
        hid = self.create(self.r)
        self.target(self.r, "hike.update", {"id": hid, "meetTime": "8:00 AM", "walkTime": "8:30 AM"})
        old = (self.r.wt / COMMUNITY).read_bytes()
        target = self.target(self.r, "hike.update", {"id": hid, "clear": ["meetTime"]})
        self.assertEqual((target.get("changed"), target.get("cleared")), ({}, ["meetTime"]))
        self.assertIs(self.capture(target)["checks"]["fieldsShown"], True)  # normal page: no Meet at line, Start kept
        stale = self.capture(target, {COMMUNITY: old})
        self.assertIs(stale["checks"]["fieldsShown"], False)
        self.assertFalse(stale["ok"])
        plain = self.target(self.r, "hike.update", {"id": hid, "description": "Easy loop."})
        self.assertNotIn("cleared", plain)

    def test_wrong_id_never_matches_a_started_card_without_a_button(self):
        import json
        hid = self.create(self.r)
        target = self.target(self.r, "hike.update", {"id": hid, "rsvpEnabled": False})
        self.assertIs(self.capture(target)["checks"]["dateShown"], True)
        data = json.loads((self.r.wt / COMMUNITY).read_text())  # same title, already started, RSVPs off: no button, no calendar link
        started = started_today()
        for event in data["events"]:
            event["startsAt"] = started.astimezone(timezone(timedelta(hours=-7))).isoformat()
            event["rsvpEnabled"] = False
        files = {COMMUNITY: json.dumps(data).encode()}
        wrong = self.capture({**target, "id": "no-such-hike", "startsAt": started.isoformat()}, files)
        self.assertEqual(self.scheduled(wrong), {"eventShown": False}, wrong)
        self.assertFalse(wrong["ok"])
        right = self.capture({**target, "startsAt": started.isoformat()}, files)
        self.assertEqual(self.scheduled(right).get("eventShown"), True, right)
        self.assertIs(right["checks"]["dateShown"], True, right)

    def test_started_rsvp_enabled_card_reads_closed(self):  # community-server.py closes RSVPs at startsAt even with rsvpEnabled and a meeting point
        import json
        hid = self.create(self.r)
        target = self.target(self.r, "hike.update", {"id": hid, "capacity": 7})
        self.assertTrue(target["rsvpEnabled"] and target["meetingPoint"], target)
        open_page = (self.r.wt / COMMUNITY).read_bytes()
        self.assertIs(self.capture(target)["checks"]["placesShown"], True)
        data = json.loads(open_page)
        started = started_today()
        for event in data["events"]:
            event["startsAt"] = started.astimezone(timezone(timedelta(hours=-7))).isoformat()
        started_target = {**target, "startsAt": started.isoformat()}
        correct = self.capture(started_target, {COMMUNITY: json.dumps(data).encode()})
        self.assertEqual(self.scheduled(correct), {"eventShown": True, "dateShown": True, "meetShown": True,
                                                   "placesShown": True}, correct)
        self.assertTrue(correct["ok"], correct)
        stale = self.capture(started_target, {COMMUNITY: open_page})  # old page still offers places
        self.assertIs(stale["checks"]["placesShown"], False, stale)
        self.assertFalse(stale["ok"])

    def test_changed_value_must_sit_under_its_own_label(self):  # stale card: Meet at still old, the new value is the Start time
        hid = self.create(self.r)
        self.target(self.r, "hike.update", {"id": hid, "walkTime": "9:00 AM", "meetTime": "8:00 AM"})
        old = (self.r.wt / COMMUNITY).read_bytes()
        target = self.target(self.r, "hike.update", {"id": hid, "meetTime": "9:00 AM"})
        self.assertEqual(target["changed"], {"meetTime": "9:00 AM"})
        self.assertIs(self.capture(target)["checks"]["fieldsShown"], True)
        self.assertIs(self.capture(target, {COMMUNITY: old})["checks"]["fieldsShown"], False)

    def test_twin_titles_without_an_rsvp_button(self):  # RSVPs off: the card has no button to name its id
        first, second = self.create(self.r, "Twin", DAY), self.create(self.r, "Twin", LATER)
        self.target(self.r, "hike.update", {"id": first, "rsvpEnabled": False})
        target = self.target(self.r, "hike.update", {"id": second, "rsvpEnabled": False})
        result = self.capture(target)
        self.assertEqual(self.scheduled(result), {"eventShown": True, "dateShown": True, "meetShown": True,
                                                  "placesShown": True}, result)
        self.assertIs(self.capture({**target, "id": first})["checks"]["dateShown"], False)
        mixed = self.target(self.r, "hike.update", {"id": second, "rsvpEnabled": True, "capacity": 5})
        self.assertIs(self.capture(mixed)["checks"]["dateShown"], True)  # the other twin has no button; this one does

    def test_twin_titles_with_a_full_card(self):  # capacity 12, 12 synthetic confirmed guests: "This hike is full.", no button
        first, second = self.create(self.r, "Twin", DAY), self.create(self.r, "Twin", LATER)
        target = self.target(self.r, "hike.update", {"id": second, "description": "Full twin."})
        original = preview.Previewer._copy_site

        def seeded_copy(previewer, tmp, files, assets=None):  # only the disposable preview database gets rows
            site = original(previewer, tmp, files, assets)
            with sqlite3.connect(tmp / "fixture.sqlite3") as db:
                db.execute(SCHEMA)
                for i in range(2):
                    db.execute("INSERT INTO rsvps(event_id,email,name,party_size,created_at) VALUES(?,?,?,?,?)",
                               (second, f"fixture{i}@example.invalid", "Synthetic fixture", 6, "2030-05-20T00:00:00Z"))
            return site

        with mock.patch.object(preview.Previewer, "_copy_site", seeded_copy):
            result = self.capture(target)
            self.assertEqual(self.scheduled(result), {"eventShown": True, "dateShown": True, "meetShown": True,
                                                      "placesShown": True}, result)
            self.assertIs(self.capture({**target, "id": first})["checks"]["dateShown"], False)  # the other twin
            self.assertIs(self.capture({**target, "meetingPoint": "Elsewhere"})["checks"]["meetShown"], False)
            self.assertIs(self.capture({**target, "rsvpEnabled": False})["checks"]["placesShown"], False)  # full is not "details later"
        self.assertIs(self.capture(target)["checks"]["placesShown"], True)  # no guests: "12 places available" also matches

    def test_twin_titles_use_the_id(self):
        first, second = self.create(self.r, "Twin", DAY), self.create(self.r, "Twin", LATER)
        target = self.target(self.r, "hike.update", {"id": second, "capacity": 5})
        result = self.capture(target)
        self.assertEqual(self.scheduled(result), {"eventShown": True, "dateShown": True, "meetShown": True,
                                                  "placesShown": True})
        self.assertIs(self.capture({**target, "id": first})["checks"]["dateShown"], False)
        self.assertIs(self.capture({**target, "title": "Nope"})["checks"]["eventShown"], False)


if __name__ == "__main__":
    unittest.main()
