"""AV1222-10 (F03): `cost <product id>: <pack cost> for <units>` saves a private dated purchase cost (memory cost.<id>);
`margin <product id> at <M>%` uses it; `forget cost.<id>` clears it. The cost never reaches the interpreter, a draft or the site.
Offline: temp repo, private state dir, injected clock, fixture or recording interpreter. Run:
python3 -B -m unittest hass.tests.test_purchase_cost -v
"""

import json
import unittest
from datetime import timedelta

from hass import conversation, margins, sitegen, voice
from hass.interpreter_local import LocalInterpreter
from hass.tests.test_conversation import CHAT, GROUP, STRANGER, T0, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS
from hass.tests.test_status_pause import PAUSED_ONE, StoreMixin

AVO = "photo-product-001"  # "Hass avocado"
SAVED = f"Saved. Hass avocado costs you 24.00 for 12. That stays private and is never on the website. Say forget cost.{AVO} to remove it."
NONE = f"I don't have a cost saved for {AVO}. Tell me first, like cost {AVO}: 24 for 12."
HINT = "I couldn't save that. Tell me the product, what you pay for a pack and how many are in it, like cost Hass avocado: 24 for 12."


class CostTestCase(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **kw: (self.calls.append(_n), _r(*a, **kw))[1])

    def chat(self, text, disposition, reply=None, **kw):
        self.assertEqual(self.say(text, **kw), disposition)
        [got] = self.replies()
        if reply is not None: self.assertEqual(got, reply)
        return got

    def rows(self, key=f"cost.{AVO}"):
        if "memory" not in self.tables(): return []
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM memory WHERE key = ? ORDER BY id", (key,))]


class SaveAndMarginTests(CostTestCase):
    def test_save_then_margin_shows_the_dated_cost_and_the_steps(self):
        self.chat(f"cost {AVO}: 24.00 for 12", "memory-saved", SAVED, pid="c1")
        [row] = self.rows()
        self.assertEqual((row["value"], row["kind"], row["source"]), ("24.00 for 12", "fact", "owner-stated:c1"))
        self.now = T0 + timedelta(hours=8)  # 01:00 UTC Nov 3 is still Nov 2 in Los Angeles
        want = "Using the cost you gave me today at 9 am.\n" + margins.say(margins.compute("24.00", "12", "0", "35"))
        self.assertEqual(self.chat(f"Margin {AVO} at 35%", "margin"), want)
        self.assertIn("Charge $3.08.", want)
        self.assertEqual(self.chat(f"margin {AVO} at 35% shrink 5%", "margin"),
                         "Using the cost you gave me today at 9 am.\n" + margins.say(margins.compute("24", "12", "5", "35")))
        self.assertEqual((self.drafts(), self.commits(), self.calls, self.editor.applies), ([], 0, [], 0))
        self.assertEqual(len(self.rows()), 1)  # margin stored nothing
        self.assertIn(f"cost.{AVO}: 24.00 for 12 (since today at 9 am)", self.chat("memory", "memory-list"))

    def test_no_cost_saved_and_margin_does_not_create_the_memory_table(self):
        self.assertEqual(self.chat(f"margin {AVO} at 35%", "margin"), NONE)
        self.assertEqual(self.chat("margin no-such-product at 35%", "margin"),
                         "I don't have a cost saved for no-such-product. Tell me first, like cost no-such-product: 24 for 12.")
        self.assertNotIn("memory", self.tables())
        self.chat(f"cost {AVO}: 24 for 12", "memory-saved")
        self.assertEqual(self.chat("margin photo-product-002 at 35%", "margin"), "I don't have a cost saved for photo-product-002. Tell me first, like cost photo-product-002: 24 for 12.")

    def test_dollar_sign_case_and_number_forms_save_one_normal_value(self):
        self.chat(f"COST {AVO.upper()}: $24 For 12", "memory-saved", SAVED)
        self.chat(f"cost {AVO}: 24.00 for 12.0", "memory-unchanged", f"I already have that cost for Hass avocado, so nothing changed.")
        self.assertEqual([r["value"] for r in self.rows()], ["24.00 for 12"])

    def test_margin_out_of_range_is_named(self):
        self.chat(f"cost {AVO}: 24 for 12", "memory-saved")
        self.assertEqual(self.chat(f"margin {AVO} at 95%", "margin"), "I couldn't work that out. Please check the margin: it needs to be a plain number in a sensible range.")
        self.assertTrue(self.chat(f"margin {AVO} at 35% shrink 95%", "margin").startswith("I couldn't work that out. Please check the shrink"))

    def test_full_length_product_ids_support_cost_update_margin_and_forget(self):
        path = self.repo.wt / "hass" / "content" / "products.json"
        doc = json.loads(path.read_text())
        for size in range(59, 65):
            with self.subTest(size=size):
                ident = "p" * size
                doc["products"][0]["id"] = ident
                path.write_text(json.dumps(doc))
                key = f"cost.{ident}"
                self.chat(f"cost {ident}: 24 for 12", "memory-saved")
                self.chat(f"cost {ident}: 24 for 12", "memory-unchanged")
                self.chat(f"cost {ident}: 30 for 12", "memory-updated")
                assert self.conv.memory is not None
                self.assertEqual(self.conv.memory.get(key), "30.00 for 12")
                self.assertEqual(self.chat(f"margin {ident} at 35%", "margin"),
                                 "Using the cost you gave me today at 9 am.\n" +
                                 margins.say(margins.compute("30", "12", "0", "35")))
                self.assertNotIn(key, [n["key"] for n in self.conv._notes()])
                self.chat(f"remember {key}: 5 for 1", "memory-invalid", HINT)
                self.chat(f"forget {key}", "memory-forgot", f"Okay, I've forgotten {key}.")
                self.assertEqual({r["value"] for r in self.rows(key)}, {""})
                self.assertTrue(self.chat(f"margin {ident} at 35%", "margin").startswith("I don't have a cost saved"))
        assert self.conv.memory is not None
        for key in ("p" * 65, "cost." + "p" * 65, "cost." + "p" * 59 + "."):
            with self.subTest(invalid_key=key), self.assertRaisesRegex(ValueError, "invalid key"):
                self.conv.memory.get(key)

    def test_hidden_product_can_have_a_cost(self):
        self.chat("cost photo-product-040: 8 for 4", "memory-saved",
                  "Saved. Raw milk white cheddar costs you 8.00 for 4. That stays private and is never on the website. "
                  "Say forget cost.photo-product-040 to remove it.")


class RefusalTests(CostTestCase):
    def test_bad_product_or_numbers_are_refused_naming_the_field_and_nothing_is_stored(self):
        for text, reply in ((f"cost photo-product-999: 24 for 12", "I don't know a product called photo-product-999. Try find and a word from its name."),
                            (f"cost {AVO}: 24 for 0", "I couldn't read those numbers. Please check how many are in a pack: it needs to be a plain number in a sensible range."),
                            (f"cost {AVO}: 24 for 12.5", "I couldn't read those numbers. Please check how many are in a pack: it needs to be a plain number in a sensible range."),
                            (f"cost {AVO}: 0 for 12", "I couldn't read those numbers. Please check the pack price: it needs to be a plain number in a sensible range."),
                            (f"cost {AVO}: abc for 12", "I couldn't read those numbers. Please check the pack price: it needs to be a plain number in a sensible range."),
                            (f"cost {AVO}: 24 for abc", "I couldn't read those numbers. Please check how many are in a pack: it needs to be a plain number in a sensible range."),
                            (f"cost {AVO}: 24.005 for 12", "I couldn't read those numbers. Please check the pack price: it needs to be a plain number in a sensible range."),
                            (f"cost {AVO}: 24", voice.plain(conversation.COST_USAGE)),
                            (f"cost {AVO} 24 for 12", voice.plain(conversation.COST_USAGE)),
                            ("cost", voice.plain(conversation.COST_USAGE)),
                            ("cost : 24 for 12", voice.plain(conversation.COST_USAGE)),
                            ("cost " + "x" * 80 + ": 24 for 12", "I don't know a product called " + "x" * 80 + ". Try find and a word from its name.")):
            with self.subTest(text=text):
                self.chat(text, "memory-invalid", reply)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM memory").fetchone()[0], 0)
        self.assertEqual(self.chat(f"margin {AVO} at 35%", "margin"), NONE)

    def test_a_refused_new_cost_keeps_the_old_one(self):
        self.chat(f"cost {AVO}: 24 for 12", "memory-saved")
        self.chat(f"cost {AVO}: 30 for 0", "memory-invalid", "I couldn't read those numbers. Please check how many are in a pack: it needs to be a plain number in a sensible range.")
        self.assertEqual([r["value"] for r in self.rows()], ["24.00 for 12"])

    def test_generic_remember_of_a_cost_key_is_refused_with_the_hint(self):
        for text in (f"remember cost.{AVO}: 5 for 1", f"Remember COST.{AVO}: 5 for 1", "remember cost.x: hi"):
            with self.subTest(text=text): self.chat(text, "memory-invalid", HINT)
        self.chat(f"cost {AVO}: 24 for 12", "memory-saved")
        self.chat(f"remember cost.{AVO}: 5 for 1", "memory-invalid", HINT)  # also over an existing cost
        self.assertEqual([r["value"] for r in self.rows()], ["24.00 for 12"])

    def test_cost_lookalikes_go_to_the_interpreter(self):
        for text in ("costs are up", "the cost of jam is high", "please cost it"):
            with self.subTest(text=text):
                self.assertIsNone(conversation.parse_memory(text))

    def test_owner_gate(self):
        for kw, disposition in ((dict(sender=STRANGER), "ignored"), (dict(chat=GROUP), "ignored"), (dict(from_me=True), "echo")):
            with self.subTest(**kw):
                self.assertEqual(self.say(f"cost {AVO}: 24 for 12", **kw), disposition)
                self.assertEqual(self.replies(), [])
        self.assertEqual(self.rows(), [])


class ChangeAndForgetTests(CostTestCase):
    def test_same_again_is_unchanged_a_new_cost_updates_and_forget_clears(self):
        self.chat(f"cost {AVO}: 24 for 12", "memory-saved", SAVED, pid="a1")
        self.now = T0 + timedelta(days=1)
        self.chat(f"cost {AVO}: 24.00 for 12", "memory-unchanged", f"I already have that cost for Hass avocado, so nothing changed.", pid="a2")
        self.assertEqual(len(self.rows()), 1)
        self.chat(f"cost {AVO}: 30 for 12", "memory-updated",
                  f"Updated. Hass avocado now costs you 30.00 for 12. That stays private and is never on the website. "
                  f"Say forget cost.{AVO} to remove it.", pid="a3")
        self.assertEqual([(r["value"], r["superseded_at"] is None, r["source"]) for r in self.rows()],
                         [("24.00 for 12", False, "owner-stated:a1"), ("30.00 for 12", True, "owner-stated:a3")])
        self.assertTrue(self.chat(f"margin {AVO} at 35%", "margin").startswith("Using the cost you gave me today at 9 am.\n"))
        self.chat(f"forget cost.{AVO}", "memory-forgot", f"Okay, I've forgotten cost.{AVO}.")
        self.assertEqual(self.chat(f"margin {AVO} at 35%", "margin"), NONE)
        self.assertEqual({r["value"] for r in self.rows()}, {""})  # the text is blanked, the dates stay
        self.chat(f"forget cost.{AVO}", "memory-none", f"I don't have a note called cost.{AVO}.")
        self.chat(f"cost {AVO}: 5 for 1", "memory-saved")  # a cleared cost can be saved again
        self.assertTrue(self.chat(f"margin {AVO} at 35%", "margin").startswith("Using the cost you gave me today at 9 am.\n"))

    def test_paused_cost_and_margin_still_answer_and_nothing_is_applied(self):
        draft, _reply = self.propose("hours")
        self.chat("pause changes", "pause", PAUSED_ONE)
        self.chat(f"cost {AVO}: 24 for 12", "memory-saved", SAVED)
        self.assertTrue(self.chat(f"margin {AVO} at 35%", "margin").startswith("Using the cost you gave me today at 9 am.\n"))
        self.assertEqual((self.drafts(), self.commits(), self.editor.applies), ([draft], 0, 0))


class LeakTests(CostTestCase):
    PACK = "73.19"

    class Fake:
        def __init__(self): self.calls = []

        def __call__(self, url, body, headers, timeout):
            self.calls.append(body)
            return 200, json.dumps({"message": {"content": json.dumps(_ops((HOURS, {"hours": NEW_HOURS})))}, "done": True}).encode()

    def test_the_interpreter_request_has_no_cost_key_or_value_but_still_carries_other_notes(self):
        fake = self.Fake()
        self.interp = LocalInterpreter("http://127.0.0.1:11434", "m", "SYSTEM", transport=fake)
        self.conv = self.open()
        self.chat("remember tone: short and friendly", "memory-saved")
        self.chat(f"cost {AVO}: {self.PACK} for 7", "memory-saved")
        self.assertEqual(self.say("make the hours longer"), "proposed")
        [reply] = self.replies()
        [body] = fake.calls
        self.assertIn("short and friendly", body.decode())  # the request did carry the note list
        for private in ("cost.", self.PACK, f"cost.{AVO}", "7 for"): self.assertNotIn(private, body.decode())
        self.assertNotIn(self.PACK, reply)  # (c) the proposal text
        self.assertNotIn(self.PACK, json.dumps(self.drafts(), default=str))
        self.assertEqual(self.conv._notes(), [{"key": "tone", "text": "short and friendly"}])

    def test_a_cost_never_uses_up_the_note_slots(self):
        self.chat(f"cost {AVO}: {self.PACK} for 7", "memory-saved")
        for i in range(conversation.MAX_NOTES):
            self.now += timedelta(minutes=1)
            self.chat(f"remember note-{i:02d}: text {i}", "memory-saved")
        self.assertEqual(len(self.conv._notes()), conversation.MAX_NOTES)
        self.assertFalse([n for n in self.conv._notes() if n["key"].startswith("cost.")])

    def test_regenerated_site_files_do_not_contain_the_cost(self):
        self.chat(f"cost {AVO}: {self.PACK} for 7", "memory-saved")
        self.assertEqual(sitegen.main(["--write", "--repo", str(self.repo.wt)]), 0)
        site = self.repo.wt / "storefront-mockup"
        files = [p for p in site.rglob("*") if p.is_file() and p.suffix in (".html", ".js", ".json", ".css", ".txt", ".xml")]
        self.assertTrue(files)
        self.assertFalse([str(p) for p in files if self.PACK.encode() in p.read_bytes()])
        self.assertFalse([str(p) for p in (self.repo.wt / "hass" / "content").rglob("*.json") if self.PACK.encode() in p.read_bytes()])


class HelpTests(unittest.TestCase):
    def test_help_lists_cost_and_the_product_form_of_margin_and_both_examples_parse(self):
        lines = voice.plain(conversation.HELP_TEXT).splitlines()
        [cost] = [ln for ln in lines if ln.startswith("cost ")]
        [margin] = [ln for ln in lines if ln.startswith("margin ")]
        self.assertEqual(cost, "cost Hass avocado: 24 for 12 - the price you pay, kept private")
        self.assertEqual(margin, "margin Hass avocado at 35% - a price idea from the cost you saved")
        self.assertEqual(conversation.parse_memory(f"cost {AVO}: 24 for 12"), ("cost", AVO, "24 for 12"))
        self.assertEqual(conversation.parse_command(f"margin {AVO} at 35%"), ("margin", f"{AVO} at 35%"))


if __name__ == "__main__":
    unittest.main()
