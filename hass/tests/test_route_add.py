"""AV1322-02 (H04) tests: ``route.add`` drafts a new undated route idea; undo removes it.

Every op runs through ``prepare`` + ``apply`` of the H02 editor on a throwaway Git repo with a linked writer worktree
and a private temp state dir (test_hike_ops.HikeRepo, production registry, injected clock). Synthetic ideas only;
no source link is fetched. Run: python3 -m unittest hass.tests.test_route_add -v
"""

import json
from datetime import datetime, timedelta, timezone

from hass import migration_check
from hass.content_model import load_and_validate
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

ADD = "route.add"
NEW = {"title": "Bluff Walk", "place": "Test Town", "character": "Short and windy", "distance": "2 miles",
       "difficulty": "Easy", "elevation": "100 ft", "elevationLabel": "Elevation gain", "duration": "About 1 hour",
       "routeType": "Loop", "terrain": "Packed dirt", "description": "A short test loop on the bluff.",
       "sourceUrl": "https://trails.example.org/bluff", "sourceName": "Test trail guide"}
NEW_ID = "idea-bluff-walk"


class RouteAddTests(HikeTestCase):
    def ideas(self, repo, site=False):
        path = repo.wt / ("storefront-mockup/community.json" if site else "hass/content/community.json")
        return {i["id"]: i for i in json.loads(path.read_text("utf-8"))["routeIdeas"]}

    def test_full_args_add_one_idea_that_validates_and_renders(self):
        repo = self.repo()
        before = self.ideas(repo)
        draft = repo.run((ADD, NEW))
        change = json.loads((repo.state / "changes" / f"{draft['change_id']}.json").read_text("utf-8"))
        self.assertEqual([(r["collection"], r["key"], r["before"]) for r in change["records"]],
                         [("routeIdeas", NEW_ID, None)])
        ideas = self.ideas(repo)
        self.assertEqual(ideas[NEW_ID], {"id": NEW_ID, **NEW, "status": "idea", "rsvpEnabled": False})
        self.assertEqual({k: v for k, v in ideas.items() if k != NEW_ID}, before)
        content = load_and_validate(repo.wt / "hass/content", repo.wt / "storefront-mockup")
        self.assertIn(NEW_ID, [i["id"] for i in content.community["routeIdeas"]])
        self.assertEqual(self.ideas(repo, site=True)[NEW_ID], ideas[NEW_ID])

    def test_missing_source_needs_both_and_drafts_nothing(self):
        repo = self.repo()
        for gone in (("sourceUrl",), ("sourceName",), ("sourceUrl", "sourceName")):
            with self.subTest(gone=gone):
                args = {k: v for k, v in NEW.items() if k not in gone}
                result = self.assertRejected(repo, "needs-details", (ADD, args))
                self.assertEqual(result["missing"], ["sourceUrl", "sourceName"])
                self.assertEqual(result["question"], "Where does this route come from (link and name)?")
        result = self.assertRejected(repo, "needs-details", (ADD, {k: v for k, v in NEW.items() if k != "terrain"}))
        self.assertEqual(result["missing"], ["terrain"])
        self.assertNotIn(NEW_ID, self.ideas(repo))

    def test_non_public_source_url_is_refused_without_echo(self):
        repo = self.repo()
        for url in ("http://trails.example.org/bluff", "https://localhost/bluff", "https://10.0.0.1/x",
                    "javascript:alert(1)", "https://user@trails.example.org/x", "https://trails.example.org:8443/x"):
            with self.subTest(url=url):
                result = self.assertRejected(repo, "refused", (ADD, {**NEW, "sourceUrl": url}))
                self.assertEqual(result["reason"], "sourceUrl must be a public https:// link")
                self.assertNotIn(url, json.dumps(result))
        self.assertNotIn(NEW_ID, self.ideas(repo))

    def test_title_taken_by_idea_or_hike_is_refused_as_route_edit(self):
        repo = self.repo()
        for title in ("Cass Hill", "cass   HILL", "ＣＡＳＳ Hill"):
            with self.subTest(title=title):
                result = self.assertRejected(repo, "refused", (ADD, {**NEW, "title": title}))
                self.assertEqual(result["reason"], "idea-cass-hill is already called Cass Hill")
        repo.run(("hike.create", HIKE))
        result = self.assertRejected(repo, "refused", (ADD, {**NEW, "title": "test HIKE"}))
        self.assertEqual(result["reason"], f"{HIKE_ID} is already called Test hike")
        repo.run((ADD, NEW))  # an idea added here blocks the same title next time
        result = self.assertRejected(repo, "refused", (ADD, {**NEW, "title": "bluff walk"}))
        self.assertEqual(result["reason"], f"{NEW_ID} is already called Bluff Walk")

    def test_same_slug_gets_suffix_and_empty_slug_is_refused(self):
        repo = self.repo()
        repo.run((ADD, NEW))
        repo.run((ADD, {**NEW, "title": "Bluff Walk!"}))
        repo.run((ADD, {**NEW, "title": "Blúff-walk"}))
        ideas = self.ideas(repo)
        self.assertEqual((ideas[NEW_ID]["title"], ideas[f"{NEW_ID}-2"]["title"], ideas[f"{NEW_ID}-3"]["title"]),
                         ("Bluff Walk", "Bluff Walk!", "Blúff-walk"))
        result = self.assertRejected(repo, "refused", (ADD, {**NEW, "title": "!!!"}))
        self.assertEqual(result["reason"], "title needs a letter or digit")

    def test_locked_fields_are_unknown_arguments(self):
        repo = self.repo()
        for name, value in (("status", "scheduled"), ("rsvpEnabled", True), ("id", "idea-mine"),
                            ("startsAt", "2026-12-05T09:00:00-08:00")):
            with self.subTest(name=name):
                result = self.assertRejected(repo, "invalid", (ADD, {**NEW, name: value}))
                self.assertIn(f"{ADD}: unknown argument {name!r}", "\n".join(result["problems"]))
        self.assertNotIn(NEW_ID, self.ideas(repo))
        self.assertNotIn("idea-mine", self.ideas(repo))

    def test_undo_removes_the_idea_and_keeps_baseline_and_later_edits(self):
        repo = self.repo()
        before, site_before = self.ideas(repo), self.ideas(repo, site=True)
        added = repo.run((ADD, NEW))
        repo.run(("route.edit", {"id": "idea-cass-hill", "distance": "3.2 miles"}))
        repo.run(("history.revert", {"changeId": added["change_id"]}))
        ideas, site = self.ideas(repo), self.ideas(repo, site=True)
        self.assertNotIn(NEW_ID, ideas)
        self.assertNotIn(NEW_ID, site)
        self.assertEqual(ideas, {**before, "idea-cass-hill": {**before["idea-cass-hill"], "distance": "3.2 miles"}})
        self.assertEqual(set(site), set(site_before))
        failures, _ = migration_check.run_checks(repo.wt)
        self.assertEqual(failures, [])

    def test_undo_after_the_idea_was_edited_is_a_conflict(self):
        repo = self.repo()
        added = repo.run((ADD, NEW))
        repo.run(("route.edit", {"id": NEW_ID, "distance": "2.5 miles"}))
        result = self.assertRejected(repo, "refused", ("history.revert", {"changeId": added["change_id"]}))
        self.assertEqual(result["reason"], f"conflict: routeIdeas {NEW_ID} changed after {added['change_id']}")
        self.assertEqual(self.ideas(repo)[NEW_ID]["distance"], "2.5 miles")

    def test_undo_is_refused_while_any_hike_links_the_new_idea(self):
        reason = f"{HIKE_ID} (Test hike) uses this route; change that hike first"
        for status in ("scheduled", "completed", "cancelled"):
            with self.subTest(status=status):
                repo = self.repo()
                added = repo.run((ADD, NEW))
                repo.run(("hike.create", {**HIKE, "trailId": NEW_ID}))
                if status != "scheduled":
                    repo.now = datetime(2026, 12, 5, 12, 0, tzinfo=timezone(timedelta(hours=-8)))
                    repo.run(({"completed": "hike.complete", "cancelled": "hike.cancel"}[status], {"id": HIKE_ID}))
                undo = ("history.revert", {"changeId": added["change_id"]})
                self.assertEqual(self.assertRejected(repo, "refused", undo)["reason"], reason)
                self.assertEqual((NEW_ID in self.ideas(repo), repo.event()["trailId"]), (True, NEW_ID))

    def test_undo_works_once_the_hike_link_is_cleared(self):
        repo = self.repo()
        added = repo.run((ADD, NEW))
        repo.run(("hike.create", {**HIKE, "trailId": NEW_ID}))
        undo = ("history.revert", {"changeId": added["change_id"]})
        self.assertRejected(repo, "refused", undo)
        repo.run(("hike.update", {"id": HIKE_ID, "clear": ["trailId"]}))
        repo.run(undo)
        self.assertNotIn(NEW_ID, self.ideas(repo))
        self.assertNotIn("trailId", repo.event())
