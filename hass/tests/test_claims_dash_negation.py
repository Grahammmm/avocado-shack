"""RF0240-12 tests: a negator attached by a dash ("not-organic", "not—organic") still negates the claim after it.

Run: python3 -m unittest hass.tests.test_claims_dash_negation -v
"""

import unittest

from hass import claims
from hass.tests import test_claims
from hass.tests.test_claims import MAKERS, edit, _ops, P1

ORGANIC = [("products p1 description", "organic")]


def hits(after, owner, before="Avocados", **kw):
    return claims.unstated(edit(before, after, **kw), owner, MAKERS)


class DashNegationTests(unittest.TestCase):
    def test_dash_attached_negator_blocks_added_claim(self):
        for owner in ("these are not-organic", "these are not\u2014organic", "these are not\u2013organic",
                      "these are not -organic", "these are not- organic", "these are not - organic"):
            with self.subTest(owner=owner):
                self.assertEqual(hits("Organic avocados", owner), ORGANIC)

    def test_three_prefix_tokens_after_dash_split(self):
        for owner in ("not-organic", "not-really-organic", "not-very-really-organic"):
            with self.subTest(owner=owner):
                self.assertEqual(hits("Organic avocados", owner), ORGANIC)
        self.assertEqual(hits("Organic avocados", "not-very-really-truly-organic"), [])

    def test_compound_claim_and_contraction_matching_survive(self):
        self.assertEqual(hits("Gluten-free bread", "not\u2014gluten-free"), [("products p1 description", "gluten-free")])
        self.assertEqual(hits("Gluten-free bread", "it is gluten-free"), [])
        self.assertEqual(hits("Organic avocados", "isn't\u2014organic"), ORGANIC)
        self.assertEqual(hits("Organic non-GMO", "organic and non-gmo"), [])
        self.assertEqual(hits("Non-GMO avocados", "non-gmo"), [])

    def test_other_clause_and_second_clean_occurrence_affirm(self):
        self.assertEqual(hits("Organic avocados", "Not-this. Organic"), [])
        self.assertEqual(hits("Organic avocados", "not-organic; organic"), [])
        self.assertEqual(hits("Organic avocados", "not-this\norganic"), [])

    def test_maker_name_prefix_uses_same_negator_tokens(self):
        maker = lambda key, owner: claims.unstated(edit(None, key, field="producerKey"), owner, MAKERS)
        self.assertEqual(maker("Etto", "not\u2014Etto"), [("products p1 producerKey", "maker")])
        self.assertEqual(maker("Etto", "from Etto"), [])

    def test_counts_and_revert_exemptions_remain(self):
        self.assertEqual(hits("Organic avocados", "not-organic", before="Organic avocados"), [])
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(hits("Organic avocados", "not-organic", ops=revert), [])


class DashNegationConversationTests(test_claims.ClaimConversationTests):
    test_added_organic_description_asks_and_owner_words_propose = None
    test_unnamed_maker_asks_and_named_maker_proposes = None
    test_revision_with_a_claim_leaves_the_waiting_draft = None
    test_undo_restoring_organic_text_is_proposed = None

    def test_denied_organic_fake_interpreter_asks_without_proposal(self):
        reply = self.asks("these are not\u2014organic",
                          _ops(("product.edit", {"id": P1, "description": "Organic and creamy."})))
        self.assertRegex(reply, r'You didn\'t say "organic" in your message')
        self.assertEqual((self.drafts(), self.commits()), ([], 0))


if __name__ == "__main__":
    unittest.main()
