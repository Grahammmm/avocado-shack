"""Render the same generated draft data the private previewer passes to shop.js."""
import unittest
from copy import deepcopy

from hass import editor, interpret_check, live_policy
from hass.ops import load_registry
from hass.tests import test_intake_simple as intake
from hass.tests.test_browser_freshness import catalog_of, CATALOG
from hass.tests.test_catalog_ops import CatalogRepo, NEW, _req
from hass.tests.test_product_new import badges


class DraftCardPrice(unittest.TestCase):
    def test_typed_price_only_in_generated_card(self):
        # The real label reader must ignore even an OCR response that offers a price.
        for text, expected in (("sell for $2, cost $73.19, quantity 63427", "2.00"),
                               ("$3.50/lb", "3.50 per lb"), ("$0/each", "0.00 each")):
            with self.subTest(owner_text=text):
                chat = intake.base.Chat([intake.base.JAR], None, {"itemIntake": True})
                try:
                    chat.conv.labels, _ = intake.reader(intake.recorded({**intake.DETAILS, "price": "91.87"}))
                    disposition, reply = chat.say("", intake.base.JAR)
                    self.assertEqual(disposition, "question", reply)
                    request = chat.live()
                    assert request is not None
                    self.assertNotIn("price", request["slots"]["intake"])
                    disposition, reply = chat.say(text)
                    self.assertEqual(disposition, "proposed", reply)
                    if "cost" in text:
                        self.assertIn("cost $73.19, quantity 63427", reply[0])
                    cid = chat.drafts()[0]["change_id"]
                    draft = chat.conv.editor.show(cid)["draft"]
                    self.assertEqual(live_policy.check(draft), [])
                    if expected == "3.50 per lb":
                        tampered = deepcopy(draft)
                        added = next(r["after"] for r in tampered["records"] if r["collection"] == "products")
                        added["sellingPrice"] = "3.50 each"
                        self.assertIn("protected field: products.sellingPrice", live_policy.check(tampered))
                    product = next(r["after"] for r in draft["records"] if r["collection"] == "products")
                    self.assertTrue({"cost", "qty", "quantity"}.isdisjoint(product))
                    rendered = chat.conv.editor.render_draft(cid)
                    self.assertEqual(rendered["result"], "ok", rendered)
                    files = rendered["files"]
                    public = next(p for p in catalog_of(files)[0] if p["id"] == product["id"])
                    html, = badges([{"card": True, "product": public, "now": "2026-11-17T20:00:00Z"}])
                    self.assertIn(f'<p class="product-meta product-price">${expected}</p>', html)
                    for private in (b"73.19", b"63427", b"91.87"):
                        self.assertFalse(any(private in generated for generated in files.values()), private)
                    for key in (b'"cost"', b'"qty"', b'"quantity"'):
                        self.assertNotIn(key, files[CATALOG])
                finally:
                    chat.close()

    def test_unpriced_draft_has_no_price_element(self):
        repo = CatalogRepo()
        self.addCleanup(repo.cleanup)
        draft = repo.prepare(_req(("product.add", NEW)))
        self.assertEqual(draft["result"], "ok", draft)
        out = editor.render_draft(draft["draft"]["change_id"], state=str(repo.state))
        self.assertEqual(out["result"], "ok", out)
        public = next(p for p in catalog_of(out["files"])[0] if p["name"] == NEW["name"])
        self.assertNotIn("sellingPrice", public)
        html, = badges([{"card": True, "product": public, "now": "2026-11-17T20:00:00Z"}])
        self.assertNotIn("product-price", html)

    def test_legacy_interpreter_cannot_supply_a_selling_price(self):
        self.assertIn("question", interpret_check.check({"ops": [{"op": "product.add", "args": {
            "sellingPrice": "2.00"}}], "revises": None}, load_registry(), ()))
