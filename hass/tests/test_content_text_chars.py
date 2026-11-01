"""RF1300-10 tests: content text refuses control, zero-width and direction-changing characters.

Each case copies the checkout content to a temporary directory, changes one value and validates it.
The checkout is only read. Run: python3 -m unittest hass.tests.test_content_text_chars -v
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hass.content_model import CONTENT_DIR, SITE_DIR, ContentError, load_and_validate, load_content, validate
from hass.tests.test_catalog_ops import CatalogTestCase, _req

EVENT = {"id": "hike-test-chars", "title": "Morning walk", "startsAt": "2026-12-05T09:00:00-08:00",
         "timezone": "America/Los_Angeles", "status": "scheduled"}
P = "product photo-product-001"  # products[0] in the checkout
MSG = ": contains invisible or control character U+"


class ContentTextCharTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.content_dir = Path(tmp.name) / "content"
        shutil.copytree(CONTENT_DIR, self.content_dir)

    def problems(self, name, fn):
        path = self.content_dir / name
        data = json.loads(path.read_text("utf-8"))
        fn(data)
        path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        try:
            validate(load_content(self.content_dir), SITE_DIR)
        except ContentError as exc:
            return exc.problems
        return []

    def char_problems(self, name, fn):
        return [p for p in self.problems(name, fn) if MSG in p]

    def first_maker(self, data):
        return next(iter(data["makers"]))

    def test_each_class_per_field_kind(self):
        def set_maker_story(d):
            d["makers"][self.first_maker(d)]["story"] += "\tmore"

        def add_event(d):
            d["events"].append({**EVENT, "title": "Morning \u202ewalk"})

        def idea_desc(d):
            d["routeIdeas"][0]["description"] = "Sea\u200bstacks"

        cases = [
            ("products.json", lambda d: d["products"][0].update(name="Two\nlines"), P + ".name", "000A"),
            ("makers.json", set_maker_story, None, "0009"),
            ("store.json", lambda d: d["hours"].__setitem__(0, "Mon\u0085Fri"), "store.hours[0]", "0085"),
            ("community.json", add_event, "events[0].title", "202E"),
            ("community.json", idea_desc, "routeIdeas[0].description", "200B"),
            ("products.json", lambda d: d["products"][0].update(imageAlt="\ufeffA crate of fruit"),
             P + ".imageAlt", "FEFF"),
        ]
        for name, fn, where, code in cases:
            with self.subTest(code=code):
                self.setUp()
                found = self.char_problems(name, fn)
                self.assertEqual(len(found), 1, found)
                self.assertTrue(found[0].endswith(MSG + code), found)
                if where is not None:
                    self.assertEqual(found[0], f"{where}{MSG}{code}")
                else:
                    self.assertTrue(found[0].startswith("maker ") and ".story" in found[0], found)

    def test_maker_key_with_isolate(self):
        new_key = "Lin\u2066n"

        def rename(d):
            d["makers"][new_key] = d["makers"].pop(self.first_maker(d))

        found = self.char_problems("makers.json", rename)
        self.assertEqual(found, [f"maker {new_key!r} key{MSG}2066"])

    def test_one_problem_per_value(self):
        found = self.char_problems("products.json", lambda d: d["products"][0].update(name="A\u200bv\u200bo\u200b"))
        self.assertEqual(found, [f"{P}.name{MSG}200B"])

    def test_first_offending_character_is_named(self):
        found = self.char_problems("products.json", lambda d: d["products"][0].update(name="A\u2060b\x07c"))
        self.assertEqual(found, [f"{P}.name{MSG}2060"])

    def test_reported_alongside_other_problems(self):
        problems = self.problems("products.json", lambda d: d["products"][0].update(name="<b>\u202e"))
        mine = [p for p in problems if p.startswith(P + ".name")]
        self.assertIn(P + ".name: contains forbidden text '<'", mine)
        self.assertIn(f"{P}.name{MSG}202E", mine)

    def test_range_edges_refused(self):
        for ch in ("\x00", "\x1f", "\x7f", "\x9f", "\u200f", "\u202a", "\u2064", "\u2069"):
            with self.subTest(code=f"{ord(ch):04X}"):
                self.setUp()
                found = self.char_problems("store.json", lambda d: d.update(name=f"Avo{ch}Shack"))
                self.assertEqual(found, [f"store.name{MSG}{ord(ch):04X}"])

    def test_allowed_text_passes(self):
        for text in ("Linn’s", "Montaña de Oro", "Chèvre", "9am – 6pm", "Avocado\u00a0Shack",
                     "Ripe\u2010ready", "Big\u202fSur"):
            with self.subTest(text=text):
                self.setUp()
                self.assertEqual(self.problems("store.json", lambda d: d.update(name=text)), [])

    def test_checkout_content_passes(self):
        load_and_validate(CONTENT_DIR, SITE_DIR)


class OpsPathTests(CatalogTestCase):
    def test_product_edit_name_with_rtl_mark_is_invalid(self):
        repo = self.repo()
        result = self.assertRejected(repo, "invalid", ("product.edit", {"id": "photo-product-001", "name": "Ched\u200fdar"}))
        self.assertTrue(any("name" in p and "U+200F" in p for p in result["problems"]), result)
        self.assertEqual(repo.status(), "")


if __name__ == "__main__":
    unittest.main()
