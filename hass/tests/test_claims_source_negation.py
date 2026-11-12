"""RF0640-10 tests: a brand/displayBrand/maker place the owner only denied is not backed; one affirmed word still is.

Run: python3 -B -m unittest hass.tests.test_claims_source_negation -q
"""

import copy
import unittest

from hass import claims
from hass.tests.test_claims import MAKERS

FIELDS = (("products", "brand"), ("products", "displayBrand"), ("makers", "place"))


def hits(collection, field, new, owner, old=""):
    draft = {"ops": [{"op": "product.edit", "args": {}}],
             "records": [{"collection": collection, "key": "k1", "before": {field: old}, "after": {field: new}}]}
    snapshot = copy.deepcopy(draft)
    out = claims.unstated(draft, owner, MAKERS)
    assert draft == snapshot
    return out


def ask(collection, field):
    return [(f"{collection} k1 {field}", field)]


class SourceNegationTests(unittest.TestCase):
    def test_denied_only_source_words_ask_for_all_three_fields(self):
        for collection, field in FIELDS:
            for owner in ("not Straus", "never Straus", "without Straus", "isn't Straus", "isnt Straus", "dont use Straus"):
                self.assertEqual(hits(collection, field, "Straus", owner), ask(collection, field), (field, owner))

    def test_affirmed_occurrence_or_other_significant_word_is_enough(self):
        for collection, field in FIELDS:
            for owner in ("Straus", "not Straus. Use Straus", "not Straus\nStraus", "not Straus; Straus",
                          "not Straus family but Dairy"):
                new = "Straus Dairy" if "Dairy" in owner else "Straus"
                self.assertEqual(hits(collection, field, new, owner), [], (field, owner))

    def test_clause_window_folding_and_word_boundaries_are_inherited(self):
        self.assertEqual(hits("products", "brand", "Café", "NOT CAFE"), ask("products", "brand"))
        self.assertEqual(hits("products", "brand", "Straus", "not one two three Straus"), [])  # negator 4 words back
        self.assertEqual(hits("products", "brand", "Straus", "not it. Straus"), [])  # earlier clause
        self.assertEqual(hits("products", "brand", "Straus", "not Strausberg"), ask("products", "brand"))  # no substring
        self.assertEqual(hits("products", "brand", "Straus", "Strausberg"), ask("products", "brand"))
        self.assertEqual(hits("products", "brand", "A & The", "not a the"), [])  # stop/single-letter only: exempt

    def test_placeholder_unchanged_empty_and_url_contracts_stay_exact(self):
        self.assertEqual(hits("makers", "place", "Producer not identified", "not Cayucos"), [])
        self.assertEqual(hits("products", "brand", "  ", "not Straus"), [])
        self.assertEqual(hits("products", "brand", "Straus", "not Straus", old="Straus"), [])
        self.assertEqual(hits("products", "name", "Straus", "not Straus"), [])  # not a source field
        self.assertEqual(hits("makers", "brand", "Straus", "not Straus"), [])  # wrong collection
        self.assertEqual(hits("makers", "url", "https://straus.example", "not straus.example"), [])  # URL branch unchanged

    def test_source_hit_and_term_hit_keep_order(self):
        out = hits("products", "brand", "Straus organic", "not Straus, not organic")
        self.assertEqual(out, [("products k1 brand", "brand"), ("products k1 brand", "organic")])


if __name__ == "__main__":
    unittest.main()
