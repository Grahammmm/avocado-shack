"""AV1052-07 (F07/H17): `listing <name or alias>` shows the one ACTIVE product that name or saved alias fits, exactly as
`listing <id>` does; several active products reply find-style lines (up to 10, with ids). Exact ids, makers, hikes, route
ideas and `listing store` keep their meaning. Read-only. Synthetic fixtures only (the conversation test store).
Run: python3 -B -m unittest hass.tests.test_listing_by_name -v
"""

import unittest

from hass import conversation, voice
from hass.tests.test_post_by_name import MORE, NameFixture

HEAD = "This is from my saved copy, not a live look at the website:"
NONE = "I don't know that one. Try find and a word from its name."


class ListingByNameTests(NameFixture):
    verb = "listing"

    def listing(self, query):
        return self.ask(f"listing {query}")[0].splitlines()

    def test_name_alias_equals_exact_id(self):
        # Contract: a unique name or alias lists the same card as its id. Bug caught: name lookups showing different fields.
        self.assertNotIn("memory", self.tables())
        for query, pid in (("Figs", "photo-product-097"), ("brians SOURDOUGH bread.", "photo-product-015"), ("chevre", "photo-product-035")):
            with self.subTest(query=query):
                want = self.listing(pid)
                self.assertEqual(want[0], HEAD)
                self.assertEqual(self.listing(query), want)
        self.assertNotIn("memory", self.tables(), "a read created the memory table")
        self.assertEqual(self.say("alias green jam: photo-product-010"), "memory-saved")
        self.replies()
        self.assertEqual(self.listing("Green-Jam"), self.listing("photo-product-010"))

    def test_several_and_none_and_inactive(self):
        # Contract: several active matches are listed with ids, none says to use find, hidden/held names are not shown.
        # Bug caught: a name quietly choosing one of several, or a held product's card shown by its name.
        ids = self.active_ids("sourdough")
        self.assertEqual(len(ids), 3)
        lines = self.listing("sourdough")
        self.assertEqual([ln.split(":")[0] for ln in lines], [f"product {i}" for i in ids])
        self.assertTrue(all(ln.endswith("(active)") for ln in lines), lines)
        self.assertGreaterEqual(len(self.active_ids("chocolate")), 10)
        capped = self.listing("chocolate")
        self.assertEqual((len(capped), capped[-1]), (11, MORE))
        self.assertEqual(self.listing("nonesuch"), [NONE])
        self.assertEqual(self.listing("raw milk goat cheddar"), [NONE])  # held only
        self.assertEqual(self.listing("photo-product-133")[0], HEAD)  # its exact id can still be inspected
        self.assertEqual(self.listing("PHOTO-PRODUCT-097"), [NONE])  # an id is not case-repaired
        self.assertEqual(self.listing("photo-product-097x"), [NONE])

    def test_reserved_and_other_kinds_keep_precedence(self):
        # Contract: store, exact ids and maker names win over product-name lookups. Bug caught: `listing Etto` (a maker whose name
        # is also five products' brand) turning into a list of pasta, or a product called "store" hiding `listing store`.
        self.edit(lambda doc: doc["products"][1].update(name="store"))
        self.assertEqual(self.listing("store")[1], "Store")
        self.assertEqual(self.listing("etto")[:2], [HEAD, "Name: Etto"])
        self.assertEqual(self.listing("photo-product-001")[:2], [HEAD, "Name: Hass avocado"])

    def test_usage_and_sentences(self):
        # Contract: a bare or over-long word is the usage; a sentence naming nothing stays with the interpreter as on main. Bug caught:
        # "listing of everything please" answered here, or the usage missing the name/alias/find words.
        for text in ("listing", "listing " + "a" * 61):
            with self.subTest(text=text):
                self.assertEqual(self.ask(text), (voice.plain(conversation.LISTING_USAGE), []))
        for text in ("listing of everything please", "listing green\njam"):
            self.sentence(text)
        (self.cdir / "products.json").write_text("{not json", "utf-8")
        self.assertEqual(self.listing("green jam")[0], "I can't look that up right now. Nothing has changed. Could you try again in a little while?")

    def test_read_only_outcomes(self):
        # Contract: nothing but the reply is written, even paused. Bug caught: a memory table, draft or content change from a lookup.
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        before = (self.tables(), self.digest(), self.drafts())
        for query in ("Figs", "sourdough", "nonesuch"):
            self.listing(query)
        self.assertEqual((self.tables(), self.digest(), self.drafts()), before)


if __name__ == "__main__":
    unittest.main()
