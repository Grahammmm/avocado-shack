"""RF2150-12: a hike.create/update with both a numeric guest limit and noCapacityLimit asks one question, shapes nothing.

Run: python3 -m unittest hass.tests.test_hike_chat_capacity_conflict -v
"""

import copy
import unittest

from hass import hike_chat

ASK = "Please give either a guest limit or no limit, not both."


def create(**extra):
    args = {"title": "Test hike", "date": "2026-12-05", "time": "09:00", "meetingPoint": "Test trailhead lot", "rsvpEnabled": False}
    args.update(extra)
    return {"op": "hike.create", "args": args}


def update(**extra):
    return {"op": "hike.update", "args": {"id": "h1", **extra}}


EVENTS = {"h1": {"title": "Short walk", "description": "A short walk."}}


class CapacityConflictTests(unittest.TestCase):
    def assert_refused(self, ops, events=None):
        before = copy.deepcopy(ops)
        shaped = hike_chat.shape(ops, events=events)
        self.assertEqual(shaped.ask, {"kind": "offer", "question": ASK, "suggest": None, "ops": None})
        self.assertEqual(shaped.ops, before)
        self.assertEqual(shaped.notes, [])
        self.assertEqual(ops, before)

    def test_create_conflict_asks_for_both_rsvp_values(self):
        for rsvp in (True, False):
            self.assert_refused([create(capacity=6, noCapacityLimit=True, rsvpEnabled=rsvp)])

    def test_update_conflict_never_offers_numeric_description(self):
        self.assert_refused([update(capacity=6, noCapacityLimit=True)], EVENTS)
        self.assert_refused([update(capacity=6, noCapacityLimit=True, rsvpEnabled=True, description="x" * 800)], EVENTS)
        self.assert_refused([update(capacity=6, noCapacityLimit=True)], {})

    def test_conflict_in_later_batch_call_stops_whole_candidate(self):
        self.assert_refused([{"op": "other.thing", "args": {}}, create(), create(capacity=3, noCapacityLimit=True)])

    def test_single_choice_and_type_boundaries_stay_compatible(self):
        shaped = hike_chat.shape([create(capacity=6)])
        self.assertIn("Limited to 6", shaped.ops[0]["args"]["description"])
        self.assertIsNone(shaped.ask)
        for extra in ({"noCapacityLimit": True}, {"capacity": 6, "noCapacityLimit": False}, {"capacity": True, "noCapacityLimit": True},
                      {"capacity": 0, "noCapacityLimit": True}, {"capacity": -2, "noCapacityLimit": True},
                      {"capacity": "6", "noCapacityLimit": True}, {"capacity": 6, "noCapacityLimit": "yes"}):
            self.assertIsNone(hike_chat.shape([create(**extra)]).ask, extra)
        ops = [create(capacity=6, noCapacityLimit=True)]
        self.assertEqual(hike_chat.shape(ops, live=False).ops, ops)
        self.assertEqual(hike_chat.shape("nope").ops, "nope")


if __name__ == "__main__":
    unittest.main()
