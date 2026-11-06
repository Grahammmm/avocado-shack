"""AV1937-09 tests: social_draft --maker KEY prints a local Meet the maker caption draft. Run:
python3 -B -m unittest hass.tests.test_social_draft_maker -v

Synthetic content only; CLI cases write a temporary content dir. Nothing is posted.
"""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from hass import social_draft
from hass.content_model import Content

TAGS = "\n\n#AvocadoShack #MeetTheMaker"
MAKER = {"name": "Sunny Farm", "place": "Pismo Beach", "story": "Three generations of growers.\nSecond line."}


def prod(pid, key="m1", status="active"):
    return {"id": pid, "producerKey": key, "status": status, "name": "N" + pid}


def content(makers=None, products=None):
    return Content(products=[prod("a"), prod("b"), prod("c", status="held"), prod("d", "m2"), prod("e", status="hidden")]
                   if products is None else products,
                   makers={"m1": dict(MAKER), "m2": dict(MAKER, name="Other")} if makers is None else makers,
                   community={}, store={})


def refused(reason):
    return {"draft": False, "reason": reason}


def caption(n="2 active products", **kw):
    m = dict(MAKER, **kw)
    return f"Meet the maker: {m['name']}\nBased in {m['place']}.\n{m['story']}\n{n} on our site." + TAGS


class MakerDraftTests(unittest.TestCase):
    def test_visible_maker_exact_caption_and_active_count(self):
        self.assertEqual(social_draft.build_maker(content(), "m1"), {"draft": True, "caption": caption()})
        one = content(products=[prod("a"), prod("b", status="held"), prod("c", "m2")])
        self.assertEqual(social_draft.build_maker(one, "m1"), {"draft": True, "caption": caption("1 active product")})

    def test_unknown_hidden_and_no_active_products(self):
        for key in ("zz", "M1", ""):
            self.assertEqual(social_draft.build_maker(content(), key), refused("no such maker"), key)
        hidden = content(makers={"m1": dict(MAKER, hidden=True)})
        self.assertEqual(social_draft.build_maker(hidden, "m1"), refused("not on the site"))
        hidden_bad = content(makers={"m1": {"hidden": True}})
        self.assertEqual(social_draft.build_maker(hidden_bad, "m1"), refused("not on the site"))
        for products in ([], [prod("a", status="held")], [prod("a", status="hidden")], [prod("a", "m2")]):
            self.assertEqual(social_draft.build_maker(content(products=products), "m1"), refused("no active products"))

    def test_malformed_collections_and_record(self):
        for makers in ([], "x", 5):
            self.assertEqual(social_draft.build_maker(content(makers=makers), "m1"), refused("cannot read content"))
        broken = content()
        broken.makers = None
        self.assertEqual(social_draft.build_maker(broken, "m1"), refused("cannot read content"))
        broken = content()
        broken.products = None
        self.assertEqual(social_draft.build_maker(broken, "m1"), refused("cannot read content"))
        for products in ({}, [prod("a"), "x"], [None]):
            self.assertEqual(social_draft.build_maker(content(products=products), "m1"), refused("cannot read content"))
        self.assertEqual(social_draft.build_maker(content(makers={"m1": "x"}), "m1"), refused("maker record incomplete"))

    def test_required_text_and_story_newlines(self):
        for field in ("name", "place", "story"):
            for bad in (None, "", "  ", 5, ["x"], "a\rb", "a\x07b", "a\u2028b", "a\u2029b"):
                m = dict(MAKER, **{field: bad})
                self.assertEqual(social_draft.build_maker(content(makers={"m1": m}), "m1"), refused("maker record incomplete"), (field, bad))
            m = {k: v for k, v in MAKER.items() if k != field}
            self.assertEqual(social_draft.build_maker(content(makers={"m1": m}), "m1"), refused("maker record incomplete"), field)
        for field in ("name", "place"):
            m = dict(MAKER, **{field: "a\nb"})
            self.assertEqual(social_draft.build_maker(content(makers={"m1": m}), "m1"), refused("maker record incomplete"), field)
        out = social_draft.build_maker(content(), "m1")
        self.assertIn("growers.\nSecond line.\n", out["caption"])

    def test_optional_url_and_no_photo_dependency(self):
        for url in (None, "https://example.com/x"):
            m = dict(MAKER, **({} if url is None else {"url": url}))
            out = social_draft.build_maker(content(makers={"m1": m}), "m1")
            self.assertEqual(out, {"draft": True, "caption": caption()})
            self.assertNotIn("example.com", out["caption"])

    def test_free_text_tag_marks(self):
        for field in ("name", "place", "story"):
            for mark in ("#", "@", "\uff03", "\uff20", "\ufe5f", "\ufe6b"):
                m = dict(MAKER, **{field: f"A {mark}tag1 b"})
                self.assertEqual(social_draft.build_maker(content(makers={"m1": m}), "m1"),
                                 refused("free text has a hashtag or account name"), (field, mark))
            m = dict(MAKER, **{field: "A # b @ c #"})
            self.assertTrue(social_draft.build_maker(content(makers={"m1": m}), "m1")["draft"], field)

    def test_caption_length_boundary(self):
        base = len(social_draft.build_maker(content(), "m1")["caption"]) - len(MAKER["story"])
        for extra, ok in ((0, True), (1, False)):
            story = "x" * (2200 - base + extra)
            out = social_draft.build_maker(content(makers={"m1": dict(MAKER, story=story)}), "m1")
            if ok:
                self.assertEqual((out["draft"], len(out["caption"])), (True, 2200))
            else:
                self.assertEqual(out, refused("caption too long"))

    def test_read_only_and_no_image_selection(self):
        c = content()
        before = copy.deepcopy((c.products, c.makers))
        out = social_draft.build_maker(c, "m1")
        self.assertEqual(set(out), {"draft", "caption"})
        self.assertEqual(social_draft.build_maker(c, "zz"), refused("no such maker"))
        self.assertEqual((c.products, c.makers), before)


class MakerCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        c = content()
        c.makers["m3"] = dict(MAKER, hidden=True)
        for name, doc in (("products", {"products": c.products}), ("makers", {"makers": c.makers}), ("community", {}), ("store", {})):
            (self.dir / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **doc}), "utf-8")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = social_draft.main(list(argv), self.dir, self.dir)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def snapshot(self):
        return {p.name: p.read_bytes() for p in sorted(self.dir.iterdir())}

    def test_cli_json_and_usage_errors(self):
        before = self.snapshot()
        code, out = self.run_cli("--maker", "m1")
        self.assertEqual((code, json.loads(out)), (0, {"draft": True, "caption": caption()}))
        self.assertTrue(out.startswith("{\n  "))
        code, out = self.run_cli("--maker", "m3")
        self.assertEqual((code, json.loads(out)), (1, refused("not on the site")))
        code, out = self.run_cli("--maker", "zz")
        self.assertEqual((code, json.loads(out)), (1, refused("no such maker")))
        self.assertEqual(self.snapshot(), before)
        for argv in (("--maker",), (), ("--maker", "m1", "p1"), ("p1", "--maker", "m1"),
                     ("--maker", "m1", "--hike", "h1"), ("--hike", "h1", "--maker", "m1"), ("--maker", "m1", "--maker2")):
            self.assertEqual(self.run_cli(*argv), (2, ""), argv)
        (self.dir / "makers.json").write_text("{bad", "utf-8")
        code, out = self.run_cli("--maker", "m1")
        self.assertEqual((code, json.loads(out)), (1, refused("cannot read content")))


if __name__ == "__main__":
    unittest.main()
