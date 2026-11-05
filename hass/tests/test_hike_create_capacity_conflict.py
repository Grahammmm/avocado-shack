"""RF0200-10 tests: hike.create asks (needs-details, no draft, no write) when a capacity and noCapacityLimit true
conflict, also with RSVPs off. Unambiguous off-RSVP choices and every on-RSVP / update answer are unchanged.

Runs through prepare + apply of the H02 editor on the throwaway repo of test_hike_ops.HikeRepo (synthetic hike,
injected clock, no network); the direct-handler case calls the op on an in-memory stub.
Run: python3 -m unittest hass.tests.test_hike_create_capacity_conflict -v
"""

import json
from types import SimpleNamespace

from hass.ops import hikes
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, HikeTestCase, _req

OFF = {**HIKE, "rsvpEnabled": False, "capacity": 12}
OFF_BARE = {k: v for k, v in OFF.items() if k != "capacity"}
CONFLICT = "Give either a capacity or noCapacityLimit true, not both."
OFF_WARNING = f"{HIKE_ID}: RSVPs are off, so capacity 12 has no effect until RSVPs are turned on"
FIELDS = ["capacity", "noCapacityLimit"]


def _snapshot(repo):
    """Everything a hike.create could touch: HEAD, status, both content files, drafts and change records."""
    changes = repo.state / "changes"
    return (repo.head(), repo.status(), repo.drafts(),
            sorted(p.name for p in changes.iterdir()) if changes.is_dir() else [],
            (repo.wt / "hass/content/community.json").read_bytes(),
            (repo.wt / "storefront-mockup/community.json").read_bytes())


class OffCapacityConflictTests(HikeTestCase):
    def test_off_create_conflict_asks_without_draft(self):
        repo = self.repo()
        before = _snapshot(repo)
        result = self.assertRejected(repo, "needs-details", ("hike.create", {**OFF, "noCapacityLimit": True}))
        self.assertEqual((result["missing"], result["question"]), (FIELDS, CONFLICT))
        self.assertNotIn("warnings", result)
        self.assertNotIn("RSVPs are off", str(result))
        self.assertEqual(_snapshot(repo), before)
        content = SimpleNamespace(community={"events": [], "routeIdeas": []})
        ctx = SimpleNamespace(now=NOW, warnings=[], settings={})
        asked = hikes._hike_create(content, {**OFF, "noCapacityLimit": True}, ctx)
        self.assertIsInstance(asked, hikes.NeedsDetails)
        self.assertEqual((asked.missing, asked.question), (FIELDS, CONFLICT))
        self.assertEqual((content.community["events"], ctx.warnings), ([], []))

    def test_conflict_is_asked_before_other_checks_and_with_other_fields_unchanged(self):
        repo = self.repo()
        for extra in ({}, {"title": "Another hike"}):
            with self.subTest(extra=extra):
                result = self.assertRejected(repo, "needs-details",
                                             ("hike.create", {**OFF, "noCapacityLimit": True, **extra}))
                self.assertEqual(result["missing"], FIELDS)
        # a past date is not reported instead of the capacity question: the capacity question comes first
        result = self.assertRejected(repo, "needs-details",
                                     ("hike.create", {**OFF, "noCapacityLimit": True, "date": "2026-10-29"}))
        self.assertEqual(result["question"], CONFLICT)

    def test_on_create_questions_unchanged(self):
        repo = self.repo()
        bare = {k: v for k, v in HIKE.items() if k != "capacity"}
        for args in ({**HIKE, "noCapacityLimit": True}, bare, {**bare, "noCapacityLimit": False}):
            with self.subTest(args=args):
                result = self.assertRejected(repo, "needs-details", ("hike.create", args))
                self.assertEqual((result["missing"], result["question"]), (FIELDS, hikes.CAPACITY_QUESTION))

    def test_off_unambiguous_capacity_matrix(self):
        cases = ((OFF_BARE, None, []),
                 ({**OFF_BARE, "noCapacityLimit": True}, None, []),
                 (OFF, 12, [OFF_WARNING]),
                 ({**OFF, "noCapacityLimit": False}, 12, [OFF_WARNING]))
        for args, capacity, warnings in cases:
            with self.subTest(args=args):
                repo = self.repo()
                draft = repo.prepare(_req(("hike.create", args)))
                self.assertEqual(draft["result"], "ok", draft)
                self.assertEqual(draft["draft"]["warnings"], warnings)
                self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
                event = repo.event()
                self.assertEqual(event.get("capacity"), capacity)
                self.assertNotIn("noCapacityLimit", event)
                self.assertIs(event["rsvpEnabled"], False)

    def test_non_bool_no_capacity_limit_is_not_a_competing_choice_but_still_typed(self):
        repo = self.repo()
        for bad in ("true", 1):
            with self.subTest(bad=bad):
                result = repo.prepare(_req(("hike.create", {**OFF, "noCapacityLimit": bad})))
                self.assertNotEqual(result["result"], "ok", result)
                self.assertNotEqual(result.get("question"), CONFLICT)

    def test_corrected_request_needs_approval(self):
        repo = self.repo()
        before = _snapshot(repo)
        self.assertRejected(repo, "needs-details", ("hike.create", {**OFF, "noCapacityLimit": True}))
        draft = repo.prepare(_req(("hike.create", OFF)))
        self.assertEqual(draft["result"], "ok", draft)
        after = _snapshot(repo)  # a normal draft exists now, but HEAD, status and both content files are unchanged
        self.assertEqual((after[:2], after[4:]), (before[:2], before[4:]))
        self.assertEqual(len(after[2]), 1)
        self.assertEqual(repo.community()["events"], [])  # nothing written before the explicit apply
        self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
        self.assertEqual([e["id"] for e in repo.community()["events"]], [HIKE_ID])

    def test_update_conflict_and_guest_guards_unchanged(self):
        repo = self.repo()
        repo.run(("hike.create", OFF_BARE))
        repo.make_db([])
        before = _snapshot(repo)
        result = self.assertRejected(repo, "needs-details",
                                     ("hike.update", {"id": HIKE_ID, "capacity": 7, "noCapacityLimit": True}))
        self.assertEqual((result["missing"], result["question"]),
                         (FIELDS, "Give either a new capacity or noCapacityLimit true, not both."))
        self.assertNotIn("warnings", result)
        self.assertEqual(_snapshot(repo), before)
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        repo.make_db([(HIKE_ID, 3)])
        low = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "capacity": 2}))
        self.assertEqual(low["reason"], "capacity 2 is below 3 confirmed guests")
        self.assertEqual(json.dumps(repo.event()["capacity"]), "12")
