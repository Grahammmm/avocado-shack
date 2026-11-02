"""RF0250-3 tests: a maker the owner names only to deny it ("isn't from Etto") is not named; producerKey to it asks.

Same 3-word negator rule (RF2030-4 `_affirmed`) as claim terms, on hand-made draft records.
Run: python3 -m unittest hass.tests.test_claims_maker_negation -v
"""

import unittest

from hass import claims
from hass.tests.test_claims import MAKERS, edit

ASK = [("products p1 producerKey", "maker")]


def maker(key, owner, makers=MAKERS):
    return claims.unstated(edit(None, key, field="producerKey"), owner, makers)


class MakerNegationTests(unittest.TestCase):
    def test_denied_maker_asks_and_the_affirmed_one_in_the_same_clause_is_said(self):
        owner = "this jam isn't from Etto, it's from Linn's"
        self.assertEqual(maker("Etto", owner), ASK)
        self.assertEqual(maker("Linn's", owner), [])

    def test_negated_key_or_name_asks_and_a_negator_in_the_next_clause_does_not(self):
        self.assertEqual(maker("Etto", "not Etto"), ASK)
        self.assertEqual(maker("Etto", "never from Etto Pastificio"), ASK)  # name match negated too
        self.assertEqual(maker("Etto", "Etto. Not organic."), [])

    def test_negator_more_than_three_words_before_does_not_negate(self):
        self.assertEqual(maker("Etto", "not the jam we get from Etto"), [])
        self.assertEqual(maker("Etto", "not jam from Etto"), ASK)  # "not" is 3 words back: inside the window

    def test_maker_on_its_own_line_after_a_negated_line(self):
        owner = "not from Linn's\nfrom Etto"
        self.assertEqual(maker("Etto", owner), [])
        self.assertEqual(maker("Linn's", owner), ASK)

    def test_maker_added_in_the_same_draft_and_named_is_said_and_negated_asks(self):
        def draft(owner):
            return claims.unstated({"ops": [{"op": "maker.add", "args": {}}, {"op": "product.edit", "args": {}}],
                                    "records": [
                {"collection": "makers", "key": "lo", "before": None, "after": {"name": "Los Osos Grove"}},
                {"collection": "products", "key": "p1", "before": {"producerKey": None},
                 "after": {"producerKey": "lo"}}]}, owner, MAKERS)
        self.assertEqual(draft("new maker Los Osos Grove"), [])
        self.assertEqual(draft("it isn't Los Osos Grove"), ASK)

    def test_unreadable_makers_always_ask_even_when_affirmed(self):
        self.assertEqual(maker("Etto", "from Etto", None), ASK)
        self.assertEqual(maker("Etto", "it is from Etto Pastificio", None), ASK)

    def test_typographic_apostrophe_in_the_negator_is_folded(self):
        self.assertEqual(maker("Etto", "isn\u2019t from Etto"), ASK)
        self.assertEqual(maker("Linn's", "it\u2019s from Linn\u2019s, it isn\u2019t from Etto"), [])
        self.assertEqual(maker("Etto", "it\u2019s from Linn\u2019s, it isn\u2019t from Etto"), ASK)


if __name__ == "__main__":
    unittest.main()
