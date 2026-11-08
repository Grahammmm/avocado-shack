"""AV2022-04 tests: a draft setting a product brand/displayBrand, maker place or maker link that shares no word with the
owner's message asks, never drafts.

Frozen rule: a changed brand/displayBrand/place must share one folded whole word (stop words and single characters
dropped) with the owner's text; a changed maker url's host (www. removed) must appear in it. "Producer not identified"
and values made only of stop words are not checked. Run: python3 -m unittest hass.tests.test_claims_sources -v
"""

import unittest

from hass import claims, conversation
from hass.tests.test_claims import MAKERS, P1, edit
from hass.tests.test_conversation import ConversationTestCase, _ops

STRAUS = "Straus Family Creamery"
ETTO = "https://www.ettopastificio.com/x"


def maker_add(after):
    return {"ops": [{"op": "maker.add", "args": {}}],
            "records": [{"collection": "makers", "key": "New", "before": None, "after": after}]}


class SourceFieldTests(unittest.TestCase):
    def hits(self, before, after, owner, field="brand", collection="products", **kw):
        return claims.unstated(edit(before, after, field, collection, **kw), owner, MAKERS)

    def test_brand_sharing_no_word_is_a_hit(self):
        self.assertEqual(self.hits("Avocado Shack", STRAUS, "change the milk brand"), [("products p1 brand", "brand")])
        self.assertEqual(self.hits(None, STRAUS, "new brand", field="displayBrand"),
                         [("products p1 displayBrand", "displayBrand")])

    def test_one_shared_word_case_folded_is_enough(self):
        self.assertEqual(self.hits("Avocado Shack", STRAUS, "brand is straus"), [])
        self.assertEqual(self.hits("Avocado Shack", STRAUS, "STRAUS milk", field="displayBrand"), [])

    def test_accents_fold_and_stop_words_do_not_count(self):
        self.assertEqual(self.hits("x", "Creme Co", "Brand: Crème Co."), [])
        self.assertEqual(self.hits("x", "Crème Co", "brand: creme"), [])
        # sharing only a stop word or a single letter is not sharing a word
        self.assertEqual(self.hits("x", "The Olive Co", "the co is new"), [("products p1 brand", "brand")])
        self.assertEqual(self.hits("x", "J Olive", "brand j"), [("products p1 brand", "brand")])

    def test_part_of_a_word_is_not_a_word(self):
        self.assertEqual(self.hits("x", STRAUS, "strausberg brand"), [("products p1 brand", "brand")])
        self.assertEqual(self.hits("x", "Linn", "linn's"), [])  # an apostrophe ends the word

    def test_placeholder_and_unchanged_brand_are_not_checked(self):
        self.assertEqual(self.hits("Straus", "Producer not identified", "clear the brand"), [])
        self.assertEqual(self.hits(STRAUS, STRAUS, "fix the price"), [])
        self.assertEqual(self.hits("x", "producer not identified", "clear it"), [("products p1 brand", "brand")])

    def test_stop_word_only_or_blank_value_is_not_checked(self):
        for new in ("The Co", "A & Co.", "", "  "):
            with self.subTest(new=new):
                self.assertEqual(self.hits("x", new, "fix it"), [])

    def test_maker_place(self):
        place = {"name": "New Maker", "place": "Cayucos, California"}
        self.assertEqual(claims.unstated(maker_add(place), "add New Maker", MAKERS), [("makers New place", "place")])
        self.assertEqual(claims.unstated(maker_add(place), "add New Maker from cayucos", MAKERS), [])
        self.assertEqual(self.hits("Cambria", "Los Osos", "moved to osos", "place", "makers"), [])
        self.assertEqual(self.hits("Cambria", "Los Osos", "moved", "place", "makers"), [("makers p1 place", "place")])

    def test_maker_link_host_must_be_in_owner_text(self):
        url = lambda owner, new=ETTO: self.hits(None, new, owner, "url", "makers", key="Etto")
        self.assertEqual(url("website is ettopastificio.com"), [])
        self.assertEqual(url("site: WWW.EttoPastificio.com/about."), [])
        self.assertEqual(url("update Etto's website"), [("makers Etto url", "link")])
        self.assertEqual(url("site is notettopastificio.com"), [("makers Etto url", "link")])
        self.assertEqual(url("site is ettopastificio.com.evil"), [("makers Etto url", "link")])
        self.assertEqual(url("site is shop.ettopastificio.com"), [("makers Etto url", "link")])
        self.assertEqual(url("ettopastificio.com", "https://ettopastificio.com.evil.example/x"), [("makers Etto url", "link")])
        self.assertEqual(url("ettopastificio.com", "https://user@ettopastificio.com:8443/"), [])
        self.assertEqual(url("anything", "https:///x"), [("makers Etto url", "link")])  # no host: asks

    def test_product_url_and_other_fields_are_not_source_fields(self):
        self.assertEqual(self.hits("x", STRAUS, "fix it", field="name"), [])
        self.assertEqual(self.hits("x", STRAUS, "fix it", field="brand", collection="makers"), [])

    def test_term_scan_still_runs_so_one_field_gives_both_hits(self):
        self.assertEqual(self.hits("x", "Organic Valley", "new brand"),
                         [("products p1 brand", "brand"), ("products p1 brand", "organic")])
        self.assertEqual(self.hits("x", "Organic Valley", "brand: valley"), [("products p1 brand", "organic")])

    def test_revert_only_draft_is_not_checked_mixed_is(self):
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(self.hits("Avocado Shack", STRAUS, "undo", ops=revert), [])
        self.assertEqual(self.hits("Avocado Shack", STRAUS, "undo", ops=revert + [{"op": "product.edit", "args": {}}]),
                         [("products p1 brand", "brand")])


class SourceConversationTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def brand(self, text, value):
        self.interp.mapping[text] = _ops(("product.edit", {"id": P1, "brand": value}))
        return self.say(text)

    def test_unsaid_brand_asks_and_writes_no_row(self):
        self.assertEqual(self.brand("change the milk brand", STRAUS), "claim-question")
        [reply] = self.replies()
        self.assertIn('You didn\'t say "brand" in your message. Is that true?', reply)
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_brand_in_owner_text_proposes(self):
        self.assertEqual(self.brand("brand is Straus Family Creamery", STRAUS), "proposed")
        self.assertIn(STRAUS, self.replies()[0])


if __name__ == "__main__":
    unittest.main()
