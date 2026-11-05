"""AV0022-12 tests: a hike number with a unit (mi, km, ft, hours, min) the owner and the linked route idea did not give asks.

Pure draft dicts like test_claims_access, plus conversation cases on the production registry and the writer worktree.
Run: python3 -m unittest hass.tests.test_claims_numbers -v
"""

import json
import unittest
from unittest import mock

from hass import claims, conversation
from hass.tests.test_claims import MAKERS, edit
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_hike_ops import HIKE, HIKE_ID

POST = "post a hike Saturday 9am at Cass Hill"
IDEA = {"id": "idea-cass-hill", "distance": "3 miles", "duration": "About 2 hours", "elevation": "About 690 ft", "rsvp": True}
ROUTES = {"idea-cass-hill": IDEA}


def hits(before, after, owner=POST, routes=ROUTES, field="distance", collection="events", ops=None, trail=None):
    draft = edit(before, after, field=field, collection=collection, key="h1", ops=ops)
    if trail:
        draft["records"][0]["after"]["trailId"] = trail
    return [term for _w, term in claims.unstated(draft, owner, MAKERS, routes)]


class NumberTests(unittest.TestCase):
    def test_unsaid_distance_asks_with_the_matched_text(self):
        draft = edit(None, "A 3.2 miles loop", field="distance", collection="events", key="h1")
        self.assertEqual(claims.unstated(draft, POST, MAKERS), [("events h1 distance", "3.2 miles")])
        self.assertIn('"3.2 miles" in events h1 distance is not in your message', claims.question(claims.unstated(draft, POST, MAKERS)))

    def test_owner_units_and_spellings_back_the_number(self):
        self.assertEqual(hits(None, "3.2 miles", "3.2 mi loop"), [])
        self.assertEqual(hits(None, "3.20 miles", "3.2 mi loop"), [])
        self.assertEqual(hits(None, "3,2 km", "a 3.2 kilometers walk"), [])
        self.assertEqual(hits(None, "690 feet", "about 690 ft of climb"), [])
        self.assertEqual(hits(None, "90 minutes", "90 min", field="duration"), [])
        self.assertEqual(hits(None, "3.2 miles", "3.2 km loop"), ["3.2 miles"])  # another unit is another claim
        self.assertEqual(hits(None, "3.2 miles", "meet at 3.2"), ["3.2 miles"])  # no unit in the owner's words

    def test_route_idea_values_back_the_number_through_trail_id(self):
        draft = {"ops": [{"op": "hike.create", "args": {}}], "records": [{
            "collection": "events", "key": "h1", "before": None,
            "after": {"distance": "3 miles", "duration": "About 2 hours", "elevation": "About 690 ft", "trailId": "idea-cass-hill"}}]}
        self.assertEqual(claims.unstated(draft, POST, MAKERS, ROUTES), [])
        draft["records"][0]["after"]["distance"] = "4 miles"
        self.assertEqual(claims.unstated(draft, POST, MAKERS, ROUTES), [("events h1 distance", "4 miles")])
        draft["records"][0]["after"]["trailId"] = "idea-other"  # an unknown idea backs nothing
        draft["records"][0]["after"]["distance"] = "3 miles"
        self.assertEqual([t for _w, t in claims.unstated(draft, POST, MAKERS, ROUTES)], ["3 miles", "2 hours", "690 ft"])

    def test_route_values_do_not_back_a_hike_without_trail_id(self):
        self.assertEqual(hits(None, "3 miles"), ["3 miles"])
        self.assertEqual(hits(None, "3 miles", trail=["idea-cass-hill"]), ["3 miles"])  # not a usable id
        self.assertEqual(hits(None, "3 miles", trail="idea-cass-hill"), [])

    def test_unreadable_routes_leave_the_owner_text_only(self):
        self.assertEqual(hits(None, "3 miles", routes=None, trail="idea-cass-hill"), ["3 miles"])
        self.assertEqual(hits(None, "3 miles", "3 miles", routes=None, trail="idea-cass-hill"), [])

    def test_ranges_need_both_ends(self):
        self.assertEqual(hits(None, "3–4 hours", "it takes 3 to 4 hours", field="duration"), [])
        self.assertEqual(hits(None, "3-4 hours", "3-4 hours", field="duration"), [])
        self.assertEqual(hits(None, "3–4 hours", "it takes 3 hours", field="duration"), ["3-4 hours"])  # the 4 is unsaid
        self.assertEqual(hits(None, "3–4 hours", "4 hours", field="duration"), ["3-4 hours"])

    def test_count_must_increase(self):
        self.assertEqual(hits("2 miles", "2 miles, easy"), [])
        self.assertEqual(hits("2 miles", "2.0 miles, easy"), [])
        self.assertEqual(hits("2 miles", "2 miles, then 2 miles more"), ["2 miles"])
        self.assertEqual(hits("2 miles", "5 miles"), ["5 miles"])
        self.assertEqual(hits("5 miles", "2 miles", "2 miles"), [])

    def test_numbers_without_units_and_other_unit_words_are_not_claims(self):
        for after in ("Meet 8:30", "Group of 12", "Highway 1", "5k", "10h", "10 hz", "about 3 milestones", "mile 3", "5km2"):
            with self.subTest(after=after):
                self.assertEqual(hits(None, after, field="meetingPoint"), [])
        self.assertEqual(hits(None, "Meet 8:30 min before", field="meetingPoint"), [])  # a clock time, not 30 min

    def test_every_unit_is_a_unit(self):
        for text in ("2 mi", "2 mile", "2 km", "2 kilometres", "2 ft", "2 foot", "2 hr", "2 hrs", "2 hour", "2 mins", "2 minutes"):
            with self.subTest(text=text):
                self.assertEqual(hits(None, text), [text])

    def test_text_fields_any_name_are_scanned_but_only_for_events(self):
        self.assertEqual(hits(None, "a 2 hour walk", field="description"), ["2 hour"])
        self.assertEqual(hits(None, "2 lb bag", field="description", collection="products"), [])
        self.assertEqual(hits(None, "walk 2 miles", field="description", collection="products"), [])
        self.assertEqual(hits(None, "walk 2 miles", field="description", collection="routeIdeas"), [])

    def test_a_revert_is_never_checked(self):
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(hits("1 mile", "9 miles", ops=revert), [])


class NumberConversationTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def ask(self, text, **extra):
        self.interp.mapping[text] = _ops(("hike.create", {**HIKE, **extra}))
        rows = self.drafts()
        return rows, self.say(text)

    def test_unsaid_distance_asks_and_writes_no_row(self):
        rows, result = self.ask(POST, distance="3.2 miles")
        self.assertEqual(result, "claim-question")
        self.assertIn('"3.2 miles" in events hike-2026-12-05-test-hike distance', self.replies()[0])
        self.assertEqual(self.drafts(), rows)

    def test_owner_words_propose(self):
        self.assertEqual(self.ask(f"{POST}, 3.2 mi", distance="3.2 miles")[1], "proposed")

    def test_route_idea_values_propose(self):
        route = self.ask(POST, distance="3 miles", duration="About 2 hours", trailId="idea-cass-hill")
        self.assertEqual(route[1], "proposed")

    def test_a_number_the_route_idea_does_not_have_asks(self):
        rows, result = self.ask(POST, distance="4 miles", trailId="idea-cass-hill")
        self.assertEqual(result, "claim-question")
        self.assertEqual(self.drafts(), rows)

    def test_routes_read_from_the_worktree_and_none_when_unreadable(self):
        self.assertEqual(self.conv._routes()["idea-cass-hill"]["distance"], "3 miles")
        community = self.repo.wt / "hass" / "content" / "community.json"
        for bad in ("{", json.dumps({"routeIdeas": "x"}), json.dumps({})):
            with self.subTest(bad=bad):
                community.write_text(bad, "utf-8")
                self.assertIsNone(self.conv._routes())

    def test_unreadable_routes_leave_only_the_owner_text(self):
        with mock.patch.object(conversation.Conversation, "_routes", return_value=None):
            rows, result = self.ask(POST, distance="3 miles", trailId="idea-cass-hill")
        self.assertEqual(result, "claim-question")
        self.assertIn('"3 miles" in events hike-2026-12-05-test-hike distance', self.replies()[0])
        self.assertEqual(self.drafts(), rows)


if __name__ == "__main__":
    unittest.main()
