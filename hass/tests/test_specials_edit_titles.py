"""RF1221-11: ``specials.edit`` refuses a title another nonexpired special already has (same rule as ``specials.add``)."""

import copy
import types
import unittest
from datetime import date, datetime, timezone

from hass.content_model import validate_specials
from hass.ops import OpContext, Refused, Touched, specials as ops_specials
from hass.skills import specials as skill_specials

NOW = datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)  # 12:00 PST on 2026-11-16
TODAY = date(2026, 11, 16)
CTX = OpContext(now=NOW, site_dir=None, settings={})
EDIT = next(op for op in ops_specials.OPS if op.name == "specials.edit").apply
ADD = next(op for op in ops_specials.OPS if op.name == "specials.add").apply


def sp(sid, title, start="2026-11-16", end="2026-11-18", order=0, deal="Free sample"):
    return {"id": sid, "title": title, "deal": deal, "start": start, "end": end, "order": order}


def content(*specials):
    return types.SimpleNamespace(store={"name": "Shop", "keep": {"a": [1]}, "specials": list(specials)}, products=[])


def run(c, args, op=EDIT):
    return op(c, args, CTX)


def touched(result):
    return isinstance(result, list) and len(result) == 1 and isinstance(result[0], Touched)


def valid(c):
    problems = []
    validate_specials(problems, c.store.get("specials", []), set(), TODAY)
    return problems == []


class EditTitleTests(unittest.TestCase):
    def base(self, **other):
        return content(sp("orchard", "Orchard fruit", **other), sp("coastal", "Coastal greens", order=1))

    def test_edit_refuses_another_nonexpired_title(self):
        for kw in ({}, {"start": "2026-11-20", "end": "2026-11-22"}, {"start": "2026-11-10", "end": "2026-11-16"}):
            for title in ("Orchard fruit", "ORCHARD fruit", "orchard   FRUIT"):
                c = self.base(**kw)
                self.assertTrue(valid(c))
                before = copy.deepcopy(c.store)
                result = run(c, {"id": "coastal", "title": title})
                self.assertEqual(result, Refused(f"there is already a special called {title}; edit it instead"), (kw, title))
                self.assertEqual(c.store, before)

    def test_duplicate_title_with_other_changes_is_atomic(self):
        c = self.base()
        before = copy.deepcopy(c.store)
        result = run(c, {"id": "coastal", "title": "orchard fruit", "deal": "Two for one", "end": "2026-11-17", "order": 5})
        self.assertIsInstance(result, Refused)
        self.assertEqual(c.store, before)
        self.assertEqual(c.products, [])

    def test_self_title_and_unique_rename_preserve_touches(self):
        c = self.base()
        before = copy.deepcopy(c.store)
        result = run(c, {"id": "coastal", "title": "coastal GREENS", "deal": "Buy one"})
        self.assertTrue(touched(result))
        self.assertEqual(c.store["specials"][1]["deal"], "Buy one")
        self.assertEqual(c.store["keep"], before["keep"])
        c = self.base()
        self.assertEqual(run(c, {"id": "coastal", "title": "Coastal greens"}), Refused("that special already says that"))
        before = copy.deepcopy(c.store)
        result = run(c, {"id": "coastal", "title": "Coastal vegetables"})
        self.assertTrue(touched(result))
        self.assertEqual([s["id"] for s in c.store["specials"]], ["orchard", "coastal"])
        self.assertEqual(c.store["specials"][1], {**before["specials"][1], "title": "Coastal vegetables"})
        self.assertEqual(c.store["specials"][0], before["specials"][0])
        self.assertTrue(valid(c))

    def test_expired_other_title_does_not_block(self):
        c = self.base(start="2026-11-10", end="2026-11-15")
        self.assertTrue(touched(run(c, {"id": "coastal", "title": "Orchard fruit"})))
        self.assertEqual(c.store["specials"][1]["title"], "Orchard fruit")
        for end in ("2026-11-16", "2026-11-30"):
            c = self.base(end=end)
            self.assertIsInstance(run(c, {"id": "coastal", "title": "Orchard fruit"}), Refused, end)
        c = self.base(start="2026-12-01", end="2026-12-03")  # future, not overlapping coastal
        self.assertIsInstance(run(c, {"id": "coastal", "title": "Orchard fruit"}), Refused)

    def test_legacy_duplicates_do_not_block_title_absent_edits(self):
        c = content(sp("a", "Same"), sp("b", "same", order=1))
        self.assertTrue(valid(c))
        self.assertTrue(touched(run(c, {"id": "b", "deal": "New deal"})))
        self.assertEqual(c.store["specials"][1]["deal"], "New deal")
        self.assertEqual(skill_specials.resolve_special(types.SimpleNamespace(today=TODAY, content=c), "same")[0], "several")

    def test_rejected_rename_preserves_unique_title_resolution(self):
        c = self.base()
        ctx = types.SimpleNamespace(today=TODAY, content=c)
        self.assertEqual(skill_specials.resolve_special(ctx, "orchard fruit")[0], "one")
        self.assertIsInstance(run(c, {"id": "coastal", "title": "Orchard  Fruit"}), Refused)
        self.assertEqual(skill_specials.resolve_special(ctx, "orchard fruit")[0], "one")
        self.assertTrue(touched(run(c, {"id": "coastal", "title": "Coastal vegetables"})))
        self.assertEqual(skill_specials.resolve_special(ctx, "coastal vegetables")[0], "one")


if __name__ == "__main__":
    unittest.main()
