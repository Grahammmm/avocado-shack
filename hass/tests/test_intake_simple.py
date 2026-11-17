"""Recorded glue read + real Conversation/editor. Synthetic storage photo, no live OCR/till/site."""
import json
import unittest
from datetime import timedelta
from unittest import mock

from hass.skills import item_intake as ii
from hass.tests import test_item_add_dispatch as base
from hass.tests.test_label_reader import reader, recorded
from hass.tests.test_photo_detail_read import GLUE

FINANCE = "bought 100 at $1, sell for $2"
DETAILS = {**GLUE, "features": ["Dries Natural Color", "No Foaming", "Type II Water Resistant"],
           "printed_claims": ["Made in USA", "Incredibly Strong", "For the Toughest Jobs on Planet Earth"]}


class SimpleIntake(unittest.TestCase):
    def chat(self, details=DETAILS):
        chat = base.Chat([base.JAR], None, {"itemIntake": True})
        chat.base_commits = int(base.testkit._git(chat.kit.wt, "rev-list", "--count", "HEAD"))
        chat.conv.labels, transport = reader(recorded(details))
        self.addCleanup(chat.close)
        return chat, transport

    def assert_preview(self, chat, said):
        self.assertEqual(len(said), 1, said)
        for word in ("Here's the listing:", "Wood Glue", "Gorilla", "4 fl. oz. (118 mL)", "Dries Natural Color",
                     "No Foaming", "Type II Water Resistant", "Made in USA", "$2.00", "$1.00", "100"):
            self.assertIn(word, said[0])
        self.assertEqual(chat.live()["state"], "drafted", said)
        self.assertNotIn("?", said[0])
        code = chat.live()["draft_code"]
        self.assertIn("yes " + code, said[0])
        self.assertEqual(chat.commits(), 0)
        return code

    def test_finance_before_with_and_after_photo_then_whats_next_and_question_mark(self):
        for when in ("before", "caption", "after"):
            with self.subTest(when=when):
                chat, transport = self.chat()
                if when == "before": chat.say(FINANCE)
                d, said = chat.say(FINANCE if when == "caption" else "", base.JAR)
                if when == "after":
                    self.assertEqual(chat.live()["asked_slot"], ii.PREFIX + "price", said)
                    self.assertEqual(sum(s.count("?") for s in said), 1)
                    d, said = chat.say(FINANCE)
                self.assertEqual(d, "proposed", said)
                code = self.assert_preview(chat, said)
                for text in ("What's next", "?"):
                    d, again = chat.say(text)
                    self.assertEqual(d, "proposed", again)
                    self.assertEqual(again, said)
                    self.assertEqual(chat.live()["draft_code"], code)
                got = chat.live()["slots"]["intake"]
                self.assertEqual((got["cost"], got["price"], got["qty"]), ("1.00", "2.00", 100))
                self.assertNotIn("$", json.dumps(chat.live()["texts"]))
                self.assertEqual(chat.asked, [])
                self.assertEqual(len(transport.calls), 1)
                self.doCleanups()

    def test_edits_keep_same_code_and_only_updated_preview_is_applied_then_undo(self):
        chat, _ = self.chat()
        _, said = chat.say(FINANCE, base.JAR)
        code = self.assert_preview(chat, said)
        old_hash = chat.drafts()[0]["draft_hash"]
        for text, present, absent in (("remove Made in USA", "No Foaming", "Made in USA"),
                                      ("add: great for furniture", "great for furniture", "Made in USA"),
                                      ("price 3", "$3.00", "Made in USA")):
            d, said = chat.say(text)
            self.assertEqual(d, "proposed", said)
            self.assertEqual(chat.live()["draft_code"], code)
            self.assertIn(present, said[0])
            self.assertNotIn(absent, said[0])
            self.assertEqual(len(said), 1)
        draft, = chat.drafts()
        self.assertNotEqual(draft["draft_hash"], old_hash)
        self.assertNotIn("Made in USA", draft["ops_json"])
        self.assertNotIn("$", draft["ops_json"])
        self.assertEqual(chat.commits(), 0)
        chat.say("yes " + code)
        self.assertEqual(chat.commits(), 1)
        saved = json.loads((chat.conv.sdir / ii.STORE).read_text().splitlines()[0])
        self.assertEqual(saved["answers"]["price"], "3.00")
        self.assertEqual(saved["answers"]["qty"], 100)
        product = next(p for p in json.loads((chat.kit.wt / "hass/content/products.json").read_text())["products"] if p["name"] == "Wood Glue")
        self.assertIn("great for furniture", product["description"])
        self.assertNotIn("Made in USA", product["description"])
        self.assertEqual(product["brand"], "Gorilla")
        chat.say("undo")
        chat.say("yes " + chat.drafts()[-1]["code"])
        self.assertEqual(chat.commits(), 2)
        rows = [json.loads(line) for line in (chat.conv.sdir / ii.STORE).read_text().splitlines()]
        self.assertEqual([r["status"] for r in rows], ["saved", "undone"])

    def test_one_price_question_then_new_info_not_yes_no_reprompt(self):
        chat, _ = self.chat()
        _, said = chat.say("", base.JAR)
        self.assertIn("What price should it sell for?", said[0])
        _, said = chat.say("What's next")
        self.assertIn("Here's the listing:", said[0])
        self.assertNotIn("?", said[0])
        d, said = chat.say("$2")
        self.assertEqual(d, "proposed", said)
        self.assertIn("$2.00", said[0])

    def test_forbidden_edit_does_not_change_approvable_draft_and_photo_money_ignored(self):
        chat, _ = self.chat({**DETAILS, "price": "99.00", "stock": 999})
        _, said = chat.say(FINANCE, base.JAR)
        original = chat.drafts()[0]
        for edit in ("add: <script>", "add: costs $500", "add: sells for two dollars", "add: bad\u202eline"):
            d, said = chat.say(edit)
            self.assertEqual(d, "not-drafted", said)
            self.assertEqual(chat.drafts()[0], original)
            self.assertEqual(chat.commits(), 0)
        self.assertEqual(chat.live()["slots"]["intake"]["price"], "2.00")

    def test_earlier_identity_does_not_mask_later_photo_brand_shelf_or_description(self):
        chat, _ = self.chat({**DETAILS, "category": "drinks"})
        text = "new glue"
        chat.script(text, base.reply(name="Glue"))
        chat.say(text + "; " + FINANCE)
        d, said = chat.say("", base.JAR)
        self.assertEqual(d, "proposed", said)
        slots = chat.live()["slots"]
        self.assertEqual(slots["name"], "Glue")
        self.assertEqual(slots["maker"], "Gorilla")
        self.assertEqual(slots["shelf"], "drinks")
        self.assertIn("pointed applicator", slots["description"])

    def test_interrupted_label_callback_cannot_leave_a_no_reply_loop(self):
        chat, _ = self.chat()
        with mock.patch.object(chat.conv, "_read_label", side_effect=RuntimeError("interrupted callback")):
            chat.say(FINANCE, base.JAR)
        self.assertTrue(chat.live()["slots"]["intake"]["reading_photo"])
        d, said = chat.say("Glue")
        self.assertEqual(d, "proposed", said)
        self.assertEqual(chat.live()["slots"]["name"], "Glue")
        self.assertEqual(len(said), 1)
        self.assertFalse(chat.live()["slots"]["intake"]["reading_photo"])

    def test_separate_quantity_and_spelled_money_clauses_and_zero_stock(self):
        for words, qty, stock in (("bought 100; paid one dollar; selling for two dollars", 100, "yes"),
                                  ("stock 0; price 2; cost 1", 0, "no")):
            with self.subTest(words=words):
                chat, _ = self.chat()
                d, said = chat.say(words, base.JAR)
                self.assertEqual(d, "proposed", said)
                slots = chat.live()["slots"]
                self.assertEqual((slots["intake"]["qty"], slots["intake"]["price"], slots["intake"]["cost"]),
                                 (qty, "2.00", "1.00"))
                self.assertEqual(slots["availability"], stock)
                self.assertNotIn("dollar", chat.drafts()[0]["ops_json"])
                self.assertEqual(chat.asked, [])
                self.doCleanups()

    def test_quantity_edits_recompute_derived_stock_but_preserve_explicit_stock(self):
        chat, _ = self.chat()
        chat.say(FINANCE, base.JAR)
        code = chat.live()["draft_code"]
        for text, qty, stock, label in (("stock 0", 0, "no", "sold out"),
                                        ("stock 7", 7, "yes", "in stock"),
                                        ("low on stock", 7, "limited", "low on stock"),
                                        ("stock 0", 0, "limited", "low on stock")):
            with self.subTest(text=text, qty=qty):
                disposition, said = chat.say(text)
                self.assertEqual(disposition, "proposed", said)
                self.assertEqual(chat.live()["draft_code"], code)
                slots = chat.live()["slots"]
                self.assertEqual(slots["intake"]["qty"], qty)
                self.assertEqual(slots["availability"], stock)
                self.assertIn("Availability: " + label, said[0])
                operations = json.loads(chat.drafts()[0]["ops_json"])
                selection, = [op for op in operations if op["op"] == "store.confirm_selection"]
                self.assertEqual(set(selection["args"]), {stock})

    def test_model_cannot_supply_private_finances_or_fake_photo_provenance(self):
        chat, _ = self.chat()
        text = "new glue from Gorilla"
        chat.script(text, base.reply(name="Glue", maker="Gorilla", intake={"price": "99.00", "qty": 100,
                                                                         "photo_details": DETAILS}))
        _, said = chat.say(text)
        got = chat.live()["slots"]["intake"]
        self.assertNotIn("price", got)
        self.assertNotIn("qty", got)
        self.assertNotIn("photo_details", got)
        self.assertEqual(chat.drafts(), [])

    def test_restart_preserves_same_code_and_latest_copy(self):
        from hass import conversation
        chat, _ = self.chat()
        chat.say(FINANCE, base.JAR)
        _, said = chat.say("remove Made in USA")
        code = chat.live()["draft_code"]
        chat.conv.db.close()
        chat.conv = conversation.Conversation(str(chat.kit.repo.state), chat.kit.editor, chat.interp, lambda: chat.now,
                                              chat.kit.previewer, photos=chat.photos, skills=chat.registry)
        _, repeated = chat.say("What's next")
        self.assertEqual(repeated, said)
        self.assertEqual(chat.live()["draft_code"], code)
        chat.say("yes " + code)
        self.assertEqual(chat.commits(), 1)

    def test_live_protected_claim_gate_remains_in_preview_and_approval(self):
        from hass import live_policy
        chat, _ = self.chat()
        chat.conv.settings["liveSite"] = {"url": "https://example.invalid"}
        # The fixture editor is sandbox-bound; exercise the real policy predicate
        # at the conversation seam, without a live site or release write.
        chat.conv._live_reasons = live_policy.check
        _, said = chat.say(FINANCE, base.JAR)
        self.assertIn("Made in USA", said[0])
        self.assertIn("I can't put this on the website", said[0])
        code = chat.live()["draft_code"]
        self.assertNotIn("yes " + code, said[0])
        chat.say("yes " + code)
        self.assertEqual(chat.commits(), 0)
        self.assertEqual(chat.drafts()[0]["state"], "proposed")

    def test_exact_live_demo_before_caption_and_late_text(self):
        from hass import answer_reader, cloud_codex
        sentence = "I bought 100 of these at one dollar per item and I will sell them at $2 per item"
        for when in ("before", "caption", "after"):
            with self.subTest(when=when):
                chat, _ = self.chat({**DETAILS, "description": DETAILS["description"] + " 4 fl. oz. (118 mL)."})
                requests, cloud = [], []
                def local(url, body, headers, timeout):
                    self.assertFalse(chat.conv.db.in_transaction)
                    request = json.loads(body)
                    requests.append(request)
                    result = ({"price_cents": 200, "cost_cents": 100, "quantity": 100}
                              if "price_cents" in request["messages"][0]["content"] else {"category": "general"})
                    return 200, json.dumps({"done": True, "message": {"content": json.dumps(result)}}).encode()
                fallback = answer_reader.AnswerReader("http://127.0.0.1:11434", "fixture", transport=local)
                chat.conv.answer_reader = answer_reader.AnswerReader(None, "gpt-6.1-sol", api="codex",
                    transport=cloud_codex.CodexTransport(runner=lambda request: cloud.append(request)), fallback=fallback)
                if when == "before":
                    chat.say(sentence)
                    chat.now += timedelta(minutes=28)
                _, said = chat.say(sentence if when == "caption" else "", base.JAR)
                if when == "after":
                    self.assertEqual(said[0].count("What price should it sell for?"), 1)
                    self.assertNotIn("Reply yes", said[0])
                    chat.now += timedelta(minutes=28)
                    _, said = chat.say(sentence)
                self.assert_preview(chat, said)
                preview = said[0]
                self.assertEqual(preview.count("4 fl. oz. (118 mL)"), 1)
                self.assertEqual(chat.live()["slots"]["description"].count("4 fl. oz. (118 mL)"), 1)
                self.assertIn("Category: General (say 'category X' to change)", preview)
                self.assertNotIn("pantry", preview.lower())
                public, private = preview.split("Private (not shown on the website): ")
                self.assertIn("Price: $2.00", public)
                self.assertNotIn("$1.00", public)
                self.assertIn("cost $1.00, quantity 100", private)
                self.assertNotIn("Stock on site", preview)  # catalog shows an availability word, not a count
                self.assertIn("Features:", preview)
                description = next(line for line in preview.splitlines() if line.startswith("Description:"))
                self.assertNotIn("Incredibly Strong", description)
                self.assertNotIn("size", description.lower())
                self.assertEqual(cloud, [])  # unchanged owner-finance local-only guard
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0]["format"]["additionalProperties"], False)
                self.assertNotIn("$", json.dumps(chat.live()["texts"]))
                self.doCleanups()

    def test_natural_fallback_money_and_quantity_and_late_edit_keep_code(self):
        chat, _ = self.chat()
        _, said = chat.say("I bought 100 of these at one dollar per item and I will sell them at two dollars per item", base.JAR)
        code = self.assert_preview(chat, said)
        for text, price, cost, qty in (("retail 3", "3.00", "1.00", 100),
                                       ("have 20", "3.00", "1.00", 20),
                                       ("cost 4", "3.00", "4.00", 20)):
            disposition, said = chat.say(text)
            self.assertEqual(disposition, "proposed", said)
            self.assertEqual(len(said), 1)
            self.assertIn("yes " + code, said[0])
            got = chat.live()["slots"]["intake"]
            self.assertEqual((got["price"], got["cost"], got["qty"]), (price, cost, qty))
        self.assertIn("selling price is below your cost", said[0])  # warning, not a publication block
        _, said = chat.say("category flowers")
        self.assertIn("Category: Flowers", said[0])
        self.assertEqual(chat.live()["draft_code"], code)

    def test_separate_finance_messages_before_photo_do_not_become_memory_or_till_commands(self):
        chat, _ = self.chat()
        till = mock.Mock()
        till.first.return_value = till.parse.return_value = None
        chat.conv.till = till
        for words in ("cost one dollar", "retail two dollars", "have 100"):
            chat.say(words)
        _, said = chat.say("", base.JAR)
        self.assert_preview(chat, said)
        self.assertFalse(till.parse.called)
        self.assertFalse(till.first.called)
        self.assertEqual(chat.asked, [])

    def test_category_uses_real_list_and_owner_context_in_the_existing_photo_read(self):
        from hass.content_model import CATEGORIES
        chat, transport = self.chat({**DETAILS, "category": "general"})
        public = "new glue for furniture"
        chat.script(public, base.reply(name="Glue"))
        _, said = chat.say(public + "; " + FINANCE, base.JAR)
        self.assertIn("Category: General", said[0])
        self.assertEqual(len(transport.calls), 1)  # no second model round trip for category
        body = transport.calls[0][1]
        prompt = body["messages"][0]["content"]
        self.assertIn(json.dumps(list(CATEGORIES)), prompt)
        self.assertIn(public, prompt)
        self.assertNotIn("$", prompt)
        self.assertIn("never guess pantry", prompt)

    def test_structured_fields_strict_validation_and_fallback(self):
        from hass import answer_reader
        valid = {"price_cents": 200, "cost_cents": 100, "quantity": 100}
        for values in (valid, {**valid, "quantity": 0}, {**valid, "quantity": 100000}):
            got = ii.commerce_answers(values)
            self.assertEqual(got["price"], "2.00")
            self.assertEqual(got["qty"], values["quantity"])
        for values in ({**valid, "quantity": 100001}, {**valid, "quantity": -1}, {**valid, "price_cents": True},
                       {**valid, "price_cents": 2.5}, {**valid, "cost_cents": "100"}, {**valid, "extra": 1}):
            with self.subTest(values=values):
                self.assertEqual(ii.commerce_answers(values), {})
                reader = answer_reader.AnswerReader("http://127.0.0.1:11434", "fixture", transport=lambda *args:
                    (200, json.dumps({"done": True, "message": {"content": json.dumps(values)}}).encode()))
                self.assertEqual(reader.fields("sell for two dollars"), {})
                self.assertEqual(ii.caption_answers("sell for two dollars", values)[1]["price"], "2.00")
        self.assertNotIn("qty", ii.caption_answers("have 100001")[1])

    def test_interpreter_can_read_non_regex_owner_finance_only(self):
        from hass import answer_reader
        chat, _ = self.chat()
        seen = []
        def transport(url, body, headers, timeout):
            self.assertFalse(chat.conv.db.in_transaction)
            request = json.loads(body)
            seen.append(request)
            values = ({"category": "general"} if "photo_read" in request["messages"][1]["content"] else
                      {"price_cents": 250, "cost_cents": 125, "quantity": 20})
            return 200, json.dumps({"done": True, "message": {"content": json.dumps(values)}}).encode()
        chat.conv.answer_reader = answer_reader.AnswerReader("http://127.0.0.1:11434", "fixture", transport=transport)
        chat.say("", base.JAR)
        _, said = chat.say("I purchased twenty of these for a dollar twenty-five each; retail is two fifty")
        self.assertEqual(chat.live()["state"], "drafted", said)
        self.assertIn("Price: $2.50", said[0])
        self.assertIn("cost $1.25, quantity 20", said[0])
        self.assertEqual(len(seen), 1)
        self.assertNotIn("photo_read", seen[0]["messages"][1]["content"])
        self.assertEqual(chat.asked, [])

    def test_photo_and_website_approval_never_call_till_parser_or_writer(self):
        chat, _ = self.chat()
        till = mock.Mock()
        till.first.return_value = till.parse.return_value = None
        chat.conv.till = till
        chat.say(FINANCE, base.JAR)
        self.assertFalse(till.parse.called)
        code = chat.live()["draft_code"]
        chat.say("yes " + code)
        self.assertFalse(till.approve.called)
        self.assertEqual(chat.commits(), 1)


if __name__ == "__main__":
    unittest.main()
