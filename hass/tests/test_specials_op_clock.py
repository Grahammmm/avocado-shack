"""RF2100-11: specials typed ops validate against the operation's Pacific day (ctx.now), never a second wall clock."""

import copy
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest import mock

from hass.content_model import shop_today as real_shop_today
from hass.ops import OpContext, Refused, specials as ops_specials

CONTEXT_NOW = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)  # 12:00 PST on 2026-11-10
WALLS = (date(2026, 11, 1), date(2026, 11, 10), date(2026, 11, 20))
OPS = {op.name: op.apply for op in ops_specials.OPS}


def sp(i, start, end, **extra):
    return {"id": f"s{i}", "title": f"Deal {i}", "deal": "Two for one", "start": start, "end": end, "order": i, **extra}


def content(*, current=True):
    """Seven expired overlapping specials (legal on the context day) plus one current special."""
    items = [sp(i, "2026-11-01", "2026-11-02") for i in range(7)]
    if current:
        items.append(sp(7, "2026-11-10", "2026-11-12"))
    return SimpleNamespace(store={"name": "Shop", "specials": items}, products=[])


def run(op, args, wall, c=None, now=CONTEXT_NOW):
    """Run one real op; an omitted-timestamp clock read returns ``wall``. Returns (result, content, wall_calls)."""
    c = c or content()
    wall_calls = []

    def clock(n=None):
        if n is None:
            wall_calls.append(1)
            return wall
        return real_shop_today(n)

    with mock.patch.object(ops_specials, "shop_today", clock):
        result = OPS[op](c, args, OpContext(now=now, site_dir=None, settings={}))
    return result, c, wall_calls


class SpecialsOpClockTests(unittest.TestCase):
    def check_same_everywhere(self, op, args, expect):
        outcomes = []
        for wall in WALLS:
            result, c, calls = run(op, args, wall)
            self.assertEqual(calls, [], f"{op} read the wall clock")
            self.assertIsInstance(result, list, f"{op} wall={wall}: {result!r}")
            outcomes.append((result[0].before, result[0].after))
            expect(c, result)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[1], outcomes[2])

    def test_add_and_edit_use_context_day_for_final_overlap_check(self):
        def added(c, result):
            self.assertEqual([s["id"] for s in c.store["specials"]][-1], "fresh")
            self.assertEqual(len(result[0].after["specials"]), 9)
            self.assertEqual(len(result[0].before["specials"]), 8)

        self.check_same_everywhere("specials.add", {"title": "Fresh", "deal": "Half off", "start": "2026-11-13", "end": "2026-11-14"}, added)

        def edited(c, result):
            self.assertEqual(c.store["specials"][7]["deal"], "Three for one")
            self.assertEqual(result[0].before["specials"][7]["deal"], "Two for one")

        self.check_same_everywhere("specials.edit", {"id": "s7", "deal": "Three for one"}, edited)

    def test_remove_uses_context_day_even_without_date_arguments(self):
        def removed(c, result):
            self.assertEqual([s["id"] for s in c.store["specials"]], [f"s{i}" for i in range(7)])

        self.check_same_everywhere("specials.remove", {"id": "s7"}, removed)
        # removing the last item drops the key
        c = SimpleNamespace(store={"name": "Shop", "specials": [sp(0, "2026-11-10", "2026-11-12")]}, products=[])
        result, c, calls = run("specials.remove", {"id": "s0"}, WALLS[0], c)
        self.assertIsInstance(result, list)
        self.assertNotIn("specials", c.store)
        self.assertEqual(calls, [])

    def test_clear_expired_uses_same_context_day_through_save(self):
        c = SimpleNamespace(store={"specials": [sp(0, "2026-11-08", "2026-11-09"), sp(1, "2026-11-10", "2026-11-10"),
                                                sp(2, "2026-11-11", "2026-11-12")]}, products=[])
        seen = []
        real = ops_specials.validate_specials
        with mock.patch.object(ops_specials, "validate_specials", lambda p, s, ids, today=None: (seen.append(today), real(p, s, ids, today))[1]):
            result, c, calls = run("specials.clear_expired", {}, WALLS[2], c)
        self.assertIsInstance(result, list)
        self.assertEqual([s["id"] for s in c.store["specials"]], ["s1", "s2"])
        self.assertEqual(seen, [date(2026, 11, 10)])
        self.assertEqual(calls, [])
        nothing = SimpleNamespace(store={"specials": [sp(1, "2026-11-10", "2026-11-10")]}, products=[])
        before = copy.deepcopy(nothing.store)
        result, nothing, _ = run("specials.clear_expired", {}, WALLS[0], nothing)
        self.assertIsInstance(result, Refused)
        self.assertEqual(nothing.store, before)

    def test_all_four_ops_read_context_once_and_never_wall_time(self):
        # 2026-11-11 03:00 UTC is still 2026-11-10 in Pacific (PST); the day must come from ctx.now, converted.
        late = datetime(2026, 11, 11, 3, 0, tzinfo=timezone.utc)
        seen = []
        real = ops_specials.validate_specials
        spy = lambda p, s, ids, today=None: (seen.append(today), real(p, s, ids, today))[1]
        cases = (("specials.add", {"title": "Fresh", "deal": "Half off", "start": "2026-11-13", "end": "2026-11-14"}),
                 ("specials.edit", {"id": "s7", "deal": "Three for one"}),
                 ("specials.remove", {"id": "s7"}),
                 ("specials.clear_expired", {}))
        for op, args in cases:
            seen.clear()
            with mock.patch.object(ops_specials, "validate_specials", spy):
                result, _, calls = run(op, args, WALLS[2], now=late)
            self.assertIsInstance(result, list, op)
            self.assertEqual(calls, [], op)
            self.assertEqual(seen, [date(2026, 11, 10)], op)

    def test_current_or_future_seventh_overlap_still_refused(self):
        items = [sp(i, "2026-11-10", "2026-11-12") for i in range(6)]
        for wall in WALLS:
            c = SimpleNamespace(store={"specials": copy.deepcopy(items)}, products=[])
            result, c, _ = run("specials.add", {"title": "Seventh", "deal": "Half off", "end": "2026-11-11"}, wall, c)
            self.assertIsInstance(result, Refused)
            self.assertEqual(c.store["specials"], items)
            c = SimpleNamespace(store={"specials": copy.deepcopy(items) + [sp(6, "2026-11-20", "2026-11-21")]}, products=[])
            before = copy.deepcopy(c.store)
            result, c, _ = run("specials.edit", {"id": "s6", "start": "2026-11-11", "end": "2026-11-12"}, wall, c)
            self.assertIsInstance(result, Refused)
            self.assertEqual(c.store, before)

    def test_ordinary_equal_clock_touch_records_are_unchanged(self):
        base = {"name": "Shop", "specials": [sp(0, "2026-11-10", "2026-11-12"), sp(1, "2026-11-08", "2026-11-09")]}
        result, c, _ = run("specials.clear_expired", {}, WALLS[1], SimpleNamespace(store=copy.deepcopy(base), products=[]))
        self.assertEqual(result[0].before, base)
        self.assertEqual(result[0].after, {"name": "Shop", "specials": [base["specials"][0]]})
        result, c, _ = run("specials.remove", {"id": "s0"}, WALLS[1], SimpleNamespace(store={"name": "Shop", "specials": [base["specials"][0]]}, products=[]))
        self.assertEqual(result[0].after, {"name": "Shop"})


if __name__ == "__main__":
    unittest.main()
