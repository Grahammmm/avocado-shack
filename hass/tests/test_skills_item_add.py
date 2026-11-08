"""SKILLS-ITEMADD-1: the item.add skill (add a new item end to end; reports/hass/SKILLS-SPEC.md 3.1, card 14).

Proves, against the real content: the lint and the case file, the live boundary class, the plain words of every owner
sentence (docs/hass/VOICE.md), the drafted defaults (derive: functions), the order of the questions, D2 (today's shelf
check on its own line), D5 (the maker note), D9 (price and size left off), "same as last time", a hidden maker, a twin
and the picture advice. The case rows themselves run through the real Conversation and Editor in test_skills_cases.
Run: python3 -B -m unittest hass.tests.test_skills_item_add -v
"""
import copy
import unittest
from types import SimpleNamespace

from hass import live_policy, skills, voice
from hass.content_model import REPO_ROOT, load_and_validate
from hass.ops import load_registry
from hass.skills import item_add as ia
from hass.skills import testkit
from hass.skills.model import lint_plan_output

CONTENT = load_and_validate(REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup")
SYN = REPO_ROOT / "reports" / "hass" / "newitem-1" / "synthetic"
SHA = "2cec1911a59002428a1c22e1a9dd1f9226243e49829bfed452aafd7773446bf3"  # jar-white-sheet.jpg
FULL = {"name": "Wildflower honey", "form": "packaged", "maker": "Bee Happy Farm", "place": "Atascadero, California",
        "shelf": "pantry", "description": "Wildflower honey from Bee Happy Farm in Atascadero. Spoon a little onto buttered toast.",
        "image_alt": "Wildflower honey in a jar", "availability": "yes", "photo": SHA}


def ctx(*texts, content=CONTENT, **extra):
    return SimpleNamespace(today="2026-11-08", content=content, texts=list(texts), **extra)


def refusal(slots, *texts, **extra):
    with unittest.TestCase().assertRaises(ia.Refusal) as caught:
        ia.describe_add(slots, ctx(*texts, **extra))
    return caught.exception


def with_last(key, form_shelf="vegetables"):
    """A copy of the content whose last added product is from ``key``."""
    content = copy.deepcopy(CONTENT)
    content.products.append({"id": "photo-product-175", "name": "Test peaches", "brand": key, "category": form_shelf,
                             "producerKey": key, "status": "active"})
    return content


class Declaration(unittest.TestCase):
    def test_registered_and_the_lint_and_case_file_are_clean(self):
        self.assertIs(skills.load_skills().get("item.add"), ia.ITEM_ADD)
        ops = load_registry()
        self.assertEqual(skills.skill_lint([ia.ITEM_ADD], ops, repo_root=REPO_ROOT), [])
        golden = ia.plan_add(dict(FULL), SimpleNamespace(today="2026-11-08", next_product_id="photo-product-175"))
        self.assertEqual(lint_plan_output(ia.ITEM_ADD, golden, ops), [])

    def test_live_class_matches_the_live_boundary(self):
        """private-only: brand, displayBrand and producerKey are protected, so live_policy stops a live release (D4)."""
        scratch = testkit.Scratch({}, {"item.add": ia.ITEM_ADD}, photos=["reports/hass/newitem-1/synthetic/jar-white-sheet.jpg"])
        try:
            plan = ia.plan_add({"name": "Cal Poly honey", "maker": "Cal Poly", "availability": "yes", "photo": SHA}, scratch._ctx())
            out = scratch.editor.prepare(plan)
            self.assertEqual(out["result"], "ok", out)
            self.assertTrue(live_policy.check(out["draft"]))
        finally:
            scratch.close()
        self.assertEqual(ia.ITEM_ADD.live_class, "private-only")

    def test_every_owner_sentence_passes_the_voice_rules(self):
        fixed = list(ia.ASK.values()) + [ia.ONE_PHOTO, ia.NO_LAST_FARM, ia.STORE_LINE, ia.NO_BYTES, ia.RETAKE_BUSY,
                                         ia.RETAKE_SMALL, ia.RETAKE_OTHER, ia.AS_TAKEN, ia.PICTURE_OK, ia.SHORT_DESC, ia.MANY_ITEMS]
        fixed += [reply.replace("<Product>", "Cal Poly honey").replace("<Maker>", "Etto") for _why, reply in ia.ITEM_ADD.refuse]
        asked = [ia.question(s, {"name": "Tomatoes", "form": "fresh", "maker": "Smith Farm"}, ctx()) for s in ia.ASK]
        for text in fixed + asked:
            with self.subTest(text=text):
                self.assertEqual(voice.check(voice.plain(text)), [])
                self.assertLessEqual(text.count("?"), 1, "one question at a time")


class DraftedDefaults(unittest.TestCase):
    def test_form_from_his_words_the_shelf_or_asked(self):
        self.assertEqual(ia.form_guess({"name": "Honey"}, ctx("new honey in a jar")), "packaged")
        self.assertEqual(ia.form_guess({"name": "Tomatoes"}, ctx("fresh tomatoes today")), "fresh")
        self.assertEqual(ia.form_guess({"name": "Roast Bros coffee", "shelf": "drinks"}, ctx("it goes with drinks")), "packaged")
        self.assertIsNone(ia.form_guess({"name": "Lemon curd"}, ctx("add lemon curd")))

    def test_shelf_he_named_else_the_shelf_of_the_same_kind_else_asked(self):
        self.assertEqual(ia.same_kind_majority({"name": "Honey"}, ctx("new honey")), "pantry")
        self.assertEqual(ia.same_kind_majority({"name": "Heirloom tomatoes"}, ctx("tomatoes")), "vegetables")
        self.assertIsNone(ia.same_kind_majority({"name": "Lemon curd"}, ctx("lemon curd")))
        with self.assertRaises(ia.Refusal) as caught:
            ia.describe_add({**FULL, "name": "Lemon curd", "shelf": None, "maker": "Linn's"}, ctx("lemon curd from Linn's"))
        self.assertTrue(caught.exception.reply.startswith("Which shelf does it go on:"))

    def test_town_of_a_saved_maker_none_for_a_new_one(self):
        self.assertEqual(ia.saved_place({"maker": "Cal Poly"}, ctx()), "San Luis Obispo, California")
        self.assertEqual(ia.saved_place({"maker": "don't know"}, ctx()), ia.NOT_NEEDED)
        self.assertIsNone(ia.saved_place({"maker": "Bee Happy Farm"}, ctx()))

    def test_description_is_machine_valid_and_names_maker_and_town(self):
        text = ia.house_description({"name": "Cal Poly honey", "maker": "Cal Poly"}, ctx("new honey from Cal Poly"))
        self.assertIn("Cal Poly in San Luis Obispo", text)
        self.assertFalse(any(c.isdigit() for c in text) or "$" in text or "!" in text)

    def test_caption_is_the_name_plus_the_container_only_when_said(self):
        self.assertEqual(ia.alt_text({"name": "Cal Poly honey"}, ctx("Cal Poly honey 8oz jar")), "Cal Poly honey in a jar")
        self.assertEqual(ia.alt_text({"name": "Cal Poly honey"}, ctx("new honey from Cal Poly")), "Cal Poly honey")


class Questions(unittest.TestCase):
    def test_the_order_is_name_form_maker_town_stock_photo(self):
        steps = [({}, "What is it called?"), ({"name": "Lemon curd"}, "Is it packaged or fresh?"),
                 ({"name": "Lemon curd", "form": "packaged"}, "Who makes this lemon curd?"),
                 ({"name": "Lemon curd", "form": "packaged", "maker": "Smith Farm", "shelf": "pantry"},
                  "Where is Smith Farm based (town and state)?"),
                 ({"name": "Lemon curd", "form": "packaged", "maker": "Linn's", "shelf": "pantry"}, "Is it in stock right now?"),
                 ({"name": "Lemon curd", "form": "packaged", "maker": "Linn's", "shelf": "pantry", "availability": "yes"},
                  "Send a photo of it.")]
        for slots, want in steps:
            with self.subTest(want=want):
                got = refusal(slots)
                self.assertEqual((voice.plain(got.reply).split(" (Say")[0], got.kind), (want, "question"))

    def test_the_farm_question_offers_same_as_last_time(self):
        content = with_last("Fair Hills Farm")
        asked = voice.plain(ia.question("maker", {"name": "Tomatoes", "form": "fresh"}, ctx(content=content)))
        self.assertEqual(asked, "Who grew these tomatoes? (Say \u201csame\u201d for Fair Hills Farm, the farm from last time.)")
        packaged = voice.plain(ia.question("maker", {"name": "Lemon curd", "form": "packaged"}, ctx()))
        self.assertTrue(packaged.endswith("(Say \u201csame\u201d for Etto, the maker from last time.)"), packaged)

    def test_same_uses_the_maker_of_the_last_product_added(self):
        content = with_last("Fair Hills Farm")
        done = ia.describe_add({**FULL, "name": "Heirloom tomatoes", "form": "fresh", "maker": "same farm as last time",
                                "shelf": "vegetables"}, ctx("same farm as last time", content=content))
        add = next(op for op in done.ops if op["op"] == "product.add")["args"]
        self.assertEqual((add["producerKey"], add["brand"]), ("Fair Hills Farm", "Fair Hills Farm"))
        self.assertIn("the maker to Fair Hills Farm, the same as last time", [voice.plain(s) for s in done.set_lines])
        self.assertNotIn("maker.add", [op["op"] for op in done.ops])

    def test_same_with_no_saved_maker_asks(self):
        content = copy.deepcopy(CONTENT)
        content.products = [p for p in content.products if not p["id"].startswith("photo-product-")]
        self.assertEqual(refusal({**FULL, "maker": "same"}, content=content).reply, ia.NO_LAST_FARM)


class Plan(unittest.TestCase):
    def test_new_maker_product_and_todays_shelf_check_on_its_own_line(self):
        done = ia.describe_add(dict(FULL), ctx("new wildflower honey from Bee Happy Farm in Atascadero, its in"))
        self.assertEqual([op["op"] for op in done.ops], ["maker.add", "product.add", "store.confirm_selection"])
        self.assertEqual(done.ops[0]["args"]["story"], "Bee Happy Farm is based in Atascadero, California.")  # D5
        self.assertEqual(done.ops[2]["args"], {"yes": ["photo-product-175"]})
        self.assertIn(ia.STORE_LINE, done.say)  # D2

    def test_check_already_recorded_today_sets_only_the_word(self):
        content = copy.deepcopy(CONTENT)
        content.store["selection_checked_on"] = "2026-11-08"
        done = ia.describe_add({**FULL, "availability": "no"}, ctx(content=content))
        self.assertEqual(done.ops[-1], {"op": "product.set_availability", "args": {"id": "photo-product-175", "available": "no"}})
        self.assertNotIn(ia.STORE_LINE, done.say)

    def test_price_and_size_are_left_off_never_written(self):
        done = ia.describe_add({**FULL, "name": "Cal Poly honey 8oz", "maker": "Cal Poly", "image_alt": None},
                               ctx("Cal Poly honey 8oz jar $9 just got in"))
        add = next(op for op in done.ops if op["op"] == "product.add")["args"]
        self.assertEqual(add["name"], "Cal Poly honey")
        self.assertFalse(any("$" in str(v) or "8oz" in str(v) for v in add.values()))
        self.assertEqual(done.left_off, ("the price ($9) and the size (8oz), because the website shows no prices or sizes",))

    def test_unknown_maker_has_no_maker_record(self):
        done = ia.describe_add({**FULL, "maker": "dont know"}, ctx("new jam, dont know who makes it"))
        add = done.ops[0]["args"]
        self.assertEqual((done.ops[0]["op"], add["brand"], "producerKey" in add), ("product.add", ia.UNKNOWN_BRAND, False))

    def test_hidden_maker_is_asked_about_not_used(self):
        content = copy.deepcopy(CONTENT)
        content.makers["Linn's"]["hidden"] = True
        got = refusal({**FULL, "maker": "Linn's"}, content=content)
        self.assertEqual((voice.plain(got.reply), got.kind), ("Linn's is hidden. Do you want me to bring them back first?", "question"))

    def test_a_twin_is_named_before_anything_else_is_asked(self):
        got = refusal({"name": "Rigatoni pasta", "maker": "Etto", "photo": SHA}, "Etto's new rigatoni")
        self.assertEqual(voice.plain(got.reply), "Rigatoni pasta is already on the site. Do you want to change it instead?")

    def test_the_plan_is_pure_and_keeps_the_slots(self):
        slots = {"name": "Cal Poly honey", "maker": "Cal Poly", "availability": "yes", "photo": SHA}
        given = dict(slots)
        first = ia.plan_add(given, ctx("new honey from Cal Poly, it's in"))
        self.assertEqual(given, slots)
        self.assertEqual(ia.plan_add(dict(slots), ctx("new honey from Cal Poly, it's in")), first)


class Picture(unittest.TestCase):
    def test_flag_off_a_photo_that_misses_the_house_look_gets_the_kind_advice(self):
        say, warn = ia.picture_review((SYN / "bag-red-cloth.jpg").read_bytes(), False)
        self.assertEqual((say, warn), ((), (ia.AS_TAKEN,)))

    def test_bytes_that_are_not_a_photo_are_one_plain_sentence(self):
        say, warn = ia.picture_review(b"not a photo", False)
        self.assertEqual(say, ())
        self.assertEqual(len(warn), 1)
        self.assertEqual(voice.check(warn[0]), [])

    def test_notes_show_the_lines_beside_the_draft(self):
        got = ia.notes("item.add", {**FULL, "name": "Cal Poly honey 8oz", "maker": "Cal Poly"}, ctx("Cal Poly honey 8oz $9"))
        self.assertIn(ia.STORE_LINE, got["say"])
        self.assertTrue(any(line.startswith("Left off: the price ($9)") for line in got["warn"]))
        self.assertEqual(ia.notes("item.add", {}, ctx()), {})


if __name__ == "__main__":
    unittest.main()
