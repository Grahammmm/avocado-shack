"""Offline recorded-reply contract for HASS-PHOTO-DETAIL-1; no model/network.

GLUE is a canned model reply for the task's reported bottle details, not a new
live-image accuracy receipt. The photo harness uses a synthetic jar for storage.
"""
import json
import unittest
from types import SimpleNamespace

from hass import cloud_codex, label_reader
from hass.skills import item_add, item_intake as ii, testkit
from hass.tests import test_item_add_dispatch as base
from hass.tests.test_label_reader import reader, recorded
from hass.tests.test_photo_draft import JPG

GLUE = {
    "name": "Wood Glue", "brand": "Gorilla", "category": "pantry",
    "product_type": "Wood Glue", "size": "4 fl. oz. (118 mL)",
    "colour": "Natural Color", "features": ["Dries Natural Color"],
    "printed_claims": ["Made in USA"],
    "description": "Wood Glue is printed on this squeeze bottle. The bottle has a pointed applicator.",
}


class PhotoDetails(unittest.TestCase):
    def chat(self, reply=GLUE):
        chat = base.Chat([base.JAR], None, {"itemIntake": True})
        chat.base_commits = int(testkit._git(chat.kit.wt, "rev-list", "--count", "HEAD"))
        chat.conv.labels, transport = reader(recorded(reply))
        self.addCleanup(chat.close)
        return chat, transport

    def test_glue_reply_retains_every_reported_detail_and_uses_catalog_categories(self):
        labels, transport = reader(recorded(GLUE))
        self.assertEqual(labels.read(JPG, ["pantry", "drinks"]), GLUE)
        prompt = transport.calls[0][1]["messages"][0]["content"]
        self.assertIn('["pantry", "drinks"]', prompt)
        full = {**GLUE, "count": "2-pack", "finish": "Matte", "materials": "Wood",
                "barcode": "012345678905", "warnings": ["Keep out of reach of children"]}
        self.assertEqual(label_reader.keep(full, ["pantry"]), full)

    def test_claim_leaks_are_quarantined_and_bad_text_or_photo_finance_is_refused(self):
        found = label_reader.keep({**GLUE, "description": "Organic glue made in USA.",
                                   "features": ["Certified organic", "Costs 4 dollars", "<script>", "${{x}}", "Dries clear"],
                                   "warnings": ["Do not ingest", "bad\u202eline"],
                                   "price": "2.00", "cost": "1.00", "stock": 99, "barcode": "123?"}, ["pantry"])
        self.assertNotIn("description", found)
        self.assertEqual(found["features"], ["Dries clear"])
        self.assertEqual(found["warnings"], ["Do not ingest"])
        self.assertEqual(found["printed_claims"], ["Organic glue made in USA.", "Certified organic", "Made in USA"])
        for key in ("price", "cost", "stock", "barcode"):
            self.assertNotIn(key, found)
        self.assertEqual(label_reader.keep({"name": "4 dollars", "brand": "5 euros"}, []), {})
        self.assertEqual(label_reader.keep({**GLUE, "category": "tools"}, ["pantry"]).get("category"), None)

    def test_codex_photo_prompt_stays_on_existing_route_without_finance_caption(self):
        calls = []
        def runner(request):
            calls.append(request)
            return {"ok": True, "text": json.dumps(GLUE)}
        transport = cloud_codex.CodexTransport(runner=runner)
        labels = label_reader.LabelReader(None, "gpt-6.1-sol", api="codex", transport=transport)
        self.assertEqual(labels.read(JPG, ["pantry"]), GLUE)
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0]["model"], calls[0]["effort"]), ("gpt-6.1-sol", "low"))
        self.assertTrue(calls[0]["images"])
        self.assertIn("printed_claims", calls[0]["instructions"])
        self.assertEqual(calls[0]["text"], "Inspect this photo.")

    def test_local_fallback_preserves_full_detail_contract_once(self):
        fallback, spare = reader(recorded(GLUE))
        labels = label_reader.LabelReader("http://127.0.0.1:11434", "vision-test", fallback=fallback,
                                          transport=lambda *args: (500, b""))
        self.assertEqual(labels.read(JPG, ["pantry"]), GLUE)
        self.assertTrue(labels.last_fallback)
        self.assertEqual(len(spare.calls), 1)

    def test_caption_finance_and_photo_join_same_request_outside_transaction(self):
        chat, transport = self.chat()
        held = []
        transport.probe = lambda: held.append(chat.conv.db.in_transaction)
        d, said = chat.say("Bought for $1, sell for $2, 20 of them", base.JAR)
        self.assertEqual(d, "question")
        self.assertEqual(held, [False])
        live = chat.live()
        self.assertEqual(live["asked_slot"], ii.PREFIX + "photo_confirm", said)
        self.assertEqual(len(said), 1, said)
        for text in ("Wood Glue", "4 fl. oz. (118 mL)", "Dries Natural Color"):
            self.assertIn(text, said[0])
        got = live["slots"]["intake"]
        self.assertEqual({k: got[k] for k in ("cost", "price", "qty", "qty_unit")},
                         {"cost": "1.00", "price": "2.00", "qty": 20, "qty_unit": "each"})
        self.assertEqual(got["photo_details"], GLUE)
        self.assertEqual(chat.asked, [])
        self.assertNotIn("$", json.dumps(live["texts"]))
        self.assertEqual(chat.commits(), 0)
        # The owner confirms details, but this does NOT approve a printed claim.
        d, said = chat.say("yes")
        self.assertEqual(chat.live()["asked_slot"], ii.PREFIX + "photo_claim_0", said)
        self.assertIn("The label says: Made in USA. Put that on the website?", said[0])
        self.assertNotIn("Made in USA", ii.photo_description(chat.live()["slots"]["intake"]))
        chat.say("no")
        got = chat.live()["slots"]["intake"]
        self.assertEqual(got["photo_claim_answers"], {"0": False})
        self.assertNotIn("Made in USA", ii.photo_description(got))
        self.assertEqual(chat.live()["slots"]["name"], "Wood Glue")
        self.assertEqual(len(transport.calls), 1)

    def test_ordinary_caption_identity_and_typed_finance_are_both_kept(self):
        chat, _ = self.chat()
        public = "new rigatoni from Etto"
        chat.script(public, base.reply(name="Rigatoni", maker="Etto", shelf="pantry"))
        chat.say(public + "; Bought for $1; sell for $2; 20 of them", base.JAR)
        self.assertEqual(chat.live()["slots"]["name"], "Rigatoni")
        chat.say("yes")
        chat.say("no")
        live = chat.live()
        self.assertEqual(live["asked_slot"], ii.PREFIX + "sold_by")
        self.assertEqual((live["slots"]["name"], live["slots"]["maker"]), ("Rigatoni", "Etto"))
        self.assertEqual([q[0] for q in chat.asked], [public])

    def test_per_claim_explicit_yes_only_and_skip_reject_cancel_are_safe(self):
        for answer in ("yes", "no", "skip", "yes but no", "okay"):
            with self.subTest(answer=answer):
                slots = {"intake": {"photo_details": GLUE, "photo_confirmed": True}}
                got = ii.photo_answer("photo_claim_0", answer, slots)
                if answer in ("yes but no", "okay"):
                    self.assertIn("again", got)
                else:
                    intake = got["slots"]["intake"]
                    self.assertEqual("Made in USA" in ii.photo_description(intake), answer == "yes")
        self.assertEqual(ii.photo_answer("photo_claim_0", "cancel", slots), {"abort": True})
        rejected = ii.photo_answer("photo_confirm", "no", {"intake": {"photo_details": GLUE}})
        self.assertEqual(set(rejected["slots"]), {"intake"})
        self.assertEqual(ii.photo_description(rejected["slots"]["intake"]), "")

    def test_ambiguous_caption_never_seeds_an_exact_value(self):
        for text in ("Bought for $1 or $3", "20 or 30 of them", "sell for $2 maybe"):
            self.assertEqual(ii.caption_answers(text), (text, {}))
        _, got = ii.caption_answers("sell for $2; sell for $3; 20 of them")
        self.assertNotIn("price", got)
        self.assertEqual(got["qty"], 20)

    def test_description_claim_yes_reaches_draft_no_stays_out_and_private_record_keeps_receipt(self):
        # Use an existing maker so this test exercises the public draft, not maker creation.
        for consent in ("yes", "no"):
            with self.subTest(consent=consent):
                reply = {**GLUE, "name": "Craft glue", "brand": "Etto"}
                chat, _ = self.chat(reply)
                chat.say("Bought for $1, sell for $2, 20 of them", base.JAR)
                chat.say("yes")
                chat.say(consent)
                steps = []
                while (live := chat.live()) and (live["asked_slot"] or "").startswith(ii.PREFIX):
                    steps.append(live["asked_slot"])
                    d, said = chat.say("skip")
                self.assertNotIn(ii.PREFIX + "qty", steps)
                self.assertNotIn(ii.PREFIX + "price", steps)
                self.assertNotIn(ii.PREFIX + "cost", steps)
                self.assertEqual(d, "proposed", said)
                draft, = chat.drafts()
                ops = json.loads(draft["ops_json"])
                description = next(o["args"]["description"] for o in ops if o["op"] == "product.add")
                self.assertEqual("Made in USA" in description, consent == "yes")
                self.assertNotIn("$", draft["ops_json"])
                self.assertEqual(chat.commits(), 0)
                chat.say("yes " + draft["code"])
                record = json.loads((chat.conv.sdir / ii.STORE).read_text().splitlines()[0])
                self.assertEqual(record["answers"]["qty"], 20)
                self.assertEqual(record["photo_read"]["claim_answers"], {"0": consent == "yes"})
                self.assertEqual(record["photo_read"]["details"], reply)
                self.assertEqual(chat.commits(), 1)
                self.doCleanups()

    def test_live_claim_hold_and_content_checks_are_not_overridden_by_label_yes(self):
        got = {"photo_details": GLUE, "photo_confirmed": True, "photo_claim_answers": {"0": True}}
        slots = {"name": "Glue", "maker": "unknown", "intake": got}
        ctx = SimpleNamespace(live=True, content=None, texts=["Made in USA"])
        self.assertIsNone(item_add.house_description(slots, ctx))
        bad = {**got, "photo_details": {**GLUE, "description": "Glue costs $2."}}
        self.assertIsNone(item_add.house_description({**slots, "intake": bad}, ctx))

    def test_large_whole_label_and_barcode_survive_strict_owner_voice_checks(self):
        reply = {**GLUE, "barcode": "012345678905", "features": ["Printed feature line " + str(i) for i in range(24)]}
        chat, _ = self.chat(reply)
        chat.conv.outbox.strict = True
        _, said = chat.say("Bought for $1, sell for $2, 20 of them", base.JAR)
        self.assertEqual(chat.live()["asked_slot"], ii.PREFIX + "photo_confirm", said)
        self.assertIn("012345678905", said[-1])
        self.assertIn("Printed feature line 23", said[-1])
        self.assertEqual(chat.commits(), 0)

    def test_failed_label_read_keeps_existing_interview_and_caption_values(self):
        chat, transport = self.chat()
        transport.answer = TimeoutError()
        d, said = chat.say("Bought for $1, sell for $2, 20 of them", base.JAR)
        self.assertEqual((d, chat.live()["asked_slot"]), ("question", "name"))
        self.assertNotIn("photo_details", chat.live()["slots"]["intake"])
        self.assertEqual(chat.live()["slots"]["intake"]["qty"], 20)


if __name__ == "__main__":
    unittest.main()
