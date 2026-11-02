"""RF0140-4 tests: social_draft refuses a #hashtag or @account in product/maker free text; nothing is rewritten.

Run: python3 -m unittest hass.tests.test_social_draft_tags -v
"""
import unittest

from hass import social_draft
from hass.tests import test_social_draft as base
from hass.tests.test_social_draft import MAKER, product

TAGGED = {"draft": False, "reason": "free text has a hashtag or account name"}
FROM = "From Brian's in Atascadero, California."


class SocialDraftTagTests(unittest.TestCase):
    # Borrow the base helpers without subclassing, so the base tests do not run twice.
    setUp, load, build = base.SocialDraftTests.setUp, base.SocialDraftTests.load, base.SocialDraftTests.build

    def with_maker(self, maker, **changes):
        content = self.load(product("p1", **changes))
        content.makers["Brian's"] = maker
        return social_draft.build(content, "p1", self.site)

    def test_tag_or_account_in_product_text_is_refused(self):
        for changes in ({"description": "Fresh Hass #organic"}, {"description": "#1 grade"},
                        {"name": "@brians_farm avocados"}, {"description": "Ask @brians_farm"},
                        {"name": "Hass #_x"}, {"description": "Line one\n#local"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.build("p1", product("p1", **changes)), TAGGED)

    def test_tag_in_maker_name_or_place_is_refused(self):
        for maker in ({**MAKER, "place": "Morro Bay #slo"}, {**MAKER, "name": "@brians"}):
            with self.subTest(maker=maker):
                self.assertEqual(self.with_maker(maker), TAGGED)

    def test_absent_or_malformed_maker_text_is_not_checked(self):
        tagged_maker = {**MAKER, "place": "Morro Bay #slo"}
        out = self.with_maker(tagged_maker, producerKey=None)  # maker absent: only product text is checked
        self.assertEqual((out["draft"], out["caption"]), (True, "Sourdough\nA crust worth tearing.\n\n#AvocadoShack #Bread"))
        out = self.with_maker({"name": "#brians", "place": None})  # malformed maker is no maker
        self.assertEqual((out["draft"], out["caption"]), (True, "Sourdough\nA crust worth tearing.\n\n#AvocadoShack #Bread"))
        self.assertEqual(self.with_maker(tagged_maker, producerKey=None, description="Fresh #organic"), TAGGED)

    def test_hash_or_at_not_followed_by_a_word_character_is_kept_verbatim(self):
        for text in ("Avocados at $3 # each", "email us at shop (at) example", "C# notes", "100% Hass",
                     "Ask at the counter @", "Full-width \uff03tag and \uff20shop"):  # full-width signs are not # or @ to the check
            with self.subTest(text=text):
                out = self.build("p1", product("p1", description=text))
                self.assertEqual(out, {"draft": True, "image": "assets/products/p1.webp", "alt": "Sourdough",
                                       "caption": f"Sourdough\n{text}\n{FROM}\n\n#AvocadoShack #Bread"})
        out = self.with_maker({**MAKER, "place": "Morro Bay # 2"}, name="C# loaf")
        self.assertEqual(out["caption"], "C# loaf\nA crust worth tearing.\nFrom Brian's in Morro Bay # 2.\n\n#AvocadoShack #Bread")

    def test_non_ascii_word_after_hash_is_refused(self):
        for text in ("Fresh #\u00f1ame", "Hola @Jos\u00e9", "#\u00e9t\u00e9"):
            with self.subTest(text=text):
                self.assertEqual(self.build("p1", product("p1", description=text)), TAGGED)

    def test_fixed_tags_still_added_and_imagealt_not_checked(self):
        for category, tag in social_draft.CATEGORY_TAGS.items():
            with self.subTest(category=category):
                out = self.build("p1", product("p1", category=category, imageAlt="Photo by @someone #nofilter"))
                self.assertTrue(out["draft"])
                self.assertEqual(out["alt"], "Photo by @someone #nofilter")
                self.assertTrue(out["caption"].endswith(f"{FROM}\n\n#AvocadoShack {tag}"))

    def test_earlier_refusals_keep_their_order(self):
        tagged = {"description": "Fresh #organic"}
        self.assertEqual(self.build("p2", product("p1", **tagged))["reason"], "no such product")
        for status in ("held", "hidden"):
            self.assertEqual(self.build("p1", product("p1", status=status, **tagged))["reason"], "not on the site")
        content = self.load(product("p1", **tagged))
        (self.site / "assets/products/p1.webp").unlink()
        self.assertEqual(social_draft.build(content, "p1", self.site)["reason"], "no photo on the site")
        self.assertEqual(self.build("p1", product("p1", name="#x", description=None))["reason"], "product record incomplete")

    def test_tagged_text_that_is_also_too_long_is_refused_as_tagged(self):
        self.assertEqual(self.build("p1", product("p1", description="#a " + "x" * 2300)), TAGGED)


if __name__ == "__main__":
    unittest.main()
