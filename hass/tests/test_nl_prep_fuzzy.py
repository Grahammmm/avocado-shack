"""RF2311-11: a tied best spelling match must not become a unique product hint. Synthetic catalogs only; no model, no socket.
Run: python3 -B -m unittest hass.tests.test_nl_prep_fuzzy -q
"""

import difflib
import json
import unittest
from datetime import date
from types import SimpleNamespace

from hass import nl_prep

MONDAY = date(2026, 11, 9)


def product(n, name, category="fruit"):
    return {"id": f"synthetic-{n}", "name": name, "category": category, "producerKey": None, "status": "active", "description": ""}


def catalog(*names, makers=None):
    return SimpleNamespace(products=[product(i + 1, n) for i, n in enumerate(names)], makers=makers or {}, community={}, store={})


def index(*names, **kw):
    return nl_prep._Index(catalog(*names, **kw))


def ratio(word, token):
    return difflib.SequenceMatcher(None, word, token).ratio()


class FuzzyTieTests(unittest.TestCase):
    def test_equal_best_spelling_words_do_not_resolve_a_product(self):
        self.assertEqual(ratio("peach", "peich"), 0.8)
        self.assertEqual(ratio("perch", "peich"), 0.8)
        for names in (("Peach", "Perch"), ("Perch", "Peach")):
            self.assertEqual(index(*names).canon("peich"), (None, False))
            hint = nl_prep.make_hinter(catalog(*names))("peich tomorrow at 9am", MONDAY)
            self.assertNotIn("products", hint)
            self.assertEqual(hint["times"], [{"said": "9am", "time": "09:00"}])
        three = index("Peach", "Perch", "Pewch")
        self.assertEqual(three.canon("peich"), (None, False))

    def test_unique_best_spelling_survives_two_above_cutoff_candidates(self):
        self.assertEqual(index("Peach").canon("peich"), ("peach", True))
        idx = index("Peach", "Peachy")
        self.assertGreater(ratio("peach", "peachz"), ratio("peachy", "peachz"))
        self.assertGreaterEqual(ratio("peachy", "peachz"), nl_prep.FUZZY_CUTOFF)
        self.assertEqual(idx.canon("peachz"), ("peach", True))
        self.assertEqual(idx.canon("zzzzzz"), (None, False))

    def test_exact_name_and_unique_prefix_are_preserved(self):
        idx = index("Peich", "Peach", "Perch", "Lemonade")
        self.assertEqual(idx.canon("peich"), ("peich", False))
        self.assertEqual(idx.canon("lemon"), ("lemonade", True))

    def test_tie_between_maker_words_is_also_omitted(self):
        idx = nl_prep._Index(SimpleNamespace(products=[], makers={"a": {"name": "Peach"}, "b": {"name": "Perch"}}, community={}, store={}))
        self.assertEqual(idx.canon("peich"), (None, False))

    def test_unresolved_token_keeps_other_spans_and_hints(self):
        hinter = nl_prep.make_hinter(catalog("Peach", "Perch", "Lemons"))
        first = hinter("peich and lemons tomorrow at 9am", MONDAY)
        self.assertEqual([p["said"] for p in first["products"]], ["lemons"])
        self.assertEqual(first["products"][0]["is"], {"id": "synthetic-3", "name": "Lemons"})
        self.assertEqual(first["dates"][0]["date"], "2026-11-10")
        self.assertEqual(first["times"], [{"said": "9am", "time": "09:00"}])
        self.assertEqual(first, hinter("peich and lemons tomorrow at 9am", MONDAY))

    def test_request_never_sends_lexical_tie_as_unique_product(self):
        hint = nl_prep.make_hinter(catalog("Peach", "Perch"))("peich tomorrow at 9am", MONDAY)
        blob = json.dumps(hint)
        self.assertNotIn("Perch", blob)
        self.assertNotIn("Peach", blob)
        self.assertEqual(hint["dates"][0]["date"], "2026-11-10")


if __name__ == "__main__":
    unittest.main()
