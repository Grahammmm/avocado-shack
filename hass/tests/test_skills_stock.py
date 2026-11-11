"""SKILLS-STOCK-1 tests: stock.set, stock.checked and stock.clear.

The case rows in hass/tests/fixtures/skills/stock/ are run by the generic kit tests (test_skills_plans, test_skills_cases).
This module adds what a row cannot do: rows start from a shop with no shelf check and no words, so the paths that need
an earlier approved change (the direct draft once today is checked, not-already-true, clear of a real word, undo of the
check day, a hidden product) are driven here on the same scratch shop with the real Conversation, Editor and sitegen.
Run: python3 -B -m unittest hass.tests.test_skills_stock -v
"""

import copy
import json
import types
import unittest
from datetime import timedelta
from pathlib import Path

from hass import live_policy, voice
from hass.content_model import REPO_ROOT
from hass.ops import KINDS as OP_KINDS, load_registry
from hass.skills import kinds, load_skills, model, openreq, skill_lint, stock, testkit
from hass.skills.model import lint_cases
from hass.tests.test_conversation import CHAT
from hass.tests.test_editor import git
from hass.tests.test_skill_dispatch import SkillCase

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

    def test_stock_items_is_a_plain_kind_only_stock_set_uses(self):  # RF0814-12
        self.assertIn("stock_items", model.SLOT_KINDS)
        for resolved_or_op in (model.SKILL_KINDS, tuple(kinds.RESOLVERS), OP_KINDS):
            self.assertNotIn("stock_items", resolved_or_op)
        self.assertEqual([(s.name, s.kind) for s in stock.STOCK_SET.slots], [("items", "stock_items")])
        self.assertEqual([(s.name, s.kind) for s in stock.STOCK_CLEAR.slots], [("items", "text_list")])
        self.assertEqual([s.kind for s in stock.STOCK_CHECKED.slots], ["day", "text_list", "text_list", "text_list"])


class PlanRules(unittest.TestCase):
    def test_set_conflicting_words_carries_question_kind_only(self):
        ctx = _ctx([_product()])
        slots = {"items": _items((EGGS, "no"), (EGGS, "limited"), (HASS, "yes"))}
        before = copy.deepcopy((slots, vars(ctx.content)))
        with self.assertRaises(stock.Refusal) as caught:
            stock.STOCK_SET.plan(slots, ctx)
        self.assertEqual(caught.exception.reply, stock.TWICE.format(name="Cal Poly eggs"))
        self.assertEqual(getattr(caught.exception, "kind", None), "question")
        self.assertIsInstance(caught.exception, ValueError)
        self.assertEqual((slots, vars(ctx.content)), before)
        self.assertEqual(stock.Refusal("unchanged").kind, "refuse")
        controls = [
            (stock.STOCK_SET, {"items": _items((EGGS, "no"))}, _ctx([_product(status=status)]))
            for status in ("held", "hidden")]
        controls += [
            (stock.STOCK_SET, {"items": _items(*((pid, "no") for pid in (*SIX, LEMONS)))}, ctx),
            (stock.STOCK_SET, {"items": _items((EGGS, "no"))},
             _ctx([_product(available="no", available_on="2026-11-08")])),
            (stock.STOCK_CLEAR, {"items": [EGGS]}, ctx),
            (stock.STOCK_CHECKED, {"in": [EGGS, EGGS]}, ctx),
            (stock.STOCK_CHECKED, {"in": [EGGS], "out": [EGGS]}, ctx)]
        for skill, args, context in controls:
            with self.subTest(skill=skill.name, args=args, context=context):
                before = copy.deepcopy((args, vars(context.content)))
                with self.assertRaises(stock.Refusal) as caught:
                    skill.plan(args, context)
                self.assertEqual(caught.exception.kind, "refuse")
                self.assertEqual((args, vars(context.content)), before)

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


T0_DAY = "2026-11-02"  # SkillCase's injected clock: Monday 2026-11-02 09:00 PST
SIX = (HASS, "photo-product-002", "photo-product-003", "photo-product-004", "photo-product-005", EGGS)
BAD_SHAPE = "I can't use that for the items: each one needs a product and in stock, low or sold out."


def _items(*pairs):
    return [{"product": pid, "availability": word} for pid, word in pairs]


class RealDispatcherStock(SkillCase):
    """RF0814-12: the PRODUCTION stock.set through the real dispatcher's slot validation (not the kit's SkillInterpreter),
    with the real Conversation and Editor on the H02 throwaway shop and SkillCase's injected clock. The model reply is the
    documented list of {product, availability} objects; nothing is written before the owner's own `yes <code>`."""
    SKILLS = (stock.STOCK_SET, stock.STOCK_CLEAR)

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")
        git(self.repo.wt, "commit", "-qam", f"seed {name}")  # the writer worktree is clean at each draft
        self.base = self.count()

    def checked_today(self):
        self.edit("store.json", lambda doc: doc.update(selection_checked_on=T0_DAY))

    def seed(self, pid, **fields):
        self.edit("products.json", lambda doc: next(p for p in doc["products"] if p["id"] == pid).update(fields))

    def tell(self, text, reply):
        self.script(text, reply)
        disposition = self.say(text)
        return disposition, "\n".join(self.replies())

    def set_items(self, text, items):
        return self.tell(text, {"skill": "stock.set", "slots": {"items": items}})

    def ops(self):
        return [(o["op"], o["args"]) for o in json.loads(self.drafts()[-1]["ops_json"])]

    def conflict(self, text="eggs are out and low, avocados are in", *, calls=False, pid=None):
        items = _items((EGGS, "no"), (EGGS, "limited"), (HASS, "yes"))
        call = {"skill": "stock.set", "slots": {"items": items}}
        self.script(text, {"calls": [call]} if calls else call)
        self.assertEqual(self.say(text, **({"pid": pid} if pid else {})), "question")
        req = self.live()
        self.assertIsNotNone(req)  # the clarification must retain its entire request
        self.assertEqual((req["skill"], req["slots"], req["texts"], req["asked_slot"], req["question"]),
                         ("stock.set", {"items": items}, [text], None, stock.TWICE.format(name="Cal Poly eggs")))
        self.assertEqual(self.replies(), [req["question"]])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()
        return req

    def test_real_set_conflict_keeps_request_and_model_snapshot(self):
        self.checked_today()
        req = self.conflict()
        self.conv = self.open()  # prove persisted context, not just in-memory state
        corrected = _items((EGGS, "limited"), (HASS, "yes"))
        self.assertEqual(self.set_items("low", corrected)[0], "proposed")
        text, recent = self.asked[-1]
        self.assertEqual((text, recent), ("low", {"skill": "stock.set", "slots": req["slots"],
                                              "question": req["question"], "earlier": req["texts"]}))
        self.assertEqual(self.live()["request_id"], req["request_id"])
        self.assertEqual(self.live()["slots"], {"items": corrected})
        self.assertEqual(self.ops(), [("product.set_availability", {"id": EGGS, "available": "limited"}),
                                     ("product.set_availability", {"id": HASS, "available": "yes"})])
        self.nothing_written()

    def test_real_set_conflict_one_call_envelope(self):
        self.checked_today()
        req = self.conflict(calls=True)
        corrected = _items((EGGS, "limited"), (HASS, "yes"))
        self.assertEqual(self.set_items("low", corrected)[0], "proposed")
        self.assertEqual(self.live()["request_id"], req["request_id"])
        self.assertEqual(self.ops(), [("product.set_availability", {"id": i["product"], "available": i["availability"]})
                                     for i in corrected])
        self.nothing_written()

    def test_set_conflict_keeps_queued_call_context(self):
        self.checked_today()
        req = self.conflict()
        queued = [{"skill": "stock.clear", "slots": {"items": [LEMONS]}}]
        # Existing queued context survives another unresolved plan and a conversation restart.
        self.conv.requests.put(CHAT, req["provider_id"], self.now, request_id=req["request_id"],
                               skill=req["skill"], slots=req["slots"], texts=req["texts"],
                               question=req["question"], calls=queued, asks=req["asks"])
        self.conv.db.commit()
        self.conv = self.open()
        self.assertEqual(self.tell("still unsure", {"skill": "stock.set", "slots": {}})[0], "question")
        self.assertEqual(self.live()["request_id"], req["request_id"])
        self.assertEqual(self.live()["slots"], req["slots"])
        self.assertEqual(self.live()["calls"], queued)
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_set_conflict_correction_preserves_shelf_confirmation(self):
        original = git(self.repo.wt, "rev-parse", "HEAD")
        self.conflict()
        disposition, reply = self.set_items("low", _items((EGGS, "limited"), (HASS, "yes")))
        self.assertEqual(disposition, "question")
        self.assertIn(SHELF_Q, reply)
        self.assertEqual(self.drafts(), [])
        self.nothing_written()
        self.assertEqual(self.say("yes"), "proposed")
        self.assertEqual(self.ops(), [("store.confirm_selection", {}),
                                     ("product.set_availability", {"id": EGGS, "available": "limited"}),
                                     ("product.set_availability", {"id": HASS, "available": "yes"})])
        self.nothing_written()
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.say("undo"), "proposed")
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(testkit.tree_diff(self.repo.wt, original)[1], [])

    def test_set_conflict_unresolved_and_cancel(self):
        self.checked_today()
        req = self.conflict()
        for number in range(2, openreq.MAX_UNRESOLVED + 1):
            disposition, reply = self.tell(f"still unsure {number}", {"skill": "stock.set", "slots": req["slots"]})
            self.assertEqual((disposition, reply), ("question", req["question"]))
            self.assertEqual((self.live()["request_id"], self.live()["slots"], self.live()["asks"]),
                             (req["request_id"], req["slots"], number))
        self.assertEqual(self.tell("still unsure again", {"skill": "stock.set", "slots": req["slots"]})[0], "backlog")
        self.assertIsNone(self.live())
        self.assertEqual(self.drafts(), [])
        self.nothing_written()
        self.conflict("eggs are both out and low, avocados in")
        self.assertEqual(self.tell("never mind", {"cancel": True})[0], "cancelled")
        self.assertIsNone(self.live())
        self.assertEqual(self.set_items("low", [])[0], "question")
        self.assertEqual(self.live()["slots"], {})
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_set_conflict_empty_slots_and_bare_approval_do_not_choose(self):
        self.checked_today()
        req = self.conflict()
        self.assertEqual(self.tell("low", {"skill": "stock.set", "slots": {}}), ("question", req["question"]))
        self.assertEqual(self.live()["slots"], req["slots"])
        self.say("yes")
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_set_conflict_duplicate_and_expired_request_do_not_continue(self):
        self.checked_today()
        req = self.conflict(pid="conflict-message")
        self.assertEqual(self.say(req["texts"][0], pid="conflict-message"), "duplicate")
        self.assertEqual(self.live(), req)
        self.now += timedelta(minutes=openreq.TTL_MINUTES + 1)
        self.assertEqual(self.tell("low", {"skill": "stock.set", "slots": {}})[0], "question")
        self.assertNotEqual(self.live()["request_id"], req["request_id"])
        self.assertEqual(self.live()["slots"], {})
        self.assertIsNone(self.asked[-1][1])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_structured_items_reach_shelf_check_and_direct_draft(self):
        disposition, reply = self.set_items("eggs are out", _items((EGGS, "no")))
        self.assertEqual(disposition, "question")
        self.assertIn(SHELF_Q, reply)
        self.assertEqual(self.drafts(), [])
        self.nothing_written()
        disposition = self.say("yes")
        self.assertEqual(disposition, "proposed")
        self.assertIn("also records that the shelf list was checked today", "\n".join(self.replies()))
        self.assertEqual(self.ops(), [("store.confirm_selection", {}), ("product.set_availability", {"id": EGGS, "available": "no"})])
        self.nothing_written()
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        # today is now checked: the one-call envelope is a direct draft of the word alone
        disposition, reply = self.tell("avocados are low", {"calls": [{"skill": "stock.set", "slots": {"items": _items((HASS, "limited"))}}]})
        self.assertEqual(disposition, "proposed", reply)
        self.assertNotIn("also records", reply)
        self.assertEqual(self.ops(), [("product.set_availability", {"id": HASS, "available": "limited"})])
        self.assertEqual(self.commits(), 1)

    def test_a_check_seeded_today_makes_it_a_direct_draft(self):
        self.checked_today()
        disposition, reply = self.set_items("eggs are out", _items((EGGS, "no")))
        self.assertEqual(disposition, "proposed", reply)
        self.assertNotIn(SHELF_Q, reply)
        self.assertEqual(self.ops(), [("product.set_availability", {"id": EGGS, "available": "no"})])
        self.nothing_written()

    def test_structured_items_invalid_shape_never_drafts(self):
        self.checked_today()  # a correct reply would be a direct draft, so only the shape can stop these
        good = {"product": EGGS, "availability": "no"}
        bad = (7, "eggs are out", [], {"product": EGGS, "availability": "no"}, [EGGS], [EGGS, good], [[EGGS, "no"]],
               [{"product": EGGS}], [{"availability": "no"}], [{**good, "count": 3}], [{"product": "Cal Poly eggs", "availability": "no"}],
               [{"product": 24, "availability": "no"}], [{"product": [EGGS], "availability": "no"}],
               [{"product": EGGS, "availability": "sold out"}], [{"product": EGGS, "availability": 0}],
               [{"product": EGGS, "availability": ["no"]}], [{"product": EGGS, "availability": {"no": 1}}], [good, None])
        for i, value in enumerate(bad):
            with self.subTest(value=value):
                disposition, reply = self.set_items(f"stock change number {i}", value)
                self.assertEqual(disposition, "question", reply)
                self.assertEqual(reply, BAD_SHAPE)
                self.assertNotIn("Traceback", reply)
                self.assertEqual(self.drafts(), [])
                self.nothing_written()
                self.conv.requests.close_live(CHAT, self.now)  # each bad reply is a fresh ask, not a third try at one
        disposition, reply = self.set_items("stock change with nothing", None)  # null: the required slot is asked for
        self.assertEqual((disposition, reply), ("question", "Which products, and in, low or out?"))
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_structured_items_keep_existing_stock_rules(self):
        self.checked_today()
        self.seed(LEMONS, status="hidden")
        self.seed(HONEY, available="no", available_on=T0_DAY)
        refusals = (
            (_items((EGGS, "no"), (EGGS, "yes")), stock.TWICE.format(name="Cal Poly eggs")),
            (_items(*((pid, "no") for pid in SIX), (LEMONS, "no")), stock.TOO_MANY.format(count=7)),
            (_items((HELD, "no")), stock.HELD.format(name="Raw milk white cheddar")),
            (_items((LEMONS, "no")), stock.HIDDEN.format(name="Lemons")),
            # RF0145-12: the dispatcher's ctx.today is a date, which the plan's ALREADY check now recognizes
            (_items((HONEY, "no")), stock.ALREADY.format(name="Big Sur Honey Company honey", word="Sold out")))
        for i, (items, words) in enumerate(refusals):
            with self.subTest(refusal=words):
                disposition, reply = self.set_items(f"refused stock change {i}", items)
                self.assertNotEqual(disposition, "proposed")
                self.assertEqual(reply, words)
                self.assertEqual(self.drafts(), [])
                self.conv.requests.close_live(CHAT, self.now)  # independent stock-rule cases, not continuation attempts
        self.nothing_written()
        disposition, reply = self.set_items("eggs are out, eggs are out", _items((EGGS, "no"), (EGGS, "no")))
        self.assertEqual(disposition, "proposed", reply)  # the same word twice is one change
        self.assertEqual(self.ops(), [("product.set_availability", {"id": EGGS, "available": "no"})])
        words = ("yes", "limited", "no", "limited", "yes", "limited")
        disposition, reply = self.set_items("six changes", _items(*zip(SIX, words)))
        self.assertEqual(disposition, "proposed", reply)
        self.assertEqual(self.ops(), [("product.set_availability", {"id": pid, "available": w}) for pid, w in zip(SIX, words)])
        self.nothing_written()
        # an unrelated text_list slot still takes only lines of text, never these objects
        disposition, reply = self.tell("clear the eggs", {"skill": "stock.clear", "slots": {"items": _items((EGGS, "no"))}})
        self.assertEqual((disposition, reply), ("question", "I can't use that for the items: that list has an empty or repeated line."))


if __name__ == "__main__":
    unittest.main()
