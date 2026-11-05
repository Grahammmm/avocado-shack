"""AV1937-04 tests (H03): a maker may have no website; url is optional on maker.add, maker.edit gains clearUrl.

Ops run on a throwaway CatalogRepo (see test_catalog_ops); the card test runs the real storefront-mockup/shop.js
card() in a Node VM (skipped without node). Nothing touches the live site.
Run: python3 -B -m unittest hass.tests.test_maker_optional_url -v
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from hass.content_model import REPO_ROOT, validate_makers
from hass.migration_check import run_checks
from hass.interpreter_prompt import build
from hass.ops import load_registry
from hass.tests.test_catalog_ops import IMAGE, CatalogTestCase, _req
from hass.tests.test_interpreter_prompt import tiny_content

FARM = {"key": "Fiction Farm", "name": "Fiction Farm", "place": "Nowhere, California", "story": "Grows pretend beans."}
URL = "https://example.com/about"
SHOP_JS = REPO_ROOT / "storefront-mockup" / "shop.js"
MAKERS = "hass/content/makers.json"


def problems_for(maker):
    problems = []
    validate_makers(problems, {"K": maker})
    return problems


class OptionalUrlTests(CatalogTestCase):
    def test_add_without_url_validates_applies_and_renders(self):
        repo = self.repo()
        before = repo.makers()
        repo.run(("maker.add", FARM))
        added = repo.makers()["Fiction Farm"]
        self.assertEqual(list(added), ["name", "place", "story"])
        self.assertEqual({k: v for k, v in repo.makers().items() if k != "Fiction Farm"}, before)
        repo.run(("product.add", {"name": "Pretend beans", "brand": "Fiction Farm", "category": "vegetables",
                                  "image": IMAGE, "description": "Beans.", "displayBrand": "Fiction Farm", "producerKey": "Fiction Farm"}))
        self.assertEqual(repo.products()[-1]["producerKey"], "Fiction Farm")
        produced = repo.read("storefront-mockup/producers.js").decode()
        self.assertIn("Fiction Farm", produced)
        self.assertEqual(repo.content().makers["Fiction Farm"], added)
        self.assertEqual(repo.makers()["Etto"]["url"], before["Etto"]["url"])
        self.assertEqual(run_checks(repo.wt)[0], [])

    def test_present_url_still_requires_public_https(self):
        repo = self.repo()
        for bad in (None, "", "   ", 5, ["https://example.com/"], "http://example.com/", "javascript:alert(1)",
                    "https://localhost/", "https://192.168.0.1/", "https://example.com/a b"):
            with self.subTest(url=bad):
                self.assertRejected(repo, "invalid", ("maker.add", {**FARM, "url": bad}))
                self.assertTrue(problems_for({**{k: FARM[k] for k in ("name", "place", "story")}, "url": bad}))
        self.assertEqual(problems_for({k: FARM[k] for k in ("name", "place", "story")}), [])
        self.assertEqual(problems_for({"name": "A", "place": "B", "story": "C", "url": URL, "hidden": True}), [])
        for missing in ("name", "place", "story"):
            with self.subTest(missing=missing):
                rec = {k: FARM[k] for k in ("name", "place", "story")}
                del rec[missing]
                self.assertTrue(any("missing field" in p for p in problems_for(rec)))
                self.assertRejected(repo, "needs-details", ("maker.add", {k: v for k, v in FARM.items() if k != missing}))
        self.assertEqual(problems_for({"name": "A", "place": "B", "story": "C", "hidden": True}), [])

    def test_clear_url_and_undo_restore_exact_shape(self):
        repo = self.repo()
        original = repo.makers()["Test Farm"] if "Test Farm" in repo.makers() else None
        self.assertIsNone(original)
        repo.run(("maker.add", {**FARM, "url": URL}))
        with_url = repo.makers()["Fiction Farm"]
        draft = repo.prepare(_req(("maker.edit", {"key": "Fiction Farm", "clearUrl": True})))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.makers()["Fiction Farm"], with_url)  # prepare is read-only
        self.assertEqual(len([r for r in draft["draft"]["records"]]), 1)
        change = repo.run(("maker.edit", {"key": "Fiction Farm", "clearUrl": True}))
        self.assertEqual(list(repo.makers()["Fiction Farm"]), ["name", "place", "story"])
        repo.run(("history.revert", {"changeId": change["change_id"]}))
        self.assertEqual(repo.makers()["Fiction Farm"], with_url)
        self.assertEqual(list(repo.makers()["Fiction Farm"]), list(with_url))
        # adding a url to a URL-less maker, then undo, restores absence
        repo.run(("maker.add", {**FARM, "key": "Plain Farm", "name": "Plain Farm"}))
        change = repo.run(("maker.edit", {"key": "Plain Farm", "url": URL}))
        self.assertEqual(repo.makers()["Plain Farm"]["url"], URL)
        repo.run(("history.revert", {"changeId": change["change_id"]}))
        self.assertNotIn("url", repo.makers()["Plain Farm"])

    def test_clear_conflict_false_missing_and_unchanged(self):
        repo = self.repo()
        repo.run(("maker.add", {**FARM, "url": URL}))
        repo.run(("maker.add", {**FARM, "key": "Plain Farm", "name": "Plain Farm"}))
        self.assertRejected(repo, "refused", ("maker.edit", {"key": "Fiction Farm", "url": URL, "clearUrl": True}))
        self.assertRejected(repo, "needs-details", ("maker.edit", {"key": "Fiction Farm", "clearUrl": False}))
        result = self.assertRejected(repo, "needs-details", ("maker.edit", {"key": "Fiction Farm"}))
        self.assertIn("clearUrl", result["missing"])
        self.assertRejected(repo, "refused", ("maker.edit", {"key": "Plain Farm", "clearUrl": True}))
        self.assertRejected(repo, "refused", ("maker.edit", {"key": "Fiction Farm", "story": FARM["story"],
                                                              "clearUrl": False}))
        self.assertRejected(repo, "invalid", ("maker.edit", {"key": "Fiction Farm", "clearUrl": "yes"}))
        self.assertRejected(repo, "invalid", ("maker.edit", {"key": "Fiction Farm", "clearUrl": True, "bogus": 1}))
        repo.run(("maker.edit", {"key": "Plain Farm", "clearUrl": True, "story": "A new story."}))
        self.assertEqual(repo.makers()["Plain Farm"]["story"], "A new story.")
        self.assertNotIn("url", repo.makers()["Plain Farm"])
        repo.run(("maker.edit", {"key": "Fiction Farm", "clearUrl": True, "story": FARM["story"]}))
        self.assertNotIn("url", repo.makers()["Fiction Farm"])
        self.assertEqual(repo.makers()["Fiction Farm"]["story"], FARM["story"])

    def test_unknown_hidden_and_baseline_source_protection(self):
        repo = self.repo()
        self.assertRejected(repo, "not-found", ("maker.edit", {"key": "No Such Maker", "clearUrl": True}))
        repo.run(("maker.add", FARM))
        repo.run(("maker.hide", {"key": "Fiction Farm"}))
        self.assertTrue(repo.makers()["Fiction Farm"]["hidden"])
        self.assertNotIn("url", repo.makers()["Fiction Farm"])
        self.assertTrue(repo.content().makers["Fiction Farm"]["hidden"])
        baseline_url = repo.makers()["Etto"]["url"]
        head = repo.head()
        draft = repo.prepare(_req(("maker.edit", {"key": "Etto", "clearUrl": True})))
        if draft["result"] == "ok":
            result = repo.apply(draft["draft"])
            self.assertNotEqual(result["result"], "applied", result)
        self.assertEqual(repo.head(), head)
        self.assertEqual(repo.makers()["Etto"]["url"], baseline_url)


class RealRegistryTests(CatalogTestCase):
    def test_existing_catalog_and_real_registry_unchanged(self):
        repo = self.repo()
        makers = repo.makers()
        self.assertEqual(len(makers), 26)
        self.assertTrue(all(m["url"].startswith("https://") for m in makers.values()))
        self.assertEqual(makers, json.loads((REPO_ROOT / MAKERS).read_text("utf-8"))["makers"])
        prompt = build(load_registry(), repo.content())
        line = next(x for x in prompt.splitlines() if "maker.add" in x)
        self.assertIn("url: url", line)
        self.assertNotIn("url: url, required", line)
        self.assertIn("clearUrl: bool", next(x for x in prompt.splitlines() if "maker.edit" in x))


NODE_CHECK = r"""
const fs=require('fs');const src=fs.readFileSync(process.argv[2],'utf8');
const esc=t=>String(t??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const start=src.indexOf('function card(p){'),end=src.indexOf('\n}\n',start)+3;
const makerCounts=new Map([['A',3],['B',1]]);
const producers={A:{name:'Fiction <Farm>',place:'Nowhere',story:'Beans & more.',url:'https://example.com/a?x=1&y="2"'},
 B:{name:'No Site Farm',place:'Elsewhere',story:'No website here.'}};
const mk=eval('(function(){const maker=p=>producers[p.producerKey],origin=p=>"Based in "+maker(p).place,photo=p=>"",badges=p=>"",'
 +'brand=p=>p.brand;'+src.slice(start,end)+';return card})()');
const prod=k=>({id:'x',category:'c',name:'n',brand:'b',description:'d',producerKey:k});
console.log(JSON.stringify({A:mk(prod('A')),B:mk(prod('B'))}));
"""


class CardTests(unittest.TestCase):
    def test_disclosure_without_visit_keeps_story_origin_and_filter(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "card.js"
            script.write_text(NODE_CHECK, "utf-8")
            out = subprocess.run([node, str(script), str(SHOP_JS)], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        cards = json.loads(out.stdout)
        with_url, without = cards["A"], cards["B"]
        self.assertIn('<a href="https://example.com/a?x=1&amp;y=&quot;2&quot;" target="_blank" rel="noopener">'
                      'Visit Fiction &lt;Farm&gt; ', with_url)
        self.assertIn("See all 3 from Fiction &lt;Farm&gt;", with_url)
        self.assertNotIn("Visit", without)
        self.assertNotIn("<a href", without.split("maker-story")[1].split("Link to this")[0])
        for bad in ("undefined", "null", "href=\"\""):
            self.assertNotIn(bad, without)
        self.assertIn("<p>No website here.</p>", without)
        self.assertIn("Based in Elsewhere", without)
        self.assertIn('<details class="maker-story">', without)
        # the single-product maker has no filter button; a multi-product one keeps it with or without a url
        self.assertNotIn("data-from", without)


if __name__ == "__main__":
    unittest.main()
