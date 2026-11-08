"""RF2020-1 tests: a draft that adds a grade, process or diet claim the owner did not say asks, never drafts.

Same NB-AV-05 rules (whole words, space or hyphen, folded text, counts against the text before) for the new terms.
Run: python3 -m unittest hass.tests.test_claims_grades -v
"""

import unittest

from hass import claims, conversation, voice
from hass.tests.test_claims import MAKERS, P1, edit
from hass.tests.test_conversation import ConversationTestCase, _ops

OLD = ("organic", "certified", "pesticide-free", "spray-free", "non-gmo", "local", "locally", "grown in", "made in",
       "raised in", "harvested in", "sourced from", "produced in", "family farm", "estate")
NEW = ("extra virgin", "cold pressed", "first press", "unfiltered", "unpasteurized", "raw honey", "gluten-free",
       "dairy-free", "nut-free", "sugar-free", "vegan", "kosher", "halal", "all natural", "no preservatives", "grass-fed",
       "pasture-raised", "wild-caught")


class GradeTermTests(unittest.TestCase):
    def hits(self, before, after, owner="", **kw):
        return [term for _w, term in claims.unstated(edit(before, after, **kw), owner, MAKERS)]

    def test_terms_appended_after_the_existing_fifteen(self):
        self.assertEqual(claims.TERMS, OLD + NEW)

    def test_each_new_term_alone_hits_only_itself(self):
        for term in NEW:
            with self.subTest(term=term):
                self.assertEqual(self.hits("", f"A {term} jar."), [term])
                self.assertEqual(self.hits("", f"A {term} jar.", f"say {term}"), [])

    def test_unsaid_extra_virgin_is_named_with_its_field(self):
        hits = claims.unstated(edit("", "Extra virgin olive oil"), "add Sunshine oil", MAKERS)
        self.assertEqual(hits, [("products p1 description", "extra virgin")])
        self.assertIn('You didn\'t say "extra virgin" in your message', voice.plain(claims.question(hits)))

    def test_owner_spellings_count_as_said(self):
        for owner in ("it is extra-virgin", "Extra Virgin oil", "extra\u2011virgin", "EXTRA  VIRGIN"):
            with self.subTest(owner=owner):
                self.assertEqual(self.hits("", "Extra virgin olive oil", owner), [])

    def test_counts_compare_with_the_text_before(self):
        kept = "Extra virgin olive oil."
        self.assertEqual(self.hits(kept, "Extra virgin olive oil. Peppery."), [])
        self.assertEqual(self.hits(kept, "Extra virgin olive oil, extra-virgin taste."), ["extra virgin"])
        self.assertEqual(self.hits(kept, "Olive oil."), [])  # removing a claim is not adding one

    def test_whole_words_only(self):
        for after in ("Virgin olive oil", "Pressed apples", "Gluten in the flour", "Veganism", "unfilteredness",
                      "kosherish salt", "first pressing"):
            with self.subTest(after=after):
                self.assertEqual(self.hits("", after), [])

    def test_hyphen_and_space_spellings_match_either(self):
        for after in ("Cold-pressed juice", "cold pressed juice", "Cold\u2011pressed juice"):
            with self.subTest(after=after):
                self.assertEqual(self.hits("", after), ["cold pressed"])
                self.assertEqual(self.hits("", after, "make it cold-pressed"), [])
        self.assertEqual(self.hits("", "Gluten Free bread"), ["gluten-free"])
        self.assertEqual(self.hits("", "No preservatives added"), ["no preservatives"])
        self.assertEqual(self.hits("", "Grass fed, wild caught"), ["grass-fed", "wild-caught"])

    def test_hits_in_terms_order_and_two_hits_have_no_more(self):
        hits = claims.unstated(edit("", "Vegan and organic"), "", MAKERS)
        self.assertEqual([t for _w, t in hits], ["organic", "vegan"])
        q = claims.question(hits)
        self.assertIn('You didn\'t say "organic" and "vegan" in your message', voice.plain(q))
        self.assertNotIn("more", q)

    def test_a_pure_revert_is_not_checked(self):
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(self.hits("Olive oil", "Extra virgin olive oil", ops=revert), [])
        mixed = revert + [{"op": "product.edit", "args": {}}]
        self.assertEqual(self.hits("Olive oil", "Extra virgin olive oil", ops=mixed), ["extra virgin"])


class GradeConversationTests(ConversationTestCase):
    """The production registry and the writer worktree's content, as the live conversation runs."""

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def test_unsaid_unfiltered_asks_and_writes_no_row(self):
        text = "edit p1 description: smooth"
        self.interp.mapping[text] = _ops(("product.edit", {"id": P1, "description": "smooth, unfiltered honey"}))
        self.assertEqual(self.say(text), "claim-question")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("You didn't say "), reply)
        self.assertIn('You didn\'t say "unfiltered" in your message', reply)
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_owner_words_still_propose(self):
        text = "edit p1 description: smooth, unfiltered honey"
        self.interp.mapping[text] = _ops(("product.edit", {"id": P1, "description": "smooth, unfiltered honey"}))
        self.assertEqual(self.say(text), "proposed")


if __name__ == "__main__":
    unittest.main()
