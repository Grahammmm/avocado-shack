"""RF0640-11 tests: oldest-first description omission orders product-id suffixes without int() conversion.

A photo-product-<digits> suffix longer than Python's integer-string digit limit must still order by exact numeric value.
Run: python3 -B -m unittest hass.tests.test_interpreter_prompt_numeric_suffix -v
"""

import copy
import json
import unittest

from hass.interpreter_prompt import MAX_PRODUCTS, OMITTED, PROMPT_MAX_BYTES, PRODUCT_ID_RE, _omission_order, build
from hass.tests.test_interpreter_prompt import TEST_REGISTRY, tiny_content

PREFIX = "photo-product-"
HEADER = "Products (id | name | brand | status | description):"
LONG_A, LONG_B, LONG_C = "1" + "0" * 4999, "1" + "0" * 4998 + "1", "9" * 5000  # each > the 4300-digit default limit
DEC = json.JSONDecoder()


def _product(pid, description: object = "describe " * 3):
    return {"id": pid, "name": "n", "status": "active", "description": description}


def _size(prompt):
    return len(prompt.encode("utf-8"))


def _rows(prompt):
    """{id: description column} for the product section."""
    lines = prompt.splitlines()
    out = {}
    for line in lines[lines.index(HEADER) + 1:]:
        if not line or line.endswith("):"):
            break
        pid, end = DEC.raw_decode(line)
        out[pid] = line.rsplit(" | ", 1)[1]
    return out


def _order(products):
    rows = sorted(products, key=lambda p: str(p.get("id", "")))[:MAX_PRODUCTS]
    return [rows[i].get("id") for i in _omission_order(products)]


class LongSuffixTest(unittest.TestCase):
    def test_fitting_prompt_with_5000_digit_suffix_builds(self):
        pid, text = PREFIX + "9" * 5000, "Whole description, kept as is."
        prompt = build(TEST_REGISTRY, tiny_content([_product(pid, text), _product(PREFIX + "1", "short one here")]))
        self.assertLess(_size(prompt), PROMPT_MAX_BYTES)
        self.assertEqual(_rows(prompt)[pid], json.dumps(text))
        self.assertIn(json.dumps(pid), prompt)

    def test_oversized_prompt_omits_by_exact_long_suffix_magnitude(self):
        ids = [PREFIX + "0" * 6000 + "7", PREFIX + "5", PREFIX + "40", PREFIX + LONG_A, PREFIX + LONG_B, PREFIX + LONG_C]
        oldest_first = [PREFIX + "5", PREFIX + "0" * 6000 + "7", PREFIX + "40", PREFIX + LONG_A, PREFIX + LONG_B,
                        PREFIX + LONG_C]
        empty = _size(build(TEST_REGISTRY, tiny_content([_product(i, "") for i in ids])))
        size = (PROMPT_MAX_BYTES - empty - 21) // 3  # each omission saves size - 7 bytes; three must go
        products = [_product(i, "x" * size) for i in ids]
        prompt = build(TEST_REGISTRY, tiny_content(products))
        self.assertLessEqual(_size(prompt), PROMPT_MAX_BYTES)
        rows = _rows(prompt)
        self.assertEqual({i for i, d in rows.items() if d == OMITTED}, set(oldest_first[:3]))
        for pid in oldest_first[3:]:
            self.assertEqual(rows[pid], json.dumps("x" * size))  # kept whole, never cut

    def test_long_suffix_overflow_before_any_shortcut(self):
        """The long id sorts after short ones even when only the short ones need to go."""
        self.assertEqual(_order([_product(PREFIX + LONG_C), _product(PREFIX + "12"), _product(PREFIX + LONG_A)]),
                         [PREFIX + "12", PREFIX + LONG_A, PREFIX + LONG_C])


class TieBreakTest(unittest.TestCase):
    def test_equal_values_keep_original_id_tiebreaker(self):
        zeros = "0" * 6000
        ids = [PREFIX + "7", PREFIX + "007", PREFIX + zeros + "7", PREFIX + "\u0667", PREFIX + "\uff17",
               PREFIX + "0", PREFIX + "000", PREFIX + zeros, PREFIX + "\u0660", PREFIX + "8"]
        for p in ([_product(i) for i in ids], [_product(i) for i in reversed(ids)]):
            order = _order(p)
            zero_group, seven_group = order[:4], order[4:9]
            self.assertEqual(set(zero_group), {PREFIX + "0", PREFIX + "000", PREFIX + zeros, PREFIX + "\u0660"})
            self.assertEqual(zero_group, sorted(zero_group))
            self.assertEqual(set(seven_group), {PREFIX + "7", PREFIX + "007", PREFIX + zeros + "7", PREFIX + "\u0667",
                                                PREFIX + "\uff17"})
            self.assertEqual(seven_group, sorted(seven_group))
            self.assertEqual(order[9], PREFIX + "8")
        prompt = build(TEST_REGISTRY, tiny_content([_product(i) for i in ids]))
        self.assertEqual(set(_rows(prompt)), set(ids))  # original id text unchanged in the prompt

    def test_short_value_order_matches_independent_integer_oracle(self):
        digits = ["0", "00", "1", "01", "9", "10", "010", "99", "100", "\u0663", "\u0661\u0660", "\uff12\uff10", "7",
                  "007", "\u0967\u0968", "12345678901234567890", "012345678901234567890", "12345678901234567891"]
        bad = [5, "", "photo-product-", "photo-product-x", "photo-product-1x", "Photo-product-3",
               " photo-product-4", "photo-product-4\n", "other-9", "a", "zz"]
        products = [_product(PREFIX + d) for d in digits] + [_product(b) for b in bad]
        products.append({"name": "no id", "description": "describe " * 3})

        def oracle(p):
            pid = p.get("id")
            m = PRODUCT_ID_RE.fullmatch(pid) if isinstance(pid, str) else None
            return (0, 0, str(pid)) if m is None else (1, int(m.group(1)), pid)  # old int-based key, short values

        self.assertEqual(_order(products), [p.get("id") for p in sorted(products, key=oracle)])

    def test_row_order_input_immutability_and_repeatability(self):
        ids = [PREFIX + "3", PREFIX + LONG_C, PREFIX + "20", "zz-other", PREFIX + LONG_A]
        products = [_product(i, "describe " * 400) for i in ids]
        pristine = copy.deepcopy(products)
        first = build(TEST_REGISTRY, tiny_content(products))
        self.assertEqual(products, pristine)
        again = build(TEST_REGISTRY, tiny_content(list(reversed(products))))
        self.assertEqual(first, again)
        self.assertEqual(list(_rows(first)), sorted(ids))  # table rows stay lexical, not age ordered
        self.assertEqual(_order(products), ["zz-other", PREFIX + "3", PREFIX + "20", PREFIX + LONG_A, PREFIX + LONG_C])

    def test_unshrinkable_descriptions_and_row_cap_keep_old_behaviour(self):
        products = [_product(PREFIX + "1", ""), _product(PREFIX + "2", "tiny"), _product(PREFIX + "3", 7),
                    _product(PREFIX + LONG_A, "describe " * 3)]
        self.assertEqual(_order(products), [PREFIX + LONG_A])
        many = [_product(f"photo-product-{n:04d}") for n in range(MAX_PRODUCTS + 1)]
        order = _order(many)
        self.assertEqual(len(order), MAX_PRODUCTS)  # the row past the display cap is not an omission candidate
        self.assertNotIn(max(p["id"] for p in many), order)


class CoreOverflowTest(unittest.TestCase):
    def test_core_overflow_still_has_exact_refusal(self):
        products = [_product(PREFIX + LONG_C), _product(PREFIX + "1", "describe " * 50),
                    {"id": "zz", "name": "n" * (PROMPT_MAX_BYTES + 1), "status": "x", "description": ""}]
        with self.assertRaises(ValueError) as caught:
            build(TEST_REGISTRY, tiny_content(products))
        self.assertEqual(str(caught.exception), "prompt too large")


if __name__ == "__main__":
    unittest.main()
