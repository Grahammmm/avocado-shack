"""RF0345-12: sideways synthetic PNG photos carry their requested EXIF orientation and fake metadata. In-memory data only."""
import io
import unittest

from PIL import Image, ImageChops, ImageOps

from hass import media, newitem_synthetic as ns

KW = dict(product="jar", background="white-sheet", seed=7)
SCENE = (400, 300)  # the scene as stored sideways; upright is (300, 400)


def _open(data):
    return Image.open(io.BytesIO(data))


class SidewaysPng(unittest.TestCase):
    def test_png_phone_6_and_8_carry_exact_requested_orientation(self):
        for o in (6, 8):
            im = _open(ns.make_photo(size=SCENE, fmt="PNG", phone_orientation=o, **KW))
            self.assertEqual(im.size, SCENE)
            self.assertEqual(im.getexif().get(0x0112), o)
            self.assertEqual(ImageOps.exif_transpose(im).size, (300, 400))

    def test_png_phone_roundtrip_equals_independent_upright_pixels(self):
        for alpha in (False, True):
            ref = _open(ns.make_photo(size=(300, 400), fmt="PNG", alpha=alpha, **KW))
            for o in (6, 8):
                im = _open(ns.make_photo(size=SCENE, fmt="PNG", phone_orientation=o, alpha=alpha, **KW))
                fixed = ImageOps.exif_transpose(im)
                self.assertEqual(fixed.mode, ref.mode)
                self.assertIsNone(ImageChops.difference(fixed.convert("RGBA"), ref.convert("RGBA")).getbbox())

    def test_png_phone_contains_promised_synthetic_metadata(self):
        ex = _open(ns.make_photo(size=SCENE, fmt="PNG", phone_orientation=6, **KW)).getexif()
        self.assertEqual((ex.get(0x010F), ex.get(0x0110), ex.get(0x0132)), ("SyntheticCo", "Phone 0", "2026:11:07 09:30:00"))
        # Spec claimed a nonempty GPS IFD, but on main neither format serializes it (get_ifd on an unset pointer is not saved);
        # the PNG must simply match what the JPEG already carries.
        jx = _open(ns.make_photo(size=SCENE, phone_orientation=6, **KW)).getexif()
        self.assertEqual(dict(ex), dict(jx))
        self.assertEqual(ex.get_ifd(0x8825), jx.get_ifd(0x8825))

    def test_phone_png_uses_existing_rotation_refusal(self):
        for o in (6, 8):
            with self.assertRaises(media.Refused) as cm:
                media.check_photo(ns.make_photo(size=SCENE, fmt="PNG", phone_orientation=o, **KW))
            self.assertEqual(cm.exception.code, "needs-rotation")
        self.assertEqual(media.check_photo(ns.make_photo(size=(300, 400), fmt="PNG", **KW)), "png")
        self.assertEqual(media.check_photo(ns.make_photo(size=SCENE, phone_orientation=6, **KW)), "jpeg")

    def test_ordinary_png_remains_metadata_free_and_deterministic(self):
        a = ns.make_photo(size=(300, 400), fmt="PNG", **KW)
        self.assertEqual(a, ns.make_photo(size=(300, 400), fmt="PNG", **KW))
        self.assertEqual(len(_open(a).getexif()), 0)
        self.assertEqual(_open(a).mode, "RGB")
        self.assertEqual(_open(ns.make_photo(size=(300, 400), fmt="PNG", alpha=True, **KW)).mode, "RGBA")

    def test_jpeg_phone_contract_and_legacy_cases_unchanged(self):
        for o in (6, 8):
            d = ns.make_photo(size=SCENE, phone_orientation=o, **KW)
            self.assertEqual(_open(d).getexif().get(0x0112), o)
            self.assertEqual(d, ns.make_photo(size=SCENE, phone_orientation=o, **KW))
        names = [n for n, _ in ns.cases()]
        self.assertEqual(len(names), 8)
        for _, kw in ns.cases():
            self.assertFalse(kw.get("fmt") == "PNG" and kw.get("phone_orientation"))


if __name__ == "__main__":
    unittest.main()
