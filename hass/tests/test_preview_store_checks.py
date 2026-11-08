"""AV1222-03 tests (H06): the store result check also finds the intro text (``introShown``) and, after
``store.confirm_selection``, the "Selection last checked" line (``selectionShown``); a failed check is named in the reply.

Target and reply tests are pure. Capture tests run the real loopback preview and Chromium against a StoreRepo worktree
holding the full tracked site; skipped when PLAYWRIGHT_MODULE is unset.
Run: python3 -B -m unittest hass.tests.test_preview_store_checks -v
"""

import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hass import owner_answers, preview, sitegen
from hass.content_model import DEFAULT_INTRO, REPO_ROOT, shop_today
from hass.tests.test_editor import git
from hass.tests.test_store_ops import INDEX, REVERT, StoreTestCase

SET_INTRO, CONFIRM = "store.set_intro", "store.confirm_selection"
FRESH = "Fresh from the coast."


def _store_record(before=None, **after):
    return {"collection": "store", "key": None, "before": before or {}, "after": {"hours": ["Open daily"], **after}}


class TargetTests(unittest.TestCase):
    def test_intro_is_carried_and_none_means_default(self):
        self.assertEqual(preview.target_for(_store_record(intro=FRESH))["intro"], FRESH)
        self.assertIsNone(preview.target_for(_store_record(before={"intro": FRESH}))["intro"])  # undo: intro removed

    def test_selection_line_only_when_the_check_date_changed_and_today_is_given(self):
        today = date(2026, 11, 4)
        record = _store_record(before={}, selection_checked_on="2026-11-04")
        self.assertEqual(preview.target_for(record, today)["selectionLine"], "Selection last checked by Michael on Wednesday, November 4.")
        self.assertNotIn("selectionLine", preview.target_for(record))  # no caller value
        hours_only = _store_record(before={"selection_checked_on": "2026-11-04"}, selection_checked_on="2026-11-04")
        self.assertNotIn("selectionLine", preview.target_for(hours_only, today))
        self.assertIsNotNone(preview.target_for(hours_only, today)["hours"])

    def test_backdated_check_line_carries_the_stale_tail(self):
        record = _store_record(selection_checked_on="2026-10-27")
        line = preview.target_for(record, date(2026, 11, 4))["selectionLine"]
        self.assertTrue(line.endswith("(more than a week ago - call or visit to confirm)."), line)

    def test_non_text_intro_is_unreadable(self):
        self.assertEqual(preview.target_for(_store_record(intro=["x"])), {"kind": "unreadable"})


class ReplyTests(unittest.TestCase):
    def reason(self, failed):
        return owner_answers.preview_reason(f"store store: check failed: {failed}")

    def test_failed_checks_are_named_in_check_name_order(self):
        self.assertEqual(self.reason("introShown, selectionShown"),
                         "the preview didn't show the change the way it should: the home-page intro, the shelf check line")
        self.assertIn("the home-page intro", self.reason("introShown"))

    def test_unknown_key_is_not_shown(self):
        text = self.reason("fooShown")
        self.assertNotIn("fooShown", text)
        self.assertEqual(text, "the preview didn't show the change the way it should")
        mixed = self.reason("fooShown, introShown")
        self.assertIn("the home-page intro", mixed)
        self.assertNotIn("foo", mixed)

    def test_every_existing_check_key_has_words(self):
        for key in ("productShown", "description", "availabilityShown", "imageShown", "hoursShown", "addressShown", "headlineShown",
                    "storyShown", "introShown", "selectionShown", "eventShown", "pastShown", "recapShown", "rsvpGone",
                    "makerName", "makerPlace", "makerHidden"):
            self.assertIn(key, owner_answers.CHECK_WORDS)


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class CaptureTests(StoreTestCase):
    def setUp(self):
        self.r = repo = self.repo()
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (repo.wt / rel).exists():
                (repo.wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, repo.wt / rel)
        git(repo.wt, "add", "-A")
        git(repo.wt, "commit", "-q", "-m", "full site")
        self.old_index = repo.read(INDEX)
        holder = tempfile.TemporaryDirectory(prefix="hass-av1222-03-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"

    def shot(self, draft, files=None, today=None):
        target = preview.target_for(draft["records"][0], today)
        return preview.Previewer(self.r.wt, viewports=("phone",)).capture(files or {}, target, self.out)

    def test_new_intro_found_and_old_page_fails(self):
        draft = self.r.run((SET_INTRO, {"text": FRESH}))
        good = self.shot(draft)
        self.assertEqual((good["ok"], good["checks"]["introShown"]), (True, True), good)
        old = self.shot(draft, {INDEX: self.old_index})
        self.assertEqual((old["checks"]["introShown"], old["error"]), (False, "check failed: introShown"))

    def test_spaces_in_the_intro_do_not_fail_the_check(self):
        draft = self.r.run((SET_INTRO, {"text": "Fresh   from the   coast."}))
        self.assertIs(self.shot(draft)["checks"]["introShown"], True)

    def test_undo_expects_the_default_intro_and_finds_it(self):
        first = self.r.run((SET_INTRO, {"text": FRESH}))
        undo = self.r.run((REVERT, {"changeId": first["change_id"]}))
        self.assertIn(DEFAULT_INTRO, self.r.text(INDEX))
        self.assertIs(self.shot(undo)["checks"]["introShown"], True)

    def test_hours_only_change_still_checks_the_intro_and_no_selection(self):
        draft = self.r.run(("store.set_hours", {"hours": ["Open daily 8-6"]}))
        checks = self.shot(draft, today=shop_today())["checks"]
        self.assertIs(checks["introShown"], True)
        self.assertNotIn("selectionShown", checks)

    def test_confirmed_selection_line_found_and_a_page_without_it_fails(self):
        today = shop_today()
        draft = self.r.run((CONFIRM, {}))
        self.assertIs(self.shot(draft, today=today)["checks"]["selectionShown"], True)
        stale = self.shot(draft, today=today + timedelta(days=8))  # expects the "more than a week ago" tail
        self.assertEqual((stale["checks"]["selectionShown"], stale["error"]), (False, "check failed: selectionShown"))
        self.assertIs(self.shot(draft, {INDEX: self.old_index}, today)["checks"]["selectionShown"], False)
