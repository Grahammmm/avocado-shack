"""RF0620-5 tests: social_draft refuses a misshaped products list; imageAlt is used only as plain untagged text.

Run: python3 -m unittest hass.tests.test_social_draft_shapes -v
"""
import contextlib
import io
import json
import unittest

from hass import social_draft
from hass.content_model import CATEGORIES
from hass.tests import test_social_draft_inputs as inputs
from hass.tests.test_social_draft import product

CANNOT = inputs.CANNOT
HAPPY_CAPTION = inputs.HAPPY_CAPTION


class SocialDraftShapeTests(unittest.TestCase):
    # Borrow the helpers without subclassing, so the borrowed tests do not run twice.
    setUp, load, build, tree, run_cli, rewrite = inputs.SocialDraftInputTests.setUp, inputs.SocialDraftInputTests.load, inputs.SocialDraftInputTests.build, inputs.SocialDraftInputTests.tree, inputs.SocialDraftInputTests.run_cli, inputs.SocialDraftInputTests.rewrite

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
                self.assertEqual(out, {"draft": True, "illustration": True, "image": "assets/products/p1.webp", "alt": "Sourdough",
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
        expected = {"draft": True, "image": "assets/products/p1.webp", "alt": "Sourdough", "caption": HAPPY_CAPTION, "illustration": True}
        self.assertEqual(out.getvalue(), json.dumps(expected, ensure_ascii=False, indent=2) + "\n")

    # RF2205-12: a container or other non-text category is treated like a null or unknown one (no category tag).
    BAD_CATEGORIES = ([], {}, ["dairy"], {"name": "dairy"}, [["dairy"]], {"a": {"b": 1}})
    OK = {"draft": True, "illustration": True, "image": "assets/products/p1.webp", "alt": "Sourdough"}

    def shack_only(self):
        return HAPPY_CAPTION.replace(" #Bread", "")

    def test_container_category_omits_only_category_tag(self):
        self.assertEqual(self.shack_only(), self.build("p1", product("p1", category=None))["caption"])
        for category in self.BAD_CATEGORIES:
            with self.subTest(category=category):
                p = product("p1", category=category)
                before = json.dumps(p, sort_keys=True)
                self.assertEqual(self.build("p1", p), {**self.OK, "caption": self.shack_only()})
                self.assertEqual(json.dumps(p, sort_keys=True), before)

    def test_container_category_real_main(self):
        for category in self.BAD_CATEGORIES:
            with self.subTest(category=category):
                self.set_products([product("p1", category=category), product("p2", category="dairy", image="assets/products/p1.webp")])
                before = self.tree()
                code, obj = self.run_cli("p1")  # run_cli: one JSON object, empty stderr, nothing written
                self.assertEqual((code, obj), (0, {**self.OK, "caption": self.shack_only()}))
                self.assertEqual(self.tree(), before)  # source and photo bytes unchanged

    def test_category_tag_controls(self):
        for category in ("absent", None, 5, True, 0, "unknown", "#Hash", "@me", "Dairy", ""):
            with self.subTest(category=category):
                p = product("p1")
                if category == "absent": del p["category"]
                else: p["category"] = category
                out = self.build("p1", p)
                self.assertEqual(out["caption"], self.shack_only())
                self.assertEqual([w for w in out["caption"].split() if w.startswith(("#", "@"))], ["#AvocadoShack"])
        for category in CATEGORIES:
            with self.subTest(category=category):
                out = self.build("p1", product("p1", category=category))
                self.assertTrue(out["caption"].endswith(f"#AvocadoShack {social_draft.CATEGORY_TAGS[category]}"))

    def test_bad_category_does_not_bypass_refusals(self):
        cases = ({"status": "held"}, {"status": "hidden"}, {"image": "assets/products/none.webp"}, {"image": None},
                 {"name": ""}, {"description": None}, {"description": "Try #tag"}, {"description": "word " * 600})
        for changes in cases:
            self.set_products([product("p1", category="dairy", **changes)])
            reference = self.run_cli("p1")  # the refusal with a valid category
            self.assertEqual(reference[1]["draft"], False)
            for category in self.BAD_CATEGORIES:
                with self.subTest(category=category, changes=list(changes)):
                    self.set_products([product("p1", category=category, **changes), product("p2", image="assets/products/p1.webp")])
                    self.assertEqual(self.run_cli("p1"), reference)
                    self.assertEqual(self.run_cli("p2")[1]["draft"], True)  # a valid neighbour is unaffected


if __name__ == "__main__":
    unittest.main()
