"""RF0740-6 tests: ``hike.recap`` with a recap equal to the stored one, or differing only by inner spacing, is refused
``hike <id> already says that``; case changes and real edits are still drafted and applied.
"""

import unittest

from hass.tests import test_hike_recap as base
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

OLD, NEW, recap = base.OLD, base.NEW, base.recap
SAYS = f"hike {HIKE_ID} already says that"


class HikeRecapSpacingTests(HikeTestCase):
    completed_repo, reason = base.HikeRecapTests.completed_repo, base.HikeRecapTests.reason

    def test_equal_recap_is_already_said_and_content_unchanged(self):
        repo = self.completed_repo(recap=OLD)
        before = repo.event()
        self.assertEqual(self.reason(repo, recap(OLD)), SAYS)
        self.assertEqual(repo.event(), before)

    def test_doubled_inner_spaces_are_already_said(self):
        repo = self.completed_repo(recap=OLD)
        before = repo.event()
        self.assertEqual(self.reason(repo, recap("Twelve of  us walked   the loop.")), SAYS)
        self.assertEqual(repo.event(), before)

    def test_tab_for_space_swap_is_refused_by_the_text_checks(self):
        repo = self.completed_repo(recap=OLD)
        before = repo.event()
        bad = self.assertRejected(repo, "invalid", recap("Twelve of\tus walked the loop."))
        self.assertEqual(bad["problems"], ["control characters are not allowed"])
        self.assertEqual(repo.event(), before)

    def test_case_only_difference_is_a_real_change_and_undo_restores(self):
        repo = self.completed_repo(recap=OLD)
        before = repo.event()
        draft = repo.run(recap(OLD.upper()))
        self.assertEqual(repo.event()["recap"], OLD.upper())
        repo.make_db([])  # history.revert of an event with a capacity reads the guest count
        repo.run(("history.revert", {"changeId": draft["change_id"]}))
        self.assertEqual(repo.event(), before)

    def test_real_edit_stores_the_owners_exact_text(self):
        repo = self.completed_repo(recap=OLD)
        repo.run(recap(NEW))
        self.assertEqual(repo.event()["recap"], NEW)

    def test_completed_hike_without_recap_adds_any_recap(self):
        repo = self.completed_repo()
        repo.run(recap(OLD))
        self.assertEqual(repo.event()["recap"], OLD)

    def test_status_refusals_come_before_already_says_that(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.now = base.AFTER_START
        self.assertEqual(self.reason(repo, recap(OLD)), f"{HIKE_ID} is scheduled; use hike.complete with a recap")
        repo.run(("hike.cancel", {"id": HIKE_ID}))
        self.assertEqual(self.reason(repo, recap(OLD)), f"{HIKE_ID} is cancelled")
        self.assertRejected(repo, "not-found", ("hike.recap", {"id": "hike-2026-12-05-nothing", "recap": OLD}))


if __name__ == "__main__":
    unittest.main()
