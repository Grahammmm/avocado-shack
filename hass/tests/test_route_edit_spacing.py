"""H04 tests: ``route.edit`` treats a value differing from the current one only by spacing as unchanged.

Spacing-only fields are dropped; an edit left with nothing is refused "already says that". Case changes stay real.
Uses the H04 harness (test_hike_ops.HikeTestCase) and the ``ideas`` reader of test_route_edit.RouteEditTests.
Fixture content only. Run: python3 -m unittest hass.tests.test_route_edit_spacing -v
"""

import json

from hass.content_model import load_and_validate
from hass.ops.routes import _route_edit
from hass.tests import test_route_edit as base
from hass.tests.test_hike_ops import HikeTestCase

CASS, EDIT, EASY = base.CASS, base.EDIT, "Easy to moderate"
SAME = f"route idea {CASS} already says that"


class RouteSpacingTests(HikeTestCase):
    # Reuse RouteEditTests' reader; a module-level RouteEditTests name would make unittest re-run its tests here.
    ideas = base.RouteEditTests.ideas

    def easy_repo(self):
        repo = self.repo()
        repo.run((EDIT, {"id": CASS, "difficulty": EASY}))
        return repo

    def snapshot(self, repo):
        return self.ideas(repo), self.ideas(repo, site=True)

    def change(self, repo, draft):
        return json.loads((repo.state / "changes" / f"{draft['change_id']}.json").read_text("utf-8"))

    def test_doubled_inner_space_is_already_says_that(self):
        repo = self.easy_repo()
        before = self.snapshot(repo)
        for value in ("Easy  to moderate", "Easy to   moderate"):
            with self.subTest(value=value):
                result = self.assertRejected(repo, "refused", (EDIT, {"id": CASS, "difficulty": value}))
                self.assertEqual(result["reason"], SAME)
        self.assertEqual(self.snapshot(repo), before)

    def test_tab_inside_is_still_refused_as_text(self):
        repo = self.easy_repo()
        before = self.snapshot(repo)
        result = self.assertRejected(repo, "invalid", (EDIT, {"id": CASS, "difficulty": "Easy\tto moderate"}))
        self.assertIn("control characters are not allowed", "\n".join(result["problems"]))
        self.assertEqual(self.snapshot(repo), before)

    def test_spacing_only_field_is_dropped_beside_a_real_change(self):
        repo = self.easy_repo()
        draft = repo.run((EDIT, {"id": CASS, "difficulty": "Easy  to moderate", "distance": "3.1 miles"}))
        [record] = self.change(repo, draft)["records"]
        changed = {k for k in record["after"] if record["after"][k] != record["before"].get(k)}
        self.assertEqual(changed, {"distance"})
        idea = self.ideas(repo)[CASS]
        self.assertEqual((idea["difficulty"], idea["distance"]), (EASY, "3.1 miles"))
        self.assertEqual(self.ideas(repo, site=True)[CASS]["difficulty"], EASY)

    def test_own_title_with_other_spacing_is_already_says_that(self):
        repo = self.repo()
        before = self.snapshot(repo)
        result = self.assertRejected(repo, "refused", (EDIT, {"id": CASS, "title": "Cass  Hill"}))
        self.assertEqual(result["reason"], SAME)  # never the duplicate-title refusal
        self.assertEqual(self.snapshot(repo), before)

    def test_case_only_difference_is_a_real_change(self):
        repo = self.easy_repo()
        draft = repo.run((EDIT, {"id": CASS, "difficulty": "easy to moderate"}))
        [record] = self.change(repo, draft)["records"]
        self.assertEqual((record["before"]["difficulty"], record["after"]["difficulty"]), (EASY, "easy to moderate"))
        self.assertEqual(self.ideas(repo)[CASS]["difficulty"], "easy to moderate")
        self.assertEqual(self.ideas(repo, site=True)[CASS]["difficulty"], "easy to moderate")

    def test_spaced_text_on_an_absent_field_is_a_real_change(self):
        wt = self.repo().wt
        content = load_and_validate(wt / "hass/content", wt / "storefront-mockup")
        idea = next(i for i in content.community["routeIdeas"] if i["id"] == CASS)
        del idea["elevationLabel"]
        touched = _route_edit(content, {"id": CASS, "elevationLabel": "Elevation  gain"}, None)
        self.assertIsInstance(touched, list)
        self.assertEqual([(t.key, "elevationLabel" in t.before, t.after["elevationLabel"]) for t in touched],
                         [(CASS, False, "Elevation  gain")])  # the owner's exact text is kept

    def test_leading_or_trailing_whitespace_is_still_refused(self):
        repo = self.easy_repo()
        before = self.snapshot(repo)
        for value in (" Easy to moderate", "Easy to moderate ", "Easy  to moderate "):
            with self.subTest(value=value):
                result = self.assertRejected(repo, "invalid", (EDIT, {"id": CASS, "difficulty": value}))
                self.assertIn("leading/trailing whitespace", "\n".join(result["problems"]))
        self.assertEqual(self.snapshot(repo), before)
