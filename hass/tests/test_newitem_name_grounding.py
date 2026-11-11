"""New-item name tokens need whole-word evidence in the owner's message, not a substring of another word."""
import copy
import unittest

from hass import newitem
from hass.tests import test_newitem as fixtures

BASE = "We have honey in a jar on the pantry shelf. Its appearance is amber."


class NameGroundingTests(unittest.TestCase):
    def ground(self, name, message=BASE):
        facts = {"name": name, "kind": "honey", "container": "jar"}
        return newitem.ground(facts, message, fixtures.CONTENT)

    def draft(self, message, facts):
        return newitem.draft(message, fixtures.PHOTO, content=fixtures.CONTENT, spec=fixtures.SPEC,
                             renderer=fixtures.FAKE, facts=facts)

    def test_inner_word_does_not_ground_product_name(self):
        for name in ("Pear honey", "Honey pear", "ppear honey", "ear honey", "pea honey"):
            with self.subTest(name=name):
                kept, dropped = self.ground(name, "We have honey in a jar. Its appearance is amber, spearmint too.")
                self.assertIsNone(kept["name"])
                self.assertEqual(dropped.count("name"), 1)
                self.assertEqual(kept["kind"], "honey")
        kept, dropped = self.ground("Honey", BASE)
        self.assertEqual(kept["name"], "Honey")
        self.assertNotIn("name", dropped)

    def test_whole_word_any_occurrence_is_required(self):
        for message in ("Pear honey, jar.", "honey\npear\njar", "(pear) honey in a jar", "Appearance is nice. Pear honey jar"):
            with self.subTest(message=message):
                kept, dropped = self.ground("Pear honey", message)
                self.assertEqual(kept["name"], "Pear honey")
                self.assertNotIn("name", dropped)

    def test_folded_owner_words_keep_existing_compatibility(self):
        for message in ("ＰＥＡＲ honey in a jar", "PEAR HONEY jar", "Pèar honey jar"):
            with self.subTest(message=message):
                kept, _ = self.ground("Pear honey" if "è" not in message else "Pèar honey", message)
                self.assertTrue(kept["name"])
        kept, dropped = self.ground("P.ar honey", "Pear honey in a jar")
        self.assertIsNone(kept["name"])

    def test_drop_name_once_preserves_other_facts_and_inputs(self):
        facts = {"name": "Pear honey", "kind": "honey", "container": "jar"}
        before = copy.deepcopy(facts)
        kept, dropped = newitem.ground(facts, BASE, fixtures.CONTENT)
        self.assertEqual(facts, before)
        self.assertEqual(dropped.count("name"), 1)
        self.assertEqual((kept["kind"], kept["container"], kept["shelf"]), ("honey", "jar", "pantry"))

    def test_draft_falls_back_to_supported_kind_without_invented_word(self):
        result = self.draft(BASE, {"name": "Pear honey", "kind": "honey", "container": "jar", "shelf": "pantry"})
        self.assertIn("name", result["dropped"])
        product = next(op["args"] for op in result["ops"] if op["op"] == "product.add")
        self.assertEqual(product["name"], "Honey")
        self.assertEqual(product["imageAlt"], "Honey in a jar")
        self.assertNotIn("pear", repr(result["ops"]).lower())

    def test_supported_structured_and_regex_names_keep_output(self):
        result = self.draft(BASE.replace("honey", "pear honey"), {"name": "Pear honey", "kind": "honey", "container": "jar"})
        self.assertNotIn("name", result["dropped"])
        product = next(op["args"] for op in result["ops"] if op["op"] == "product.add")
        self.assertEqual(product["name"], "Pear honey")
        self.assertEqual(product["imageAlt"], "Pear honey in a jar")
        regular = self.draft("got in honey from Cal Poly, jar", None)
        self.assertEqual(next(op["args"] for op in regular["ops"] if op["op"] == "product.add")["name"], "Cal Poly honey")


if __name__ == "__main__":
    unittest.main()
