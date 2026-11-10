"""RF2115-11: a multi-call (several asks in one message) proposal says which owner-word fields it left off, as a single-skill
proposal does (SKILLS-SPEC 2.2/2.8). Only the field NAMES are shown, never the invented value, and nothing is written before the
owner's own yes.

Real Conversation, Dispatcher and clocked Editor on the throwaway repo with an injected clock; the interpreter is a scripted
stand-in (no model, no socket). Toy skills come from test_skill_dispatch.
Run: python3 -m unittest hass.tests.test_skill_multicall_left_off -v
"""
import json
import unittest
from datetime import timedelta

from hass.skills.model import Slot
from hass.tests.test_skill_dispatch import DESCRIBE, HIKE_ADD, MILL, SATURDAY, SkillCase, registry_of, skill_reply, toy

SAYS = "Hike notes: bring a hat."
SETS = "I set: the hike to easy."
WARNS = "The meeting place is far."
BREAD = "Brian's sourdough bread"
TEXT = f"add the Mill Creek hike Saturday 8am at Mill Creek trailhead, easy, and change {BREAD} to tasty"
LEFT = "Left off (you didn't say it): difficulty."
FAKE = "strenuous"  # an optional owner-word value the owner never said
NO_TIME = {k: v for k, v in MILL.items() if k != "time"}


def notes(name, slots, ctx):
    return {"say": [SAYS], "set": [SETS], "warn": [WARNS]} if name == "hike.add" else {}


def _plan_hike(slots, ctx):
    args = {"title": slots["title"], "date": slots["day"], "time": slots["time"], "meetingPoint": slots["place"], "rsvpEnabled": False}
    if slots.get("difficulty"):
        args["difficulty"] = slots["difficulty"]
    return [{"op": "hike.create", "args": args}]


def _plan_walk(slots, ctx):
    return [{"op": "hike.create", "args": {"title": slots["title"], "date": slots["day"], "time": slots["time"],
                                           "meetingPoint": slots["place"], "rsvpEnabled": False}}]


def _plan_refused(slots, ctx):
    raise Refused("That one is cancelled, so nothing changed.")


class Refused(ValueError):
    def __init__(self, reply):
        super().__init__(reply)
        self.reply, self.kind, self.backlog = reply, "refuse", "policy"


for fn in (_plan_hike, _plan_walk, _plan_refused):
    fn.__module__ = __name__  # the dispatcher finds a skill's notes hook in the module that defines its plan
HOOKED = toy("hike.add", "add a hike", HIKE_ADD.slots, _plan_hike)
WALK = toy("walk.add", "add a walk", (*HIKE_ADD.slots[:4], Slot("bring", "text", False, owner_words=True)), _plan_walk)
REFUSER = toy("hike.cancel", "cancel a hike", (Slot("title", "text", True, ask="Which hike?"),), _plan_refused)


class LeftOffCase(SkillCase):
    SKILLS = (HOOKED, DESCRIBE, WALK, REFUSER)

    def send(self, text, calls):
        self.script(text, {"calls": calls, "revises": None})
        self.assertEqual(self.say(text), "proposed")
        [reply] = self.replies()
        return self.drafts()[-1], reply

    def left_lines(self, reply):
        return [line for line in reply.splitlines() if line.startswith("Left off")]

    def assert_value_absent(self, draft, reply):
        self.assertNotIn(FAKE, reply)
        self.assertNotIn(FAKE, draft["ops_json"])
        for op in json.loads(draft["ops_json"]):
            self.assertNotIn("difficulty", op["args"])


class MultiCallLeftOff(LeftOffCase):
    def calls(self, **hike):
        return [{"skill": "hike.add", "slots": {**MILL, "difficulty": FAKE, **hike}},
                {"skill": "item.describe", "slots": {"product": BREAD, "description": "tasty"}}]

    def test_completed_calls_disclose_untraceable_optional_field(self):
        text = f"add the Mill Creek hike Saturday 8am at Mill Creek trailhead and change {BREAD} to tasty"
        draft, reply = self.send(text, self.calls())
        self.assertEqual(self.left_lines(reply), [LEFT])
        ops = json.loads(draft["ops_json"])
        self.assertEqual([op["op"] for op in ops], ["hike.create", "product.edit"])
        self.assert_value_absent(draft, reply)
        self.assertEqual(self.say("yes " + draft["code"]), "approved")  # the valid sibling is proposed and approvable

    def test_single_and_one_element_calls_have_same_left_off_disclosure(self):
        text = "add a hike Saturday at 8am, Mill Creek trailhead, easy"
        self.script(text, skill_reply("hike.add", **{**MILL, "difficulty": FAKE}))
        single_draft, single = self.propose(text)
        self.now += timedelta(minutes=1)
        other = "add the Mill Creek hike Saturday at 8am at Mill Creek trailhead, easy"
        draft, many = self.send(other, [{"skill": "hike.add", "slots": {**MILL, "difficulty": FAKE}}])
        self.assertEqual(self.left_lines(single), [LEFT])
        self.assertEqual(self.left_lines(many), self.left_lines(single))
        self.assertEqual(json.loads(draft["ops_json"]), json.loads(single_draft["ops_json"]))
        self.assertEqual([line for line in many.splitlines() if line.startswith(("Hike notes", "I set", "The meeting"))],
                         [line for line in single.splitlines() if line.startswith(("Hike notes", "I set", "The meeting"))])

    def test_multiple_successful_calls_keep_field_order_and_other_notes(self):
        text = "add the Mill Creek hike Saturday 8am at Mill Creek trailhead, easy, and a walk at the pier Saturday 8am, easy"
        walk = {"title": "Pier walk", "place": "the pier", "day": SATURDAY, "time": "08:00", "bring": "kayak"}
        draft, reply = self.send(text, [{"skill": "hike.add", "slots": {**MILL, "difficulty": FAKE}},
                                        {"skill": "walk.add", "slots": walk}])
        self.assertEqual(self.left_lines(reply), ["Left off (you didn't say it): difficulty, bring."])
        lines = reply.splitlines()
        order = [lines.index(x) for x in (SAYS, SETS, "Left off (you didn't say it): difficulty, bring.", WARNS)]
        self.assertEqual(order, sorted(order))  # say, set, left off, warn: the formatter's own order
        self.assertNotIn("kayak", reply)
        self.assertNotIn(FAKE, reply)
        self.assertEqual(len(json.loads(draft["ops_json"])), 2)

    def test_complete_calls_without_a_dropped_field_have_no_left_off_line(self):
        text = f"add the Mill Creek hike Saturday 8am at Mill Creek trailhead, easy, and change {BREAD} to tasty"
        _, reply = self.send(text, self.calls(difficulty="easy"))
        self.assertEqual(self.left_lines(reply), [])
        self.assertNotIn("Left off", reply)


class WaitingAndRefusedCalls(LeftOffCase):
    def test_waiting_call_is_not_claimed_as_part_of_the_proposal(self):
        text = "add the Mill Creek hike Saturday 8am at Mill Creek trailhead, easy, and the Pine hike at Pine lot Saturday"
        pine = {"title": "Pine hike", "place": "Pine lot", "day": SATURDAY, "bring": FAKE}  # no time: it waits; bring is untraceable
        self.script(text, {"calls": [{"skill": "hike.add", "slots": {**MILL, "difficulty": FAKE}},
                                     {"skill": "walk.add", "slots": pine}], "revises": None})
        self.assertEqual(self.say(text), "proposed")
        replies = self.replies()
        self.assertEqual(len(replies), 2)  # the proposal, then exactly one next question
        reply, asked = replies
        draft = self.drafts()[-1]
        # the proposal is the first call only: its own dropped field is named, the waiting call's is not
        self.assertEqual(self.left_lines(reply), [LEFT])
        self.assertNotIn("bring", reply.replace("Hike notes: bring a hat.", ""))
        self.assertEqual(len(json.loads(draft["ops_json"])), 1)
        self.assert_value_absent(draft, reply)
        self.assertEqual(asked, "What time does it start?")
        live = self.live()
        self.assertEqual((live["skill"], live["asked_slot"], live["calls"]), ("walk.add", "time", []))
        self.assertEqual(len([d for d in self.drafts() if d["state"] == "proposed"]), 1)
        self.nothing_written()

    def test_refused_call_does_not_invent_a_left_off_proposal(self):
        text = "add the Mill Creek hike Saturday 8am at Mill Creek trailhead, easy, and cancel the Pine hike"
        self.script(text, {"calls": [{"skill": "hike.add", "slots": {**MILL, "difficulty": FAKE}},
                                     {"skill": "hike.cancel", "slots": {"title": "Pine hike"}}], "revises": None})
        self.assertEqual(self.say(text), "proposed")
        replies = self.replies()
        self.assertEqual(len(replies), 2)
        said = [r for r in replies if "cancelled" in r]
        proposal = [r for r in replies if "Reply yes" in r]
        self.assertEqual((len(said), len(proposal)), (1, 1))  # the refusal is said as before; the proposal is the successful call's
        self.assertEqual(self.left_lines(proposal[0]), [LEFT])
        self.assertEqual(self.left_lines(said[0]), [])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM backlog").fetchone()[0], 1)  # the refusal's backlog row stays
        self.assert_value_absent(self.drafts()[-1], proposal[0])

    def test_all_calls_refused_has_no_left_off_proposal(self):
        text = "cancel the Pine hike and the Oak hike"
        self.script(text, {"calls": [{"skill": "hike.cancel", "slots": {"title": "Pine hike"}},
                                     {"skill": "hike.cancel", "slots": {"title": "Oak hike"}}], "revises": None})
        self.say(text)
        self.assertFalse([r for r in self.replies() if "Left off" in r])
        self.nothing_written()


class WriterUntouched(LeftOffCase):
    def test_reply_and_duplicate_leave_writer_untouched(self):
        text = f"add the Mill Creek hike Saturday 8am at Mill Creek trailhead and change {BREAD} to tasty"
        calls = [{"skill": "hike.add", "slots": {**MILL, "difficulty": FAKE}},
                 {"skill": "item.describe", "slots": {"product": BREAD, "description": "tasty"}}]
        self.script(text, {"calls": calls, "revises": None})
        self.assertEqual(self.say(text, pid="dup1"), "proposed")
        [first] = self.replies()
        self.assertEqual(self.left_lines(first), [LEFT])
        self.nothing_written()
        self.say(text, pid="dup1")  # the same delivery again: no second draft, no second disclosure
        self.assertEqual(self.replies(), [])
        self.assertEqual(len(self.drafts()), 1)
        self.nothing_written()
        self.assert_value_absent(self.drafts()[-1], first)


if __name__ == "__main__":
    unittest.main()
