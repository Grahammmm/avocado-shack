"""Recorded glue read + real Conversation/editor. Synthetic storage photo, no live OCR/till/site."""
import json
import unittest
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
        self.assertIn("What is the selling price?", said[0])
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
