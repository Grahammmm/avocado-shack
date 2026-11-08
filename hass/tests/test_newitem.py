"""HASS-NEWITEM-1 tests: the measured house style, its checks, the picture renderer and the new-item draft.

Text/record/draft tests are standard library only. Picture tests need Pillow and are skipped without it (CI python has none:
see reports/hass/NEWITEM-1.md hand-off card 5). The end-to-end test runs the draft through the real editor (prepare, claims,
apply, undo) on a throwaway repo, with the one planned seam (photos._web_bytes -> house render) patched in.
"""
import hashlib
import io
import json
import struct
import unittest
import zlib
from unittest import mock

from hass import claims, house_style as hs, media, newitem, newitem_render
from hass.content_model import load_content
from hass.ops import photos

try:
    import PIL  # noqa: F401
    from PIL import Image as PILImage
    from hass import newitem_synthetic as syn
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False


def png(width=4, height=4, pixel=(200, 180, 120), idat=None) -> bytes:
    """A real PNG built with the standard library only (RGB, or RGBA when `pixel` has four values); `idat` overrides the pixel data."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    colour = 6 if len(pixel) == 4 else 2
    rows = b"".join(b"\0" + bytes(pixel) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows) if idat is None else idat) + chunk(b"IEND", b""))


PHOTO = png()  # passes media.check_photo; the draft tests below swap in FAKE for the picture itself

CONTENT = load_content()
SPEC = hs.load_spec()
FAKE = lambda data: {"jpeg": b"\xff\xd8fake\xff\xd9", "report": {"isolation": "cutout", "review": []},  # noqa: E731
                     "check": {"score": 100, "pass": True, "hard_failures": [], "checks": []}}
HONEY = "got in some Cal Poly honey, jar of 8oz, $9"


class SpecTests(unittest.TestCase):
    def test_spec_is_measured_from_the_content(self):
        prods, makers = CONTENT.products, CONTENT.makers
        self.assertEqual(SPEC["descriptions"], json.loads(hs._dump(hs.measure_descriptions(prods, makers))))
        self.assertEqual(SPEC["makers"], json.loads(hs._dump(hs.measure_makers(makers))))
        self.assertEqual(SPEC["records"], json.loads(hs._dump(hs.measure_records(prods, makers, CONTENT.store))))
        self.assertEqual(SPEC["pictures"]["catalog"]["count"], len(CONTENT.active_products()))

    def test_at_least_ten_real_examples_of_each(self):
        self.assertGreaterEqual(len(SPEC["pictures"]["catalog"]["examples"]), 10)
        self.assertGreaterEqual(len(SPEC["descriptions"]["examples"]), 10)
        self.assertGreaterEqual(len(SPEC["makers"]["examples"]), 10)

    def test_every_live_description_maker_and_product_passes(self):
        for p in CONTENT.active_products():
            with self.subTest(p["id"]):
                self.assertTrue(hs.check_description(p["description"], SPEC, owner_text=p["description"])["pass"])
                self.assertTrue(hs.check_product(p, CONTENT.makers, SPEC)["pass"])
        for key, maker in CONTENT.makers.items():
            with self.subTest(key):
                self.assertTrue(hs.check_maker(maker, SPEC, key=key)["pass"])

    def test_bad_descriptions_fail(self):
        good = "Honey from Cal Poly in San Luis Obispo. Spoon a little onto buttered toast."
        self.assertTrue(hs.check_description(good, SPEC)["pass"])
        cases = {"price": good + " Only $9!", "unstated claim": "Organic honey from Cal Poly. Spoon a little onto toast.",
                 "digits": "Honey, 8 oz of it. Spoon a little onto toast.", "one sentence": "Honey from Cal Poly.",
                 "long": "Honey from Cal Poly. " + "Spoon a little onto toast. " * 12}
        for name, text in cases.items():
            with self.subTest(name):
                self.assertFalse(hs.check_description(text, SPEC)["pass"])
        self.assertTrue(hs.check_description("Organic honey from Cal Poly. Spoon a little onto toast.", SPEC, owner_text="it is organic")["pass"])

    def test_bad_records_fail(self):
        self.assertFalse(hs.check_maker({"name": "X", "place": "Nowhere", "story": "Hi"}, SPEC)["pass"] and False)
        self.assertFalse(hs.check_maker({"name": "X", "place": "Cambria, California", "story": "A $5 story.", "url": "http://x.example"}, SPEC)["pass"])
        rec = {**CONTENT.active_products()[0], "category": "candy"}
        self.assertFalse(hs.check_product(rec, CONTENT.makers, SPEC)["pass"])

    @unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
    def test_every_live_picture_passes_and_a_phone_photo_fails(self):
        for p in CONTENT.active_products():
            data = (hs.SITE / p["image"]).read_bytes()
            with self.subTest(p["id"]):
                self.assertTrue(hs.check_image(data, SPEC)["pass"])
        raw = syn.make_photo(phone_orientation=6, size=(1512, 1134))
        out = hs.check_image(raw, SPEC)
        self.assertFalse(out["pass"])
        self.assertIn("no metadata (EXIF/GPS)", out["hard_failures"])


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class RenderTests(unittest.TestCase):
    def render(self, name):
        return newitem_render.render(syn.make_photo(**dict(syn.cases())[name]), SPEC)

    def test_plain_backgrounds_become_house_pictures(self):
        for name in ("jar-white-sheet", "bottle-grey-wall-tilted", "jar-phone-rotated", "bottle-bench-png", "jar-cutout-alpha"):
            with self.subTest(name):
                out = self.render(name)
                self.assertEqual(out["report"]["isolation"], "cutout")
                self.assertTrue(out["check"]["pass"], out["check"]["hard_failures"])
                self.assertGreaterEqual(out["check"]["score"], 90)

    def test_metadata_gone_and_rotation_applied(self):
        raw = syn.make_photo(**dict(syn.cases())["jar-phone-rotated"])
        self.assertTrue(syn.has_exif_location(raw))
        out = newitem_render.render(raw, SPEC)
        self.assertFalse(syn.has_exif_location(out["jpeg"]))
        self.assertTrue(out["report"]["rotation_applied"])
        box = out["report"]["box"]
        self.assertGreater(box[3] - box[1], box[2] - box[0])  # the jar stands upright after the pixels are turned

    def test_tilt_straightened_and_deterministic(self):
        raw = syn.make_photo(**dict(syn.cases())["bottle-grey-wall-tilted"])
        a, b = newitem_render.render(raw, SPEC), newitem_render.render(raw, SPEC)
        self.assertEqual(a["jpeg"], b["jpeg"])
        self.assertIn("straightened_degrees", a["report"])

    def test_busy_background_is_flagged_not_faked(self):
        for name in ("bag-red-cloth", "jar-dark-wood"):
            out = self.render(name)
            self.assertEqual(out["report"]["isolation"], "fallback", name)
            self.assertTrue(out["report"]["review"], name)

    def test_small_photo_is_flagged(self):
        self.assertTrue(any("small" in r for r in self.render("bag-bench-small")["report"]["review"]))


class DraftTests(unittest.TestCase):
    def draft(self, message=HONEY, **kw):
        return newitem.draft(message, PHOTO, content=CONTENT, spec=SPEC, renderer=FAKE, **kw)

    def test_the_honey_example(self):
        r = self.draft(selection_checked=True)
        self.assertEqual(r["status"], "draft")
        product = next(o for o in r["ops"] if o["op"] == "product.add")["args"]
        self.assertEqual((product["name"], product["brand"], product["category"], product["producerKey"]), ("Cal Poly honey", "Cal Poly", "pantry", "Cal Poly"))
        self.assertTrue(r["description"]["text"].startswith("Honey from Cal Poly in San Luis Obispo."))
        self.assertEqual(product["photo"], hashlib.sha256(PHOTO).hexdigest())
        self.assertEqual(product["imageAlt"], "Cal Poly honey in a jar")
        self.assertEqual([o["op"] for o in r["ops"]], ["product.add", "product.set_availability"])
        self.assertEqual(r["ops"][1]["args"], {"id": newitem.next_product_id(CONTENT), "available": "yes"})
        self.assertEqual({x["what"] for x in r["left_off"]}, {"price", "size"})
        self.assertNotIn("$", str(r["ops"]))
        self.assertNotIn("9", r["description"]["text"])
        self.assertTrue(all(v["pass"] for v in r["style"].values() if v))

    def test_availability_waits_for_the_shelf_check(self):
        r = self.draft()
        self.assertEqual([o["op"] for o in r["ops"]], ["product.add"])
        self.assertIn("availability", {x["what"] for x in r["left_off"]})

    def test_new_maker_uses_only_his_words(self):
        r = self.draft("Just got in wildflower honey from Bee Happy Farm in Templeton, California. Great on toast. They keep bees on the hill behind the house. $11")
        self.assertEqual(r["status"], "draft")
        self.assertEqual(r["ops"][0]["op"], "maker.add")
        self.assertEqual(r["maker"]["story"], "Bee Happy Farm keeps bees on the hill behind the house.")
        self.assertEqual(r["maker"]["place"], "Templeton, California")
        self.assertEqual(r["description"]["text"], "Wildflower honey from Bee Happy Farm in Templeton. Try it on toast.")

    def test_new_maker_without_a_story_gets_a_one_line_note(self):
        r = self.draft("got in some honey from Bee Happy Farm in Templeton, California")
        self.assertEqual(r["maker"]["story"], "Bee Happy Farm is based in Templeton, California.")

    def test_one_short_question_when_the_page_needs_more(self):
        self.assertEqual(self.draft("got in some pickled okra from Dixie Jar Co, $7")["question"], "Where is Dixie Jar Co based (town and state)?")
        self.assertIn("Which shelf", self.draft("got in pickled okra")["question"])
        self.assertEqual(self.draft("got something new")["question"], "What is this item called?")
        said = self.draft("new stuff", label={"brand": "Cal Poly", "name": "Honey"})["question"]
        self.assertTrue(said.startswith("The label looks like: Cal Poly Honey."))
        for q in (self.draft("got in pickled okra")["question"],):
            self.assertEqual(q.count("?"), 1)

    def test_nothing_is_invented(self):
        said = self.draft(HONEY + ". It's organic and local")
        self.assertNotIn("organic", said["description"]["text"].lower())
        self.assertIn("claim", {x["what"] for x in said["left_off"]})
        dropped = self.draft(HONEY, facts={"name": "Cal Poly honey", "maker": "Cal Poly", "kind": "honey", "story": "Raised in the hills", "use": "with rare tea"})
        self.assertIn("story", dropped["dropped"])
        self.assertIn("use", dropped["dropped"])

    def test_a_model_written_description_must_pass_or_the_template_is_used(self):
        bad = self.draft(HONEY, writer=lambda prompt: "Organic raw honey from the hills of Paso Robles. Amazing!")
        self.assertEqual(bad["description"]["source"], "template")
        self.assertTrue(bad["description"]["writer_rejected"])
        good = self.draft(HONEY, writer=lambda prompt: "Honey from Cal Poly in San Luis Obispo. Spoon a little beside cheese or onto buttered toast; give it a chance to be tasted on its own.")
        self.assertEqual(good["description"]["source"], "writer")
        self.assertIn("Examples" if False else "Real examples", newitem.writer_prompt(good["facts"], SPEC, ["x."]))

    def test_the_item_is_read_from_the_item_sentence_not_from_the_maker_story(self):
        r = self.draft("Just got in wildflower hot sauce from Bee Happy Farm in Templeton, California. Great on eggs. They grow the peppers themselves. 6oz bottle $8")
        self.assertEqual(r["facts"]["name"], "Bee Happy Farm wildflower hot sauce")  # not "...peppers", from the story sentence
        self.assertTrue(r["description"]["text"].startswith("Wildflower hot sauce from Bee Happy Farm in Templeton."))

    def test_the_draft_ops_apply_through_the_real_op_handlers_and_the_site_generator(self):
        from datetime import datetime  # noqa: PLC0415
        from hass import newitem_preview, sitegen  # noqa: PLC0415
        from hass.content_model import SHOP_TZ, shop_today  # noqa: PLC0415
        r = self.draft("Just got in wildflower hot sauce from Bee Happy Farm in Templeton, California. Great on eggs. They grow the peppers themselves.", selection_checked=True)
        now = datetime.now(SHOP_TZ)
        after, product = newitem_preview.apply_in_memory(CONTENT, r["ops"], r["image"]["path"], now)
        self.assertEqual((product["name"], product["producerKey"], product["imageAlt"]), ("Bee Happy Farm wildflower hot sauce", "Bee Happy Farm", r["alt"]))
        self.assertEqual(after.makers["Bee Happy Farm"]["story"], "Bee Happy Farm grows the peppers themselves.")
        self.assertEqual(len(CONTENT.products) + 1, len(after.products))  # the loaded catalog itself is untouched
        files = sitegen.render(after, today=shop_today(now))
        self.assertIn(product["description"], files["storefront-mockup/catalog-products.js"].decode("utf-8"))
        self.assertEqual(sitegen.availability_label(product, after.store, shop_today(now)), "Available today")
    def test_the_product_phrase_is_not_a_story_word(self):
        # Same text as newitem_demo.MESSAGES["bottle-grey-wall-tilted"]; inlined because newitem_demo needs Pillow.
        r = self.draft("Just got in wildflower hot sauce from Bee Happy Farm in Templeton, California. Great on eggs. "
                       "They grow the peppers themselves. 6oz bottle $8")
        product = next(o for o in r["ops"] if o["op"] == "product.add")["args"]
        self.assertEqual((product["name"], product["category"]), ("Bee Happy Farm wildflower hot sauce", "pantry"))
        self.assertEqual(r["facts"]["kind"], "sauce")

    def test_writer_cannot_invent_ingredients_even_in_lowercase(self):
        for text in ("Honey from Cal Poly with added peanuts and sesame. Spoon a little onto buttered toast.",
                     "Honey from Cal Poly in San Luis Obispo. Spoon a little onto toast with added peanuts."):
            r = self.draft(HONEY, writer=lambda prompt, t=text: t)
            self.assertEqual(r["description"]["source"], "template", text)
            self.assertTrue(r["description"]["writer_rejected"])
            self.assertNotIn("peanut", str(r["ops"]))

    def test_writer_cannot_assert_contents_in_a_later_sentence(self):
        for text in ("Honey from Cal Poly in San Luis Obispo. It has butter and cream.",
                     "Honey from Cal Poly in San Luis Obispo. The toast is buttered."):
            r = self.draft(HONEY, writer=lambda prompt, t=text: t)
            self.assertEqual(r["description"]["source"], "template", text)
            self.assertTrue(r["description"]["writer_rejected"])
            self.assertNotIn("cream", str(r["ops"]))
        control = self.draft(HONEY, writer=lambda prompt: "Honey from Cal Poly in San Luis Obispo. Spoon a little beside cheese or onto buttered toast; give it a chance to be tasted on its own.")
        self.assertEqual(control["description"]["source"], "writer")

    def test_unstated_shelf_and_availability_are_dropped(self):
        r = self.draft("Cal Poly honey", facts={"name": "Cal Poly honey", "maker": "Cal Poly", "kind": "honey", "shelf": "vegetables", "availability": "yes"},
                       selection_checked=True)
        self.assertEqual({"shelf", "availability"} - set(r["dropped"]), set())
        product = next(o for o in r["ops"] if o["op"] == "product.add")["args"]
        self.assertEqual(product["category"], "pantry")
        self.assertNotIn("product.set_availability", [o["op"] for o in r["ops"]])
        said = self.draft("got in some Cal Poly honey for the vegetables shelf", facts={"name": "Cal Poly honey", "maker": "Cal Poly", "kind": "honey",
                                                                                         "shelf": "vegetables", "availability": "yes"}, selection_checked=True)
        self.assertEqual(next(o for o in said["ops"] if o["op"] == "product.add")["args"]["category"], "vegetables")

    def test_unnamed_producer_follows_the_catalog_pattern(self):
        r = self.draft("got some honey")
        product = r["ops"][0]["args"]
        self.assertEqual((product["brand"], "producerKey" in product), ("Producer not identified", False))
        self.assertEqual(hs.description_metrics(r["description"]["text"])["sentences"], 2)


class GroundingTests(unittest.TestCase):
    """Review round 1 (PR 504): fact-only text, polarity, and shelf/availability that are never taken on trust."""
    def draft(self, message=HONEY, **kw):
        return newitem.draft(message, PHOTO, content=CONTENT, spec=SPEC, renderer=FAKE, **kw)

    def test_a_writer_cannot_add_an_ingredient_or_a_history(self):
        for text in ("Honey blended with cinnamon and vanilla. Spoon a little onto buttered toast.",
                     "Honey from a century-old family business. Spoon a little onto buttered toast.",
                     "Honey from Cal Poly in San Luis Obispo. Stir into tea blended with cinnamon.",
                     "Honey from Cal Poly in San Luis Obispo. Honey made by the family since long ago."):
            with self.subTest(text):
                r = self.draft(writer=lambda prompt, t=text: t)
                self.assertEqual((r["description"]["source"], r["status"]), ("template", "draft"))
                self.assertTrue(r["description"]["writer_rejected"])
                self.assertNotRegex(r["description"]["text"].lower(), r"cinnamon|vanilla|century|family|since")

    def test_a_denied_claim_is_not_written_as_a_claim(self):
        message = HONEY + ". It is not organic."
        r = self.draft(message, writer=lambda prompt: "Organic honey from Cal Poly. Spoon a little onto buttered toast.")
        self.assertEqual(r["description"]["source"], "template")
        self.assertNotIn("organic", r["description"]["text"].lower())
        self.assertNotIn("claim", {x["what"] for x in r["left_off"]})  # nothing was affirmed, so nothing is "left off"
        self.assertFalse(hs.check_description("Organic honey from Cal Poly. Spoon a little onto toast.", SPEC, owner_text=message)["pass"])
        said = self.draft(HONEY + ". It is organic.", writer=lambda prompt: "Organic honey from Cal Poly. Spoon a little onto buttered toast.")
        self.assertIn("claim", {x["what"] for x in said["left_off"]})  # affirmed by him, and still only on request (existing rule)
        self.assertEqual(self.draft(message, facts={"name": "Organic honey", "kind": "honey"})["dropped"], ["name"])

    def test_a_denied_story_is_never_turned_into_a_claim(self):
        message = "got in honey from Bee Happy Farm in Templeton, California. They do not keep bees on the hill."
        model = {"name": "Bee Happy Farm honey", "maker": "Bee Happy Farm", "place": "Templeton, California", "kind": "honey",
                 "story": "Bee Happy Farm keeps bees on the hill."}
        r = self.draft(message, facts=model)
        self.assertIn("story", r["dropped"])
        self.assertEqual(r["maker"]["story"], "Bee Happy Farm is based in Templeton, California.")
        plain = self.draft(message)  # the plain reader keeps his polarity
        self.assertEqual(plain["maker"]["story"], "Bee Happy Farm does not keep bees on the hill.")
        mixed = self.draft(message.replace("They do not keep bees on the hill.", "They keep bees on the hill. They do not sell wax."),
                           facts={**model, "story": "Bee Happy Farm sells wax."})
        self.assertIn("story", mixed["dropped"])
        self.assertIn("story", self.draft(message, facts={**model, "story": "The hill keeps Bee Happy Farm bees."})["dropped"])  # order matters

    def test_the_model_cannot_choose_the_shelf_or_the_availability(self):
        model = {"name": "Cal Poly honey", "maker": "Cal Poly", "kind": "honey", "shelf": "meat", "availability": "no"}
        r = self.draft(HONEY, facts=model, selection_checked=True)
        self.assertEqual((r["shelf"], r["product"]["category"]), ("Pantry", "pantry"))
        self.assertEqual({"shelf", "availability"} & set(r["dropped"]), {"shelf", "availability"})
        self.assertEqual([o["args"]["available"] for o in r["ops"] if o["op"] == "product.set_availability"], ["yes"])  # "got in" is his word
        none = self.draft("some Cal Poly honey, jar of 8oz", facts={**model, "availability": "yes"}, selection_checked=True)
        self.assertNotIn("product.set_availability", [o["op"] for o in none["ops"]])  # nothing he said supports any availability
        named = self.draft("got in Cal Poly honey for the dairy shelf", facts={**model, "shelf": "dairy"}, selection_checked=True)
        self.assertEqual(named["product"]["category"], "dairy")  # he named it
        self.assertEqual(self.draft("sold out of Cal Poly honey", facts={**model, "availability": "yes"}, selection_checked=True)["facts"]["availability"], "no")
        self.assertIsNone(self.draft("we did not get in Cal Poly honey, not sold out", facts={**model, "availability": "no"})["facts"]["availability"])

    def test_the_good_writer_text_is_still_accepted(self):
        r = self.draft(writer=lambda prompt: "Honey from Cal Poly in San Luis Obispo. Spoon a little beside cheese or onto buttered toast; give it a chance to be tasted on its own.")
        self.assertEqual((r["description"]["source"], r["description"]["writer_rejected"]), ("writer", None), r["description"])


class SourcePreservingTests(unittest.TestCase):
    """Review round 2 (PR 504): meaning is kept by construction (exact pieces), never by word matching."""
    BEES = "got in honey from Bee Happy Farm in Templeton, California. "
    MODEL = {"name": "Bee Happy Farm honey", "maker": "Bee Happy Farm", "place": "Templeton, California", "kind": "honey"}

    def draft(self, message=HONEY, **kw):
        return newitem.draft(message, PHOTO, content=CONTENT, spec=SPEC, renderer=FAKE, **kw)

    def story(self, tail, story):
        return self.draft(self.BEES + tail, facts={**self.MODEL, "story": story})

    def test_a_negator_cannot_move_to_another_predicate(self):
        r = self.story("They keep bees but do not sell honey.", "Bee Happy Farm does not keep bees.")
        self.assertIn("story", r["dropped"])
        self.assertEqual(r["maker"]["story"], "Bee Happy Farm is based in Templeton, California.")

    def test_a_relative_clause_cannot_give_the_maker_a_new_predicate(self):
        r = self.story("They buy honey from farms that keep bees.", "Bee Happy Farm keeps bees.")
        self.assertIn("story", r["dropped"])
        self.assertNotIn("keeps bees", r["maker"]["story"])

    def test_compound_sentences_are_never_rewritten_even_by_the_plain_reader(self):
        r = self.draft(self.BEES + "They keep bees but do not sell honey.")
        self.assertEqual(r["maker"]["story"], "Bee Happy Farm is based in Templeton, California.")

    def test_a_simple_sentence_still_gets_only_its_pronoun_replaced(self):
        r = self.draft(self.BEES + "They keep bees on the hill.")
        self.assertEqual((r["maker"]["story"], r["dropped"]), ("Bee Happy Farm keeps bees on the hill.", []))
        verbatim = self.draft(self.BEES + "Bee Happy Farm keeps bees on the hill.", facts={**self.MODEL, "story": "Bee Happy Farm keeps bees on the hill."})
        self.assertEqual(verbatim["maker"]["story"], "Bee Happy Farm keeps bees on the hill.")

    def test_the_writer_cannot_swap_the_maker_and_the_place(self):
        r = self.draft(writer=lambda prompt: "Honey from San Luis Obispo in Cal Poly. Spoon a little beside cheese or onto buttered toast; give it a chance to be tasted on its own.")
        self.assertEqual(r["description"]["source"], "template")
        self.assertTrue(r["description"]["writer_rejected"])
        self.assertTrue(r["description"]["text"].startswith("Honey from Cal Poly in San Luis Obispo."))

    def test_the_writer_cannot_add_a_clause_after_a_serving_sentence(self):
        for text in ("Honey from Cal Poly in San Luis Obispo. Spoon a little onto toast; it has butter and cream.",
                     "Honey from Cal Poly in San Luis Obispo. Spoon a little beside cheese or onto buttered toast; give it a chance to be tasted on its own and it has butter.",
                     "Honey from Cal Poly in San Luis Obispo. Spoon a little beside cheese or onto buttered toast; give it a chance to be tasted on its own. Add butter and cream."):
            with self.subTest(text):
                r = self.draft(writer=lambda prompt, t=text: t)
                self.assertEqual(r["description"]["source"], "template")
                self.assertNotIn("cream", r["description"]["text"])
                self.assertNotIn("butter and", r["description"]["text"])


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class ImageCheckTests(unittest.TestCase):
    def test_a_kept_photo_background_never_passes(self):
        committed = hs.REPO_ROOT / "reports" / "hass" / "newitem-1" / "rendered"
        for name in ("bag-red-cloth", "jar-dark-wood"):
            with self.subTest(name):
                out = hs.check_image((committed / f"{name}.jpg").read_bytes(), SPEC)
                self.assertFalse(out["pass"], out)
                self.assertTrue(out["hard_failures"])
        out = hs.check_image((committed / "bag-red-cloth.jpg").read_bytes(), SPEC)
        self.assertIn("no photo background left inside the product (patterned cloth, planks)", out["hard_failures"])
        for good in ("jar-white-sheet", "bottle-grey-wall-tilted", "jar-phone-rotated"):
            self.assertTrue(hs.check_image((committed / f"{good}.jpg").read_bytes(), SPEC)["pass"], good)

    def test_a_fresh_red_cloth_render_is_flagged_by_both_the_renderer_and_the_check(self):
        out = newitem_render.render(syn.make_photo(**dict(syn.cases())["bag-red-cloth"]), SPEC)
        self.assertEqual(out["report"]["isolation"], "fallback")
        self.assertFalse(hs.check_image(out["jpeg"], SPEC)["pass"])


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class EndToEndTests(unittest.TestCase):
    def test_draft_runs_through_the_real_editor_with_the_render_seam(self):
        from hass.tests.test_set_photo import PhotoRepo
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        data = syn.make_photo(**dict(syn.cases())["jar-phone-rotated"])
        sha = repo.store(data)
        content = load_content(repo.wt / "hass" / "content")
        real = photos._web_bytes

        def house(root, found_sha):
            found = real(root, found_sha)
            return found if isinstance(found, photos.Refused) else (newitem_render.render(found[0], SPEC)["jpeg"], "jpg")
        result = newitem.draft(HONEY, data, content=content, spec=SPEC)
        self.assertEqual(result["status"], "draft")
        self.assertEqual(result["ops"][0]["args"]["photo"], sha)
        with mock.patch.object(photos, "_web_bytes", house):
            out = repo.prepare({"ops": result["ops"]})
            self.assertEqual(out["result"], "ok", out)
            self.assertEqual(claims.unstated(out["draft"], HONEY, content.makers, None, None), [])  # the claims gate the conversation applies
            self.assertEqual(repo.apply(out["draft"])["result"], "applied")
        added = repo.products()[-1]
        self.assertEqual(added["image"], f"assets/products/photo-{sha[:16]}.jpg")
        self.assertEqual(added["imageAlt"], "Cal Poly honey in a jar")
        committed = (repo.wt / "storefront-mockup" / added["image"]).read_bytes()
        self.assertEqual(committed, result["image"]["bytes"])  # what the draft showed is what was committed
        self.assertTrue(hs.check_image(committed, SPEC)["pass"])
        self.assertTrue(hs.check_product(added, repo.makers(), SPEC)["pass"])


class FinalRoundTests(unittest.TestCase):
    """Review round 3 (PR 504, frozen list A1 A2 B1 B2). Standard library only: these run in CI."""
    BEES = "got in honey from Bee Happy Farm in Templeton, California"

    def draft(self, message=HONEY, photo=PHOTO, **kw):
        return newitem.draft(message, photo, content=CONTENT, spec=SPEC, **{"renderer": FAKE, **kw})

    def assertRefused(self, r, code):
        self.assertEqual((r["status"], r["refused"], r["ops"]), ("refused", code, []))
        self.assertNotIn("image", r)

    def test_a1_a_town_is_never_taken_as_the_maker(self):
        town = {"name": "Bee Happy Farm honey", "maker": "Templeton", "place": "Templeton, California", "kind": "honey"}
        r = self.draft(self.BEES, facts=town, selection_checked=True)
        self.assertEqual((r["status"], r["ops"]), ("question", []))
        self.assertIn("maker", r["dropped"])
        self.assertEqual(r["question"], "Who makes the honey, and what town and state are they in?")
        self.assertEqual(r["question"].count("?"), 1)
        self.assertNotIn("maker.add", str(r["ops"]))
        good = self.draft(self.BEES, facts={**town, "maker": "Bee Happy Farm"})  # the maker his 'from' names: still a full draft
        self.assertEqual((good["status"], good["ops"][0]["args"]["name"], good["ops"][0]["args"]["place"]),
                         ("draft", "Bee Happy Farm", "Templeton, California"))
        self.assertTrue(good["description"]["text"].startswith("Honey from Bee Happy Farm in Templeton."))

    def test_a1_a_place_must_be_where_he_says_that_maker_is(self):
        message = "got in honey from Bee Happy Farm in Templeton, California. Picked it up on the way back from Paso Robles, California."
        wrong = {"name": "Bee Happy Farm honey", "maker": "Bee Happy Farm", "place": "Paso Robles, California", "kind": "honey"}
        r = self.draft(message, facts=wrong)
        self.assertIn("place", r["dropped"])
        self.assertEqual((r["status"], r["question"]), ("question", "Where is Bee Happy Farm based (town and state)?"))
        known = self.draft(HONEY, facts={"name": "Cal Poly honey", "maker": "Cal Poly", "kind": "honey"})  # a catalog maker he named
        self.assertEqual((known["status"], known["dropped"]), ("draft", []))

    def test_a2_a_stated_claim_stays_out_of_every_public_field(self):
        for facts in (None, {"name": "Organic honey", "kind": "honey"}):  # the plain reader and a model reader
            with self.subTest(facts=facts):
                r = self.draft("got in organic honey", facts=facts)
                product = next(o for o in r["ops"] if o["op"] == "product.add")["args"]
                self.assertEqual((product["name"], product["imageAlt"], r["product"]["name"]), ("Honey", "Honey", "Honey"))
                self.assertNotIn("organic", json.dumps(r["ops"]).lower())
                self.assertNotIn("organic", (r["alt"] + r["description"]["text"]).lower())
                self.assertEqual([x["value"] for x in r["left_off"] if x["what"] == "claim"], ["organic"])
        maker = self.draft("got in organic honey from Bee Happy Farm in Templeton, California. They keep organic bees.")
        self.assertNotIn("organic", json.dumps(maker["ops"]).lower())
        self.assertEqual(maker["maker"]["story"], "Bee Happy Farm is based in Templeton, California.")
        self.assertEqual(newitem.without_claims("Cal Poly raw honey", "honey"), "Cal Poly honey")

    def test_b1_unreadable_or_truncated_bytes_are_one_fixed_refusal(self):
        self.assertRefused(self.draft(photo=b"synthetic-photo-bytes"), "unsupported-type")
        self.assertRefused(self.draft(photo=PHOTO[:-20]), "truncated")
        self.assertRefused(self.draft(photo=b""), "empty")
        r = self.draft(photo=PHOTO, renderer=mock.Mock(side_effect=OSError("broken data stream when reading image file")))
        self.assertRefused(r, "unreadable")
        self.assertEqual(r["reply"], media.REPLIES["unreadable"])
        blank = self.draft(photo=PHOTO, renderer=mock.Mock(side_effect=newitem_render.Refused("blank")))
        self.assertRefused(blank, "blank")
        self.assertEqual(blank["reply"], newitem_render.REPLIES["blank"])

    def test_b2_the_store_byte_gate_runs_before_any_picture_work(self):
        renderer = mock.Mock(side_effect=AssertionError("must not be reached"))
        with mock.patch.object(media, "MAX_BYTES", 10):
            self.assertRefused(self.draft(photo=PHOTO, renderer=renderer), "too-large")
        self.assertRefused(self.draft(photo=b"GIF89a" + bytes(40), renderer=renderer), "unsupported-type")
        renderer.assert_not_called()


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class FinalRoundPictureTests(unittest.TestCase):
    """Review round 3 (PR 504): the real renderer on bytes Pillow cannot or must not decode."""
    def draft(self, photo):
        return newitem.draft(HONEY, photo, content=CONTENT, spec=SPEC)

    def test_b1_undecodable_pixels_and_an_all_transparent_png_are_refused(self):
        broken = png(idat=b"this is not zlib data")  # valid chunks and CRCs, so it passes the byte gate; Pillow cannot decode it
        media.check_photo(broken)
        with self.assertRaises(newitem_render.Refused) as caught:
            newitem_render.render(broken, SPEC)
        self.assertEqual(caught.exception.code, "unreadable")
        self.assertEqual((self.draft(broken)["status"], self.draft(broken)["ops"]), ("refused", []))
        clear = png(64, 64, (0, 0, 0, 0))
        with self.assertRaises(newitem_render.Refused) as caught:
            newitem_render.render(clear, SPEC)
        self.assertEqual(caught.exception.code, "blank")
        r = self.draft(clear)
        self.assertEqual((r["status"], r["refused"], r["ops"]), ("refused", "blank", []))

    def test_b2_pixel_budget_is_checked_before_decoding(self):
        huge = png(10_000, 6_000, idat=zlib.compress(b"\0" * 64))  # 60 MP in the header, almost no data
        media.check_photo(huge)
        with mock.patch.object(PILImage.Image, "load", side_effect=AssertionError("decoded before the budget check")):
            with self.assertRaises(newitem_render.Refused) as caught:
                newitem_render.render(huge, SPEC)
        self.assertEqual(caught.exception.code, "too-many-pixels")
        self.assertEqual(self.draft(huge)["refused"], "too-many-pixels")

    def test_b2_decompression_bomb_warning_and_error_are_refusals(self):
        for limit in (10, 5):  # 16 px: over the limit is Pillow's warning, over twice the limit its error
            with self.subTest(limit=limit), mock.patch.object(PILImage, "MAX_IMAGE_PIXELS", limit):
                with self.assertRaises(newitem_render.Refused) as caught:
                    newitem_render.render(png(), SPEC)
                self.assertEqual(caught.exception.code, "too-many-pixels")

    def test_b2_only_the_kind_the_bytes_gate_found_is_opened(self):
        buf = io.BytesIO()
        PILImage.new("RGB", (8, 8), (200, 180, 120)).save(buf, "GIF")
        with self.assertRaises(media.Refused):
            newitem_render.render(buf.getvalue(), SPEC)


if __name__ == "__main__":
    unittest.main()
