"""RF0535-13: a smooth linear background gradient is background, not texture; real texture still falls back."""
from __future__ import annotations

import io
import unittest

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

from hass import newitem_render as nr

SUBJECT = (140, 90, 260, 310)
RED = (210, 45, 35)


def _png(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _ramp(w, h, fn, subject=None, texture=False):
    """RGB image; fn(x, y) -> (r, g, b) floats (rounded); optional subject rectangle and border checker texture."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            c = tuple(round(v) for v in fn(x, y))
            if texture and (x < 30 or y < 30 or x >= w - 30 or y >= h - 30) and (x // 2 + y // 2) % 2:
                c = tuple(max(0, min(255, v + 70)) for v in c)
            px[x, y] = c
    if subject:
        x0, y0, x1, y1 = subject
        for y in range(y0, y1):
            for x in range(x0, x1):
                px[x, y] = RED
    return img


def _probe(kind, subject=None):
    return _ramp(400, 400, {
        "vertical": lambda x, y: (100 + 130 * y / 399,) * 3,
        "horizontal": lambda x, y: (100 + 130 * x / 399,) * 3,
        "diagonal": lambda x, y: (100 + 130 * (x / 399 + y / 399) / 2,) * 3,
    }[kind], subject)


@unittest.skipIf(Image is None, "Pillow required")
class GradientPlane(unittest.TestCase):
    def _fit(self, img, ring):
        return nr._bg_plane(list(img.getdata()), img.width, img.height, ring)

    def test_affine_plane_recovers_axis_and_diagonal_backgrounds(self):
        cases = [
            (320, 240, lambda x, y: (60 + .4 * x, 200 - .5 * y, 120 + .1 * x + .2 * y)),
            (240, 320, lambda x, y: (220 - .3 * x, 80 + .25 * y, 140 - .2 * x - .1 * y)),
            (300, 300, lambda x, y: (100, 110 + .2 * x, 90)),
        ]
        for w, h, fn in cases:
            img = _ramp(w, h, fn)
            plane, noise = self._fit(img, 10)
            self.assertLessEqual(noise, 2)
            for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, h // 3)):
                want = fn(x, y)
                self.assertTrue(all(abs(p - q) <= 2 for p, q in zip(plane(x, y), want)), (x, y, plane(x, y), want))
        flat = _ramp(100, 100, lambda x, y: (120, 130, 140))
        plane, noise = self._fit(flat, 4)
        self.assertEqual(noise, 0)
        self.assertEqual(plane(50, 50), (120, 130, 140))

    def test_ring_centroids_do_not_shrink_the_gradient(self):
        fn = lambda x, y: (60 + .4 * x, 90 + .3 * y, 110 + .2 * x + .1 * y)  # noqa: E731
        img = _ramp(300, 300, fn)
        for ring in (3, 9, 24):
            plane, noise = self._fit(img, ring)
            self.assertLessEqual(noise, 2, ring)
            for x, y in ((0, 0), (299, 299), (0, 299), (299, 0), (150, 150)):
                self.assertTrue(all(abs(p - q) <= 2 for p, q in zip(plane(x, y), fn(x, y))), (ring, x, y))


@unittest.skipIf(Image is None, "Pillow required")
class GradientRender(unittest.TestCase):
    def test_gradient_mask_retains_subject_not_background(self):
        for kind in ("vertical", "horizontal", "diagonal"):
            mask, report = nr.isolate(_probe(kind, SUBJECT))
            self.assertIsNotNone(mask, (kind, report))
            self.assertGreater(mask.getpixel((200, 200)), 240, kind)
            for pt in ((10, 10), (390, 10), (10, 390), (390, 390), (200, 20), (70, 200)):
                self.assertLess(mask.getpixel(pt), 10, (kind, pt))

    def test_full_render_plain_gradient_is_cutout_not_busy(self):
        for kind in ("vertical", "horizontal", "diagonal"):
            data = _png(_probe(kind, SUBJECT))
            out = nr.render(data)
            self.assertEqual(out["report"]["isolation"], "cutout", kind)
            self.assertFalse([r for r in out["report"]["review"] if "not plain" in r or "Could not cut" in r], kind)
            self.assertEqual(out["jpeg"], nr.render(data)["jpeg"])
            im = Image.open(io.BytesIO(out["jpeg"]))
            self.assertEqual((im.format, im.size, im.mode), ("JPEG", (800, 800), "RGB"))
            self.assertFalse(im.getexif())

    def test_real_texture_still_falls_back(self):
        ramp = lambda x, y: (100 + 130 * x / 399,) * 3  # noqa: E731
        img = _ramp(400, 400, ramp, SUBJECT, texture=True)
        mask, report = nr.isolate(img)
        self.assertIsNone(mask)
        self.assertEqual(report["isolation"], "fallback")
        self.assertIn("not plain", report["reason"])
        out = nr.render(_png(img))
        self.assertEqual(out["report"]["isolation"], "fallback")
        self.assertTrue(out["report"]["review"])


if __name__ == "__main__":
    unittest.main()
