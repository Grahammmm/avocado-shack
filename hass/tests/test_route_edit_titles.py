"""H04 tests: ``route.edit`` refuses a new title another route idea or a hike already uses (case and spacing ignored).

Uses the H04 harness (test_hike_ops.HikeTestCase: throwaway Git repo, writer worktree, temp state, production registry)
and the ``ideas`` reader of test_route_edit.RouteEditTests. Fixture content only.
Run: python3 -m unittest hass.tests.test_route_edit_titles -v
"""

from hass.content_model import load_and_validate
from hass.ops import Refused
from hass.ops.routes import _route_edit
from hass.tests import test_route_edit as base
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

CASS, BUCHON, EDIT, LOOP = base.CASS, base.BUCHON, base.EDIT, "Cass Hill Loop"


class RouteTitleTests(HikeTestCase):
    # Reuse RouteEditTests' reader; a module-level RouteEditTests name would make unittest re-run its tests here.
    ideas = base.RouteEditTests.ideas

    def content(self, repo):
        return load_and_validate(repo.wt / "hass/content", repo.wt / "storefront-mockup")

    def test_other_idea_title_with_other_case_and_spacing_is_refused(self):
        repo = self.repo()
        before, site_before = self.ideas(repo), self.ideas(repo, site=True)
        for title in ("cass  HILL", "Cass Hill", "CASS   hill"):
            with self.subTest(title=title):
                result = self.assertRejected(repo, "refused", (EDIT, {"id": BUCHON, "title": title}))
                self.assertEqual(result["reason"], f"{CASS} is already called Cass Hill")
        # A title change bundled with other fields is refused whole: nothing at all is drafted.
        bundled = {"id": BUCHON, "title": "cass hill", "distance": "9 miles"}
        result = self.assertRejected(repo, "refused", (EDIT, bundled))
        self.assertEqual(result["reason"], f"{CASS} is already called Cass Hill")
        self.assertEqual((self.ideas(repo), self.ideas(repo, site=True)), (before, site_before))

    def test_hike_title_is_refused_naming_the_hike(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        before = self.ideas(repo)
        result = self.assertRejected(repo, "refused", (EDIT, {"id": CASS, "title": "test  HIKE"}))
        self.assertEqual(result["reason"], f"{HIKE_ID} is already called Test hike")
        self.assertEqual(self.ideas(repo), before)

    def test_own_title_with_other_case_is_allowed(self):
        repo = self.repo()
        repo.run((EDIT, {"id": CASS, "title": "cass hill"}))
        repo.run((EDIT, {"id": CASS, "title": "Cass Hill"}))
        self.assertEqual(self.ideas(repo)[CASS]["title"], "Cass Hill")
        result = self.assertRejected(repo, "refused", (EDIT, {"id": CASS, "title": "Cass Hill"}))
        self.assertEqual(result["reason"], f"route idea {CASS} already says that")  # same-title check still first

    def test_other_fields_on_an_already_duplicated_title_are_allowed(self):
        content = self.content(self.repo())
        buchon = next(i for i in content.community["routeIdeas"] if i["id"] == BUCHON)
        buchon["title"] = "cass hill"  # stored data already duplicates idea-cass-hill
        touched = _route_edit(content, {"id": BUCHON, "difficulty": "Hard"}, None)
        self.assertIsInstance(touched, list)
        self.assertEqual([(t.collection, t.key, t.after["difficulty"]) for t in touched],
                         [("routeIdeas", BUCHON, "Hard")])
        # ... but a new title for idea-cass-hill is still compared against the stored duplicate.
        self.assertEqual(_route_edit(content, {"id": CASS, "title": "CASS HILL"}, None),
                         Refused(f"{BUCHON} is already called cass hill"))

    def test_stored_non_text_titles_are_skipped(self):
        content = self.content(self.repo())
        content.community["events"] += [{"id": "hike-odd", "title": 42}, {"id": "hike-none"},
                                        {"id": "hike-loop", "title": "cass hill  loop"}]
        content.community["routeIdeas"].append({"id": "idea-odd", "title": None})
        touched = _route_edit(content, {"id": CASS, "title": "Cass Hill Trail"}, None)
        self.assertIsInstance(touched, list)
        self.assertEqual([t.after["title"] for t in touched], ["Cass Hill Trail"])
        self.assertEqual(_route_edit(content, {"id": BUCHON, "title": LOOP}, None),
                         Refused("hike-loop is already called cass hill  loop"))

    def test_revert_brings_old_title_back_and_frees_new_one(self):
        repo = self.repo()
        change = repo.run((EDIT, {"id": CASS, "title": LOOP}))
        result = self.assertRejected(repo, "refused", (EDIT, {"id": BUCHON, "title": LOOP.lower()}))
        self.assertEqual(result["reason"], f"{CASS} is already called {LOOP}")
        repo.run(("history.revert", {"changeId": change["change_id"]}))
        self.assertEqual(self.ideas(repo)[CASS]["title"], "Cass Hill")
        self.assertEqual(self.ideas(repo, site=True)[CASS]["title"], "Cass Hill")
        repo.run((EDIT, {"id": BUCHON, "title": LOOP}))
        self.assertEqual(self.ideas(repo)[BUCHON]["title"], LOOP)
