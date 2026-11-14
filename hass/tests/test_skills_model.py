"""SKILLS-FW-1: skill model, registry and slot resolvers. Offline, stdlib, no model and no git."""

import unittest
from datetime import date

from hass import skills
from hass.content_model import Content
from hass.ops import load_registry
from hass.skills import kinds, model

TODAY = date(2026, 11, 8)  # a Sunday


def _content():
    def prod(n, name, brand, status="active"):
        return {"id": f"photo-product-{n:03d}", "name": name, "brand": brand, "status": status}

    products = [prod(1, "Eggs, dozen", "Hilltop"), prod(2, "Honey", "Bee Co"), prod(3, "Honey Wheat Bread", "Oven"),
                prod(4, "Lemons", "Grove", "hidden"), prod(5, "Salsa", "Casa", "held"), prod(6, "Peppers", "Grove")]
    makers = {"hilltop": {"name": "Hilltop Farm"}, "grove": {"name": "Grove", "hidden": True}}
    community = {"events": [{"id": "hike-1", "title": "Big Sur Ridge Hike"}, {"id": "hike-2", "title": "Big Sur Beach Walk"}],
                 "routeIdeas": [{"id": "route-1", "title": "Moonstone Beach Loop"}]}
    return Content(products=products, makers=makers, community=community, store={})


def _skill(**over):
    base = dict(
        name="stock.set", label="change what's in stock", summary="Mark products in stock, low or out.",
        triggers=(model.Trigger("eggs are out"), model.Trigger("got more honey in"), model.Trigger("avocados limited today"),
                  model.Trigger("bread is gone"), model.Trigger("egs r sold out again lol", "typo"),
                  model.Trigger("the stock thing", "vague"), model.Trigger("no more strawberries, peppers low", "multi")),
        slots=(model.Slot("items", "text_list", True, ask="Which products, and in, low or out?"),
               model.Slot("checked", "bool", False, default="derive:checked_today")),
        rules=("shelf-check-today",), plan=lambda s, c: [], edits=(("hass/content/products.json", "products[id].available"),),
        side_effects=("inventory-word",), preview="product:eggs", approval="owner-yes", live_class="chat-live",
        undo=model.Undo("revert", "none"), refuse=(("price in message", "No prices on the site."),),
        cases="hass/tests/fixtures/skills/inventory/stock.set.jsonl", version=1)
    base.update(over)
    return model.Skill(**base)


class RegistryTests(unittest.TestCase):
    def test_load_skills_finds_the_catch_all_skills_and_is_clean(self):
        reg = skills.load_skills()
        self.assertIn("backlog.log", reg.skills)
        self.assertIn("page.faq", reg.skills)
        self.assertEqual(skills.skill_lint(reg, load_registry()), [])

    def test_retired_skill_is_listed_but_not_served(self):
        reg = skills.Registry({"a.b": _skill(name="a.b", status="retired"), "c.d": _skill(name="c.d")})
        self.assertIsNone(reg.get("a.b"))
        self.assertIsNotNone(reg.get("c.d"))
        self.assertEqual([s.name for s in reg.active()], ["c.d"])

    def test_duplicate_name_across_modules_raises(self):
        import sys, types
        mod = types.ModuleType("hass.skills.dupe_probe")
        mod.SKILLS = (skills.load_skills().skills["backlog.log"],)
        sys.modules["hass.skills.dupe_probe"] = mod
        self.addCleanup(sys.modules.pop, "hass.skills.dupe_probe", None)
        import pkgutil
        original = pkgutil.iter_modules
        pkgutil.iter_modules = lambda path: [*original(path), pkgutil.ModuleInfo(None, "dupe_probe", False)]
        self.addCleanup(setattr, pkgutil, "iter_modules", original)
        with self.assertRaisesRegex(ValueError, "duplicate skill name"):
            skills.load_skills()


class UndoRowLintTests(unittest.TestCase):
    """lint_cases asks for an undo row only from a skill that can change something."""

    def _problems(self, skill):
        import json, tempfile
        from pathlib import Path
        rows = [{"kind": "clean", "version": 1}] * 8 + [{"kind": "refuse", "version": 1}] * 2  # no undo row
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / skill.cases
            path.parent.mkdir(parents=True)
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            return model.lint_cases(skill, tmp)

    def test_read_only_skill_without_an_undo_row_passes(self):
        ro = _skill(name="stock.look", approval="none", live_class="read-only", preview="none", edits=(),
                    undo=model.Undo("none", "none"), cases="hass/tests/fixtures/skills/inventory/stock.look.jsonl")
        self.assertEqual(self._problems(ro), [])

    def test_skill_with_approval_and_no_undo_row_still_fails(self):
        problems = self._problems(_skill())
        self.assertEqual(len(problems), 1)
        self.assertIn("undo row", problems[0])


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.content = _content()

    def test_product_one(self):
        r = kinds.product_ref(self.content, "eggs")
        self.assertEqual((r.status, r.value), ("one", "photo-product-001"))

    def test_product_several_gives_names_not_ids(self):
        r = kinds.product_ref(self.content, "honey")
        self.assertEqual(r.status, "several")
        self.assertEqual(len(r.candidates), 2)
        self.assertNotIn("photo-product", r.reply)
        self.assertTrue(r.reply.startswith("Which one"))
        self.assertEqual(r.ids, ("photo-product-002", "photo-product-003"))

    def test_product_none(self):
        r = kinds.product_ref(self.content, "unicorn")
        self.assertEqual(r.status, "none")
        self.assertIn("I don't know", r.reply)
        self.assertEqual(kinds.product_ref(self.content, "  ").status, "none")

    def test_product_held_is_never_resolvable(self):
        r = kinds.product_ref(self.content, "salsa")
        self.assertEqual((r.status, r.value), ("held", None))
        self.assertNotIn("photo-product", r.reply)

    def test_product_hidden_is_named(self):
        r = kinds.product_ref(self.content, "lemons")
        self.assertEqual((r.status, r.value), ("hidden", None))
        self.assertIn("bring it back", r.reply)

    def test_product_alias(self):
        r = kinds.product_ref(self.content, "the usual", {"the usual": ("product", "photo-product-006")})
        self.assertEqual((r.status, r.value), ("one", "photo-product-006"))

    def test_maker(self):
        self.assertEqual(kinds.maker_ref(self.content, "hilltop").value, "hilltop")
        self.assertEqual(kinds.maker_ref(self.content, "grove").status, "hidden")
        self.assertEqual(kinds.maker_ref(self.content, "nobody").status, "none")

    def test_hike_and_route(self):
        self.assertEqual(kinds.hike_ref(self.content, "ridge").value, "hike-1")
        self.assertEqual(kinds.hike_ref(self.content, "big sur").status, "several")
        self.assertEqual(kinds.hike_ref(self.content, "zzz").status, "none")
        self.assertEqual(kinds.route_ref(self.content, "moonstone").value, "route-1")

    def test_shelf(self):
        self.assertEqual(kinds.shelf("the veggies").value, "vegetables")
        self.assertEqual(kinds.shelf("bread").value, "bread")
        self.assertEqual(kinds.shelf("stuff").status, "none")

    def test_availability(self):
        for said, want in (("sold out", "no"), ("running low", "limited"), ("back in", "yes"), ("limited", "limited"), ("no", "no")):
            with self.subTest(said=said):
                self.assertEqual(kinds.availability(said).value, want)
        self.assertEqual(kinds.availability("maybe").status, "none")
        for said in ("not available", "not in stock", "not out", "isn't in stock", "isn't available", "never in stock"):
            with self.subTest(said=said):
                self.assertEqual(kinds.availability(said).status, "none")
                self.assertIn("in stock", kinds.availability(said).reply)

    def test_day_and_clock(self):
        self.assertEqual(kinds.day("tomorrow", TODAY).value, "2026-11-09")
        self.assertEqual(kinds.day("2026-11-14", TODAY).value, "2026-11-14")
        self.assertEqual(kinds.day("2026-02-31", TODAY).status, "invalid")
        self.assertEqual(kinds.day("whenever", TODAY).status, "none")
        self.assertEqual(kinds.clock("9am").value, "09:00")
        self.assertEqual(kinds.clock("15:30").value, "15:30")
        self.assertEqual(kinds.clock("3:30 pm").value, "15:30")
        self.assertEqual(kinds.clock("9").status, "none")

    def test_attachment(self):
        self.assertEqual(kinds.attachment("a" * 64).status, "one")
        self.assertEqual(kinds.attachment("abc").status, "none")

    def test_every_skill_kind_has_a_resolver(self):
        self.assertEqual(set(kinds.RESOLVERS), set(model.SKILL_KINDS))

    def test_resolvers_do_not_change_content(self):
        before = repr(self.content)
        for q in ("eggs", "honey", "salsa", "lemons", "nothing"):
            kinds.product_ref(self.content, q)
        self.assertEqual(repr(self.content), before)


if __name__ == "__main__":
    unittest.main()
