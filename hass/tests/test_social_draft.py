"""AVB-22 tests: the local Instagram post draft. Run: python3 -m unittest hass.tests.test_social_draft -v

Each case builds a temporary content dir and site dir; the checkout is only read.
"""
import ast
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from hass import social_draft
from hass.content_model import CATEGORIES, load_content

MAKER = {"name": "Brian's", "place": "Atascadero, California", "story": "Bread.", "url": "https://example.com/"}


def product(pid, **changes):
    return {"id": pid, "name": "Sourdough", "brand": "Brian's", "category": "bread", "image": f"assets/products/{pid}.webp",
            "description": "A crust worth tearing.", "producerKey": "Brian's", "displayBrand": "Brian's", "status": "active", **changes}


class SocialDraftTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "content").mkdir()
        (self.root / "site" / "assets" / "products").mkdir(parents=True)
        self.site = self.root / "site"

    def load(self, *products):
        for p in products:
            (self.site / p["image"]).resolve().write_bytes(b"x")
        for name, doc in (("products", {"products": list(products)}), ("makers", {"makers": {"Brian's": MAKER}}),
                          ("community", {}), ("store", {})):
            (self.root / "content" / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **doc}), "utf-8")
        return load_content(self.root / "content")

    def build(self, pid, *products):
        return social_draft.build(self.load(*products), pid, self.site)

    def test_active_product_with_maker(self):
        out = self.build("p1", product("p1"))
        self.assertTrue(out["draft"])
        self.assertEqual(out["image"], "assets/products/p1.webp")
        self.assertEqual(out["alt"], "Sourdough")
        self.assertEqual(out["caption"],
                         "Sourdough\nA crust worth tearing.\nFrom Brian's in Atascadero, California.\n\n#AvocadoShack #Bread")
        self.assertLessEqual(out["caption"].count("#"), 5)

    def test_alt_uses_image_alt_and_no_maker_sentence(self):
        out = self.build("p1", product("p1", producerKey=None, imageAlt="A round loaf"))
        self.assertEqual(out["alt"], "A round loaf")
        self.assertNotIn("From ", out["caption"])
        out = self.build("p1", product("p1", producerKey=None))
        self.assertEqual(out["alt"], "Sourdough")

    def test_every_category_gets_one_fixed_tag(self):
        for category in CATEGORIES:
            tags = [w for w in self.build("p1", product("p1", category=category))["caption"].split() if w.startswith("#")]
            self.assertEqual(tags, ["#AvocadoShack", social_draft.CATEGORY_TAGS[category]])

    def test_held_and_hidden_are_not_on_the_site(self):
        for status in ("held", "hidden"):
            self.assertEqual(self.build("p1", product("p1", status=status)), {"draft": False, "reason": "not on the site"})

    def test_unknown_id_and_path_ids_are_not_products(self):
        listed = product("p1")
        for pid in ("nope", "../p1", "assets/../p1", "", "P1"):
            self.assertEqual(self.build(pid, listed), {"draft": False, "reason": "no such product"})

    def test_missing_photo_or_escaping_image_path(self):
        content = self.load(product("p1"))
        (self.site / "assets/products/p1.webp").unlink()
        self.assertEqual(social_draft.build(content, "p1", self.site), {"draft": False, "reason": "no photo on the site"})
        (self.site / "assets/products/p1.webp").mkdir()  # a directory is not a regular file
        self.assertEqual(social_draft.build(content, "p1", self.site)["reason"], "no photo on the site")
        (self.root / "secret.webp").write_bytes(b"x")
        self.assertEqual(self.build("p1", product("p1", image="../secret.webp"))["reason"], "no photo on the site")

    def test_organic_stays_verbatim_and_nothing_is_added(self):
        text = "Made with organic wheat."
        out = self.build("p1", product("p1", description=text))
        self.assertIn(text, out["caption"])
        self.assertEqual(out["caption"].lower().count("organic"), 1)
        for word in ("$", "available", "fresh", "local", "today"):
            self.assertNotIn(word, out["caption"].lower())

    def test_caption_length_limit(self):
        base = len(self.build("p1", product("p1", description=""))["caption"])
        self.assertTrue(self.build("p1", product("p1", description="x" * (2200 - base)))["draft"])
        self.assertEqual(self.build("p1", product("p1", description="x" * (2201 - base))),
                         {"draft": False, "reason": "caption too long"})

    def test_cli_prints_json_and_exit_code(self):
        self.load(product("p1"), product("p2", status="held"))
        for pid, code, draft in (("p1", 0, True), ("p2", 1, False)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(social_draft.main([pid], self.root / "content", self.site), code)
            self.assertIs(json.loads(out.getvalue())["draft"], draft)

    def test_module_imports_no_network_module(self):
        tree = ast.parse(Path(social_draft.__file__).read_text("utf-8"))
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertFalse(names & {"urllib", "socket", "http", "requests", "smtplib", "ssl", "subprocess", "ftplib"}, names)


if __name__ == "__main__":
    unittest.main()
