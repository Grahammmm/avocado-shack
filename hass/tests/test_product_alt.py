"""RF0905-5 (H10): product imageAlt via product ops (H02 editor, throwaway repo) and the storefront alt fallback."""

import copy, json, shutil, subprocess, unittest  # noqa: E401
from pathlib import Path

from hass import sitegen
from hass.content_model import PRODUCT_PUBLIC_FIELDS, REPO_ROOT, SITE_DIR, ContentError, load_and_validate, \
    load_content, validate
from hass.tests.test_catalog_ops import NEW, CatalogTestCase

ALT, PID, HELD = "Sunrise over the bluffs", "photo-product-001", "photo-product-040"
CATALOG = "storefront-mockup/catalog-products.js"
NODE = shutil.which("node")
DRIVER = Path(__file__).resolve().parent / "fixtures" / "shop_photo_driver.cjs"
BAD = ("", "  ", " lead", "<b>x</b>", "{{x}}", "$5", "x" * 201)


def _record(products, pid):
    return next(p for p in products if p["id"] == pid)


def _problems(content):
    try:
        validate(content, SITE_DIR)
    except ContentError as exc:
        return exc.problems
    return []


class AltOpTests(CatalogTestCase):
    def alt(self, repo):
        return _record(repo.products(), PID).get("imageAlt")

    def test_add_with_and_without_alt(self):
        repo = self.repo()
        repo.run(("product.add", NEW))
        self.assertNotIn("imageAlt", repo.products()[-1])
        repo.run(("product.add", {**NEW, "name": "Test quince with alt", "imageAlt": ALT}))
        added = repo.products()[-1]
        self.assertEqual((list(added)[-2:], added["imageAlt"]), (["status", "imageAlt"], ALT))
        public = _record(repo.catalog(), added["id"])
        self.assertEqual(list(public), list(PRODUCT_PUBLIC_FIELDS) + ["imageAlt"])
        self.assertNotIn("imageAlt", repo.catalog()[-2])
        repo.content()  # validates

    def test_edit_sets_replaces_and_undo_restores(self):
        repo = self.repo()
        original = _record(repo.products(), PID)
        first = repo.run(("product.edit", {"id": PID, "imageAlt": ALT}))
        self.assertEqual((self.alt(repo), _record(repo.catalog(), PID)["imageAlt"]), (ALT, ALT))
        second = repo.run(("product.edit", {"id": PID, "imageAlt": "Avocados on a board"}))
        self.assertEqual(self.alt(repo), "Avocados on a board")
        repo.run(("history.revert", {"changeId": second["change_id"]}))
        self.assertEqual(self.alt(repo), ALT)
        repo.run(("history.revert", {"changeId": first["change_id"]}))
        self.assertEqual(_record(repo.products(), PID), original)
        self.assertNotIn("imageAlt", _record(repo.catalog(), PID))

    def test_clear(self):
        repo = self.repo()
        for flag in (True, False):  # nothing to clear and nothing else: no empty change
            with self.subTest(clearImageAlt=flag):
                result = self.assertRejected(repo, "needs-details", ("product.edit", {"id": PID, "clearImageAlt": flag}))
                self.assertTrue({"imageAlt", "clearImageAlt"} <= set(result["missing"]), result)
        repo.run(("product.edit", {"id": PID, "clearImageAlt": True, "description": "Fresh today."}))
        self.assertEqual((_record(repo.products(), PID)["description"], self.alt(repo)), ("Fresh today.", None))
        repo.run(("product.edit", {"id": PID, "imageAlt": ALT}))
        result = self.assertRejected(repo, "refused", ("product.edit", {"id": PID, "imageAlt": "B", "clearImageAlt": True}))
        self.assertEqual((result["reason"], self.alt(repo)), ("imageAlt and clearImageAlt cannot be combined", ALT))
        repo.run(("product.edit", {"id": PID, "clearImageAlt": True}))
        self.assertNotIn("imageAlt", _record(repo.products(), PID))
        self.assertNotIn("imageAlt", _record(repo.catalog(), PID))

    def test_rejected_text_names_imagealt_without_write(self):
        repo = self.repo()
        for bad in BAD:
            for op, args in (("product.edit", {"id": PID, "imageAlt": bad}), ("product.add", {**NEW, "imageAlt": bad})):
                with self.subTest(op=op, value=bad):
                    result = self.assertRejected(repo, "invalid", (op, args))
                    self.assertTrue(result["problems"] and all("imageAlt" in p for p in result["problems"]), result)
        result = self.assertRejected(repo, "invalid", ("product.edit", {"id": PID, "imageALT": ALT}))
        self.assertTrue(any("unknown argument 'imageALT'" in p for p in result["problems"]), result)
        repo.run(("product.edit", {"id": PID, "imageAlt": "y" * 200}))
        self.assertEqual(self.alt(repo), "y" * 200)

    def test_hidden_keeps_alt_and_held_is_refused(self):
        repo = self.repo()
        repo.run(("product.edit", {"id": PID, "imageAlt": ALT}))
        catalog = repo.read(CATALOG)
        repo.run(("product.hide", {"id": PID}))
        self.assertEqual(self.alt(repo), ALT)
        self.assertNotIn(ALT.encode(), repo.read(CATALOG))
        repo.run(("product.restore", {"id": PID}))
        self.assertEqual(repo.read(CATALOG), catalog)
        for args in ({"imageAlt": ALT}, {"clearImageAlt": True}):
            with self.subTest(args=args):
                self.assertIn("held", self.assertRejected(repo, "refused", ("product.edit", {"id": HELD, **args}))["reason"])


class AltModelTests(unittest.TestCase):
    def setUp(self):
        self.content = copy.deepcopy(load_content())

    def product(self, pid):
        return _record(self.content.products, pid)

    def test_committed_content_is_byte_identical(self):
        self.assertFalse(any("imageAlt" in p for p in load_and_validate().products))
        self.assertEqual(sitegen.render(load_and_validate())[CATALOG], (REPO_ROOT / CATALOG).read_bytes())

    def test_model_rejects_bad_text_and_accepts_200(self):
        for bad in BAD + (5,):
            with self.subTest(value=bad):
                self.product(PID)["imageAlt"] = bad
                problems = _problems(self.content)
                self.assertTrue(problems and all(f"product {PID}.imageAlt" in p for p in problems), problems)
        self.product(PID)["imageAlt"] = "z" * 200
        self.assertEqual(_problems(self.content), [])
        self.product(PID)["imageALT"] = ALT  # the allow-list is not loosened: wrong case is still unknown
        self.assertEqual(_problems(self.content), ["products[0]: unknown field 'imageALT'"])

    def test_hidden_and_held_may_carry_alt_but_never_reach_catalog(self):
        self.product(PID).update(status="hidden", imageAlt="Hidden photo alt")
        self.product(HELD)["imageAlt"] = "Held photo alt"
        self.assertEqual(_problems(self.content), [])
        self.assertNotIn(b"photo alt", sitegen.render(self.content)[CATALOG])
        self.product(HELD)["imageAlt"] = "<held>"  # held records are still validated
        self.assertEqual({p.split(":")[0] for p in _problems(self.content)}, {f"product {HELD}.imageAlt"})


@unittest.skipUnless(NODE, "node is required for the storefront photo() driver")
class StorefrontAltTests(unittest.TestCase):
    def photo(self, **product):
        argv = [str(NODE), str(DRIVER), json.dumps({"image": "assets/products/a.webp", **product})]
        return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=True).stdout

    def test_alt_text_falls_back_to_escaped_name(self):
        self.assertIn(f'alt="{ALT}"', self.photo(name="Quince", imageAlt=ALT))
        self.assertIn('alt="Tom &amp; Jerry"', self.photo(name="Tom & Jerry"))
        self.assertIn('alt="Say &quot;hi&quot; &amp; go"', self.photo(name="Quince", imageAlt='Say "hi" & go'))
