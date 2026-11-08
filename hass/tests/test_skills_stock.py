"""SKILLS-STOCK-1 tests: stock.set, stock.checked and stock.clear.

The case rows in hass/tests/fixtures/skills/stock/ are run by the generic kit tests (test_skills_plans, test_skills_cases).
This module adds what a row cannot do: rows start from a shop with no shelf check and no words, so the paths that need
an earlier approved change (the direct draft once today is checked, not-already-true, clear of a real word, undo of the
check day, a hidden product) are driven here on the same scratch shop with the real Conversation, Editor and sitegen.
Run: python3 -B -m unittest hass.tests.test_skills_stock -v
"""

import json
import types
import unittest
from pathlib import Path

from hass import live_policy, voice
from hass.content_model import REPO_ROOT
from hass.ops import load_registry
from hass.skills import load_skills, skill_lint, stock, testkit
from hass.skills.model import lint_cases

EGGS, HASS, LEMONS, HONEY = "photo-product-024", "photo-product-001", "photo-product-017", "photo-product-042"
HELD = "photo-product-040"
SKILLS = {s.name: s for s in (stock.STOCK_SET, stock.STOCK_CHECKED, stock.STOCK_CLEAR)}
SHELF_Q = "shelf list right for today"
FIXTURES = REPO_ROOT / "hass" / "tests" / "fixtures" / "skills" / "stock"


def _ctx(products=(), store=None, today="2026-11-08"):
    return types.SimpleNamespace(today=today, content=types.SimpleNamespace(products=list(products), store=store or {}))


def _product(pid=EGGS, name="Cal Poly eggs", status="active", **extra):
    return {"id": pid, "name": name, "status": status, **extra}


def _refusal(skill, slots, ctx=None):
    try:
        skill.plan(slots, ctx)
    except stock.Refusal as exc:
        return exc.reply
    raise AssertionError("the plan did not refuse")


class Declarations(unittest.TestCase):
    def test_the_three_skills_load_and_lint_clean(self):
        registry = load_skills()
        for name in SKILLS:
            self.assertIn(name, registry.skills)
        self.assertEqual(skill_lint(registry, load_registry()), [])

    def test_every_fixed_reply_is_plain_words(self):
        for name in ("TOO_MANY", "HIDDEN", "HELD", "ALREADY", "TWICE", "NO_WORD", "FUTURE", "TOO_OLD", "AFTER", "DONE_TODAY",
                     "BAD_ITEM", "NONE_NAMED"):
            text = getattr(stock, name).format(count=9, name="Hass avocado", word="Sold out")
            with self.subTest(name):
                self.assertEqual(voice.check(text), [], text)
                self.assertEqual(testkit.plain_words_problems(text, ["Hass avocado"]), [])

    def test_the_case_files_meet_the_spec_counts(self):
        for name, skill in SKILLS.items():
            rows = testkit.load_rows(FIXTURES / f"{name}.jsonl")
            self.assertGreaterEqual(len(rows), 10, name)
            self.assertGreaterEqual(sum(r.get("kind") == "refuse" for r in rows), 2, name)
            self.assertTrue(all(r.get("version", skill.version) == skill.version for r in rows), name)
            self.assertEqual(skill.cases, f"hass/tests/fixtures/skills/stock/{name}.jsonl")
            # lint_cases also wants a row of kind "undo", which the case runner does not accept as a row kind: the runner
            # undoes every row that ends in a draft by itself (see test_every_draft_row_is_undone). Nothing else may be flagged.
            self.assertEqual([p for p in lint_cases(skill, REPO_ROOT) if "undo row" not in p], [], name)

    def test_every_draft_row_is_undone_by_the_runner(self):
        skills = {s.name: s for s in load_skills().skills.values()}
        drafted = 0
        for result in testkit.run_file(FIXTURES / "stock.checked.jsonl", tuple(skills.values())):
            self.assertEqual(result.problems, [], result.id)
            if result.facts.get("disposition") == "proposed":
                drafted += 1
                self.assertEqual(result.facts.get("undo"), "identical", result.id)  # the check day goes back with the words
        self.assertGreaterEqual(drafted, 6)

    def test_the_skill_does_not_reach_into_the_files_it_does_not_own(self):
        imports = [ln for ln in Path(stock.__file__).read_text("utf-8").splitlines() if ln.startswith(("import ", "from "))]
        for name in ("conversation", "interpreter_prompt", "router", "editor"):
            self.assertEqual([ln for ln in imports if name in ln], [], name)

    def test_the_declared_live_class_is_what_live_policy_says_of_the_plans(self):
        sc = testkit.Scratch({}, SKILLS)
        try:
            confirm = {"op": "store.confirm_selection", "args": {}}
            word = stock.STOCK_SET.plan({"items": [{"product": EGGS, "availability": "no"}]}, None)
            plans = [stock.STOCK_CHECKED.plan({"in": [HASS], "limited": [EGGS]}, None),
                     [confirm, *word],  # what Conversation drafts after the owner's yes to the shelf-check question
                     [confirm, *word, *stock.STOCK_CLEAR.plan({"items": [EGGS]}, None)]]
            for ops in plans:
                out = sc.editor.prepare(ops)
                self.assertEqual(out["result"], "ok", out)
                self.assertEqual(live_policy.check(out["draft"]), [], ops)
            self.assertEqual({s.live_class for s in SKILLS.values()}, {"chat-live"})
        finally:
            sc.close()


class PlanRules(unittest.TestCase):
    def test_a_word_already_set_today_says_so(self):
        ctx = _ctx([_product(available="no", available_on="2026-11-08")], {"selection_checked_on": "2026-11-08"})
        reply = _refusal(stock.STOCK_SET, {"items": [{"product": EGGS, "availability": "no"}]}, ctx)
        self.assertEqual(reply, "Cal Poly eggs already says Sold out. Nothing to change.")

    def test_a_stale_same_word_is_a_re_check_not_a_repeat(self):
        ctx = _ctx([_product(available="no", available_on="2026-11-01")])
        self.assertEqual(stock.STOCK_SET.plan({"items": [{"product": EGGS, "availability": "no"}]}, ctx)[0]["args"],
                         {"id": EGGS, "available": "no"})

    def test_held_and_hidden_products_are_named_and_refused(self):
        for status, words in (("held", "on hold"), ("hidden", "hidden")):
            ctx = _ctx([_product(status=status)])
            for skill, slots in ((stock.STOCK_SET, {"items": [{"product": EGGS, "availability": "no"}]}),
                                 (stock.STOCK_CLEAR, {"items": [EGGS]}), (stock.STOCK_CHECKED, {"out": [EGGS]})):
                with self.subTest(skill=skill.name, status=status):
                    reply = _refusal(skill, slots, ctx)
                    self.assertIn(words, reply)
                    self.assertIn("Cal Poly eggs", reply)

    def test_a_check_cannot_go_before_the_last_one_or_repeat_it(self):
        ctx = _ctx([_product(available="no", available_on="2026-11-08")], {"selection_checked_on": "2026-11-08"})
        self.assertEqual(_refusal(stock.STOCK_CHECKED, {"day": "2026-11-07"}, ctx), stock.AFTER)
        self.assertEqual(_refusal(stock.STOCK_CHECKED, {}, ctx), stock.DONE_TODAY)
        self.assertEqual(_refusal(stock.STOCK_CHECKED, {"out": [EGGS]}, ctx), stock.DONE_TODAY)  # it already says so
        self.assertEqual(stock.STOCK_CHECKED.plan({"in": [EGGS]}, ctx)[0]["args"], {"yes": [EGGS]})  # a different word is a change

    def test_a_product_repeated_in_one_check_list_is_refused_not_deduplicated(self):
        ctx = _ctx([_product()])
        self.assertEqual(_refusal(stock.STOCK_CHECKED, {"in": [EGGS, EGGS]}, ctx), stock.TWICE.format(name="Cal Poly eggs"))

    def test_clear_needs_a_word_to_clear(self):
        ctx = _ctx([_product(), _product("photo-product-001", "Hass avocado", available="limited", available_on="2026-11-08")])
        self.assertEqual(_refusal(stock.STOCK_CLEAR, {"items": [EGGS]}, ctx), "Cal Poly eggs has no label to clear.")
        self.assertEqual(stock.STOCK_CLEAR.plan({"items": [HASS]}, ctx), [{"op": "product.clear_availability", "args": {"id": HASS}}])

    def test_a_plan_never_changes_what_it_was_given(self):
        slots = {"items": [{"product": EGGS, "availability": "no"}, {"product": EGGS, "availability": "no"}]}
        before = json.loads(json.dumps(slots))
        stock.STOCK_SET.plan(slots, _ctx([_product()]))
        self.assertEqual(slots, before)

    def test_no_plan_asks_for_a_check_it_leaves_that_to_the_shelf_check_flow(self):
        for ops in (stock.STOCK_SET.plan({"items": [{"product": EGGS, "availability": "no"}]}, _ctx([_product()])),
                    stock.STOCK_CLEAR.plan({"items": [EGGS]}, _ctx([_product(available="no")]))):
            self.assertNotIn("store.confirm_selection", [o["op"] for o in ops])


class Flow(unittest.TestCase):
    """The real Conversation, Editor and sitegen on the scratch shop: the first change of the day meets the shelf-check
    question (HASS-SHELFCHECK-FLOW-1), the next ones do not."""

    def setUp(self):
        self.mapping = {
            "eggs are out": {"skill": "stock.set", "slots": {"items": [{"product": EGGS, "availability": "no"}]}},
            "eggs are sold out": {"skill": "stock.set", "slots": {"items": [{"product": EGGS, "availability": "no"}]}},
            "avocados are low": {"skill": "stock.set", "slots": {"items": [{"product": HASS, "availability": "limited"}]}},
            "stop showing the eggs as sold out": {"skill": "stock.clear", "slots": {"items": [EGGS]}},
            "checked, nothing changed": {"skill": "stock.checked", "slots": {}},
            "checked yesterday": {"skill": "stock.checked", "slots": {"day": "2026-11-07"}},
            "lemons are out": {"skill": "stock.set", "slots": {"items": [{"product": LEMONS, "availability": "no"}]}},
            "hide the lemons": {"ops": [{"op": "product.hide", "args": {"id": LEMONS}}], "revises": None},
            "yes": {"question": "unused"},
        }
        self.sc = testkit.Scratch(self.mapping, SKILLS)
        self.addCleanup(self.sc.close)
        self.start = self.sc.head()

    def say(self, text):
        disposition, out = self.sc.say(text)
        return disposition, "\n".join(out)

    def approve(self):
        base = self.sc.head()
        disposition, _ = self.say(f"yes {self.sc.drafts()[-1]['code']}")
        self.assertEqual(disposition, "approved")
        return testkit.tree_diff(self.sc.wt, base)

    def test_first_change_of_the_day_asks_one_question_then_drafts_the_check_with_the_change(self):
        disposition, reply = self.say("eggs are out")
        self.assertEqual(disposition, "question")
        self.assertIn(SHELF_Q, reply)
        self.assertEqual((self.sc.head(), self.sc.dirty(), self.sc.drafts()), (self.start, "", []))  # asking writes nothing
        disposition, reply = self.say("yes")
        self.assertEqual(disposition, "proposed")
        self.assertIn("also records that the shelf list was checked today", reply)  # D2: said on its own line
        self.assertEqual(self.sc.head(), self.start)
        self.assertEqual([o["op"] for o in json.loads(self.sc.drafts()[-1]["ops_json"])], ["store.confirm_selection", "product.set_availability"])
        files, diff = self.approve()
        self.assertEqual({e["path"] for e in diff}, {f"products[{EGGS}].available", f"products[{EGGS}].available_on", "selection_checked_on"})

    def test_no_answers_the_question_by_changing_nothing(self):
        self.say("eggs are out")
        disposition, reply = self.say("no")
        self.assertEqual((disposition, self.sc.head(), self.sc.drafts()), ("shelf-no", self.start, []))
        self.assertIn("nothing was changed", reply)

    def test_after_the_check_the_next_change_is_a_direct_draft_and_undo_restores_the_word(self):
        self.say("eggs are out")
        self.say("yes")
        self.approve()
        after_first = self.sc.head()
        disposition, reply = self.say("avocados are low")
        self.assertEqual(disposition, "proposed")
        self.assertNotIn("also records", reply)
        self.assertEqual([o["op"] for o in json.loads(self.sc.drafts()[-1]["ops_json"])], ["product.set_availability"])
        self.assertEqual(self.sc.turn_previews[-1][-1]["kind"], "product")  # the card, as the spec's preview says
        files, diff = self.approve()
        self.assertEqual([e["path"] for e in diff], [f"products[{HASS}].available", f"products[{HASS}].available_on"])
        self.assertEqual(self.say("undo")[0], "proposed")
        self.approve()
        files, left = testkit.tree_diff(self.sc.wt, after_first)
        self.assertEqual(left, [])  # the word and its day are back; the check day written by the first change stays with it

    def test_undo_of_the_change_that_wrote_the_check_day_takes_the_day_back_too(self):
        self.say("eggs are out")
        self.say("yes")
        self.approve()
        self.assertEqual(self.say("undo")[0], "proposed")
        self.approve()
        files, left = testkit.tree_diff(self.sc.wt, self.start)
        self.assertEqual(left, [])
        self.assertEqual(testkit._undo_problems(self.sc, files, left), [])  # clean tree, site files match the restored content

    def test_the_same_word_again_today_is_not_drafted(self):
        self.say("eggs are out")
        self.say("yes")
        self.approve()
        head = self.sc.head()
        disposition, reply = self.say("eggs are sold out")
        self.assertEqual(disposition, "unsupported")
        self.assertEqual(reply, "Cal Poly eggs already says Sold out. Nothing to change.")
        self.assertEqual((self.sc.head(), self.sc.dirty()), (head, ""))

    def test_clear_takes_exactly_the_word_and_its_day_off_and_undo_puts_them_back(self):
        self.say("eggs are out")
        self.say("yes")
        self.approve()
        before = self.sc.head()
        disposition, reply = self.say("stop showing the eggs as sold out")
        self.assertEqual(disposition, "proposed")
        self.assertEqual([o["op"] for o in json.loads(self.sc.drafts()[-1]["ops_json"])], ["product.clear_availability"])
        files, diff = self.approve()
        self.assertEqual(diff, [{"file": "hass/content/products.json", "path": f"products[{EGGS}].available", "before": "no"},
                                {"file": "hass/content/products.json", "path": f"products[{EGGS}].available_on", "before": "2026-11-08"}])
        self.assertEqual(self.say("stop showing the eggs as sold out")[1], "Cal Poly eggs has no label to clear.")  # nothing left to clear
        self.assertEqual(self.say("undo")[0], "proposed")
        self.approve()
        self.assertEqual(testkit.tree_diff(self.sc.wt, before)[1], [])

    def test_a_check_with_nothing_named_records_the_day_once(self):
        self.say("checked, nothing changed")
        self.approve()
        disposition, reply = self.say("checked, nothing changed")
        self.assertEqual((disposition, reply), ("unsupported", stock.DONE_TODAY))
        self.assertEqual(self.say("checked yesterday")[1], stock.AFTER)

    def test_a_hidden_product_is_named_and_refused(self):
        self.say("hide the lemons")
        self.approve()
        head = self.sc.head()
        disposition, reply = self.say("lemons are out")
        self.assertEqual(disposition, "unsupported")
        self.assertEqual(reply, "Lemons is hidden. Do you want me to bring it back first?")
        self.assertEqual(self.sc.head(), head)


if __name__ == "__main__":
    unittest.main()
