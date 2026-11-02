"""RF2030-4 tests: a negated owner word ("not organic", "isn't local") does not count as saying it.

Frozen rule: a match is negated when a negator is among the (up to) 3 words just before it in the same clause
(clauses end at . ! ? ; : or a newline). Fail-closed: a negated owner word leaves the claim unsaid, so the owner gets
the claim question, never a draft. Run: python3 -m unittest hass.tests.test_claims_negation -v
"""

import unittest

from hass import claims, conversation
from hass.tests.test_claims import MAKERS, P1, edit
from hass.tests.test_conversation import ConversationTestCase, _ops


class NegatedOwnerWordTests(unittest.TestCase):
    def hits(self, before, after, owner="", **kw):
        return [term for _w, term in claims.unstated(edit(before, after, **kw), owner, MAKERS)]

    def test_negated_owner_word_is_a_hit_with_its_field(self):
        hits = claims.unstated(edit("Avocados", "Organic avocados"), "these are NOT organic, please fix it", MAKERS)
        self.assertEqual(hits, [("products p1 description", "organic")])

    def test_plain_owner_word_is_still_said(self):
        self.assertEqual(self.hits("Avocados", "Organic avocados", "Organic avocados from our farm"), [])

    def test_each_negator_negates(self):
        for neg in claims.NEGATORS:
            with self.subTest(neg=neg):
                self.assertEqual(self.hits("", "Local avocados", f"they {neg} local"), ["local"])

    def test_negator_up_to_three_words_before(self):
        for owner in ("isn't local", "is not really local", "not grown very local", "no longer organic local"):
            with self.subTest(owner=owner):
                self.assertEqual(self.hits("", "Local avocados", owner), ["local"])
        # 4 words before: outside the window, so the comma-only clause leaves "organic" said
        self.assertEqual(self.hits("", "Organic avocados", "not from the farm, organic"), [])

    def test_clause_boundary_keeps_the_earlier_word_said(self):
        self.assertEqual(self.hits("", "Organic, local avocados", "organic. Not local."), ["local"])
        for owner in ("Not local. Organic", "not local! organic", "not local? organic", "not local; organic",
                      "not local: organic", "not local\norganic", "not local\r\norganic"):
            with self.subTest(owner=owner):  # a negator in the previous clause never negates
                self.assertEqual(self.hits("", "Organic avocados", owner), [])

    def test_typographic_apostrophe_is_folded(self):
        self.assertEqual(self.hits("", "Certified organic avocados", "it isn\u2019t certified organic"),
                         ["organic", "certified"])
        self.assertEqual(self.hits("", "Local avocados", "they aren\u02bct local"), ["local"])
        self.assertEqual(self.hits("", "Local avocados", "We DON\u2019T grow local"), ["local"])

    def test_no_longer_negates_and_non_inside_a_term_does_not(self):
        self.assertEqual(self.hits("", "Organic avocados", "no longer organic"), ["organic"])
        self.assertEqual(self.hits("", "Non-GMO avocados", "non-gmo avocados"), [])
        self.assertEqual(self.hits("", "Non-GMO avocados", "they are not non-gmo"), ["non-gmo"])
        self.assertEqual(self.hits("", "No preservatives added", "say no preservatives"), [])

    def test_stripped_punctuation_does_not_hide_a_negator(self):
        for owner in ('"not" organic', "(not organic)", "not, organic", 'is "not organic"'):
            with self.subTest(owner=owner):
                self.assertEqual(self.hits("", "Organic avocados", owner), ["organic"])

    def test_once_negated_once_plain_is_said(self):
        for owner in ("not organic yesterday, but organic now", "organic now. it was not organic before"):
            with self.subTest(owner=owner):
                self.assertEqual(self.hits("", "Organic avocados", owner), [])

    def test_fail_closed_on_not_only(self):
        self.assertEqual(self.hits("", "Organic, local avocados", "not only organic but local"), ["organic"])

    def test_revert_and_unchanged_counts_still_skip_even_when_negated(self):
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(self.hits("Avocados", "Organic avocados", "not organic", ops=revert), [])
        self.assertEqual(self.hits("Organic avocados", "Organic avocados, creamy", "not organic"), [])
        self.assertEqual(self.hits("Organic avocados", "Avocados", "not organic"), [])

    def test_maker_check_is_unchanged(self):
        draft = edit("Linn's", "Etto", field="producerKey")
        self.assertEqual(claims.unstated(draft, "not Etto", MAKERS),
                         [("products p1 producerKey", "maker")])  # RF0250-3: a negated maker is not named


class NegatedConversationTests(ConversationTestCase):
    """The production registry and the writer worktree's content, as the live conversation runs."""

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def test_negated_owner_text_asks_and_writes_no_row(self):
        text = "these are NOT organic, fix the p1 description"
        self.interp.mapping[text] = _ops(("product.edit", {"id": P1, "description": "Organic Hass avocados"}))
        self.assertEqual(self.say(text), "claim-question")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("I did not draft that: "), reply)
        self.assertIn(f'"organic" in products {P1} description is not in your message', reply)
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_plain_owner_text_still_proposes(self):
        text = "edit p1 description: Organic Hass avocados"
        self.interp.mapping[text] = _ops(("product.edit", {"id": P1, "description": "Organic Hass avocados"}))
        self.assertEqual(self.say(text), "proposed")


if __name__ == "__main__":
    unittest.main()
