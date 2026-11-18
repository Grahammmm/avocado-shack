"""AV2152-10 tests: a draft that adds a health or award claim the owner did not say asks, never drafts.

Same NB-AV-05 rules (whole words, space or hyphen, folded text, negation, counts against the text before).
Run: python3 -B -m unittest hass.tests.test_claims_health_awards -v
"""

import unittest

from hass import claims, conversation, voice
from hass.label_reader import keep
from hass.tests.test_claims import MAKERS, P1, edit
from hass.tests.test_conversation import ConversationTestCase, _ops

TERMS = ("cures", "heals", "prevents", "immune", "immunity", "detox", "anti-inflammatory", "antioxidant", "probiotic",
         "superfood", "medicinal", "lowers cholesterol", "weight loss", "award-winning", "prize-winning", "gold medal")
CATS = ["fruit", "honey", "oils"]


class HealthAwardTermTests(unittest.TestCase):
    def hits(self, before, after, owner="", **kw):
        return [term for _w, term in claims.unstated(edit(before, after, **kw), owner, MAKERS)]

    def test_terms_are_a_separate_tuple_not_in_terms(self):
        self.assertEqual(claims.HEALTH_AWARD_TERMS, TERMS)
        self.assertFalse(set(TERMS) & set(claims.TERMS))
        self.assertNotIn("treat", claims.HEALTH_AWARD_TERMS + claims.TERMS)
        self.assertNotIn("best", claims.HEALTH_AWARD_TERMS + claims.TERMS)

    def test_each_health_award_term_asks(self):
        for term in TERMS:
            with self.subTest(term=term):
                hits = claims.unstated(edit("", f"A {term} jar."), "describe it", MAKERS)
                self.assertEqual(hits, [("products p1 description", term)])

    def test_each_owner_affirmed_term_is_allowed(self):
        for term in TERMS:
            with self.subTest(term=term):
                self.assertEqual(self.hits("", f"A {term} jar.", f"say {term}"), [])

    def test_folding_and_hyphen_space_variants(self):
        cases = (("ANTIOXIDANT", "antioxidant"), ("Pr\u00f3biotic", "probiotic"), ("\uff53\uff55\uff50\uff45\uff52\uff46\uff4f\uff4f\uff44", "superfood"),
                 ("anti\u2011inflammatory", "anti-inflammatory"), ("anti inflammatory", "anti-inflammatory"),
                 ("lowers-cholesterol", "lowers cholesterol"), ("weight-loss", "weight loss"),
                 ("award winning", "award-winning"), ("prize winning", "prize-winning"), ("gold-medal", "gold medal"))
        for spelled, term in cases:
            with self.subTest(spelled=spelled):
                self.assertEqual(self.hits("", f"A {spelled} jar."), [term])
                self.assertEqual(self.hits("", f"A {spelled} jar.", f"it is {term}"), [])
                self.assertEqual(self.hits("", f"A {term} jar.", f"it is {spelled}"), [])

    def test_whole_words_and_excluded_words(self):
        self.assertEqual(self.hits("", "Boosts immunity"), ["immunity"])
        self.assertEqual(self.hits("", "Stay immune"), ["immune"])
        self.assertEqual(self.hits("", "Boosts immunity", "stay immune"), ["immunity"])
        self.assertEqual(self.hits("", "Stay immune", "boosts immunity"), ["immune"])
        for after in ("detoxification", "healsome", "antioxidants", "probioticity", "superfoods", "gold medallion"):
            with self.subTest(after=after):
                self.assertEqual(self.hits("", f"A {after} jar."), [])
        self.assertEqual(self.hits("", "The best way to treat yourself"), [])
        self.assertEqual(self.hits("", "Best treat", "probiotic"), [])

    def test_negation_and_clause_window(self):
        for owner, term in (("not immune", "immune"), ("isnt probiotic", "probiotic"),
                            ("without award-winning", "award-winning"), ("it is no gold medal", "gold medal")):
            with self.subTest(owner=owner):
                self.assertEqual(self.hits("", f"A {term} jar.", owner), [term])
        self.assertEqual(self.hits("", "Stay immune", "not sick. immune is good"), [])
        self.assertEqual(self.hits("", "Stay immune", "I do not think so but immune"), [])  # negator 4 words back: outside the window
        self.assertEqual(self.hits("", "Stay immune", "I do not think so immune"), ["immune"])  # 3 words back: inside
        self.assertEqual(self.hits("", "Not immune at all"), ["immune"])  # negated draft wording still asks

    def test_counts_lists_and_collections(self):
        self.assertEqual(self.hits("Award-winning jam", "Award-winning jam, sweet"), [])
        self.assertEqual(self.hits("Award-winning jam", "Jam"), [])
        self.assertEqual(self.hits("Award-winning jam", "Award-winning jam, award winning"), ["award-winning"])
        for collection, key, field in (("makers", "m1", "bio"), ("events", "e1", "description"),
                                       ("stores", "s1", "note"), ("products", "p1", "name")):
            with self.subTest(collection=collection):
                hits = claims.unstated(edit("", "Probiotic", field=field, collection=collection, key=key), "", MAKERS)
                self.assertEqual(hits, [(f"{collection} {key} {field}", "probiotic")])
        draft = edit(["Mon 9-6"], ["Mon 9-6", "Detox Saturdays"], field="hours", collection="stores", key="s1")
        self.assertEqual([t for _w, t in claims.unstated(draft, "", MAKERS)], ["detox"])
        self.assertEqual(claims.unstated(edit(None, 5, field="rank"), "", MAKERS), [])
        many = claims.unstated(edit("", "Cures, heals, prevents, immune"), "", MAKERS)
        self.assertEqual([t for _w, t in many], ["cures", "heals", "prevents", "immune"])
        q = claims.question(many)
        self.assertIn('You didn\'t say "cures" and "heals" (and a few more) in your message', voice.plain(q))

    def test_revert_and_repeat_scope(self):
        revert = [{"op": "history.revert", "args": {"changeId": "c1"}}]
        self.assertEqual(self.hits("Jam", "Award-winning jam", ops=revert), [])
        mixed = revert + [{"op": "product.edit", "args": {}}]
        self.assertEqual(self.hits("Jam", "Award-winning jam", ops=mixed), ["award-winning"])
        sources = {"h1": {"title": "Detox hike", "trailId": "t1", "description": "A gold medal view"}}
        draft = {"ops": [{"op": "hike.repeat", "args": {"id": "h1", "date": "2026-12-01", "time": "08:00"}}],
                 "records": [{"collection": "events", "key": "hike-2026-12-01-a", "before": None,
                              "after": {"id": "hike-2026-12-01-a", "status": "scheduled", "title": "Detox hike",
                                        "startsAt": "2026-12-01T08:00", "trailId": "t1",
                                        "description": "A gold medal view"}}]}
        self.assertEqual(claims.unstated(draft, "", MAKERS, None, sources), [])
        draft["records"][0]["after"]["description"] = "A gold medal view, superfood"
        self.assertEqual([t for _w, t in claims.unstated(draft, "", MAKERS, None, sources)], ["superfood", "gold medal"])

    def test_label_values_cannot_supply_claims(self):
        for term in TERMS:
            for field in ("name", "brand", "category"):
                with self.subTest(term=term, field=field):
                    base = {"name": "Ranch Honey", "brand": "Acme", "category": "honey"}
                    found = keep({**base, field: f"{term} honey" if field != "category" else term}, CATS)
                    self.assertNotIn(field, found)
                    claim = f"{term} honey" if field != "category" else term
                    self.assertEqual(found, {**{k: v for k, v in base.items() if k != field},
                                             "printed_claims": [claim]})

    def test_treat_and_best_labels_remain_allowed(self):
        self.assertEqual(keep({"name": "Best Treat Honey", "brand": "Acme"}, CATS),
                         {"name": "Best Treat Honey", "brand": "Acme"})


class HealthAwardConversationTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def draft(self, owner, description):
        self.interp.mapping[owner] = _ops(("product.edit", {"id": P1, "description": description}))
        return self.say(owner)

    def test_unsaid_claim_asks_without_proposal_or_commit(self):
        self.assertEqual(self.draft("edit p1 description: smooth", "smooth, antioxidant honey"), "claim-question")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("You didn't say "), reply)
        self.assertIn('You didn\'t say "antioxidant" in your message', reply)
        self.assertEqual((self.drafts(), self.commits()), ([], 0))

    def test_owner_claim_proposes_not_applies(self):
        self.assertEqual(self.draft("edit p1 description: smooth, antioxidant honey", "smooth, antioxidant honey"),
                         "proposed")
        self.assertEqual(self.commits(), 0)

    def test_negated_owner_words_still_ask(self):
        text = "edit p1 description: smooth, not antioxidant honey"
        self.assertEqual(self.draft(text, "smooth, antioxidant honey"), "claim-question")
        self.assertEqual((self.drafts(), self.commits()), ([], 0))


if __name__ == "__main__":
    unittest.main()
