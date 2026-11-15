"""AV0222-10 tests (H03/H15): a maker may have no story, so Hass never has to write one the owner did not give.

story is optional on maker.add, maker.edit gains clearStory, content validation accepts a maker with no story (a present
story stays strict), the card's Meet the maker panel shows place and link only (no panel with neither), social_draft
--maker refuses a maker with no story, and one prompt rule says never invent a maker story. Synthetic content only: ops run
on a throwaway CatalogRepo, the card runs the real storefront-mockup/shop.js in a Node VM, no model, no network.
Run: python3 -B -m unittest hass.tests.test_maker_optional_story -v
"""

import contextlib
import copy
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from hass import social_draft
from hass.content_model import Content, validate_makers
from hass.interpreter_prompt import RULES, build
from hass.migration_check import run_checks
from hass.ops import load_registry
from hass.tests.test_catalog_ops import IMAGE, CatalogTestCase, _req
from hass.tests.test_interpreter_prompt import tiny_content

DRIVER = Path(__file__).resolve().parent / "fixtures" / "shop_maker_story_driver.cjs"
NODE = shutil.which("node")
URL = "https://example.com/about"
BARE = {"key": "Fiction Farm", "name": "Fiction Farm", "place": "Nowhere, California"}
STORY = "Grows pretend beans."
RULE_START = "Never invent a maker story."


def problems_for(maker):
    problems = []
    validate_makers(problems, {"K": maker})
    return problems


def bean_product(key):
    return ("product.add", {"name": "Pretend beans", "brand": key, "category": "vegetables", "image": IMAGE,
                            "description": "Beans.", "displayBrand": key, "producerKey": key})


class StorylessAddTests(CatalogTestCase):
    def test_add_storyless_with_and_without_url(self):
        repo = self.repo()
        before = repo.makers()
        self.assertEqual(len(before), 26)
        self.assertTrue(all(m["story"] for m in before.values()))  # the 26 sourced stories
        raw = repo.read("hass/content/makers.json")
        draft = repo.prepare(_req(("maker.add", BARE)))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.read("hass/content/makers.json"), raw)  # nothing is written before approval
        self.assertEqual(draft["draft"]["records"][0]["after"], {"name": "Fiction Farm", "place": "Nowhere, California"})
        added = repo.run(("maker.add", BARE), bean_product("Fiction Farm"))
        maker = repo.makers()["Fiction Farm"]
        self.assertEqual(list(maker), ["name", "place"])  # no story key, no null, no placeholder
        self.assertEqual({k: v for k, v in repo.makers().items() if k != "Fiction Farm"}, before)
        self.assertEqual(json.loads(repo.read("storefront-mockup/producers.json"))["Fiction Farm"], maker)  # generated site: no story key
        self.assertEqual(run_checks(repo.wt)[0], [])
        repo.run(("history.revert", {"changeId": added["change_id"]}))
        # undo of an add hides the new record (nothing is ever deleted); no story is written and every other maker is unchanged
        self.assertEqual(repo.makers()["Fiction Farm"], {"name": "Fiction Farm", "place": "Nowhere, California", "hidden": True})
        self.assertEqual({k: v for k, v in repo.makers().items() if k != "Fiction Farm"}, before)
        # a website without a story is the other storyless shape
        repo.run(("maker.add", {**BARE, "key": "Link Farm", "name": "Link Farm", "url": URL}))
        self.assertEqual(list(repo.makers()["Link Farm"]), ["name", "place", "url"])
        self.assertEqual(repo.content().makers["Link Farm"], {"name": "Link Farm", "place": "Nowhere, California", "url": URL})

    def test_present_story_remains_strict(self):
        repo = self.repo()
        base = {"name": "A", "place": "B"}
        for bad in (None, "", "   ", 5, ["x"], "<b>x</b>", "Costs $5", "bell\x07", "zero\u200bwidth", "x" * 601, " lead", "trail "):
            with self.subTest(story=bad):
                self.assertTrue(problems_for({**base, "story": bad}), bad)
        self.assertEqual(problems_for({**base, "story": "x" * 600}), [])
        self.assertEqual(problems_for(base), [])
        self.assertEqual(problems_for({**base, "hidden": True}), [])
        for missing in ("name", "place"):
            self.assertTrue(any("missing field" in p for p in problems_for({k: v for k, v in base.items() if k != missing})))
        self.assertTrue(any("unknown field" in p for p in problems_for({**base, "bio": "x"})))
        self.assertTrue(problems_for({**base, "url": "http://example.com/"}))
        # the op keeps its named refusal for a supplied story, and still needs the name and place
        refused = self.assertRejected(repo, "refused", ("maker.add", {**BARE, "story": "x" * 601}))
        self.assertEqual(refused["reason"], "story is longer than 600 characters")
        self.assertRejected(repo, "invalid", ("maker.add", {**BARE, "story": "<b>x</b>"}))
        for missing in ("name", "place"):
            self.assertRejected(repo, "needs-details", ("maker.add", {k: v for k, v in BARE.items() if k != missing}))
        repo.run(("maker.add", {**BARE, "story": "x" * 600}))
        self.assertEqual(repo.makers()["Fiction Farm"]["story"], "x" * 600)


class ClearStoryTests(CatalogTestCase):
    def test_clear_story_exact_shape_and_undo(self):
        repo = self.repo()
        repo.run(("maker.add", {**BARE, "story": STORY, "url": URL}), ("maker.add", {**BARE, "key": "Plain", "name": "Plain"}))
        full, plain = repo.makers()["Fiction Farm"], repo.makers()["Plain"]
        draft = repo.prepare(_req(("maker.edit", {"key": "Fiction Farm", "clearStory": True})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(len(draft["draft"]["records"]), 1)  # one maker Touched
        self.assertEqual(repo.makers()["Fiction Farm"], full)  # prepare writes nothing
        change = repo.run(("maker.edit", {"key": "Fiction Farm", "clearStory": True}))
        self.assertEqual(list(repo.makers()["Fiction Farm"]), ["name", "place", "url"])
        self.assertEqual(repo.makers()["Plain"], plain)
        repo.run(("history.revert", {"changeId": change["change_id"]}))
        self.assertEqual(list(repo.makers()["Fiction Farm"]), list(full))  # exact key presence, value and order
        self.assertEqual(repo.makers()["Fiction Farm"], full)
        # restoring a newly supplied story on a storyless maker, then undo, restores absence
        added = repo.run(("maker.edit", {"key": "Plain", "story": "A new story."}))
        self.assertEqual(repo.makers()["Plain"]["story"], "A new story.")
        repo.run(("history.revert", {"changeId": added["change_id"]}))
        self.assertEqual(repo.makers()["Plain"], plain)

    def test_clear_story_refusals_and_combinations(self):
        repo = self.repo()
        repo.run(("maker.add", {**BARE, "story": STORY, "url": URL}), ("maker.add", {**BARE, "key": "Plain", "name": "Plain"}))
        both = self.assertRejected(repo, "refused", ("maker.edit", {"key": "Fiction Farm", "story": "Other.", "clearStory": True}))
        self.assertEqual(both["reason"], "story and clearStory cannot be combined")
        self.assertRejected(repo, "needs-details", ("maker.edit", {"key": "Fiction Farm", "clearStory": False}))
        guide = self.assertRejected(repo, "needs-details", ("maker.edit", {"key": "Fiction Farm"}))
        self.assertIn("clearStory", guide["missing"])
        self.assertRejected(repo, "invalid", ("maker.edit", {"key": "Fiction Farm", "clearStory": "yes"}))
        self.assertRejected(repo, "not-found", ("maker.edit", {"key": "No Such Maker", "clearStory": True}))
        absent = self.assertRejected(repo, "refused", ("maker.edit", {"key": "Plain", "clearStory": True}))
        self.assertEqual(absent["reason"], "maker Plain has no story; nothing to change")
        # an unchanged ordinary field keeps its named no-change refusal; false never clears
        same = self.assertRejected(repo, "refused", ("maker.edit", {"key": "Fiction Farm", "place": BARE["place"], "clearStory": False}))
        self.assertIn("nothing to change", same["reason"])
        self.assertEqual(repo.makers()["Fiction Farm"]["story"], STORY)
        # a clear plus an unchanged name still works; a clear that is absent plus a different change still succeeds
        repo.run(("maker.edit", {"key": "Fiction Farm", "name": "Fiction Farm", "clearStory": True}))
        self.assertNotIn("story", repo.makers()["Fiction Farm"])
        self.assertEqual(repo.makers()["Fiction Farm"]["url"], URL)
        repo.run(("maker.edit", {"key": "Plain", "place": "Elsewhere, California", "clearStory": True}))
        self.assertEqual(repo.makers()["Plain"], {"name": "Plain", "place": "Elsewhere, California"})
        # a repeated clear is refused; in one draft the second op refuses the whole draft with nothing written
        raw = repo.read("hass/content/makers.json")
        self.assertRejected(repo, "refused", ("maker.edit", {"key": "Fiction Farm", "clearStory": True}))
        self.assertRejected(repo, "refused", ("maker.add", {**BARE, "key": "Another", "name": "Another", "story": STORY}),
                            ("maker.edit", {"key": "Another", "clearStory": True}),
                            ("maker.edit", {"key": "Another", "clearStory": True}))
        self.assertEqual(repo.read("hass/content/makers.json"), raw)

    def test_story_and_url_clear_together_and_hidden_maker(self):
        repo = self.repo()
        repo.run(("maker.add", {**BARE, "story": STORY, "url": URL}))
        full = repo.makers()["Fiction Farm"]
        change = repo.run(("maker.edit", {"key": "Fiction Farm", "clearStory": True, "clearUrl": True}))
        self.assertEqual(repo.makers()["Fiction Farm"], {"name": "Fiction Farm", "place": "Nowhere, California"})
        self.assertEqual(len(change["records"]), 1)
        repo.run(("history.revert", {"changeId": change["change_id"]}))
        self.assertEqual(repo.makers()["Fiction Farm"], full)
        repo.run(("maker.hide", {"key": "Fiction Farm"}))
        repo.run(("maker.edit", {"key": "Fiction Farm", "clearStory": True}))
        self.assertEqual(repo.makers()["Fiction Farm"], {"name": "Fiction Farm", "place": "Nowhere, California",
                                                          "url": URL, "hidden": True})


def drive(catalog, producers, **kw):
    out = subprocess.run([NODE, str(DRIVER), json.dumps({"catalog": catalog, "producers": producers, **kw})],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)["cards"]


def item(pid, key, **kw):
    return {"id": pid, "name": f"Item {pid}", "brand": "Brand", "producerKey": key, "category": "pantry",
            "description": "d", "image": "assets/x.png", **kw}


HOSTILE = "<img src=x onerror=alert(1)> & \"quoted\" 'single'"
PRODUCERS = {
    "SL": {"name": "Story <Link>", "place": "Place & One", "story": HOSTILE, "url": "https://example.com/a?x=1&y=2"},
    "SO": {"name": "Story Only", "place": "Place Two", "story": "Only a story."},
    "LO": {"name": "Link \"Only\"", "place": "Place <Three>", "url": "https://example.com/l"},
    "NO": {"name": "Neither Farm", "place": "Place Four"},
}
CATALOG = [item("sl1", "SL"), item("sl2", "SL"), item("so1", "SO"), item("lo1", "LO"), item("lo2", "LO"),
           item("no1", "NO"), item("no2", "NO"), item("ghost", "Ghost"), item("none", None)]


@unittest.skipUnless(NODE, "node not installed")
class PanelMatrixTests(unittest.TestCase):
    def cards(self, **kw):
        found = drive(CATALOG, PRODUCERS, **kw)
        return {re.search(r'data-product-id="([^"]*)"', c).group(1): c for c in found}

    def test_panel_matrix(self):
        cards = self.cards()
        self.assertEqual(sorted(cards), sorted(p["id"] for p in CATALOG))
        for pid, html in cards.items():
            for bad in ("undefined", "null", "<p></p>", 'href=""', "<img src=x"):
                self.assertNotIn(bad, html, pid)
        sl = cards["sl1"]  # story and link: as before, the escaped story, no place paragraph
        self.assertIn("<p>&lt;img src=x onerror=alert(1)&gt; &amp; &quot;quoted&quot; &#39;single&#39;</p>", sl)
        self.assertNotIn("maker-place", sl)
        self.assertIn('href="https://example.com/a?x=1&amp;y=2" target="_blank" rel="noopener">Visit Story &lt;Link&gt;', sl)
        self.assertIn("See all 2 from Story &lt;Link&gt;", sl)
        so = cards["so1"]  # story only: no Visit link, no See all (one product)
        self.assertIn("<p>Only a story.</p>", so)
        self.assertNotIn("Visit", so)
        self.assertNotIn("data-from", so)
        lo = cards["lo1"]  # link only: the place paragraph and the Visit link, never an empty story paragraph
        self.assertIn('<details class="maker-story">', lo)
        self.assertIn('<p class="maker-place">Based in Place &lt;Three&gt;</p>', lo)
        self.assertIn('Visit Link &quot;Only&quot; ', lo)
        self.assertIn("See all 2 from Link &quot;Only&quot;", lo)
        for pid in ("no1", "no2"):  # neither: no panel at all, even with several products
            self.assertNotIn("maker-story", cards[pid])
            self.assertNotIn("<details", cards[pid])
            self.assertNotIn("data-from", cards[pid])
            self.assertIn('<p class="origin-label">Based in Place Four</p>', cards[pid])

    def test_card_identity_survives_without_a_panel(self):
        cards = self.cards()
        no = cards["no1"]
        self.assertIn(' data-maker-key="NO"', no)
        self.assertIn('<span class="sr-only maker-name">Neither Farm</span>', no)
        identity = no.split('class="food-identity">')[1].split("</div>")[0]
        self.assertIn('<p class="origin-label">Based in Place Four</p><span class="sr-only maker-name">', identity)
        self.assertIn('<span class="sr-only maker-name">Story &lt;Link&gt;</span>', cards["sl1"])
        for pid in ("ghost", "none"):  # an unknown or absent maker has no key, no name and no panel
            self.assertNotIn("data-maker-key", cards[pid])
            self.assertNotIn("maker-name", cards[pid])
            self.assertNotIn("maker-story", cards[pid])
            self.assertIn("Ask us about the source in store.", cards[pid])

    def test_maker_filter_still_lists_its_cards_without_a_panel(self):
        shown = drive(CATALOG, PRODUCERS, **{"from": "NO"})
        self.assertEqual([re.search(r'data-product-id="([^"]*)"', c).group(1) for c in shown], ["no1", "no2"])
        self.assertTrue(all("maker-story" not in c and 'data-maker-key="NO"' in c for c in shown))


class SocialDraftStorylessTests(unittest.TestCase):
    MAKER = {"name": "Sunny Farm", "place": "Pismo Beach", "story": "Three generations of growers."}
    NO_STORY = {"draft": False, "reason": "maker has no story"}

    def content(self, makers):
        products = [{"id": "a", "producerKey": "m1", "status": "active", "name": "Na"}]
        return Content(products=products, makers=makers, community={}, store={})

    def test_absent_story_refuses_without_a_caption(self):
        bare = {k: v for k, v in self.MAKER.items() if k != "story"}
        self.assertEqual(social_draft.build_maker(self.content({"m1": bare}), "m1"), self.NO_STORY)
        self.assertEqual(social_draft.build_maker(self.content({"m1": {**bare, "url": URL}}), "m1"), self.NO_STORY)
        # hidden, zero-active and unknown keep their own refusals; name/place problems win over the story
        self.assertEqual(social_draft.build_maker(self.content({"m1": {**bare, "hidden": True}}), "m1"),
                         {"draft": False, "reason": "not on the site"})
        c = self.content({"m1": bare})
        c.products = []
        self.assertEqual(social_draft.build_maker(c, "m1"), {"draft": False, "reason": "no active products"})
        self.assertEqual(social_draft.build_maker(self.content({"m1": bare}), "zz"), {"draft": False, "reason": "no such maker"})
        self.assertEqual(social_draft.build_maker(self.content({"m1": {"name": "x"}}), "m1"),
                         {"draft": False, "reason": "maker record incomplete"})
        # a PRESENT story that is blank, null or has a control character stays incomplete; a tagged one keeps its reason
        for story in (None, "", "  ", 5, "a\x07b"):
            self.assertEqual(social_draft.build_maker(self.content({"m1": {**bare, "story": story}}), "m1"),
                             {"draft": False, "reason": "maker record incomplete"}, story)
        self.assertEqual(social_draft.build_maker(self.content({"m1": {**bare, "story": "Hi #tag"}}), "m1"),
                         {"draft": False, "reason": "free text has a hashtag or account name"})
        self.assertTrue(social_draft.build_maker(self.content({"m1": dict(self.MAKER)}), "m1")["draft"])

    def test_cli_prints_one_object_and_exits_one(self):
        bare = {k: v for k, v in self.MAKER.items() if k != "story"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c = self.content({"m1": bare})
            for name, doc in (("products", {"products": c.products}), ("makers", {"makers": c.makers}), ("community", {}), ("store", {})):
                (root / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **doc}), "utf-8")
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = social_draft.main(["--maker", "m1"], root, root)
            self.assertEqual((code, json.loads(out.getvalue())), (1, self.NO_STORY))
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)  # nothing written

    def test_product_captions_stay_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets" / "products").mkdir(parents=True)
            (root / "assets" / "products" / "p1.webp").write_bytes(b"x")
            product = {"id": "p1", "name": "Beans", "brand": "Bare", "category": "vegetables", "image": "assets/products/p1.webp",
                       "description": "Good beans.", "producerKey": "m1", "displayBrand": "Bare", "status": "active"}
            bare = {"name": "Bare Farm", "place": "Nowhere, California"}
            c = Content(products=[product], makers={"m1": bare}, community={}, store={})
            self.assertEqual(social_draft.build(c, "p1", root)["caption"],
                             "Beans\nGood beans.\nFrom Bare Farm in Nowhere, California.\n\n#AvocadoShack #Vegetables")


class PromptRuleTests(unittest.TestCase):
    def test_rule_once_and_registry_shapes(self):
        rules = [r for r in RULES if r.startswith(RULE_START)]
        self.assertEqual(len(rules), 1)
        self.assertEqual(RULES[RULES.index(rules[0]) - 1][:20], "Never add organic, o")  # right after the unprovided-claims rule
        self.assertIn("omit story when the owner gave none", rules[0])
        self.assertIn("clearStory removes it only when explicitly requested", rules[0])
        prompt = build(load_registry(), tiny_content())
        self.assertEqual(prompt.count(RULE_START), 1)
        lines = prompt.splitlines()
        add = next(x for x in lines if x.startswith("maker.add("))
        edit = next(x for x in lines if x.startswith("maker.edit("))
        self.assertIn("story: text;", add)
        self.assertNotIn("story: text, required", add)
        self.assertIn("name: text, required; place: text, required", add)
        self.assertIn("clearStory: bool", edit)
        self.assertNotIn("<omitted>", add)


if __name__ == "__main__":
    unittest.main()
