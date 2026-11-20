"""RF0140-3 tests: social_draft prints one JSON refusal for unreadable content or an incomplete product record.

Run: python3 -m unittest hass.tests.test_social_draft_inputs -v
"""
import contextlib
import io
import json
import unittest

from hass import social_draft
from hass.tests import test_social_draft as base
from hass.tests.test_social_draft import product

CANNOT = (1, {"draft": False, "reason": "cannot read content"})
INCOMPLETE = {"draft": False, "reason": "product record incomplete"}
NO_MAKER_CAPTION = "Sourdough\nA crust worth tearing.\n\n#AvocadoShack #Bread"
HAPPY_CAPTION = "Sourdough\nA crust worth tearing.\nFrom Brian's in Atascadero, California.\n\n#AvocadoShack #Bread"


class SocialDraftInputTests(unittest.TestCase):
    # Borrow the base helpers without subclassing, so the base tests do not run twice.
    setUp, load, build = base.SocialDraftTests.setUp, base.SocialDraftTests.load, base.SocialDraftTests.build

    def tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes() if p.is_file() else None for p in self.root.rglob("*")}

    def run_cli(self, pid="p1", content_dir=None):
        """Run main(); assert one JSON object on stdout, no traceback on stderr, nothing written. Return (code, obj)."""
        before, out, err = self.tree(), io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = social_draft.main([pid], content_dir or self.root / "content", self.site)
        self.assertEqual(err.getvalue(), "")
        self.assertIsInstance(json.loads(out.getvalue()), dict)  # exactly one JSON value, nothing else
        self.assertEqual(self.tree(), before, "read-only: the folders must not change")
        return code, json.loads(out.getvalue())

    def rewrite(self, name, data):
        (self.root / "content" / f"{name}.json").write_bytes(data.encode() if isinstance(data, str) else data)

    def test_missing_content_folder(self):
        self.assertEqual(self.run_cli(content_dir=self.root / "nowhere"), CANNOT)

    def test_content_that_load_content_refuses(self):
        for name, data in (("products", "{not json"), ("products", json.dumps({"schemaVersion": 2, "products": []})),
                           ("makers", "[]"), ("store", "null"), ("makers", b"\xff\xfe"),
                           ("products", json.dumps({"schemaVersion": 1, "products": [], "x": 1}))):
            with self.subTest(name=name, data=data):
                self.load(product("p1"))
                self.rewrite(name, data)
                self.assertEqual(self.run_cli(), CANNOT)
        self.load(product("p1"))
        (self.root / "content" / "community.json").unlink()
        self.assertEqual(self.run_cli(), CANNOT)

    def test_description_absent_null_empty_or_non_text(self):
        bare = product("p1")
        del bare["description"]
        for record in (bare, *(product("p1", description=v) for v in (None, "", 7, ["x"], {"t": "x"}))):
            with self.subTest(record=record):
                self.assertEqual(self.build("p1", record), INCOMPLETE)
                self.assertEqual(self.run_cli(), (1, INCOMPLETE))

    def test_name_absent_or_bad_is_incomplete_after_id_match(self):
        bare = product("p1")
        del bare["name"]
        self.assertEqual(self.build("p1", bare), INCOMPLETE)
        self.assertEqual(self.run_cli(), (1, INCOMPLETE))
        for value in (None, "", 3):
            self.assertEqual(self.build("p1", product("p1", name=value)), INCOMPLETE)
        self.assertEqual(self.build("p1", product("p1", name=None, imageAlt="A loaf")), INCOMPLETE)  # alt cannot rescue it

    def test_earlier_refusals_keep_their_order(self):
        self.assertEqual(self.build("p2", product("p1", description=None))["reason"], "no such product")
        self.assertEqual(self.build("p1", product("p1", description=None, status="held"))["reason"], "not on the site")
        content = self.load(product("p1", description=None))
        (self.site / "assets/products/p1.webp").unlink()
        self.assertEqual(social_draft.build(content, "p1", self.site)["reason"], "no photo on the site")

    def test_malformed_maker_is_no_maker(self):
        content = self.load(product("p1"))
        for maker in (["Brian's", "Atascadero"], "Brian's", 5, {"name": "Brian's"}, {"place": "Atascadero"},
                      {"name": "Brian's", "place": None}, {"name": 1, "place": "Atascadero"}):
            with self.subTest(maker=maker):
                content.makers["Brian's"] = maker
                out = social_draft.build(content, "p1", self.site)
                self.assertEqual((out["draft"], out["caption"]), (True, NO_MAKER_CAPTION))
        for makers in (["Brian's"], {"Brian's": ["x"]}, {"Brian's": {"name": "Brian's"}}):  # as loaded from makers.json
            with self.subTest(makers=makers):
                self.load(product("p1"))
                self.rewrite("makers", json.dumps({"schemaVersion": 1, "makers": makers}))
                code, out = self.run_cli()
                self.assertEqual((code, out["caption"]), (0, NO_MAKER_CAPTION))

    def test_happy_path_unchanged(self):
        self.load(product("p1"))
        self.assertEqual(self.run_cli(), (0, {"draft": True, "illustration": True, "availability": None, "image": "assets/products/p1.webp", "alt": "Sourdough",
                                              "caption": HAPPY_CAPTION}))


if __name__ == "__main__":
    unittest.main()
