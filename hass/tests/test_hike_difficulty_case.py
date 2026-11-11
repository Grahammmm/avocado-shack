"""RF2345-9: hike.add / hike.edit keep the difficulty spelling the owner wrote, not the interpreter's capitalisation.

Run: python3 -B -m unittest hass.tests.test_hike_difficulty_case -q
"""
import types
import unittest
from datetime import datetime, timedelta, timezone

from hass.skills import hikes, load_skills
from hass.tests.test_skill_dispatch import SATURDAY, SkillCase, registry_of, skill_reply

PST = timezone(timedelta(hours=-8))
CASS = {"id": "hike-2026-11-21-cass-hill", "title": "Cass Hill", "startsAt": "2026-11-21T09:00:00-08:00",
        "timezone": "America/Los_Angeles", "status": "scheduled", "meetingPoint": "the gate", "rsvpEnabled": False}


def ctx(*texts):
    return types.SimpleNamespace(today="2026-11-08", now=datetime(2026, 11, 8, 9, 0, tzinfo=PST), texts=list(texts),
                                 content={"community": {"events": [CASS], "routeIdeas": []}})


def add(difficulty, *texts):
    slots = {"title": "Harbor Walk", "day": "2026-11-14", "clock": "09:00", "meeting_point": "the gate", "difficulty": difficulty}
    [op] = hikes.plan_add(slots, ctx(*texts))
    return op["args"]


def edit(difficulty, *texts):
    [op] = hikes.plan_edit({"hike": CASS["id"], "difficulty": difficulty}, ctx(*texts))
    return op["args"]


class OwnerCase(unittest.TestCase):
    def test_add_recovers_owner_case(self):
        for slot in ("Easy", "EASY", "easy"):
            self.assertEqual(add(slot, "add a hike Saturday at 9am, the gate, easy")["difficulty"], "easy")
        self.assertEqual(add("EASY-ISH, MOSTLY FLAT", "hike at the gate, Easy-ish, mostly flat")["difficulty"], "Easy-ish, mostly flat")
        self.assertEqual(add("easy", "it is   EASY")["difficulty"], "EASY")

    def test_edit_recovers_owner_case_without_touching_other_fields(self):
        slots = {"hike": CASS["id"], "difficulty": "Moderate", "meeting_point": "The Gate", "bring": "Water", "title": "Cass HILL"}
        [op] = hikes.plan_edit(slots, ctx("make Cass Hill moderate"))
        self.assertEqual(op["args"], {"id": CASS["id"], "title": "Cass HILL", "meetingPoint": "The Gate", "bring": "Water",
                                      "difficulty": "moderate"})
        self.assertEqual(slots["difficulty"], "Moderate")  # inputs are not mutated

    def test_latest_matching_phrase_wins(self):
        self.assertEqual(add("Easy", "easy would be nice", "no, make it EASY")["difficulty"], "EASY")
        self.assertEqual(add("easy", "easy then EASY", "ok")["difficulty"], "EASY")
        self.assertEqual(edit("Easy", "Easy", "x", "something else")["difficulty"], "Easy")

    def test_whole_phrase_and_missing_context_compatibility(self):
        self.assertEqual(add("EASY", "I feel uneasy")["difficulty"], "EASY")  # uneasy is not easy
        self.assertEqual(add("EASY")["difficulty"], "EASY")  # no texts
        self.assertEqual(add("EASY", "")["difficulty"], "EASY")
        self.assertEqual(add("Hard", "an easy one")["difficulty"], "Hard")  # a different difficulty is not copied
        self.assertEqual(add("EASY-ISH", "easy, ish")["difficulty"], "EASY-ISH")  # punctuation is not rewritten
        self.assertEqual(edit("Easy", "uneasy")["difficulty"], "Easy")
        slots = {"title": "Harbor Walk", "day": "2026-11-14", "clock": "09:00", "meeting_point": "the gate"}
        [op] = hikes.plan_add(slots, ctx("easy"))
        self.assertNotIn("difficulty", op["args"])  # nothing is invented


class RealDispatch(SkillCase):
    MODE = "both"
    TEXT = "add a hike Saturday at 9am at the gate called Harbor Walk, easy"

    def setUp(self):
        reg = load_skills()
        self.SKILLS = (reg.get("hike.add"),)
        super().setUp()
        self.registry = registry_of(*self.SKILLS)
        self.conv = self.open()

    def slots(self, difficulty):
        return dict(title="Harbor Walk", day=SATURDAY, clock="09:00", meeting_point="the gate", difficulty=difficulty)

    def test_real_dispatch_and_approval_keep_owner_case(self):
        self.script(self.TEXT, skill_reply("hike.add", **self.slots("EASY")))
        draft, reply = self.propose(self.TEXT)
        self.assertIn("how hard it is: easy", reply)
        self.assertNotIn("EASY", reply)
        self.nothing_written()
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.commits(), 1)
        ops = self.drafts()[-1]["ops_json"]
        self.assertIn('"difficulty": "easy"', ops)
        self.assertNotIn("EASY", ops)

    def test_calls_envelope_keeps_owner_case(self):
        calls = [{"skill": "hike.add", "slots": self.slots("EASY")}, {"skill": "hike.add", "slots": {**self.slots("EASY"), "title": "Pine Walk"}}]
        self.script(self.TEXT, {"calls": calls})
        self.assertEqual(self.say(self.TEXT), "proposed")
        self.assertNotIn("EASY", "\n".join(self.replies()))
        self.nothing_written()

    def test_unstated_difficulty_stays_dropped(self):
        text = "add a hike Saturday at 9am at the gate called Harbor Walk"
        self.script(text, skill_reply("hike.add", **self.slots("EASY")))
        self.assertEqual(self.say(text), "proposed")
        [reply] = self.replies()
        self.assertNotIn("how hard it is", reply)
        self.assertNotIn("EASY", reply)


if __name__ == "__main__":
    unittest.main()
