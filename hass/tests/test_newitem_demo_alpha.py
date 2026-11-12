"""RF2150-11: the offline montage composites transparent inputs over the page colour, not hidden RGB or opaque black."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False


@unittest.skipUnless(HAVE_PIL, "Pillow required")
class DemoAlphaTests(unittest.TestCase):
    def setUp(self):
        from hass import newitem_demo as demo
        self.demo = demo

    def px(self, img):  # the tile's centre pixel
        return img.getpixel((self.demo.TILE // 2, self.demo.TILE // 2))

    def test_rgba_transparent_pixels_use_page_not_hidden_rgb(self):
        for hidden in ((0, 0, 0), (255, 0, 0)):
            src = Image.new("RGBA", (40, 40), hidden + (0,))
            before = src.copy()
            self.assertEqual(self.px(self.demo.tile(src, "x")), self.demo.PAGE)
            self.assertEqual((src.mode, src.tobytes()), (before.mode, before.tobytes()))
        self.assertEqual(self.px(self.demo.tile(Image.new("RGBA", (40, 40), (10, 20, 30, 255)), "x")), (10, 20, 30))

    def test_fractional_alpha_composites_exactly_once(self):
        got = self.demo._on_page(Image.new("RGBA", (2, 2), (200, 40, 20, 128))).getpixel((0, 0))
        self.assertEqual(got, (222, 140, 125))
        for a in (1, 254):
            got = self.demo._on_page(Image.new("RGBA", (2, 2), (200, 40, 20, a))).getpixel((0, 0))
            want = [(c * a + p * (255 - a)) / 255 for c, p in zip((200, 40, 20), self.demo.PAGE)]
            for g, w in zip(got, want):
                self.assertLessEqual(abs(g - w), 1)

    def test_palette_and_luminance_alpha_are_composited(self):
        pal = Image.new("P", (4, 4), 0)
        pal.putpalette([0, 0, 0] + [255, 255, 255] * 255)
        pal.info["transparency"] = 0
        self.assertEqual(self.demo._on_page(pal).getpixel((0, 0)), self.demo.PAGE)
        self.assertEqual(self.demo._on_page(Image.new("LA", (4, 4), (0, 0))).getpixel((0, 0)), self.demo.PAGE)
        self.assertEqual(self.demo._on_page(Image.new("LA", (4, 4), (255, 255))).getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(self.demo._on_page(Image.new("P", (4, 4), 0)).mode, "RGB")
        self.assertEqual(self.demo._on_page(Image.new("L", (4, 4), 90)).getpixel((0, 0)), (90, 90, 90))
        self.assertEqual(self.demo._on_page(Image.new("RGB", (4, 4), (1, 2, 3))).getpixel((0, 0)), (1, 2, 3))

    def test_orientation_precedes_page_composition(self):
        for tag in (6, 8):
            src = Image.new("RGBA", (60, 20), (0, 0, 255, 255))
            ex = Image.Exif()
            ex[0x0112] = tag
            src.info["exif"] = ex.tobytes()
            out = self.demo.tile(src, "x")
            self.assertEqual(out.getpixel((self.demo.TILE // 2, 100)), (0, 0, 255))  # tall footprint
            self.assertEqual(out.getpixel((self.demo.TILE // 2 - 40, self.demo.TILE // 2)), self.demo.PAGE)
            self.assertEqual(src.size, (60, 20))

    def test_real_main_keeps_transparency_in_reference_and_before(self):
        demo = self.demo
        buf = io.BytesIO()
        Image.new("RGBA", (260, 260), (0, 0, 0, 0)).save(buf, "PNG")
        case = ("jar-dark-wood", dict(fmt="PNG"))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "demo"
            ref = Path(td) / "ref.png"
            Image.new("RGBA", (260, 260), (0, 0, 0, 0)).save(ref)
            prods = [{"category": "pantry", "name": f"p{i}", "image": "ref.png"} for i in range(13)]
            content = mock.Mock()
            content.active_products.return_value = prods
            fake_render = {"jpeg": b"", "report": {"isolation": "x"}, "check": {"score": 1, "pass": True, "checks": []}}
            jb = io.BytesIO()
            Image.new("RGB", (260, 260), (9, 9, 9)).save(jb, "JPEG")
            fake_render["jpeg"] = jb.getvalue()
            with mock.patch.object(demo, "OUT", out), mock.patch.object(demo, "load_content", return_value=content), \
                    mock.patch.object(demo.hs, "SITE", Path(td)), mock.patch.object(demo, "SHOW", ("jar-dark-wood",)), \
                    mock.patch.object(demo.syn, "cases", return_value=[case]), \
                    mock.patch.object(demo.syn, "make_photo", return_value=buf.getvalue()), \
                    mock.patch.object(demo.newitem_render, "render", return_value=fake_render):
                self.assertEqual(demo.main(), 0)
            sheet = Image.open(out / "before-after.png").convert("RGB")
            self.assertEqual(sheet.size, (4 * demo.TILE, demo.TILE + 22))
            for col in (0, 1, 2):  # two catalog references and BEFORE
                self.assertEqual(sheet.getpixel((col * demo.TILE + 130, 130)), demo.PAGE, col)
            self.assertEqual(json.loads((out / "drafts.json").read_text("utf-8")).keys(), {"jar-dark-wood"})
            self.assertTrue((out / "synthetic" / "jar-dark-wood.png").exists())


if __name__ == "__main__":
    unittest.main()
