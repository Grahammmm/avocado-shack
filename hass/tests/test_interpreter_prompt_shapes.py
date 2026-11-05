"""RF1100-7 (H05) tests: build() never crashes on a damaged catalog shape; damaged rows are skipped. No model call.

Run: python3 -m unittest hass.tests.test_interpreter_prompt_shapes -v
"""

import unittest

from hass.interpreter_prompt import build
from hass.tests.test_interpreter_prompt import FIXTURE, TEST_REGISTRY, tiny_content

PRODUCTS = "Products (id | name | brand | status | description):"
MAKERS = "Makers (key | name):"
GOOD = {"id": "zz-honey", "name": "Wildflower honey", "status": "active"}
GOOD2 = {"id": "aa-avocado", "name": "Hass avocado", "status": "sold-out"}


def _section(prompt, header):
    lines = prompt.splitlines()
    out = []
    for line in lines[lines.index(header) + 1:]:
        if not line or line.endswith("):"):
            break
        out.append(line)
    return out


def _prompt(products=None, makers=None, *, raw_products=False, raw_makers=False):
    content = tiny_content(products, makers)
    if raw_products:
        content.products = products
    if raw_makers:
        content.makers = makers
    return build(TEST_REGISTRY, content)


class ProductShapeTest(unittest.TestCase):
    def test_non_object_products_are_skipped_in_id_order(self):
        prompt = _prompt([GOOD, "x", None, 3, [GOOD], GOOD2])
        self.assertEqual(_section(prompt, PRODUCTS), ['"aa-avocado" | "Hass avocado" | "" | "sold-out" | ""',
                                                      '"zz-honey" | "Wildflower honey" | "" | "active" | ""'])

    def test_only_damaged_products_gives_none(self):
        self.assertEqual(_section(_prompt(["x", None, 3]), PRODUCTS), ["(none)"])

    def test_non_list_products_give_none(self):
        for products in ({"a": dict(GOOD)}, None, "zz-honey", 7, GOOD):
            with self.subTest(products=products):
                prompt = _prompt(products, raw_products=True)
                self.assertEqual(_section(prompt, PRODUCTS), ["(none)"])
                self.assertIn('"Stepladder" | "Stepladder Ranch"', _section(prompt, MAKERS))


class MakerShapeTest(unittest.TestCase):
    def test_non_object_maker_keeps_key_with_empty_name(self):
        prompt = _prompt(makers={"m1": "x", "m2": [1], "m3": {"name": "Ojai Farm"}, "m4": None, "m5": 0})
        self.assertEqual(_section(prompt, MAKERS), ['"m1" | ""', '"m2" | ""', '"m3" | "Ojai Farm"',
                                                    '"m4" | ""', '"m5" | ""'])

    def test_non_dict_makers_give_none(self):
        for makers in (["m1"], None, "m1", 3, [{"name": "Ojai Farm"}]):
            with self.subTest(makers=makers):
                prompt = _prompt(makers=makers, raw_makers=True)
                self.assertEqual(_section(prompt, MAKERS), ["(none)"])
                self.assertEqual(len(_section(prompt, PRODUCTS)), 3)


class WellFormedTest(unittest.TestCase):
    def test_well_formed_prompt_equals_main_golden(self):
        self.assertEqual(build(TEST_REGISTRY, tiny_content()), FIXTURE.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
