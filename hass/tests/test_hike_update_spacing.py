"""RF0740-5 tests: hike.update drops a text field equal to the stored value up to inner spacing; an update left with
nothing to change is refused 'hike <id> already says that'. Case changes stay real changes.

Runs through prepare + apply of the H02 editor on the throwaway repo of test_hike_ops.HikeRepo (temp content,
synthetic titles, injected clock); the same-day-twin case calls the op directly on an in-memory stub.
Run: python3 -B -m unittest hass.tests.test_hike_update_spacing -v
"""

from types import SimpleNamespace

from hass.ops import Refused, hikes
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, HikeTestCase

SAYS = f"hike {HIKE_ID} already says that"
FULL = {**HIKE, "bring": "Water and a hat"}


def update(**args):
    return ("hike.update", {"id": HIKE_ID, **args})


class HikeUpdateSpacingTests(HikeTestCase):
    def created(self, args=FULL):
        repo = self.repo()
        repo.run(("hike.create", args))
        return repo

    def refused(self, repo, op):
        return self.assertRejected(repo, "refused", op)["reason"]

    def test_doubled_inner_space_in_meeting_point_is_already_said(self):
        repo = self.created()
        before = repo.event()
        self.assertEqual(self.refused(repo, update(meetingPoint="Test  trailhead   lot")), SAYS)
        self.assertEqual(self.refused(repo, update(bring="Water  and a hat")), SAYS)
        self.assertEqual(self.refused(repo, update(meetingPoint="Test trailhead  lot", title="Test  hike")), SAYS)
        self.assertEqual(repo.event(), before)

    def test_exactly_equal_title_gets_the_same_refusal_not_the_generic_one(self):
        repo = self.created()
        self.assertEqual(self.refused(repo, update(title=HIKE["title"])), SAYS)

    def test_spacing_only_text_with_a_capacity_change_drafts_only_the_capacity(self):
        repo = self.created()
        repo.make_db([])  # a capacity change reads the guest count
        repo.run(update(meetingPoint="Test  trailhead lot", capacity=20))
        event = repo.event()
        self.assertEqual((event["capacity"], event["meetingPoint"]), (20, "Test trailhead lot"))

    def test_case_only_title_difference_is_a_real_change(self):
        repo = self.created()
        repo.run(update(title="Test Hike"))
        self.assertEqual(repo.event()["title"], "Test Hike")
        repo.run(update(meetingPoint="TEST  trailhead lot"))  # case differs too: stored as the owner gave it
        self.assertEqual(repo.event()["meetingPoint"], "TEST  trailhead lot")

    def test_spacing_only_text_with_a_clear_still_applies_the_clear(self):
        repo = self.created()
        repo.run(update(meetingPoint="Test  trailhead lot", clear=["bring"]))
        event = repo.event()
        self.assertNotIn("bring", event)
        self.assertEqual(event["meetingPoint"], "Test trailhead lot")

    def test_text_field_absent_on_the_event_is_a_real_change(self):
        repo = self.created(HIKE)
        self.assertNotIn("bring", repo.event())
        repo.run(update(bring="Water and a hat"))
        self.assertEqual(repo.event()["bring"], "Water and a hat")

    def test_no_fields_still_needs_details_first(self):
        repo = self.created()
        self.assertRejected(repo, "needs-details", update())

    def test_spacing_only_title_beside_a_same_day_twin_is_already_said_not_a_twin(self):
        target = {"id": HIKE_ID, "status": "scheduled", "title": "Test hike", "startsAt": "2026-12-05T09:00:00-08:00",
                  "meetingPoint": "Test trailhead lot", "rsvpEnabled": False}
        twin = {**target, "id": "hike-2026-12-05-test-hike-2"}
        content = SimpleNamespace(community={"events": [twin, target], "routeIdeas": []})
        ctx = SimpleNamespace(now=NOW, warnings=[], settings={})
        result = hikes._hike_update(content, {"id": HIKE_ID, "title": "Test   hike"}, ctx)
        self.assertIsInstance(result, Refused)
        self.assertEqual(result.reason, SAYS)
        self.assertEqual(target["title"], "Test hike")
