"""parse_facts: decoder-excessive JSON nesting falls back like any other invalid JSON."""
import contextlib
import io
import json
import unittest
from unittest import mock

from hass import newitem

EMPTY = {k: None for k in newitem.FACT_KEYS}
DEPTH = 10000


class ParseFactsTests(unittest.TestCase):
    def test_decoder_recursion_uses_exact_empty_facts(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(newitem.json, "loads", side_effect=RecursionError("CANARY-7731")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            got = newitem.parse_facts('{"name": "Honey"}')
        self.assertEqual(got, EMPTY)
        self.assertEqual(list(got), list(newitem.FACT_KEYS))
        self.assertEqual(out.getvalue() + err.getvalue(), "")

    def test_real_deep_unused_member_refuses_whole_response(self):
        raw = '{"name": "Honey", "extra": ' + "[" * DEPTH + "]" * DEPTH + "}"
        with self.assertRaises(RecursionError):
            json.loads(raw)  # the real decoder does fail on this input
        self.assertEqual(newitem.parse_facts(raw), EMPTY)

    def test_deep_top_level_array_falls_back(self):
        self.assertEqual(newitem.parse_facts("[" * DEPTH + "]" * DEPTH), EMPTY)
        for raw in ("[1]", "null", '"Honey"', "42"):
            self.assertEqual(newitem.parse_facts(raw), EMPTY, raw)

    def test_valid_selected_fields_preserved(self):
        doc = {k: f"  v{i} é  " for i, k in enumerate(newitem.FACT_KEYS)}
        doc[newitem.FACT_KEYS[0]] = "Miel de forêt"
        doc[newitem.FACT_KEYS[1]] = "   "
        doc[newitem.FACT_KEYS[2]] = 7
        doc["unknown"] = [[1]]
        raw = json.dumps(doc)
        want = {k: (f"v{i} é" if isinstance(doc[k], str) else None) for i, k in enumerate(newitem.FACT_KEYS)}
        want[newitem.FACT_KEYS[0]] = "Miel de forêt"
        want[newitem.FACT_KEYS[1]] = None
        want[newitem.FACT_KEYS[2]] = None
        got = newitem.parse_facts(raw)
        self.assertEqual(got, want)
        self.assertEqual(list(got), list(newitem.FACT_KEYS))
        self.assertNotIn("unknown", got)

    def test_ordinary_invalid_inputs_still_fall_back(self):
        for raw in ('{"name": "Hon', "", "not json", None, 5, b"\xff"):
            self.assertEqual(newitem.parse_facts(raw), EMPTY, repr(raw))
        with mock.patch.object(newitem.json, "loads", side_effect=KeyError("bug")):
            with self.assertRaises(KeyError):
                newitem.parse_facts("{}")


if __name__ == "__main__":
    unittest.main()
