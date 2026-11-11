"""RF0845-12: synthetic phone JPEGs really serialize the fake GPS IFD. In-memory data only."""
import io
import unittest

from hass import house_style as hs, newitem_render, newitem_synthetic as ns

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

KW = dict(product="jar", background="white-sheet", seed=7, size=(400, 300))


def _gps(data):
    return dict(Image.open(io.BytesIO(data)).getexif().get_ifd(0x8825))


def _jpeg_with(tags, gps=None):
    ex = Image.Exif()
    for k, v in tags.items():
        ex[k] = v
    if gps is not None:
        ex[0x8825] = gps
    out = io.BytesIO()
    Image.new("RGB", (800, 800), (200, 200, 200)).save(out, "JPEG", exif=ex)
    return out.getvalue()


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class SyntheticGps(unittest.TestCase):
    def test_phone_jpeg_six_and_eight_contain_gps_ifd(self):
        for o in (6, 8):
            with self.subTest(o):
                data = ns.make_photo(phone_orientation=o, **KW)
                ex = Image.open(io.BytesIO(data)).getexif()
                self.assertIn(0x8825, ex)
                g = _gps(data)
                self.assertEqual((g[1], g[3]), ("N", "W"))
                self.assertEqual([float(x) for x in g[2]], [35.0, 22.0, 0.0])
                self.assertEqual([float(x) for x in g[4]], [120.0, 51.0, 0.0])
                self.assertEqual(ex[0x010F], "SyntheticCo")
                self.assertEqual(ex[0x0112], o)
                self.assertEqual(data, ns.make_photo(phone_orientation=o, **KW))

    def test_device_metadata_cannot_stand_in_for_gps(self):
        data = _jpeg_with({0x010F: "SyntheticCo", 0x0110: "Phone 0", 0x0132: "2026:11:07 09:30:00"})
        self.assertTrue(ns.has_exif_location(data))
        self.assertEqual(_gps(data), {})

    def test_nonphone_jpeg_stays_metadata_free(self):
        data = ns.make_photo(**KW)
        self.assertEqual(len(Image.open(io.BytesIO(data)).getexif()), 0)

    def test_renderer_strips_actual_generator_gps(self):
        raw = ns.make_photo(phone_orientation=6, size=(1512, 1134))
        self.assertTrue(_gps(raw))  # non-vacuous: the input really carries GPS
        out = newitem_render.render(raw, hs.load_spec())["jpeg"]
        self.assertEqual(_gps(out), {})
        self.assertEqual(len(Image.open(io.BytesIO(out)).getexif()), 0)
        self.assertFalse(ns.has_exif_location(out))

    def test_explicit_gps_only_fixture_is_detected_and_stripped(self):
        raw = _jpeg_with({}, {1: "N", 2: (35.0, 22.0, 0.0), 3: "W", 4: (120.0, 51.0, 0.0)})
        self.assertTrue(_gps(raw))
        out = newitem_render.render(raw, hs.load_spec())["jpeg"]
        self.assertEqual(_gps(out), {})


if __name__ == "__main__":
    unittest.main()
