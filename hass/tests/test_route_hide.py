"""AV1322-03 (H04) tests: ``route.hide`` / ``route.restore`` take a route idea off the generated route list and back.

Every op runs through ``prepare`` + ``apply`` of the H02 editor on a throwaway Git repo with a linked writer worktree
and a private temp state dir (test_hike_ops.HikeRepo, production registry, injected clock). Synthetic data only.
Run: python3 -m unittest hass.tests.test_route_hide -v
"""

import copy
import json
from datetime import datetime, timedelta, timezone

from hass import migration_check
from hass.content_model import load_and_validate, validate_community
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

IDEA = "idea-cass-hill"
HIDE, RESTORE = ("route.hide", {"id": IDEA}), ("route.restore", {"id": IDEA})
SITE, SOURCE = "storefront-mockup/community.json", "hass/content/community.json"


class RouteHideTests(HikeTestCase):
    def read(self, repo, rel):
        return (repo.wt / rel).read_bytes()

    def ideas(self, repo, rel):
        return {i["id"]: i for i in json.loads(self.read(repo, rel))["routeIdeas"]}

    def test_hide_leaves_generated_list_keeps_source_and_migration_count(self):
        repo = self.repo()
        source_before = self.ideas(repo, SOURCE)
        draft = repo.run(HIDE)
        change = json.loads((repo.state / "changes" / f"{draft['change_id']}.json").read_text("utf-8"))
        self.assertEqual([(r["collection"], r["key"]) for r in change["records"]], [("routeIdeas", IDEA)])
        self.assertNotIn(IDEA, self.ideas(repo, SITE))
        self.assertEqual(set(self.ideas(repo, SITE)), set(source_before) - {IDEA})
        self.assertEqual(self.ideas(repo, SOURCE)[IDEA], {**source_before[IDEA], "status": "hidden"})
        load_and_validate(repo.wt / "hass/content", repo.wt / "storefront-mockup")
        failures, report = migration_check.run_checks(repo.wt)
        self.assertEqual(failures, [])
        self.assertEqual(report["routeIdeas"], len(source_before))
        self.assertEqual(report["sourceLinksPreserved"], report["baselineSourceLinks"])

    def test_scheduled_hike_link_blocks_hide_completed_or_cancelled_does_not(self):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "trailId": IDEA}))
        result = self.assertRejected(repo, "refused", HIDE)
        self.assertEqual(result["reason"], f"{HIKE_ID} (Test hike) uses this route; change that hike first")
        repo.now = datetime(2026, 12, 5, 12, 0, tzinfo=timezone(timedelta(hours=-8)))
        repo.run(("hike.complete", {"id": HIKE_ID}))
        repo.run(HIDE)
        self.assertEqual(self.ideas(repo, SOURCE)[IDEA]["status"], "hidden")
        self.assertEqual(repo.event()["trailId"], IDEA)  # the completed hike keeps its link

    def test_cancelled_link_does_not_block_and_cleared_link_unblocks(self):
        repo = self.repo()
        repo.run(("hike.create", {**HIKE, "trailId": IDEA}), ("hike.create", {**HIKE, "title": "Two", "trailId": IDEA}))
        repo.run(("hike.cancel", {"id": HIKE_ID}))
        result = self.assertRejected(repo, "refused", HIDE)
        self.assertEqual(result["reason"], "hike-2026-12-05-two (Two) uses this route; change that hike first")
        repo.run(("hike.update", {"id": "hike-2026-12-05-two", "clear": ["trailId"]}))
        repo.run(HIDE)

    def test_hide_twice_restore_visible_and_restore_is_byte_identical(self):
        repo = self.repo()
        result = self.assertRejected(repo, "refused", RESTORE)
        self.assertEqual(result["reason"], f"route idea {IDEA} is not hidden")
        site, source = self.read(repo, SITE), self.read(repo, SOURCE)
        repo.run(HIDE)
        result = self.assertRejected(repo, "refused", HIDE)
        self.assertEqual(result["reason"], f"route idea {IDEA} is already hidden")
        repo.run(RESTORE)
        self.assertEqual((self.read(repo, SITE), self.read(repo, SOURCE)), (site, source))
        result = self.assertRejected(repo, "refused", RESTORE)
        self.assertEqual(result["reason"], f"route idea {IDEA} is not hidden")

    def test_unknown_id_and_hike_id_are_refused(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        for op in ("route.hide", "route.restore"):
            with self.subTest(op=op):
                result = self.assertRejected(repo, "refused", (op, {"id": "idea-nowhere"}))
                self.assertEqual(result["reason"], "unknown route idea idea-nowhere")
                result = self.assertRejected(repo, "refused", (op, {"id": HIKE_ID}))
                self.assertEqual(result["reason"], f"{HIKE_ID} is a hike, not a route idea")
                result = self.assertRejected(repo, "invalid", (op, {"id": IDEA, "status": "idea"}))
                self.assertIn(f"{op}: unknown argument 'status'", "\n".join(result["problems"]))

    def test_hike_create_and_update_refuse_a_hidden_trail(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE), HIDE)
        reason = f"route idea {IDEA} is hidden; restore it first"
        result = self.assertRejected(repo, "refused", ("hike.create", {**HIKE, "title": "Other", "trailId": IDEA}))
        self.assertEqual(result["reason"], reason)
        result = self.assertRejected(repo, "refused", ("hike.update", {"id": HIKE_ID, "trailId": IDEA}))
        self.assertEqual(result["reason"], reason)
        repo.run(RESTORE, ("hike.update", {"id": HIKE_ID, "trailId": IDEA}))
        self.assertEqual(repo.event()["trailId"], IDEA)

    def test_route_edit_works_on_hidden_and_status_stays_locked(self):
        repo = self.repo()
        repo.run(HIDE, ("route.edit", {"id": IDEA, "distance": "3.2 miles"}))
        idea = self.ideas(repo, SOURCE)[IDEA]
        self.assertEqual((idea["status"], idea["distance"]), ("hidden", "3.2 miles"))
        self.assertNotIn(IDEA, self.ideas(repo, SITE))
        result = self.assertRejected(repo, "invalid", ("route.edit", {"id": IDEA, "status": "idea"}))
        self.assertIn("route.edit: unknown argument 'status'", "\n".join(result["problems"]))

    def test_undo_hide_brings_it_back_and_undo_restore_hides_it(self):
        repo = self.repo()
        site = self.ideas(repo, SITE)
        hidden = repo.run(HIDE)
        repo.run(("history.revert", {"changeId": hidden["change_id"]}))
        self.assertEqual(self.ideas(repo, SOURCE)[IDEA]["status"], "idea")
        self.assertEqual(self.ideas(repo, SITE), site)  # same records (undo may store keys in another order)
        repo.run(HIDE)
        restored = repo.run(RESTORE)
        repo.run(("hike.create", {**HIKE, "trailId": IDEA}))
        result = self.assertRejected(repo, "invalid", ("history.revert", {"changeId": restored["change_id"]}))
        self.assertIn(f"trailId {IDEA} is hidden", "\n".join(result["problems"]))

    def test_validator_statuses_and_scheduled_link_to_hidden(self):
        repo = self.repo()
        community = {k: v for k, v in repo.community().items() if k != "schemaVersion"}  # the loader strips it
        bad = ["routeIdeas[0]: status must be 'idea' or 'hidden'"]
        for status, expected in (("idea", []), ("hidden", []), ("gone", bad), (None, bad)):
            with self.subTest(status=status):
                data = copy.deepcopy(community)
                data["routeIdeas"][0]["status"] = status
                problems = []
                validate_community(problems, data)
                self.assertEqual(problems, expected)
        data = copy.deepcopy(community)
        data["routeIdeas"][0]["status"] = "hidden"
        rid = data["routeIdeas"][0]["id"]
        event = {"id": HIKE_ID, "title": "Test hike", "startsAt": "2026-12-05T09:00:00-08:00",
                 "timezone": "America/Los_Angeles", "status": "scheduled", "trailId": rid}
        for status, expected in (("scheduled", [f"events[0]: trailId {rid} is hidden"]), ("completed", []),
                                 ("cancelled", [])):
            with self.subTest(event_status=status):
                problems = []
                validate_community(problems, {**data, "events": [{**event, "status": status}]})
                self.assertEqual(problems, expected)
