"""FAV-04 (H13): the home-page headline is a named copy slot (``store.set_headline``, hass/ops/home.py).

Every change goes through ``editor.prepare`` + ``editor.apply`` on a throwaway Git repo (test_store_ops.StoreRepo).
Capture tests run the real loopback preview server and Chromium; they are skipped when PLAYWRIGHT_MODULE is unset.
Nothing touches the checkout, the live service or its database.
Run: python3 -m unittest hass.tests.test_store_headline -v
"""

import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from hass import preview, sitegen
from hass.content_model import DEFAULT_HEADLINE, REPO_ROOT, load_content, validate_store
from hass.tests.test_editor import git
from hass.tests.test_store_ops import INDEX, REVERT, StoreTestCase, _req

SET = "store.set_headline"
TODAY_H1 = "<h1>A little market.<br><em>A lot to discover.</em></h1>"
NEW = {"first": "Fresh from the coast.", "second": "Grown close to home."}
NEW_H1 = "<h1>Fresh from the coast.<br><em>Grown close to home.</em></h1>"
STORE = load_content().store


def problems_for(**changes):
    store = copy.deepcopy(STORE)
    store.update(changes)
    problems = []
    validate_store(problems, store)
    return problems


class HeadlineOpTests(StoreTestCase):
    def test_no_headline_renders_todays_page_byte_for_byte(self):
        self.assertNotIn("headline", STORE)
        self.assertEqual(sitegen.main(["--check"]), 0)
        files = sitegen.render(load_content())
        self.assertEqual(files[INDEX], (REPO_ROOT / INDEX).read_bytes())
        self.assertIn(TODAY_H1, files[INDEX].decode("utf-8"))
        self.assertEqual(sitegen.store_slots(STORE)["store.headlineHtml"], "A little market.<br><em>A lot to discover.</em>")

    def test_set_then_undo_returns_to_the_identical_default_page(self):
        repo = self.repo()
        original, before = repo.read(INDEX), repo.store()
        change = repo.run((SET, NEW))
        self.assertEqual(repo.store(), {**before, "headline": [NEW["first"], NEW["second"]]})
        self.assertIn(NEW_H1, repo.text(INDEX))
        self.assertNotIn(TODAY_H1, repo.text(INDEX))
        self.assertEqual([r["collection"] for r in change["records"]], ["store"])
        repo.run((REVERT, {"changeId": change["change_id"]}))
        self.assertNotIn("headline", repo.store())
        self.assertEqual(repo.store(), before)
        self.assertEqual(repo.read(INDEX), original)
        self.assertEqual(repo.status(), "")

    def test_markup_template_and_dollar_are_refused_before_any_draft(self):
        repo = self.repo()
        head = repo.head()
        for bad in ("<b>Big</b> news", "{{x}} market", "Apples $5"):
            for line in ("first", "second"):
                with self.subTest(bad=bad, line=line):
                    result = repo.prepare(_req((SET, {**NEW, line: bad})))
                    self.assertEqual(result["result"], "invalid", result)
        self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, [], ""))

    def test_hand_edited_ampersand_renders_escaped(self):
        slot = sitegen.store_slots({**STORE, "headline": ["Salt & pepper", "<b>x</b>"]})["store.headlineHtml"]
        self.assertEqual(slot, "Salt &amp; pepper<br><em>&lt;b&gt;x&lt;/b&gt;</em>")

    def test_forty_characters_accepted_forty_one_refused_naming_the_line(self):
        repo = self.repo()
        for line, number in (("first", 1), ("second", 2)):
            with self.subTest(line=line):
                result = repo.prepare(_req((SET, {**NEW, line: "a" * 41})))
                self.assertEqual((result["result"], result["reason"]),
                                 ("refused", f"headline line {number} is longer than 40 characters"))
        self.assertEqual(repo.drafts(), [])
        repo.run((SET, {"first": "a" * 40, "second": "b" * 40}))
        self.assertEqual(repo.store()["headline"], ["a" * 40, "b" * 40])
        self.assertEqual(repo.status(), "")

    def test_a_line_without_two_letters_is_refused(self):
        repo = self.repo()
        for text, line, number in (("12 34!", "first", 1), ("9 - 5", "second", 2), ("A 1", "first", 1)):
            with self.subTest(text=text):
                result = repo.prepare(_req((SET, {**NEW, line: text})))
                self.assertEqual((result["result"], result["reason"]),
                                 ("refused", f"headline line {number} needs at least 2 letters"))
        self.assertEqual(repo.prepare(_req((SET, {**NEW, "second": "Go"})))["result"], "ok")

    def test_same_words_as_the_default_and_as_the_current_are_refused(self):
        repo = self.repo()
        default = {"first": DEFAULT_HEADLINE[0], "second": DEFAULT_HEADLINE[1]}
        same = repo.prepare(_req((SET, default)))
        self.assertEqual((same["result"], same["reason"]), ("refused", "the headline already says that"))
        repo.run((SET, NEW))
        head = repo.head()
        for args in (NEW, {"first": "Fresh  from the coast.", "second": NEW["second"]}):
            with self.subTest(args=args):
                again = repo.prepare(_req((SET, args)))
                self.assertEqual((again["result"], again["reason"]), ("refused", "the headline already says that"))
        self.assertEqual((repo.head(), repo.status()), (head, ""))
        swapped = repo.prepare(_req((SET, {"first": NEW["second"], "second": NEW["first"]})))
        self.assertEqual(swapped["result"], "ok", swapped)


class ValidatorTests(unittest.TestCase):
    def test_headline_shape_and_limits(self):
        self.assertEqual(problems_for(headline=["A little market.", "A lot to discover."]), [])
        self.assertEqual(problems_for(headline=["a" * 40, "b" * 40]), [])
        for bad in (["One line only"], ["One", "Two", "Three"], "Big news", ["Big news", 5], ["a" * 41, "Fine"],
                    ["<b>Big</b>", "Fine"], ["12 34", "Fine"]):
            with self.subTest(bad=bad):
                problems = problems_for(headline=bad)
                self.assertTrue(problems)
                self.assertTrue(all(p.startswith("store.headline") for p in problems), problems)

    def test_an_extra_store_key_is_still_refused(self):
        self.assertEqual(problems_for(headlines=["Big", "News"]), ["store: unknown field 'headlines'"])


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class HeadlineCaptureTests(StoreTestCase):
    def setUp(self):
        self.store_repo = repo = self.repo()
        wt = repo.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "full site")
        self.old_index = repo.read(INDEX)
        holder = tempfile.TemporaryDirectory(prefix="hass-fav04-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"
        self.target = preview.target_for(repo.run((SET, NEW))["records"][0])

    def capture(self, files=None, viewports=("phone",)):
        return preview.Previewer(self.store_repo.wt, viewports=viewports).capture(files or {}, self.target, self.out)

    def test_new_headline_is_shown_on_phone_and_desktop(self):
        self.assertEqual(self.target["headline"], [NEW["first"], NEW["second"]])
        result = self.capture(viewports=preview.VIEWPORTS)
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        for prefix in ("", "desktop:"):
            self.assertIs(result["checks"][prefix + "headlineShown"], True)

    def test_headline_with_doubled_spaces_is_shown(self):
        spaced = {"first": "Picked  this   morning.", "second": "Grown  close to home."}
        self.target = preview.target_for(self.store_repo.run((SET, spaced))["records"][0])
        self.assertEqual(self.target["headline"], [spaced["first"], spaced["second"]])
        result = self.capture()
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        self.assertIs(result["checks"]["headlineShown"], True)

    def test_old_page_with_new_target_fails(self):
        result = self.capture({INDEX: self.old_index})
        self.assertIs(result["checks"]["headlineShown"], False)
        self.assertEqual((result["ok"], result["error"]), (False, "check failed: headlineShown"))


if __name__ == "__main__":
    unittest.main()
