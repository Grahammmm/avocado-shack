"""make_photo admits only phone_orientation None, 6 or 8, and refuses the rest before drawing."""
import io
import unittest
from unittest import mock

from hass import newitem_synthetic as ns

MSG = "phone_orientation must be None, 6 or 8"
INVALID = [0, 1, 2, 3, 4, 5, 7, 9, -1, 65536, True, False, 6.0, 8.0, float("nan"), float("inf"),
           "6", "8", "", [], [6], {}, {"a": 1}, object()]


class OrientationAdmission(unittest.TestCase):
    def test_invalid_values_refuse_before_drawing(self):
        for bad in INVALID:
            for fmt in ("JPEG", "PNG"):
                for alpha in (False, True):
                    with self.subTest(bad=repr(bad), fmt=fmt, alpha=alpha), \
                            mock.patch.object(ns, "_background") as bg, mock.patch.object(ns, "_product") as pr:
                        with self.assertRaises(ValueError) as ctx:
                            ns.make_photo(phone_orientation=bad, fmt=fmt, alpha=alpha)
                        self.assertEqual(str(ctx.exception), MSG)
                        bg.assert_not_called()
                        pr.assert_not_called()

    def test_invalid_precedes_pillow_import(self):
        import builtins
        real = builtins.__import__

        def refuse(name, *a, **k):
            if name == "PIL" or name.startswith("PIL."):
                raise AssertionError("Pillow imported")
            return real(name, *a, **k)
        with mock.patch("builtins.__import__", side_effect=refuse):
            with self.assertRaises(ValueError):
                ns.make_photo(phone_orientation=7)

    def test_none_six_eight_still_work(self):
        from PIL import Image
        size = (160, 120)
        self.assertEqual(ns.make_photo(size=size), ns.make_photo(size=size, phone_orientation=None))
        for o in (6, 8):
            data = ns.make_photo(size=size, phone_orientation=o)
            self.assertEqual(data, ns.make_photo(size=size, phone_orientation=o))
            im = Image.open(io.BytesIO(data))
            self.assertEqual(im.getexif()[0x0112], o)
            self.assertEqual(im.size, size)
        self.assertTrue(ns.make_photo(size=size, phone_orientation=6, fmt="PNG"))


if __name__ == "__main__":
    unittest.main()
