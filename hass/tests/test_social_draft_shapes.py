"""RF0620-5 tests: social_draft refuses a misshaped products list; imageAlt is used only as plain untagged text.

Run: python3 -m unittest hass.tests.test_social_draft_shapes -v
"""
import contextlib
import io
import json
import unittest

from hass import social_draft
from hass.tests import test_social_draft_inputs as inputs
from hass.tests.test_social_draft import product

CANNOT = inputs.CANNOT
HAPPY_CAPTION = inputs.HAPPY_CAPTION
T = inputs.SocialDraftInputTests


class SocialDraftShapeTests(unittest.TestCase):
    # Borrow the helpers without subclassing, so the borrowed tests do not run twice.
    setUp, load, build, tree, run_cli, rewrite = T.setUp, T.load, T.build, T.tree, T.run_cli, T.rewrite

    def set_products(self, products):
        self.load(product("p1"))  # photo, makers, community and store in place
        self.rewrite("products", json.dumps({"schemaVersion": 1, "products": products}))

    def test_products_not_a_list_is_cannot_read_content(self):
        for products in ({}, {"p1": product("p1")}, "p1", 5, None):
            with self.subTest(products=products):
                self.set_products(products)
                self.assertEqual(self.run_cli(), CANNOT)  # run_cli: no traceback on stderr, nothing written

    def test_a_non_object_entry_refuses_even_for_a_good_product(self):
        for bad in ("oops", 5, None, ["p1"]):
            with self.subTest(bad=bad):
                self.set_products([product("p1"), bad])
                self.assertEqual(self.run_cli("p1"), CANNOT)
                self.set_products([bad, product("p1")])
                self.assertEqual(self.run_cli("p1"), CANNOT)
                self.assertEqual(self.run_cli("nope"), CANNOT)  # shape check runs before "no such product"

    def test_shape_check_runs_before_every_other_refusal(self):
        content = self.load(product("p1", status="held", description=None))
        content.products.append("oops")
        self.assertEqual(social_draft.build(content, "p1", self.site), CANNOT[1])
        content.products = {"p1": product("p1")}
        self.assertEqual(social_draft.build(content, "p1", self.site), CANNOT[1])

    def test_non_text_or_empty_image_alt_falls_back_to_name(self):
        for alt in (5, ["a"], {"t": "a"}, True, None, "", "  ", "\n\t"):
            with self.subTest(alt=alt):
                out = self.build("p1", product("p1", imageAlt=alt))
                self.assertEqual((out["draft"], out["alt"], out["caption"]), (True, "Sourdough", HAPPY_CAPTION))
                self.assertEqual(self.run_cli(), (0, out))

    def test_tagged_image_alt_falls_back_to_name_not_a_refusal(self):
        for alt in ("Fresh loaf #bread", "Photo by @shop", "#1 loaf", "by @_shop", "Loaf #pan"):
            with self.subTest(alt=alt):
                out = self.build("p1", product("p1", imageAlt=alt))
                self.assertEqual(out, {"draft": True, "image": "assets/products/p1.webp", "alt": "Sourdough",
                                       "caption": HAPPY_CAPTION})

    def test_plain_image_alt_is_used_as_is(self):
        for alt in ("A sourdough loaf on a board", "Loaf # 2, 50% rye", "Email us @ the shop"):  # no tag: # or @ then a space
            with self.subTest(alt=alt):
                out = self.build("p1", product("p1", imageAlt=alt))
                self.assertEqual((out["alt"], out["caption"]), (alt, HAPPY_CAPTION))

    def test_absent_image_alt_is_the_name(self):
        out = self.build("p1", product("p1"))
        self.assertNotIn("imageAlt", product("p1"))
        self.assertEqual(out["alt"], "Sourdough")

    def test_happy_path_json_byte_identical(self):
        self.load(product("p1"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(social_draft.main(["p1"], self.root / "content", self.site), 0)
        expected = {"draft": True, "image": "assets/products/p1.webp", "alt": "Sourdough", "caption": HAPPY_CAPTION}
        self.assertEqual(out.getvalue(), json.dumps(expected, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
