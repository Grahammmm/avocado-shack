"""SKILLS-ITEMS-1: the hide / restore / edit an item skills (hass/skills/items.py).

The case rows themselves (plans, golden diffs, undo, preview, ten owner sentences per skill) are in
hass/tests/fixtures/skills/items/ and run through the generic runners of the test kit (test_skills_plans.py and
test_skills_cases.py). This module pins what those rows cannot: the lint, the sentence and rule coverage of the
fixtures, the plain words of every owner-facing sentence, the live class derived from the real live policy, the extra
proposal lines, and the two small test-kit additions (a row's `setup` and the `undo` marker).
Run: python3 -B -m unittest hass.tests.test_skills_items -v
"""

import copy
import json
import tempfile
import types
import unittest
from pathlib import Path

from hass import conversation, editor, live_policy, voice
from hass.content_model import REPO_ROOT, load_and_validate
from hass.interpret_check import PRICE_REPLY
from hass.ops import load_registry
from hass.skills import kinds, load_skills, skill_lint, testkit
from hass.skills import items as it
from hass.skills.testkit import FIXTURES, load_rows, plain_words_problems, run_case_row
from hass.tests.test_editor import WriterRepo

CONTENT, SITE = REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup"
SKILLS = {s.name: s for s in it.SKILLS}
ROWS = {name: load_rows(REPO_ROOT / s.cases) for name, s in SKILLS.items()}
HIDE, RESTORE, EDIT = "item.hide", "item.restore", "item.edit"

# rule id -> the case row that proves it (a refusal row, tree untouched)
RULE_ROWS = {
    HIDE: {"held-refused": "hide-12-held", "already-hidden": "hide-13-already-hidden", "whole-shelf": "hide-11-more-than-six",
           "no-permanent-delete": "hide-14-forever"},
    RESTORE: {"not-hidden": "restore-11-already-on", "held-refused": "restore-8-held", "maker-hidden": "restore-12-maker-hidden"},
    EDIT: {"not-already-true": "edit-13-already-true", "twin": "edit-12-twin", "no-price": "edit-7-price", "held-refused": "edit-14-held"},
}


def product_id(content, name):
    return next(p["id"] for p in content.products if p["name"] == name)


def ctx_for(content=None, **more):
    return types.SimpleNamespace(today="2026-11-08", **({"content": content} if content is not None else {}), **more)


class Declaration(unittest.TestCase):
    def test_the_three_skills_load_and_lint_clean(self):
        registry = load_skills()
        for name in SKILLS:
            self.assertIs(registry.get(name), SKILLS[name])
        golden = {HIDE: [{"items": ["photo-product-055"]}], RESTORE: [{"items": ["photo-product-017"]}],
                  EDIT: [{"item": "photo-product-001", "name": "Hass avocados"}]}
        self.assertEqual(skill_lint(list(SKILLS.values()), load_registry(), repo_root=REPO_ROOT, golden=golden), [])
        self.assertEqual(skill_lint(registry, load_registry(), golden=golden), [])  # and beside backlog.log / page.faq

    def test_no_slot_carries_a_price(self):
        for skill in SKILLS.values():
            with self.subTest(skill.name):
                self.assertFalse({s.name for s in skill.slots} & it.PRICE_SLOTS)
                self.assertFalse({s.name.lower() for s in skill.slots} & {"price", "cost", "amount", "pricing"})

    def test_a_price_slot_is_refused_by_every_skill(self):
        for name, slots in ((HIDE, {"items": ["a"], "price": "5"}), (RESTORE, {"items": ["a"], "cost": "5"}),
                            (EDIT, {"item": "a", "price": "6.50"})):
            with self.subTest(name), self.assertRaises(it.Refusal) as caught:
                SKILLS[name].plan(slots, ctx_for())
            self.assertEqual(caught.exception.reply, PRICE_REPLY)

    def test_declared_edits_and_classes(self):
        for skill in SKILLS.values():
            self.assertEqual((skill.approval, skill.undo.mode, skill.undo.residue, skill.side_effects),
                             ("owner-yes", "revert", "none", ("none",)))
            self.assertTrue(skill.preview.startswith("product:"))
        self.assertEqual((SKILLS[HIDE].live_class, SKILLS[RESTORE].live_class, SKILLS[EDIT].live_class),
                         ("chat-live", "chat-live", "private-only"))
        for skill in (SKILLS[HIDE], SKILLS[RESTORE]):
            self.assertEqual([e for e in skill.edits if e[0].startswith("hass/")], [("hass/content/products.json", "products[id].status")])

    def test_every_rule_has_a_function_and_a_proving_row(self):
        declared = {r for s in SKILLS.values() for r in s.rules}
        self.assertEqual(declared, set(it.RULE_FUNCTIONS))
        for name, skill in SKILLS.items():
            ids = {r["id"]: r for r in ROWS[name]}
            for rule in skill.rules:
                if rule == "image-missing":
                    continue  # proved on a real site folder in ImageMissing below; the case rows have no missing picture
                with self.subTest(skill=name, rule=rule):
                    row = ids[RULE_ROWS[name][rule]]
                    self.assertEqual(row["kind"], "refuse")
                    self.assertNotIn("diff", row["expect"])


class Fixtures(unittest.TestCase):
    def test_ten_owner_sentences_per_skill_are_in_the_fixtures(self):
        for name, skill in SKILLS.items():
            with self.subTest(name):
                self.assertEqual(len(skill.triggers), 10)
                said = {t for r in ROWS[name] if not r.get("plan") for t in r["texts"]}
                self.assertEqual({t.text for t in skill.triggers} - said, set())
                tags = {t.tag for t in skill.triggers}
                self.assertTrue({"vague", "typo", "multi"} <= tags)

    def test_row_mix_per_skill(self):
        for name, skill in SKILLS.items():
            cases = [r for r in ROWS[name] if not r.get("plan")]
            kinds_seen = {r["kind"] for r in cases}
            with self.subTest(name):
                self.assertGreaterEqual(len(cases), 10)
                self.assertGreaterEqual(sum(r["kind"] == "refuse" for r in cases), 2)
                self.assertTrue({"clean", "vague", "typo", "multi", "refuse"} <= kinds_seen, kinds_seen)
                self.assertGreaterEqual(sum(1 for r in ROWS[name] if r.get("plan")), 4)
                self.assertTrue(all(r["version"] == skill.version for r in ROWS[name]))
                self.assertGreaterEqual(sum(r.get("undo") is True for r in cases), 5)

    def test_no_owner_sentence_is_a_whole_message_command(self):
        """The commands are judged before any skill: a sentence that is one would never reach the skill."""
        for skill in SKILLS.values():
            for trigger in skill.triggers:
                with self.subTest(trigger.text):
                    self.assertIsNone(conversation.COMMAND_RE.fullmatch(trigger.text.strip().lower()))

    def test_every_row_that_says_so_uses_the_slots_own_question_or_the_resolver_words(self):
        content = load_and_validate(CONTENT, SITE)
        asks = {HIDE: it.NO_ITEMS_HIDE, RESTORE: it.NO_ITEMS_RESTORE}
        for name, rows in ROWS.items():
            for row in rows:
                note = row.get("note", "")
                if note == "the slot's own question" and name in asks:
                    self.assertEqual(row["replies"][0]["question"], asks[name], row["id"])
                if note.startswith("resolver: product_ref "):
                    query = note.split()[2]
                    self.assertEqual(row["replies"][0]["question"], kinds.product_ref(content, query).reply, row["id"])
        self.assertEqual(kinds.product_ref(content, "plums").status, "none")

    def test_the_shops_own_names_are_what_the_rows_use(self):
        content = load_and_validate(CONTENT, SITE)
        by_id = {p["id"]: p["name"] for p in content.products}
        for pid, name in (("photo-product-055", "Cashews"), ("photo-product-017", "Lemons"), ("photo-product-097", "Figs"),
                          ("photo-product-031", "Guacamole"), ("photo-product-040", "Raw milk white cheddar")):
            self.assertEqual(by_id[pid], name)
        self.assertEqual(sum(1 for p in content.products if p.get("producerKey") == "Etto"), 5)  # the Etto row hides all five
        self.assertEqual(sum(1 for p in content.products if p["category"] == "fruit"), 13)  # "13 products at once"


class Plans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = load_and_validate(CONTENT, SITE)
        cls.ctx = ctx_for(cls.content)

    def refusal(self, name, slots, ctx=None):
        with self.assertRaises(it.Refusal) as caught:
            SKILLS[name].plan(slots, ctx or self.ctx)
        return caught.exception

    def test_the_refusal_is_a_value_error_with_the_owners_sentence(self):
        exc = self.refusal(HIDE, {"items": []})
        self.assertIsInstance(exc, ValueError)
        self.assertEqual((exc.reply, exc.backlog), (it.NO_ITEMS_HIDE, None))
        self.assertEqual(self.refusal(HIDE, {"items": ["photo-product-055"], "reason": "delete it for good"}).backlog, "policy")

    def test_a_single_id_string_is_one_item_and_the_slots_are_left_alone(self):
        slots = {"items": "photo-product-055", "reason": "slow seller"}
        before = copy.deepcopy(slots)
        self.assertEqual(it.plan_hide(slots, self.ctx), [{"op": "product.hide", "args": {"id": "photo-product-055"}}])
        self.assertEqual(slots, before)

    def test_unknown_slots_and_ids(self):
        self.assertEqual(self.refusal(HIDE, {"items": ["photo-product-055"], "colour": "red"}).reply, it.CANT_DO)
        self.assertEqual(self.refusal(HIDE, {"items": ["photo-product-999"]}).reply, it.UNKNOWN_PRODUCT)
        self.assertEqual(self.refusal(RESTORE, {"items": ["photo-product-999"]}).reply, it.UNKNOWN_PRODUCT)
        self.assertEqual(self.refusal(EDIT, {"item": "photo-product-999", "name": "X"}).reply, it.UNKNOWN_PRODUCT)
        self.assertEqual(self.refusal(EDIT, {"item": "photo-product-001", "maker": "Nobody"}).reply, it.UNKNOWN_MAKER)

    def test_a_problem_in_a_list_names_the_product_and_offers_the_rest(self):
        held = self.refusal(HIDE, {"items": ["photo-product-055", "photo-product-040"]}).reply
        self.assertIn("Raw milk white cheddar", voice.plain(held))
        self.assertTrue(held.endswith(it.REST_OF.strip()))
        again = self.refusal(RESTORE, {"items": ["photo-product-017", "photo-product-055"]}).reply
        self.assertIn("I already have", again)
        self.assertTrue(again.endswith(it.REST_OF.strip()))

    def test_the_largest_list_is_six(self):
        ids = [p["id"] for p in self.content.products if p["status"] == "active"][:7]
        self.assertEqual(len(it.plan_hide({"items": ids[:6]}, self.ctx)), 6)
        for fn in (it.plan_hide, it.plan_restore):
            self.assertIn("7 products at once", self.refusal(HIDE if fn is it.plan_hide else RESTORE, {"items": ids}).reply)

    def test_edit_drops_what_already_matches_and_keeps_the_rest(self):
        pesto = product_id(self.content, "Garlic pesto")
        ops = it.plan_edit({"item": pesto, "name": "Garlic pesto", "category": "dairy"}, self.ctx)  # the name is unchanged
        self.assertEqual(ops, [{"op": "product.edit", "args": {"id": pesto, "category": "dairy"}}])
        figs = product_id(self.content, "Figs")
        self.assertEqual(self.refusal(EDIT, {"item": figs, "clear": ["clearProducer"]}).reply,
                         f"It already says that on {voice.quote('Figs')}. Nothing changed.")

    def test_edit_maker_follows_the_makers_own_name_and_a_label_can_differ(self):
        figs = product_id(self.content, "Figs")
        [op] = it.plan_edit({"item": figs, "maker": "Etto"}, self.ctx)
        self.assertEqual(op["args"], {"id": figs, "brand": "Etto", "producerKey": "Etto", "displayBrand": "Etto"})
        [op] = it.plan_edit({"item": figs, "maker": "Etto", "display_brand": "Etto Pasta"}, self.ctx)
        self.assertEqual(op["args"]["displayBrand"], "Etto Pasta")

    def test_a_hidden_maker_cannot_be_chosen(self):
        content = load_and_validate(CONTENT, SITE)
        content.makers["Etto"]["hidden"] = True
        reply = self.refusal(EDIT, {"item": "photo-product-097", "maker": "Etto"}, ctx_for(content)).reply
        self.assertIn("is hidden", reply)

    def test_text_limits_and_marks_come_from_the_content_model(self):
        long_text = "x" * 601
        self.assertIn("600 characters", self.refusal(EDIT, {"item": "photo-product-001", "description": long_text}).reply)
        for text in ("<b>x</b>", "a {{ b }}", "zero\u200bwidth"):
            self.assertIn("plain words", self.refusal(EDIT, {"item": "photo-product-001", "description": text}).reply)
        for text in ("Sweet, $2", "9 cents each", "3 dollars", "two for 5\u00a2", "per lb", "per pound please"):
            self.assertEqual(self.refusal(EDIT, {"item": "photo-product-001", "name": text}).reply, PRICE_REPLY, text)

    def test_unambiguous_amounts_without_a_dollar_sign_are_prices_too(self):
        for text in ("Two for five.", "2 for 5.", "Five bucks each.", "two for five, best deal", "Three for 10", "a buck apiece",
                     "Only 5 a pound", "TWO FOR FIVE!"):
            for key in ("description", "name", "display_brand", "image_alt"):
                with self.subTest(text=text, slot=key):
                    self.assertEqual(self.refusal(EDIT, {"item": "photo-product-017", key: text}).reply, PRICE_REPLY)
        for text in ("Two for the road: a squeeze of lemon over fish for five minutes.", "Good for two for five minutes of toasting.",
                     "Buckwheat noodles from Bucks County.", "Pick one for dinner and two for lunch.", "Keep it 5 minutes, then another 2 for crisp edges and 3 to serve.",
                     "Add 2 for a milder dish."):
            with self.subTest(text=text):
                [op] = it.plan_edit({"item": "photo-product-017", "description": text}, self.ctx)
                self.assertEqual(op["args"]["description"], text)

    def test_a_price_form_never_reaches_a_draft_in_the_real_kit(self):
        for rid in ("edit-19-two-for-five", "edit-20-five-bucks"):
            row = next(r for r in ROWS[EDIT] if r["id"] == rid)
            self.assertTrue(run_case_row(row, SKILLS, SKILLS[EDIT]).ok, rid)
        digits = copy.deepcopy(next(r for r in ROWS[EDIT] if r["id"] == "edit-19-two-for-five"))
        digits["texts"] = ["the lemons description: 2 for 5."]
        digits["replies"][0]["slots"]["description"] = "2 for 5."
        self.assertTrue(run_case_row(digits, SKILLS, SKILLS[EDIT]).ok)

    def test_a_held_product_is_refused_with_the_recorded_concern_in_plain_words(self):
        content = load_and_validate(CONTENT, SITE)
        ctx = ctx_for(content)
        for fn, slots in ((it.plan_restore, {"items": ["photo-product-040"]}), (it.plan_hide, {"items": ["photo-product-040"]}),
                          (it.plan_edit, {"item": "photo-product-040", "name": "White cheddar"})):
            with self.assertRaises(it.Refusal) as caught:
                fn(slots, ctx)
            reply = voice.plain(caught.exception.reply)
            self.assertIn("on hold", reply)
            self.assertIn("raw-milk cheese recall", reply)
            self.assertIn("exact product/lot verification", reply)
            for leak in ("http", ".com", ".json", "photo-product", "storefront-mockup", "Supplied store photograph"):
                self.assertNotIn(leak, reply)
            self.assertEqual(voice.check(caught.exception.reply), [])
        held = next(p for p in content.products if p["id"] == "photo-product-040")
        held["hold"]["reason"] = "see https://example.test/x"  # a web address is never repeated: the generic sentence stands
        with self.assertRaises(it.Refusal) as caught:
            it.plan_restore({"items": ["photo-product-040"]}, ctx)
        self.assertIn("on hold", caught.exception.reply)
        self.assertNotIn("http", caught.exception.reply)
        self.assertNotIn("What was written down", caught.exception.reply)

    def test_rule_functions_are_pure_and_named(self):
        for rule_id, fn in it.RULE_FUNCTIONS.items():
            self.assertTrue(callable(fn) and fn.__doc__ and fn.__doc__.startswith(rule_id), rule_id)


class ImageMissing(unittest.TestCase):
    def test_a_missing_picture_stops_the_restore_when_the_site_folder_is_known(self):
        content = load_and_validate(CONTENT, SITE)
        pid = product_id(content, "Lemons")
        next(p for p in content.products if p["id"] == pid)["status"] = "hidden"
        self.assertEqual(it.plan_restore({"items": [pid]}, ctx_for(content)), [{"op": "product.restore", "args": {"id": pid}}])  # no folder: the editor checks
        if (SITE / "assets").exists():
            self.assertEqual(it.plan_restore({"items": [pid]}, ctx_for(content, site_dir=SITE)), [{"op": "product.restore", "args": {"id": pid}}])
        with tempfile.TemporaryDirectory() as empty, self.assertRaises(it.Refusal) as caught:
            it.plan_restore({"items": [pid]}, ctx_for(content, site_dir=empty))
        self.assertIn("picture is missing", caught.exception.reply)
        self.assertIn("Graham", caught.exception.reply)


class OwnerWords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = load_and_validate(CONTENT, SITE)

    def sentences(self):
        """Every owner-facing sentence the skills can produce, from real refusals plus the fixed texts."""
        out = [it.NO_ITEMS_HIDE, it.NO_ITEMS_RESTORE, it.NO_ITEM_EDIT, it.UNKNOWN_PRODUCT, it.UNKNOWN_MAKER, it.CANT_DO,
               it.NOT_DELETED, it.HIDDEN_NOT_DELETED, PRICE_REPLY]
        out += [reply for s in SKILLS.values() for _cond, reply in s.refuse]
        ctx = ctx_for(self.content)
        hidden = copy.deepcopy(self.content)
        for p in hidden.products:
            if p["id"] in ("photo-product-017", "photo-product-031"):
                p["status"] = "hidden"
        hidden.makers["Stardust Grove"]["hidden"] = True
        attempts = [
            (it.plan_hide, {"items": ["photo-product-040"]}, ctx), (it.plan_hide, {"items": ["photo-product-040", "photo-product-001"]}, ctx),
            (it.plan_hide, {"items": ["photo-product-017"]}, ctx_for(hidden)),
            (it.plan_hide, {"items": ["photo-product-017", "photo-product-001"]}, ctx_for(hidden)),
            (it.plan_hide, {"items": [p["id"] for p in self.content.products[:9]]}, ctx),
            (it.plan_hide, {"items": ["photo-product-001"], "reason": "forever"}, ctx),
            (it.plan_restore, {"items": ["photo-product-001"]}, ctx), (it.plan_restore, {"items": ["photo-product-040"]}, ctx),
            (it.plan_restore, {"items": ["photo-product-017", "photo-product-001"]}, ctx_for(hidden)),
            (it.plan_restore, {"items": ["photo-product-031"]}, ctx_for(hidden)),
            (it.plan_restore, {"items": ["photo-product-031", "photo-product-017"]}, ctx_for(hidden)),
            (it.plan_edit, {"item": "photo-product-001"}, ctx), (it.plan_edit, {"item": "photo-product-017", "name": "Oranges"}, ctx),
            (it.plan_edit, {"item": "photo-product-055", "category": "pantry"}, ctx),
            (it.plan_edit, {"item": "photo-product-040", "name": "X"}, ctx), (it.plan_edit, {"item": "photo-product-017", "name": "x" * 90}, ctx),
            (it.plan_edit, {"item": "photo-product-017", "category": "snacks"}, ctx), (it.plan_edit, {"item": "photo-product-017", "description": "<i>"}, ctx),
            (it.plan_edit, {"item": "photo-product-001", "maker": "Etto", "clear": ["clearProducer"]}, ctx),
            (it.plan_edit, {"item": "photo-product-001", "image_alt": "a", "clear": ["clearImageAlt"]}, ctx),
            (it.plan_edit, {"item": "photo-product-017", "name": "Lemons!"}, ctx_for(hidden)),
            (it.plan_edit, {"item": "photo-product-001", "maker": "Stardust Grove"}, ctx_for(hidden)),
        ]
        for fn, slots, c in attempts:
            try:
                fn(slots, c)
            except it.Refusal as exc:
                out.append(exc.reply)
        return out

    def test_every_sentence_follows_the_voice_rules_and_has_no_jargon(self):
        sentences = self.sentences()
        self.assertGreaterEqual(len(sentences), 30)
        for text in sentences:
            with self.subTest(voice.plain(text)[:60]):
                self.assertEqual(voice.check(text), [])
                self.assertEqual(plain_words_problems(voice.plain(text), allow=[p["name"] for p in self.content.products]), [])
                self.assertEqual(voice.claims_success(text), False)  # a refusal or a note never says "done"

    def test_every_refusal_is_honest_that_nothing_changed_or_asks_one_thing(self):
        for text in self.sentences():
            if text == it.HIDDEN_NOT_DELETED:
                continue  # a line beside a draft, not a refusal
            plain = voice.plain(text)
            with self.subTest(plain[:60]):
                self.assertTrue("Nothing changed" in plain or plain.count("?") == 1 or "haven't made any change" in plain
                                or "right now" in plain or "Tell me" in plain or "Bring" in plain or "Say" in plain, plain)
                self.assertLessEqual(plain.count("?"), 1)

    def test_the_extra_lines(self):
        ctx = ctx_for(self.content)
        self.assertEqual(it.notes(HIDE, {"items": ["photo-product-055"]}, ctx), {"say": [it.HIDDEN_NOT_DELETED], "set": [], "warn": []})
        self.assertEqual(it.notes(RESTORE, {"items": ["photo-product-055"]}, ctx), {"say": [], "set": [], "warn": []})
        said = it.notes(HIDE, {"items": ["photo-product-055"], "reason": "out of season"}, ctx)["say"]
        self.assertEqual([voice.plain(s) for s in said], [voice.plain(it.HIDDEN_NOT_DELETED),
                                                          "You told me why: out of season. I haven't saved that on the product."])
        for text in said:
            self.assertEqual(voice.check(text), [])
        lines = it.notes(EDIT, {"item": "photo-product-097", "maker": "Etto"}, ctx)
        self.assertEqual(voice.plain(lines["set"][0]), "I set: the maker line on the card to Etto.")
        self.assertEqual(it.notes(EDIT, {"item": "photo-product-097", "maker": "Etto", "display_brand": "Etto Pasta"}, ctx)["set"], [])
        self.assertEqual(voice.plain(it.notes(EDIT, {"item": "photo-product-031", "clear": ["clearProducer"]}, ctx)["set"][0]),
                         "I set: the maker line on the card to From the market.")
        for text in (it.HIDDEN_NOT_DELETED, *lines["set"]):
            self.assertEqual(voice.check(text), [])

    def test_description_advice_is_advice_only(self):
        good = "Creamy flesh, a little lime, enough salt. Mash it onto toast or cut it into a bowl of something bright and crunchy."
        self.assertEqual(it.advisory(good), [])
        self.assertEqual(len(it.advisory("Great stuff!")), 3)  # too short, no full stop, an exclamation mark
        self.assertEqual(len(it.advisory("A " * 100 + "end.")), 1)  # longer than the others
        for line in it.advisory("Great stuff?") + it.advisory("x" * 200):
            self.assertEqual(voice.check(line), [])
        ctx = ctx_for(self.content)
        warned = it.notes(EDIT, {"item": "photo-product-017", "description": "Great stuff!"}, ctx)["warn"]
        self.assertTrue(warned)
        it.plan_edit({"item": "photo-product-017", "description": "Great stuff!"}, ctx)  # a warning, never a refusal


class EditNotesFollowThePlan(unittest.TestCase):
    """RF2235-9: the 'I set:' and advice lines describe only what survives in the planned product.edit."""

    PESTO, FIGS = "photo-product-032", "photo-product-097"

    @classmethod
    def setUpClass(cls):
        cls.content = load_and_validate(CONTENT, SITE)

    def content_with(self, pid, **fields):
        content = copy.deepcopy(self.content)
        next(p for p in content.products if p["id"] == pid).update(fields)
        return content

    def notes(self, slots, content=None):
        return it.notes(EDIT, slots, ctx_for(content or self.content))

    def row(self, text, slots, expect, **more):
        base = {"id": "notes-row", "kind": "clean", "version": 1, "texts": [text],
                "replies": [{"skill": EDIT, "slots": slots}], "expect": {"skill": EDIT, "disposition": "proposed", **expect}}
        return {**base, **more}

    def test_same_maker_plus_shelf_has_no_default_note(self):
        slots = {"item": self.PESTO, "maker": "Stardust Grove", "category": "dairy"}  # the pesto is already Stardust Grove's
        self.assertEqual(self.notes(slots), {"say": [], "set": [], "warn": []})
        row = self.row("move the garlic pesto to dairy, it is Stardust Grove's", slots, {
            "ops": [{"op": "product.edit", "args": {"id": self.PESTO, "category": "dairy"}}],
            "diff": [{"file": "hass/content/products.json", "path": f"products[{self.PESTO}].category", "before": "pantry", "after": "dairy"}],
            "files": ["hass/content/products.json", "storefront-mockup/catalog-products.js"],
            "preview": {"kind": "product", "id": self.PESTO}, "reply_contains": "dairy", "reply_not_contains": ["I set:", "maker line"]})
        result = run_case_row(row, SKILLS, SKILLS[EDIT])
        self.assertEqual(result.problems, [])

    def test_unchanged_default_line_with_changed_maker_key_is_not_disclosed(self):
        content = self.content_with(self.PESTO, displayBrand="Etto")  # the line already reads Etto; the maker key is Stardust Grove
        slots = {"item": self.PESTO, "maker": "Etto"}
        [op] = it.plan_edit(slots, ctx_for(content))
        self.assertEqual(op["args"], {"id": self.PESTO, "brand": "Etto", "producerKey": "Etto"})
        self.assertEqual(self.notes(slots, content)["set"], [])

    def test_clear_producer_default_only_when_display_line_changes(self):
        clear = {"item": self.PESTO, "clear": ["clearProducer"]}
        [line] = self.notes(clear)["set"]
        self.assertEqual(voice.plain(line), "I set: the maker line on the card to From the market.")
        content = self.content_with(self.PESTO, displayBrand=it.UNKNOWN_SHOWN)  # already the fallback line: only the relation changes
        self.assertEqual(self.notes({**clear, "category": "dairy"}, content)["set"], [])

    def test_clear_producer_on_unlinked_product_still_discloses_a_changed_default(self):
        content = self.content_with(self.PESTO, producerKey=None, displayBrand="Grandma's pesto")  # no maker link left to clear
        clear = {"item": self.PESTO, "clear": ["clearProducer"]}
        [op] = it.plan_edit(clear, ctx_for(content))
        self.assertNotIn("clearProducer", op["args"])  # the plan dropped the already-true relation
        self.assertEqual(op["args"]["displayBrand"], it.UNKNOWN_SHOWN)  # but the custom line is still replaced
        [line] = self.notes(clear, content)["set"]
        self.assertEqual(voice.plain(line), "I set: the maker line on the card to From the market.")
        with_shelf = self.notes({**clear, "category": "dairy"}, content)["set"]
        self.assertEqual([voice.plain(x) for x in with_shelf], ["I set: the maker line on the card to From the market."])
        owner_line = self.notes({**clear, "display_brand": "Home made"}, content)["set"]  # the owner's own label: no default note
        self.assertEqual(owner_line, [])

    def test_unchanged_description_does_not_warn(self):
        saved = "Great stuff!"  # short, no full stop, an exclamation mark: every advisory would fire
        content = self.content_with(self.PESTO, description=saved)
        for repeated in (saved, "  Great   stuff! "):
            with self.subTest(repeated):
                self.assertEqual(self.notes({"item": self.PESTO, "description": repeated, "category": "dairy"}, content),
                                 {"say": [], "set": [], "warn": []})
        changed = self.notes({"item": self.PESTO, "description": "Okay stuff?"}, content)["warn"]
        self.assertEqual(changed, it.advisory("Okay stuff?"))
        self.assertEqual(len(changed), 3)
        self.assertEqual(self.notes({"item": self.PESTO, "description": "Great stuff!"}, self.content)["warn"], it.advisory("Great stuff!"))

    def test_real_default_and_explicit_label_controls(self):
        slots = {"item": self.FIGS, "maker": "Etto"}
        before = copy.deepcopy((slots, self.content.products))
        [line] = self.notes(slots)["set"]
        self.assertEqual(voice.plain(line), "I set: the maker line on the card to Etto.")
        self.assertEqual(self.notes({**slots, "display_brand": "Etto Pasta"})["set"], [])
        self.assertEqual(self.notes({**slots, "display_brand": "Etto Pasta", "category": "dairy"})["set"], [])
        self.assertTrue((slots, self.content.products) == before)
        bare = it.notes(EDIT, {"item": self.FIGS, "maker": "Etto"}, types.SimpleNamespace(today="2026-11-08"))  # no content: the plan is not reduced
        self.assertEqual(voice.plain(bare["set"][0]), "I set: the maker line on the card to Etto.")

    def test_refused_edit_has_no_notes(self):
        hidden = self.content_with("photo-product-055", status="hidden")
        refused = (
            ({"item": self.FIGS, "name": "Figs", "description": "Great stuff!"}, self.content_with(self.FIGS, description="Great stuff!")),  # nothing left
            ({"item": "photo-product-040", "maker": "Etto", "description": "Great stuff!"}, None),  # on hold
            ({"item": "photo-product-055", "maker": "Etto", "description": "Great stuff!"}, hidden),  # hidden
            ({"item": self.FIGS, "maker": "Etto", "clear": ["clearProducer"], "description": "Great stuff!"}, None),  # conflicting
            ({"item": "photo-product-999", "maker": "Etto", "description": "Great stuff!"}, None),  # missing
            ({"item": self.FIGS, "maker": "Etto", "description": "Two for five."}, None),  # a price
        )
        for slots, content in refused:
            with self.subTest(slots):
                with self.assertRaises(it.Refusal):
                    it.plan_edit(slots, ctx_for(content or self.content))
                self.assertEqual(self.notes(slots, content), {"say": [], "set": [], "warn": []})


class LiveClass(unittest.TestCase):
    """The class each skill declares is what the real live policy says about the plans it builds."""

    @classmethod
    def setUpClass(cls):
        cls.repo = WriterRepo()
        cls.state = str(cls.repo.state)
        cls.content = load_and_validate(CONTENT, SITE)

    @classmethod
    def tearDownClass(cls):
        cls.repo.cleanup()

    def reasons(self, ops):
        out = editor.prepare({"ops": ops}, state=self.state)
        self.assertEqual(out["result"], "ok", out)
        return live_policy.check(out["draft"]), out["draft"]

    def test_hide_and_restore_are_chat_live(self):
        reasons, draft = self.reasons(it.plan_hide({"items": ["photo-product-055", "photo-product-017"]}, ctx_for(self.content)))
        self.assertEqual(reasons, [])
        done = editor.apply(draft["change_id"], draft["draft_hash"], state=self.state)
        self.assertEqual(done["result"], "applied")
        hidden = load_and_validate(self.repo.wt / "hass" / "content", self.repo.wt / "storefront-mockup")
        reasons, _ = self.reasons(it.plan_restore({"items": ["photo-product-055"]}, ctx_for(hidden)))
        self.assertEqual(reasons, [])
        self.assertEqual(SKILLS[HIDE].live_class, SKILLS[RESTORE].live_class)
        self.assertEqual(SKILLS[HIDE].live_class, "chat-live")

    def test_edit_is_chat_live_for_description_shelf_and_private_only_for_a_name_or_a_maker(self):
        ctx = ctx_for(load_and_validate(self.repo.wt / "hass" / "content", self.repo.wt / "storefront-mockup"))
        reasons, _ = self.reasons(it.plan_edit({"item": "photo-product-032", "name": "Hass avocados"}, ctx))
        self.assertEqual(reasons, ["not live: product.edit.name"])  # G's list is description and category only
        for slots in ({"description": "Creamy flesh and a little lime."}, {"category": "dairy"}):
            reasons, _ = self.reasons(it.plan_edit({"item": "photo-product-032", **slots}, ctx))
            self.assertEqual(reasons, [], slots)
        for slots in ({"maker": "Etto"}, {"display_brand": "Somewhere nice"}, {"clear": ["clearProducer"]}):
            reasons, _ = self.reasons(it.plan_edit({"item": "photo-product-032", **slots}, ctx))
            self.assertTrue(any(r.startswith("protected field: products.") for r in reasons), (slots, reasons))
        self.assertEqual(SKILLS[EDIT].live_class, "private-only")  # the worst of the plans it can build


class KitAdditions(unittest.TestCase):
    """`setup` and `undo`, the two additions this card makes to the test kit."""

    def row(self, **more):
        base = {"id": "r", "kind": "clean", "version": 1, "texts": ["bring back the lemons"],
                "replies": [{"skill": RESTORE, "slots": {"items": ["photo-product-017"]}}],
                "expect": {"skill": RESTORE, "disposition": "proposed", "ops": [{"op": "product.restore", "args": {"id": "photo-product-017"}}],
                           "diff": [{"file": "hass/content/products.json", "path": "products[photo-product-017].status", "before": "hidden", "after": "active"}],
                           "files": ["hass/content/products.json", "storefront-mockup/catalog-products.js"], "preview": {"kind": "product"}}}
        return {**base, **more}

    def test_a_setup_gives_the_row_its_starting_state(self):
        good = self.row(setup=[{"op": "product.hide", "args": {"id": "photo-product-017"}}], undo=True)
        self.assertEqual(run_case_row(good, SKILLS, SKILLS[RESTORE]).problems, [])
        without = run_case_row(self.row(), SKILLS, SKILLS[RESTORE])  # nothing is hidden: the plan itself refuses
        self.assertEqual(without.codes, ["wrong-disposition", "wrong-disposition"])

    def test_a_bad_setup_is_a_bad_row_and_cleans_up(self):
        for setup in ("hide it", [], [{"op": "product.hide"}], [{"op": "product.hide", "args": {"id": "photo-product-999"}}]):
            with self.subTest(setup):
                self.assertEqual(run_case_row(self.row(setup=setup), SKILLS, SKILLS[RESTORE]).codes, ["bad-row"])

    def test_the_undo_marker_has_to_be_true_and_the_row_has_to_undo(self):
        self.assertEqual(run_case_row(self.row(undo=False), SKILLS, SKILLS[RESTORE]).codes, ["bad-row"])
        refusal = {"id": "r", "kind": "refuse", "version": 1, "texts": ["hide the raw milk white cheddar"], "undo": True,
                   "replies": [{"skill": HIDE, "slots": {"items": ["photo-product-040"]}}],
                   "expect": {"disposition": "unsupported", "reply_contains": "on hold"}}
        self.assertEqual(run_case_row(refusal, SKILLS, SKILLS[HIDE]).codes, ["wrong-turn"])
        del refusal["undo"]
        self.assertTrue(run_case_row(refusal, SKILLS, SKILLS[HIDE]).ok)

    def test_the_proposal_notes_are_shown_in_the_captured_reply_and_asserted(self):
        """The kit plays the notes contract: what notes() says is in the reply the row sees, so a row can pin it."""
        row = next(r for r in ROWS[HIDE] if r["id"] == "hide-15-with-reason")
        self.assertTrue(run_case_row(row, SKILLS, SKILLS[HIDE]).ok)
        for wrong in ("it is gone for ever", "a reason nobody gave"):
            bad = copy.deepcopy(row)
            bad["expect"]["reply_contains"] = [wrong]
            self.assertEqual(run_case_row(bad, SKILLS, SKILLS[HIDE]).codes, ["wrong-reply"], wrong)
        plain = copy.deepcopy(row)  # no reason slot: no reason line
        plain["replies"][0]["slots"].pop("reason")
        plain["expect"]["reply_contains"] = ["hidden, not deleted"]
        plain["expect"]["reply_not_contains"] = ["told me why"]
        self.assertTrue(run_case_row(plain, SKILLS, SKILLS[HIDE]).ok)


class FixtureFiles(unittest.TestCase):
    def test_the_files_are_where_the_skills_say_and_well_formed(self):
        for name, skill in SKILLS.items():
            path = REPO_ROOT / skill.cases
            self.assertTrue(path.is_file(), skill.cases)
            self.assertEqual(path.parent, FIXTURES / "items")
            for line in path.read_text("utf-8").splitlines():
                json.loads(line)
            ids = [r["id"] for r in ROWS[name]]
            self.assertEqual(len(ids), len(set(ids)))

    def test_the_doc_lists_every_sentence_and_rule(self):
        doc = (REPO_ROOT / "docs" / "hass" / "skills" / "items.md").read_text("utf-8")
        for skill in SKILLS.values():
            self.assertIn(f"`{skill.name}`", doc)
            for trigger in skill.triggers:
                self.assertIn(trigger.text, doc, trigger.text)
            for rule in skill.rules:
                self.assertIn(f"`{rule}`", doc, rule)
        self.assertEqual(testkit.MAX_OPS, 20)


if __name__ == "__main__":
    unittest.main()
