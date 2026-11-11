"""RF2345-10: hike.add asks when the owner stated guest spots but sign-up would be off, instead of silently dropping them.

Run: python3 -B -m unittest hass.tests.test_hike_signup_mismatch -q
"""
import copy
import json
import types
import unittest
from datetime import datetime, timedelta, timezone

from hass.skills import hikes, load_skills
from hass.tests.test_skill_dispatch import SATURDAY, SkillCase, registry_of, skill_reply

PST = timezone(timedelta(hours=-8))
CASS = {"id": "hike-2026-11-21-cass-hill", "title": "Cass Hill", "startsAt": "2026-11-21T09:00:00-08:00",
        "timezone": "America/Los_Angeles", "status": "scheduled", "meetingPoint": "the gate", "rsvpEnabled": True, "capacity": 8}
TEXT = "Add Harbor Walk November 14 at 9, meet at the gate, 3 spots"
BASE = {"title": "Harbor Walk", "day": "2026-11-14", "clock": "09:00", "meeting_point": "the gate"}


def ctx(*texts, multi_call=False):
    return types.SimpleNamespace(today="2026-11-08", now=datetime(2026, 11, 8, 9, 0, tzinfo=PST), texts=list(texts), multi_call=multi_call,
                                 content={"community": {"events": [CASS], "routeIdeas": []}})


def add_args(slots, *texts, multi_call=False):
    [op] = hikes.plan_add({**BASE, **slots}, ctx(*texts, multi_call=multi_call))
    return op["args"]


class PurePlan(unittest.TestCase):
    def test_add_asks_when_spots_would_be_lost(self):
        for extra in ({"signup": False, "capacity": 3}, {"capacity": 3}, {"signup": False}, {}, {"signup": False, "capacity": None}):
            slots = {**BASE, **extra}  # no capacity slot at all (omitted or None): the owner's words still state the 3 spots
            before = copy.deepcopy(slots)
            with self.assertRaises(hikes.Refusal) as cm:
                hikes.plan_add(slots, ctx(TEXT))
            self.assertEqual(cm.exception.reply, hikes.R_SIGNUP_UNCLEAR, extra)
            self.assertEqual(getattr(cm.exception, "kind", None), "question")
            self.assertEqual(slots, before)  # inputs are not changed

    def test_omitted_capacity_asks_for_alternative_counts_too(self):
        with self.assertRaises(hikes.Refusal) as cm:  # one call, two stated counts, no capacity slot: asked, never chosen or dropped
            hikes.plan_add({**BASE, "signup": False}, ctx("Add Harbor Walk November 14 at 9, the gate, 3 spots or 4 spots"))
        self.assertEqual(cm.exception.reply, hikes.R_SIGNUP_UNCLEAR)
        self.assertEqual(getattr(cm.exception, "kind", None), "question")

    def test_existing_refusals_keep_their_kind(self):
        self.assertFalse(hasattr(hikes.Refusal("x"), "kind"))

    def test_affirmed_guest_alternatives_are_not_silently_ignored(self):
        for text in ("Add Harbor Walk November 14 at 9, the gate, 3 spots or 4 spots", "hike at the gate, 3 spots, 4 spots"):
            with self.assertRaises(hikes.Refusal) as cm:
                hikes.plan_add({**BASE, "signup": False, "capacity": 3}, ctx(text))
            self.assertEqual(cm.exception.reply, hikes.R_SPOTS_NOT_SAID)  # the existing ambiguity refusal fires first: no count is chosen or dropped
            self.assertFalse(hasattr(cm.exception, "kind"))
        with self.assertRaises(hikes.Refusal) as cm:  # sign-up on keeps the existing ambiguity refusal
            hikes.plan_add({**BASE, "signup": True, "capacity": 3}, ctx("sign up the gate, 3 spots or 4 spots"))
        self.assertEqual(cm.exception.reply, hikes.R_SPOTS_NOT_SAID)
        self.assertFalse(hasattr(cm.exception, "kind"))

    def test_intentional_off_and_no_guest_request_stay_compatible(self):
        off = add_args({"signup": False}, "add Harbor Walk Saturday at 9, the gate, sign-up off")
        self.assertEqual(off["rsvpEnabled"], False)
        self.assertNotIn("capacity", off)
        latest_off = add_args({"signup": False}, "sign up please, 3 spots", "actually no sign ups")
        self.assertEqual(latest_off["rsvpEnabled"], False)
        self.assertNotIn("capacity", latest_off)
        with self.assertRaises(hikes.Refusal) as cm:  # off and spots in one message stay contradictory (existing refusal, not the new question)
            hikes.plan_add({**BASE, "signup": False, "capacity": 3}, ctx("add Harbor Walk at the gate, sign-up off, 3 spots"))
        self.assertEqual(cm.exception.reply, hikes.R_SIGNUP_UNCLEAR)
        self.assertFalse(hasattr(cm.exception, "kind"))
        answered = add_args({"signup": False, "capacity": 3}, TEXT, "no, leave sign up off")  # off said AFTER the spots: drafted off
        self.assertEqual(answered["rsvpEnabled"], False)
        self.assertNotIn("capacity", answered)
        for text in ("add Harbor Walk Dec 12 at 10am, the gate", "add Harbor Walk at the gate, bring 2 liters of water",
                     "add Harbor Walk at the gate, not 3 spots", "add a hike at 9, the gate"):
            args = add_args({}, text)
            self.assertEqual(args["rsvpEnabled"], False, text)
            self.assertNotIn("capacity", args)
        on = add_args({"signup": True, "capacity": 3}, TEXT)  # affirmative sign-up passes through the existing validation
        self.assertEqual((on["rsvpEnabled"], on["capacity"]), (True, 3))
        direct = hikes.plan_add({**BASE}, types.SimpleNamespace(today="2026-11-08"))  # no ctx.texts: slot-only behaviour
        shared = add_args({"signup": False}, "Add Harbor Walk 4 spots or 6 spots, and Pine hike at the gate", multi_call=True)  # a count no slot ties to one call of several
        self.assertEqual(shared["rsvpEnabled"], False)
        self.assertEqual(direct[0]["args"]["rsvpEnabled"], False)
        self.assertEqual(hikes.plan_add({**BASE, "signup": False, "capacity": 3}, types.SimpleNamespace(today="2026-11-08", texts=[]))[0]["args"]["rsvpEnabled"], False)

    def test_edit_capacity_only_does_not_gain_signup_question(self):
        [op] = hikes.plan_edit({"hike": CASS["id"], "capacity": 3}, ctx("cap Cass Hill at 3"))
        self.assertEqual(op, {"op": "hike.update", "args": {"id": CASS["id"], "capacity": 3}})


class RealDispatch(SkillCase):
    MODE = "both"
    ANSWER_ON = "yes, guests can sign up"
    ANSWER_OFF = "no, leave sign up off"

    def setUp(self):
        self.SKILLS = (load_skills().get("hike.add"),)
        super().setUp()
        self.registry = registry_of(*self.SKILLS)
        self.conv = self.open()

    def slots(self, **extra):
        return {**BASE, "meeting_point": "the gate", "day": SATURDAY, "signup": False, "capacity": 3, **extra}

    def test_real_dispatch_asks_then_continues_with_all_slots(self):
        self.script(TEXT, skill_reply("hike.add", **self.slots()))
        self.assertEqual(self.say(TEXT), "question")
        self.assertEqual(self.replies(), [hikes.R_SIGNUP_UNCLEAR])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()
        self.now += timedelta(minutes=1)
        self.conv = self.open()  # the open request is persisted
        self.script(self.ANSWER_ON, skill_reply("hike.add", signup=True, capacity=3))
        self.assertEqual(self.say(self.ANSWER_ON), "proposed")
        self.nothing_written()
        [draft] = self.drafts()
        [op] = json.loads(draft["ops_json"])
        self.assertEqual(op["op"], "hike.create")
        self.assertEqual(op["args"], {"title": "Harbor Walk", "date": SATURDAY, "time": "09:00", "meetingPoint": "the gate",
                                      "rsvpEnabled": True, "capacity": 3})
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual(self.commits(), 1)

    def test_real_owner_off_clarification_retains_no_signup(self):
        self.script(TEXT, skill_reply("hike.add", **self.slots()))
        self.assertEqual(self.say(TEXT), "question")
        self.replies()
        self.script(self.ANSWER_OFF, skill_reply("hike.add", signup=False, capacity=None))
        self.assertEqual(self.say(self.ANSWER_OFF), "proposed")
        self.assertNotIn(hikes.R_SIGNUP_UNCLEAR, "\n".join(self.replies()))
        self.nothing_written()
        [op] = json.loads(self.drafts()[-1]["ops_json"])
        self.assertEqual(op["args"]["rsvpEnabled"], False)
        self.assertNotIn("capacity", op["args"])

    def test_real_dispatch_asks_when_capacity_slot_is_omitted(self):
        for extra in ({}, {"capacity": None}):  # one call, sign-up off, the owner's 3 spots left out of the slots
            slots = self.slots(**extra)
            if not extra:
                slots.pop("capacity")
            self.script(TEXT, skill_reply("hike.add", **slots))
            self.assertEqual(self.say(TEXT), "question")
            self.assertIn(hikes.R_SIGNUP_UNCLEAR, "\n".join(self.replies()))
            self.assertEqual(self.drafts(), [])
            self.nothing_written()
            self.now += timedelta(minutes=1)
            self.conv = self.open()

    def test_calls_envelope_shared_count_without_capacity_slot_is_not_asked(self):
        shared = "Add Harbor Walk 4 spots or 6 spots, and Pine Walk at the gate"
        harbor, pine = self.slots(), self.slots(title="Pine Walk")
        for call in (harbor, pine):
            call.pop("capacity"), call.pop("signup")
        self.script(shared, {"calls": [{"skill": "hike.add", "slots": harbor}, {"skill": "hike.add", "slots": pine}]})
        self.assertEqual(self.say(shared), "proposed")
        self.assertNotIn(hikes.R_SIGNUP_UNCLEAR, "\n".join(self.replies()))
        self.nothing_written()

    def test_calls_envelope_does_not_partially_apply(self):
        pine = {**self.slots(title="Pine Walk", signup=None, capacity=None)}
        pine.pop("signup"), pine.pop("capacity")
        self.script(TEXT, {"calls": [{"skill": "hike.add", "slots": self.slots()}, {"skill": "hike.add", "slots": pine}]})
        self.say(TEXT)
        self.assertIn(hikes.R_SIGNUP_UNCLEAR, "\n".join(self.replies()))
        self.nothing_written()  # only a proposal exists for the other call: no commit, no approval
        self.assertEqual(len(self.table("SELECT * FROM open_requests WHERE state != 'superseded'")), 1)


if __name__ == "__main__":
    unittest.main()
