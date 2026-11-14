"""HASS-CLOVER-1: the SKU scheme: readable, deterministic, collision-checked, stable. Fixtures and constructed items only.
Run: python3 -B -m unittest hass.tests.test_clover_sku
"""
import itertools
import random
import unittest

from hass.clover import mapper as m
from hass.clover import sku
from hass.tests.test_clover_mapper import item, items


class SchemeTests(unittest.TestCase):
    def test_the_owner_example(self):
        self.assertEqual(sku.generate_sku("Sunshine olive oil", "pantry", []), "AS-PAN-SUNSHINE-OLIVE-OIL-01")

    def test_readable_slugs(self):
        for name, slug in (("Sunshine olive oil", "SUNSHINE-OLIVE-OIL"), ("The Best of Honey", "BEST-HONEY"), ("Linn\u2019s Blueberry Preserves", "LINNS-BLUEBERRY"), ("Linn's Blueberry Preserves", "LINNS-BLUEBERRY"),
                           ("Jalape\u00f1o jam", "JALAPENO-JAM"), ("  eggs,  dozen ", "EGGS-DOZEN"), ("Strawberries 2 lb", "STRAWBERRIES-2-LB"),
                           ("A", "A"), ("the", "THE"), ("Supercalifragilisticexpialidocious", "SUPERCALIFRAGILIST"), ("Olive-oil/extra   virgin", "OLIVE-OIL-EXTRA")):
            with self.subTest(name=name):
                self.assertEqual(sku.slug(name), slug)

    def test_a_name_with_no_letters_or_digits_is_refused(self):
        for name in ("", "   ", "!!!", "\u2603\u2603"):
            with self.subTest(name=name), self.assertRaises(m.MapError):
                sku.slug(name)

    def test_category_codes_cover_the_site_categories_and_unknown_is_general(self):
        self.assertEqual(set(sku.CATEGORY_CODES), set(m.CATEGORIES))
        self.assertEqual(len(set(sku.CATEGORY_CODES.values())), len(m.CATEGORIES))           # no two categories share a code
        self.assertTrue(all(len(c) == 3 and c.isalpha() and c.isupper() for c in sku.CATEGORY_CODES.values()))
        self.assertEqual(sku.base("Thing", "pantry"), "AS-PAN-THING")
        for cat in (None, "", "gadgets", "PANTRY"):
            self.assertEqual(sku.base("Thing", cat), "AS-GEN-THING")

    def test_shape_and_length_for_hostile_names(self):
        rng = random.Random(7)
        alphabet = "abc XYZ-_/.'\u2019\u00e9\u00f1 0123456789&!"
        for _ in range(300):
            name = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 100)))
            try:
                got = sku.generate_sku(name, rng.choice((*m.CATEGORIES, None)), [])
            except m.MapError:
                continue
            self.assertTrue(sku.is_hass_sku(got), got)
            self.assertLessEqual(len(got), sku.SKU_MAX)

    def test_is_hass_sku(self):
        self.assertTrue(sku.is_hass_sku("AS-PAN-SUNSHINE-OLIVE-OIL-01"))
        for bad in ("EGG12", "as-pan-x-01", "AS-PAN-X-1", "AS-PAN-X-001", "AS-PA-X-01", "AS-PAN--01", "AS-PAN-X-01 ", "", None, "AS-PAN-" + "X" * 30 + "-01"):
            self.assertFalse(sku.is_hass_sku(bad), bad)


class UniquenessTests(unittest.TestCase):
    def test_the_same_inputs_give_the_same_sku(self):
        till = list(items().values())
        self.assertEqual(sku.generate_sku("Sourdough loaf", "bread", till), sku.generate_sku("Sourdough loaf", "bread", list(reversed(till))))

    def test_a_taken_number_moves_on_to_the_next_free_one(self):
        taken = [item(id="A", name="Other one", sku="AS-PAN-SUNSHINE-OLIVE-OIL-01")]
        self.assertEqual(sku.generate_sku("Sunshine olive oil", "pantry", taken), "AS-PAN-SUNSHINE-OLIVE-OIL-02")
        taken.append(item(id="B", name="Another", sku="AS-PAN-SUNSHINE-OLIVE-OIL-02"))
        self.assertEqual(sku.generate_sku("Sunshine olive oil", "pantry", taken), "AS-PAN-SUNSHINE-OLIVE-OIL-03")

    def test_the_fixture_till_forces_the_second_number(self):
        till = list(items().values())                                       # the till already holds ...-01 for Sunshine olive oil
        with self.assertRaises(sku.DuplicateItem) as ctx:
            sku.generate_sku("sunshine OLIVE oil", "pantry", till)           # same exact name: a duplicate, not a new SKU
        self.assertEqual(ctx.exception.item.id, "FAKEITEM00001")
        self.assertEqual(sku.generate_sku("Sunshine olive oil 1 litre", "pantry", till), "AS-PAN-SUNSHINE-OLIVE-OIL-02")   # same short form, other name

    def test_collisions_are_case_insensitive_and_count_barcodes_and_hidden_items(self):
        for taken in (item(id="A", name="x", sku="as-pan-thing-01"), item(id="B", name="y", code="AS-PAN-THING-01"),
                      item(id="C", name="z", sku="AS-PAN-THING-01", hidden=True)):
            with self.subTest(taken=taken.id):
                self.assertEqual(sku.generate_sku("Thing", "pantry", [taken]), "AS-PAN-THING-02")

    def test_a_hidden_twin_is_not_a_duplicate(self):
        hidden = item(id="H", name="Thing", sku="AS-PAN-THING-01", hidden=True)
        self.assertEqual(sku.generate_sku("Thing", "pantry", [hidden]), "AS-PAN-THING-02")

    def test_many_new_items_never_collide(self):
        till, made = [], set()
        names = [f"Item {w} {n}" for w in ("alpha", "beta") for n in range(60)] + ["Sunshine olive oil"] * 1
        for i, name in enumerate(names):
            got = sku.generate_sku(name, "pantry", till)
            self.assertNotIn(got.casefold(), made)
            made.add(got.casefold())
            till.append(item(id=f"N{i}", name=name, sku=got))
        self.assertEqual(len(made), len(names))

    def test_same_short_form_different_names_get_a_run_of_numbers(self):
        till, got = [], []
        for n in range(1, 6):
            new = sku.generate_sku(f"Sunshine olive oil {'x' * n}", "pantry", till)    # all cut to the same 18 characters
            got.append(new)
            till.append(item(id=f"I{n}", name=f"Sunshine olive oil {'x' * n}", sku=new))
        self.assertEqual([g.rsplit("-", 1)[1] for g in got], ["01", "02", "03", "04", "05"])
        self.assertEqual(len({g.rsplit("-", 1)[0] for g in got}), 1)

    def test_running_out_of_numbers_is_reported(self):
        till = [item(id=f"I{n}", name=f"Other {n}", sku=f"AS-PAN-THING-{n:02d}") for n in range(1, 100)]
        with self.assertRaises(sku.SkuExhausted):
            sku.generate_sku("Thing", "pantry", till)

    def test_a_sku_is_stable_for_an_item_that_already_has_one(self):
        # Generating for the till again never changes what is already there: the function only reads the till.
        till = list(items().values())
        before = [(i.id, i.sku) for i in till]
        sku.generate_sku("Brand new item", "pantry", till)
        self.assertEqual(before, [(i.id, i.sku) for i in till])
        oil = items()["FAKEITEM00001"]
        renamed = item(id=oil.id, name="Sunshine extra virgin olive oil", sku=oil.sku)
        self.assertEqual(sku.used_values([renamed]), {oil.sku.casefold()})          # a rename keeps the SKU taken

    def test_all_shapes_of_a_name_pair_exhaustively_small(self):
        words = ("olive", "oil", "the", "sunshine")
        names = {" ".join(p) for r in (1, 2, 3) for p in itertools.permutations(words, r)}
        till, seen = [], set()
        for n, name in enumerate(sorted(names)):
            got = sku.generate_sku(name, "pantry", till)
            self.assertNotIn(got, seen)
            seen.add(got)
            till.append(item(id=f"X{n}", name=name, sku=got))


if __name__ == "__main__":
    unittest.main()
