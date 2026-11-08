"""RF1730-1: invisible model-supplied names are refused in plain words.

Name cleaning still preserves visible characters, while owner replies no longer expose op/field names.
Run: python3 -m unittest hass.tests.test_interpret_check_names -v
"""

import unicodedata
import unittest

from hass import interpret_check
from hass.ops import load_registry

REGISTRY = load_registry()
AGAIN = interpret_check.AGAIN
CANT_DO = "I can't do that kind of change yet. You can ask Graham."
MISSING = "I can't find that change any more. Could you tell me the change again?"
INVISIBLE = "\u200b\u200c\u200d\u2060\ufeff\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200e\u200f\u2028\u2029"


def ask(ops, revises=None, pending=()):
    return interpret_check.check({"ops": ops, "revises": revises}, REGISTRY, pending)


def call(op, **args):
    return {"op": op, "args": args}


class NameTests(unittest.TestCase):
    def question(self, out):
        self.assertEqual(set(out), {"question"}, out)
        text = out["question"]
        hidden = [c for c in text if unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"}]
        self.assertEqual(hidden, [], repr(text))
        return text

    def test_direction_override_in_op_is_removed(self):
        self.assertEqual(self.question(ask([call("store\u202e.set")])), CANT_DO)
        self.assertEqual(interpret_check._clean("store\u202e.set"), "store.set")

    def test_zero_width_and_isolates_in_field_are_removed(self):
        field = "co\u200blo\u200dur\ufeff\u2066\u2067\u2068\u2069"
        text = self.question(ask([call("product.edit", id="p1", **{field: "green"})]))
        self.assertEqual(text, CANT_DO)
        self.assertEqual(interpret_check._clean(field), "colour")
        # A hidden mark cannot make an unknown field look like a real one and slip through.
        self.assertEqual(self.question(ask([call("product.edit", **{"id\u200b": "p1"})])), CANT_DO)

    def test_line_and_paragraph_separators_are_removed(self):
        text = self.question(ask([call("hike\u2028.no\u2029pe")]))
        self.assertEqual(text, CANT_DO)
        self.assertEqual(interpret_check._clean("hike\u2028.no\u2029pe"), "hike.nope")
        self.assertEqual(text.splitlines(), [text])

    def test_name_of_only_invisible_characters_is_unnamed(self):
        self.assertEqual(self.question(ask([call(INVISIBLE)])), CANT_DO)
        self.assertEqual(self.question(ask([call("product.edit", id="p1", **{INVISIBLE: "v"})])), CANT_DO)
        self.assertEqual(self.question(ask([call("store.set_hours", hours=["9-5"])], revises="\u200b\u2028")), MISSING)
        self.assertEqual(interpret_check._clean(INVISIBLE), "(unnamed)")

    def test_accents_non_latin_and_emoji_are_kept(self):
        for name in ("café", "日本", "avocado🥑", "naïve.Ünïcode"):
            with self.subTest(name=name):
                self.assertEqual(self.question(ask([call(name)])), CANT_DO)
                self.assertEqual(interpret_check._clean(name), name)
        self.assertEqual(self.question(ask([call("product.edit", id="p1", **{"prénom日本🥑": "v"})])), CANT_DO)
        self.assertEqual(interpret_check._clean("prénom日本🥑"), "prénom日本🥑")

    def test_cut_counts_visible_characters_only(self):
        name = "".join(c + "\u200b\u202e" for c in "abcdefghij" * 6)
        text = self.question(ask([call(name)]))
        self.assertEqual(text, CANT_DO)
        self.assertEqual(interpret_check._clean(name), ("abcdefghij" * 4)[:37] + "...")
        exact = "\u2066" + "k" * 40 + "\ufeff\u2028"
        self.assertEqual(self.question(ask([call(exact)])), CANT_DO)
        self.assertEqual(interpret_check._clean(exact), "k" * 40)

    def test_revises_code_with_zero_width_is_shown_clean(self):
        ops = [call("store.set_hours", hours=["9-5"])]
        self.assertEqual(ask(ops, "be\u200bef", {"beef"}), {"question": MISSING})

    def test_valid_result_is_returned_unchanged(self):
        result = {"ops": [call("hike.update", id="h1", capacity=10, rsvpEnabled=True)], "revises": "beef"}
        self.assertIs(interpret_check.check(result, REGISTRY, {"beef"}), result)
        self.assertEqual(result["ops"][0]["args"], {"id": "h1", "capacity": 10, "rsvpEnabled": True})
        value = {"ops": [call("product.edit", id="p1", name="Ha\u200bss")], "revises": None}
        self.assertIs(interpret_check.check(value, REGISTRY, ()), value)
        self.assertEqual(value["ops"][0]["args"]["name"], "Ha\u200bss")


if __name__ == "__main__":
    unittest.main()
