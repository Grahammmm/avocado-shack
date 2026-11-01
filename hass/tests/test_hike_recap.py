"""AV1537-09 tests: ``hike.recap {id, recap}`` sets or corrects the trail-journal recap of a completed hike; every
other field of a completed hike stays locked. Fixture repos only (test_hike_ops helpers).
"""

import unittest
from datetime import datetime, timedelta, timezone

from hass.content_model import load_and_validate
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

AFTER_START = datetime(2026, 12, 5, 12, 0, tzinfo=timezone(timedelta(hours=-8)))
OLD, NEW = "Twelve of us walked the loop.", "Fourteen of us walked the loop."


def recap(text=NEW, **extra):
    return ("hike.recap", {"id": HIKE_ID, "recap": text, **extra})


class HikeRecapTests(HikeTestCase):
    def completed_repo(self, **complete_args):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "bring": "Water"}))
        repo.now = AFTER_START
        repo.run(("hike.complete", {"id": HIKE_ID, **complete_args}))
        return repo

    def reason(self, repo, op, result="refused"):
        return self.assertRejected(repo, result, op)["reason"]

    def test_corrects_recap_only_that_field_changes_and_undo_restores_it(self):
        repo = self.completed_repo(recap=OLD)
        before = repo.event()
        draft = repo.run(recap())
        after = repo.event()
        self.assertEqual(after["recap"], NEW)
        self.assertEqual({k: v for k, v in after.items() if k != "recap"}, {k: v for k, v in before.items() if k != "recap"})
        [record] = draft["records"]
        self.assertEqual((record["collection"], record["key"]), ("events", HIKE_ID))
        changed = {k for k in record["before"].keys() | record["after"].keys()
                   if record["before"].get(k) != record["after"].get(k)}
        self.assertEqual(changed, {"recap"})
        load_and_validate(repo.wt / "hass" / "content", repo.wt / "storefront-mockup")
        repo.make_db([])  # history.revert of an event with a capacity reads the guest count
        repo.run(("history.revert", {"changeId": draft["change_id"]}))
        self.assertEqual(repo.event(), before)

    def test_adds_a_recap_when_the_completed_hike_has_none(self):
        repo = self.completed_repo()
        self.assertNotIn("recap", repo.event())
        repo.run(recap())
        event = repo.event()
        self.assertEqual((event["status"], event["recap"], event["bring"]), ("completed", NEW, "Water"))

    def test_scheduled_cancelled_and_unknown_hikes_are_refused(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        self.assertEqual(self.reason(repo, recap()), f"{HIKE_ID} is scheduled; use hike.complete with a recap")
        repo.now = AFTER_START  # started but not completed: still scheduled
        self.assertEqual(self.reason(repo, recap()), f"{HIKE_ID} is scheduled; use hike.complete with a recap")
        self.assertNotIn("recap", repo.event())
        repo.run(("hike.cancel", {"id": HIKE_ID}))
        self.assertEqual(self.reason(repo, recap()), f"{HIKE_ID} is cancelled")
        self.assertNotIn("recap", repo.event())
        self.assertRejected(repo, "not-found", ("hike.recap", {"id": "hike-2026-12-05-nothing", "recap": NEW}))

    def test_same_recap_again_changes_nothing(self):
        repo = self.completed_repo(recap=OLD)
        self.assertEqual(self.reason(repo, recap(OLD)), "the operations change nothing")
        repo.run(recap())
        self.assertEqual(self.reason(repo, recap()), "the operations change nothing")

    def test_missing_or_bad_recap_text_is_rejected(self):
        repo = self.completed_repo(recap=OLD)
        missing = self.assertRejected(repo, "needs-details", ("hike.recap", {"id": HIKE_ID}))
        self.assertEqual(missing["missing"], ["recap"])
        for text in ("<b>Great</b> walk", "Cost $5 each", "{{ name }} came", "", "  padded  ", "Line\u200bbreak", 12):
            with self.subTest(text=text):
                self.assertRejected(repo, "invalid", recap(text))
        self.assertEqual(repo.event()["recap"], OLD)

    def test_no_other_field_can_change_through_recap(self):
        repo = self.completed_repo(recap=OLD)
        for extra in ({"title": "Renamed"}, {"status": "scheduled"}, {"bring": "Snacks"}, {"clear": ["bring"]}):
            with self.subTest(extra=extra):
                self.assertRejected(repo, "invalid", recap(**extra))
        event = repo.event()
        self.assertEqual((event["title"], event["status"], event["bring"], event["recap"]),
                         ("Test hike", "completed", "Water", OLD))

    def test_other_ops_on_a_completed_hike_stay_refused(self):
        repo = self.completed_repo(recap=OLD)
        for op, args in (("hike.update", {"title": "New name"}), ("hike.update", {"clear": ["bring"]}),
                         ("hike.cancel", {}), ("hike.complete", {"recap": NEW})):
            with self.subTest(op=op, args=args):
                self.assertEqual(self.reason(repo, (op, {"id": HIKE_ID, **args})), f"{HIKE_ID} is completed, not scheduled")
        self.assertEqual(repo.event()["recap"], OLD)


if __name__ == "__main__":
    unittest.main()
