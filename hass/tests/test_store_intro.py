"""AVB-13 (H13): the home-page intro line is an owner-editable store field (``store.set_intro``).

Every change goes through ``editor.prepare`` + ``editor.apply`` on a throwaway Git repo (test_store_ops.StoreRepo).
Nothing touches the checkout, the live service or its database.
Run: python3 -m unittest hass.tests.test_store_intro -v
"""

import copy
import unittest

from hass import sitegen
from hass.content_model import DEFAULT_INTRO, load_content, validate_store
from hass.tests.test_store_ops import INDEX, REVERT, StoreTestCase, _req

SET_INTRO = "store.set_intro"
DEFAULT_TAG = f'<p class="hero-intro">{DEFAULT_INTRO}</p>'
STORE = load_content().store


def problems_for(**changes):
    store = copy.deepcopy(STORE)
    store.update(changes)
    problems = []
    validate_store(problems, store)
    return problems


class IntroTests(StoreTestCase):
    def test_no_intro_renders_the_default_sentence_byte_for_byte(self):
        repo = self.repo()
        self.assertNotIn("intro", repo.store())
        self.assertIn(DEFAULT_TAG, repo.text(INDEX))
        self.assertEqual(sitegen.store_slots(STORE)["store.introHtml"], DEFAULT_INTRO)
        self.assertEqual(problems_for(), [])

    def test_set_then_undo_returns_to_the_identical_default_page(self):
        repo = self.repo()
        original = repo.read(INDEX)
        change = repo.run((SET_INTRO, {"text": "Fresh from the coast."}))
        self.assertEqual(repo.store()["intro"], "Fresh from the coast.")
        self.assertIn('<p class="hero-intro">Fresh from the coast.</p>', repo.text(INDEX))
        self.assertNotIn(DEFAULT_INTRO, repo.text(INDEX))
        repo.run((REVERT, {"changeId": change["change_id"]}))
        self.assertNotIn("intro", repo.store())
        self.assertEqual(repo.read(INDEX), original)
        self.assertEqual(repo.status(), "")

    def test_markup_is_refused_and_a_hand_written_value_renders_escaped(self):
        repo = self.repo()
        head = repo.head()
        result = repo.prepare(_req((SET_INTRO, {"text": "<script>alert(1)</script>"})))
        self.assertEqual(result["result"], "invalid", result)
        self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, [], ""))
        # defence in depth: whatever reaches the slot is escaped, never raw
        slot = sitegen.store_slots({**STORE, "intro": "<script>alert(1)</script>"})["store.introHtml"]
        self.assertEqual(slot, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_length_boundary_and_one_line(self):
        repo = self.repo()
        too_long = repo.prepare(_req((SET_INTRO, {"text": "a" * 161})))
        self.assertEqual(too_long["result"], "refused", too_long)
        self.assertEqual(too_long["reason"], "the intro is longer than 160 characters")
        for text in ("Line one\nline two", "Line one\rline two"):
            with self.subTest(text=repr(text)):
                self.assertEqual(repo.prepare(_req((SET_INTRO, {"text": text})))["result"], "invalid")
        repo.run((SET_INTRO, {"text": "a" * 160}))
        self.assertEqual(len(repo.store()["intro"]), 160)
        self.assertEqual(repo.status(), "")

    def test_same_text_is_refused_for_default_and_current(self):
        repo = self.repo()
        same_default = repo.prepare(_req((SET_INTRO, {"text": DEFAULT_INTRO})))
        self.assertEqual((same_default["result"], same_default["reason"]), ("refused", "the intro already says that"))
        repo.run((SET_INTRO, {"text": "Fresh from the coast."}))
        head = repo.head()
        again = repo.prepare(_req((SET_INTRO, {"text": "Fresh from the coast."})))
        self.assertEqual((again["result"], again["reason"]), ("refused", "the intro already says that"))
        self.assertEqual((repo.head(), repo.status()), (head, ""))

    def test_text_needs_three_letters_and_no_template_syntax(self):
        repo = self.repo()
        for text in ("12 34 56", "ab", "{{store.mapsUrl}}"):
            with self.subTest(text=text):
                self.assertNotEqual(repo.prepare(_req((SET_INTRO, {"text": text})))["result"], "ok")
        self.assertEqual(repo.prepare(_req((SET_INTRO, {"text": "ab"})))["reason"], "the intro needs at least 3 letters")
        self.assertEqual(repo.drafts(), [])


class ValidatorTests(unittest.TestCase):
    def test_unknown_store_key_is_still_refused(self):
        self.assertEqual(problems_for(introduction="Hello there"), ["store: unknown field 'introduction'"])

    def test_intro_limits_in_the_validator(self):
        self.assertEqual(problems_for(intro="a" * 160), [])
        self.assertEqual(problems_for(intro="a" * 161), ["store.intro: longer than 160 characters"])
        self.assertTrue(problems_for(intro="Line one\nline two"))
        self.assertTrue(problems_for(intro="<b>Fresh</b> food"))
        self.assertTrue(problems_for(intro="12 34"))
        self.assertTrue(problems_for(intro=5))


if __name__ == "__main__":
    unittest.main()
