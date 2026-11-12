"""RF0145-12: stock.set and stock.checked recognize the dispatcher's Pacific date object as today.

Production dispatch builds Ctx.today with content_model.shop_today (a datetime.date); the fixtures use ISO strings. Both
must give the same day-window and already-true answers. Run: python3 -B -m unittest hass.tests.test_stock_today_date -v
"""

import copy
import json
import types
import unittest
from datetime import date, datetime, timedelta, timezone

from hass.skills import dispatch, stock
from hass.tests.test_editor import git
from hass.tests.test_skill_dispatch import SkillCase

EGGS = "photo-product-024"
TODAY = date(2026, 11, 2)
SET = stock.STOCK_SET
CHECKED = stock.STOCK_CHECKED


def _ctx(today, products=(), store=None):
    return types.SimpleNamespace(today=today, content=types.SimpleNamespace(
        products=list(products), store=store or {}))


def _eggs(**extra):
    return {"id": EGGS, "name": "Cal Poly eggs", "status": "active", **extra}


def _both(fn):
    """The answer (ops or refusal reply) for a date-object and an ISO-string today; they must agree."""
    out = []
    for today in (TODAY, TODAY.isoformat()):
        out.append(fn(today))
    return out


def _run(skill, slots, ctx):
    try:
        return skill.plan(slots, ctx)
    except stock.Refusal as exc:
        return exc.reply


class PureParity(unittest.TestCase):
    def test_today_accepts_production_date_and_preserves_string_compatibility(self):
        self.assertEqual(stock._today(_ctx(TODAY)), TODAY)
        self.assertEqual(stock._today(_ctx("2026-11-02")), TODAY)
        for bad in (None, "", "2026-13-40", "yesterday", 20261102, ["2026-11-02"], {"d": 1},
                    datetime(2026, 11, 2, 9, 0)):
            with self.subTest(bad=bad):
                self.assertIsNone(stock._today(_ctx(bad)))
        self.assertIsNone(stock._today(types.SimpleNamespace()))
        ctx = _ctx(TODAY)
        stock._today(ctx)
        self.assertIs(ctx.today, TODAY)

    def test_set_already_true_uses_same_day_for_both_context_types(self):
        slots = {"items": [{"product": EGGS, "availability": "no"}]}
        said = "Cal Poly eggs already says Sold out. Nothing to change."
        for today in (TODAY, TODAY.isoformat()):
            with self.subTest(today=type(today).__name__):
                now = _ctx(today, [_eggs(available="no", available_on="2026-11-02")])
                before = copy.deepcopy((slots, vars(now.content)))
                self.assertEqual(_run(SET, slots, now), said)
                self.assertEqual((slots, vars(now.content)), before)
                stale = _ctx(today, [_eggs(available="no", available_on="2026-11-01")])
                self.assertEqual(_run(SET, slots, stale)[0]["args"], {"id": EGGS, "available": "no"})
                other = _ctx(today, [_eggs(available="yes", available_on="2026-11-02")])
                self.assertEqual(_run(SET, slots, other)[0]["args"], {"id": EGGS, "available": "no"})

    def test_checked_window_and_default_day_match_string_context(self):
        for offset, expect in ((0, "ok"), (-1, "ok"), (-7, "ok"), (-8, stock.TOO_OLD), (1, stock.FUTURE)):
            day = (TODAY + timedelta(days=offset)).isoformat()
            results = _both(lambda t: _run(CHECKED, {"day": day}, _ctx(t, [_eggs()], {})))
            self.assertEqual(results[0], results[1], offset)
            if expect == "ok":
                args = {} if offset == 0 else {"date": day}
                self.assertEqual(results[0], [{"op": "store.confirm_selection", "args": args}], offset)
            else:
                self.assertEqual(results[0], expect, offset)
        # the extremes: no neighbour beyond date.min / date.max is built
        low = _run(CHECKED, {"day": "0001-01-01"}, _ctx(date.min, [], {}))
        self.assertEqual(low, [{"op": "store.confirm_selection", "args": {}}])
        high = _run(CHECKED, {"day": "9999-12-31"}, _ctx(date.max, [], {}))
        self.assertEqual(high, [{"op": "store.confirm_selection", "args": {}}])
        self.assertEqual(_run(CHECKED, {"day": "9999-12-31"}, _ctx(date.min, [], {})), stock.FUTURE)

    def test_checked_default_today_noop_and_real_change(self):
        store = {"selection_checked_on": "2026-11-02"}
        for today in (TODAY, TODAY.isoformat()):
            with self.subTest(today=type(today).__name__):
                done = _ctx(today, [_eggs(available="no", available_on="2026-11-02")], store)
                self.assertEqual(_run(CHECKED, {}, done), stock.DONE_TODAY)
                self.assertEqual(_run(CHECKED, {"out": [EGGS]}, done), stock.DONE_TODAY)
                self.assertEqual(_run(CHECKED, {"in": [EGGS]}, done),
                                 [{"op": "store.confirm_selection", "args": {"yes": [EGGS]}}])
                self.assertEqual(_run(CHECKED, {"day": "2026-11-01"}, done), stock.AFTER)

    def test_absent_context_today_keeps_the_id_only_golden_plans(self):
        self.assertEqual(_run(CHECKED, {"out": [EGGS]}, _ctx(None, [], {})),
                         [{"op": "store.confirm_selection", "args": {"no": [EGGS]}}])
        self.assertEqual(_run(CHECKED, {"day": "2026-11-03"}, _ctx(None, [], {}))[0]["args"]["date"], "2026-11-03")


def _items(pid, word):
    return [{"product": pid, "availability": word}]


class RealDispatch(SkillCase):
    """The production Ctx (shop_today) through the real Conversation, Editor and dispatcher, raw skill envelopes."""
    SKILLS = (SET, CHECKED)

    def setUp(self):
        super().setUp()
        self.prepared = []
        real = self.editor.prepare
        self.editor.prepare = lambda ops: (self.prepared.append(ops), real(ops))[1]

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")
        git(self.repo.wt, "commit", "-qam", f"seed {name}")
        self.base = self.count()

    def seed_checked(self, day, **eggs):
        self.edit("store.json", lambda doc: doc.update(selection_checked_on=day))
        if eggs:
            self.edit("products.json", lambda doc: next(p for p in doc["products"] if p["id"] == EGGS).update(eggs))

    def tell(self, text, reply):
        self.script(text, reply)
        disposition = self.say(text)
        return disposition, "\n".join(self.replies())

    def rejected(self, disposition, reply, expected):
        self.assertEqual((disposition, reply), ("refused", expected))
        self.assertEqual(self.prepared, [])
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def test_real_dispatch_rejects_dates_and_noops_before_prepare(self):
        self.seed_checked("2026-11-02", available="no", available_on="2026-11-02")
        said = "Cal Poly eggs already says Sold out. Nothing to change."
        envelope = {"skill": "stock.set", "slots": {"items": _items(EGGS, "no")}}
        self.rejected(*self.tell("eggs are out", envelope), said)
        self.rejected(*self.tell("eggs sold out", {"calls": [envelope]}), said)
        self.rejected(*self.tell("shelves checked", {"skill": "stock.checked", "slots": {}}), stock.DONE_TODAY)
        self.rejected(*self.tell("shelves checked tomorrow", {"calls": [{"skill": "stock.checked", "slots": {"day": "2026-11-03"}}]}),
                      stock.FUTURE)

    def test_real_dispatch_too_old_day_is_refused_before_prepare(self):
        self.rejected(*self.tell("checked long ago", {"skill": "stock.checked", "slots": {"day": "2026-10-25"}}), stock.TOO_OLD)

    def test_real_dispatch_valid_check_keeps_existing_approval_boundary(self):
        for text, slots, args in (("checked today", {}, {}),
                                  ("checked last week", {"day": "2026-10-26"}, {"date": "2026-10-26"})):
            with self.subTest(text=text):
                self.prepared.clear()
                disposition, reply = self.tell(text, {"skill": "stock.checked", "slots": slots})
                self.assertEqual(disposition, "proposed", reply)
                self.assertEqual([[(o["op"], o["args"]) for o in ops] for ops in self.prepared],
                                 [[("store.confirm_selection", args)]])
                self.nothing_written()  # nothing is applied before the owner's coded yes
                self.say("no")

    def test_production_ctx_uses_the_pacific_day_not_the_utc_day(self):
        self.seed_checked("2026-11-02")
        late = datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc)  # 18:00 PST on 2026-11-02
        ctx = dispatch.Dispatcher(self.conv, self.registry)._ctx(late, ["checked"])
        self.assertEqual(ctx.today, date(2026, 11, 2))
        self.assertEqual(_run(CHECKED, {}, ctx), stock.DONE_TODAY)
        after_midnight = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)  # 01:00 PST on 2026-11-03
        ctx = dispatch.Dispatcher(self.conv, self.registry)._ctx(after_midnight, ["checked"])
        self.assertEqual(ctx.today, date(2026, 11, 3))
        self.assertEqual(_run(CHECKED, {}, ctx)[0]["op"], "store.confirm_selection")


if __name__ == "__main__":
    unittest.main()
