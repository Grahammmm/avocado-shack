"""AV2137-03 (H03): a maker.edit that changes ``name`` still changes only the maker, and warns how many of that maker's
active product cards still show the old name as their brand (displayBrand, else brand; case and spacing ignored).

Fixture content only, via test_catalog_ops.CatalogRepo (throwaway Git repo, private temp state dir); nothing is sent.
Run: python3 -B -m unittest hass.tests.test_maker_rename_warning -v
"""

import copy
from types import SimpleNamespace

from hass import conversation, voice
from hass.ops import Refused
from hass.ops.catalog import _maker_edit
from hass.tests.test_catalog_ops import CatalogTestCase, _req

EXPIRES = "2026-11-02T17:10:00+00:00"


def left(n, key, old):
    return f"{n} active product card{'s' if n != 1 else ''} of maker {key} still show {old} as their brand; ask to change them too"


def based_in(key, n):
    return f"changes the \"Based in\" line on {n} active product card{'s' if n != 1 else ''} of maker {key} (town search follows it)"


class MakerRenameWarningTests(CatalogTestCase):
    def setUp(self):
        self.r = self.repo()
        self.key, self.one = "Alle-Pia", "AG Berries"  # on the fixture every maker's products show the maker name as brand
        self.content = self.r.content()
        self.mine = [p for p in self.content.products if p.get("producerKey") == self.key]
        self.assertEqual(len([p for p in self.mine if p["status"] == "active"]), 3)

    def rename(self, content=None, key=None, **args):
        """Run _maker_edit on a copy: (result, warnings, copy)."""
        content = copy.deepcopy(content or self.content)
        ctx = SimpleNamespace(warnings=[])
        out = _maker_edit(content, {"key": key or self.key, **args}, ctx)
        return out, ctx.warnings, content

    def warnings_for(self, mutate, new="Alle Pia Farm", key=None):
        content = copy.deepcopy(self.content)
        mutate(content)
        out, warnings, _ = self.rename(content, key=key, name=new)
        self.assertNotIsInstance(out, Refused, out)
        return warnings

    def draft(self, *ops):
        head = self.r.head()
        draft = self.r.prepare(_req(*ops))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(self.r.head(), head)  # prepare commits nothing
        return draft["draft"]

    def test_rename_counts_only_own_active_matching_shown_brands(self):
        def of(content):
            return [p for p in content.products if p.get("producerKey") == self.key]

        def hide(content): of(content)[0]["status"] = "hidden"

        def hold(content): of(content)[0]["status"] = "held"

        def override(content): of(content)[0]["displayBrand"] = "Somebody Else"  # brand still matches, card does not

        def fallback(content):
            for p in of(content): p.pop("displayBrand", None)  # brand alone is shown

        def blank_override(content): of(content)[0]["displayBrand"] = "  "  # blank displayBrand: the brand is shown

        def other_maker(content):
            for p in content.products:
                if p.get("producerKey") == self.one: p["brand"] = p["displayBrand"] = self.key  # shows our name, is not ours

        def no_producer(content):
            for p in content.products:
                if p.get("producerKey") is None: p["brand"] = p["displayBrand"] = self.key

        self.assertEqual(self.warnings_for(lambda c: None), [left(3, self.key, self.key)])
        self.assertEqual(self.warnings_for(hide), [left(2, self.key, self.key)])
        self.assertEqual(self.warnings_for(hold), [left(2, self.key, self.key)])
        self.assertEqual(self.warnings_for(override), [left(2, self.key, self.key)])
        self.assertEqual(self.warnings_for(blank_override), [left(3, self.key, self.key)])
        self.assertEqual(self.warnings_for(fallback), [left(3, self.key, self.key)])
        self.assertEqual(self.warnings_for(other_maker), [left(3, self.key, self.key)])
        self.assertEqual(self.warnings_for(no_producer), [left(3, self.key, self.key)])
        self.assertEqual(self.warnings_for(lambda c: None, key=self.one, new="AG Berry Co"), [left(1, self.one, self.one)])

        def none_match(content):
            for p in of(content): p["displayBrand"] = "From the market"

        def all_hidden(content):
            for p in of(content): p["status"] = "hidden"

        self.assertEqual(self.warnings_for(none_match), [])  # none: no warning
        self.assertEqual(self.warnings_for(all_hidden), [])

    def test_brand_comparison_case_and_spacing_not_fuzzy(self):
        def brands(*values):
            def mutate(content):
                for p, value in zip([p for p in content.products if p.get("producerKey") == self.key], values):
                    p["displayBrand"] = value
            return mutate

        self.assertEqual(self.warnings_for(brands("ALLE-PIA", "  alle-pia\t", "Alle-Pia")), [left(3, self.key, self.key)])
        self.assertEqual(self.warnings_for(brands("Alle -Pia", "Alle-Pia Farm", "Allé-Pia")), [])  # inner space, substring, accent
        self.assertEqual(self.warnings_for(brands("Alle-Pias", "Alle’Pia", "Alle Pia")), [])
        old = "Big  Sur\tHoney"  # spacing runs in the stored name fold too
        content = copy.deepcopy(self.content)
        content.makers[self.key]["name"] = old
        for p in content.products:
            if p.get("producerKey") == self.key: p["displayBrand"] = "big sur honey"
        out, warnings, _ = self.rename(content, name="Sur Honey")
        self.assertEqual(warnings, [left(3, self.key, old)])  # old spelling kept as stored
        # a case-only rename is a real edit and warns; a spacing-only one is dropped as before
        out, warnings, changed = self.rename(name=self.key.upper())
        self.assertEqual((warnings, changed.makers[self.key]["name"]), ([left(3, self.key, self.key)], self.key.upper()))
        out, warnings, changed = self.rename(name=self.key + "  ")
        self.assertIsInstance(out, Refused)
        self.assertEqual((warnings, changed.makers[self.key]["name"]), ([], self.key))

    def test_unchanged_name_and_refused_edits_stay_silent(self):
        story = self.content.makers[self.key]["story"]
        for args in ({"name": self.key}, {"name": self.key, "story": story}, {"name": " ".join(self.key.split()) + " "},
                     {"name": self.key, "story": "A new story."}, {"name": self.key, "clearStory": True},
                     {"name": self.key, "clearUrl": True}, {"name": self.key, "place": "Morro Bay, California"},
                     {"story": "A new story."}, {"clearStory": True}):
            with self.subTest(args=args):
                _, warnings, _ = self.rename(**args)
                self.assertEqual([w for w in warnings if "still show" in w], [])
        other = self.content.makers[self.one]["name"]
        for key, args in ((self.key, {"name": other}), ("No Such Maker", {"name": "New Name"}), (self.key, {"name": "x" * 200}),
                          (self.key, {"name": "New Name", "story": "s", "clearStory": True})):
            with self.subTest(key=key, args=args):
                out, warnings, changed = self.rename(key=key, **args)
                self.assertNotIsInstance(out, list)
                self.assertEqual(warnings, [])
                self.assertEqual(changed.makers.get(key), self.content.makers.get(key))
        result = self.assertRejected(self.r, "refused", ("maker.edit", {"key": self.key, "name": other}))
        self.assertNotIn("warnings", result)

    def test_name_and_place_keep_both_warnings_in_order(self):
        draft = self.draft(("maker.edit", {"key": self.key, "name": "Alle Pia Farm", "place": "Morro Bay, California"}))
        self.assertEqual(draft["warnings"], [based_in(self.key, 3), left(3, self.key, self.key)])
        (rec,) = draft["records"]  # one maker record, no product record
        self.assertEqual((rec["collection"], rec["key"]), ("makers", self.key))
        # a second operation sees the first one's provisional product edit
        pid = self.mine[0]["id"]
        draft = self.draft(("product.edit", {"id": pid, "displayBrand": "Something Else"}),
                           ("maker.edit", {"key": self.key, "name": "Alle Pia Farm"}))
        self.assertEqual(draft["warnings"], [left(2, self.key, self.key)])
        self.assertEqual([(r["collection"], r["key"]) for r in draft["records"]], [("products", pid), ("makers", self.key)])
        draft = self.draft(("maker.edit", {"key": self.key, "name": "Alle Pia Farm"}),
                           ("maker.edit", {"key": self.key, "name": "Alle Pia Farm Two"}))
        self.assertEqual(draft["warnings"], [left(3, self.key, self.key)])  # the second sees the new name, which no card shows

    def test_prepare_apply_and_undo_do_not_rebrand_products(self):
        products, makers = self.r.read("hass/content/products.json"), self.r.makers()
        draft = self.draft(("maker.edit", {"key": self.key, "name": "Alle Pia Farm"}))
        self.assertEqual(self.r.read("hass/content/products.json"), products)
        self.assertEqual(self.r.makers(), makers)
        self.assertEqual(self.r.apply(draft)["result"], "applied")
        self.assertEqual(self.r.read("hass/content/products.json"), products)
        after = self.r.makers()
        self.assertEqual({k for k in after if after[k] != makers[k]}, {self.key})
        self.assertEqual(after[self.key]["name"], "Alle Pia Farm")
        self.assertEqual({p["brand"] for p in self.r.products() if p.get("producerKey") == self.key}, {self.key})
        undo = self.r.prepare(_req(("history.revert", {"changeId": draft["change_id"]})))
        self.assertEqual(undo["result"], "ok", undo)
        self.assertEqual(self.r.apply(undo["draft"])["result"], "applied")
        self.assertEqual(self.r.makers(), makers)
        self.assertEqual(self.r.read("hass/content/products.json"), products)

    def test_owner_projection_keeps_count_old_spelling_and_followup(self):
        def said(draft):
            return voice.plain(conversation.proposal_text("ab12", draft, EXPIRES))

        plural = said(self.draft(("maker.edit", {"key": self.key, "name": "Alle Pia Farm"})))
        self.assertIn("\nHeads up: 3 product cards still show Alle-Pia as the brand. Ask me to change those too.\n", plural)
        singular = said(self.draft(("maker.edit", {"key": self.one, "name": "AG Berry Co"})))
        self.assertIn("\nHeads up: 1 product card still shows AG Berries as the brand. Ask me to change it too.\n", singular)
        for text in (plural, singular):
            self.assertNotIn("one thing to double-check", text)
            self.assertNotIn("of maker", text)
        # accented, cased and punctuated owner words are quoted as written and never cut short
        old = "Café “Zoë”; Ö as their brand; ask to change them too"
        content = copy.deepcopy(self.content)
        content.makers[self.key]["name"] = old
        for p in content.products:
            if p.get("producerKey") == self.key: p["displayBrand"] = old.upper()
        _, warnings, _ = self.rename(content, name="Plain Name")
        (warning,) = warnings
        self.assertEqual(warning, left(3, self.key, old))
        sentence = voice.explain_warning(warning)
        self.assertEqual(sentence, f"3 product cards still show {voice.quote(old)} as the brand. Ask me to change those too.")
        self.assertEqual(voice.plain(sentence), f"3 product cards still show {old} as the brand. Ask me to change those too.")
        self.assertEqual(voice.check(sentence), [])
        # legacy and unknown warnings are answered as before
        self.assertEqual(voice.explain_warning(based_in(self.key, 3)), "This changes the 'Based in' line on 3 product cards.")
        self.assertEqual(voice.explain_warning("3 active product cards of maker X still show Y as their brand"),
                         "There is one thing to double-check before you say yes.")
