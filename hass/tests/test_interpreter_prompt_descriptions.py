"""AV2152-06 (H05) tests: product descriptions in the interpreter prompt, whole or <omitted>, oldest first. No model call.

Run: python3 -B -m unittest hass.tests.test_interpreter_prompt_descriptions -v
"""

import json
import unittest
from datetime import datetime, timezone

from hass.interpreter_local import LocalInterpreter
from hass.interpreter_prompt import OMITTED, PROMPT_MAX_BYTES, build
from hass.tests.test_interpreter_prompt import TEST_REGISTRY, tiny_content

HEADER = "Products (id | name | brand | status | description):"


def _section(prompt, header):
    lines = prompt.splitlines()
    out = []
    for line in lines[lines.index(header) + 1:]:
        if not line or line.endswith("):"):
            break
        out.append(line)
    return out


def _product(pid, description: object = "", name="n"):
    return {"id": pid, "name": name, "status": "active", "description": description}


def _size(prompt):
    return len(prompt.encode("utf-8"))


def _filler(products, makers=None):
    """Descriptions that exactly fill ``products`` ids so the full prompt is a known size."""
    return _size(build(TEST_REGISTRY, tiny_content(products, makers)))


class WholeDescriptionTest(unittest.TestCase):
    def test_whole_description_and_partial_edit_rule(self):
        tail = "Sourdough, baked daily. " * 20 + "END-OF-TEXT"
        prompt = build(TEST_REGISTRY, tiny_content([_product("photo-product-001", tail, "Sourdough")]))
        self.assertEqual(_section(prompt, HEADER), [json.dumps("photo-product-001") + ' | "Sourdough" | "" | "active" | '
                                                    + json.dumps(tail)])
        self.assertIn("product.edit description replaces the whole text", prompt)
        self.assertIn(f"never send {OMITTED} as an argument", prompt)
        sent = []

        def transport(url, body, headers, timeout):
            sent.append(json.loads(body)["messages"][0]["content"])
            return 200, json.dumps({"done": True, "message": {"content": '{"unsupported": "x"}'}}).encode()

        LocalInterpreter("http://127.0.0.1:11434", "m", prompt, transport=transport,
                         clock=lambda: datetime(2026, 11, 5, tzinfo=timezone.utc)).interpret("add great on toast", [])
        self.assertEqual(sent, [prompt])  # the whole system text, not a prefix

    def test_missing_empty_none_malformed_and_literal_marker(self):
        products = [{"id": "a", "name": "n", "status": "s"}, _product("b", ""), _product("c", None),
                    _product("d", {"k": "v"}), _product("e", 7), _product("f", OMITTED)]
        rows = _section(build(TEST_REGISTRY, tiny_content(products)), HEADER)
        ends = [row.split(" | ")[-1] for row in rows]
        self.assertEqual(ends, ['""', '""', '""', OMITTED, OMITTED, json.dumps(OMITTED)])  # literal text stays quoted

    def test_json_escapes_one_line(self):
        text = 'say "hi" | a/b\nline\u0085\u2028\u2029end'
        row = _section(build(TEST_REGISTRY, tiny_content([_product("p", text)])), HEADER)
        self.assertEqual(row, ['"p" | "n" | "" | "active" | "say \\"hi\\" | a/b\\nline\\u0085\\u2028\\u2029end"'])


class BudgetTest(unittest.TestCase):
    def test_json_escapes_and_utf8_exact_boundary(self):
        def make(room):  # room = bytes of description text beyond the empty-description prompt; "é" is 2 bytes
            first = "é" * (room // 4) + "x" * (room - 2 * (room // 4))
            return [_product("photo-product-001", first), _product("photo-product-002", "newer text")]

        base = _size(build(TEST_REGISTRY, tiny_content(make(0))))
        room = PROMPT_MAX_BYTES - base
        full = build(TEST_REGISTRY, tiny_content(make(room)))
        self.assertEqual(_size(full), PROMPT_MAX_BYTES)
        self.assertNotIn(OMITTED, "\n".join(_section(full, HEADER)))  # fits exactly: nothing omitted
        rows = _section(build(TEST_REGISTRY, tiny_content(make(room + 1))), HEADER)  # one byte over
        self.assertTrue(rows[0].endswith(" | " + OMITTED))  # the oldest goes, whole
        self.assertTrue(rows[1].endswith(' | "newer text"'))

    def test_oldest_description_omitted_first(self):
        big = "x" * 9000
        ids = ["photo-product-1000", "photo-product-9", "zz-damaged", "photo-product-10", "aa-damaged", "photo-product-1"]
        products = [_product(i, big) for i in ids]  # 6 * 9000 = 54000 + core; add pressure with one more big one
        products.append(_product("photo-product-2000", big))
        rows = [r.split(" | ") for r in _section(build(TEST_REGISTRY, tiny_content(products)), HEADER)]
        state = {json.loads(r[0]): r[-1] == OMITTED for r in rows}
        self.assertTrue(any(state.values()) and not all(state.values()))
        order = ["aa-damaged", "zz-damaged", "photo-product-1", "photo-product-9", "photo-product-10",
                 "photo-product-1000", "photo-product-2000"]
        omitted = [i for i in order if state[i]]
        self.assertEqual(omitted, order[:len(omitted)])  # a prefix of the oldest-first order
        shuffled = build(TEST_REGISTRY, tiny_content(list(reversed(products))))
        self.assertEqual(shuffled, build(TEST_REGISTRY, tiny_content(products)))
        self.assertEqual([json.loads(r[0]) for r in rows], sorted(ids + ["photo-product-2000"]))  # row order unchanged

    def test_equal_suffix_ties_by_exact_id_and_short_values_skipped(self):
        big = "x" * 30000
        products = [_product("photo-product-07", big), _product("photo-product-7", big), _product("photo-product-8", big),
                    _product("tiny", "ab")]
        rows = {json.loads(r.split(" | ")[0]): r.split(" | ")[-1] == OMITTED
                for r in _section(build(TEST_REGISTRY, tiny_content(products)), HEADER)}
        self.assertTrue(rows["photo-product-07"])  # '07' < '7' on the tie
        self.assertFalse(rows["photo-product-8"])
        self.assertFalse(rows["tiny"])  # a 4-byte literal cannot save bytes against the marker

    def test_core_oversize_still_refuses_and_content_unchanged(self):
        products = [{"id": f"p-{i:03d}", "name": "n" * 200, "status": "active", "description": "d" * 50}
                    for i in range(400)]
        before = json.dumps(products)
        with self.assertRaisesRegex(ValueError, r"^prompt too large$"):
            build(TEST_REGISTRY, tiny_content(products))
        self.assertEqual(json.dumps(products), before)

    def test_row_cap_only_budgets_displayed_descriptions(self):
        # 405 ids; the 5 over the cap (p-400..p-404) carry huge text that is not displayed and must not force omissions
        products = [_product(f"photo-product-{i:03d}", "short text here") for i in range(400)]
        products += [_product(f"zz-{i}", "y" * 50000) for i in range(5)]
        prompt = build(TEST_REGISTRY, tiny_content(products))
        self.assertNotIn(OMITTED, "\n".join(_section(prompt, HEADER)))
        self.assertIn("… and 5 more (ask the owner)", prompt)
        self.assertNotIn("zz-0", prompt)

    def test_real_catalog_fits_with_every_description(self):
        from hass.content_model import load_and_validate
        from hass.ops import load_registry
        content = load_and_validate()
        prompt = build(load_registry(), content)
        rows = _section(prompt, HEADER)
        self.assertEqual(len(rows), len(content.products))
        self.assertLessEqual(_size(prompt), PROMPT_MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
