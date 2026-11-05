"""FAV-05 (H13): the "COME ON IN" story paragraph is a named copy slot (``store.set_story``, hass/ops/home.py).

Every change goes through ``editor.prepare`` + ``editor.apply`` on a throwaway Git repo (test_store_ops.StoreRepo).
Capture tests run the real loopback preview server and Chromium; they are skipped when PLAYWRIGHT_MODULE is unset.
Run: python3 -m unittest hass.tests.test_store_story -v
"""

import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from hass import preview, sitegen
from hass.content_model import DEFAULT_STORY, REPO_ROOT, load_content, validate_store
from hass.tests.test_editor import git
from hass.tests.test_store_ops import INDEX, REVERT, StoreTestCase, _req

SET = "store.set_story"
NEW = "Michael Wolfe walks the farmers' market every week & brings back the best of the Central Coast for neighbors."
STORE = load_content().store


def refusal(repo, text):
    result = repo.prepare(_req((SET, {"text": text})))
    return result["result"], result.get("reason")


class StoryOpTests(StoreTestCase):
    def test_no_story_renders_todays_page_byte_for_byte(self):
        self.assertNotIn("story", STORE)
        self.assertEqual(sitegen.main(["--check"]), 0)
        page = sitegen.render(load_content())[INDEX]
        self.assertEqual(page, (REPO_ROOT / INDEX).read_bytes())
        self.assertIn(f"</h2><p>{DEFAULT_STORY}</p>", page.decode("utf-8"))
        self.assertIn("produce buyer\u2019s curiosity", DEFAULT_STORY)

    def test_set_then_undo_returns_to_the_identical_default_page(self):
        repo = self.repo()
        original, before = repo.read(INDEX), repo.store()
        change = repo.run((SET, {"text": NEW}))
        self.assertEqual(repo.store(), {**before, "story": NEW})
        self.assertIn("</h2><p>Michael Wolfe walks the farmers' market every week &amp; brings", repo.text(INDEX))
        self.assertNotIn(DEFAULT_STORY, repo.text(INDEX))
        self.assertIn('<p class="signature">With much gratitude', repo.text(INDEX))
        repo.run((REVERT, {"changeId": change["change_id"]}))
        self.assertEqual(repo.store(), before)
        self.assertEqual(repo.read(INDEX), original)
        self.assertEqual(repo.status(), "")

    def test_markup_template_dollar_and_control_characters_are_refused_before_any_draft(self):
        repo = self.repo()
        head = repo.head()
        for bad in ("<b>Big</b> " + NEW, NEW + " {{x}}", NEW + " $5", NEW + "\x07", NEW + "\nSecond line"):
            with self.subTest(bad=bad):
                self.assertEqual(refusal(repo, bad)[0], "invalid")
        self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, [], ""))

    def test_line_or_paragraph_separator_is_refused_as_not_one_paragraph(self):
        repo = self.repo()
        for sep in ("\u2028", "\u2029", "\u2028\u2028"):
            with self.subTest(sep=repr(sep)):
                self.assertEqual(refusal(repo, NEW + sep + "More words here."), ("refused", "the story is one paragraph"))
        self.assertEqual(repo.drafts(), [])

    def test_quotes_and_ampersand_render_escaped(self):
        slot = sitegen.store_slots({**STORE, "story": 'Salt & "pepper" <b>'})["store.storyHtml"]
        self.assertEqual(slot, 'Salt &amp; "pepper" &lt;b&gt;')

    def test_four_hundred_characters_accepted_four_hundred_one_refused(self):
        repo = self.repo()
        self.assertEqual(refusal(repo, "a" * 401), ("refused", "the story is longer than 400 characters"))
        self.assertEqual(repo.drafts(), [])
        repo.run((SET, {"text": "a" * 400}))
        self.assertEqual(repo.store()["story"], "a" * 400)

    def test_nineteen_letters_refused_twenty_accepted(self):
        repo = self.repo()
        self.assertEqual(refusal(repo, "abcdefghij klmnopqrs 1234 !!"), ("refused", "the story needs at least 20 letters"))
        self.assertEqual(refusal(repo, "abcdefghij klmnopqrst")[0], "ok")

    def test_same_words_as_the_default_and_as_the_current_are_refused(self):
        repo = self.repo()
        self.assertEqual(refusal(repo, DEFAULT_STORY), ("refused", "the story already says that"))
        self.assertEqual(refusal(repo, DEFAULT_STORY.replace(" ", "  ", 1)), ("refused", "the story already says that"))
        repo.run((SET, {"text": NEW}))
        self.assertEqual(refusal(repo, NEW), ("refused", "the story already says that"))
        self.assertEqual(refusal(repo, DEFAULT_STORY)[0], "ok")

    def test_undo_older_headline_keeps_the_newer_story_and_either_order_works(self):  # AV2152-11: was a conflict
        repo = self.repo()
        before = repo.store()
        older = repo.run(("store.set_headline", {"first": "Fresh from the coast.", "second": "Grown close to home."}))
        newer = repo.run((SET, {"text": NEW}))
        repo.run((REVERT, {"changeId": older["change_id"]}))
        self.assertEqual(repo.store(), {**before, "story": NEW})
        repo.run((REVERT, {"changeId": newer["change_id"]}))
        self.assertEqual(repo.store(), before)


class ValidatorTests(unittest.TestCase):
    def problems(self, story):
        store = copy.deepcopy(STORE)
        store["story"] = story
        problems = []
        validate_store(problems, store)
        return problems

    def test_story_limits(self):
        self.assertEqual(self.problems(DEFAULT_STORY), [])
        self.assertEqual(self.problems("a" * 400), [])
        for bad in ("a" * 401, 5, "<b>" + NEW, "a" * 19, NEW + "\u2029More", " " + NEW):
            with self.subTest(bad=bad):
                problems = self.problems(bad)
                self.assertTrue(problems)
                self.assertTrue(all(p.startswith("store.story") for p in problems), problems)


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class StoryCaptureTests(StoreTestCase):
    def setUp(self):  # as test_store_headline.HeadlineCaptureTests: the full site in a throwaway repo
        self.store_repo = repo = self.repo()
        wt = repo.wt
        for rel in git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
            if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, wt / rel)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "full site")
        self.old_index = repo.read(INDEX)
        holder = tempfile.TemporaryDirectory(prefix="hass-fav05-")
        self.addCleanup(holder.cleanup)
        self.out = Path(holder.name) / "shot.png"
        self.target = preview.target_for(repo.run((SET, {"text": NEW}))["records"][0])

    def capture(self, files=None, viewports=("phone",)):
        return preview.Previewer(self.store_repo.wt, viewports=viewports).capture(files or {}, self.target, self.out)

    def test_new_story_is_shown_on_phone_and_desktop(self):
        self.assertEqual(self.target["story"], NEW)
        result = self.capture(viewports=preview.VIEWPORTS)
        self.assertEqual((result["ok"], result["error"]), (True, None), result)
        for prefix in ("", "desktop:"):
            self.assertIs(result["checks"][prefix + "storyShown"], True)

    def test_old_page_with_new_target_fails(self):
        result = self.capture({INDEX: self.old_index})
        self.assertIs(result["checks"]["storyShown"], False)
        self.assertEqual((result["ok"], result["error"]), (False, "check failed: storyShown"))


if __name__ == "__main__":
    unittest.main()
