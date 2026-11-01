"""H04 tests: ``route.edit`` corrects a route idea's text through prepare/apply; id, status, RSVPs and source stay locked.

Every op runs through ``prepare`` + ``apply`` of the H02 editor on a throwaway Git repo with a linked writer worktree
and a private temp state dir (test_hike_ops.HikeRepo, production registry, injected clock). Fixture content only.
Run: python3 -m unittest hass.tests.test_route_edit -v
"""

import json

from hass import migration_check
from hass.content_model import load_and_validate
from hass.ops.routes import ROUTE_EDITABLE
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

CASS, BUCHON = "idea-cass-hill", "idea-point-buchon"
EDIT = "route.edit"


class RouteEditTests(HikeTestCase):
    def ideas(self, repo, site=False):
        path = repo.wt / ("storefront-mockup/community.json" if site else "hass/content/community.json")
        return {i["id"]: i for i in json.loads(path.read_text("utf-8"))["routeIdeas"]}

    def test_edit_one_field_reaches_content_and_site(self):
        repo = self.repo()
        before, site_before = self.ideas(repo), self.ideas(repo, site=True)
        draft = repo.prepare({"ops": [{"op": EDIT, "args": {"id": CASS, "difficulty": "Moderate to hard"}}]})
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.apply(draft["draft"])["result"], "applied")
        after, site_after = self.ideas(repo), self.ideas(repo, site=True)
        self.assertEqual(after[CASS], {**before[CASS], "difficulty": "Moderate to hard"})
        self.assertEqual(site_after[CASS]["difficulty"], "Moderate to hard")
        for key in before:
            if key != CASS:
                self.assertEqual(json.dumps(after[key]), json.dumps(before[key]), key)
                self.assertEqual(json.dumps(site_after[key]), json.dumps(site_before[key]), key)

    def test_two_fields_make_one_record(self):
        repo = self.repo()
        draft = repo.run((EDIT, {"id": CASS, "distance": "3.2 miles", "duration": "About 2.5 hours"}))
        change = json.loads((repo.state / "changes" / f"{draft['change_id']}.json").read_text("utf-8"))
        self.assertEqual([(r["collection"], r["key"]) for r in change["records"]], [("routeIdeas", CASS)])
        idea = self.ideas(repo)[CASS]
        self.assertEqual((idea["distance"], idea["duration"]), ("3.2 miles", "About 2.5 hours"))

    def test_unknown_id_and_real_event_are_refused(self):
        repo = self.repo()
        result = self.assertRejected(repo, "refused", (EDIT, {"id": "idea-nowhere", "title": "Nowhere"}))
        self.assertEqual(result["reason"], "unknown route idea idea-nowhere")
        repo.run(("hike.create", HIKE))
        event = repo.event()
        result = self.assertRejected(repo, "refused", (EDIT, {"id": HIKE_ID, "title": "Renamed"}))
        self.assertEqual(result["reason"], f"{HIKE_ID} is a hike, not a route idea; use hike.update")
        self.assertEqual(repo.event(), event)

    def test_locked_fields_are_unknown_arguments(self):
        repo = self.repo()
        before = self.ideas(repo)[CASS]
        for name, value in (("status", "scheduled"), ("rsvpEnabled", True), ("sourceUrl", "https://example.invalid/"),
                            ("sourceName", "Other guide"), ("newId", "idea-other"), ("date", "2026-12-05")):
            # ``id`` only selects the idea (there is no rename argument); any other id name is unknown.
            with self.subTest(name=name):
                result = self.assertRejected(repo, "invalid", (EDIT, {"id": CASS, "title": "Cass", name: value}))
                self.assertIn(f"{EDIT}: unknown argument {name!r}", "\n".join(result["problems"]))
        self.assertEqual(self.ideas(repo)[CASS], before)
        idea = next(i for i in load_and_validate(repo.wt / "hass/content", repo.wt / "storefront-mockup")
                    .community["routeIdeas"] if i["id"] == CASS)
        self.assertEqual((idea["status"], idea["rsvpEnabled"]), ("idea", False))

    def test_no_field_needs_details_and_same_text_is_refused(self):
        repo = self.repo()
        result = self.assertRejected(repo, "needs-details", (EDIT, {"id": CASS}))
        self.assertEqual(result["missing"], list(ROUTE_EDITABLE))
        self.assertEqual(result["question"], "What should change on this route idea?")
        current = self.ideas(repo)[CASS]
        same = {"id": CASS, "difficulty": current["difficulty"], "distance": current["distance"]}
        result = self.assertRejected(repo, "refused", (EDIT, same))
        self.assertEqual(result["reason"], f"route idea {CASS} already says that")
        changed = repo.run((EDIT, {**same, "distance": "3.1 miles"}))  # unchanged fields are dropped, not refused
        change = json.loads((repo.state / "changes" / f"{changed['change_id']}.json").read_text("utf-8"))
        self.assertEqual(change["records"][0]["after"]["difficulty"], current["difficulty"])

    def test_markup_dollar_and_whitespace_are_refused(self):
        repo = self.repo()
        before = self.ideas(repo)[CASS]
        for value in ("<b>Hard</b>", "Costs $5", " Hard", "Hard\n"):
            with self.subTest(value=value):
                self.assertRejected(repo, "invalid", (EDIT, {"id": CASS, "difficulty": value}))
        self.assertEqual(self.ideas(repo)[CASS], before)

    def test_revert_restores_text_and_keeps_later_edit(self):
        repo = self.repo()
        old = self.ideas(repo)[CASS]["description"]
        first = repo.run((EDIT, {"id": CASS, "description": "A short climb with a wide coast view."}))
        repo.run((EDIT, {"id": BUCHON, "title": "Point Buchon Trail"}))
        repo.run(("history.revert", {"changeId": first["change_id"]}))
        ideas = self.ideas(repo)
        self.assertEqual((ideas[CASS]["description"], ideas[BUCHON]["title"]), (old, "Point Buchon Trail"))
        self.assertEqual(self.ideas(repo, site=True)[CASS]["description"], old)

    def test_migration_check_passes_after_edit(self):
        repo = self.repo()
        sources = {k: (v["sourceUrl"], v["sourceName"]) for k, v in self.ideas(repo).items()}
        repo.run((EDIT, {"id": CASS, "terrain": "Exposed hillside; a few steep pitches"}))
        failures, _ = migration_check.run_checks(repo.wt)
        self.assertEqual(failures, [])
        self.assertEqual({k: (v["sourceUrl"], v["sourceName"]) for k, v in self.ideas(repo).items()}, sources)
