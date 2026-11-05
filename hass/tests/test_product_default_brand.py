"""AV0007-04 tests: product.add takes displayBrand as optional (defaults to the brand, or 'From the market').

Throwaway Git repos (test_catalog_ops.CatalogRepo); no network, no model.
"""

import unittest
from pathlib import Path

from hass import editor
from hass.interpreter_prompt import _op_lines
from hass.ops import load_registry
from hass.tests.test_catalog_ops import NEW, CatalogTestCase, _req

OMIT = {k: v for k, v in NEW.items() if k != "displayBrand"}
DOC = Path(__file__).resolve().parents[2] / "docs" / "hass" / "COMMANDS.md"


class DefaultBrandTests(CatalogTestCase):
    def test_add_omitted_display_brand_uses_brand(self):
        repo = self.repo()
        before = repo.head()
        draft = repo.prepare(_req(("product.add", OMIT)))
        self.assertEqual(draft["result"], "ok", draft)
        self.assertEqual(repo.head(), before)  # nothing written before approval
        repo.apply(draft["draft"])
        added = repo.products()[-1]
        self.assertEqual(list(added), ["id", "name", "brand", "category", "image", "description", "producerKey",
                                       "displayBrand", "status"])
        self.assertEqual((added["brand"], added["displayBrand"]), ("Test Orchard", "Test Orchard"))
        self.assertEqual(repo.catalog()[-1]["displayBrand"], "Test Orchard")

    def test_unknown_producer_gets_market_label(self):
        repo = self.repo()
        repo.run(("product.add", {**OMIT, "brand": "Producer not identified"}))
        self.assertEqual(repo.products()[-1]["displayBrand"], "From the market")
        # near-sentinel is not normalised
        repo.run(("product.add", {**OMIT, "name": "Other quince", "brand": "producer not identified"}))
        self.assertEqual(repo.products()[-1]["displayBrand"], "producer not identified")
        # an explicit label wins, even with the sentinel brand
        repo.run(("product.add", {**OMIT, "name": "Third quince", "brand": "Producer not identified",
                                  "displayBrand": "Test Label"}))
        self.assertEqual(repo.products()[-1]["displayBrand"], "Test Label")

    def test_missing_other_fields_still_asks(self):
        repo = self.repo()
        for field in ("brand", "description", "name"):
            with self.subTest(field=field):
                result = self.assertRejected(repo, "needs-details",
                                             ("product.add", {k: v for k, v in OMIT.items() if k != field}))
                self.assertEqual(result["missing"], [field])

    def test_explicit_invalid_label_never_defaults(self):
        repo = self.repo()
        for bad in (None, "", "   ", 5, True, ["x"], "<b>x</b>", "a\x07b", "x" * 61):
            with self.subTest(bad=bad):
                result = repo.prepare(_req(("product.add", {**OMIT, "displayBrand": bad})))
                self.assertIn(result["result"], ("invalid", "needs-details", "refused"), result)
                self.assertEqual(repo.drafts(), [])
        repo.run(("product.add", {**OMIT, "displayBrand": "x" * 60}))
        self.assertEqual(len(repo.products()[-1]["displayBrand"]), 60)

    def test_edit_brand_only_keeps_label(self):
        repo = self.repo()
        repo.run(("product.add", OMIT))
        pid = repo.products()[-1]["id"]
        repo.run(("product.edit", {"id": pid, "brand": "New Orchard"}))
        self.assertEqual(repo.products()[-1]["displayBrand"], "Test Orchard")
        repo.run(("product.edit", {"id": pid, "displayBrand": "Label"}))
        last = repo.products()[-1]
        self.assertEqual((last["brand"], last["displayBrand"]), ("New Orchard", "Label"))
        self.assertRejected(repo, "needs-details", ("product.edit", {"id": pid}))

    def test_real_prompt_add_optional_edit_unchanged(self):
        lines = {ln.split("(")[0]: ln for ln in _op_lines(load_registry())}
        add, edit = lines["product.add"], lines["product.edit"]
        self.assertIn("displayBrand: text;", add + ";")
        self.assertNotIn("displayBrand: text, required", add)
        self.assertIn("brand: text, required", add)
        self.assertIn("displayBrand: text", edit)
        self.assertNotIn("required", edit.split("displayBrand")[1].split(";")[0])

    def test_commands_default_brand_paragraph(self):
        text = DOC.read_text("utf-8")
        self.assertIn("From the market", text)
        self.assertIn("Add Test Orchard quince, brand Test Orchard", text)
        self.assertNotIn("|", next(ln for ln in text.splitlines() if "Producer not identified" in ln))


if __name__ == "__main__":
    unittest.main()
