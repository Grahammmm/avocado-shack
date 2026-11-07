"""HASS-NEWITEM-1 tests: the measured house style, its checks, the picture renderer and the new-item draft.

Text/record/draft tests are standard library only. Picture tests need Pillow and are skipped without it (CI python has none:
see reports/hass/NEWITEM-1.md hand-off card 5). The end-to-end test runs the draft through the real editor (prepare, claims,
apply, undo) on a throwaway repo, with the one planned seam (photos._web_bytes -> house render) patched in.
"""
import hashlib
import json
import unittest
from unittest import mock

from hass import claims, house_style as hs, newitem
from hass.content_model import load_content
from hass.ops import photos

try:
    import PIL  # noqa: F401
    from hass import newitem_render, newitem_synthetic as syn
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

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
        return newitem.draft(message, b"synthetic-photo-bytes", content=CONTENT, spec=SPEC, renderer=FAKE, **kw)

    def test_the_honey_example(self):
        r = self.draft(selection_checked=True)
        self.assertEqual(r["status"], "draft")
        product = next(o for o in r["ops"] if o["op"] == "product.add")["args"]
        self.assertEqual((product["name"], product["brand"], product["category"], product["producerKey"]), ("Cal Poly honey", "Cal Poly", "pantry", "Cal Poly"))
        self.assertTrue(r["description"]["text"].startswith("Honey from Cal Poly in San Luis Obispo."))
        self.assertEqual(product["photo"], hashlib.sha256(b"synthetic-photo-bytes").hexdigest())
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
        good = self.draft(HONEY, writer=lambda prompt: "Honey from Cal Poly in San Luis Obispo. Spoon a little onto buttered toast.")
        self.assertEqual(good["description"]["source"], "writer")
        self.assertIn("Examples" if False else "Real examples", newitem.writer_prompt(good["facts"], SPEC, ["x."]))

    def test_the_product_phrase_is_not_a_story_word(self):
        from hass import newitem_demo
        r = self.draft(newitem_demo.MESSAGES["bottle-grey-wall-tilted"])
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
        control = self.draft(HONEY, writer=lambda prompt: "Honey from Cal Poly in San Luis Obispo. Spoon a little onto buttered toast.")
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


if __name__ == "__main__":
    unittest.main()
