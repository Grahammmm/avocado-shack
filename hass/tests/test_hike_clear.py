"""AV1537-08 tests: ``hike.update clear: [...]`` deletes optional hike text or the trail link; title, date, time,
meetingPoint, RSVPs and capacity are never cleared. Fixture repos only (test_hike_ops helpers).
"""

import unittest
from datetime import datetime, timedelta, timezone

from hass.content_model import load_and_validate
from hass.tests.test_editor import git
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase, _req

FULL = {**HIKE, "bring": "Water and a hat", "accessNote": "Park on the street", "trailId": "idea-fiscalini-bluff"}


def update(**args):
    return ("hike.update", {"id": HIKE_ID, **args})


class HikeClearTests(HikeTestCase):
    def full_repo(self, args=FULL):
        repo = self.repo()
        repo.run(("hike.create", args))
        return repo

    def refused(self, repo, op):
        return self.assertRejected(repo, "refused", op)["reason"]

    def test_clear_bring_deletes_the_key_validates_and_undo_restores_it(self):
        repo = self.full_repo()
        draft = repo.run(update(clear=["bring"]))
        event = repo.event()
        self.assertNotIn("bring", event)
        self.assertEqual(event["accessNote"], "Park on the street")
        load_and_validate(repo.wt / "hass" / "content", repo.wt / "storefront-mockup")
        repo.make_db([])  # history.revert of an event reads the guest count
        repo.run(("history.revert", {"changeId": draft["change_id"]}))
        self.assertEqual(repo.event()["bring"], "Water and a hat")

    def test_clear_trail_link_and_several_fields_with_duplicates(self):
        repo = self.full_repo()
        repo.run(update(clear=["trailId", "accessNote", "trailId"]))
        event = repo.event()
        self.assertNotIn("trailId", event)
        self.assertNotIn("accessNote", event)
        self.assertEqual((event["bring"], event["title"], event["meetingPoint"]),
                         ("Water and a hat", "Test hike", "Test trailhead lot"))

    def test_clear_with_a_set_field_is_one_draft(self):
        repo = self.full_repo()
        head = repo.head()
        draft = repo.prepare(_req(update(clear=["trailId"], title="Renamed hike")))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
        event = repo.event()
        self.assertEqual(event["title"], "Renamed hike")
        self.assertNotIn("trailId", event)
        self.assertEqual(git(repo.wt, "rev-list", "--count", f"{head}..HEAD"), "1")

    def test_required_and_never_clearable_fields_cannot_be_removed(self):
        repo = self.full_repo()
        for name in ("title", "date", "time", "meetingPoint", "capacity", "rsvpEnabled", "noCapacityLimit",
                     "startsAt", "status", "id", "recap"):
            with self.subTest(name=name):
                self.assertEqual(self.refused(repo, update(clear=[name])), f"clear: {name} cannot be removed")
        self.assertEqual(self.refused(repo, update(clear=["bring", "meetingPoint"])),
                         "clear: meetingPoint cannot be removed")  # one bad entry refuses the whole op
        self.assertEqual(repo.event()["bring"], "Water and a hat")

    def test_unknown_names_are_not_hike_fields(self):
        repo = self.full_repo()
        for name in ("parking", "Bring", "trail"):
            with self.subTest(name=name):
                self.assertEqual(self.refused(repo, update(clear=[name])), f"clear: {name} is not a hike field")
        self.assertEqual(self.refused(repo, update(clear=["title", "parking"])), "clear: parking is not a hike field")

    def test_set_and_cleared_together_is_refused(self):
        repo = self.full_repo()
        self.assertEqual(self.refused(repo, update(clear=["bring"], bring="x")), "bring cannot be set and cleared together")
        self.assertEqual(self.refused(repo, update(clear=["trailId"], trailId="idea-fiscalini-bluff")),
                         "trailId cannot be set and cleared together")
        self.assertEqual(repo.event()["bring"], "Water and a hat")

    def test_clearing_an_absent_field_changes_nothing_and_empty_clear_is_invalid(self):
        repo = self.full_repo(HIKE)
        self.assertEqual(self.refused(repo, update(clear=["bring"])), "the operations change nothing")
        self.assertRejected(repo, "invalid", update(clear=[]))
        self.assertRejected(repo, "invalid", update(clear="bring"))
        self.assertEqual(self.assertRejected(repo, "needs-details", update())["result"], "needs-details")

    def test_cancelled_or_completed_hike_refuses_clear(self):
        repo = self.full_repo()
        repo.run(("hike.cancel", {"id": HIKE_ID}))
        self.assertEqual(self.refused(repo, update(clear=["bring"])), f"{HIKE_ID} is cancelled, not scheduled")
        repo = self.full_repo()
        repo.now = datetime(2026, 12, 5, 12, 0, tzinfo=timezone(timedelta(hours=-8)))
        repo.run(("hike.complete", {"id": HIKE_ID}))
        self.assertEqual(self.refused(repo, update(clear=["bring"])), f"{HIKE_ID} is completed, not scheduled")
        self.assertEqual(repo.event()["bring"], "Water and a hat")


if __name__ == "__main__":
    unittest.main()
