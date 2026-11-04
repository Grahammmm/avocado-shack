"""RF1530-6 (H04/H09) tests: ``route.add`` / ``route.edit`` refuse a route text over its TEXT_LIMITS limit by name.

Same harness as test_route_edit (test_hike_ops.HikeRepo, production registry). Fixture content only.
Run: python3 -m unittest hass.tests.test_route_limits -v
"""

import json

from hass.content_model import TEXT_LIMITS
from hass.tests.test_hike_ops import HikeTestCase
from hass.tests.test_route_add import ADD, NEW, NEW_ID

CASS, EDIT = "idea-cass-hill", "route.edit"
LIMIT = TEXT_LIMITS["routeIdea"]["description"]  # 600


class RouteLimitTests(HikeTestCase):
    def ideas(self, repo):
        path = repo.wt / "hass/content/community.json"
        return {i["id"]: i for i in json.loads(path.read_text("utf-8"))["routeIdeas"]}

    def test_edit_description_over_limit_is_refused_by_name(self):
        repo = self.repo()
        before = self.ideas(repo)
        text = "x" * (LIMIT + 1)
        result = self.assertRejected(repo, "refused", (EDIT, {"id": CASS, "description": text}))
        self.assertEqual(result["reason"], "description is longer than 600 characters")
        self.assertNotIn(text, json.dumps(result))
        self.assertEqual(self.ideas(repo), before)

    def test_edit_exactly_at_limit_is_drafted(self):
        repo = self.repo()
        repo.run((EDIT, {"id": CASS, "description": "y" * LIMIT}))
        self.assertEqual(self.ideas(repo)[CASS]["description"], "y" * LIMIT)

    def test_add_title_over_limit_is_refused_before_slug_and_title_checks(self):
        repo = self.repo()
        for title in ("!" * (LIMIT + 1), "a" * (LIMIT + 1)):  # no letter or digit (slug refusal) / a valid slug
            with self.subTest(title=title[:1]):
                result = self.assertRejected(repo, "refused", (ADD, {**NEW, "title": title}))
                self.assertEqual(result["reason"], "title is longer than 600 characters")
        self.assertNotIn(NEW_ID, self.ideas(repo))

    def test_add_source_name_over_limit_is_refused_before_the_https_check(self):
        repo = self.repo()
        result = self.assertRejected(repo, "refused", (ADD, {**NEW, "sourceName": "s" * (LIMIT + 1),
                                                           "sourceUrl": "http://trails.example.org/bluff"}))
        self.assertEqual(result["reason"], "sourceName is longer than 600 characters")

    def test_add_at_limit_is_drafted(self):
        repo = self.repo()
        repo.run((ADD, {**NEW, "sourceName": "s" * LIMIT, "description": "d" * LIMIT}))
        self.assertEqual(len(self.ideas(repo)[NEW_ID]["description"]), LIMIT)

    def test_two_over_limit_fields_name_the_first_in_editable_order(self):
        repo = self.repo()
        long = "z" * (LIMIT + 1)
        result = self.assertRejected(repo, "refused", (EDIT, {"id": CASS, "description": long, "place": long}))
        self.assertEqual(result["reason"], "place is longer than 600 characters")
        result = self.assertRejected(repo, "refused", (ADD, {**NEW, "sourceName": long, "terrain": long}))
        self.assertEqual(result["reason"], "terrain is longer than 600 characters")
