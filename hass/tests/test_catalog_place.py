"""AV1537-10 (H03) tests: a maker.edit that changes ``place`` drafts as usual and warns how many active product cards
show that maker's "Based in" line (town search follows it); nothing is refused for it.

Fixture content only, via test_catalog_ops.CatalogRepo (throwaway Git repo, private temp state dir).
Run: python3 -m unittest hass.tests.test_catalog_place -v
"""

from types import SimpleNamespace

from hass.ops.catalog import _maker_edit
from hass.tests.test_catalog_ops import CatalogTestCase, _req


def based_in(key, n):
    return f"changes the \"Based in\" line on {n} active product card{'s' if n != 1 else ''} of maker {key} " \
           "(town search follows it)"


def none_active(key):
    return f"maker {key} has no active products; no product card changes"


class PlaceWarningTests(CatalogTestCase):
    def setUp(self):
        self.r = self.repo()
        content = self.r.content()
        self.mine = lambda key: [p for p in content.products if p.get("producerKey") == key]
        self.three = next(k for k in content.makers if len(self.mine(k)) == 3
                          and all(p["status"] == "active" for p in self.mine(k)))
        self.one = next(k for k in content.makers if len(self.mine(k)) == 1 and self.mine(k)[0]["status"] == "active")

    def draft(self, *ops):
        head, drafts = self.r.head(), self.r.drafts()
        draft = self.r.prepare(_req(*ops))
        self.assertEqual(draft["result"], "ok", draft)  # never refused
        self.assertEqual(self.r.head(), head)  # prepare commits nothing
        self.assertEqual(len(self.r.drafts()), len(drafts) + 1)
        return draft["draft"]

    def warnings(self, *ops):
        return self.draft(*ops)["warnings"]

    def test_three_active_cards(self):
        draft = self.draft(("maker.edit", {"key": self.three, "place": "Morro Bay, California"}))
        self.assertEqual(draft["warnings"], [based_in(self.three, 3)])
        (rec,) = draft["records"]
        self.assertEqual({k for k in rec["after"] if rec["before"].get(k) != rec["after"][k]}, {"place"})
        self.assertEqual(rec["after"]["place"], "Morro Bay, California")

    def test_one_active_card_is_singular(self):
        (warning,) = self.warnings(("maker.edit", {"key": self.one, "place": "Morro Bay, California"}))
        self.assertEqual(warning, based_in(self.one, 1))
        self.assertIn(" 1 active product card of maker ", warning)

    def test_hidden_products_not_counted(self):
        (pid,) = [p["id"] for p in self.mine(self.one)]
        self.r.run(("product.hide", {"id": pid}))
        self.assertEqual(self.warnings(("maker.edit", {"key": self.one, "place": "Morro Bay, California"})),
                         [none_active(self.one)])
        first = self.mine(self.three)[0]["id"]
        self.r.run(("product.hide", {"id": first}))
        self.assertEqual(self.warnings(("maker.edit", {"key": self.three, "place": "Morro Bay, California"})),
                         [based_in(self.three, 2)])

    def test_held_products_not_counted(self):
        content = self.r.content()
        for product in content.products:
            if product.get("producerKey") == self.three:
                product["status"] = "held"
        ctx = SimpleNamespace(warnings=[])
        _maker_edit(content, {"key": self.three, "place": "Morro Bay, California"}, ctx)
        self.assertEqual(ctx.warnings, [none_active(self.three)])
        content.products[[p.get("producerKey") for p in content.products].index(self.three)]["status"] = "active"
        ctx = SimpleNamespace(warnings=[])
        _maker_edit(content, {"key": self.three, "place": "Avila Beach, California"}, ctx)
        self.assertEqual(ctx.warnings, [based_in(self.three, 1)])

    def test_unchanged_place_with_story_change_gives_no_warning(self):
        place = self.r.makers()[self.three]["place"]
        draft = self.draft(("maker.edit", {"key": self.three, "place": place, "story": "A new story."}))
        self.assertEqual(draft["warnings"], [])
        (rec,) = draft["records"]
        self.assertEqual({k for k in rec["after"] if rec["before"].get(k) != rec["after"][k]}, {"story"})

    def test_case_or_space_change_of_place_still_warns(self):
        place = self.r.makers()[self.three]["place"]
        self.assertEqual(self.warnings(("maker.edit", {"key": self.three, "place": place.upper()})),
                         [based_in(self.three, 3)])

    def test_other_fields_give_no_warning(self):
        for args in ({"story": "A new story."}, {"url": "https://example.org/maker"}):
            with self.subTest(args=args):
                self.assertEqual(self.warnings(("maker.edit", {"key": self.three, **args})), [])
        self.assertEqual(self.warnings(("maker.edit", {"key": self.three, "name": "A Fresh Maker Name"})),  # AV2137-03: the rename warning
                         [f"3 active product cards of maker {self.three} still show {self.three} as their brand; "
                          "ask to change them too"])

    def test_unknown_maker_and_refused_rename_give_no_warning(self):
        result = self.assertRejected(self.r, "not-found", ("maker.edit", {"key": "No Such Maker", "place": "Here"}))
        self.assertEqual(result["key"], "No Such Maker")
        self.assertNotIn("warnings", result)
        other = self.r.makers()[self.one]["name"]
        result = self.assertRejected(self.r, "refused", ("maker.edit", {"key": self.three, "name": other,
                                                                        "place": "Morro Bay, California"}))
        self.assertNotIn("warnings", result)
        ctx = SimpleNamespace(warnings=[])
        _maker_edit(self.r.content(), {"key": self.three, "name": other, "place": "Morro Bay, California"}, ctx)
        self.assertEqual(ctx.warnings, [])

    def test_two_place_edits_warn_in_op_order(self):
        self.assertEqual(self.warnings(("maker.edit", {"key": self.one, "place": "Morro Bay, California"}),
                                       ("maker.edit", {"key": self.three, "place": "Avila Beach, California"})),
                         [based_in(self.one, 1), based_in(self.three, 3)])
