"""RF0720-2 (H03) tests: product/maker edits drop a field whose new text differs from the stored text only by inner
spacing, exactly as they drop an equal value; case changes and new values stay real changes.

Fixture content only, via test_catalog_ops.CatalogRepo (throwaway Git repo, private temp state dir).
Run: python3 -B -m unittest hass.tests.test_catalog_unchanged_spacing -v
"""

import copy
from types import SimpleNamespace

from hass.ops import Refused
from hass.ops.catalog import _maker_edit, _product_edit, _shown
from hass.tests.test_catalog_ops import CatalogTestCase


def doubled(text):
    return text.replace(" ", "  ", 1)


class SpacingOnlyEditTests(CatalogTestCase):
    def setUp(self):
        self.r = self.repo()
        content = self.r.content()
        active = content.active_products()
        self.p = next(p for p in active if " " in p["name"] and " " in (p.get("description") or ""))
        self.key = next(k for k, m in content.makers.items() if " " in m["place"] and " " in m["story"]
                        and any(p.get("producerKey") == k for p in active))

    def refused(self, op, args):
        return self.assertRejected(self.r, "refused", (op, args))["reason"]

    def edit_records(self, *ops):
        draft = self.r.prepare({"ops": [{"op": o, "args": a} for o, a in ops]})
        self.assertEqual(draft["result"], "ok", draft)
        return draft["draft"]

    @staticmethod
    def diff(rec):
        return {k for k in set(rec["before"]) | set(rec["after"]) if rec["before"].get(k) != rec["after"].get(k)}

    def test_description_spacing_only_is_refused_and_content_untouched(self):
        pid, new = self.p["id"], doubled(self.p["description"])
        before = self.r.read("hass/content/products.json")
        reason = self.refused("product.edit", {"id": pid, "description": new})
        self.assertTrue(reason.startswith(f"{pid} already has description="), reason)
        self.assertTrue(reason.endswith("; nothing to change"), reason)
        self.assertEqual(self.r.read("hass/content/products.json"), before)
        content = self.r.content()  # a tab run folds the same way when the op is called directly
        products, ctx = copy.deepcopy(content.products), SimpleNamespace(warnings=[])
        out = _product_edit(content, {"id": pid, "description": self.p["description"].replace(" ", " \t ", 1)}, ctx)
        self.assertIsInstance(out, Refused)
        self.assertEqual((content.products, ctx.warnings), (products, []))

    def test_name_spacing_only_with_real_category_changes_category_only(self):
        others = {p["category"] for p in self.r.content().products} - {self.p["category"]}
        category = sorted(others)[0]
        (rec,) = self.edit_records(("product.edit", {"id": self.p["id"], "name": doubled(self.p["name"]),
                                                     "category": category}))["records"]
        self.assertEqual(self.diff(rec), {"category"})
        self.assertEqual((rec["after"]["name"], rec["after"]["category"]), (self.p["name"], category))

    def test_surviving_change_saves_the_owners_exact_text(self):
        new = "Fresh  text, owner's  spacing"
        (rec,) = self.edit_records(("product.edit", {"id": self.p["id"], "name": doubled(self.p["name"]),
                                                     "description": new}))["records"]
        self.assertEqual(self.diff(rec), {"description"})
        self.assertEqual(rec["after"]["description"], new)

    def test_maker_place_spacing_only_is_refused_without_relabel_warning(self):
        place = self.r.makers()[self.key]["place"]
        self.assertEqual(self.refused("maker.edit", {"key": self.key, "place": doubled(place)}),
                         f"maker {self.key} already has place={_shown(doubled(place))}; nothing to change")
        content = self.r.content()
        makers, ctx = copy.deepcopy(content.makers), SimpleNamespace(warnings=[])
        self.assertIsInstance(_maker_edit(content, {"key": self.key, "place": doubled(place)}, ctx), Refused)
        self.assertEqual((content.makers, ctx.warnings), (makers, []))
        # A spacing-only place beside a real story change drafts the story only, with no relabel warning.
        draft = self.edit_records(("maker.edit", {"key": self.key, "place": doubled(place), "story": "A new story."}))
        self.assertEqual(self.diff(draft["records"][0]), {"story"})
        self.assertFalse(any("Based in" in w or "no product card" in w for w in draft.get("warnings", [])), draft)

    def test_maker_story_spacing_only_with_real_url_drafts_url_only(self):
        maker = self.r.makers()[self.key]
        url = "https://example.com/rf0720-2"
        (rec,) = self.edit_records(("maker.edit", {"key": self.key, "story": doubled(maker["story"]),
                                                   "url": url}))["records"]
        self.assertEqual(self.diff(rec), {"url"})
        self.assertEqual((rec["after"]["story"], rec["after"]["url"]), (maker["story"], url))

    def test_case_only_change_is_a_real_change(self):
        name = self.p["name"]
        new = name.lower() if name.lower() != name else name.upper()
        (rec,) = self.edit_records(("product.edit", {"id": self.p["id"], "name": new}))["records"]
        self.assertEqual((self.diff(rec), rec["after"]["name"]), ({"name"}, new))

    def test_absent_stored_value_and_new_text_is_a_real_change(self):
        free = next(p for p in self.r.content().active_products() if "imageAlt" not in p)
        (rec,) = self.edit_records(("product.edit", {"id": free["id"], "imageAlt": "A  jar on a shelf"}))["records"]
        self.assertEqual((self.diff(rec), rec["after"]["imageAlt"]), ({"imageAlt"}, "A  jar on a shelf"))

    def test_held_product_refusal_still_comes_first(self):
        held = next(p for p in self.r.content().products if p.get("status") == "held")
        reason = self.refused("product.edit", {"id": held["id"], "name": doubled(held["name"])})
        self.assertTrue(reason.startswith("held: "), reason)
