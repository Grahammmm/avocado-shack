"""SKILLS-FW-3 follow-up tests: the three optional hooks a skill module may offer the dispatcher, and the settings the plan sees.

* ``question(slot name, slots, ctx)``: the skill's own wording of the one question for a missing slot (the product's name, a saved
  maker offered as "same"); the slot's static ``ask`` stays the fallback.
* ``Refusal``-style errors (any exception with ``.reply`` and ``.kind``): said as they are. A ``question`` keeps the open request so
  the owner's short answer continues it; anything else closes it. An error with no sentence is still the generic failure.
* ``notes(skill name, slots, ctx)`` -> ``{say, set, warn}``: lines shown beside the draft, before the owner's yes.
* ``ctx.media_root`` / ``ctx.house_render``: the settings a plan reads to check a stored original.

Toy skills, a scripted interpreter, the production op registry: nothing is written before the owner's own ``yes <code>``.
Run: python3 -m unittest hass.tests.test_skill_dispatch_hooks -v
"""
import sys
import unittest

from hass import voice
from hass.skills import dispatch
from hass.skills.model import Slot
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_skill_dispatch import DESCRIBE, HIKE_ADD, LIVE1, MILL, SkillCase, registry_of, skill_reply, toy

OPEN = "add a hike Saturday, Mill Creek trailhead, easy"  # no time
SEEN = {}


class Stop(ValueError):
    """A plan that must stop: ``reply`` is the owner's sentence, ``kind`` is "question" or "refuse"."""

    def __init__(self, reply, kind="refuse", backlog=None):
        super().__init__(reply)
        self.reply, self.kind, self.backlog = reply, kind, backlog


def question(slot_name, slots, ctx):
    SEEN["question"] = (slot_name, dict(slots), type(ctx).__name__)
    if slot_name == "time":
        return f"What time does {slots.get('title', 'it')} start?"
    return None


def notes(name, slots, ctx):
    SEEN["notes"] = (name, dict(slots), ctx.media_root, ctx.house_render)
    return {"say": ["The meeting place is saved."], "set": ["I set: the hike to easy."], "warn": ["The photo is small."]}


def _plan(slots, ctx):
    if slots.get("title") == "Q":
        raise Stop("Which hike do you mean: Mill Creek or Fiscalini?", "question")
    if slots.get("title") == "R":
        raise Stop("That hike is cancelled, so nothing changed.")
    if slots.get("title") == "B":
        raise Stop("The website shows no prices.", "refuse", "price")
    if slots.get("title") == "X":
        raise RuntimeError("boom")
    return [{"op": "hike.create", "args": {"title": slots["title"], "date": slots["day"], "time": slots["time"],
                                           "meetingPoint": slots["place"], "rsvpEnabled": False}}]


_plan.__module__ = __name__  # the dispatcher finds a skill's hooks in the module that defines its plan
HOOKED = toy("hike.add", "add a hike", HIKE_ADD.slots, _plan)
PLAIN = None


class HookCase(SkillCase):
    SKILLS = (HOOKED,)

    def setUp(self):
        SEEN.clear()
        super().setUp()

    def reply_of(self, text):
        disposition = self.say(text)
        return disposition, self.replies()


class QuestionHook(HookCase):
    def test_the_skills_own_question_is_asked_with_the_slots_so_far(self):
        self.script(OPEN, skill_reply("hike.add", title="Mill Creek hike", place="Mill Creek trailhead", day="2026-11-07"))
        disposition, [asked] = self.reply_of(OPEN)
        self.assertEqual((disposition, asked), ("question", "What time does Mill Creek hike start?"))
        self.assertEqual(SEEN["question"][0], "time")
        self.assertEqual(SEEN["question"][1]["title"], "Mill Creek hike")
        self.assertEqual(SEEN["question"][2], "Ctx")
        self.assertEqual(self.live()["question"], asked)
        self.assertEqual(self.live()["asked_slot"], "time")
        self.nothing_written()

    def test_a_slot_the_hook_does_not_word_keeps_the_static_ask(self):
        self.script("add a hike at 8am", skill_reply("hike.add", title="Mill Creek hike", day="2026-11-07", time="08:00"))
        self.assertEqual(self.reply_of("add a hike at 8am"), ("question", [HIKE_ADD.slots[1].ask]))

    def test_a_hook_that_fails_falls_back_to_the_static_ask(self):
        self.script(OPEN, skill_reply("hike.add", title="Mill Creek hike", place="Mill Creek trailhead", day="2026-11-07"))
        original = sys.modules[__name__].question
        sys.modules[__name__].question = lambda *a: 1 / 0
        self.addCleanup(setattr, sys.modules[__name__], "question", original)
        self.assertEqual(self.reply_of(OPEN), ("question", [HIKE_ADD.slots[3].ask]))


class RefusalReplies(HookCase):
    def complete(self, title):
        self.script(LIVE1, skill_reply("hike.add", **{**MILL, "title": title}))
        return self.reply_of(LIVE1)

    def test_a_question_is_said_and_keeps_the_request_so_the_short_answer_continues_it(self):
        self.script("Mill Creek", skill_reply("hike.add", **MILL))
        disposition, [asked] = self.complete("Q")
        self.assertEqual((disposition, asked), ("question", "Which hike do you mean: Mill Creek or Fiscalini?"))
        live = self.live()
        self.assertEqual((live["skill"], live["question"], live["slots"]["title"]), ("hike.add", asked, "Q"))
        self.nothing_written()
        self.assertEqual(self.say("Mill Creek"), "proposed")  # his answer: the model reads it with the kept slots
        self.replies()
        self.assertEqual(self.commits(), 0)

    def test_the_same_question_three_times_closes_the_request(self):
        self.complete("Q")
        for _ in range(3):
            self.script(LIVE1, skill_reply("hike.add", **{**MILL, "title": "Q"}))
            self.say(LIVE1)
            self.replies()
        self.assertIsNone(self.live())

    def test_a_refusal_is_said_and_closes_the_request(self):
        disposition, [said] = self.complete("R")
        self.assertEqual((disposition, said), ("refused", "That hike is cancelled, so nothing changed."))
        self.assertIsNone(self.live())
        self.nothing_written()

    def test_a_refusal_with_a_backlog_reason_is_written_down(self):
        disposition, [said] = self.complete("B")
        self.assertEqual(disposition, "backlog")
        self.assertTrue(said.startswith("The website shows no prices."))
        self.nothing_written()

    def test_an_error_with_no_sentence_is_still_the_generic_failure(self):
        self.assertEqual(self.complete("X"), ("not-drafted", [dispatch.PLAN_FAILED]))
        self.assertIsNone(self.live())


class NotesHook(HookCase):
    def test_the_skills_notes_are_shown_before_the_yes(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        draft, reply = self.propose(LIVE1)
        lines = reply.split("\n")
        self.assertEqual(lines[:3], ["The meeting place is saved.", "I set: the hike to easy.", "The photo is small."])
        self.assertLess(reply.index("The photo is small."), reply.lower().index("yes"))
        self.assertEqual(voice.check(reply, long_ok=True), [])
        self.nothing_written()

    def test_a_skill_without_hooks_shows_what_it_did_before(self):
        self.registry = registry_of(toy("hike.add", "add a hike", HIKE_ADD.slots, lambda s, c: _plan(s, c)))
        sys.modules[__name__].notes, saved = None, sys.modules[__name__].notes
        self.addCleanup(setattr, sys.modules[__name__], "notes", saved)
        self.conv = self.open()
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        _, reply = self.propose(LIVE1)
        self.assertNotIn("The photo is small.", reply)

    def test_a_failing_hook_never_loses_the_draft(self):
        saved = sys.modules[__name__].notes
        sys.modules[__name__].notes = lambda *a: 1 / 0
        self.addCleanup(setattr, sys.modules[__name__], "notes", saved)
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        draft, _ = self.propose(LIVE1)
        self.assertEqual(draft["state"], "proposed")


class CallsHooks(HookCase):
    """RETURN items 1 and 2: several asks in one message get the same notes and refusals as one ask."""
    SKILLS = (HOOKED, DESCRIBE)
    TEXT = LIVE1 + " and change the bread"

    def calls(self, title):
        self.script(self.TEXT, {"calls": [{"skill": "hike.add", "slots": {**MILL, "title": title}},
                                          {"skill": "item.describe", "slots": {"product": "bread"}}], "revises": None})

    def test_a_complete_call_keeps_its_say_set_and_warn_lines_beside_the_combined_proposal(self):
        self.calls("Mill Creek hike")
        self.assertEqual(self.say(self.TEXT), "proposed")
        proposal, asked = self.replies()
        lines = proposal.split("\n")
        self.assertEqual(lines[:3], ["The meeting place is saved.", "I set: the hike to easy.", "The photo is small."])
        self.assertLess(proposal.index("The photo is small."), proposal.lower().index("yes"))
        self.assertEqual(voice.check(proposal, long_ok=True), [])
        self.assertEqual(SEEN["notes"][0], "hike.add")
        self.assertTrue(asked.startswith("Which one do you mean:"), asked)  # the other ask is still asked next
        self.assertEqual(self.live()["skill"], "item.describe")
        self.nothing_written()

    def test_a_refused_call_is_said_and_closed_while_the_other_asks_go_on(self):
        self.calls("R")
        self.assertEqual(self.say(self.TEXT), "question")
        said, asked = self.replies()
        self.assertEqual(said, "That hike is cancelled, so nothing changed.")
        self.assertTrue(asked.startswith("Which one do you mean:"), asked)  # not NOT_SURE: the other ask is the open request
        live = self.live()
        self.assertEqual((live["skill"], live["asked_slot"], live["calls"]), ("item.describe", "product", []))
        self.assertEqual([d for d in self.drafts() if d["state"] == "proposed"], [])
        self.nothing_written()

    def test_a_refused_call_beside_a_complete_one_is_said_before_the_proposal_of_the_other(self):
        self.script(self.TEXT, {"calls": [{"skill": "hike.add", "slots": {**MILL, "title": "R"}},
                                          {"skill": "hike.add", "slots": MILL}], "revises": None})
        self.assertEqual(self.say(self.TEXT), "proposed")
        said, proposal = self.replies()
        self.assertEqual(said, "That hike is cancelled, so nothing changed.")
        self.assertIn("The photo is small.", proposal)
        self.assertIn("Mill Creek hike", proposal)
        self.assertEqual(len([d for d in self.drafts() if d["state"] == "proposed"]), 1)
        self.nothing_written()

    def test_only_refused_calls_are_said_and_close_the_request(self):
        self.script(self.TEXT, {"calls": [{"skill": "hike.add", "slots": {**MILL, "title": "R"}},
                                          {"skill": "hike.add", "slots": {**MILL, "title": "B"}}], "revises": None})
        self.assertEqual(self.say(self.TEXT), "backlog")
        said, backlog = self.replies()
        self.assertEqual(said, "That hike is cancelled, so nothing changed.")
        self.assertTrue(backlog.startswith("The website shows no prices."), backlog)
        self.assertIn("I wrote it down as request #", backlog)
        self.assertIsNone(self.live())
        self.nothing_written()

    def test_a_refusal_alone_in_a_calls_reply_closes_the_request(self):
        self.script(self.TEXT, {"calls": [{"skill": "hike.add", "slots": {**MILL, "title": "R"}}], "revises": None})
        self.assertEqual(self.say(self.TEXT), "refused")
        self.assertEqual(self.replies(), ["That hike is cancelled, so nothing changed."])
        self.assertIsNone(self.live())

    def test_a_call_that_fails_without_a_sentence_is_the_generic_failure(self):
        self.script(self.TEXT, {"calls": [{"skill": "hike.add", "slots": {**MILL, "title": "X"}}], "revises": None})
        self.assertEqual(self.say(self.TEXT), "not-drafted")
        self.assertEqual(self.replies(), [dispatch.PLAN_FAILED])
        self.assertIsNone(self.live())

    def test_a_question_from_a_plan_is_still_the_one_asked_for_that_call(self):
        self.script(self.TEXT, {"calls": [{"skill": "hike.add", "slots": {**MILL, "title": "Q"}}], "revises": None})
        self.assertEqual(self.say(self.TEXT), "question")
        self.assertEqual(self.replies(), ["Which hike do you mean: Mill Creek or Fiscalini?"])
        self.assertEqual(self.live()["skill"], "hike.add")


class PlanContext(HookCase):
    def test_the_plan_sees_the_media_root_and_the_house_render_setting(self):
        self.set_settings({**SETTINGS, "skills": {"mode": self.MODE}, "mediaRoot": "/tmp/hook-media", "houseRender": True})
        self.conv = self.open()
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        self.propose(LIVE1)
        self.assertEqual(SEEN["notes"][2:], ("/tmp/hook-media", True))

    def test_both_default_to_nothing(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        self.propose(LIVE1)
        self.assertEqual(SEEN["notes"][2:], (None, False))


if __name__ == "__main__":
    unittest.main()
