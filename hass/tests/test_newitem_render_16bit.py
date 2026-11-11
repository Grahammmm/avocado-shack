"""RF0925-12: unsigned 16-bit grayscale PNG samples keep their tones (fixed full-range scaling) instead of clipping to white.

PNGs are encoded by hand from literal unsigned samples (no Pillow encoder, no production helper in any expectation). Expected
gray values are written out as literals from (s*255+32767)//65535. Picture tests need Pillow.
"""
import io
import struct
import unittest
import zlib

from hass import house_style as hs, newitem_render

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def png16(width, height, samples, key=None, size=None, idat=None):
    """A real 16-bit grayscale PNG (colour type 0) of row-major unsigned samples; key is an optional tRNS sample;
    size overrides the IHDR dimensions and idat the compressed pixel data."""
    rows = b"".join(b"\0" + b"".join(struct.pack(">H", s) for s in samples[y * width:(y + 1) * width]) for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", *(size or (width, height)), 16, 0, 0, 0, 0))
            + (chunk(b"tRNS", struct.pack(">H", key)) if key is not None else b"")
            + chunk(b"IDAT", idat or zlib.compress(rows)) + chunk(b"IEND", b""))


def rect16(inside, outside, w=128, h=128, box=(40, 20, 87, 107)):
    return [inside if box[0] <= i % w <= box[2] and box[1] <= i // w <= box[3] else outside for i in range(w * h)]


def png8(mode, size, data, **save):
    out = io.BytesIO()
    img = Image.frombytes(mode, size, data)
    img.save(out, "PNG", **save)
    return out.getvalue()


def pixels(rgb):
    return list(rgb.getdata())


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class SixteenBitTests(unittest.TestCase):
    def test_real_16bit_png_preserves_fixed_range_samples(self):
        samples = [0, 1, 128, 129, 256, 257, 16384, 32767, 32768, 49152, 65534, 65535]
        gray = [0, 0, 0, 1, 1, 1, 64, 127, 128, 191, 255, 255]  # literal (s*255+32767)//65535, incl. the 128|129 and 32767|32768 rounding edges
        data = png16(len(samples), 1, samples)
        self.assertIn(Image.open(io.BytesIO(data)).mode, newitem_render.GRAY16_MODES)
        rgb, alpha, turned = newitem_render._upright(data)
        self.assertEqual(pixels(rgb), [(g, g, g) for g in gray])
        self.assertEqual((alpha, turned, rgb.mode), (None, False, "RGB"))

    def test_midgray_and_low_contrast_are_not_autostretched(self):
        rgb, *_ = newitem_render._upright(png16(4, 4, [32768] * 16))
        self.assertEqual(set(pixels(rgb)), {(128, 128, 128)})
        rgb, *_ = newitem_render._upright(png16(4, 1, [30000, 30000, 30500, 30500]))
        self.assertEqual(pixels(rgb), [(117, 117, 117)] * 2 + [(119, 119, 119)] * 2)  # still near the middle, not 0..255
        rgb, *_ = newitem_render._upright(png8("L", (3, 1), bytes([0, 128, 255])))  # 8-bit grayscale keeps its exact values
        self.assertEqual(pixels(rgb), [(0, 0, 0), (128, 128, 128), (255, 255, 255)])

    def test_rendered_16bit_subject_matches_8bit_control(self):
        spec = hs.load_spec()
        data = png16(128, 128, rect16(16384, 49152))
        control = png8("L", (128, 128), bytes(rect16(64, 191)))
        rgb, *_ = newitem_render._upright(data)
        self.assertEqual(sorted(set(pixels(rgb))), [(64, 64, 64), (191, 191, 191)])  # not both white
        out = newitem_render.render(data, spec)
        self.assertEqual(out["report"]["isolation"], "cutout")
        self.assertTrue(any("photo is small" in line for line in out["report"]["review"]))  # the control's own genuine warning
        jpeg = Image.open(io.BytesIO(out["jpeg"]))
        self.assertEqual((jpeg.format, jpeg.mode, jpeg.size), ("JPEG", "RGB", (newitem_render.SIZE, newitem_render.SIZE)))
        ref = newitem_render.render(control, spec)
        self.assertEqual(out["jpeg"], ref["jpeg"])
        self.assertEqual(out["report"], ref["report"])
        self.assertEqual(out["jpeg"], newitem_render.render(data, spec)["jpeg"])
        self.assertFalse(jpeg.getexif() or jpeg.info.get("icc_profile") or "exif" in jpeg.info)

    def test_16bit_trns_uses_original_sample_identity(self):
        samples = [49152, 49151, 16384, 49153]  # key, a neighbour that rounds to the same gray 191, product, another neighbour
        rgb, alpha, _ = newitem_render._upright(png16(4, 1, samples, key=49152))
        self.assertEqual(pixels(rgb), [(191,) * 3, (191,) * 3, (64,) * 3, (191,) * 3])
        self.assertEqual(list(alpha.getdata()), [0, 255, 255, 255])
        for key in (1234, None):  # key never used / no tRNS: opaque, no invented alpha
            with self.subTest(key=key):
                rgb, alpha, _ = newitem_render._upright(png16(4, 1, samples, key=key))
                self.assertIsNone(alpha)
                self.assertEqual(pixels(rgb)[2], (64, 64, 64))

    def test_16bit_trns_cutout_renders_as_a_supplied_alpha(self):
        data = png16(128, 128, rect16(16384, 49152), key=49152)
        out = newitem_render.render(data, hs.load_spec())
        self.assertEqual((out["report"]["isolation"], out["report"]["source"]), ("cutout", "alpha channel"))

    def test_ordinary_photo_modes_remain_identical(self):
        rgb, alpha, _ = newitem_render._upright(png8("L", (2, 1), bytes([10, 200])))
        self.assertEqual((pixels(rgb), alpha), ([(10,) * 3, (200,) * 3], None))
        rgb, alpha, _ = newitem_render._upright(png8("LA", (2, 1), bytes([10, 0, 200, 255])))
        self.assertEqual((pixels(rgb), list(alpha.getdata())), ([(10,) * 3, (200,) * 3], [0, 255]))
        rgb, alpha, _ = newitem_render._upright(png8("RGBA", (2, 1), bytes([1, 2, 3, 128, 4, 5, 6, 255])))
        self.assertEqual((pixels(rgb), list(alpha.getdata())), ([(1, 2, 3), (4, 5, 6)], [128, 255]))
        pal = Image.new("P", (2, 1))
        pal.putpalette([9, 8, 7, 1, 2, 3])
        pal.putdata([0, 1])
        out = io.BytesIO()
        pal.save(out, "PNG", transparency=0)
        rgb, alpha, _ = newitem_render._upright(out.getvalue())
        self.assertEqual((pixels(rgb), list(alpha.getdata())), ([(9, 8, 7), (1, 2, 3)], [0, 255]))

    def test_high_depth_refusal_contracts(self):
        bad = png16(8, 8, [30000] * 64, idat=b"this is not zlib data")  # valid chunks and CRCs, so it passes the byte gate
        with self.assertRaises(newitem_render.Refused) as caught:
            newitem_render._upright(bad)
        self.assertEqual(caught.exception.code, "unreadable")
        huge = png16(1, 1, [0], size=(10_000, 6_000))  # 60 MP in the header, one sample of data
        with self.assertRaises(newitem_render.Refused) as caught:
            newitem_render._upright(huge)
        self.assertEqual(caught.exception.code, "too-many-pixels")
        with self.assertRaises(newitem_render.Refused) as caught:
            newitem_render.render(png16(100, 1, [30000] * 100), hs.load_spec())  # 100:1 strip
        self.assertEqual(caught.exception.code, "too-narrow")
        out = newitem_render.render(png16(128, 128, rect16(16384, 49152)), hs.load_spec())
        self.assertEqual(Image.open(io.BytesIO(out["jpeg"])).getexif(), {})  # no EXIF/GPS/device/time in the output


if __name__ == "__main__":
    unittest.main()
