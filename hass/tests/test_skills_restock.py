"""AV1109-04: the stock.restock skill (reports/hass/SKILLS-SPEC.md 3.8) over AV1109-03's product.set_restock.

Proves the declaration and the ten sentence rows, the pure plan and its refusals (past, +61, hidden, held, unknown, same day,
nothing to clear, a quantity), the strict voice of every fixed sentence, and the real dispatcher, Conversation and Editor path:
a raw day phrase computed from today and shown before the yes, clear without a day, a quantity never stored, two products in one
draft, the private-only live refusal, and apply + undo that leave the shelf word, the site and the stored files as they were.
The case rows themselves run through the kit: python3 -B hass/skills/testkit.py run hass/tests/fixtures/skills/restock/stock.restock.jsonl
Run: python3 -B -m unittest hass.tests.test_skills_restock -v
"""
import copy
import json
import sys
import types
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest import mock

from hass import conversation, editor, live_policy, morning_report, voice
from hass.content_model import REPO_ROOT, load_and_validate, shop_today
from hass.ops import load_registry
from hass.skills import dispatch, load_skills, restock as rs, skill_lint, testkit
from hass.skills.model import Registry, lint_plan_output

CONTENT = load_and_validate(REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup")
HONEY, EGGS, LEMONS, HELD = "photo-product-042", "photo-product-024", "photo-product-017", "photo-product-040"
HONEY_NAME, EGGS_NAME = "Big Sur Honey Company honey", "Cal Poly eggs"
CASES = REPO_ROOT / rs.STOCK_RESTOCK.cases
SENTENCES = ("more honey coming Thursday", "egs back on firday", "restock the lemons on the 14th", "honey and eggs both back Thursday",
             "more soon", "the bread truck comes Monday", "more honey last Tuesday", "never mind about the honey restock",
             "eggs back in 2 weeks", "restock 40 jars of honey")  # SKILLS-SPEC 3.8, in order


def ctx(*texts, content=CONTENT, today="2026-11-08"):
    return SimpleNamespace(today=today, content=content, texts=list(texts))


def with_product(pid, **fields):
    content = copy.deepcopy(CONTENT)
    next(p for p in content.products if p["id"] == pid).update(fields)
    return content


def refusal(slots, *texts, **extra):
    with unittest.TestCase().assertRaises(rs.Refusal) as caught:
        rs.STOCK_RESTOCK.plan(slots, ctx(*texts, **extra))
    return caught.exception


def set_op(pid, day):
    return [{"op": "product.set_restock", "args": {"id": pid, "restock_on": day}}]


class Declaration(unittest.TestCase):
    def test_discovered_lints_private_only_and_one_row_per_sentence(self):
        registry, ops = load_skills(), load_registry()
        skill = rs.STOCK_RESTOCK
        self.assertIs(registry.get("stock.restock"), skill)
        self.assertEqual(skill_lint(registry, ops), [])
        self.assertEqual(skill_lint([skill], ops, repo_root=REPO_ROOT), [])
        self.assertEqual(lint_plan_output(skill, skill.plan({"item": HONEY, "day": "2026-11-12"}, ctx()), ops), [])
        self.assertEqual((skill.label, skill.live_class, skill.preview, skill.approval, skill.side_effects, skill.undo.mode),
                         ("record when more is coming", "private-only", "none", "owner-yes", ("restock-date",), "revert"))
        self.assertEqual(skill.edits, (("hass/content/products.json", "products[id].restock_on"),))
        self.assertEqual([(s.name, s.kind, s.required, s.ask) for s in skill.slots],
                         [("item", "product_ref", True, "Which product?"), ("day", "day", "unless:clear", "What day is more coming?"),
                          ("clear", "bool", False, "")])
        texts = {t for line in CASES.read_text("utf-8").splitlines() if line.strip() for t in json.loads(line).get("texts", [])}
        self.assertTrue(set(SENTENCES) <= texts, set(SENTENCES) - texts)  # every sentence of 3.8 has its own row
        self.assertEqual([t.text for t in skill.triggers], list(SENTENCES))

    def test_every_owner_sentence_passes_the_voice_rules(self):
        fixed = [rs.ASK_ITEM, rs.ASK_DAY, rs.COUNTS, rs.COUNTS_REFUSED, rs.UNKNOWN, rs.TOO_FAR, rs.NOT_BOTH, rs.SHELF_SAME,
                 rs.COUNTS + " " + rs.ASK_DAY, rs.COUNTS + " " + rs.ASK_ITEM]
        fixed += [reply.format(name=rs._q("Honey"), when="Thu Nov 12") for _why, reply in rs.STOCK_RESTOCK.refuse]
        fixed += [refusal({"item": HELD, "day": "2026-11-12"}).reply, refusal({"item": HONEY, "day": "2026-11-03"}).reply]
        for text in fixed:
            with self.subTest(text=text):
                self.assertEqual(voice.check(voice.plain(text)), [])
                self.assertEqual(testkit.plain_words_problems(voice.plain(text)), [])
                self.assertLessEqual(text.count("?"), 1, "one question at a time")


class Plan(unittest.TestCase):
    def test_today_and_sixty_days_are_in_the_window_and_the_op_is_exact(self):
        for day in ("2026-11-08", "2026-11-12", "2027-01-07"):
            with self.subTest(day=day):
                self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": day}, ctx()), set_op(HONEY, day))
        self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": "2026-11-12"}, ctx(content=None)), set_op(HONEY, "2026-11-12"))  # the op judges the product
        self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": "2026-11-12"}, ctx(today=date(2026, 11, 8))),
                         set_op(HONEY, "2026-11-12"))  # the dispatcher's date as well as the kit's ISO text

    def test_past_plus61_and_a_missing_day_or_today_refuse_or_ask_without_a_guess(self):
        self.assertIn("Sat Nov 7 has already passed", refusal({"item": HONEY, "day": "2026-11-07"}).reply)
        self.assertEqual(refusal({"item": HONEY, "day": "2027-01-08"}).reply, rs.TOO_FAR)
        for slots, extra in (({"item": HONEY}, {}), ({"item": HONEY, "day": "soon"}, {}), ({"item": HONEY, "day": "2026-02-30"}, {}),
                             ({"item": HONEY, "day": "2026-11-12"}, {"today": None}), ({"item": HONEY, "day": "2026-11-12"}, {"today": "later"})):
            with self.subTest(slots=slots, extra=extra):
                err = refusal(slots, **extra)
                self.assertEqual((err.reply, err.kind), (rs.ASK_DAY, "question"))
        self.assertEqual((refusal({"day": "2026-11-12"}).reply, refusal({"item": "Honey!", "day": "2026-11-12"}).kind), (rs.ASK_ITEM, "question"))

    def test_hidden_held_unknown_same_day_and_nothing_to_clear_change_nothing(self):
        held = refusal({"item": HELD, "day": "2026-11-12"}).reply
        self.assertEqual(voice.plain(held), "I can't change Raw milk white cheddar right now. It is on hold until someone has looked at it.")
        hidden = refusal({"item": HONEY, "day": "2026-11-12"}, content=with_product(HONEY, status="hidden")).reply
        self.assertEqual(voice.plain(hidden), f"{HONEY_NAME} is hidden. Do you want me to bring it back first?")
        self.assertEqual(refusal({"item": "photo-product-999", "day": "2026-11-12"}).reply, rs.UNKNOWN)
        same = with_product(HONEY, restock_on="2026-11-12")
        self.assertIn("already says more is expected Thu Nov 12", voice.plain(refusal({"item": HONEY, "day": "2026-11-12"}, content=same).reply))
        self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": "2026-11-13"}, ctx(content=same)), set_op(HONEY, "2026-11-13"))
        self.assertIn("has no restock day to clear", voice.plain(refusal({"item": HONEY, "clear": True}).reply))
        self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "clear": True}, ctx(content=same)),
                         [{"op": "product.set_restock", "args": {"id": HONEY, "clear": True}}])
        self.assertEqual(refusal({"item": HONEY, "day": "2026-11-12", "clear": True}).reply, rs.NOT_BOTH)

    def test_quantity_never_enters_a_date_and_a_date_is_never_a_quantity(self):
        self.assertEqual(refusal({"item": HONEY, "day": "2026-11-12"}, "restock 40 jars of honey on Thursday").reply, rs.COUNTS_REFUSED)
        self.assertEqual(refusal({"item": HONEY}, "restock 40 jars of honey").reply, rs.COUNTS + " " + rs.ASK_DAY)
        self.assertEqual(refusal({"item": HONEY, "clear": True}, "never mind the 2 dozen jars").reply, rs.COUNTS_REFUSED)
        for text in ("eggs back in 2 weeks", "restock the lemons on the 14th", "more honey on Nov 12", "back 1/2 way", "honey 2026-11-12"):
            with self.subTest(text=text):
                self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": "2026-11-12"}, ctx(text)), set_op(HONEY, "2026-11-12"))
        self.assertIsNone(rs.question("day", {}, ctx("eggs back in 2 weeks")))
        self.assertEqual(rs.question("item", {}, ctx("restock 40 jars of honey")), rs.COUNTS + " " + rs.ASK_ITEM)
        self.assertIsNone(rs.question("day", {}, None))


# -- the real dispatcher, Conversation and Editor ------------------------------------------------------------------------
class _Interp(conversation.FixtureInterpreter):
    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        return super().interpret(text, pending)


class Chat:
    """One owner conversation on the throwaway repo with the real dispatcher, stock.restock the only skill."""

    def __init__(self, setup=None):
        self.kit = testkit.Scratch({}, {"stock.restock": rs.STOCK_RESTOCK}, setup=setup)
        self.kit.conv.db.close()
        cfg = json.loads((self.kit.repo.state / "config.json").read_text("utf-8"))
        editor._write_json(self.kit.repo.state / "config.json", {**cfg, "settings": {**cfg["settings"], "skills": {"mode": "both"}}})
        self.now, self.n, self.out = testkit.START, 0, self.kit.out
        self.interp = _Interp({})
        router = types.ModuleType("hass.skills.router")
        router.candidates = lambda text, hints=None, open_request=None, attachment=None, skills=(): [("stock.restock", 10.0)]
        self._patch = mock.patch.dict(sys.modules, {"hass.skills.router": router})
        self._patch.start()
        self.conv = conversation.Conversation(str(self.kit.repo.state), self.kit.editor, self.interp, lambda: self.now, self.kit.previewer,
                                              skills=Registry(skills={"stock.restock": rs.STOCK_RESTOCK}))
        self.base = self.head()

    def close(self):
        self._patch.stop()
        self.conv.db.close()
        self.kit.close()

    def say(self, text, reply=None, calls=None):
        if calls is not None:
            self.interp.mapping[text] = {"calls": [{"skill": "stock.restock", "slots": s} for s in calls], "revises": None}
        elif reply is not None:
            self.interp.mapping[text] = {"skill": "stock.restock", "slots": reply, "revises": None}
        self.n += 1
        self.now += timedelta(minutes=1)
        disposition = self.conv.handle(conversation.Inbound(f"rs-{self.n}", testkit.CHAT, testkit.OWNER, text, False, "new", self.now.isoformat()))
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return disposition, "\n".join(row["text"] for row in self.out.sent[before:])

    def yes(self):
        return self.say(f"yes {self.drafts()[-1]['code']}")

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def head(self):
        return testkit._git(self.kit.wt, "rev-parse", "HEAD").strip()

    def product(self, pid):
        products = json.loads((self.kit.wt / "hass" / "content" / "products.json").read_text("utf-8"))["products"]
        return next(p for p in products if p["id"] == pid)

    def report(self):
        content = load_and_validate(self.kit.wt / "hass" / "content", self.kit.wt / "storefront-mockup")
        return voice.plain(morning_report.render(morning_report.facts(content, shop_today(self.now))))


class RealDispatcher(unittest.TestCase):
    def open(self, **kw):
        chat = Chat(**kw)
        self.addCleanup(chat.close)
        return chat

    def test_relative_day_is_computed_said_before_yes_and_written_only_after_it(self):
        chat = self.open()
        d, r = chat.say("eggs back in 2 weeks", {"item": EGGS_NAME, "day": "in 2 weeks"})
        self.assertEqual(d, "proposed")
        self.assertIn("Cal Poly eggs: more expected Sun Nov 22", r)  # Sunday 2026-11-08 plus 14 days, in the report's own wording
        self.assertIn(rs.SHELF_SAME, r)
        self.assertEqual((chat.head(), chat.product(EGGS).get("restock_on")), (chat.base, None))
        self.assertEqual(json.loads(chat.drafts()[-1]["ops_json"]), set_op(EGGS, "2026-11-22"))
        d, r = chat.say("restock the lemons on the 14th", {"item": "Lemons", "day": "the 14th"})  # a date, not a count
        self.assertEqual(json.loads(chat.drafts()[-1]["ops_json"]), set_op(LEMONS, "2026-11-14"))

    def test_apply_and_undo_leave_the_shelf_the_site_and_the_files_as_they_were(self):
        chat = self.open()
        before = {p: (chat.kit.wt / p).read_bytes() for p in ("storefront-mockup/index.html", "storefront-mockup/catalog-products.js")}
        old = chat.product(EGGS)
        self.assertNotIn("Cal Poly eggs: more expected", chat.report())
        chat.say("eggs back Thursday", {"item": EGGS_NAME, "day": "Thursday"})
        chat.yes()
        new = chat.product(EGGS)
        self.assertEqual({k: v for k, v in new.items() if k != "restock_on"}, old)  # the shelf word and every other field are untouched
        self.assertEqual(new["restock_on"], "2026-11-12")
        self.assertIn("Cal Poly eggs: more expected Thu Nov 12", chat.report())
        self.assertEqual({p: (chat.kit.wt / p).read_bytes() for p in before}, before)  # the public site is byte-identical
        changed = testkit._git(chat.kit.wt, "diff", "--name-only", chat.base, "HEAD").split()
        self.assertEqual(changed, ["hass/content/products.json"])
        chat.say("undo")
        chat.yes()
        self.assertEqual(chat.product(EGGS), old)
        self.assertNotIn("Cal Poly eggs: more expected", chat.report())
        self.assertEqual(testkit._git(chat.kit.wt, "status", "--porcelain").strip(), "")

    def test_clear_does_not_ask_for_a_day(self):
        chat = self.open(setup=[{"op": "product.set_restock", "args": {"id": HONEY, "restock_on": "2026-11-12"}}])
        d, r = chat.say("never mind about the honey restock", {"item": HONEY_NAME, "clear": True})
        self.assertEqual(d, "proposed", r)
        self.assertEqual(json.loads(chat.drafts()[-1]["ops_json"]), [{"op": "product.set_restock", "args": {"id": HONEY, "clear": True}}])
        chat.yes()
        self.assertNotIn("restock_on", chat.product(HONEY))
        d, r = chat.say("never mind about the lemons restock", {"item": "Lemons", "clear": True})  # nothing is set on the lemons
        self.assertNotEqual(d, "proposed")
        self.assertIn("has no restock day to clear", r)

    def test_a_missing_day_asks_and_the_answer_goes_on_and_a_quantity_is_never_stored(self):
        chat = self.open()
        d, r = chat.say("more soon", {"item": HONEY_NAME})
        self.assertEqual((d, r), ("question", rs.ASK_DAY))
        d, r = chat.say("Thursday", {"day": "Thursday"})
        self.assertEqual(d, "proposed")
        self.assertEqual(json.loads(chat.drafts()[-1]["ops_json"]), set_op(HONEY, "2026-11-12"))
        chat = self.open()  # a quantity: the one question carries the counts sentence, the answer cannot store it
        d, r = chat.say("restock 40 jars of honey", {"item": HONEY_NAME})
        self.assertEqual((d, r), ("question", rs.COUNTS + " " + rs.ASK_DAY))
        d, r = chat.say("Thursday", {"day": "Thursday"})
        self.assertEqual((d, r), ("refused", rs.COUNTS_REFUSED))
        self.assertEqual((chat.drafts(), chat.head()), ([], chat.base))

    def test_past_and_far_and_held_refuse_with_no_draft_and_no_write(self):
        chat = self.open()
        for text, slots, said in (("more honey last Tuesday", {"item": HONEY_NAME, "day": "2026-11-03"}, "has already passed"),
                                  ("more honey in March", {"item": HONEY_NAME, "day": "2027-03-02"}, "up to 60 days ahead"),
                                  ("restock the raw milk cheese Friday", {"item": "Raw milk white cheddar", "day": "2026-11-13"}, "on hold")):
            with self.subTest(text=text):
                d, r = chat.say(text, slots)
                self.assertEqual(d, "refused")
                self.assertIn(said, r)
                self.assertEqual((chat.drafts(), chat.head()), ([], chat.base))

    def test_two_products_in_one_message_are_one_draft_one_yes_and_one_undo(self):
        chat = self.open()
        d, r = chat.say("honey and eggs both back Thursday", calls=[{"item": HONEY_NAME, "day": "Thursday"}, {"item": EGGS_NAME, "day": "Thursday"}])
        self.assertEqual((d, len(chat.drafts())), ("proposed", 1))
        self.assertEqual(json.loads(chat.drafts()[-1]["ops_json"]), set_op(HONEY, "2026-11-12") + set_op(EGGS, "2026-11-12"))
        self.assertEqual(chat.head(), chat.base)
        chat.yes()
        self.assertEqual((chat.product(HONEY)["restock_on"], chat.product(EGGS)["restock_on"]), ("2026-11-12", "2026-11-12"))
        chat.say("undo")
        chat.yes()
        self.assertEqual((chat.product(HONEY).get("restock_on"), chat.product(EGGS).get("restock_on")), (None, None))

    def test_the_draft_stays_outside_the_live_boundary_until_the_operator_lists_it(self):
        chat = self.open()
        out = chat.kit.editor.prepare(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": "2026-11-12"}, chat.kit._ctx()))
        self.assertEqual(out["result"], "ok", out)
        self.assertEqual(live_policy.check(out["draft"]), ["not live: product.set_restock"])
        self.assertEqual(rs.STOCK_RESTOCK.live_class, "private-only")
        self.assertIn("stock", dispatch.GROUP_OPS)


class CalendarEnd(unittest.TestCase):
    """RF0015-9: the 60-day window is a difference of days, so it never builds a date past 9999-12-31."""

    def test_plan_accepts_representable_days_at_calendar_end(self):
        for today, day in (("9999-12-01", "9999-12-31"), ("9999-12-31", "9999-12-31")):
            for form in (today, date.fromisoformat(today)):
                with self.subTest(today=today, day=day, form=type(form).__name__):
                    self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": day}, ctx(today=form)), set_op(HONEY, day))
        self.assertIn("has already passed", refusal({"item": HONEY, "day": "9999-12-30"}, today="9999-12-31").reply)

    def test_sixty_and_sixty_one_day_boundaries_unchanged(self):
        self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": "2028-02-29"}, ctx(today="2027-12-31")), set_op(HONEY, "2028-02-29"))
        self.assertEqual(refusal({"item": HONEY, "day": "2028-03-01"}, today="2027-12-31").reply, rs.TOO_FAR)
        self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "day": "2027-01-07"}, ctx()), set_op(HONEY, "2027-01-07"))
        self.assertEqual(refusal({"item": HONEY, "day": "2027-01-08"}).reply, rs.TOO_FAR)
        same = with_product(HONEY, restock_on="9999-12-31")
        self.assertIn("already says", voice.plain(refusal({"item": HONEY, "day": "9999-12-31"}, content=same, today="9999-12-31").reply))

    def test_notes_at_calendar_end_use_existing_report_wording(self):
        out = rs.notes("stock.restock", {"item": HONEY, "day": "9999-12-31"}, ctx(today="9999-12-31"))
        self.assertEqual(out, {"say": [rs.restock_text(HONEY_NAME, "9999-12-31") + ".", rs.SHELF_SAME]})

    def test_calendar_end_clear_and_refusals_preserve_state(self):
        before = copy.deepcopy(CONTENT.products)
        end = {"today": "9999-12-31"}
        self.assertEqual(rs.STOCK_RESTOCK.plan({"item": HONEY, "clear": True}, ctx(content=with_product(HONEY, restock_on="9999-12-31"), **end)),
                         [{"op": "product.set_restock", "args": {"id": HONEY, "clear": True}}])
        self.assertIn("has no restock day to clear", voice.plain(refusal({"item": HONEY, "clear": True}, **end).reply))
        self.assertEqual(refusal({"item": HONEY, "day": "9999-12-31", "clear": True}, **end).reply, rs.NOT_BOTH)
        self.assertIn("on hold", voice.plain(refusal({"item": HELD, "day": "9999-12-31"}, **end).reply))
        self.assertIn("is hidden", voice.plain(refusal({"item": HONEY, "day": "9999-12-31"}, content=with_product(HONEY, status="hidden"), **end).reply))
        self.assertEqual(refusal({"item": "photo-product-999", "day": "9999-12-31"}, **end).reply, rs.UNKNOWN)
        self.assertEqual(CONTENT.products, before)


if __name__ == "__main__":
    unittest.main()
