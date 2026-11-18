"""F2/F14: separate a typed price from the owner's product words."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hass.skills.item_intake import caption_answers
from hass.tests import test_item_add_dispatch as base
from hass.tests.test_browser_freshness import catalog_of
from hass.tests.test_label_reader import reader as label_reader, recorded
from hass.tests.test_photo_detail_read import GLUE
from hass.tests.test_product_new import badges

VOICE = ("okay so um hey hass we got the uh kiwis in today from etto farms "
         "they're like three bucks a basket comma sell them at three dollars period "
         "they look really good um yeah")


class PricedCaption(unittest.TestCase):
    def test_mixed_caption_keeps_owner_words_and_price_basis(self):
        for caption, public, facts in (
            ("add persimmins fuyu $3.50 a lb", "add persimmins fuyu", {"price": "3.50", "sold_by": "pound"}),
            ("ADD BLOOD ORANGES $2.50 LB", "ADD BLOOD ORANGES", {"price": "2.50", "sold_by": "pound"}),
            ("new item hachiya persimmons $3.5O/lb", "new item hachiya persimmons", {"price": "3.50", "sold_by": "pound"}),
            ("add satsumas $4 per lb per pound", "add satsumas", {"price": "4.00", "sold_by": "pound"}),
            ("add fuyu persimmons $3500/lb", "add fuyu persimmons", {"price": "3500.00", "sold_by": "pound"}),
            ("add organic local strawberries best ever $6 a basket", "add strawberries", {"price": "6.00", "price_unit": "basket"}),
            (VOICE, "okay so um hey hass we got the uh kiwis in today from etto farms; they look really good um yeah",
             {"price": "3.00", "price_unit": "basket"}),
            ("add blueberries 8 lb in stock", "add blueberries", {"qty": 8, "qty_unit": "lb"}),
            ("add blueberries cost $5", "add blueberries", {"cost": "5.00"}),
        ):
            with self.subTest(caption=caption):
                self.assertEqual(caption_answers(caption), (public, facts))

    def test_copy_edits_and_ambiguous_prices_do_not_become_sale_prices(self):
        for text in ("add: costs $500", "rename it to $20", "add plums $1,250", "add plums $3.5OO",
                     "add plums -$2 each", "add plums $3 or $5 each", "add plums maybe $3 each"):
            with self.subTest(text=text):
                self.assertEqual(caption_answers(text), (text, {}))


class PricedTextConversation(unittest.TestCase):
    def chat(self):
        chat = base.Chat([base.JAR], settings={"itemIntake": True})
        self.addCleanup(chat.close)
        return chat

    @staticmethod
    def illustration(prompt, out, timeout):
        from PIL import Image
        Image.new("RGB", (800, 800), "#eab04a").save(out, "JPEG")
        return {"ok": True, "code": "ok"}

    @staticmethod
    def commit_count(chat):
        return int(base.testkit._git(chat.kit.wt, "rev-list", "--count", "HEAD"))

    def test_openers_prepare_one_unpublished_listing_from_the_retained_words(self):
        for text, source, name, price in (
            ("add persimmins fuyu $3.50 a lb", "add persimmins fuyu", "Persimmins fuyu", "3.50 per lb"),
            ("ADD BLOOD ORANGES $2.50 LB", "ADD BLOOD ORANGES", "Blood oranges", "2.50 per lb"),
            ("add tayberries $6", "add tayberries", "Tayberries", "6.00"),
            # A basket price must not become public just because the basis cannot be displayed.
            ("add organic local tayberries best ever $6 a basket", "add tayberries", "Tayberries", "6.00 a basket"),
            (VOICE.replace("kiwis", "tayberries"),
             "okay so um hey hass we got the uh tayberries in today from etto farms; they look really good um yeah",
             "Tayberries", "3.00 a basket"),
        ):
            with self.subTest(text=text):
                chat = self.chat()
                before = self.commit_count(chat)
                reader = Mock()
                chat.script(source, base.reply(name=name, shelf="fruit"))
                with patch.object(chat.conv, "answer_reader", reader), patch.object(
                    chat.conv, "polish_transport", SimpleNamespace(generate=self.illustration)
                ):
                    disposition, (reply,) = chat.say(text)
                self.assertEqual(disposition, "proposed", reply)
                draft, = chat.drafts()
                listing, = [op["args"] for op in json.loads(draft["ops_json"]) if op["op"] == "product.add"]
                self.assertEqual(listing["name"], name)
                self.assertNotIn("organic", json.dumps(listing).lower())
                self.assertNotIn("best ever", json.dumps(listing).lower())
                self.assertIn("yes " + draft["code"], reply)
                self.assertEqual(self.commit_count(chat), before)
                reader.fields.assert_not_called()
                if price.endswith(" a basket"):
                    self.assertNotIn("sellingPrice", listing)
                    self.assert_basket_preview(chat, draft, name, price, reply)
                else:
                    self.assertEqual(listing["sellingPrice"], price)
                self.doCleanups()

    def assert_basket_preview(self, chat, draft, name, price, reply):
        before = self.commit_count(chat)
        amount = price.removesuffix(" a basket")
        self.assertIn(f'Price: ${price} (not on the website: it can show a price per lb or each. '
                      f'Reply "each" to show ${amount} each.)', reply.splitlines())
        self.assertEqual(chat.live()["slots"]["intake"]["price_unit"], "basket")
        self.assertNotIn("product-price", self.render_card(chat, draft, name))
        expected = None
        if amount == "6.00":
            # The unit reply must edit this draft, not start a new one or approve it.
            disposition, (reply,) = chat.say("each")
            self.assertEqual(disposition, "proposed", reply)
            revised, = chat.drafts()
            self.assertEqual(revised["code"], draft["code"])
            edited, = [op["args"] for op in json.loads(revised["ops_json"]) if op["op"] == "product.add"]
            expected = "6.00 each"
            self.assertEqual(edited["sellingPrice"], expected)
            self.assertIn("Price: $6.00 each", reply.splitlines())
            self.assertIn('<p class="product-meta product-price">$6.00 each</p>', self.render_card(chat, revised, name))
            self.assertNotIn("price_unit", chat.live()["slots"]["intake"])
            self.assertEqual(self.commit_count(chat), before)
        chat.say("yes " + draft["code"])
        self.assertEqual(self.commit_count(chat), before + 1)
        products = json.loads((chat.kit.wt / "hass/content/products.json").read_text())["products"]
        saved, = [p for p in products if p["name"] == name]
        if expected is None:
            self.assertNotIn("sellingPrice", saved)  # approving as-is must not supply an unstated public basis
        else:
            self.assertEqual(saved["sellingPrice"], expected)

    def render_card(self, chat, draft, name):
        rendered = chat.conv.editor.render_draft(draft["change_id"])
        self.assertEqual(rendered["result"], "ok", rendered)
        public, = [p for p in catalog_of(rendered["files"])[0] if p["name"] == name]
        html, = badges([{"card": True, "product": public, "now": "2026-11-17T20:00:00Z"}])
        return html

    def test_basket_price_cannot_bypass_existing_strawberry_twin_refusal(self):
        # A separate basket intake path could bypass the seed catalog's name/brand check.
        chat = self.chat()
        chat.script("add strawberries", base.reply(name="Strawberries", shelf="fruit"))
        with patch.object(chat.conv, "polish_transport", SimpleNamespace(generate=self.illustration)):
            disposition, (reply,) = chat.say("add strawberries $6 a basket")
        self.assertEqual(disposition, "not-drafted", reply)
        self.assertEqual(reply, "That's already how it is, so nothing changed.")
        self.assertEqual(chat.drafts(), [])

    def test_price_without_product_words_prompts_for_name_and_never_drafts(self):
        chat = self.chat()
        _, (reply,) = chat.say("add this $3.50 a lb")
        self.assertIn("name", reply)
        request = chat.live()
        assert request is not None
        self.assertNotIn("name", request["slots"])
        self.assertEqual(request["slots"]["intake"]["price"], "3.50")
        self.assertEqual(chat.drafts(), [])
        self.assertEqual(chat.asked, [])

    def test_finance_reader_runs_only_without_a_deterministic_price_cost_or_count(self):
        chat = self.chat()
        def fields(words):
            self.assertFalse(chat.conv.db.in_transaction)
            return {"price_cents": 275, "cost_cents": None, "quantity": None}

        reader = Mock()
        reader.fields.side_effect = fields
        unparsed = "retail is two seventy-five"
        with patch.object(chat.conv, "answer_reader", reader):
            for text in ("cost $0", "have 0 each", "sell for $2"):
                chat.say(text)
            reader.fields.assert_not_called()
            chat.say(unparsed)
        reader.fields.assert_called_once_with(unparsed)
        request = chat.live()
        assert request is not None
        self.assertEqual(request["slots"]["intake"]["price"], "2.75")
        self.assertEqual(chat.asked, [])

    def test_priced_photo_while_a_draft_waits_keeps_the_label_and_preview_path(self):
        chat = self.chat()
        chat.conv.labels, labels = label_reader(recorded({k: v for k, v in GLUE.items() if k != "brand"}))
        disposition, said = chat.say("bought 100 at $1, sell for $2", base.JAR)
        self.assertEqual(disposition, "proposed", said)
        waiting, = chat.drafts()
        self.assertEqual(waiting["state"], "proposed")

        text = "raspberry jam $7"
        labels.answer = recorded({"name": "Raspberry Jam", "brand": "Hillside Kitchen", "category": "pantry"})
        finance = Mock()
        finance.fields.return_value = {"price_cents": 700, "cost_cents": None, "quantity": None}
        with patch.object(chat.conv, "answer_reader", finance):
            disposition, said = chat.say(text, base.BAG)
        self.assertEqual(disposition, "proposed", said)  # not a claim question from the general interpreter
        self.assertIn("$7.00", "\n".join(said))
        finance.fields.assert_called_once_with(text)
        self.assertEqual(len(labels.calls), 2)
        self.assertEqual(chat.asked, [])
