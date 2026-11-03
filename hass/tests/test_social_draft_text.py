"""RF0910-6 tests: blank or line-break/control-character free text in social_draft.

Run: python3 -m unittest hass.tests.test_social_draft_text -v
"""
import unittest

from hass import social_draft
from hass.tests import test_social_draft as base
from hass.tests import test_social_draft_inputs as inputs
from hass.tests.test_social_draft import MAKER, product
from hass.tests.test_social_draft_inputs import HAPPY_CAPTION, INCOMPLETE, NO_MAKER_CAPTION

BAD_LINES = ("   ", "\t", "Loaf\nBread", "Loaf\rBread", "Loaf\u2028", "Loaf\u2029Bread", "Lo\x00af", "Lo\x1baf", "Loaf\u200b")


class SocialDraftTextTests(unittest.TestCase):
    # Borrow the helpers without subclassing, so the borrowed tests do not run twice.
    setUp, load, build = base.SocialDraftTests.setUp, base.SocialDraftTests.load, base.SocialDraftTests.build
    tree, run_cli = inputs.SocialDraftInputTests.tree, inputs.SocialDraftInputTests.run_cli

    def maker_build(self, **maker):
        content = self.load(product("p1"))
        content.makers["Brian's"] = {**MAKER, **maker}
        return social_draft.build(content, "p1", self.site)

    def test_blank_or_multiline_or_control_name_is_incomplete(self):
        for name in BAD_LINES:
            with self.subTest(name=name):
                self.assertEqual(self.build("p1", product("p1", name=name)), INCOMPLETE)
                self.assertEqual(self.run_cli(), (1, INCOMPLETE))

    def test_blank_or_control_description_is_incomplete(self):
        for description in ("  ", "\n", " \n ", "A crust\x07 worth tearing.", "A crust\r\nworth.", "A crust\u2028worth."):
            with self.subTest(description=description):
                self.assertEqual(self.build("p1", product("p1", description=description)), INCOMPLETE)
                self.assertEqual(self.run_cli(), (1, INCOMPLETE))

    def test_description_with_one_plain_newline_drafts(self):
        out = self.build("p1", product("p1", description="A crust worth tearing.\nBaked daily."))
        self.assertEqual(out["caption"], HAPPY_CAPTION.replace("tearing.\n", "tearing.\nBaked daily.\n", 1))
        self.assertEqual(self.run_cli(), (0, out))

    def test_blank_or_control_maker_name_or_place_is_no_maker(self):
        cases = [{"name": v} for v in ("  ", "Brian's\nBakery", "Bri\x00an's")]
        cases += [{"place": v} for v in ("", "\t", "Paso\nRobles", "Paso\u2028Robles", "Paso\x7fRobles")]
        for maker in cases:
            with self.subTest(maker=maker):
                out = self.maker_build(**maker)
                self.assertEqual((out["draft"], out["caption"]), (True, NO_MAKER_CAPTION))

    def test_clean_maker_still_gives_from_line(self):
        out = self.maker_build(name="Brian's Bakery", place="Paso Robles")
        self.assertEqual(out["caption"], HAPPY_CAPTION.replace("Brian's in Atascadero, California", "Brian's Bakery in Paso Robles"))

    def test_multiline_or_control_image_alt_falls_back_to_name(self):
        for alt in ("A loaf\nof bread", "A loaf\x1b[31m", "A loaf\rof bread", "A loaf\u2029", "  "):
            with self.subTest(alt=alt):
                out = self.build("p1", product("p1", imageAlt=alt))
                self.assertEqual((out["alt"], out["caption"]), ("Sourdough", HAPPY_CAPTION))
        self.assertEqual(self.build("p1", product("p1", imageAlt="A round loaf"))["alt"], "A round loaf")

    def test_incomplete_comes_before_tags_and_after_earlier_refusals(self):
        self.assertEqual(self.build("p1", product("p1", name="   ", description="Fresh #bread")), INCOMPLETE)
        self.assertEqual(self.build("p1", product("p1", name="Loaf\nBread", description="@baker")), INCOMPLETE)
        self.assertEqual(self.build("p1", product("p1", name="   ", status="held"))["reason"], "not on the site")
        self.assertEqual(self.build("p2", product("p1", name="   "))["reason"], "no such product")
        # A clean name with a tagged description is still the tag refusal; a bad maker is dropped before the tag check.
        self.assertEqual(self.build("p1", product("p1", description="Fresh #bread"))["reason"],
                         "free text has a hashtag or account name")
        self.assertTrue(self.maker_build(name="@brian\nx")["draft"])

    def test_happy_path_byte_identical(self):
        self.load(product("p1"))
        self.assertEqual(self.run_cli(), (0, {"draft": True, "image": "assets/products/p1.webp", "alt": "Sourdough",
                                              "caption": HAPPY_CAPTION}))


if __name__ == "__main__":
    unittest.main()
