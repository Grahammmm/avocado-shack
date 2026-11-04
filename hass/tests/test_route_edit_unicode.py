"""H04 tests: ``route.edit`` treats look-alike Unicode titles as the same title.

Duplicate titles fold NFKC + spacing + case; "already says that" folds NFC + spacing (case kept). Nothing is normalized
on write. Uses the H04 harness (test_hike_ops.HikeTestCase) and test_route_edit's reader. Fixture content only.
Run: python3 -m unittest hass.tests.test_route_edit_unicode -v
"""

from hass.content_model import load_and_validate
from hass.ops import Refused
from hass.ops.routes import _route_edit
from hass.tests import test_route_edit as base
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

CASS, BUCHON, EDIT = base.CASS, base.BUCHON, base.EDIT
CAFE, CAFE_NFD = "Caf\u00e9 Loop", "Cafe\u0301 Loop"


class RouteUnicodeTitleTests(HikeTestCase):
    # Reuse RouteEditTests' reader; a module-level RouteEditTests name would make unittest re-run its tests here.
    ideas = base.RouteEditTests.ideas

    def content(self, repo):
        return load_and_validate(repo.wt / "hass/content", repo.wt / "storefront-mockup")

    def test_decomposed_title_of_another_idea_is_refused(self):
        repo = self.repo()
        repo.run((EDIT, {"id": CASS, "title": CAFE}))
        before = self.ideas(repo)
        for title in (CAFE_NFD, "CAFE\u0301  loop", "caf\u00c9 LOOP"):
            with self.subTest(title=ascii(title)):
                result = self.assertRejected(repo, "refused", (EDIT, {"id": BUCHON, "title": title}))
                self.assertEqual(result["reason"], f"{CASS} is already called {CAFE}")
        self.assertEqual(self.ideas(repo), before)

    def test_full_width_title_of_an_idea_or_a_hike_is_refused(self):
        repo = self.repo()
        repo.run(("hike.create", HIKE))
        before = self.ideas(repo)
        result = self.assertRejected(repo, "refused", (EDIT, {"id": BUCHON, "title": "\uff23\uff21\uff33\uff33 Hill"}))
        self.assertEqual(result["reason"], f"{CASS} is already called Cass Hill")
        result = self.assertRejected(repo, "refused", (EDIT, {"id": CASS, "title": "\uff34\uff45\uff53\uff54 hike"}))
        self.assertEqual(result["reason"], f"{HIKE_ID} is already called Test hike")
        self.assertEqual(self.ideas(repo), before)

    def test_compatibility_forms_in_stored_titles_are_folded_too(self):
        content = self.content(self.repo())
        content.community["events"].append({"id": "hike-fig", "title": "\ufb01g Tree  Trail"})  # "fi" ligature
        self.assertEqual(_route_edit(content, {"id": BUCHON, "title": "FIG tree trail"}, None),
                         Refused("hike-fig is already called \ufb01g Tree  Trail"))

    def test_re_encoding_own_title_already_says_that(self):
        repo = self.repo()
        repo.run((EDIT, {"id": CASS, "title": CAFE}))
        before = self.ideas(repo)
        place = before[CASS]["place"]
        for args in ({"title": CAFE_NFD}, {"title": "Cafe\u0301   Loop"}, {"title": CAFE_NFD, "place": place}):
            with self.subTest(args=ascii(args)):
                result = self.assertRejected(repo, "refused", (EDIT, {"id": CASS, **args}))
                self.assertEqual(result["reason"], f"route idea {CASS} already says that")
        self.assertEqual(self.ideas(repo), before)
        # Other fields fold NFC as well: re-encoding a description is no change either.
        content = self.content(repo)
        idea = next(i for i in content.community["routeIdeas"] if i["id"] == CASS)
        idea["description"] = "Caf\u00e9 at the top."
        self.assertEqual(_route_edit(content, {"id": CASS, "description": "Cafe\u0301 at the top."}, None),
                         Refused(f"route idea {CASS} already says that"))

    def test_case_or_width_only_change_on_own_title_is_still_drafted(self):
        repo = self.repo()
        repo.run((EDIT, {"id": CASS, "title": "cass hill"}))
        self.assertEqual(self.ideas(repo)[CASS]["title"], "cass hill")
        repo.run((EDIT, {"id": CASS, "title": "Cass Hill"}))
        self.assertEqual(self.ideas(repo)[CASS]["title"], "Cass Hill")
        content = self.content(repo)
        touched = _route_edit(content, {"id": CASS, "title": "\uff23ass Hill"}, None)
        self.assertEqual([t.after["title"] for t in touched], ["\uff23ass Hill"])

    def test_new_accented_title_is_drafted_and_stored_as_sent(self):
        for title in ("Pe\u00f1a Trail", "Pen\u0303a Trail"):
            with self.subTest(title=ascii(title)):
                repo = self.repo()
                repo.run((EDIT, {"id": BUCHON, "title": title}))
                stored = self.ideas(repo)[BUCHON]["title"]
                self.assertEqual(stored.encode("utf-8"), title.encode("utf-8"))
                self.assertEqual(self.ideas(repo, site=True)[BUCHON]["title"], title)
