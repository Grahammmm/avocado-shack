"""HASS-HIKE-FLOW-1 tests: a hike request ends in a draft, and a short answer is joined to the request it answers.

Conversation runs on the H02 throwaway repo with the PRODUCTION op registry (hass.ops.hikes) and an injected clock; the
interpreter is a scripted stand-in that returns what a correct model returns for each text (no model, no socket). What the
real model does with these texts is measured by the corpus rows tagged hike-flow (nl_eval --live, operator only) and
reported in reports/hass/HIKE-FLOW-1.md. Every test also checks the rule that did not change: an unconfirmed message never
writes anything (no writer commit, no approval row).
Run: python3 -m unittest hass.tests.test_hike_flow -v
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

from hass import conversation, editor as editor_mod, interpreter_prompt, nl_eval, nl_prep
from hass.interpreter_local import LocalInterpreter
from hass.tests.test_claims import P1
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_nl_prep import URL, tiny

LIVE1 = "add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water"
LIVE2 = "Fiscalini Ranch"
LIVE3 = "create a new hike on Fiscalini Ranch this Saturday at 8am, easy, bring water"
OPEN1 = "add a hike Saturday, Mill Creek trailhead, easy, bring water"  # no time: the one missing field
SATURDAY = "2026-11-07"  # T0 is Monday 2026-11-02
MILL = {"title": "Mill Creek hike", "date": SATURDAY, "time": "08:00", "meetingPoint": "Mill Creek trailhead", "rsvpEnabled": False,
        "difficulty": "easy", "bring": "Water"}
FISC = {"title": "Fiscalini Ranch hike", "date": SATURDAY, "time": "08:00", "meetingPoint": "Fiscalini Ranch", "rsvpEnabled": False,
        "difficulty": "easy", "bring": "Water", "trailId": "idea-fiscalini-bluff"}
Q_TIME = {"question": "What time on Saturday for the Mill Creek hike?"}
Q_PLACE = {"question": "Where should we meet for the Saturday hike?"}


class Clocked(conversation.Editor):
    """The production registry, with the editor's clock the test clock (a fixed Saturday must not go stale)."""

    def __init__(self, state, clock):
        super().__init__(state)
        self.clock = clock

    def prepare(self, ops):
        return editor_mod.prepare({"ops": ops}, state=self.state, registry=self.registry, now=self.clock())

    def apply(self, change_id, draft_hash):
        return editor_mod.apply(change_id, draft_hash, state=self.state, registry=self.registry, now=self.clock())


class Scripted(conversation.FixtureInterpreter):
    def __init__(self, mapping, asked):
        super().__init__(mapping)
        self.asked = asked

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        self.asked.append((text, recent))
        return super().interpret(text, pending)


class FlowCase(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.asked = []
        self.interp = Scripted({
            LIVE1: _ops(("hike.create", MILL)), LIVE3: _ops(("hike.create", FISC)), OPEN1: Q_TIME, "8am": _ops(("hike.create", MILL)),
            "add a hike this Saturday at 8am, easy, bring water": Q_PLACE, "Mill Creek trailhead": _ops(("hike.create", MILL)),
            "Saturday": {"question": "What time on Saturday for the beach hike?"}, "9am": _ops(("hike.create", {**MILL, "time": "09:00"})),
            LIVE2: {"question": "Do you want a new hike on Fiscalini Ranch? What day and time?"}}, self.asked)
        self.editor = Clocked(self.repo.state, lambda: self.now)
        self.conv = self.open()

    def open_asks(self):  # SKILLS-FW-3: the one open-request store (was the open_asks table)
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'open_requests'").fetchone(): return []
        return [json.loads(r["texts_json"]) for r in self.conv.db.execute("SELECT texts_json FROM open_requests")]

    def nothing_written(self):
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0], 0)


class CompleteRequestTests(FlowCase):
    """The live texts of 2026-11-08: a complete request is a draft the owner can approve, not a question."""

    def test_the_first_live_text_is_a_draft_with_every_field_and_an_unlisted_place(self):
        draft, reply = self.propose(LIVE1)
        for line in ("the title: Mill Creek hike", "the meeting place: Mill Creek trailhead", "the start time: Saturday, Nov 7 at 8 am", "how hard it is: easy",
                     "what to bring: Water", "whether guests can sign up: no"):
            self.assertIn(line, reply)
        self.assertNotIn("trailId", reply)  # a place that is not a route idea is plain text, never forced onto a listed trail
        self.assertNotIn("capacity", reply)
        self.assertIn("Reply yes to save it", reply)
        self.assertEqual(draft["state"], "proposed")
        self.nothing_written()

    def test_create_a_new_hike_on_a_route_idea_is_a_new_hike_with_the_route_linked(self):
        draft, reply = self.propose(LIVE3)
        self.assertIn("A new hike: Fiscalini Ranch hike", reply)
        self.assertIn("the route idea: Fiscalini Ranch", reply)  # HASS-CHAT-1: a route link is the route's name, never its id
        self.assertIn("what to bring: Water", reply)
        self.nothing_written()

    def test_yes_applies_it_and_only_yes(self):
        draft, _ = self.propose(LIVE1)
        self.nothing_written()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        events = json.loads((self.repo.wt / "hass" / "content" / "community.json").read_text("utf-8"))["events"]
        self.assertEqual([(e["title"], e["meetingPoint"], e["difficulty"]) for e in events], [("Mill Creek hike", "Mill Creek trailhead", "easy")])


class AnswerAfterQuestionTests(FlowCase):
    def test_the_answer_goes_to_the_interpreter_with_the_request_it_answers(self):
        self.assertEqual(self.say(OPEN1), "question")
        self.assertEqual(self.replies(), [Q_TIME["question"]])
        self.assertEqual(self.asked[-1], (OPEN1, None))
        self.assertEqual(self.open_asks(), [[OPEN1]])
        self.now += timedelta(minutes=2)
        draft, reply = self.propose("8am")
        self.assertEqual(self.asked[-1], ("8am", {"question": Q_TIME["question"], "earlier": [OPEN1]}))
        self.assertIn("the meeting place: Mill Creek trailhead", reply)
        self.assertEqual(self.open_asks(), [])  # the draft closed the open request: no owner text is kept
        self.nothing_written()

    def test_a_missing_place_is_asked_and_the_answer_completes_the_request(self):
        first = "add a hike this Saturday at 8am, easy, bring water"
        self.assertEqual(self.say(first), "question")
        self.replies()
        self.assertEqual(self.say("Mill Creek trailhead"), "proposed")
        self.assertEqual(self.asked[-1][1], {"question": Q_PLACE["question"], "earlier": [first]})
        self.nothing_written()

    def test_two_questions_in_a_row_keep_the_whole_request_oldest_first(self):
        beach = "put a hike on the site for sometime next weekend, somewhere at the beach"
        self.interp.mapping[beach] = {"question": "Which day next weekend?"}
        self.assertEqual(self.say(beach), "question")
        self.assertEqual(self.say("Saturday"), "question")
        self.assertEqual(self.asked[-1][1], {"question": "Which day next weekend?", "earlier": [beach]})
        self.assertEqual(self.say("9am"), "proposed")
        self.assertEqual(self.asked[-1][1], {"question": "What time on Saturday for the beach hike?", "earlier": [beach, "Saturday"]})
        self.assertEqual(self.open_asks(), [])
        self.nothing_written()

    def test_the_open_request_is_forgotten_after_the_ttl(self):
        self.assertEqual(self.say(OPEN1), "question")
        self.now += timedelta(minutes=conversation.RECENT_MINUTES + 1)
        self.say("8am")
        self.assertIsNone(self.asked[-1][1])
        self.assertEqual(self.open_asks(), [])  # the old text is deleted, not just ignored
        self.nothing_written()

    def test_within_the_ttl_it_is_still_joined(self):
        self.say(OPEN1)
        self.now += timedelta(minutes=conversation.RECENT_MINUTES - 1)
        self.say("8am")
        self.assertEqual(self.asked[-1][1]["earlier"], [OPEN1])

    def test_a_command_between_ends_it_and_the_text_is_deleted_at_the_ttl(self):
        self.say(OPEN1)
        self.assertEqual(self.say("status"), "status")
        self.say("8am")
        self.assertIsNone(self.asked[-1][1])
        self.now += timedelta(minutes=conversation.RECENT_MINUTES + 1)
        self.say("status")
        self.assertEqual(self.open_asks(), [])

    def test_no_drops_the_open_request(self):
        self.say(OPEN1)
        self.say("no")
        self.assertEqual(self.open_asks(), [])
        self.say("8am")
        self.assertIsNone(self.asked[-1][1])
        self.nothing_written()

    def test_what_is_kept_is_bounded(self):
        for n in range(conversation.ASK_TURNS + 3):
            self.interp.mapping[f"more {n}"] = {"question": f"Q{n}?"}
            self.say(f"more {n}")
        [kept] = self.open_asks()
        self.assertEqual(kept, [f"more {n}" for n in range(3, conversation.ASK_TURNS + 3)])
        long = "x" * 3000
        self.interp.mapping[long] = {"question": "Which?"}
        self.say(long)
        [kept] = self.open_asks()
        self.assertTrue(all(len(t) <= conversation.ASK_TEXT_CUT for t in kept))
        self.assertTrue(len(kept) == 1 or sum(map(len, kept)) <= conversation.ASK_CHARS)

    def test_a_missing_or_broken_store_is_no_earlier_text_not_a_crash(self):
        self.say(OPEN1)
        self.conv.db.execute("DROP TABLE open_requests")  # SKILLS-FW-3: the store is open_requests now
        self.assertEqual(self.conv._recent_question(self.now), {"question": Q_TIME["question"]})
        self.conv.db.execute("CREATE TABLE open_requests(request_id INTEGER PRIMARY KEY, provider_id TEXT NOT NULL, owner TEXT NOT NULL,"
                             " state TEXT NOT NULL, texts_json TEXT NOT NULL, expires_at TEXT NOT NULL)")
        far = (self.now + timedelta(hours=1)).isoformat()
        self.conv.db.execute("INSERT INTO open_requests VALUES (1, ?, ?, 'open', 'not json', ?)",
                             (self.conv.db.execute("SELECT provider_id FROM messages").fetchone()[0], self.conv.settings["ownerChat"], far))
        self.assertEqual(self.conv._recent_question(self.now), {"question": Q_TIME["question"]})

    def test_a_claim_the_owner_made_in_the_first_text_still_counts_for_the_answer(self):
        first = "make the eggs description cage-free eggs, which product?"
        self.interp.mapping[first] = {"question": "Which product do you mean?"}
        self.interp.mapping["the eggs"] = _ops(("product.edit", {"id": P1, "description": "Cage-free eggs"}))
        self.say(first)
        self.assertEqual(self.say("the eggs"), "proposed")  # joined: the owner did say cage-free
        self.nothing_written()
        alone = Scripted({"the eggs": self.interp.mapping["the eggs"]}, self.asked)
        self.conv.interpreter = alone
        self.now += timedelta(minutes=conversation.RECENT_MINUTES + 1)
        self.assertEqual(self.say("the eggs", pid="alone"), "claim-question")  # alone it is still an unstated claim


class EditAndCancelTests(FlowCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping.update({
            "push the Mill Creek hike to 10am": _ops(("hike.update", {"id": "hike-2026-11-07-mill-creek-hike", "time": "10:00"})),
            "cancel the Mill Creek hike, it's going to rain": _ops(("hike.cancel", {"id": "hike-2026-11-07-mill-creek-hike", "note": "It's going to rain"}))})
        draft, _ = self.propose(LIVE1)
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.replies()
        self.base = self.count()

    def test_edit_a_hikes_time_is_a_one_line_draft(self):
        draft, reply = self.propose("push the Mill Creek hike to 10am")
        self.assertIn("Mill Creek hike (Saturday, Nov 7): rescheduled\nMill Creek hike (Saturday, Nov 7), the start time:\n  was: Saturday, Nov 7 at 8 am (Pacific time)\n  now: Saturday, Nov 7 at 10 am (Pacific time)", reply)
        self.assertEqual(self.commits(), 0)

    def test_cancel_a_hike_is_a_draft_with_the_note(self):
        draft, reply = self.propose("cancel the Mill Creek hike, it's going to rain")
        self.assertIn("Mill Creek hike (Saturday, Nov 7): cancelled", reply)
        self.assertNotIn("whether it shows", reply)
        self.assertIn("It's going to rain", reply)
        self.assertEqual(self.commits(), 0)


class RequestAndPromptTests(unittest.TestCase):
    def fake(self, seen):
        def transport(url, body, headers, timeout):
            seen.append(json.loads(body))
            return 200, json.dumps({"done": True, "message": {"content": json.dumps({"question": "ok"})}}).encode()
        return transport

    def make(self, seen):
        return LocalInterpreter(URL, "m", "SYSTEM", transport=self.fake(seen), hinter=nl_prep.make_hinter(tiny()),
                                clock=lambda: datetime(2026, 11, 9, 17, 40, tzinfo=timezone.utc))

    def user(self, seen):
        return json.loads(seen[-1]["messages"][1]["content"])

    def test_earlier_texts_go_out_with_the_question_and_the_hints_read_the_whole_request(self):
        seen = []
        self.make(seen).interpret("Cass Hill", [], recent={"question": "Which trail?", "earlier": ["add a hike Saturday at 8am, easy"]})
        user = self.user(seen)
        self.assertEqual(user["message"], "Cass Hill")
        self.assertEqual(user["recent"], {"question": "Which trail?", "earlier": ["add a hike Saturday at 8am, easy"]})
        self.assertEqual(user["hints"]["dates"][0]["next"], "2026-11-14")  # the day is in the first text, not in the answer
        self.assertEqual(user["hints"]["times"][0]["time"], "08:00")

    def test_bad_earlier_values_are_left_out(self):
        for bad in ("text", [], [1], ["ok", ""], ["a"] * 5, {"x": 1}):
            seen = []
            self.make(seen).interpret("8am", [], recent={"question": "When?", "earlier": bad})
            self.assertEqual(self.user(seen)["recent"], {"question": "When?"}, bad)

    def test_the_rules_say_adding_a_hike_is_a_draft_and_an_unlisted_place_is_text(self):
        rules = " ".join(interpreter_prompt.RULES)
        for phrase in ("is ALWAYS hike.create", "never a change to a listed hike", "as soon as the day, the time and one place are known",
                       "trailId is optional", "plain text for meetingPoint", "never ask which trail", "ONE short question",
                       'rsvpEnabled is false unless the owner talks about sign-ups', "never set capacity or noCapacityLimit unless the owner gave them",
                       '"earlier" lists the owner', "ONE request", "ignore \"recent\""):
            self.assertIn(phrase, rules)
        self.assertNotIn("Never make a route idea", rules)  # the old rule that made the model refuse a hike on a route idea

    def test_the_three_live_texts_and_the_flow_cases_are_in_the_corpus(self):
        rows = {r["text"] + json.dumps(r.get("recent")): r for r in nl_eval.load_corpus()}
        flow = [r for r in rows.values() if "hike-flow" in r.get("tags", [])]
        texts = {r["text"] for r in flow}
        for live in (LIVE1, LIVE2, LIVE3):
            self.assertIn(live, texts)
        tags = {t for r in flow for t in r["tags"]}
        for tag in ("answer", "edit-time", "cancel", "unknown-place", "route-idea"):
            self.assertIn(tag, tags)
        self.assertTrue(any(r.get("recent", {}).get("earlier") for r in flow))


if __name__ == "__main__":
    unittest.main()
