"""RF0440-11: a shorter saved-route name never shadows an exact or longer prefix route when a hike's meeting place is only a trail.

Pure offline shaper tests with synthetic routes. Run: python3 -B -m unittest hass.tests.test_hike_chat_route_specificity -q
"""

import itertools
import unittest

from hass import hike_chat

CEDAR = {"title": "Cedar", "place": "North Town"}
RIDGE = {"title": "Cedar Ridge", "place": "South Town"}
NORTH = {"title": "Cedar Ridge North", "place": "East Town"}


def routes_in_order(*items):
    return {f"idea-{n}": item for n, item in enumerate(items)}


def create(meeting, trail=None):
    args = {"title": "Cedar hike", "date": "2026-11-08", "time": "10:00", "meetingPoint": meeting, "rsvpEnabled": False}
    if trail:
        args["trailId"] = trail
    return {"op": "hike.create", "args": args}


class RouteSpecificityTests(unittest.TestCase):
    def test_exact_route_beats_earlier_short_prefix_in_both_orders(self):
        for routes in (routes_in_order(CEDAR, RIDGE), routes_in_order(RIDGE, CEDAR)):
            for meeting in ("Cedar Ridge", "Cedar Ridge loop"):
                with self.subTest(order=list(routes), meeting=meeting):
                    self.assertIs(hike_chat._route_for({"meetingPoint": meeting}, routes), RIDGE)
                    ops = [create(meeting)]
                    shaped = hike_chat.shape(ops, routes)
                    self.assertEqual(shaped.ask["suggest"], "Cedar Ridge trailhead, South Town")
                    done = hike_chat.with_meeting(shaped.ops, shaped.ask["suggest"], routes, shaped.ask["index"])
                    self.assertEqual(done[0]["args"]["meetingPoint"], "Cedar Ridge trailhead, South Town")
                    self.assertEqual(ops[0]["args"]["meetingPoint"], meeting)  # input untouched

    def test_longest_boundary_prefix_wins_across_three_lengths(self):
        for items in itertools.permutations((CEDAR, RIDGE, NORTH)):
            routes = routes_in_order(*items)
            with self.subTest(order=[i["title"] for i in items]):
                self.assertIs(hike_chat._route_for({"meetingPoint": "Cedar Ridge North loop"}, routes), NORTH)
                self.assertIs(hike_chat._route_for({"meetingPoint": "Cedar Ridge North"}, routes), NORTH)
                self.assertIs(hike_chat._route_for({"meetingPoint": "Cedar Ridge loop"}, routes), RIDGE)
                self.assertIs(hike_chat._route_for({"meetingPoint": "Cedar loop"}, routes), CEDAR)

    def test_folded_specificity_uses_nfkc_case_and_collapsed_whitespace(self):
        short = {"title": "  CEDAR  ", "place": "North Town"}
        long = {"title": "ＣＥＤＡＲ   ridge", "place": "South Town"}  # fullwidth, longer raw than folded
        for routes in (routes_in_order(short, long), routes_in_order(long, short)):
            with self.subTest(order=list(routes)):
                self.assertIs(hike_chat._route_for({"meetingPoint": " cedar  RIDGE   loop"}, routes), long)
                self.assertIs(hike_chat._route_for({"meetingPoint": "cedar loop"}, routes), short)
        self.assertEqual(hike_chat.suggest_meeting(long), "ＣＥＤＡＲ   ridge trailhead, South Town")
        # accents and punctuation are not newly folded away
        self.assertIsNone(hike_chat._route_for({"meetingPoint": "Cédar loop"}, routes_in_order(CEDAR)))
        self.assertIsNone(hike_chat._route_for({"meetingPoint": "Cedar, Ridge"}, routes_in_order(CEDAR)))

    def test_explicit_valid_route_id_still_overrides_meeting_text(self):
        routes = routes_in_order(CEDAR, RIDGE)
        self.assertIs(hike_chat._route_for({"trailId": "idea-0", "meetingPoint": "Cedar Ridge"}, routes), CEDAR)
        for bad in ("missing", 7, None):
            self.assertIs(hike_chat._route_for({"trailId": bad, "meetingPoint": "Cedar Ridge"}, routes), RIDGE)
        routes["idea-bad"] = "not a route"
        self.assertIs(hike_chat._route_for({"trailId": "idea-bad", "meetingPoint": "Cedar Ridge"}, routes), RIDGE)
        self.assertEqual(RIDGE, {"title": "Cedar Ridge", "place": "South Town"})

    def test_boundary_empty_no_match_and_equal_title_ties(self):
        routes = routes_in_order(CEDAR)
        for meeting in ("Cedarwood", "Cedarwood Ridge", "The Cedar", "", "x Cedar y"):
            self.assertIsNone(hike_chat._route_for({"meetingPoint": meeting}, routes), meeting)
        self.assertIsNone(hike_chat._route_for({"meetingPoint": "Ced"}, routes))
        odd = {"a": None, "b": {"title": ""}, "c": {"title": "  "}, "d": "Cedar", "e": {}, "f": CEDAR}
        self.assertIs(hike_chat._route_for({"meetingPoint": "Cedar loop"}, odd), CEDAR)
        self.assertIsNone(hike_chat._route_for({"meetingPoint": "Cedar loop"}, {}))
        self.assertIsNone(hike_chat._route_for({"meetingPoint": "Cedar loop"}, None))
        first, second = {"title": "Cedar", "place": "A"}, {"title": " cedar ", "place": "B"}
        self.assertIs(hike_chat._route_for({"meetingPoint": "Cedar loop"}, routes_in_order(first, second)), first)
        self.assertIs(hike_chat._route_for({"meetingPoint": "Cedar loop"}, routes_in_order(second, first)), second)

    def test_public_question_confirmation_preserves_call_identity(self):
        other = {"op": "product.set_availability", "args": {"id": "p", "available": "no"}}
        for routes in (routes_in_order(CEDAR, RIDGE), routes_in_order(RIDGE, CEDAR)):
            ops = [other, create("Cedar Ridge loop")]
            before = [dict(c) for c in ops]
            shaped = hike_chat.shape(ops, routes)
            self.assertEqual((shaped.ask["kind"], shaped.ask["index"]), ("meet", 1))
            self.assertEqual(shaped.ask["suggest"], "Cedar Ridge trailhead, South Town")
            done = hike_chat.with_meeting(shaped.ops, shaped.ask["suggest"], routes, 1)
            self.assertNotIn("meetingPoint", done[0]["args"])
            self.assertEqual(done[1]["args"]["meetingPoint"], "Cedar Ridge trailhead, South Town")
            self.assertIsNone(hike_chat.shape(done, routes).ask)  # a real trailhead is not asked about again
            self.assertEqual(ops, [other, create("Cedar Ridge loop")])
            self.assertEqual(before[0], ops[0])
        # a real meeting place and live=False stay unchanged
        routes = routes_in_order(CEDAR, RIDGE)
        self.assertIsNone(hike_chat.shape([create("Cedar Ridge trailhead")], routes).ask)
        off = hike_chat.shape([create("Cedar Ridge")], routes, live=False)
        self.assertIsNone(off.ask)
        self.assertEqual(off.ops[0]["args"]["meetingPoint"], "Cedar Ridge")

    def test_longer_route_that_is_too_long_is_not_replaced_by_a_shorter_one(self):
        huge = {"title": "Cedar Ridge " + "x" * hike_chat.MEETING_LIMIT, "place": "South Town"}
        for routes in (routes_in_order(CEDAR, huge), routes_in_order(huge, CEDAR)):
            shaped = hike_chat.shape([create(huge["title"])], routes)
            self.assertEqual(shaped.ask["kind"], "meet")
            self.assertIsNone(shaped.ask["suggest"])


if __name__ == "__main__":
    unittest.main()
