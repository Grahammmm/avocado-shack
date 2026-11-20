"""RF1240-19 tests: full-width and small-form hashtag/at signs (U+FF03, U+FF20, U+FE5F, U+FE6B) are refused like # and @.

Run: python3 -m unittest hass.tests.test_social_draft_fullwidth -v
"""
import unittest
from pathlib import Path

from hass import social_draft
from hass.tests import test_social_draft as base
from hass.tests import test_social_draft_tags as tags
from hass.tests.test_social_draft import MAKER, product

TAGGED = tags.TAGGED
FROM = tags.FROM
MARKS = ("\uff03", "\uff20", "\ufe5f", "\ufe6b")
# Golden captured from main 0f374c0 (before RF1240-19) for a clean product with an imageAlt.
MAIN_GOLDEN = {"draft": True, "illustration": True, "availability": None, "image": "assets/products/p1.webp", "alt": "A round loaf",
               "caption": "Sourdough\nA crust worth tearing.\nFrom Brian's in Atascadero, California.\n\n#AvocadoShack #Bread"}


class SocialDraftFullWidthTests(unittest.TestCase):
    # Borrow the base helpers without subclassing, so no other TestCase runs twice.
    setUp, load, build = base.SocialDraftTests.setUp, base.SocialDraftTests.load, base.SocialDraftTests.build
    with_maker = tags.SocialDraftTagTests.with_maker

    def test_spec_examples_in_each_free_text_field_are_refused(self):
        self.assertEqual(self.build("p1", product("p1", name="Salt \uff03organic")), TAGGED)
        self.assertEqual(self.build("p1", product("p1", description="Ask \uff20shack")), TAGGED)
        self.assertEqual(self.with_maker({**MAKER, "name": "Farm \ufe5f1"}), TAGGED)
        self.assertEqual(self.with_maker({**MAKER, "place": "Ojai \ufe6bx"}), TAGGED)

    def test_every_mark_before_a_letter_digit_or_underscore_is_refused(self):
        for mark in MARKS:
            for text in (f"{mark}tag", f"Fresh {mark}9", f"Hass {mark}_x", f"Line one\n{mark}local", f"Hola {mark}Jos\u00e9"):
                with self.subTest(mark=hex(ord(mark)), text=text):
                    self.assertEqual(self.build("p1", product("p1", description=text)), TAGGED)

    def test_tagged_imagealt_is_not_used_and_draft_still_built(self):
        for mark in MARKS:
            with self.subTest(mark=hex(ord(mark))):
                out = self.build("p1", product("p1", imageAlt=f"Jar {mark}1"))
                self.assertEqual(out, {**MAIN_GOLDEN, "alt": "Sourdough"})

    def test_mark_before_a_space_or_at_the_end_is_kept_verbatim(self):
        for mark in MARKS:
            for text in (f"Size {mark} 2", f"Box{mark}", f"A {mark}-shaped jar"):
                with self.subTest(mark=hex(ord(mark)), text=text):
                    out = self.build("p1", product("p1", description=text, imageAlt=text))
                    self.assertEqual(out, {"draft": True, "illustration": True, "availability": None, "image": "assets/products/p1.webp", "alt": text,
                                           "caption": f"Sourdough\n{text}\n{FROM}\n\n#AvocadoShack #Bread"})

    def test_ascii_cases_keep_todays_results(self):
        self.assertTrue(self.build("p1", product("p1", description="C# notes"))["draft"])
        self.assertEqual(self.build("p1", product("p1", description="Fresh #tag")), TAGGED)
        self.assertEqual(self.build("p1", product("p1", description="Ask @shack")), TAGGED)

    def test_clean_product_draft_equals_main(self):
        out = self.build("p1", product("p1", imageAlt="A round loaf"))
        self.assertEqual(out, MAIN_GOLDEN)
        self.assertTrue(out["caption"].endswith("\n\n#AvocadoShack #Bread"))

    def test_absent_maker_text_is_not_checked(self):
        out = self.with_maker({**MAKER, "place": "Ojai \ufe6bx"}, producerKey=None)
        self.assertEqual((out["draft"], out["caption"]), (True, "Sourdough\nA crust worth tearing.\n\n#AvocadoShack #Bread"))

    def test_refusal_reason_unchanged_and_source_stays_ascii(self):
        self.assertEqual(TAGGED["reason"], "free text has a hashtag or account name")
        Path(social_draft.__file__).read_text("utf-8").encode("ascii")  # raises if a literal mark is in the source


if __name__ == "__main__":
    unittest.main()
