"""AV2022-11 tests (H06): a completed hike's preview check finds its title (and recap) under past hikes
(``pastShown``, ``recapShown``); a cancelled hike's check finds no RSVP button for its id (``rsvpGone``).
Target tests are pure; product, maker and store targets stay pinned by test_preview_store_address. Capture tests run
the real loopback preview server and Chromium against a HikeRepo writer worktree holding the full tracked site; they
are skipped when PLAYWRIGHT_MODULE is unset. Run: python3 -m unittest hass.tests.test_preview_hike_results -v
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import preview
from hass.content_model import REPO_ROOT
from hass.tests.test_editor import git
from hass.tests.test_hike_ops import HikeTestCase

DAY, LATER = "2030-06-01", "2030-06-08"  # far ahead, so a scheduled hike still has an open RSVP on the live clock
AFTER = datetime(2030, 6, 9, 12, 0, tzinfo=timezone(timedelta(hours=-7)))
BEFORE = datetime(2030, 5, 20, 12, 0, tzinfo=timezone(timedelta(hours=-7)))  # fixture clock when a hike is created
COMMUNITY, RECAP = "storefront-mockup/community.json", "Windy but clear."
ODD = 'Cass "Ridge" [loop]'
EVENT_CHECKS = ("eventShown", "pastShown", "recapShown", "rsvpGone")


def hike(title="Cass Hill", day=DAY):
    return {"title": title, "date": day, "time": "09:00", "meetingPoint": "Test trailhead lot", "rsvpEnabled": True,
            "capacity": 12}


class HikeTargetMixin:
    def create(self, repo, title="Cass Hill", day=DAY):
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


if __name__ == "__main__":
    unittest.main()
