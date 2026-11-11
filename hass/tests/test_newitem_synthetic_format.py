"""make_photo admits only fmt "JPEG" or "PNG", and refuses the rest before any image work."""
import builtins
import io
import unittest
from unittest import mock

from hass import newitem_synthetic as ns

MSG = "fmt must be JPEG or PNG"
INVALID = ["WEBP", "TIFF", "GIF", "JPG", "png", "jpeg", "Png", " PNG", "JPEG ", "",
           None, True, False, 0, 7, 1.5, b"PNG", [], ["PNG"], {}, {"a": 1}, object()]


class FormatAdmission(unittest.TestCase):
    def test_unsupported_formats_refuse_with_fixed_message(self):
        for bad in INVALID:
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ValueError) as ctx:
                    ns.make_photo(size=(160, 120), fmt=bad)
                self.assertEqual(str(ctx.exception), MSG)

    def test_refusal_precedes_pillow_and_drawing(self):
        real = builtins.__import__

        def refuse(name, *a, **k):
            if name == "PIL" or name.startswith("PIL."):
                raise AssertionError("Pillow imported")
            return real(name, *a, **k)
        for kw in ({}, {"alpha": True}, {"phone_orientation": 6}, {"phone_orientation": 8}):
            with self.subTest(kw=kw), mock.patch.object(ns, "_background") as bg, mock.patch.object(ns, "_product") as pr, \
                    mock.patch("builtins.__import__", side_effect=refuse):
                with self.assertRaises(ValueError) as ctx:
                    ns.make_photo(fmt="WEBP", **kw)
                self.assertEqual(str(ctx.exception), MSG)
                bg.assert_not_called()
                pr.assert_not_called()

    def test_invalid_orientation_keeps_priority(self):
        with self.assertRaises(ValueError) as ctx:
            ns.make_photo(phone_orientation=7, fmt="WEBP")
        self.assertEqual(str(ctx.exception), "phone_orientation must be None, 6 or 8")

    def test_supported_formats_decode_and_omitted_is_jpeg(self):
        from PIL import Image
        size = (160, 120)
        for fmt in ("JPEG", "PNG"):
            data = ns.make_photo(size=size, fmt=fmt)
            im = Image.open(io.BytesIO(data))
            self.assertEqual((im.format, im.size), (fmt, size))
            self.assertEqual(data, ns.make_photo(size=size, fmt=fmt))
        self.assertEqual(ns.make_photo(size=size), ns.make_photo(size=size, fmt="JPEG"))
        self.assertEqual(Image.open(io.BytesIO(ns.make_photo(size=size, alpha=True, fmt="PNG"))).mode, "RGBA")

    def test_all_eight_cases_still_render(self):
        from PIL import Image
        cs = ns.cases()
        self.assertEqual(len(cs), 8)
        for name, kw in cs:
            with self.subTest(name=name):
                data = ns.make_photo(**kw)
                self.assertEqual(Image.open(io.BytesIO(data)).format, kw.get("fmt", "JPEG"))


if __name__ == "__main__":
    unittest.main()
