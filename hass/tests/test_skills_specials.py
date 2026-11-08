"""SKILLS-SPECIALS-1: the weekly specials skills (hass/skills/specials.py) on top of the AVO-SPECIALS-1 ops.

Parts: the declarations and the lint; every rule, the special finder, each plan and the read-only answer on synthetic
content; the owner's words against the voice rules; the live boundary (the deal line is the one price on the site);
the hook into the dispatcher; the interpreter check that used to refuse the deal argument; and the end-to-end rows of
hass/tests/fixtures/specials/e2e.jsonl, which run through the real Conversation, Editor, sitegen and claims on a
scratch writer worktree (the test kit of SKILLS-TK-1) with their dates counted from the shop's real today and some
specials pre-saved. The time-stable rows of hass/tests/fixtures/skills/specials/ are run by test_skills_cases and
test_skills_plans as for every skill.
Run: python3 -B -m unittest hass.tests.test_skills_specials -v
"""
import copy
import json
import re
import sys
import types
import unittest
from datetime import date, timedelta
from unittest import mock

from hass import editor, interpret_check, live_policy, sitegen, skills, voice
from hass.content_model import REPO_ROOT, load_and_validate, shop_today
from hass.ops import load_registry
from hass.skills import kinds, model, specials as sp, testkit
from hass.tests.test_store_ops import StoreTestCase, _req

FIXTURES = REPO_ROOT / "hass" / "tests" / "fixtures"
CASES = FIXTURES / "skills" / "specials"
E2E = FIXTURES / "specials" / "e2e.jsonl"
SHOW_CONTENT = json.loads((FIXTURES / "specials" / "show-content.json").read_text("utf-8"))
TODAY = date(2026, 11, 8)  # a Sunday
NAMES = ("specials.add", "specials.edit", "specials.remove", "specials.clear_expired", "specials.show")
ADD, EDIT, REMOVE, CLEAR = NAMES[:4]


def day(n=0):
    return TODAY + timedelta(days=n)


def special(id, title, start=0, end=3, *, deal="2 for $5", order=0, **extra):
    return {"id": id, "title": title, "deal": deal, "start": day(start).isoformat(), "end": day(end).isoformat(), "order": order, **extra}


def ctx(*specials, today=TODAY, texts=None, products=()):
    store = {"specials": list(specials)} if specials else {}
    return types.SimpleNamespace(today=today, texts=texts, content=types.SimpleNamespace(store=store, products=list(products)))


def refusal(skill, slots, c=None):
    """The owner's reply (marks removed) of a plan that refuses; the test fails when it does not."""
    try:
        skill.plan(slots, c if c is not None else ctx())
    except sp.Refusal as exc:
        return voice.plain(exc.reply)
    raise AssertionError(f"{skill.name} planned {slots} instead of refusing")


class DeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = skills.load_skills()
        cls.mine = list(sp.SKILLS)

    def test_the_five_skills_are_loaded_and_the_lint_is_clean(self):
        self.assertEqual([s.name for s in self.mine], list(NAMES))
        self.assertEqual([self.registry.get(n) for n in NAMES], self.mine)
        self.assertEqual(skills.skill_lint(self.mine, load_registry()), [])
        self.assertEqual(skills.skill_lint(self.registry, load_registry()), [])  # and no trigger text is shared with another skill

    def test_the_task_sentences_are_triggers_and_each_skill_has_the_mix(self):
        said = {model._fold(t.text): s.name for s in self.mine for t in s.triggers}
        for text, name in (("put the avocado honey on special this week, 2 for 5 dollars", ADD), ("special on jam till Friday", ADD),
                           ("take the special off", REMOVE), ("what are this week's specials", NAMES[4]),
                           ("extend the honey special to next Sunday", EDIT)):
            self.assertEqual(said.get(model._fold(text)), name, text)
        for skill in self.mine:
            self.assertEqual({"vague", "typo", "multi"} - {t.tag for t in skill.triggers}, set(), skill.name)

    def test_what_each_skill_may_touch(self):
        for skill in self.mine[:4]:
            self.assertEqual(skill.edits, (("hass/content/store.json", "specials"),), skill.name)
            self.assertEqual((skill.approval, skill.preview, skill.live_class, skill.undo.mode), ("owner-yes", "home", "private-only", "revert"))
        show = self.mine[4]
        self.assertEqual((show.approval, show.live_class, show.edits, show.preview), ("none", "read-only", (), "none"))
        self.assertEqual(show.plan({}, ctx()), [])

    def test_end_date_is_the_only_required_date_and_it_asks_one_short_question(self):
        add = self.mine[0]
        slots = {s.name: s for s in add.slots}
        self.assertIs(slots["end"].required, True)
        self.assertEqual(slots["end"].ask, "Until what day should it run?")
        self.assertIs(slots["start"].required, False)
        self.assertEqual(slots["title"].required, "unless:product")
        self.assertTrue(slots["deal"].owner_words and slots["title"].owner_words)
        for skill in self.mine:
            for s in skill.slots:
                self.assertLessEqual(len(s.ask.split()), 14, (skill.name, s.name))

    def test_every_rule_id_has_one_function_and_is_prefixed(self):
        used = {r for s in self.mine for r in s.rules}
        self.assertEqual(used, set(sp.RULES))
        self.assertTrue(all(r.startswith("specials-") for r in sp.RULES))  # the dispatcher's rule table is shared by every group

    def test_case_files_are_in_the_catalog_shape(self):
        found = {p.name for p in testkit.discover() if p.parent.name == "specials"}
        self.assertEqual(found, {f"{n}.jsonl" for n in NAMES})
        for skill in self.mine:
            problems = model.lint_cases(skill, REPO_ROOT)
            # The kit's rows have no 'undo' field (the kit undoes every draft itself); the lint's undo-row count cannot be met.
            self.assertEqual([p for p in problems if "undo row" not in p], [], skill.name)
            rows = testkit.load_rows(REPO_ROOT / skill.cases)
            self.assertGreaterEqual(len(rows), 10)
            self.assertGreaterEqual(sum(r.get("kind") == "refuse" for r in rows), 2)


class RuleTests(unittest.TestCase):
    def rule(self, name, slots, c=None, texts=None):
        return sp.RULES[name](slots, texts, c if c is not None else ctx())

    def test_text_limits(self):
        self.assertIsNone(self.rule("specials-text-limits", {"title": "a" * 60, "deal": "b" * 60}))
        self.assertIn("at most 60 characters", self.rule("specials-text-limits", {"title": "a" * 61})[0])
        self.assertIn("deal line can be at most 60", self.rule("specials-text-limits", {"deal": "b" * 61})[0])
        for bad in ("<b>2 for 5</b>", "x {{y}} z", "!!", "two\nlines", "&lt;b&gt;"):
            self.assertIn("something I can't use", self.rule("specials-text-limits", {"deal": bad})[0], bad)

    def test_links_email_and_phone_numbers_stay_out(self):
        for text, word in (("see shack.com", "web address"), ("www.x.org now", "web address"), ("http://x.org", "web address"),
                           ("mail me@shack.example", "email address"), ("call 805 555 0123", "phone number"), ("call 8055550123", "phone number")):
            for field in ("title", "deal"):
                hit = self.rule("specials-no-links-or-contact", {field: text})
                self.assertIn(word, hit[0], (field, text))
                self.assertEqual(hit[1], "policy")
        for fine in ("2 for $5", "Free sample Saturday", "$3.50 a bunch", "Buy 2, get 1 free", "10% off"):
            self.assertIsNone(self.rule("specials-no-links-or-contact", {"deal": fine}), fine)

    def test_a_price_goes_in_the_deal_line_only(self):
        for title in ("Eggs $3", "Eggs 3 dollars", "Eggs 3 bucks", "Eggs 50 cents", "Eggs 50¢", "Eggs five dollars", "Eggs twenty-five cents", "Eggs a buck", "Eggs Two Bucks"):
            reply, reason = self.rule("specials-price-in-deal-only", {"title": title})
            self.assertIn("A price can only go in the deal line", reply)
            self.assertEqual(reason, "price")
        self.assertIsNone(self.rule("specials-price-in-deal-only", {"title": "Eggs", "deal": "2 for $5 or 3 dollars"}))
        self.assertIsNone(self.rule("specials-price-in-deal-only", {"title": "Dollar Menu Day"}))
        self.assertIsNone(self.rule("specials-price-in-deal-only", {"title": "Eggs", "deal": "five dollars a dozen"}))  # words are fine in the deal
        self.assertIsNone(self.rule("specials-price-in-deal-only", {"title": "Dollar Menu Day"}))

    def test_the_deal_is_shown_exactly_as_typed(self):
        slots = {"deal": "2 for 5 dollars"}
        self.assertIsNone(self.rule("specials-deal-as-typed", slots, texts=["put the honey on special, 2 for 5 dollars, till Friday"]))
        self.assertIsNone(self.rule("specials-deal-as-typed", slots, texts=["put the honey on special, 2  for   5 dollars"]))  # spacing only
        self.assertIsNone(self.rule("specials-deal-as-typed", slots, texts=["special on honey", "2 for 5 dollars"]))  # said in a later text
        for reworded in ("2 for $5", "2 For 5 Dollars", "two for 5 dollars", "2 for 5 dollars!"):
            self.assertIn("exactly as you type it", self.rule("specials-deal-as-typed", {"deal": reworded}, texts=["honey 2 for 5 dollars"])[0], reworded)
        for inside in ("Eggs 12 for 5 dollars till Friday", "x2 for 5 dollars", "2 for 5 dollarsX", "Eggs 1,2 for 5 dollars"):  # not a whole token run
            self.assertIn("exactly as you type it", self.rule("specials-deal-as-typed", slots, texts=[inside])[0], inside)
        self.assertIsNone(self.rule("specials-deal-as-typed", {"deal": "$5"}, texts=["eggs $5, till Friday"]))
        self.assertIsNone(self.rule("specials-deal-as-typed", slots, texts=["honey (2 for 5 dollars)."]))
        for decimal, deal in (("Eggs 1.5 dollars till Friday", "5 dollars"), ("Eggs 2 for 1.5 dollars", "2 for 1")):  # a decimal is one amount
            self.assertIn("exactly as you type it", self.rule("specials-deal-as-typed", {"deal": deal}, texts=[decimal])[0], decimal)
        self.assertIsNone(self.rule("specials-deal-as-typed", {"deal": "1.5 dollars"}, texts=["Eggs 1.5 dollars. Till Friday"]))
        self.assertIsNone(self.rule("specials-deal-as-typed", slots, texts=None))  # no owner texts to compare (plan golden)

    def test_a_deal_cut_out_of_a_longer_figure_or_word_is_not_the_deal_he_typed(self):
        rule = lambda deal, text: self.rule("specials-deal-as-typed", {"deal": deal}, texts=[text])
        said = "put honey on special, 12 for $5, until Friday"
        self.assertIsNone(rule("12 for $5", said))  # the exact deal is kept
        for cut in ("2 for $5", "12 for $", "12 for", "2 for"):
            self.assertIn("exactly as you type it", rule(cut, said)[0], cut)  # a figure's tail or head is not a deal
        for deal, text in (("$5", "jam $5.50 till Friday"), ("$5", "jam $55 till Friday"), ("2 for $5", "jam 2 for $5.5 till Friday"),
                           ("2 for $5", "jam 1.2 for $5"), ("2 for $5", "jam 1,2 for $5"), ("5", "jam 5 dollars"), ("20", "jam 20% off"),
                           ("buy one get one", "jam buy one get one free"), ("2 for $5", "jam 2 for $5 each"), ("$5", "jam €$5")):
            self.assertIn("exactly as you type it", rule(deal, text)[0], (deal, text))
        for deal, text in (("2 for $5", "jam 2 for $5."), ("2 for $5", "jam, 2 for $5, till Friday"), ("2 for $5", "jam:2 for $5"),
                           ("$5 off", "jam $5 off till Friday"), ("buy one get one free", "jam buy one get one free, through Sunday")):
            self.assertIsNone(rule(deal, text), (deal, text))

    def test_a_deal_missing_its_front_is_not_the_deal_he_typed(self):
        rule = lambda deal, text: self.rule("specials-deal-as-typed", {"deal": deal}, texts=[text])
        for deal, text in (("get one free", "put honey on special, buy one get one free, until Friday"),
                           ("one get one free", "put honey on special, buy one get one free, until Friday"),
                           ("get one free", "honey on special, buy one, get one free, till Friday"),  # a comma between does not hide it
                           ("for $5", "put honey on special, 12 for $5, until Friday"),
                           ("for 5 dollars", "honey two for 5 dollars till Friday"),
                           ("get the third free", "honey buy two get the third free"),
                           ("price", "honey half price till Friday"),
                           ("off", "honey 20% off till Friday"),
                           ("$2 off", "honey save $2 off till Friday")):
            self.assertIn("exactly as you type it", rule(deal, text)[0], (deal, text))
        for deal, text in (("buy one get one free", "put honey on special, buy one get one free, until Friday"),  # whole deals stay
                           ("12 for $5", "put honey on special, 12 for $5, until Friday"),
                           ("get one free", "honey on special, get one free, till Friday"),  # said that way, so kept that way
                           ("20% off", "honey 20% off till Friday"),
                           ("half price", "honey half price till Friday"),
                           ("2 for $5", "special on jam: 2 for $5 till Friday"),
                           ("2 for $5", "put the jam on special this week, 2 for $5"),
                           ("2 for $5", "2 for $5 on the jam till Friday")):
            self.assertIsNone(rule(deal, text), (deal, text))

    def test_a_spelled_out_amount_in_a_title_is_a_price_too(self):
        for title in ("Honey five dollars", "Honey twenty-five cents", "Honey twenty five bucks", "Eggs a buck", "Eggs one hundred dollars",
                      "Eggs 5 euros", "Eggs €5", "Eggs £3", "Eggs three DOLLARS", "Eggs ten bucks each"):
            reply, reason = self.rule("specials-price-in-deal-only", {"title": title})
            self.assertIn("A price can only go in the deal line", reply, title)
            self.assertEqual(reason, "price", title)
        for plain in ("Honey", "Dollar Menu Day", "Five Star Honey", "Five pound jar of honey", "A quarter pound of honey", "Penny candy",
                      "Three kinds of jam", "Two for the road", "Buck's honey", "Half dozen eggs", "Sample Saturday"):
            self.assertIsNone(self.rule("specials-price-in-deal-only", {"title": plain}), plain)

    def test_a_spelled_out_price_in_a_title_cannot_be_planned_for_an_add_or_an_edit_or_come_from_a_product(self):
        said = ["honey five dollars on special, buy one get one, until Friday"]
        add = {"title": "Honey five dollars", "deal": "buy one get one", "end": "2026-11-13"}
        self.assertIn("price can only go in the deal line", refusal(sp.SPECIALS_ADD, add, ctx(texts=said)))
        c = ctx(special("avocado-honey", "Avocado honey"), texts=said)
        self.assertIn("price can only go in the deal line", refusal(sp.SPECIALS_EDIT, {"special": "honey", "title": "Honey five dollars"}, c))
        product = {"id": "photo-product-041", "name": "Honey five dollars"}  # a product named like a price: ask, do not title it so
        self.assertEqual(refusal(sp.SPECIALS_ADD, {"product": "photo-product-041", "deal": "buy one get one", "end": "2026-11-13"},
                                 ctx(products=[product])), sp.ASK_ON)
        plain = {"id": "photo-product-042", "name": "Avocado honey"}
        op = sp.SPECIALS_ADD.plan({"product": "photo-product-042", "deal": "buy one get one", "end": "2026-11-13"}, ctx(products=[plain]))[0]
        self.assertEqual(op["args"]["title"], "Avocado honey")

    def test_both_add_and_edit_run_the_as_typed_and_word_price_rules(self):
        for rules in (sp.ADD_RULES, sp.EDIT_RULES):
            self.assertIn("specials-deal-as-typed", rules)
            self.assertIn("specials-price-in-deal-only", rules)

    def test_end_date_required(self):
        self.assertEqual(self.rule("specials-end-date-required", {}), ("Until what day should it run?", "other"))
        self.assertIsNone(self.rule("specials-end-date-required", {"end": "2026-11-13"}))

    def test_dates(self):
        make = lambda **s: self.rule("specials-dates", s)  # noqa: E731
        self.assertIsNone(make(start="2026-11-08", end="2026-11-08"))  # a one-day special
        self.assertIsNone(make(start="2026-11-08", end="2026-12-08"))  # exactly 31 days
        self.assertIn("at most 31 days", make(start="2026-11-08", end="2026-12-09")[0])
        self.assertIn("Saturday, November 7 has already passed", make(end="2026-11-07")[0])
        self.assertIn("before the first day", make(start="2026-11-12", end="2026-11-10")[0])
        self.assertIsNone(make(end="2026-11-08"))  # the last day counts: today is not past

    def test_dates_of_a_finished_special_and_a_special_with_a_new_last_day(self):
        old = special("old", "Old eggs", start=-9, end=-3)
        c = ctx(old)
        self.assertIn("finished on Thursday, November 5", self.rule("specials-dates", {"special": "old", "deal": "x"}, c)[0])
        self.assertIsNone(self.rule("specials-dates", {"special": "old", "end": "2026-11-10"}, c))  # run again: the new last day counts
        self.assertIn("at most 31 days", self.rule("specials-dates", {"special": "old", "end": "2026-12-30"}, c)[0])

    def test_never_more_than_six_at_once(self):
        six = [special(f"s{n}", f"Special {n}", start=0, end=5, order=n) for n in range(6)]
        hit = self.rule("specials-max-six-active", {"title": "Figs", "start": "2026-11-09", "end": "2026-11-11"}, ctx(*six))
        self.assertIn("more than six specials on Monday, November 9", hit[0])
        self.assertIn("Which one should I take off first", hit[0])
        for n in range(6):
            self.assertIn(f"Special {n}", voice.plain(hit[0]))
        five = six[:5]
        self.assertIsNone(self.rule("specials-max-six-active", {"title": "Figs", "end": "2026-11-11"}, ctx(*five)))
        self.assertIsNone(self.rule("specials-max-six-active", {"title": "Figs", "start": "2026-11-14", "end": "2026-11-16"}, ctx(*six)))  # starts after the six end
        self.assertIsNone(self.rule("specials-max-six-active", {"title": "Figs", "end": "2026-11-11"}, ctx(*[special(f"o{n}", f"Old {n}", -9, -3) for n in range(8)])))  # finished ones do not count

    def test_an_edit_that_keeps_six_does_not_count_itself_twice(self):
        six = [special(f"s{n}", f"Special {n}", start=0, end=5, order=n) for n in range(6)]
        self.assertIsNone(self.rule("specials-max-six-active", {"special": "s2", "end": "2026-11-12"}, ctx(*six)))
        later = special("late", "Late", start=6, end=8, order=7)
        self.assertIn("more than six", self.rule("specials-max-six-active", {"special": "late", "start": "2026-11-10"}, ctx(*six, later))[0])

    def test_a_special_with_the_same_title_is_not_added_twice(self):
        c = ctx(special("avocado-honey", "Avocado honey"))
        hit = self.rule("specials-twin", {"title": "avocado   HONEY"}, c)
        self.assertIn("already a special called", hit[0])
        self.assertIsNone(self.rule("specials-twin", {"title": "Avocado honey"}, ctx(special("avocado-honey", "Avocado honey", -9, -3))))  # a finished one
        self.assertIsNone(self.rule("specials-twin", {"special": "avocado-honey", "title": "Avocado honey"}, c))  # an edit keeping its own title

    def test_the_saved_list_has_room(self):
        full = [special(f"o{n}", f"Old {n}", -40 - n, -39 - n) for n in range(sp.MAX_SPECIALS_STORED)]
        self.assertIn("full", self.rule("specials-room", {}, ctx(*full))[0])
        self.assertIsNone(self.rule("specials-room", {}, ctx(*full[:-1])))

    def test_which_something_to_change_and_nothing_new(self):
        c = ctx(special("avocado-honey", "Avocado honey"))
        self.assertIsNone(self.rule("specials-which", {"special": "honey"}, c))
        self.assertIn("no specials on right now", self.rule("specials-which", {"special": "honey"}, ctx())[0])
        self.assertEqual(self.rule("specials-something-to-change", {"special": "honey"}, c)[0], sp.ASK_CHANGE)
        self.assertIsNone(self.rule("specials-something-to-change", {"special": "honey", "clear_product": True}, c))
        self.assertEqual(self.rule("specials-not-already-true", {"special": "honey", "deal": "2 for $5"}, c)[0], sp.ALREADY_SAYS)
        self.assertIsNone(self.rule("specials-not-already-true", {"special": "honey", "deal": "3 for $5"}, c))
        self.assertIsNone(self.rule("specials-not-already-true", {"special": "honey"}, c))  # nothing given is the other rule's question

    def test_only_finished_specials_can_be_cleared(self):
        self.assertEqual(self.rule("specials-finished-to-clear", {}, ctx())[0], sp.NOTHING_FINISHED)
        self.assertEqual(self.rule("specials-finished-to-clear", {}, ctx(special("a", "A")))[0], sp.NOTHING_FINISHED)
        self.assertIsNone(self.rule("specials-finished-to-clear", {}, ctx(special("a", "A"), special("b", "B", -9, -1))))
        self.assertIsNone(self.rule("specials-finished-to-clear", {}, types.SimpleNamespace(today=TODAY)))  # nothing to look at: the editor decides

    def test_dispatcher_style_use_never_mutates_the_slots(self):
        slots = {"title": " Eggs ", "deal": "2 for $5", "end": "2026-11-13"}
        before = copy.deepcopy(slots)
        sp.SPECIALS_ADD.plan(slots, ctx())
        self.assertEqual(slots, before)


class FinderTests(unittest.TestCase):
    def setUp(self):
        self.honey = special("avocado-honey", "Avocado honey", product="photo-product-041")
        self.jam = special("plum-jam", "Plum jam", order=1)
        self.old = special("old-eggs", "Old eggs", start=-9, end=-3)
        self.products = [{"id": "photo-product-041", "name": "Stepladder avocado blossom honey"}]

    def find(self, query, *specials):
        status, found, reply = sp.resolve_special(ctx(*specials, products=self.products), query)
        return status, (found or {}).get("id"), voice.plain(reply)

    def test_by_title_by_product_by_plural_and_by_id(self):
        both = (self.honey, self.jam)
        for query in ("the honey special", "honey", "avocado honey", "Avocado Honey special", "the stepladder one", "avocado-honey", "honeys"):
            self.assertEqual(self.find(query, *both)[:2], ("one", "avocado-honey"), query)
        self.assertEqual(self.find("the jam special", *both)[:2], ("one", "plum-jam"))

    def test_no_name_means_the_only_running_special_else_ask(self):
        for query in ("the special", "it", "that one", "", None):
            self.assertEqual(self.find(query, self.honey)[:2], ("one", "avocado-honey"), query)
        status, found, reply = self.find("the special", self.honey, self.jam)
        self.assertEqual((status, found), ("several", None))
        self.assertEqual(reply, "Which special do you mean: Avocado honey or Plum jam?")
        self.assertEqual(self.find("the special")[::2], ("none", sp.NO_SPECIALS_NOW))
        self.assertEqual(self.find("the special", self.old)[::2], ("none", sp.NO_SPECIALS_NOW))  # finished ones are not 'the' special

    def test_several_fit_asks_and_none_fit_says_what_is_on(self):
        jam2 = special("raspberry-jam", "Raspberry jam", order=2)
        self.assertEqual(self.find("jam", self.jam, jam2)[::2], ("several", "Which special do you mean: Plum jam or Raspberry jam?"))
        status, _id, reply = self.find("eggs", self.honey, self.jam)
        self.assertEqual(status, "none")
        self.assertIn("Right now there is Avocado honey or Plum jam", reply)

    def test_exact_title_beats_a_longer_title(self):
        a, b = special("jam", "Jam"), special("plum-jam", "Plum jam", order=1)
        self.assertEqual(self.find("jam", a, b)[:2], ("one", "jam"))

    def test_a_finished_special_is_found_only_when_nothing_running_fits(self):
        self.assertEqual(self.find("eggs", self.honey, self.old)[:2], ("one", "old-eggs"))
        live_eggs = special("eggs", "Eggs")
        self.assertEqual(self.find("eggs", self.old, live_eggs)[:2], ("one", "eggs"))

    def test_all_is_never_a_bulk_removal(self):
        status, _id, reply = self.find("all of them", self.honey, self.jam)
        self.assertEqual(status, "all")
        self.assertIn("one at a time", reply)
        self.assertEqual(self.find("everything")[0], "none")

    def test_without_content_only_an_exact_id_resolves(self):
        bare = types.SimpleNamespace(today=TODAY)
        self.assertEqual(sp.resolve_special(bare, "avocado-honey")[:2], ("one", {"id": "avocado-honey"}))
        self.assertEqual(sp.resolve_special(bare, "the honey special")[0], "none")
        self.assertEqual(sp.resolve_special(bare, None)[0], "none")


class PlanTests(unittest.TestCase):
    def test_start_defaults_to_today_and_an_explicit_start_is_kept(self):
        op = sp.SPECIALS_ADD.plan({"title": "Eggs", "deal": "2 for $5", "end": "2026-11-13"}, ctx())[0]
        self.assertEqual(op["args"]["start"], "2026-11-08")
        op = sp.SPECIALS_ADD.plan({"title": "Eggs", "deal": "2 for $5", "end": "2026-11-13", "start": "2026-11-10"}, ctx())[0]
        self.assertEqual(op["args"]["start"], "2026-11-10")
        self.assertEqual(sp.SPECIALS_ADD.plan({"title": "Eggs", "deal": "x deal", "end": "2026-11-13"}, ctx(today="2026-11-08"))[0]["args"]["start"], "2026-11-08")  # an ISO string works too
        no_clock = sp.SPECIALS_ADD.plan({"title": "Eggs", "deal": "x deal", "end": "2026-11-13"}, None)[0]  # the lint calls plans with no ctx
        self.assertNotIn("start", no_clock["args"])  # the editor then starts it today

    def test_product_gives_title_and_picture(self):
        products = [{"id": "photo-product-041", "name": "Stepladder avocado blossom honey"}, {"id": "photo-product-099", "name": "A" * 61},
                    {"id": "photo-product-098", "name": "Honey $5"}]
        c = ctx(products=products)
        args = sp.SPECIALS_ADD.plan({"product": "photo-product-041", "deal": "2 for 5 dollars", "end": "2026-11-13"}, c)[0]["args"]
        self.assertEqual((args["title"], args["product"], args["picture"]), ("Stepladder avocado blossom honey", "photo-product-041", True))
        args = sp.SPECIALS_ADD.plan({"product": "photo-product-041", "title": "Honey week", "deal": "x deal", "end": "2026-11-13", "picture": False}, c)[0]["args"]
        self.assertEqual((args["title"], "picture" in args), ("Honey week", False))
        for pid in ("photo-product-099", "photo-product-098"):  # too long or not plain: the owner names the special
            self.assertEqual(refusal(sp.SPECIALS_ADD, {"product": pid, "deal": "x deal", "end": "2026-11-13"}, c), sp.ASK_ON)

    def test_the_one_short_question_for_each_missing_part(self):
        full = {"title": "Eggs", "deal": "2 for $5", "end": "2026-11-13"}
        for missing, ask in (("title", sp.ASK_ON), ("deal", sp.ASK_DEAL), ("end", sp.ASK_END)):
            slots = {k: v for k, v in full.items() if k != missing}
            self.assertEqual(refusal(sp.SPECIALS_ADD, slots), ask)
            self.assertLessEqual(len(ask.split()), 14)

    def test_the_deal_line_is_the_one_place_for_a_price(self):
        op = sp.SPECIALS_ADD.plan({"title": "Eggs", "deal": "2 for 5 dollars, $3.50 each", "end": "2026-11-13"}, ctx())[0]
        self.assertEqual(op["args"]["deal"], "2 for 5 dollars, $3.50 each")  # exactly as typed, price and all
        self.assertIn("price can only go in the deal line", refusal(sp.SPECIALS_ADD, {"title": "Eggs $3", "deal": "x deal", "end": "2026-11-13"}))

    def test_a_plan_texts_check_when_the_dispatcher_gives_them(self):
        c = ctx(texts=["eggs on special, 2 for 5 dollars till Friday"])
        self.assertTrue(sp.SPECIALS_ADD.plan({"title": "Eggs", "deal": "2 for 5 dollars", "end": "2026-11-13"}, c))
        self.assertIn("exactly as you type it", refusal(sp.SPECIALS_ADD, {"title": "Eggs", "deal": "2 for $5", "end": "2026-11-13"}, c))

    def test_a_decimal_amount_is_not_cut_in_add_or_edit(self):
        c = ctx(special("avocado-honey", "Avocado honey", deal="2 for $5", product="photo-product-041", picture=True), texts=["Eggs 1.5 dollars till Friday"])
        self.assertIn("exactly as you type it", refusal(sp.SPECIALS_ADD, {"title": "Eggs", "deal": "5 dollars", "end": "2026-11-13"}, c))
        self.assertIn("exactly as you type it", refusal(sp.SPECIALS_EDIT, {"special": "honey", "deal": "5 dollars"}, c))
        ok = ctx(texts=["Eggs 1.5 dollars till Friday"])
        self.assertTrue(sp.SPECIALS_ADD.plan({"title": "Eggs", "deal": "1.5 dollars", "end": "2026-11-13"}, ok))

    def test_edit_sends_only_what_changes(self):
        c = ctx(special("avocado-honey", "Avocado honey", deal="2 for $5", product="photo-product-041", picture=True))
        args = sp.SPECIALS_EDIT.plan({"special": "honey", "deal": "2 for $5", "end": "2026-11-15"}, c)[0]["args"]
        self.assertEqual(args, {"id": "avocado-honey", "end": "2026-11-15"})  # the same deal is not sent again
        args = sp.SPECIALS_EDIT.plan({"special": "honey", "clear_product": True}, c)[0]["args"]
        self.assertEqual(args, {"id": "avocado-honey", "clearProduct": True})
        self.assertEqual(refusal(sp.SPECIALS_EDIT, {"special": "honey", "end": "2026-11-11"}, c), sp.ALREADY_SAYS)
        no_product = ctx(special("avocado-honey", "Avocado honey"))
        self.assertEqual(refusal(sp.SPECIALS_EDIT, {"special": "honey", "clear_product": True}, no_product), sp.ALREADY_SAYS)

    def test_extending_runs_through_the_same_checks_as_adding(self):
        six = [special(f"s{n}", f"Special {n}", start=0, end=2, order=n) for n in range(6)] + [special("later", "Later", start=3, end=5, order=7)]
        self.assertIn("more than six", refusal(sp.SPECIALS_EDIT, {"special": "later", "start": "2026-11-09"}, ctx(*six)))
        self.assertTrue(sp.SPECIALS_EDIT.plan({"special": "later", "end": "2026-11-20"}, ctx(*six)))  # later start, still at most six
        c = ctx(special("avocado-honey", "Avocado honey", start=0, end=3))
        self.assertIn("at most 31 days", refusal(sp.SPECIALS_EDIT, {"special": "honey", "end": "2026-12-30"}, c))
        self.assertIn("price can only go in the deal line", refusal(sp.SPECIALS_EDIT, {"special": "honey", "title": "Honey $5"}, c))

    def test_remove_names_one_special(self):
        c = ctx(special("avocado-honey", "Avocado honey"), special("plum-jam", "Plum jam", order=1))
        self.assertEqual(sp.SPECIALS_REMOVE.plan({"special": "the jam special"}, c), [{"op": "specials.remove", "args": {"id": "plum-jam"}}])
        self.assertEqual(refusal(sp.SPECIALS_REMOVE, {"special": "the special"}, c), "Which special do you mean: Avocado honey or Plum jam?")
        self.assertIn("one at a time", refusal(sp.SPECIALS_REMOVE, {"special": "all"}, c))

    def test_clear_expired_needs_something_finished(self):
        self.assertEqual(sp.SPECIALS_CLEAR.plan({}, ctx(special("a", "A", -9, -1), special("b", "B"))), [{"op": "specials.clear_expired", "args": {}}])
        self.assertEqual(refusal(sp.SPECIALS_CLEAR, {}, ctx(special("b", "B"))), sp.NOTHING_FINISHED)

    def test_every_plan_op_is_a_registered_op_with_valid_arguments(self):
        registry = load_registry()
        saved = ctx(special("avocado-honey", "Avocado honey"))
        for skill, slots, c in ((sp.SPECIALS_ADD, {"title": "Eggs", "deal": "2 for $5", "end": "2026-11-13", "product": "photo-product-041", "picture": True}, ctx()),
                                (sp.SPECIALS_EDIT, {"special": "avocado-honey", "title": "New", "deal": "d eal", "start": "2026-11-09", "end": "2026-11-12",
                                                    "product": "photo-product-041"}, saved),
                                (sp.SPECIALS_EDIT, {"special": "avocado-honey", "clear_product": True}, ctx(special("avocado-honey", "Avocado honey", product="photo-product-041"))),
                                (sp.SPECIALS_REMOVE, {"special": "avocado-honey"}, saved), (sp.SPECIALS_CLEAR, {}, ctx(special("o", "Old", -9, -3)))):
            for op in skill.plan(slots, c):
                self.assertIn(op["op"], registry)
                self.assertEqual(set(op["args"]) - set(registry[op["op"]].args), set(), op)
                for name, arg in registry[op["op"]].args.items():
                    self.assertTrue(name in op["args"] or not arg.required, (op, name))


class ShowTests(unittest.TestCase):
    def reply(self, name):
        return sp.show_reply({}, ctx(*SHOW_CONTENT[name]))

    def test_the_recorded_answers_equal_what_the_code_says(self):
        rows = testkit.load_rows(CASES / "specials.show.jsonl")
        self.assertEqual({r["note"] for r in rows}, {f"content: {n}" for n in SHOW_CONTENT})
        for row in rows:
            name = row["note"].split(": ")[1]
            with self.subTest(name):
                self.assertEqual(row["replies"], [{"unsupported": self.reply(name)}])

    def test_what_is_shown_and_in_which_order(self):
        self.assertEqual(self.reply("none"), "There are no specials on right now.")
        one = voice.plain(self.reply("one-live"))
        self.assertEqual(one, "On now:\nAvocado honey: 2 for 5 dollars, through Friday, November 13")
        two = voice.plain(self.reply("two-live-in-order")).splitlines()
        self.assertEqual([ln.split(":")[0] for ln in two[1:]], ["Free samples", "Plum jam"])  # the page's own order
        self.assertIn("Coming up:\nFigs: buy one get one, from Tuesday, November 10", voice.plain(self.reply("live-and-coming-up")))
        self.assertNotIn("Old eggs", self.reply("finished-ones-are-not-listed"))
        self.assertEqual(len([ln for ln in voice.plain(self.reply("three-coming-up-only-three-shown")).splitlines() if ln.startswith("Special")]), 3)
        self.assertIn("from Saturday, January 2, 2027", voice.plain(self.reply("starts-next-year")))  # the year only when it is not this one

    def test_every_deal_is_shown_exactly_as_it_was_typed(self):
        for name, specials in SHOW_CONTENT.items():
            reply = voice.plain(self.reply(name))
            for s in specials:
                if reply.count(s["title"]):
                    self.assertIn(f"{s['title']}: {s['deal']},", reply, name)

    def test_every_answer_passes_the_voice_rules(self):
        for name in SHOW_CONTENT:
            self.assertEqual(voice.check(self.reply(name)), [], name)

    def test_without_content_or_a_clock_it_says_so(self):
        self.assertEqual(sp.show_reply({}, types.SimpleNamespace(today=TODAY)), sp.NOT_AVAILABLE)
        self.assertEqual(sp.show_reply({}, None), sp.NOT_AVAILABLE)


class VoiceTests(unittest.TestCase):
    def test_every_fixed_reply_passes_the_voice_rules_and_the_plain_words_check(self):
        names = ("ASK_END", "ASK_ON", "ASK_DEAL", "ASK_WHICH", "ASK_CHANGE", "NOT_AS_TYPED", "PRICE_ONLY_IN_DEAL", "ALREADY_SAYS",
                 "NOTHING_FINISHED", "LIST_FULL", "NOT_AVAILABLE", "NO_SPECIALS_NOW")
        texts = [getattr(sp, n) for n in names]
        texts += [reply for skill in sp.SKILLS for _cond, reply in skill.refuse]
        self.assertGreater(len(texts), 12)
        for text in texts:
            self.assertEqual(voice.check(text), [], text)
            self.assertEqual(testkit.plain_words_problems(text), [], text)

    def test_every_refusal_the_plans_give_passes_too(self):
        six = [special(f"s{n}", f"Special {n}", start=0, end=5, order=n) for n in range(6)]
        old = special("old-eggs", "Old eggs", start=-9, end=-3)
        honey = special("avocado-honey", "Avocado honey")
        attempts = [
            (sp.SPECIALS_ADD, {"title": "Eggs $3", "deal": "x deal", "end": "2026-11-13"}, ctx()),
            (sp.SPECIALS_ADD, {"title": "Eggs", "deal": "mail me@shack.example", "end": "2026-11-13"}, ctx()),
            (sp.SPECIALS_ADD, {"title": "Eggs", "deal": "x" * 61, "end": "2026-11-13"}, ctx()),
            (sp.SPECIALS_ADD, {"title": "Eggs", "deal": "x deal", "end": "2026-11-01"}, ctx()),
            (sp.SPECIALS_ADD, {"title": "Eggs", "deal": "x deal", "end": "2026-12-30"}, ctx()),
            (sp.SPECIALS_ADD, {"title": "Figs", "deal": "x deal", "end": "2026-11-11"}, ctx(*six)),
            (sp.SPECIALS_ADD, {"title": "Avocado honey", "deal": "x deal", "end": "2026-11-11"}, ctx(honey)),
            (sp.SPECIALS_ADD, {"title": "Figs", "deal": "x deal", "end": "2026-11-11"}, ctx(*[special(f"o{n}", f"Old {n}", -40 - n, -39 - n) for n in range(20)])),
            (sp.SPECIALS_EDIT, {"special": "eggs", "deal": "x deal"}, ctx(old)),
            (sp.SPECIALS_EDIT, {"special": "honey", "end": "2026-11-11"}, ctx(honey)),
            (sp.SPECIALS_EDIT, {"special": "honey"}, ctx(honey)),
            (sp.SPECIALS_EDIT, {"special": "jam", "end": "2026-11-11"}, ctx(honey)),
            (sp.SPECIALS_REMOVE, {"special": "all"}, ctx(honey, special("plum-jam", "Plum jam"))),
            (sp.SPECIALS_REMOVE, {"special": "the special"}, ctx()),
            (sp.SPECIALS_CLEAR, {}, ctx(honey)),
        ]
        for skill, slots, c in attempts:
            with self.subTest(skill.name, slots=slots):
                with self.assertRaises(sp.Refusal) as caught:
                    skill.plan(slots, c)
                self.assertEqual(voice.check(caught.exception.reply), [], caught.exception.reply)
                self.assertEqual(testkit.plain_words_problems(voice.plain(caught.exception.reply)), [])
                self.assertLessEqual(len(voice.plain(caught.exception.reply).split("\n")), 2)

    def test_the_owners_own_words_are_marked_as_his(self):
        reply = refusal(sp.SPECIALS_REMOVE, {"special": "the special"}, ctx(special("a", "Avocado honey"), special("b", "Plum jam")))
        self.assertNotIn(voice.OPEN, reply)  # plain() strips the marks
        raw = sp.resolve_special(ctx(special("a", "Service bureau"), special("b", "Plum jam")), "the special")[2]
        self.assertIn(voice.OPEN + "Service bureau" + voice.CLOSE, raw)  # a title with a word the voice rules ban is still his
        self.assertEqual(voice.check(raw), [])


class LiveBoundaryTests(StoreTestCase):
    """The deal line is the one place a price may appear, and the live boundary still stops it from going out from chat."""

    def draft(self, repo, *ops):
        out = repo.prepare(_req(*ops))
        self.assertEqual(out["result"], "ok", out)
        return out["draft"]

    def test_a_deal_with_a_price_is_private_only_and_one_without_is_not(self):
        repo = self.repo()
        today = shop_today()
        priced = sp.SPECIALS_ADD.plan({"title": "Eggs", "deal": "2 for 5 dollars", "end": (today + timedelta(days=3)).isoformat()}, ctx(today=today))
        plain = sp.SPECIALS_ADD.plan({"title": "Samples", "deal": "Free sample Saturday", "end": (today + timedelta(days=3)).isoformat()}, ctx(today=today))
        self.assertIn("protected sentences: prices", live_policy.check(self.draft(repo, *[(o["op"], o["args"]) for o in priced])))
        self.assertEqual(live_policy.check(self.draft(repo, *[(o["op"], o["args"]) for o in plain])), [])
        self.assertTrue(all(s.live_class == "private-only" for s in sp.SKILLS[:4]))  # a deal may carry a price: declared for all four

    def test_taking_a_priced_special_off_or_clearing_it_is_private_only_too(self):
        repo = self.repo()
        today = shop_today()
        repo.run(("specials.add", {"title": "Eggs", "deal": "2 for $5", "end": (today + timedelta(days=3)).isoformat()}))
        remove = sp.SPECIALS_REMOVE.plan({"special": "eggs"}, types.SimpleNamespace(today=today, content=types.SimpleNamespace(
            store=repo.store(), products=[])))
        self.assertIn("protected sentences: prices", live_policy.check(self.draft(repo, *[(o["op"], o["args"]) for o in remove])))

    def test_the_editor_still_refuses_a_price_in_the_title_and_markup_in_the_deal(self):
        repo = self.repo()
        end = (shop_today() + timedelta(days=3)).isoformat()
        self.assertEqual(repo.prepare(_req(("specials.add", {"title": "Eggs", "deal": "2 for $5", "end": end})))["result"], "ok")
        for args in ({"title": "Eggs $3", "deal": "x deal", "end": end}, {"title": "Eggs", "deal": "<b>x</b>", "end": end}):
            out = repo.prepare(_req(("specials.add", args)))
            self.assertNotEqual(out["result"], "ok", args)


class DispatcherHookTests(unittest.TestCase):
    def test_rules_and_the_read_only_answer_are_handed_to_the_dispatcher_when_it_exists(self):
        fake = types.ModuleType("hass.skills.dispatch")
        fake.RULES, fake.READ_ONLY = {"no-price": object()}, {}
        with mock.patch.dict(sys.modules, {"hass.skills.dispatch": fake}), mock.patch.object(skills, "dispatch", fake, create=True):
            sp._register()
        self.assertEqual(set(fake.RULES) - {"no-price"}, set(sp.RULES))
        self.assertIs(fake.READ_ONLY["specials.show"], sp.show_reply)
        self.assertIsNot(fake.RULES["no-price"], sp.RULES.get("no-price"))  # another group's rule is never replaced

    def test_without_the_dispatcher_nothing_happens(self):
        real = sys.modules.pop("hass.skills.dispatch", None)
        try:
            with mock.patch.dict(sys.modules, {"hass.skills.dispatch": None}):
                sp._register()  # an ImportError, swallowed
        finally:
            if real is not None:
                sys.modules["hass.skills.dispatch"] = real

    def test_a_rule_answer_is_the_pair_the_dispatcher_reads(self):
        for rule in sp.RULES.values():
            hit = rule({"title": "Eggs $3", "deal": "<b>", "end": None, "special": "zzz"}, ["x"], ctx())
            self.assertTrue(hit is None or (isinstance(hit, tuple) and len(hit) == 2 and isinstance(hit[0], str)
                                            and hit[1] in ("unknown-skill", "policy", "unsupported-page", "stuck", "price", "other")))


class OutsideAssumptionTests(unittest.TestCase):
    def test_the_day_words_the_dispatcher_resolves_before_the_plan(self):
        self.assertEqual(kinds.day("Friday", TODAY).value, "2026-11-13")
        self.assertEqual(kinds.day("2026-11-15", TODAY).value, "2026-11-15")
        self.assertEqual(kinds.day("next Sunday", TODAY).status, "none")  # on a Sunday that is two readings: the owner is asked which day

    def test_the_interpreter_check_lets_the_deal_argument_through(self):
        registry = load_registry()
        reply = {"ops": [{"op": "specials.add", "args": {"title": "Eggs", "deal": "2 for $5", "end": "2026-11-15"}}], "revises": None}
        self.assertEqual(interpret_check.check(copy.deepcopy(reply), registry, set()), reply)
        reply["ops"][0]["args"]["deal"] = 5
        self.assertIn("question", interpret_check.check(reply, registry, set()))  # a number is not a deal line
        reply["ops"][0]["args"]["title"] = "Eggs $3"
        reply["ops"][0]["args"]["deal"] = "2 for $5"
        self.assertEqual(interpret_check.check(reply, registry, set())["question"], interpret_check.PRICE_REPLY)  # the title still refuses a price


# -- end to end ---------------------------------------------------------------------------------------------------------
TOKEN = re.compile(r"\{d([+-]\d+)\}")


def _dated(value, today):
    if isinstance(value, str):
        return TOKEN.sub(lambda m: (today + timedelta(days=int(m.group(1)))).isoformat(), value)
    if isinstance(value, list):
        return [_dated(v, today) for v in value]
    if isinstance(value, dict):
        return {k: _dated(v, today) for k, v in value.items()}
    return value


def _seed(scratch, specials):
    """Save ``specials`` into the scratch worktree and commit it, so the row starts from a site that already has them."""
    path = scratch.wt / "hass" / "content" / "store.json"
    data = json.loads(path.read_text("utf-8"))
    data["specials"] = specials
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
    content = load_and_validate(scratch.wt / "hass" / "content", scratch.wt / "storefront-mockup")
    sitegen.write_files(sitegen.render(content, scratch.wt / "hass" / "templates"), scratch.wt)
    testkit._git(scratch.wt, "-c", "user.name=kit", "-c", "user.email=kit@example.invalid", "commit", "-q", "-a", "-m", "seed specials")


class EndToEndTests(unittest.TestCase):
    """Each row: the owner's words, the recorded interpreter reply, then the real draft, the wrong-code check, the yes, the exact diff
    and files, the undo back to the same tree and the plain-words check, as for every skill (hass/tests/fixtures/skills/README.md)."""

    rows = testkit.load_rows(E2E)

    def run_row(self, row):
        today = shop_today()
        seed = _dated(row.get("seed"), today)
        row = _dated({k: v for k, v in row.items() if k != "seed"}, today)
        by_name = {s.name: s for s in skills.load_skills().skills.values()}
        first = next((c["skill"] for r in row["replies"] for c in ([r] + r.get("calls", [])) if "skill" in c), None)

        class Seeded(testkit.Scratch):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                if seed:
                    _seed(self, seed)

        with mock.patch.object(testkit, "Scratch", Seeded):
            return testkit.run_case_row(row, by_name, by_name.get(first))

    def test_every_row(self):
        ran = []
        for row in self.rows:
            with self.subTest(row["id"]):
                result = self.run_row(row)
                self.assertEqual(result.problems, [], result.line())
                ran.append(result)
        self.assertEqual(len(ran), len(self.rows))
        drafts = [r for r in ran if r.facts.get("diff")]
        self.assertGreaterEqual(len(drafts), 10)
        for r in drafts:
            self.assertEqual(r.facts["undo"], "identical", r.id)  # nothing stays behind after an undo, so the skills declare no residue
        self.assertEqual({s.undo.residue for s in sp.SKILLS[:4]}, {"none"})

    def test_all_four_changing_skills_and_every_refusal_group_are_covered(self):
        used = {c["skill"] for row in self.rows for r in row["replies"] for c in ([r] + r.get("calls", [])) if "skill" in c}
        self.assertEqual(used, set(NAMES[:4]))
        kinds_ = {row["kind"] for row in self.rows}
        self.assertTrue({"clean", "multi", "refuse", "vague"} <= kinds_)
        text = E2E.read_text("utf-8")
        for needle in ("more than six specials", "already a special called", "Which special do you mean", "already says that", "finished on", "at most 31 days"):
            self.assertIn(needle, text)

    def test_the_rows_do_not_depend_on_the_calendar(self):
        raw = E2E.read_text("utf-8")
        self.assertIsNone(re.search(r"20\d\d-\d\d-\d\d", raw), "dates in e2e.jsonl are {d+N} offsets from the shop's today")


class GroundedEndToEndTests(unittest.TestCase):
    """The same checks with the owner's texts handed to the rules, the way the dispatcher does (the kit's own context has none):
    through the real Conversation and Editor on a scratch worktree, a wrong deal or a priced title never reaches a draft,
    and the exact deal still saves after ``yes`` and reads back unchanged from the store."""

    def go(self, text, skill, slots, seed=None):
        """(disposition, owner replies, the saved specials after a yes when a draft was made)."""
        registry = skills.load_skills().skills
        sc = testkit.Scratch({text: {"skill": skill, "slots": slots}}, registry)
        try:
            if seed:
                _seed(sc, seed)
            ctx_for = sc.interp.ctx_for

            def grounded():
                c = ctx_for()
                c.texts = [text]
                return c

            sc.interp.ctx_for = grounded
            disposition, replies = sc.say(text)
            saved = None
            if disposition == "proposed":
                _approved, _out = sc.say("yes " + sc.drafts()[-1]["code"])
                saved = json.loads((sc.wt / "hass/content/store.json").read_text("utf-8")).get("specials")
            return disposition, [voice.plain(r) for r in replies], saved, sc.drafts()
        finally:
            sc.close()

    def add_slots(self, title, deal):
        return {"title": title, "deal": deal, "start": shop_today().isoformat(), "end": (shop_today() + timedelta(days=3)).isoformat()}

    def edit_seed(self):
        today = shop_today()
        return [{"id": "honey", "title": "Honey", "deal": "buy one get one", "start": today.isoformat(),
                 "end": (today + timedelta(days=5)).isoformat(), "order": 0}]

    def test_add_keeps_the_exact_deal_and_refuses_a_cut_one_before_any_draft(self):
        text = "put honey on special, 12 for $5, until Friday"
        disposition, _replies, saved, _drafts = self.go(text, ADD, self.add_slots("Honey", "12 for $5"))
        self.assertEqual(disposition, "proposed")
        self.assertEqual([(x["title"], x["deal"]) for x in saved], [("Honey", "12 for $5")])
        for cut in ("2 for $5", "12 for", "12 for $", "2 for 5"):
            disposition, replies, saved, drafts = self.go(text, ADD, self.add_slots("Honey", cut))
            self.assertNotEqual(disposition, "proposed", cut)
            self.assertIsNone(saved, cut)
            self.assertEqual(drafts, [], cut)  # no draft was made at all
            self.assertTrue(any("exactly as you type it" in r for r in replies), (cut, replies))

    def test_edit_keeps_the_exact_deal_and_refuses_a_cut_one_before_any_draft(self):
        text = "change the honey special to 12 for $5"
        disposition, _replies, saved, _drafts = self.go(text, EDIT, {"special": "honey", "deal": "12 for $5"}, self.edit_seed())
        self.assertEqual(disposition, "proposed")
        self.assertEqual([x["deal"] for x in saved], ["12 for $5"])
        for cut in ("2 for $5", "12 for"):
            disposition, replies, saved, drafts = self.go(text, EDIT, {"special": "honey", "deal": cut}, self.edit_seed())
            self.assertNotEqual(disposition, "proposed", cut)
            self.assertIsNone(saved, cut)
            self.assertEqual(drafts, [], cut)
            self.assertTrue(any("exactly as you type it" in r for r in replies), (cut, replies))

    def test_add_and_edit_refuse_a_deal_missing_its_front_and_keep_the_whole_one(self):
        for skill, text, slots_for, seed in (
                (ADD, "put honey on special, buy one get one free, until Friday", lambda d: self.add_slots("Honey", d), None),
                (EDIT, "change the honey special to buy one get one free", lambda d: {"special": "honey", "deal": d}, self.edit_seed)):
            disposition, _replies, saved, _drafts = self.go(text, skill, slots_for("buy one get one free"), seed and seed())
            self.assertEqual(disposition, "proposed", skill)
            self.assertEqual([x["deal"] for x in saved], ["buy one get one free"], skill)  # the whole deal, read back from the store
            disposition, replies, saved, drafts = self.go(text, skill, slots_for("get one free"), seed and seed())
            self.assertNotEqual(disposition, "proposed", skill)
            self.assertEqual((saved, drafts), (None, []), skill)  # no draft, nothing saved
            self.assertTrue(any("exactly as you type it" in r for r in replies), (skill, replies))
        for skill, text, slots_for, seed in (
                (ADD, "put honey on special, 12 for $5, until Friday", lambda d: self.add_slots("Honey", d), None),
                (EDIT, "change the honey special to 12 for $5", lambda d: {"special": "honey", "deal": d}, self.edit_seed)):
            disposition, replies, saved, drafts = self.go(text, skill, slots_for("for $5"), seed and seed())
            self.assertNotEqual(disposition, "proposed", skill)
            self.assertEqual((saved, drafts), (None, []), skill)
            self.assertTrue(any("exactly as you type it" in r for r in replies), (skill, replies))

    def test_add_refuses_a_spelled_out_price_in_the_title_and_keeps_a_plain_one(self):
        text = "put Honey five dollars on special, buy one get one, until Friday"
        disposition, replies, saved, drafts = self.go(text, ADD, self.add_slots("Honey five dollars", "buy one get one"))
        self.assertNotEqual(disposition, "proposed")
        self.assertEqual((saved, drafts), (None, []))
        self.assertTrue(any("price can only go in the deal line" in r for r in replies), replies)
        disposition, _replies, saved, _drafts = self.go("put Five Star Honey on special, buy one get one, until Friday", ADD,
                                                          self.add_slots("Five Star Honey", "buy one get one"))
        self.assertEqual(disposition, "proposed")
        self.assertEqual([x["title"] for x in saved], ["Five Star Honey"])

    def test_edit_refuses_a_spelled_out_price_in_the_title_and_keeps_a_plain_one(self):
        text = "rename the honey special to Honey five dollars"
        disposition, replies, saved, drafts = self.go(text, EDIT, {"special": "honey", "title": "Honey five dollars"}, self.edit_seed())
        self.assertNotEqual(disposition, "proposed")
        self.assertEqual((saved, drafts), (None, []))
        self.assertTrue(any("price can only go in the deal line" in r for r in replies), replies)
        disposition, _replies, saved, _drafts = self.go("rename the honey special to Wildflower honey", EDIT,
                                                          {"special": "honey", "title": "Wildflower honey"}, self.edit_seed())
        self.assertEqual(disposition, "proposed")
        self.assertEqual([x["title"] for x in saved], ["Wildflower honey"])


if __name__ == "__main__":
    unittest.main()
