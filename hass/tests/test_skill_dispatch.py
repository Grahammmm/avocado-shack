"""SKILLS-FW-3 tests: a skill reply from the interpreter becomes slots, a plan and an ordinary draft; the open request keeps what
was asked between turns (spec 2.6, 2.7).

Conversation runs on the H02 throwaway repo with the PRODUCTION op registry and an injected clock; the interpreter is a scripted
stand-in (no model, no socket) that returns what a correct model returns for each text. The skills are TOY skills defined here,
because the catalog skills are later cards; they exercise the same Skill/Slot model. Every test also checks the rule that never
changes: nothing is written before the owner's own `yes <code>` (no writer commit, no approval row).
Run: python3 -m unittest hass.tests.test_skill_dispatch -v
"""
import json
import unittest
from datetime import timedelta

from hass import conversation
from hass.skills import dispatch
from hass.skills.model import Registry, Skill, Slot, Trigger, Undo
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, STRANGER, ConversationTestCase
from hass.tests.test_hike_flow import Clocked, Scripted

SATURDAY = "2026-11-07"  # the test clock starts Monday 2026-11-02
LIVE1 = "add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water"
OPEN1 = "add a hike Saturday, Mill Creek trailhead, easy"  # no time: the one missing slot
FIRST = "add a hike this Saturday at 8am, easy, bring water"  # no place
LIVE3 = "create a new hike on Fiscalini Ranch this Saturday at 8am"


def _plan_hike(slots, ctx):
    args = {"title": slots["title"], "date": slots["day"], "time": slots["time"], "meetingPoint": slots["place"], "rsvpEnabled": False}
    if slots.get("difficulty"):
        args["difficulty"] = slots["difficulty"]
    return [{"op": "hike.create", "args": args}]


def _plan_describe(slots, ctx):
    return [{"op": "product.edit", "args": {"id": slots["product"], "description": slots["description"]}}]


def toy(name, label, slots, plan, **kw):
    fields = dict(name=name, label=label, summary="A toy skill for the dispatch tests.", triggers=(Trigger("toy"),), slots=slots,
                  rules=(), plan=plan, edits=(("hass/content/community.json", "events"),), side_effects=("none",),
                  preview="hike", approval="owner-yes", live_class="chat-live", undo=Undo("revert", "none"), refuse=(),
                  cases="hass/tests/fixtures/skills/toy/%s.jsonl" % name, version=1)
    fields.update(kw)
    return Skill(**fields)


HIKE_ADD = toy("hike.add", "add a hike", (
    Slot("title", "text", True, ask="What is the hike called?", limit=("event", "title")),
    Slot("place", "text", True, ask="Where should we meet?", owner_words=True),
    Slot("day", "day", True, ask="Which day is the hike?"),
    Slot("time", "clock", True, ask="What time does it start?"),
    Slot("difficulty", "text", False, owner_words=True)), _plan_hike)
DESCRIBE = toy("item.describe", "change an item's description", (
    Slot("product", "product_ref", True, ask="Which product?"),
    Slot("description", "text", True, ask="What should it say?", owner_words=True)), _plan_describe,
    edits=(("hass/content/products.json", "products[id].description"),), preview="product:x")
PHOTO_ITEM = toy("item.picture", "put this photo on an item", (
    Slot("product", "product_ref", True, ask="Which product is it?"),
    Slot("photo", "attachment", True, from_attachment=True)),
    # a toy plan: the editor needs a stored original for a real set_photo; here the photo slot only has to arrive filled
    lambda s, c: [{"op": "hike.create", "args": {"title": "Photo " + s["photo"][:4], "date": "2026-11-07", "time": "09:00",
                                                  "meetingPoint": "Front door", "rsvpEnabled": False}}], preview="picture")


def registry_of(*skills):
    return Registry(skills={s.name: s for s in skills})


def skill_reply(name, revises=None, **slots):
    return {"skill": name, "slots": slots, "revises": revises}


MILL = dict(title="Mill Creek hike", place="Mill Creek trailhead", day=SATURDAY, time="08:00", difficulty="easy")


class SkillCase(ConversationTestCase):
    MODE = "both"
    SKILLS = (HIKE_ADD, DESCRIBE)

    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "skills": {"mode": self.MODE}})
        self.asked = []
        self.interp = Scripted({}, self.asked)
        self.editor = Clocked(self.repo.state, lambda: self.now)
        self.registry = registry_of(*self.SKILLS)
        self.conv = self.open()

    def open(self, ed=None):
        return conversation.Conversation(str(self.repo.state), ed or self.editor, self.interp, lambda: self.now,
                                         skills=getattr(self, "registry", None))

    def script(self, text, reply):
        self.interp.mapping[text] = reply

    def nothing_written(self):
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)

    def live(self):
        return self.conv.requests.get(CHAT, self.now)

    def table(self, sql="SELECT * FROM open_requests"):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'open_requests'").fetchone(): return []
        return [dict(r) for r in self.conv.db.execute(sql)]


class CompleteRequestTests(SkillCase):
    def test_a_complete_hike_skill_reply_is_a_draft_with_every_slot_and_needs_the_owners_yes(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        draft, reply = self.propose(LIVE1)
        for line in ("A new hike: Mill Creek hike", "the meeting place: Mill Creek trailhead", "the start time: Saturday, Nov 7 at 8 am", "how hard it is: easy"):
            self.assertIn(line, reply)
        self.assertEqual(draft["state"], "proposed")
        self.assertEqual(self.live()["state"], "drafted")
        self.assertEqual(self.live()["draft_code"], draft["code"])
        self.nothing_written()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.live(), None)  # approved: the request is finished

    def test_a_slot_the_owner_did_not_say_is_left_off_and_listed(self):
        self.script(LIVE1, skill_reply("hike.add", **{**MILL, "difficulty": "strenuous"}))
        draft, reply = self.propose(LIVE1)
        self.assertNotIn("strenuous", reply)
        self.assertNotIn("difficulty", json.loads(draft["ops_json"])[0]["args"])
        self.assertIn("Left off", reply)

    def test_defaults_are_shown_as_what_was_set(self):
        dispatch.DERIVERS["toy_difficulty"] = lambda slots, ctx: "easy"
        self.addCleanup(dispatch.DERIVERS.pop, "toy_difficulty")
        skill = toy("hike.add", "add a hike", (*HIKE_ADD.slots[:4], Slot("difficulty", "text", False, default="derive:toy_difficulty")), _plan_hike)
        self.registry = registry_of(skill)
        self.conv = self.open()
        self.script(LIVE1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "difficulty"}))
        _, reply = self.propose(LIVE1)
        self.assertIn("I set: difficulty: easy.", reply)


class MultiTurnTests(SkillCase):
    """The live hike texts of 2026-11-08 as multi-turn rows: the answer is joined to what it answers."""

    def test_the_missing_time_is_asked_once_and_the_short_answer_is_read_by_code_without_the_model(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.assertEqual(self.say(OPEN1), "question")
        self.assertEqual(self.replies(), ["What time does it start?"])
        req = self.live()
        self.assertEqual((req["skill"], req["asked_slot"], req["texts"]), ("hike.add", "time", [OPEN1]))
        self.assertEqual(len(self.asked), 1)
        self.now += timedelta(minutes=2)
        draft, reply = self.propose("8am")
        self.assertEqual(len(self.asked), 1)  # no second model call: a clock answer to a clock slot
        self.assertIn("the meeting place: Mill Creek trailhead", reply)
        self.assertEqual(json.loads(draft["ops_json"])[0]["args"]["time"], "08:00")
        self.nothing_written()

    def test_a_text_answer_goes_to_the_model_with_the_whole_request_and_is_merged_by_code(self):
        self.script(FIRST, skill_reply("hike.add", title="Fiscalini Ranch hike", day=SATURDAY, time="08:00", difficulty="easy"))
        self.assertEqual(self.say(FIRST), "question")
        self.assertEqual(self.replies(), ["Where should we meet?"])
        self.script("Fiscalini Ranch", skill_reply("hike.add", place="Fiscalini Ranch"))
        self.assertEqual(self.say("Fiscalini Ranch"), "proposed")
        text, recent = self.asked[-1]
        self.assertEqual((text, recent["skill"], recent["asked_slot"], recent["earlier"]), ("Fiscalini Ranch", "hike.add", "place", [FIRST]))
        self.assertEqual(recent["slots"]["title"], "Fiscalini Ranch hike")
        self.assertEqual(recent["question"], "Where should we meet?")
        self.nothing_written()

    def test_the_owners_earlier_words_count_for_the_owner_words_check_of_a_later_answer(self):
        first = "add a hike Saturday at 8am, called Wilson hike, it is moderate"
        self.script(first, skill_reply("hike.add", title="Wilson hike", day=SATURDAY, time="08:00", difficulty="moderate"))
        self.say(first)
        self.script("the Wilson trailhead", skill_reply("hike.add", place="Wilson trailhead"))
        self.assertEqual(self.say("the Wilson trailhead"), "proposed")  # "wilson" was said in the joined texts; "trailhead" now

    def test_a_vague_value_the_owner_never_said_is_not_kept_as_a_place(self):
        self.script(FIRST, skill_reply("hike.add", title="Beach hike", place="Secret Cove", day=SATURDAY, time="08:00"))
        self.assertEqual(self.say(FIRST), "question")
        self.assertEqual(self.replies(), ["Where should we meet?"])  # "Secret Cove" is not in the owner's words
        self.assertNotIn("place", self.live()["slots"])


class MergeTests(SkillCase):
    def test_a_slot_that_cannot_be_used_is_asked_again_at_most_twice_then_the_request_is_written_down(self):
        self.script(FIRST, skill_reply("hike.add", title="Beach hike", day=SATURDAY, time="08:00"))
        self.say(FIRST)  # asks for the place (question 1)
        self.replies()
        for n in (2, 3):
            self.script(f"huh {n}", skill_reply("hike.add", place=None))
            self.assertEqual(self.say(f"huh {n}"), "question")
            self.assertEqual(self.replies(), ["Where should we meet?"])
        self.script("huh 4", skill_reply("hike.add", place=None))
        self.assertEqual(self.say("huh 4"), "backlog")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("I'm not getting this. Send it in one message, like: toy"), reply)
        self.assertEqual(self.live(), None)
        self.assertEqual(self.conv.db.execute("SELECT reason FROM backlog").fetchall()[0][0], "stuck")
        self.nothing_written()

    def test_an_unknown_slot_name_is_ignored_and_a_new_valid_value_replaces_an_old_one(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}, capacity=40))
        self.say(OPEN1)
        self.assertNotIn("capacity", self.live()["slots"])
        self.script("make that 10am and call it Mill Creek loop", skill_reply("hike.add", time="10:00", title="Mill Creek loop"))
        self.assertEqual(self.say("make that 10am and call it Mill Creek loop"), "proposed")
        args = json.loads(self.drafts()[-1]["ops_json"])[0]["args"]
        self.assertEqual((args["time"], args["title"]), ("10:00", "Mill Creek loop"))


class CheapAnswerTests(SkillCase):
    SKILLS = (HIKE_ADD, DESCRIBE)

    def ask_for_bread(self):
        self.script("make the bread say tasty", skill_reply("item.describe", product="bread", description="tasty"))
        self.assertEqual(self.say("make the bread say tasty"), "question")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("Which one do you mean:"), reply)
        self.assertEqual(len(self.live()["ask"]["ids"]), 2)

    def test_a_choice_by_number_fills_the_product_without_the_model(self):
        self.ask_for_bread()
        calls = len(self.asked)
        self.assertEqual(self.say("2"), "proposed")
        self.assertEqual(len(self.asked), calls)
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"])[0]["args"]["id"], "photo-product-122")
        self.nothing_written()

    def test_a_choice_by_name_fills_the_product_and_an_unclear_one_goes_to_the_model(self):
        self.ask_for_bread()
        calls = len(self.asked)
        self.script("the rye one", skill_reply("item.describe", product="Rye bread"))
        self.assertEqual(self.say("the rye one"), "proposed")
        self.assertEqual(len(self.asked), calls)
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"])[0]["args"]["id"], "photo-product-122")

    def test_a_long_answer_is_never_read_by_code(self):
        self.ask_for_bread()
        calls = len(self.asked)
        long_answer = "the second one please, I think that is the right one, sorry for the confusion earlier today"
        self.script(long_answer, skill_reply("item.describe", product="Rye bread"))
        self.say(long_answer)
        self.assertEqual(len(self.asked), calls + 1)


class SeveralItemsTests(SkillCase):
    def test_complete_calls_make_one_draft_and_the_incomplete_one_is_asked_next(self):
        text = "add the Mill Creek hike Saturday 8am at Mill Creek trailhead and change the bread"
        self.script(text, {"calls": [
            {"skill": "hike.add", "slots": {k: v for k, v in MILL.items() if k != "difficulty"}},
            {"skill": "item.describe", "slots": {"product": "bread"}}], "revises": None})
        self.assertEqual(self.say(text), "proposed")
        replies = self.replies()
        self.assertEqual(len(replies), 2)
        self.assertIn("Reply yes to save it", replies[0])
        self.assertTrue(replies[1].startswith("Which one do you mean:"), replies[1])
        self.assertEqual(len([d for d in self.drafts() if d["state"] == "proposed"]), 1)
        req = self.live()
        self.assertEqual((req["skill"], req["asked_slot"]), ("item.describe", "product"))
        self.nothing_written()
        self.assertEqual(self.say("yes"), "approved")  # the draft can be approved while the next question waits

    def test_two_incomplete_calls_are_asked_and_drafted_in_sequence(self):
        text = "add the Mill Creek hike at Mill Creek trailhead and the Fiscalini Ranch hike at Fiscalini parking lot Saturday, easy"
        no_time = {k: v for k, v in MILL.items() if k != "time"}
        fisc = {**no_time, "title": "Fiscalini Ranch hike", "place": "Fiscalini parking lot"}
        self.script(text, {"calls": [{"skill": "hike.add", "slots": no_time}, {"skill": "hike.add", "slots": fisc}], "revises": None})
        self.assertEqual(self.say(text), "question")
        self.assertEqual(self.replies(), ["What time does it start?"])
        self.assertEqual(len(self.live()["calls"]), 1)  # the second call waits in the store
        self.now += timedelta(minutes=1)
        self.assertEqual(self.say("8am"), "proposed")
        replies = self.replies()
        self.assertIn("Mill Creek hike", replies[0])
        self.assertEqual(replies[-1], "What time does it start?")  # the queued call is asked next
        req = self.live()
        self.assertEqual((req["skill"], req["slots"]["title"], req["calls"]), ("hike.add", "Fiscalini Ranch hike", []))
        self.now += timedelta(minutes=1)
        self.conv = self.open()  # a restart between the two answers keeps the queue
        self.assertEqual(self.say("9am"), "proposed")
        self.assertIn("Fiscalini Ranch hike", self.replies()[0])
        self.assertEqual(len([d for d in self.drafts() if d["state"] == "proposed"]), 2)
        self.nothing_written()

    def test_more_than_the_limit_of_calls_is_not_a_skill_reply(self):
        many = {"calls": [{"skill": "hike.add", "slots": {}}] * (dispatch.MAX_CALLS + 1), "revises": None}
        self.assertIsNone(dispatch.checked(many))


class NoneAndUnknownTests(SkillCase):
    def test_none_is_written_down_and_changes_nothing(self):
        self.script("order eggs from the farm", {"skill": "none", "summary": "order eggs from the farm"})
        self.assertEqual(self.say("order eggs from the farm"), "backlog")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("I can't do that yet. I wrote it down as request #1."), reply)
        self.assertEqual(self.say("backlog"), "backlog")
        self.assertIn("1. Nov 2 - order eggs from the farm", self.replies()[0])
        self.nothing_written()

    def test_an_unknown_skill_name_is_written_down_too(self):
        self.script("do the thing", skill_reply("made.up", x=1))
        self.assertEqual(self.say("do the thing"), "backlog")
        self.assertEqual(self.conv.db.execute("SELECT reason FROM backlog").fetchone()[0], "unknown-skill")

    def test_forget_backlog_removes_one_row_and_only_that_row(self):
        for n in (1, 2):
            self.script(f"ask {n}", {"skill": "none", "summary": f"ask {n}"})
            self.say(f"ask {n}")
        self.replies()
        self.assertEqual(self.say("forget backlog.1"), "backlog-forgot")
        self.assertEqual(self.replies(), ["Done. I took that one off the list."])
        self.assertEqual([r[0] for r in self.conv.db.execute("SELECT id FROM backlog")], [2])
        self.assertEqual(self.say("forget backlog.1"), "backlog-none")
        self.assertEqual(self.say("forget backlog.7"), "backlog-none")


class ReviseAndTopicTests(SkillCase):
    def test_a_correction_of_the_same_skill_revises_the_draft_it_made(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        first, _ = self.propose(LIVE1)
        self.now += timedelta(minutes=1)
        self.script("make that 10am", skill_reply("hike.add", time="10:00"))
        self.assertEqual(self.say("make that 10am"), "proposed")
        states = {d["code"]: d["state"] for d in self.drafts()}
        self.assertEqual(states[first["code"]], "rejected")
        self.assertEqual(sum(1 for s in states.values() if s == "proposed"), 1)
        self.nothing_written()

    def test_a_different_complete_request_supersedes_the_open_one_and_status_says_so(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.replies()
        self.script("make the honey say Big Sur honey", skill_reply("item.describe", product="Big Sur Honey Company honey", description="Big Sur honey"))
        self.assertEqual(self.say("make the honey say Big Sur honey"), "proposed")
        old = self.table("SELECT state, skill FROM open_requests WHERE skill = 'hike.add'")
        self.assertEqual([r["state"] for r in old], ["superseded"])
        self.replies()
        self.say("status")
        self.assertIn("Replaced: add a hike", self.replies()[0])

    def test_no_cancels_the_open_request(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.replies()
        self.assertEqual(self.say("no"), "no-target")
        self.assertEqual(self.live(), None)
        self.script("8am", skill_reply("hike.add", time="08:00"))
        self.assertEqual(self.say("8am"), "question")  # starts over: nothing of the cancelled request is left to join
        self.assertEqual(self.live()["slots"], {"time": "08:00"})

    def test_a_cancel_reply_drops_the_request(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.script("scratch that, never mind", {"cancel": True})
        self.assertEqual(self.say("scratch that, never mind"), "cancelled")
        self.assertEqual(self.live(), None)


class StatusTests(SkillCase):
    def test_status_names_the_open_request_in_plain_words(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.replies()
        self.say("status")
        self.assertIn("Open: add a hike, waiting for the time", self.replies()[0])

    def test_status_with_nothing_open_has_no_open_line(self):
        self.say("status")
        self.assertNotIn("Open:", self.replies()[0])


class PhotoTests(SkillCase):
    """Spec 2.7: the photo of a message joins the open request (the store side; the fetch is _photo's, unchanged)."""
    SKILLS = (HIKE_ADD, PHOTO_ITEM)
    SHA = "a" * 64

    def test_a_photo_fills_the_asked_attachment_slot_and_the_request_becomes_a_draft(self):
        self.script("this is for the jam", skill_reply("item.picture", product="Cal Poly strawberry jam"))
        self.assertEqual(self.say("this is for the jam"), "question")  # asks for the photo (the attachment slot)
        self.assertEqual(self.live()["asked_slot"], "photo")
        photo = conversation.Inbound("p2", CHAT, OWNER, "", False, "new", self.now.isoformat(), 1)
        self.assertEqual(self.conv.dispatch.photo(photo, self.now, self.SHA, ""), "proposed")
        self.assertEqual(self.live()["state"], "drafted")
        self.assertEqual(self.live()["slots"]["photo"], self.SHA)
        self.assertEqual(self.live()["attachments"], [self.SHA])

    def test_only_photo_skills_are_offered_for_a_photo_with_no_request(self):
        names = [s.name for s in self.conv.dispatch.photo_skills()]
        self.assertEqual(names, ["item.picture"])

    def test_a_photo_for_a_skill_without_an_attachment_slot_is_asked_about(self):
        how, req = self.conv.requests.bind_attachment(CHAT, "p1", self.SHA, self.now, self.registry)
        self.assertEqual(how, "opened")
        self.script("add a hike", skill_reply("hike.add", title="x"))
        self.assertEqual(self.say("add a hike"), "question")
        self.assertIn("A photo goes with put this photo on an item", self.replies()[0])


class ModeTests(SkillCase):
    MODE = "ops-only"

    def test_ops_only_reads_a_skill_reply_as_unreadable_exactly_as_before_and_makes_no_skill_state(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        self.assertEqual(self.say(LIVE1), "unsupported")
        self.assertEqual(self.replies(), [conversation.UNREADABLE["unsupported"]])
        self.assertEqual(self.table(), [])
        self.assertIsNone(self.conv.dispatch)
        self.nothing_written()

    def test_a_bad_mode_refuses_to_start(self):
        self.set_settings({**SETTINGS, "skills": {"mode": "sometimes"}})
        with self.assertRaises(conversation.ConfigError):
            self.open()
        self.set_settings({**SETTINGS, "houseRender": "yes"})
        with self.assertRaises(conversation.ConfigError):
            self.open()

    def test_the_modes_and_the_house_render_flag_are_read_from_the_host_settings(self):
        self.set_settings({**SETTINGS, "skills": {"mode": "skills-first"}, "houseRender": True})
        conv = self.open()
        self.assertEqual((conv.settings["skillsMode"], conv.settings["houseRender"]), ("skills-first", True))
        self.set_settings(SETTINGS)
        conv = self.open()
        self.assertEqual((conv.settings["skillsMode"], conv.settings["houseRender"]), ("ops-only", False))


class SkillsFirstTests(SkillCase):
    MODE = "skills-first"

    def test_raw_ops_for_something_a_skill_owns_are_not_taken(self):
        self.script("raw", {"ops": [{"op": "hike.create", "args": {"title": "x"}}], "revises": None})
        self.assertEqual(self.say("raw"), "unsupported")
        self.nothing_written()

    def test_raw_ops_nobody_owns_still_work(self):
        from hass.tests.test_conversation import _ops
        self.registry = registry_of(HIKE_ADD)  # no skill owns the product ops
        self.conv = self.open()
        self.script("hours", _ops(("product.edit", {"id": "photo-product-001", "description": "Ripe and creamy."})))
        self.assertEqual(self.say("hours"), "proposed")


class OnlyTheOwnerTests(SkillCase):
    def test_a_stranger_or_another_chat_neither_opens_nor_reads_nor_closes_a_request(self):
        self.script(OPEN1, skill_reply("hike.add", **{k: v for k, v in MILL.items() if k != "time"}))
        self.say(OPEN1)
        self.replies()
        before = self.table()
        self.script("8am", skill_reply("hike.add", time="08:00"))
        self.assertEqual(self.say("8am", sender=STRANGER), "ignored")
        self.assertEqual(self.say("8am", chat="chat-fixture-group"), "ignored")
        self.assertEqual(self.say("no", sender=STRANGER), "ignored")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.table(), before)
        self.assertEqual(len(self.asked), 1)  # the model was never asked about them
        self.assertIsNone(self.conv.requests.get("someone-else", self.now))


if __name__ == "__main__":
    unittest.main()


class AgreementTests(SkillCase):
    """The routing agreement (spec 2.5) uses the FW-2 router contract: candidates(text, hints, open_request, attachment, skills)."""

    def fake_router(self, found):
        import sys
        import types
        seen = []
        mod = types.ModuleType("hass.skills.router")

        def candidates(text, hints=None, open_request=None, attachment=None, skills=()):
            seen.append({"hints": hints, "skills": skills})
            return found if skills else []
        mod.candidates = candidates
        old = sys.modules.get("hass.skills.router")
        sys.modules["hass.skills.router"] = mod
        self.addCleanup(lambda: sys.modules.pop("hass.skills.router", None) if old is None else sys.modules.__setitem__("hass.skills.router", old))
        return seen

    def test_the_registry_is_passed_and_a_near_tie_asks_which_task(self):
        seen = self.fake_router([("item.describe", 4.0), ("hike.add", 3.8)])
        self.script(OPEN1, skill_reply("hike.add", **MILL))
        self.assertEqual(self.say(OPEN1), "question")
        self.assertIs(seen[0]["skills"], self.registry)
        self.assertIsInstance(seen[0]["hints"], dict)
        self.assertEqual(self.replies(), ["Do you want to add a hike, or change an item's description?"])
        self.nothing_written()

    def test_a_near_tie_asks_even_when_the_model_picked_the_leader(self):
        self.fake_router([("hike.add", 4.0), ("item.describe", 3.8)])
        self.script(OPEN1, skill_reply("hike.add", **MILL))
        self.assertEqual(self.say(OPEN1), "question")
        self.assertEqual(self.replies(), ["Do you want to add a hike, or change an item's description?"])
        self.nothing_written()

    def test_the_ten_percent_boundary_for_the_leading_pair(self):
        self.fake_router([("hike.add", 4.4), ("item.describe", 4.0)])  # exactly 10%: tied
        self.script(OPEN1, skill_reply("hike.add", **MILL))
        self.assertEqual(self.say(OPEN1), "question")

    def test_a_lead_over_ten_percent_goes_on_to_the_draft(self):
        self.fake_router([("hike.add", 4.6), ("item.describe", 4.0)])
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        draft, _ = self.propose(LIVE1)
        self.assertEqual(draft["state"], "proposed")

    def test_a_clear_agreement_goes_on_to_the_draft(self):
        self.fake_router([("hike.add", 5.0), ("item.describe", 1.0)])
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        draft, _ = self.propose(LIVE1)
        self.assertEqual(draft["state"], "proposed")
