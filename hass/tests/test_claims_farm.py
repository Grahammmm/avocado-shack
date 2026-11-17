"""RF2330-12: farm claims need owner words; a photo never supplies them."""
import unittest

from hass import claims, conversation
from hass.tests.test_claims import MAKERS, P1, edit
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_label_reader import reader, recorded

FARM = ("fair trade", "fairtrade", "free-range", "cage-free", "hormone-free", "antibiotic-free", "biodynamic",
        "regenerative", "chemical-free", "unsprayed")


class FarmTermTests(unittest.TestCase):
    def hits(self, before, after, owner="", **kw):
        return [term for _where, term in claims.unstated(edit(before, after, **kw), owner, MAKERS)]

    def test_each_term_needs_affirmative_owner_words(self):
        self.assertEqual(claims.FARM_TERMS, FARM)
        for term in FARM:
            with self.subTest(term=term):
                self.assertEqual(self.hits("", f"A {term} item."), [term])
                self.assertEqual(self.hits("", f"A {term} item.", f"say {term}"), [])
                self.assertEqual(self.hits("", term, f"they are not {term}"), [term])

    def test_folded_hyphen_and_space_spellings(self):
        for text, term in (("Free range eggs", "free-range"), ("free‑range", "free-range"),
                           ("Cage free", "cage-free"), ("FAIR-TRADE coffee", "fair trade"),
                           ("Fairtrade beans", "fairtrade")):
            with self.subTest(text=text):
                self.assertEqual(self.hits("", text), [term])
                self.assertEqual(self.hits("", term, f"say {text}"), [])
        self.assertEqual(self.hits("", "fair trade coffee", "fair-trade"), [])

    def test_whole_words_and_fail_closed_ambiguous_phrase(self):
        for text in ("rangefinder", "regenerate the page", "chemicals", "sprayed"):
            with self.subTest(text=text):
                self.assertEqual(self.hits("", text), [])
        # Fail closed: even this non-claim wording asks rather than drafting a claim.
        self.assertEqual(self.hits("", "a free range of sizes"), ["free-range"])

    def test_counts_and_removal_for_every_term(self):
        for term in FARM:
            with self.subTest(term=term):
                self.assertEqual(self.hits(term, f"{term} item."), [])
                self.assertEqual(self.hits(term, f"{term} item, {term}."), [term])
                self.assertEqual(self.hits(term, "plain item"), [])

    def test_applies_outside_products_too(self):
        for collection in ("makers", "store", "events", "routeIdeas"):
            with self.subTest(collection=collection):
                self.assertEqual(self.hits("", "regenerative", collection=collection), ["regenerative"])

    def test_label_transport_quarantines_farm_claims_from_identity_fields(self):
        for term in FARM + ("Cage-Free Eggs", "free‑range", "FAIR-TRADE"):
            for field in ("name", "brand", "category"):
                with self.subTest(term=term, field=field):
                    values = {"name": "Large Eggs", "brand": "Dana", "category": "eggs"}
                    values[field] = term
                    labels, transport = reader(recorded(values))
                    found = labels.read(b"fixture image", ["eggs", term])
                    self.assertEqual(found, {**{k: v for k, v in values.items() if k != field},
                                             "printed_claims": [term]})
                    self.assertEqual(len(transport.calls), 1)
        labels, _ = reader(recorded({"name": "Large Eggs"}))
        self.assertEqual(labels.read(b"fixture image", []), {"name": "Large Eggs"})


class FarmConversationTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def test_unstated_or_negated_claim_never_creates_a_draft(self):
        for text in ("edit description: eggs", "they are not cage-free"):
            with self.subTest(text=text):
                self.interp.mapping[text] = _ops(("product.edit", {"id": P1, "description": "Cage-free eggs"}))
                self.assertEqual(self.say(text), "claim-question")
                [reply] = self.replies()
                self.assertIn('You didn\'t say "cage-free" in your message. Is that true?', reply)
                self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_owner_words_still_propose(self):
        text = "edit description: cage free eggs"
        self.interp.mapping[text] = _ops(("product.edit", {"id": P1, "description": "Cage-free eggs"}))
        self.assertEqual(self.say(text), "proposed")


if __name__ == "__main__":
    unittest.main()
