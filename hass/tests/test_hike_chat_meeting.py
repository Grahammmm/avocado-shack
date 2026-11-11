"""HASS-CHAT-1: the meeting-place question keeps the identity of the hike call it was asked about.

shape() strips ``trailId`` from the waiting call, so a later yes could not find the saved route again when the owner had
abbreviated the place ("Fiscalini" for the route "Fiscalini Ranch"): the confirmed place was dropped and the proposal ignored it.
The question now carries the index of its call, and ``with_meeting`` applies the confirmed place to that call.
Run: python3 -m unittest hass.tests.test_hike_chat_meeting -v
"""

import unittest

from hass import hike_chat

ROUTES = {"idea-fiscalini-bluff": {"title": "Fiscalini Ranch", "place": "Cambria"},
          "idea-cass-hill": {"title": "Cass Hill", "place": "Cambria"}}


def create(meeting, trail=None, title="Fiscalini Ranch hike"):
    args = {"title": title, "date": "2026-11-08", "time": "10:00", "meetingPoint": meeting, "rsvpEnabled": False}
    if trail:
        args["trailId"] = trail
    return {"op": "hike.create", "args": args}


class MeetingQuestionIdentityTests(unittest.TestCase):
    def test_the_abbreviated_name_is_asked_and_the_yes_applies_the_suggestion_to_that_call(self):
        shaped = hike_chat.shape([create("Fiscalini", "idea-fiscalini-bluff")], ROUTES)
        self.assertEqual(shaped.ask["kind"], "meet")
        self.assertEqual(shaped.ask["suggest"], "Fiscalini Ranch trailhead, Cambria")
        self.assertNotIn("trailId", shaped.ops[0]["args"])
        ops = hike_chat.with_meeting(shaped.ops, shaped.ask["suggest"], ROUTES, shaped.ask["index"])
        self.assertEqual(ops[0]["args"]["meetingPoint"], "Fiscalini Ranch trailhead, Cambria")
        # the next shape of the confirmed call no longer asks: the proposal carries the confirmed place
        again = hike_chat.shape(ops, ROUTES)
        self.assertIsNone(again.ask)
        self.assertEqual(again.ops[0]["args"]["meetingPoint"], "Fiscalini Ranch trailhead, Cambria")

    def test_the_yes_goes_to_the_call_that_was_asked_about_not_an_earlier_trail_only_call(self):
        ops = [create("Cass Hill", "idea-cass-hill", "Cass Hill hike"), create("Fiscalini", "idea-fiscalini-bluff")]
        shaped = hike_chat.shape(ops, ROUTES)
        self.assertEqual(shaped.ask["index"], 0)  # the first call that is only a trail is the one asked about
        self.assertEqual(shaped.ask["suggest"], "Cass Hill trailhead, Cambria")
        done = hike_chat.with_meeting(shaped.ops, shaped.ask["suggest"], ROUTES, shaped.ask["index"])
        self.assertEqual([c["args"]["meetingPoint"] for c in done], ["Cass Hill trailhead, Cambria", "Fiscalini"])
        # a stored index past the first call lands on that call and no other
        later = hike_chat.with_meeting(shaped.ops, "Fiscalini Ranch trailhead, Cambria", ROUTES, 1)
        self.assertEqual([c["args"]["meetingPoint"] for c in later], ["Cass Hill", "Fiscalini Ranch trailhead, Cambria"])

    def test_the_index_counts_every_call_not_only_hikes(self):
        ops = [{"op": "product.set_availability", "args": {"id": "p", "available": "no"}}, create("Fiscalini", "idea-fiscalini-bluff")]
        shaped = hike_chat.shape(ops, ROUTES)
        self.assertEqual(shaped.ask["index"], 1)
        done = hike_chat.with_meeting(shaped.ops, shaped.ask["suggest"], ROUTES, 1)
        self.assertEqual(done[1]["args"]["meetingPoint"], "Fiscalini Ranch trailhead, Cambria")
        self.assertNotIn("meetingPoint", done[0]["args"])

    def test_a_call_with_a_real_place_is_never_overwritten_by_a_stored_index(self):
        ops = [create("Cass Hill trailhead", "idea-cass-hill", "Cass Hill hike")]
        self.assertEqual(hike_chat.with_meeting(ops, "Somewhere else", ROUTES, 0)[0]["args"]["meetingPoint"], "Cass Hill trailhead")

    def test_a_bad_or_missing_index_falls_back_to_the_first_trail_only_call(self):
        shaped = hike_chat.shape([create("Fiscalini Ranch bluff trail", "idea-fiscalini-bluff")], ROUTES)
        for index in (None, 7, -1, "0", True):
            with self.subTest(index=index):
                got = hike_chat.with_meeting(shaped.ops, "Fiscalini Ranch trailhead, Cambria", ROUTES, index)
                self.assertEqual(got[0]["args"]["meetingPoint"], "Fiscalini Ranch trailhead, Cambria")


if __name__ == "__main__":
    unittest.main()
