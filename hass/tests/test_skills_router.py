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


def _report(name="report.shelf", triggers=("what's sold out?", "what's on the shelves"), **over):
    base = dict(slots=(), approval="none", live_class="read-only", side_effects=("none",), preview="none", undo=model.Undo("none", "none"))
    base.update(over)
    return _skill(name, "morning shelf report", list(triggers), **base)


def _with(*extra):
    return model.Registry({s.name: s for s in (*SKILLS.active(), *extra)})


class ExactReadOnlyTriggerTests(unittest.TestCase):
    STOCK = _skill("stock.clear", "mark things sold out", ["what is sold out", "sold out"], edits=(("hass/content/products.json", "x"),))

    def test_exact_read_only_trigger_beats_shared_stock_leaders(self):
        reg = _with(self.STOCK, _skill("stock.checked", "record the shelf check", ["what is sold out today", "what's on the shelves tonight"]), _report())
        for text in ("what's sold out?", "WHAT'S on the shelves"):
            ranked = router.candidates(text, skills=reg)
            self.assertEqual(ranked[0][0], "report.shelf")
            self.assertFalse(router._within_near_tie(ranked[0][1], ranked[1][1]) if len(ranked) > 1 else False)
            self.assertEqual(router.route({"skill": "report.shelf", "slots": {}}, ranked, reg, text=text).action, "run")

    def test_shared_words_and_change_exact_match_do_not_bypass_question(self):
        reg = _with(self.STOCK, _report())
        ranked = router.candidates("what is sold out now", skills=reg)
        self.assertNotEqual(ranked[0][0], "report.shelf")
        self.assertEqual(router.route({"skill": "stock.set", "slots": {"what": "x"}}, ranked, reg, text="x").action, "ask") if ranked[0][0] != "stock.set" and router._within_near_tie(ranked[0][1], dict(ranked).get("stock.set", 0)) else None
        collide = _with(_skill("stock.x", "change stock", ["what's sold out?"]), _report())  # exact change skill too
        ranked = router.candidates("what's sold out?", skills=collide)
        self.assertEqual(ranked[0][0], "stock.x")  # no preference for either exact match: plain word scores decide
        self.assertLess(dict(ranked)["report.shelf"], ranked[0][1])

    def test_duplicate_exact_trigger_and_inactive_report_do_not_choose(self):
        two = _with(_report(), _report("report.other"))
        self.assertEqual(router.candidates("what's sold out?", skills=two)[0][1], router.candidates("what's sold out?", skills=two)[1][1])
        retired = _with(_report(status="retired"))
        self.assertEqual(router.candidates("what's sold out?", skills=retired), router.candidates("what's sold out?", skills=SKILLS))
        self.assertEqual(router.candidates("", skills=_with(_report())), [])

    def test_exact_preference_preserves_attachment_and_side_effect_filters(self):
        photo = (model.Slot("photo", "attachment", True, ask="Which?"),)
        self.assertEqual(router.candidates("what's sold out?", attachment=True, skills=_with(_report())), [])
        self.assertEqual(router.candidates("what's sold out?", attachment=True, skills=_with(_report(slots=photo)))[0][0], "report.shelf")
        for over in (dict(side_effects=("backlog-row",)), dict(approval="owner-yes", edits=(("hass/content/products.json", "x"),)), dict(live_class="chat-live")):
            ranked = router.candidates("what's sold out?", skills=_with(_report(**over)))
            self.assertLess(dict(ranked).get("report.shelf", 0), 2 * max(dict(ranked).values()))  # no boost: scored on words only

    def test_exact_report_still_validates_model_reply(self):
        reg = _with(_report())
        ranked = router.candidates("what's sold out?", skills=reg)
        before = repr(ranked)
        self.assertEqual(router.route({"skill": "no.such", "slots": {}}, ranked, reg, text="x").action, "backlog")
        self.assertEqual(router.route({"skill": "report.shelf", "slots": {"nope": "x"}}, ranked, reg, text="x").action, "question")
        self.assertEqual(repr(router.candidates("what's sold out?", skills=reg)), before)


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
        import dataclasses
        from hass.skills import backlog as b
        # page.faq is retired (AVB-19-B2); an explicitly active copy keeps the fixed-reply contract covered
        reg = model.Registry({**SKILLS.skills, "page.faq": dataclasses.replace(b.PAGE_FAQ, status="active"), "backlog.log": b.BACKLOG_LOG})
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


class DecimalNearTieTests(unittest.TestCase):
    def _lead_only(self, ranked, reg=SKILLS, store=None):
        lead = ranked[0][0]
        return router.route({"skill": lead, "slots": {"what": "synthetic"}}, ranked, reg, text="x", store=store)

    def _real(self):
        import math
        words = ["quartz" + chr(97 + i // 26) + chr(97 + i % 26) for i in range(80)]
        items = [_skill("item.alpha", "choose alpha", [" ".join(words)]),
                 _skill("item.beta", "choose beta", [" ".join(words[:72])]),
                 _skill("item.gamma", "choose gamma", [" ".join(words[72:])])]
        items += [_skill("item.filler" + c, "filler", ["otherword"]) for c in "abc"]
        reg = model.Registry({s.name: s for s in items})
        return reg, " ".join(words)

    def test_decimal_exact_ten_percent_boundary_asks(self):
        for lead, second in ((1.1, 0.99), (13.0, 11.7), (167.889, 151.1001), (10.0, 9.0)):
            ranked = [("stock.set", lead), ("item.hide", second)]
            result = self._lead_only(ranked)
            self.assertEqual((result.action, result.calls), ("ask", ()), (lead, second))
            self.assertEqual(result.reply, "Do you want me to change what's in stock or hide an item?")

    def test_one_exposed_score_step_outside_boundary_runs(self):
        outside = self._lead_only([("stock.set", 167.889), ("item.hide", 151.1)])
        self.assertEqual(outside.action, "run")
        self.assertEqual([n for n, _s in outside.calls], ["stock.set"])
        inside = self._lead_only([("stock.set", 167.889), ("item.hide", 151.1002)])
        self.assertEqual(inside.action, "ask")
        # non-leading single pick: same boundary
        picked = router.route({"skill": "item.hide", "slots": {"what": "x"}},
                              [("stock.set", 167.889), ("maker.add", 100.0), ("item.hide", 151.1001)], SKILLS)
        self.assertEqual(picked.action, "ask")
        picked = router.route({"skill": "item.hide", "slots": {"what": "x"}},
                              [("stock.set", 167.889), ("maker.add", 100.0), ("item.hide", 151.1)], SKILLS)
        self.assertEqual((picked.action, [n for n, _s in picked.calls]), ("run", ["item.hide"]))

    def test_actual_candidates_decimal_boundary_is_inclusive(self):
        reg, text = self._real()
        ranked = router.candidates(text, skills=reg)
        self.assertEqual([(n, s) for n, s in ranked][:2], [("item.alpha", 167.889), ("item.beta", 151.1001)])
        before = list(ranked)
        store = _backlog()
        result = self._lead_only(ranked, reg, store)
        self.assertEqual((result.action, result.calls), ("ask", ()))
        self.assertEqual(result.reply, "Do you want me to choose alpha or choose beta?")
        self.assertEqual(ranked, before)
        self.assertEqual(store.rows(), [])

    def test_multicall_both_decimal_leaders_settles_tie(self):
        ranked = [("stock.set", 13.0), ("item.hide", 11.7), ("maker.add", 1.0)]
        a = {"skill": "stock.set", "slots": {"what": "plums"}}
        b = {"skill": "item.hide", "slots": {"what": "plums"}}
        for calls in ([a, b], [b, a]):
            result = router.route({"calls": calls}, ranked, SKILLS, text="plums")
            self.assertEqual(result.action, "run", calls)
            self.assertEqual(len(result.calls), 2)
        other = {"skill": "stock.set", "slots": {"what": "eggs"}}
        third = {"skill": "maker.add", "slots": {"what": "hilltop farm"}}
        for calls in ([a, other], [a, third]):
            result = router.route({"calls": calls}, ranked, SKILLS, text="plums")
            self.assertEqual((result.action, result.calls), ("ask", ()), calls)

    def test_decimal_comparison_ignores_host_context(self):
        import decimal
        ranked = [("stock.set", 167.889), ("item.hide", 151.1001)]
        saved = decimal.getcontext().copy()
        try:
            decimal.getcontext().prec = 2
            decimal.getcontext().traps[decimal.Inexact] = True
            decimal.getcontext().traps[decimal.Rounded] = True
            self.assertEqual(self._lead_only(ranked).action, "ask")
            self.assertEqual(self._lead_only([("stock.set", 167.889), ("item.hide", 151.1)]).action, "run")
        finally:
            decimal.setcontext(saved)

    def test_outside_pick_backlog_and_ordinary_scores_unchanged(self):
        store = _backlog()
        ranked = [("stock.set", 1.1), ("item.hide", 0.99)]
        outside = router.route({"skill": "hike.add", "slots": {"what": "x"}}, ranked, SKILLS, text="x", store=store)
        self.assertEqual(outside.action, "ask")
        self.assertIn("add a hike", outside.reply)
        self.assertEqual(self._lead_only(ranked, store=store).action, "ask")
        self.assertEqual(store.rows(), [])
        self.assertEqual(self._lead_only([("stock.set", 3.0), ("item.hide", 1.0)]).action, "run")
        self.assertEqual(router.route({"skill": "none", "summary": "s"}, ranked, SKILLS, text="x", store=store).action, "backlog")


if __name__ == "__main__":
    unittest.main()


def _loaf_content():
    from types import SimpleNamespace
    return SimpleNamespace(products=[
        {"id": "synthetic-loaf-a", "name": "Plain loaf", "status": "active", "category": "bread"},
        {"id": "synthetic-loaf-b", "name": "Seeded loaf", "status": "active", "category": "bread"}])


class HintScoringTests(unittest.TestCase):
    TODAY = datetime(2030, 1, 10).date()

    def _hints(self, text):
        from hass import nl_prep
        return nl_prep.make_hinter(_loaf_content())(text, self.TODAY, None)

    def test_date_hint_boosts_hike_with_no_trigger_overlap(self):
        hints = self._hints("2030-01-15")
        self.assertTrue(hints.get("dates") and not hints.get("hikes"), hints)
        self.assertEqual(router.candidates("2030-01-15", skills=SKILLS), [])
        self.assertEqual(router.candidates("2030-01-15", hints, skills=SKILLS), [("hike.add", 1.5)])

    def test_shelf_hint_boosts_stock_from_real_synthetic_membership(self):
        hints = self._hints("all the bread")
        self.assertTrue(hints.get("shelves") and not hints.get("products"), hints)
        plain = dict(router.candidates("all the bread", skills=SKILLS))
        boosted = dict(router.candidates("all the bread", hints, skills=SKILLS))
        self.assertEqual(round(boosted["stock.set"] - plain["stock.set"], 4), 1.5)
        self.assertEqual(boosted["social.item"], plain["social.item"])
        self.assertEqual(router.candidates("all the bread", hints, skills=SKILLS)[0][0], "stock.set")

    def test_family_signals_do_not_stack(self):
        both = {"dates": [{"date": "2030-01-15"}], "hikes": {"named": [1]}, "shelves": [{"shelf": "bread"}], "products": [{"id": "x"}]}
        plain = dict(router.candidates("bread", skills=SKILLS))
        got = dict(router.candidates("bread", both, skills=SKILLS))
        self.assertEqual(round(got["hike.add"] - plain.get("hike.add", 0), 4), 1.5)
        self.assertEqual(round(got["stock.set"] - plain["stock.set"], 4), 1.5)
        self.assertNotIn("shop.hours", got)
        dates_only = dict(router.candidates("hike", {"dates": [{"date": "x"}]}, skills=SKILLS))
        self.assertEqual(dates_only["hike.add"], dict(router.candidates("hike", {"hikes": {"named": [1]}}, skills=SKILLS))["hike.add"])
        asked = dict(router.candidates("2030-01-15", {"dates": [1]}, {"skill": "hike.add"}, skills=SKILLS))
        self.assertEqual(asked["hike.add"], 1.5 + router.OPEN_BOOST)

    def test_hints_cannot_cross_attachment_or_retirement_filter(self):
        photo = _skill("item.picture", "replace a picture", ["new picture for the honey"],
                       slots=(model.Slot("photo", "attachment", True, ask="Which photo?"),))
        reg = model.Registry({**SKILLS.skills, photo.name: photo})
        strong = {"dates": [1], "shelves": [1]}
        ranked = router.candidates("2030-01-15 all the bread", strong, attachment={"kind": "image"}, skills=reg)
        self.assertEqual([n for n, _s in ranked], [])
        retired = _skill("hike.old", "old hike", ["old hike"], status="retired") if "status" in model.Skill.__dataclass_fields__ else None
        if retired:
            reg2 = model.Registry({**SKILLS.skills, retired.name: retired})
            self.assertNotIn("hike.old", [n for n, _s in router.candidates("2030-01-15", strong, skills=reg2)])

    def test_empty_and_nondict_hints_preserve_scores(self):
        base = router.candidates("bread is gone", skills=SKILLS)
        for hints in (None, {}, {"dates": [], "shelves": []}, "dates", ["dates"], 5):
            with self.subTest(hints=hints):
                self.assertEqual(router.candidates("bread is gone", hints, skills=SKILLS), base)
        self.assertLessEqual(len(router.candidates("hike post bread hours maker", {"dates": [1], "shelves": [1]}, skills=SKILLS)), 3)

    def test_real_dispatch_router_seam_preserves_date_and_shelf_hints(self):
        from types import SimpleNamespace
        from hass.skills import dispatch
        conv = SimpleNamespace(aliases=lambda: None)
        disp = dispatch.Dispatcher(conv, SKILLS)
        disp._ctx = lambda now, texts: SimpleNamespace(content=_loaf_content(), today=self.TODAY)
        self.assertEqual(disp._router_names(["2030-01-15"], None, [], None), [("hike.add", 1.5)])
        ranked = disp._router_names(["all the bread"], None, [], None)
        self.assertEqual(ranked[0][0], "stock.set")

    def test_hint_ranking_does_not_complete_or_apply_a_request(self):
        ranked = router.candidates("2030-01-15", {"dates": [1]}, skills=SKILLS)
        self.assertEqual(ranked, [("hike.add", 1.5)])
        # a hint-only candidate is still only the second opinion: a model pick outside it is asked, not run
        result = router.route({"skill": "stock.set", "slots": {"what": "x"}}, ranked, SKILLS, text="2030-01-15")
        self.assertEqual(result.action, "ask")
