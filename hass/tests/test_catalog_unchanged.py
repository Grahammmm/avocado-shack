"""RF1300-11 (H03) tests: product/maker edits drop fields that already have the asked value; an edit left with nothing
is refused, naming the unchanged fields.

Fixture content only, via test_catalog_ops.CatalogRepo (throwaway Git repo, private temp state dir).
Run: python3 -m unittest hass.tests.test_catalog_unchanged -v
"""

import copy
from types import SimpleNamespace

from hass.ops.catalog import _maker_edit, _product_edit
from hass.ops import Refused
from hass.tests.test_catalog_ops import CatalogTestCase

HOURS = ["Monday–Saturday 9am–6pm", "Closed Sunday"]


class UnchangedEditTests(CatalogTestCase):
    def setUp(self):
        self.r = self.repo()
        active = self.r.content().active_products()
        self.p = next(p for p in active if p["producerKey"] is not None and " " in p["name"])
        self.free = next(p for p in active if p["producerKey"] is None)

    def refused(self, op, args):
        return self.assertRejected(self.r, "refused", (op, args))["reason"]

    def edit_records(self, *ops):
        draft = self.r.prepare({"ops": [{"op": o, "args": a} for o, a in ops]})
        self.assertEqual(draft["result"], "ok", draft)
        return draft["draft"]["records"]

    def test_all_unchanged_refused_by_name_and_content_untouched(self):
        pid, name = self.p["id"], self.p["name"]
        self.assertEqual(self.refused("product.edit", {"id": pid, "name": name}),
                         f"{pid} already has name={name}; nothing to change")
        content = self.r.content()
        products, ctx = copy.deepcopy(content.products), SimpleNamespace(warnings=[])
        out = _product_edit(content, {"id": pid, "name": name}, ctx)
        self.assertIsInstance(out, Refused)
        self.assertEqual((content.products, ctx.warnings), (products, []))
        # Several unchanged fields are named in PRODUCT_EDITABLE order, then producerKey.
        self.assertEqual(self.refused("product.edit", {"id": pid, "producerKey": self.p["producerKey"],
                                                       "category": self.p["category"], "name": name}),
                         f"{pid} already has name={name}, category={self.p['category']}, "
                         f"producerKey={self.p['producerKey']}; nothing to change")

    def test_partly_unchanged_records_only_real_change(self):
        (rec,) = self.edit_records(("product.edit", {"id": self.p["id"], "name": self.p["name"],
                                                     "description": "New text"}))
        diff = {k for k in set(rec["before"]) | set(rec["after"]) if rec["before"].get(k) != rec["after"].get(k)}
        self.assertEqual(diff, {"description"})
        self.assertEqual(rec["after"]["name"], self.p["name"])

    def test_producer_unchanged_and_clear_absent_producer(self):
        pid = self.p["id"]
        self.assertEqual(self.refused("product.edit", {"id": pid, "producerKey": self.p["producerKey"]}),
                         f"{pid} already has producerKey={self.p['producerKey']}; nothing to change")
        fid = self.free["id"]
        self.assertEqual(self.refused("product.edit", {"id": fid, "clearProducer": True}),
                         f"{fid} already has producerKey=none; nothing to change")

    def test_alt_text_unchanged_and_clear_absent_alt(self):
        pid = self.p["id"]
        self.assertEqual(self.assertRejected(self.r, "needs-details", (
            "product.edit", {"id": pid, "clearImageAlt": True}))["missing"][0], "name")
        self.r.run(("product.edit", {"id": pid, "imageAlt": "A jar on a shelf"}))
        self.assertEqual(self.refused("product.edit", {"id": pid, "imageAlt": "A jar on a shelf"}),
                         f"{pid} already has imageAlt=A jar on a shelf; nothing to change")
        # Clearing the alt is a real change even when another field repeats its value.
        (rec,) = self.edit_records(("product.edit", {"id": pid, "name": self.p["name"], "clearImageAlt": True}))
        self.assertNotIn("imageAlt", rec["after"])
        self.assertEqual(rec["after"]["name"], self.p["name"])

    def test_exact_equality_case_and_space_are_changes(self):
        pid, name = self.p["id"], self.p["name"]
        for new in (name.upper() if name.upper() != name else name.lower(), name.replace(" ", "  ", 1)):
            (rec,) = self.edit_records(("product.edit", {"id": pid, "name": new}))
            self.assertEqual((rec["before"]["name"], rec["after"]["name"]), (name, new))

    def test_maker_unchanged_and_partly_unchanged(self):
        key = "Etto"
        place = self.r.makers()[key]["place"]
        self.assertEqual(self.refused("maker.edit", {"key": key, "place": place}),
                         f"maker {key} already has place={place}; nothing to change")
        (rec,) = self.edit_records(("maker.edit", {"key": key, "place": place, "story": "A new story."}))
        diff = {k for k in rec["after"] if rec["before"].get(k) != rec["after"][k]}
        self.assertEqual(diff, {"story"})
        content = self.r.content()
        makers = copy.deepcopy(content.makers)
        self.assertIsInstance(_maker_edit(content, {"key": key, "place": place}, SimpleNamespace(warnings=[])),
                              Refused)
        self.assertEqual(content.makers, makers)

    def test_long_unchanged_value_is_cut(self):
        pid, text = self.p["id"], "x" * 199 + "y"
        self.r.run(("product.edit", {"id": pid, "description": text}))
        self.assertEqual(self.refused("product.edit", {"id": pid, "description": text}),
                         f"{pid} already has description={'x' * 40}…; nothing to change")

    def test_multi_op_request_with_unchanged_edit_is_refused(self):
        pid = self.p["id"]
        result = self.assertRejected(self.r, "refused", ("store.set_hours", {"hours": HOURS}),
                                     ("product.edit", {"id": pid, "name": self.p["name"]}))
        self.assertEqual(result["reason"], f"{pid} already has name={self.p['name']}; nothing to change")

    def test_held_product_message_wins(self):
        held = next(p for p in self.r.content().products if p.get("status") == "held")
        reason = self.refused("product.edit", {"id": held["id"], "name": held["name"]})
        self.assertTrue(reason.startswith("held: "), reason)
