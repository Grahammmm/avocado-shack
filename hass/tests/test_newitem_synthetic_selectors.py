"""RF0421-12: make_photo refuses product/background names outside PRODUCTS/BACKGROUNDS instead of drawing a substitute scene."""
import io
import sys
import unittest
from unittest import mock

from hass import newitem_synthetic as ns

# Guarded like test_newitem_synthetic.py so the CI planner (no Pillow) counts the same methods that run later.
try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

SIZE = (240, 180)
PRODUCT_ERR = "product must be one of PRODUCTS"
BACKGROUND_ERR = "background must be one of BACKGROUNDS"
DECLARED_PRODUCTS = ("jar", "bottle", "bag")
DECLARED_BACKGROUNDS = ("white-sheet", "grey-wall", "kitchen-bench", "dark-wood", "red-cloth")
BAD_NAMES = ("bottel", "pouch", "", "Jar", "JAR", " jar", "jar ", "grey-wal", "White-Sheet", "white-sheet ", "red cloth")
BAD_TYPES = (None, True, False, 0, 1, 1.5, b"jar", b"white-sheet", [], ["jar"], {}, {"jar": 1}, object())


class _Tripwire(Exception):
    pass


def _forbid_work():
    """Patches that fail loudly if make_photo imports Pillow, builds an RNG or draws before refusing."""
    def boom(*a, **k):
        raise _Tripwire("work started before refusal")
    return (mock.patch.dict(sys.modules, {"PIL": None}), mock.patch.object(ns.random, "Random", boom),
            mock.patch.object(ns, "_background", boom), mock.patch.object(ns, "_product", boom))


class SceneSelectorRefusal(unittest.TestCase):
    def test_unknown_scene_names_are_not_silent_substitutes(self):
        for name in BAD_NAMES:
            for fmt in ("JPEG", "PNG"):
                with self.assertRaises(ValueError) as cm:
                    ns.make_photo(product=name, size=SIZE, fmt=fmt)
                self.assertEqual(str(cm.exception), PRODUCT_ERR)
                with self.assertRaises(ValueError) as cm:
                    ns.make_photo(background=name, size=SIZE, fmt=fmt)
                self.assertEqual(str(cm.exception), BACKGROUND_ERR)

    def test_nonstring_scene_selectors_are_deliberately_refused(self):
        for bad in BAD_TYPES:
            with self.assertRaises(ValueError) as cm:
                ns.make_photo(product=bad, size=SIZE)
            self.assertEqual(str(cm.exception), PRODUCT_ERR)
            with self.assertRaises(ValueError) as cm:
                ns.make_photo(background=bad, size=SIZE)
            self.assertEqual(str(cm.exception), BACKGROUND_ERR)

    def test_scene_refusal_precedes_pillow_rng_and_drawing(self):
        patches = _forbid_work()
        with patches[0], patches[1], patches[2], patches[3]:
            for kw, msg in (({"product": "bottel"}, PRODUCT_ERR), ({"background": "grey-wal"}, BACKGROUND_ERR),
                            ({"product": None}, PRODUCT_ERR), ({"background": []}, BACKGROUND_ERR)):
                with self.assertRaises(ValueError) as cm:
                    ns.make_photo(size=SIZE, **kw)
                self.assertEqual(str(cm.exception), msg)
            with self.assertRaises(ValueError) as cm:  # both invalid: product is checked first
                ns.make_photo(product="bottel", background="grey-wal", size=SIZE)
            self.assertEqual(str(cm.exception), PRODUCT_ERR)

    def test_existing_guards_keep_precedence_over_scene_guards(self):
        with self.assertRaises(ValueError) as cm:
            ns.make_photo(product="bottel", background="grey-wal", phone_orientation=3, fmt="GIF", size=SIZE)
        self.assertEqual(str(cm.exception), "phone_orientation must be None, 6 or 8")
        with self.assertRaises(ValueError) as cm:
            ns.make_photo(product="bottel", background="grey-wal", fmt="GIF", size=SIZE)
        self.assertEqual(str(cm.exception), "fmt must be JPEG or PNG")

    def test_transparent_png_still_validates_background(self):
        patches = _forbid_work()
        with patches[0], patches[1], patches[2], patches[3]:
            for bad in ("grey-wal", None, [], ""):
                with self.assertRaises(ValueError) as cm:
                    ns.make_photo(background=bad, size=SIZE, alpha=True, fmt="PNG")
                self.assertEqual(str(cm.exception), BACKGROUND_ERR)
            for o in (6, 8):  # phone orientations do not bypass admission either
                with self.assertRaises(ValueError) as cm:
                    ns.make_photo(background="grey-wal", size=SIZE, phone_orientation=o)
                self.assertEqual(str(cm.exception), BACKGROUND_ERR)


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class DeclaredScenesStillSupported(unittest.TestCase):
    def test_declared_vocabulary_is_unchanged(self):
        self.assertEqual(ns.PRODUCTS, DECLARED_PRODUCTS)
        self.assertEqual(ns.BACKGROUNDS, DECLARED_BACKGROUNDS)

    def test_all_declared_scene_pairs_and_defaults_remain_supported(self):
        for p in DECLARED_PRODUCTS:
            for b in DECLARED_BACKGROUNDS:
                for fmt, want in (("JPEG", "JPEG"), ("PNG", "PNG")):
                    data = ns.make_photo(product=p, background=b, size=SIZE, seed=11, fmt=fmt)
                    im = Image.open(io.BytesIO(data))
                    self.assertEqual((im.format, im.size), (want, SIZE))
                    self.assertEqual(data, ns.make_photo(product=p, background=b, size=SIZE, seed=11, fmt=fmt))
        self.assertEqual(ns.make_photo(size=SIZE, seed=11), ns.make_photo(product="jar", background="white-sheet", size=SIZE, seed=11))

    def test_valid_alpha_phone_and_eight_named_cases_still_render(self):
        rgba = Image.open(io.BytesIO(ns.make_photo(background="grey-wall", size=SIZE, alpha=True, fmt="PNG", seed=3)))
        self.assertEqual((rgba.mode, rgba.size), ("RGBA", SIZE))
        for o in (6, 8):
            im = Image.open(io.BytesIO(ns.make_photo(product="bag", background="red-cloth", size=SIZE, phone_orientation=o, seed=3)))
            self.assertEqual((im.size, im.getexif().get(0x0112)), (SIZE, o))
        names = [n for n, _ in ns.cases()]
        self.assertEqual(len(names), 8)
        for name, kw in ns.cases():
            self.assertIn(kw["product"], DECLARED_PRODUCTS, name)
            self.assertIn(kw["background"], DECLARED_BACKGROUNDS, name)
            small = dict(kw, size=(kw["size"][0] // 5, kw["size"][1] // 5))
            self.assertTrue(ns.make_photo(**small), name)


if __name__ == "__main__":
    unittest.main()
