"""SKILLS-FW-2: the skill router and the skill reply check. Offline, no model, no clock; the backlog is in memory."""

import sqlite3
import unittest
from datetime import datetime, timezone

from hass import interpret_check
from hass.skills import backlog as backlog_mod
from hass.skills import model, router


def _skill(name, label, examples, slots=None, **over):
    base = dict(
        name=name, label=label, summary=f"{label}.",
        triggers=tuple(model.Trigger(t) for t in examples),
        slots=slots if slots is not None else (model.Slot("what", "text", True, ask="Which one?"),),
        rules=(), plan=lambda s, c: [], edits=(), side_effects=(), preview="none", approval="owner-yes",
        live_class="chat-live", undo=model.Undo("revert", "none"), refuse=(), cases="hass/tests/fixtures/skills/x/y.jsonl",
        version=1)
    base.update(over)
    return model.Skill(**base)


SKILLS = model.Registry({s.name: s for s in (
    _skill("stock.set", "change what's in stock",
           ["eggs are out", "got more honey in", "avocados limited today", "bread is gone", "peppers running low"]),
    _skill("hike.add", "add a hike",
           ["add a hike at cass hill on saturday", "new hike on the 29th", "schedule a group walk at the beach",
            "post a hike saturday morning", "put a hike on the calendar"]),
    _skill("item.hide", "hide an item",
           ["remove the strawberry jam", "hide the plums", "take the walnut oil off the site", "delete the dried figs",
            "pull the lemon curd from the shop"]),
    _skill("maker.add", "add a maker",
           ["add a new maker called hilltop farm", "we have a new supplier", "put a new maker on the makers page",
            "add the bakery as a maker", "a new farm joins us"]),
    _skill("shop.hours", "change the opening hours",
           ["change friday hours to 9 to 5", "we close early on saturday", "open late on thursday",
            "update the opening hours", "closed on monday now"]),
    _skill("social.item", "write a post",
           ["post the honey on instagram", "write a caption for the new bread", "draft a social post about the eggs",
            "make an instagram post for the plums", "write a facebook post for the farm bread"]),
)})
SKILLS_BY_SENTENCE = [
    ("eggs are sold out", "stock.set"), ("we got more honey in today", "stock.set"), ("avocados are limited", "stock.set"),
    ("the bread is gone", "stock.set"), ("peppers are running low", "stock.set"),
    ("add a hike at cass hill saturday", "hike.add"), ("a new hike on the 29th", "hike.add"),
    ("schedule a group walk on the beach", "hike.add"), ("post a hike for saturday morning", "hike.add"),
    ("put a hike on the calendar", "hike.add"),
    ("remove the strawberry jam", "item.hide"), ("hide the plums please", "item.hide"),
    ("take the walnut oil off the site", "item.hide"), ("delete the dried figs", "item.hide"),
    ("pull the lemon curd from the shop", "item.hide"),
    ("add a new maker called sunny acres", "maker.add"), ("we have a new supplier", "maker.add"),
    ("put a new maker on the makers page", "maker.add"), ("add the bakery as a maker", "maker.add"),
    ("a new farm joins us", "maker.add"),
    ("change friday hours to 10 to 4", "shop.hours"), ("we close early on saturday", "shop.hours"),
    ("open late on thursday", "shop.hours"), ("update the opening hours", "shop.hours"),
    ("closed on monday now", "shop.hours"),
    ("post the honey on instagram", "social.item"), ("write a caption for the new bread", "social.item"),
    ("draft a social post about the eggs", "social.item"), ("make an instagram post for the plums", "social.item"),
    ("write a facebook post for the farm bread", "social.item"),
]


def _backlog():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.row_factory = sqlite3.Row
    return backlog_mod.Backlog(db, lambda: datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc))


class CandidateTests(unittest.TestCase):
    def test_thirty_sentences_route_to_the_expected_skill(self):
        self.assertEqual(len(SKILLS_BY_SENTENCE), 30)
        for sentence, want in SKILLS_BY_SENTENCE:
            with self.subTest(sentence):
                ranked = router.candidates(sentence, skills=SKILLS)
                self.assertTrue(ranked and ranked[0][0] == want, ranked)
                self.assertLessEqual(len(ranked), 3)
                result = router.route({"skill": want, "slots": {"what": sentence}}, ranked, SKILLS, text=sentence)
                self.assertEqual(result.action, "run", sentence)
                self.assertEqual(result.calls, ((want, {"what": sentence}),))

    def test_same_input_same_ranking(self):
        a = router.candidates("remvoe the strawbery jam", skills=SKILLS)
        self.assertEqual(a, router.candidates("remvoe the strawbery jam", skills=SKILLS))
        self.assertEqual(a[0][0], "item.hide")

    def test_an_attachment_only_lets_skills_with_an_attachment_slot_compete(self):
        photo = _skill("item.picture", "replace a picture", ["new picture for the honey"],
                       slots=(model.Slot("photo", "attachment", True, ask="Which photo?"),))
        reg = model.Registry({**SKILLS.skills, photo.name: photo})
        ranked = router.candidates("hide the plums", attachment={"kind": "image"}, skills=reg)
        self.assertTrue(all(n == "item.picture" for n, _s in ranked))
        self.assertTrue(router.candidates("hide the plums", skills=reg))

    def test_an_open_request_raises_its_skill(self):
        plain = dict(router.candidates("saturday", skills=SKILLS))
        asked = dict(router.candidates("saturday", open_request={"skill": "hike.add"}, skills=SKILLS))
        self.assertGreater(asked["hike.add"], plain.get("hike.add", 0))

    def test_nothing_in_common_gives_no_candidate(self):
        self.assertEqual(router.candidates("xyzzy plugh", skills=SKILLS), [])
        self.assertEqual(router.candidates("hello", skills=model.Registry({})), [])


class RouteTests(unittest.TestCase):
    def test_none_goes_to_the_backlog_and_says_so_plainly(self):
        store = _backlog()
        text = "can you order more eggs from the farm"
        ranked = router.candidates(text, skills=SKILLS)
        result = router.route({"skill": "none", "summary": "order eggs from the farm"}, ranked, SKILLS, text=text, store=store)
        self.assertEqual(result.action, "backlog")
        self.assertEqual(result.reply, backlog_mod.CANT_DO)
        self.assertTrue(result.reply.startswith("I can't do that yet"))
        rows = store.rows(text=True)
        self.assertEqual([r["reason"] for r in rows], ["unknown-skill"])
        self.assertEqual(rows[0]["id"], result.backlog_id)
        self.assertEqual(rows[0]["text"], text)

    def test_an_unknown_skill_name_is_the_catch_all_not_a_guess(self):
        store = _backlog()
        result = router.route({"skill": "stock.teleport", "slots": {}}, [("stock.set", 3.0)], SKILLS, text="beam the eggs", store=store)
        self.assertEqual(result.action, "backlog")
        self.assertEqual(len(store.rows()), 1)

    def test_an_unknown_slot_is_one_question(self):
        reply = {"skill": "stock.set", "slots": {"colour": "red"}}
        result = router.route(reply, [("stock.set", 3.0)], SKILLS, text="eggs are out", store=_backlog())
        self.assertEqual(result.action, "question")
        self.assertEqual(result.reply.count("?"), 1)
        self.assertNotIn("colour", result.reply)

    def test_a_wrong_slot_type_is_one_question(self):
        reply = {"skill": "stock.set", "slots": {"what": 5}}
        self.assertEqual(router.route(reply, [("stock.set", 3.0)], SKILLS).action, "question")

    def test_a_price_in_a_slot_is_refused_in_site_words(self):
        reply = {"skill": "stock.set", "slots": {"what": "eggs $4"}}
        result = router.route(reply, [("stock.set", 3.0)], SKILLS)
        self.assertEqual(result.action, "question")
        self.assertEqual(result.calls, ())

    def test_a_price_only_message_gets_the_price_reply_and_a_price_row(self):
        store = _backlog()
        result = router.route({"skill": "none", "summary": "set honey to 5 dollars"}, [], SKILLS, text="honey is 5 dollars now",
                              hints={"price": [5]}, store=store)
        self.assertEqual(result.reply, interpret_check.PRICE_REPLY)
        self.assertEqual([r["reason"] for r in store.rows()], ["price"])

    def test_calls_run_together_and_a_revises_code_must_be_waiting(self):
        reply = {"calls": [{"skill": "stock.set", "slots": {"what": "eggs out"}}, {"skill": "item.hide", "slots": {"what": "plums"}}]}
        ranked = router.candidates("eggs are out and hide the plums", skills=SKILLS)
        result = router.route(reply, ranked, SKILLS, text="eggs are out and hide the plums")
        self.assertEqual(result.action, "run")
        self.assertEqual([n for n, _s in result.calls], ["stock.set", "item.hide"])
        bad = router.route({"skill": "stock.set", "slots": {}, "revises": "abc"}, [("stock.set", 3.0)], SKILLS, pending_codes=("xyz",))
        self.assertEqual(bad.action, "question")
        good = router.route({"skill": "stock.set", "slots": {}, "revises": "abc"}, [("stock.set", 3.0)], SKILLS, pending_codes=("abc",))
        self.assertEqual((good.action, good.revises), ("run", "abc"))

    def test_the_two_opinions_split_asks_the_owner_and_drafts_nothing(self):
        ranked = [("stock.set", 3.0), ("item.hide", 2.9)]
        result = router.route({"skill": "item.hide", "slots": {"what": "plums"}}, ranked, SKILLS)
        self.assertEqual(result.action, "ask")
        self.assertIn("change what's in stock", result.reply)
        self.assertIn("hide an item", result.reply)
        self.assertEqual(result.calls, ())

    def test_a_pick_outside_the_candidates_asks(self):
        result = router.route({"skill": "maker.add", "slots": {"what": "x"}}, [("stock.set", 3.0)], SKILLS)
        self.assertEqual(result.action, "ask")

    def test_no_candidate_and_no_slots_is_never_guessed(self):
        store = _backlog()
        result = router.route({"skill": "stock.set", "slots": {}}, [], SKILLS, text="mumble", store=store)
        self.assertEqual(result.action, "backlog")
        self.assertEqual(len(store.rows()), 1)

    def test_old_style_replies_pass_through(self):
        reply = {"ops": [{"op": "product.set", "args": {}}]}
        self.assertEqual(router.route(reply, [], SKILLS).action, "ops")
        self.assertEqual(router.route({"question": "Which one?"}, [], SKILLS).reply, "Which one?")
        self.assertEqual(router.route({"unsupported": "No."}, [], SKILLS).action, "unsupported")

    def test_an_unreadable_reply_is_asked_again_once_then_written_down(self):
        store = _backlog()
        self.assertEqual(router.route("garbage", [], SKILLS).action, "retry")
        self.assertEqual(router.route({"hello": 1}, [], SKILLS).action, "retry")
        again = router.route({"hello": 1}, [], SKILLS, text="hmm", store=store, retried=True)
        self.assertEqual(again.action, "backlog")
        self.assertEqual(len(store.rows()), 1)

    def test_a_backlog_skill_uses_its_own_fixed_reply(self):
        from hass.skills import backlog as b
        reg = model.Registry({**SKILLS.skills, "page.faq": b.PAGE_FAQ, "backlog.log": b.BACKLOG_LOG})
        store = _backlog()
        ranked = router.candidates("add an FAQ", skills=reg)
        result = router.route({"skill": "page.faq", "slots": {}}, ranked, reg, text="add an FAQ", store=store)
        self.assertEqual((result.action, result.reply), ("backlog", b.NO_FAQ))
        self.assertEqual([r["reason"] for r in store.rows()], ["unsupported-page"])

    def test_a_near_tie_asks_whichever_one_the_model_picked(self):
        ranked = [("stock.set", 3.0), ("item.hide", 2.9), ("maker.add", 1.0)]
        for name in ("stock.set", "item.hide", "maker.add"):
            result = router.route({"skill": name, "slots": {"what": "plums"}}, ranked, SKILLS, text="plums")
            self.assertEqual(result.action, "ask", name)
            self.assertEqual(result.calls, ())

    def test_a_multi_call_reply_must_settle_the_leading_near_tie(self):
        ranked = [("stock.set", 3.0), ("item.hide", 2.9), ("maker.add", 1.0)]
        stock = {"skill": "stock.set", "slots": {"what": "plums"}}
        for calls in (
            [stock, {"skill": "maker.add", "slots": {"what": "hilltop farm"}}],
            [stock, {"skill": "stock.set", "slots": {"what": "eggs"}}],
        ):
            result = router.route({"calls": calls}, ranked, SKILLS, text="plums and a maker")
            self.assertEqual(result.action, "ask", calls)
            self.assertEqual(result.calls, ())
            self.assertIn("change what's in stock", result.reply)
            self.assertIn("hide an item", result.reply)
        control = router.route({"calls": [stock, {"skill": "item.hide", "slots": {"what": "plums"}}]}, ranked, SKILLS, text="plums")
        self.assertEqual(control.action, "run")
        self.assertEqual([n for n, _s in control.calls], ["stock.set", "item.hide"])

    def test_a_per_call_revises_is_not_allowed(self):
        calls = [{"skill": "stock.set", "slots": {"what": "plums"}, "revises": "not-waiting"},
                 {"skill": "item.hide", "slots": {"what": "plums"}}]
        checked = interpret_check.check_skill({"calls": calls}, SKILLS, pending_codes=())
        self.assertIn("question", checked)
        self.assertIn("could not read that message as a change", checked["question"])
        ranked = [("stock.set", 3.0), ("item.hide", 2.0)]
        for pending in ((), ("not-waiting",)):  # even a waiting code is not honoured inside a call
            result = router.route({"calls": calls}, ranked, SKILLS, text="plums", pending_codes=pending)
            self.assertEqual(result.action, "question", pending)
            self.assertIsNone(result.revises)

    def test_the_envelope_revises_with_a_waiting_code_still_works(self):
        single = {"skill": "stock.set", "slots": {"what": "plums"}, "revises": "abc"}
        self.assertIs(interpret_check.check_skill(single, SKILLS, pending_codes=("abc",)), single)
        result = router.route(single, [("stock.set", 3.0)], SKILLS, pending_codes=("abc",))
        self.assertEqual((result.action, result.revises), ("run", "abc"))
        multi = {"calls": [{"skill": "stock.set", "slots": {"what": "plums"}}, {"skill": "item.hide", "slots": {"what": "plums"}}],
                 "revises": "abc"}
        result = router.route(multi, [("stock.set", 3.0), ("item.hide", 2.0)], SKILLS, pending_codes=("abc",))
        self.assertEqual((result.action, result.revises), ("run", "abc"))

    def test_backlog_log_pick_uses_the_ordinary_cant_do_reply(self):
        from hass.skills import backlog as b
        reg = model.Registry({**SKILLS.skills, "page.faq": b.PAGE_FAQ, "backlog.log": b.BACKLOG_LOG})
        text = "can you order more eggs from the farm"
        store = _backlog()
        ranked = router.candidates(text, skills=reg)
        reply = {"skill": "backlog.log", "slots": {"summary": "order eggs from the farm"}}
        result = router.route(reply, ranked, reg, text=text, store=store)
        self.assertEqual((result.action, result.reply), ("backlog", backlog_mod.CANT_DO))

    def test_check_skill_leaves_other_replies_alone(self):
        reply = {"ops": []}
        self.assertIs(interpret_check.check_skill(reply, SKILLS), reply)
        too_many = {"calls": [{"skill": "stock.set", "slots": {"what": str(i)}} for i in range(interpret_check.MAX_OPS + 1)]}
        self.assertIn("question", interpret_check.check_skill(too_many, SKILLS))
        twice = {"calls": [{"skill": "stock.set", "slots": {"what": "x"}}] * 2}
        self.assertIn("question", interpret_check.check_skill(twice, SKILLS))


if __name__ == "__main__":
    unittest.main()
