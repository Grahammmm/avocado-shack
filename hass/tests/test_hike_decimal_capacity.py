"""RF0005-1: a decimal guest count ("3.5 spots") never authorizes an integer capacity taken from either side of the dot.

Run: python3 -B -m unittest hass.tests.test_hike_decimal_capacity -q
"""
import copy
import types
import unittest
from datetime import datetime, timedelta, timezone

from hass.skills import hikes, load_skills
from hass.tests.test_skill_dispatch import SATURDAY, SkillCase, registry_of, skill_reply

PST = timezone(timedelta(hours=-8))
CASS = {"id": "hike-2026-11-21-cass-hill", "title": "Cass Hill", "startsAt": "2026-11-21T09:00:00-08:00",
        "timezone": "America/Los_Angeles", "status": "scheduled", "meetingPoint": "the gate", "rsvpEnabled": True, "capacity": 8}
BASE = {"title": "Harbor Walk", "day": "2026-11-14", "clock": "09:00", "meeting_point": "the gate", "signup": True}


def ctx(*texts):
    return types.SimpleNamespace(today="2026-11-08", now=datetime(2026, 11, 8, 9, 0, tzinfo=PST), texts=list(texts), multi_call=False,
                                 content={"community": {"events": [CASS], "routeIdeas": []}})


class DecimalEvidence(unittest.TestCase):
    def test_decimals_give_no_guest_count_evidence(self):
        for text in ("sign-up on, 3.5 spots", "sign-up on, 0.5 guests", "12.5 people", "sign-up on, max 3.5",
                     "limit to 3.5 spots", "3.5 SPOTS"):
            self.assertEqual(hikes._said_limits(text), set(), text)

    def test_integers_and_corrections_still_count(self):
        self.assertEqual(hikes._said_limits("sign-up on, 5 spots"), {5})
        self.assertEqual(hikes._said_limits("five spots"), {5})
        self.assertEqual(hikes._said_limits("3 spots. Actually 5 spots"), {5})
        self.assertEqual(hikes._said_limits("3.5 spots. Actually 5 spots"), {5})
        self.assertEqual(hikes._said_limits("bring water for 2.5 miles, 5 spots"), {5})

    def test_add_and_edit_refuse_integer_from_a_decimal_fragment(self):
        for text, cap in (("sign-up on, 3.5 spots", 5), ("sign-up on, 3.5 spots", 3), ("sign-up on, max 3.5", 3),
                          ("sign-up on, 0.5 guests", 5)):
            add = {**BASE, "capacity": cap}
            edit = {"hike": CASS["id"], "signup": True, "capacity": cap}
            before = copy.deepcopy((add, edit))
            with self.assertRaises(hikes.Refusal) as cm:
                hikes.plan_add(add, ctx(text))
            self.assertEqual(cm.exception.reply, hikes.R_SPOTS_NOT_SAID, (text, cap))
            with self.assertRaises(hikes.Refusal) as cm:
                hikes.plan_edit(edit, ctx(text))
            self.assertEqual(cm.exception.reply, hikes.R_SPOTS_NOT_SAID, (text, cap))
            self.assertEqual((add, edit), before)

    def test_integer_capacity_is_still_accepted(self):
        [op] = hikes.plan_add({**BASE, "capacity": 5}, ctx("sign-up on, 5 spots"))
        self.assertEqual(op["args"]["capacity"], 5)
        [op] = hikes.plan_edit({"hike": CASS["id"], "signup": True, "capacity": 5}, ctx("sign-up on, 3.5 spots. Actually 5 spots"))
        self.assertEqual(op["args"]["capacity"], 5)


class RealDispatch(SkillCase):
    MODE = "both"

    def setUp(self):
        self.SKILLS = (load_skills().get("hike.add"),)
        super().setUp()
        self.registry = registry_of(*self.SKILLS)
        self.conv = self.open()

    def test_decimal_spots_create_no_draft(self):
        text = "Add Harbor Walk Saturday at 9, meet at the gate, sign up on, 3.5 spots"
        self.script(text, skill_reply("hike.add", title="Harbor Walk", day=SATURDAY, clock="09:00", meeting_point="the gate",
                                      signup=True, capacity=5))
        self.assertNotEqual(self.say(text), "proposed")
        self.assertIn(hikes.R_SPOTS_NOT_SAID, "\n".join(self.replies()))
        self.assertEqual(self.drafts(), [])
        self.nothing_written()


if __name__ == "__main__":
    unittest.main()
