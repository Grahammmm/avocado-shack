"""RF2135-10: stock.checked and stock.clear resolve product names and aliases in their lists (SKILLS-SPEC 3.7, 3.9).

Pure plan tests on synthetic products, then the PRODUCTION skills through the real dispatcher, Conversation and Editor on
the throwaway shop (SkillCase), with product names the model reply carries as plain text_list lines.
Run: python3 -B -m unittest hass.tests.test_stock_list_references -q
"""

import copy
import json
import types
import unittest

from hass.skills import stock, testkit
from hass.tests.test_conversation import CHAT
from hass.tests.test_editor import git
from hass.tests.test_skill_dispatch import SkillCase

EGGS, HASS, HONEY, LEMONS, MILK, SIDE = ("photo-product-024", "photo-product-001", "photo-product-042", "photo-product-017",
                                         "photo-product-040", "photo-product-099")
TODAY = "2026-11-08"
CATALOG = (
    (EGGS, "Synthetic eggs", "Brand A", "active"), (HASS, "Synthetic avocado", "Brand B", "active"),
    (HONEY, "Synthetic honey", "Brand C", "active"), (LEMONS, "Synthetic lemons", "Brand D", "active"),
    (MILK, "Synthetic cheddar", "Brand E", "held"), (SIDE, "Synthetic plums", "Brand F", "hidden"),
    ("photo-product-101", "Synthetic jam raspberry", "Brand G", "active"), ("photo-product-102", "Synthetic jam plum", "Brand G", "active"),
    ("photo-product-103", "Synthetic bread", "Brand H", "active"), ("photo-product-104", "Synthetic figs", "Brand H", "active"),
    ("photo-product-105", "Synthetic peppers", "Brand H", "active"), ("photo-product-106", "Synthetic basil", "Brand H", "active"),
    ("photo-product-107", "Synthetic mint", "Brand H", "active"),
)


def _ctx(aliases=None, with_content=True, words=True):
    products = [{"id": pid, "name": name, "brand": brand, "status": status, **({"available": "limited", "available_on": TODAY} if words else {})}
                for pid, name, brand, status in CATALOG]
    content = types.SimpleNamespace(products=products, store={}, makers={}) if with_content else None
    return types.SimpleNamespace(today=TODAY, content=content, aliases=aliases or {})


def _refusal(skill, slots, ctx):
    try:
        skill.plan(slots, ctx)
    except stock.Refusal as exc:
        return exc.reply
    raise AssertionError("the plan did not refuse")


def _clear(*pids):
    return [{"op": "product.clear_availability", "args": {"id": pid}} for pid in pids]


class PurePlans(unittest.TestCase):
    def test_clear_resolves_names_aliases_and_ids_in_owner_order(self):
        ctx = _ctx({"the hens": ("product", EGGS)})
        slots = {"items": ["Synthetic honey", "the hens", HASS, "synthetic EGGS", "Synthetic avocado"]}
        before = copy.deepcopy(slots)
        self.assertEqual(stock.STOCK_CLEAR.plan(slots, ctx), _clear(HONEY, EGGS, HASS))  # one op per product, first mention order
        self.assertEqual(slots, before)
        self.assertEqual(stock.STOCK_CLEAR.plan({"items": [HONEY, HASS, EGGS]}, _ctx()), _clear(HONEY, HASS, EGGS))  # id callers

    def test_clear_cap_counts_distinct_products_after_resolving(self):
        names = ["Synthetic eggs", "Synthetic avocado", "Synthetic honey", "Synthetic lemons", "Synthetic bread", "Synthetic figs"]
        self.assertEqual(len(stock.STOCK_CLEAR.plan({"items": names + [EGGS, "synthetic eggs"]}, _ctx())), 6)
        self.assertEqual(_refusal(stock.STOCK_CLEAR, {"items": names + ["Synthetic peppers"]}, _ctx()), stock.TOO_MANY.format(count=7))

    def test_checked_resolves_each_bucket_and_refuses_identity_duplicates(self):
        ctx = _ctx({"the hens": ("product", EGGS)}, words=False)
        slots = {"in": ["Synthetic eggs", HASS], "limited": ["Synthetic honey"], "out": ["Synthetic lemons"]}
        self.assertEqual(stock.STOCK_CHECKED.plan(slots, ctx), [{"op": "store.confirm_selection", "args": {
            "yes": [EGGS, HASS], "limited": [HONEY], "no": [LEMONS]}}])
        twice = stock.TWICE.format(name="Synthetic eggs")
        self.assertEqual(_refusal(stock.STOCK_CHECKED, {"in": ["Synthetic eggs", "the hens"]}, ctx), twice)  # same list
        self.assertEqual(_refusal(stock.STOCK_CHECKED, {"in": ["Synthetic eggs"], "out": [EGGS]}, ctx), twice)  # across lists
        self.assertEqual(_refusal(stock.STOCK_CHECKED, {"in": ["the hens"], "limited": ["synthetic eggs"]}, ctx), twice)
        self.assertEqual(stock.STOCK_CHECKED.plan({}, ctx), [{"op": "store.confirm_selection", "args": {}}])  # empty lists still record a day
        seven = ["Synthetic eggs", "Synthetic avocado", "Synthetic honey", "Synthetic lemons", "Synthetic bread", "Synthetic figs",
                 "Synthetic peppers"]  # no six-product cap on a morning check
        self.assertEqual(stock.STOCK_CHECKED.plan({"in": seven}, ctx)[0]["args"]["yes"][-1], "photo-product-105")

    def test_named_refusal_is_atomic(self):
        ctx = _ctx(words=False)
        cases = (("Synthetic jam", "Which one do you mean: Synthetic jam raspberry (Brand G) or Synthetic jam plum (Brand G)?"),
                 ("Nothing like it", "I don't know a product called that. What is it called on the site?"),
                 ("Synthetic cheddar", "I can't change Synthetic cheddar right now. It is on hold until someone has looked at it."),
                 ("Synthetic plums", "Synthetic plums is hidden. Do you want me to bring it back first?"))
        for name, reply in cases:
            for skill, slots in ((stock.STOCK_CLEAR, {"items": ["Synthetic eggs", name, "Synthetic honey"]}),
                                 (stock.STOCK_CHECKED, {"in": ["Synthetic eggs"], "out": ["Synthetic honey", name]})):
                with self.subTest(skill=skill.name, name=name):
                    got = _refusal(skill, slots, ctx)
                    self.assertEqual(got, reply)
                    self.assertNotIn("photo-product", got)

    def test_without_content_or_with_malformed_members_refusals_stay_ordinary(self):
        for skill, key in ((stock.STOCK_CLEAR, "items"), (stock.STOCK_CHECKED, "out")):
            for ctx in (None, _ctx(with_content=False)):
                with self.subTest(skill=skill.name, ctx=ctx):
                    self.assertEqual(_refusal(skill, {key: ["Synthetic eggs"]}, ctx), stock.BAD_ITEM)
                    ops = skill.plan({key: [EGGS]}, ctx)  # an id still needs no content
                    self.assertEqual(ops, [{"op": "store.confirm_selection", "args": {"no": [EGGS]}}] if key == "out" else _clear(EGGS))
            for bad in ("Synthetic eggs", ["Synthetic eggs", 7], ["Synthetic eggs", None], ["Synthetic eggs", ["x"]],
                        ["Synthetic eggs", {"product": EGGS}], ["Synthetic eggs", True], ["Synthetic eggs", " "], ["Synthetic eggs", ""]):
                with self.subTest(skill=skill.name, bad=bad):
                    self.assertEqual(_refusal(skill, {key: bad}, _ctx()), stock.BAD_ITEM)

    def test_unknown_canonical_id_is_left_to_the_editor(self):
        self.assertEqual(stock.STOCK_CLEAR.plan({"items": ["photo-product-999"]}, _ctx()), _clear("photo-product-999"))


T0_DAY = "2026-11-02"  # SkillCase's injected clock: Monday 2026-11-02 09:00 PST
REAL = {EGGS: "Cal Poly eggs", HASS: "Hass avocado", HONEY: "Big Sur Honey Company honey"}


class RealDispatch(SkillCase):
    """The production skills through the real dispatcher: raw model replies carry names; nothing is written before a yes."""
    SKILLS = (stock.STOCK_CHECKED, stock.STOCK_CLEAR)

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")
        git(self.repo.wt, "commit", "-qam", f"seed {name}")
        self.base = self.count()

    def seed(self, pid, **fields):
        self.edit("products.json", lambda doc: next(p for p in doc["products"] if p["id"] == pid).update(fields))

    def tell(self, text, reply):
        self.script(text, reply)
        disposition = self.say(text)
        return disposition, "\n".join(self.replies())

    def ops(self):
        return [(o["op"], o["args"]) for o in json.loads(self.drafts()[-1]["ops_json"])]

    def fresh(self):
        self.conv.requests.close_live(CHAT, self.now)

    def both(self, skill, id_slots, name_slots, single=True):
        """The id control and the name reply must draft the same ops; returns the named draft's reply text."""
        def envelope(slots):
            return {"skill": skill, "slots": slots} if single else {"calls": [{"skill": skill, "slots": slots}]}
        self.assertEqual(self.tell(f"{skill} by id {single}", envelope(id_slots))[0], "proposed")
        control = self.ops()
        self.assertEqual(self.say("no"), "rejected")  # the id control is cancelled before the named reply
        disposition, reply = self.tell(f"{skill} by name {single}", envelope(name_slots))
        self.assertEqual(disposition, "proposed", reply)
        self.assertEqual(self.ops(), control)
        self.assertEqual(self.say("no"), "rejected")
        self.nothing_written()
        return control

    def test_known_names_propose_the_same_ops_as_ids_and_undo_restores(self):
        self.edit("store.json", lambda doc: doc.update(selection_checked_on=T0_DAY))
        self.seed(EGGS, available="no", available_on=T0_DAY)
        self.seed(HASS, available="limited", available_on=T0_DAY)
        control = self.both("stock.clear", {"items": [EGGS, HASS]}, {"items": ["Cal Poly eggs", "Hass avocado", "cal poly EGGS"]})
        self.assertEqual(control, [("product.clear_availability", {"id": EGGS}), ("product.clear_availability", {"id": HASS})])
        self.both("stock.clear", {"items": [HASS]}, {"items": ["Hass avocado"]}, single=False)
        before = git(self.repo.wt, "rev-parse", "HEAD")
        self.tell("stock.clear by name approve", {"skill": "stock.clear", "slots": {"items": ["Cal Poly eggs", "Hass avocado"]}})
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        files, diff = testkit.tree_diff(self.repo.wt, before)
        self.assertEqual({(e["path"], e["before"]) for e in diff}, {
            (f"products[{EGGS}].available", "no"), (f"products[{EGGS}].available_on", T0_DAY),
            (f"products[{HASS}].available", "limited"), (f"products[{HASS}].available_on", T0_DAY)})
        self.assertEqual(self.say("undo"), "proposed")
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(testkit.tree_diff(self.repo.wt, before)[1], [])

    def test_checked_names_propose_the_same_ops_as_ids(self):
        self.edit("store.json", lambda doc: doc.update(selection_checked_on=T0_DAY))
        id_slots = {"in": [HASS], "limited": [HONEY], "out": [EGGS]}
        name_slots = {"in": ["Hass avocado"], "limited": ["Big Sur Honey Company honey"], "out": ["Cal Poly eggs"]}
        control = self.both("stock.checked", id_slots, name_slots)
        self.assertEqual(control, [("store.confirm_selection", {"yes": [HASS], "limited": [HONEY], "no": [EGGS]})])
        self.both("stock.checked", id_slots, name_slots, single=False)
        before = git(self.repo.wt, "rev-parse", "HEAD")
        self.tell("stock.checked approve", {"skill": "stock.checked", "slots": name_slots})
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        files, diff = testkit.tree_diff(self.repo.wt, before)
        self.assertIn(f"products[{EGGS}].available", {e["path"] for e in diff})
        self.assertEqual(self.say("undo"), "proposed")
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(testkit.tree_diff(self.repo.wt, before)[1], [])

    def test_unresolvable_names_draft_nothing(self):
        self.edit("store.json", lambda doc: doc.update(selection_checked_on=T0_DAY))
        self.seed(EGGS, available="no", available_on=T0_DAY)
        for i, (skill, slots) in enumerate((("stock.clear", {"items": ["Cal Poly eggs", "Zebra pudding"]}),
                                            ("stock.checked", {"in": ["Hass avocado"], "out": ["Zebra pudding"]}),
                                            ("stock.checked", {"in": ["Hass avocado", "hass avocado"]}))):
            with self.subTest(skill=skill, slots=slots):
                disposition, reply = self.tell(f"unresolvable {i}", {"skill": skill, "slots": slots})
                self.assertNotEqual(disposition, "proposed", reply)
                self.assertEqual(self.drafts(), [])
                self.nothing_written()
                self.fresh()


if __name__ == "__main__":
    unittest.main()
