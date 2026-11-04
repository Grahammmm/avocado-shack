"""RF1230-17 tests: a negator typed without its apostrophe ("isnt", "dont") or a has/have/had + n't contraction in
either spelling, among the 3 words before a claim term, leaves that term unsaid exactly like "not".

Window, clause and revert rules are unchanged (RF2030-4); the maker check (RF0250-3) gains the same words.
Run: python3 -m unittest hass.tests.test_claims_negation_spelling -v
"""

import unittest

from hass import claims
from hass.tests.test_claims import MAKERS, edit

SMITH = {**MAKERS, "smith": {"name": "Smith Farm"}}
ORGANIC = [("products p1 description", "organic")]


def hits(before, after, owner, **kw):
    return claims.unstated(edit(before, after, **kw), owner, MAKERS)


class NegatorSpellingTests(unittest.TestCase):
    def test_negator_without_apostrophe_is_a_hit_with_its_field(self):
        for neg in ("isnt", "doesnt", "dont", "arent", "wasnt", "cant"):
            with self.subTest(neg=neg):
                self.assertEqual(hits("Avocados", "Organic avocados", f"it {neg} organic"),
                                 [("products p1 description", "organic")])

    def test_every_new_spelling_is_a_negator(self):
        for neg in ("isnt", "arent", "wasnt", "werent", "dont", "doesnt", "didnt", "wont", "cant",
                    "hasn't", "haven't", "hadn't", "hasnt", "havent", "hadnt"):
            with self.subTest(neg=neg):
                self.assertIn(neg, claims.NEGATORS)
                self.assertEqual(hits("", "Local avocados", f"they {neg} local"),
                                 [("products p1 description", "local")])

    def test_old_negators_are_kept_and_negators_stay_a_tuple(self):
        self.assertIsInstance(claims.NEGATORS, tuple)
        for neg in ("not", "no", "never", "nor", "without", "isn't", "aren't", "wasn't", "weren't", "don't",
                    "doesn't", "didn't", "won't", "cannot", "can't"):
            self.assertIn(neg, claims.NEGATORS)

    def test_has_have_had_contractions_in_both_spellings(self):
        for owner in ("it hasn't been certified", "it hasnt been certified", "we haven't certified it",
                      "we havent certified it", "it hadn\u2019t been certified", "it hadnt been certified"):
            with self.subTest(owner=owner):
                self.assertEqual(hits("Avocados", "Certified avocados", owner),
                                 [("products p1 description", "certified")])

    def test_typographic_apostrophe_still_negates_and_plain_word_is_said(self):
        self.assertEqual(hits("", "Organic avocados", "it isn\u2019t organic"), ORGANIC)
        self.assertEqual(hits("", "Organic avocados", "it is organic"), [])
        self.assertEqual(hits("", "Organic avocados", "IT ISNT ORGANIC"), ORGANIC)

    def test_negator_outside_the_three_word_window_does_not_negate(self):
        self.assertEqual(hits("", "Organic avocados", "dont ask me why but it is organic"), [])
        self.assertEqual(hits("", "Organic avocados", "isnt really very organic"), ORGANIC)

    def test_clause_boundary_keeps_the_later_word_said(self):
        owner = "isnt local. it is organic"
        self.assertEqual(hits("", "Organic, local avocados", owner), [("products p1 description", "local")])
        self.assertEqual(hits("", "Organic avocados", owner), [])

    def test_once_negated_once_plain_is_said(self):
        self.assertEqual(hits("", "Organic avocados", "it wasnt organic before, but organic now"), [])

    def test_word_containing_a_negator_does_not_negate(self):
        for owner in ("dontcha love it, organic", "cantaloupe organic", "the wonton is organic"):
            with self.subTest(owner=owner):
                self.assertEqual(hits("", "Organic avocados", owner), [])

    def test_maker_negated_without_apostrophe_asks(self):
        def maker(owner):
            return claims.unstated(edit(None, "smith", field="producerKey"), owner, SMITH)
        ask = [("products p1 producerKey", "maker")]
        self.assertEqual(maker("we dont buy from Smith Farm"), ask)
        self.assertEqual(maker("we havent bought from smith"), ask)
        self.assertEqual(maker("we buy from Smith Farm"), [])
        self.assertEqual(maker("we dont buy from Etto. we buy from Smith Farm"), [])

    def test_revert_draft_is_never_checked(self):
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(hits("Avocados", "Organic avocados", "it isnt organic", ops=revert), [])
        self.assertEqual(claims.unstated(edit(None, "smith", field="producerKey", ops=revert),
                                         "we dont buy from Smith Farm", SMITH), [])


if __name__ == "__main__":
    unittest.main()
