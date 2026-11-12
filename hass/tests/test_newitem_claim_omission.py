"""Canonical claim omission keeps original nonclaim text and draft disclosure aligned."""
import unittest

from hass import newitem
from hass.tests import test_newitem as fixtures


class ClaimOmissionTests(unittest.TestCase):
    def test_unicode_claim_spans_are_removed(self):
        spellings = ("ｏｒｇａｎｉｃ", "órganíc", "o\u0301rganic\u0301", "organic",
                     "pesticide‐free", "pesticide‑free", "gluten–free", "gluten—free",
                     "pesticide-free", "pesticide   free", "pesticide\t\nfree",
                     "organic ｏｒｇａｎｉｃ órganíc", "ｒａｗ honey organic", "raw ｏｒｇａｎｉｃ honey", "lowers cholesterol")
        for spelling in spellings:
            with self.subTest(spelling=spelling):
                self.assertTrue(newitem.claim_terms(spelling))
                name = newitem.without_claims(f"{spelling} honey", "honey")
                self.assertEqual(newitem.claim_terms(name), [])
                self.assertEqual(name, "Honey")

    def test_nonclaim_name_text_is_preserved(self):
        for name, expected in (
            ("Élodie ｏｒｇａｎｉｃ Crème HONEY", "Élodie Crème HONEY"),
            ("Élodie o\u0301rganic\u0301 Cre\u0300me honey", "Élodie Cre\u0300me honey"),
            ("organically locale honey", "organically locale honey"),
            ("  Élodie Cre\u0300me HONEY  ", "  Élodie Cre\u0300me HONEY  "),
            ("organic, honey -", "Honey"),
        ):
            with self.subTest(name=name):
                self.assertEqual(newitem.without_claims(name, "honey"), expected)

    def test_clean_kind_and_empty_fallbacks_unchanged(self):
        for name, kind, expected in (("ｏｒｇａｎｉｃ", "honey", "Honey"),
                                     ("raw honey", "honey", "Honey"),
                                     ("organic", None, None), (None, "honey", None),
                                     ("", "honey", ""), ("Bee honey", "honey", "Bee honey")):
            with self.subTest(name=name, kind=kind):
                self.assertEqual(newitem.without_claims(name, kind), expected)

    def draft(self, message, **kwargs):
        return newitem.draft(message, fixtures.PHOTO, content=fixtures.CONTENT,
                             spec=fixtures.SPEC, renderer=fixtures.FAKE, **kwargs)

    def test_draft_claim_omission_matches_left_off(self):
        for spelling, canonical in (("organic", "organic"), ("ｏｒｇａｎｉｃ", "organic"),
                                    ("pesticide‑free", "pesticide-free"), ("gluten–free", "gluten-free")):
            message = f"got in {spelling} honey from Cal Poly, jar"
            facts = {"name": f"Cal Poly {spelling} honey", "kind": "honey",
                     "maker": "Cal Poly", "container": "jar"}
            for reader in (facts, None):
                with self.subTest(spelling=spelling, structured=reader is not None):
                    result = self.draft(message, facts=reader)
                    self.assertEqual(result["status"], "draft")
                    product = next(op["args"] for op in result["ops"] if op["op"] == "product.add")
                    for field in ("name", "imageAlt", "description"):
                        self.assertEqual(newitem.claim_terms(product[field]), [], (field, product[field]))
                    self.assertEqual(product["name"], "Cal Poly honey")
                    self.assertEqual(product["imageAlt"], "Cal Poly honey in a jar")
                    self.assertEqual(result["description"]["source"], "template")
                    self.assertEqual([x["value"] for x in result["left_off"] if x["what"] == "claim"], [canonical])
                    self.assertTrue(all(x["why"] for x in result["left_off"]))

    def test_negated_and_unstated_claim_behavior_unchanged(self):
        for message in ("got in honey from Cal Poly, jar", "got in honey from Cal Poly, jar. It is not ｏｒｇａｎｉｃ."):
            with self.subTest(message=message):
                result = self.draft(message, facts={"name": "Cal Poly ｏｒｇａｎｉｃ honey", "kind": "honey",
                                                    "maker": "Cal Poly", "container": "jar"})
                self.assertIn("name", result["dropped"])
                self.assertEqual(result["status"], "draft")
                self.assertEqual([x for x in result["left_off"] if x["what"] == "claim"], [])
                product = next(op["args"] for op in result["ops"] if op["op"] == "product.add")
                for field in ("name", "imageAlt", "description"):
                    self.assertEqual(newitem.claim_terms(product[field]), [])
