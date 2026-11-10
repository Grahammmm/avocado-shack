"""HASS-SEC-2 (findings H1, M1 and L4 of reports/hass/SEC-1.md): the live claim gate on adversarial text.

H1: lookalike letters, soft hyphens, variation selectors, tag and zero-width characters are folded or dropped BEFORE matching
(NFKC, then the lookalike skeleton); bare and +1 phone numbers, emails, web addresses and 'at/dot' spellings are contact; the
semantic claim classes have paraphrase patterns; and text the gate cannot classify but that carries a price, contact details,
a superlative or a word of mixed scripts is refused with the plain reason. Ordinary edits still pass.
M1 (pure part): an undo is judged by the same content gates as a change (protected sentences and fields, sign-up, 10 records).
L4: a town or brand named only in a question, or hedged ("-ish", "maybe", "no idea", "not sure"), is not the owner's words.
Entirely synthetic drafts; nothing is written. Run: python3 -B -m unittest hass.tests.test_sec2_live_gate -v
"""
import unittest

from hass import live_policy as policy, voice
from hass.tests.test_live_policy import edit

PLAIN = "A fresh jar."

# The adversarial strings of the SEC-1 probe (probe_policy.py), each must now be refused in every public text slot.
ADVERSARIAL = {
    "cyrillic o": "Pure \u043erganic avocados.",
    "greek omicron": "Pure \u03bfrganic avocados.",
    "soft hyphen": "Pure or\u00adganic avocados.",
    "variation selector": "Pure o\ufe0frganic avocados.",
    "tag char": "Pure o\U000e0020rganic avocados.",
    "zero-width space": "Pure or\u200bganic avocados.",
    "zero-width joiner": "Pure org\u200danic avocados.",
    "hangul filler": "Pure org\u3164anic avocados.",
    "armenian o": "Pure \u0585rganic avocados.",
    "malayalam tta (no lookalike entry: mixed script)": "Pure \u0d20rganic avocados.",
    "origin paraphrase 1": "Grown on the family ranch in Fillmore.",
    "origin paraphrase 2": "Picked fresh from Ojai orchards this week.",
    "pesticide paraphrase": "Never sprayed with pesticides.",
    "health paraphrase": "Good for your heart and your gut.",
    "health paraphrase 2": "Helps lower blood pressure naturally.",
    "award paraphrase": "Won first place at the county fair.",
    "endorse paraphrase": "Loved by the chefs at Chez Panisse.",
    "endorse paraphrase 2": "Trusted by Whole Foods.",
    "phone no separators": "Call Mike at 8055551234.",
    "phone +1": "Text +18055551234 any time.",
    "phone +1 spaced": "Text +1 805 555 1234 any time.",
    "phone half spaced": "Call 805 5551234.",
    "phone spelled": "Call eight oh five, five five five, one two three four.",
    "email spelled": "Email mike at gmail dot com.",
    "email bracket spelled": "Email mike [at] gmail [dot] com.",
    "email half spelled": "Email mike at gmail.com today.",
    "web host": "Find them at harborlane.com.",
    "web url": "See https://harborlane.example/about for more.",
    "web www": "See www.harborlane.net for more.",
    "web spelled": "Find them at harborlane dot com.",
    "social handle": "Follow @harborlane on Instagram.",
    "price words": "Five bucks a jar.",
    "price USD": "Only 5 USD a jar.",
    "price euro": "\u20ac5 a jar.",
    "price trailing": "Only 5\u20ac a jar.",
    "price pound": "\u00a34 a jar.",
    "price a dollar": "Just a dollar a jar.",
    "superlative": "The best lemon curd in California.",
    "superlative 2": "The creamiest avocados around.",
    "superlative 3": "World's finest honey.",
    "number one": "The number one jam in town.",
}

# Words a shop owner really uses for products, makers and hikes: still go live.
BENIGN = ["Sweet and creamy.", "Picked this week.", "Great on warm toast.", "A bright lemon curd.", "Sweet and tart on warm toast.",
          "A jar of quince jam on a plain counter", "Harbor Lane is based in Ventura, California.", "Back on the shelf Saturday.",
          "Ripe today, eat within two days.", "Bring a hat and a friend.", "Meet at the shop at 9.", "Rich, nutty and smooth.",
          "Café-style beans, roasted dark.", "Made with Meyer lemons.", "Thanks for a lovely morning!", "Ready by 10am."]


def maker_draft(story, place="Ventura, CA", alt="A jar of lemon curd"):
    prod = {"id": "p99", "name": "Lemon curd", "brand": "Harbor Lane", "displayBrand": "Harbor Lane", "producerKey": "harbor-lane",
            "description": "A bright lemon curd.", "imageAlt": alt}
    maker = {"name": "Harbor Lane", "place": place, "story": story}
    return {"ops": [{"op": "product.add", "args": {"name": "Lemon curd", "brand": "Harbor Lane", "producerKey": "harbor-lane",
                                                    "description": "A bright lemon curd.", "imageAlt": alt, "photo": "x"}},
                    {"op": "maker.add", "args": {"key": "harbor-lane", "name": "Harbor Lane", "place": place, "story": story}}],
            "records": [{"collection": "products", "key": "p99", "before": None, "after": prod},
                        {"collection": "makers", "key": "harbor-lane", "before": None, "after": maker}]}


def hike_draft(title):
    return {"ops": [{"op": "hike.create", "args": {"title": title}}],
            "records": [{"collection": "events", "key": "hike-x", "before": None,
                         "after": {"id": "hike-x", "title": title, "rsvpEnabled": False}}]}


def edit_draft(text, before=PLAIN):
    return {"ops": [{"op": "product.edit", "args": {"id": "p1", "description": text}}],
            "records": [{"collection": "products", "key": "p1", "before": {"id": "p1", "description": before},
                         "after": {"id": "p1", "description": text}}]}


class H1ClaimGateTests(unittest.TestCase):
    def slots(self, text):
        return {"description": policy.check(edit_draft(text)),
                "imageAlt": policy.check(maker_draft("Harbor Lane is based in Ventura.", alt=text)),
                "maker story": policy.check(maker_draft(text)),
                "hike title": policy.check(hike_draft(text))}

    def test_every_adversarial_string_is_refused_in_every_public_text_slot(self):
        for name, text in ADVERSARIAL.items():
            for slot, reasons in self.slots(text).items():
                with self.subTest(case=name, slot=slot):
                    self.assertTrue(reasons, f"{text!r} went live in {slot}")
                    self.assertTrue(all(r.startswith("protected sentences: ") for r in reasons), reasons)
                    words = policy.refusal(reasons)
                    self.assertIn("I can't put this on the website from chat", words)
                    self.assertEqual(voice.check(words, long_ok=True), [], words)

    def test_the_lookalike_spellings_are_the_same_claim_as_the_plain_word(self):
        for name in ("cyrillic o", "greek omicron", "soft hyphen", "variation selector", "tag char", "zero-width space",
                     "zero-width joiner", "hangul filler", "armenian o"):
            with self.subTest(case=name):
                self.assertIn("protected sentences: origin/organic", policy.check(edit_draft(ADVERSARIAL[name])))
                self.assertEqual(policy.sentences(ADVERSARIAL[name]), policy.sentences("Pure organic avocados."))

    def test_each_class_is_named(self):
        expect = {"pesticide paraphrase": "origin/organic", "origin paraphrase 1": "origin/organic",
                  "health paraphrase": "health/awards/endorsements", "award paraphrase": "health/awards/endorsements",
                  "endorse paraphrase": "health/awards/endorsements", "phone no separators": "contact", "phone +1": "contact",
                  "phone spelled": "contact", "email spelled": "contact", "web host": "contact", "social handle": "contact",
                  "price words": "prices", "price USD": "prices", "price euro": "prices", "price a dollar": "prices",
                  "superlative": "unchecked claims", "malayalam tta (no lookalike entry: mixed script)": "unchecked claims",
                  "armenian o": "unchecked claims"}
        for name, kind in expect.items():
            with self.subTest(case=name):
                self.assertIn(f"protected sentences: {kind}", policy.check(edit_draft(ADVERSARIAL[name])))
        self.assertIn("a claim I can't check", policy.refusal(["protected sentences: unchecked claims"]))

    def test_trail_paraphrases_are_refused_on_hikes(self):
        for text in ("Bring your dog, there is plenty of parking.", "Leashed pups are fine.", "Wheelchairs can reach the bench.",
                     "No permit needed for this one.", "An easy, flat walk.", "Restrooms at the trailhead."):
            with self.subTest(text=text):
                self.assertIn("protected sentences: trail facts", policy.check(hike_draft(text)))

    def test_a_maker_place_with_a_phone_number_is_refused(self):
        self.assertIn("protected sentences: contact", policy.check(maker_draft("Harbor Lane makes curd.", place="Call 8055551234, CA")))
        self.assertIn("protected sentences: origin/organic", policy.check(maker_draft("Harbor Lane makes curd.", place="Certified \u043erganic orchard")))

    def test_ordinary_words_still_go_live(self):
        for text in BENIGN:
            with self.subTest(text=text):
                self.assertEqual(policy.check(edit_draft(text)), [])
                self.assertEqual(policy.check(hike_draft(text)), [])
                self.assertEqual(policy.check(maker_draft(text)), [])

    def test_an_edit_that_keeps_an_existing_claim_sentence_still_passes(self):
        before = "Picked fresh from our own orchard. Sweet and creamy."
        self.assertEqual(policy.check(edit_draft("Picked fresh from our own orchard. Rich and creamy.", before)), [])
        self.assertTrue(policy.check(edit_draft("Rich and creamy.", before)))  # removing the claim is a claim change

    def test_decimal_numbers_and_coordinates_are_not_phones(self):
        for text in ("Mile 2.5 is the view point.", "Trailhead at 34.4208, -119.6982.", "Open 9-5.", "Batch 2026-11-09."):
            with self.subTest(text=text): self.assertEqual(policy.check(hike_draft(text)), [])


class M1UndoContentTests(unittest.TestCase):
    def undo(self, before, after, collection="products", field="description"):
        return {"ops": [{"op": "history.revert", "args": {"changeId": "chg-000000000001"}}],
                "records": [{"collection": collection, "key": "p1", "before": {field: before}, "after": {field: after}}]}

    def test_an_undo_that_would_put_back_a_claim_is_refused(self):
        self.assertIn("protected sentences: origin/organic", policy.check(self.undo("Sweet.", "Certified organic. Sweet.")))
        self.assertIn("protected sentences: contact", policy.check(self.undo("Sweet.", "Call 805-555-0101.")))
        self.assertIn("protected field: products.brand", policy.check(self.undo("Old", "New", field="brand")))
        self.assertIn("sign-up is on", policy.check(self.undo(None, None, "events") | {"records": [
            {"collection": "events", "key": "e", "before": {"status": "cancelled", "rsvpEnabled": True},
             "after": {"status": "scheduled", "rsvpEnabled": True}}]}))

    def test_an_undo_of_more_than_ten_records_is_refused(self):
        draft = self.undo("old", "new")
        draft["records"] *= 11
        self.assertIn("more than 10 records", policy.check(draft))

    def test_an_undo_with_plain_content_still_passes(self):
        self.assertEqual(policy.check(self.undo("Sweet and creamy.", "Rich and creamy.")), [])
        self.assertEqual(policy.check(self.undo("Pure organic. Sweet.", "Pure organic. Rich.")), [])


class L4HedgedWordsTests(unittest.TestCase):
    DRAFT = maker_draft("Harbor Lane makes curd.", place="Fillmore, CA")

    def test_a_town_only_in_a_question_or_a_hedge_is_not_his_words(self):
        for said in ("add lemon curd from Harbor Lane. Fillmore? no idea",
                     "add lemon curd from Harbor Lane, fillmore-ish",
                     "add lemon curd from Harbor Lane in Fillmore maybe",
                     "add lemon curd from Harbor Lane, Fillmore, not sure",
                     "add lemon curd from Harbor Lane in Fillmore I think, no idea really",
                     "add lemon curd from Harbor Lane. Is it from Fillmore?",
                     "add lemon curd from Harbor Lane, perhaps Fillmore"):
            with self.subTest(said=said):
                self.assertEqual(policy.unsaid(self.DRAFT, said), ["Fillmore"])

    def test_a_brand_only_in_a_question_is_not_his_words(self):
        self.assertEqual(policy.unsaid(self.DRAFT, "add lemon curd, is it Harbor Lane? from Fillmore"), ["Harbor Lane"])

    def test_a_plain_mention_is_still_his_words(self):
        for said in ("add lemon curd from Harbor Lane in Fillmore",
                     "add lemon curd from Harbor Lane. Fillmore? yes, Fillmore.",
                     "Is this right? Add lemon curd from Harbor Lane in Fillmore.",
                     "Can you add lemon curd from Harbor Lane in Fillmore?",
                     "please add lemon curd from Harbor Lane in Fillmore?",
                     "add lemon curd from Harbor Lane in Fillmore, maybe 6 jars\nit is from Fillmore"):
            with self.subTest(said=said):
                self.assertEqual(policy.unsaid(self.DRAFT, said), [])


class StoreContactOwnedByItsOperationTests(unittest.TestCase):
    """The phone and the street address are refused for their protected operation; only those two fields skip the sentence screen."""
    PHONE = "8055550123"

    def draft(self, op, **after):
        return {"ops": [{"op": op, "args": {}}], "records": [{"collection": "store", "key": "store", "before": {}, "after": after}]}

    def test_the_phone_value_is_not_screened_again_beside_its_own_protected_operation(self):
        self.assertEqual(policy.check(self.draft("store.set_phone", phone=self.PHONE)), ["protected operation: store.set_phone"])
        self.assertEqual(policy.check(self.draft("store.set_address", streetAddress="1023 Example Street")),
                         ["protected operation: store.set_address"])

    def test_a_phone_number_in_any_other_store_field_is_still_a_contact_sentence(self):
        for field in ("intro", "headline", "story", "town", "notice"):
            with self.subTest(field=field):
                self.assertIn("protected sentences: contact", policy.check(self.draft("store.set_phone", **{field: f"Call {self.PHONE}"})))

    def test_the_other_operations_field_is_not_skipped(self):
        self.assertIn("protected sentences: contact", policy.check(self.draft("store.set_address", phone=self.PHONE)))

    def test_without_the_protected_operation_the_phone_value_is_a_contact_sentence(self):
        self.assertIn("protected sentences: contact", policy.check(self.draft("store.confirm_selection", phone=self.PHONE)))
        undo = {"ops": [{"op": "history.revert", "args": {"changeId": "chg-000000000001"}}],
                "records": [{"collection": "store", "key": "store", "before": {}, "after": {"phone": self.PHONE}}]}
        self.assertIn("protected sentences: contact", policy.check(undo))


if __name__ == "__main__":
    unittest.main()
