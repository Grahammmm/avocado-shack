"""RF0725-12: a tilted alpha=True synthetic PNG keeps the rotated product's own straight RGB and alpha coverage.

The oracles below are written out by hand (source layer from the real _product + rotate, positions from the documented
seed recipe, source-over arithmetic as plain integers); none of them calls the compositing helper production uses.
"""
import io
import random
import unittest
from unittest import mock

from hass import newitem_synthetic as ns

# Guarded like test_newitem_synthetic.py: Pillow is pinned in CI; the CI planner counts tests before it is installed.
try:
    from PIL import Image, ImageDraw, ImageFont
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def _decode(data):
    return Image.open(io.BytesIO(data)).convert("RGBA")


def _source(product, height, angle):
    layer = ns._product(Image, ImageDraw, ImageFont, product, height)
    return layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC) if angle else layer


def _where(size, share, seed, item):
    """Top-left of the layer, from the documented recipe (an alpha scene draws no background, so rng starts fresh)."""
    w, h = size
    rng = random.Random(seed)
    return (w - item.width) // 2 + rng.randint(-w // 40, w // 40), (h - item.height) // 2 + rng.randint(-h // 60, h // 60)


def _expected(size, share, seed, angle, product="jar"):
    """(scene-sized dict of expected RGBA for covered pixels, source layer, left, top) from the source layer alone."""
    item = _source(product, round(size[1] * share), angle)
    left, top = _where(size, share, seed, item)
    px, want = item.load(), {}
    for y in range(item.height):
        for x in range(item.width):
            if 0 <= x + left < size[0] and 0 <= y + top < size[1]:
                want[(x + left, y + top)] = px[x, y]
    return want, item, left, top


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class TiltedAlpha(unittest.TestCase):
    SIZE, SHARE, SEED = (900, 900), .62, 6

    def _photo(self, angle, **kw):
        kw = {**dict(product="jar", size=self.SIZE, share=self.SHARE, seed=self.SEED, alpha=True, fmt="PNG"), **kw}
        return _decode(ns.make_photo(angle=angle, **kw))

    def test_tilted_alpha_keeps_source_coverage(self):
        for angle in (12, -12):
            with self.subTest(angle=angle):
                want, _, _, _ = _expected(self.SIZE, self.SHARE, self.SEED, angle)
                got = self._photo(angle).load()
                partial = [p for p, v in want.items() if 0 < v[3] < 255]
                self.assertGreater(len(partial), 100)  # a real fractional edge, not a binary one
                bad = [(p, got[p][3], want[p][3]) for p in want if got[p][3] != want[p][3]]
                self.assertEqual(bad[:3], [])
                outside = [(x, y) for y in (0, 450, 899) for x in (0, 899) if (x, y) not in want and got[x, y][3]]
                self.assertEqual(outside, [])

    def test_partial_edge_keeps_straight_rgb(self):
        # Controlled pixel: a half-covered layer pixel lands on transparent black with its own RGB and alpha.
        tiny = Image.new("RGBA", (4, 4), (200, 100, 50, 128))
        with mock.patch.object(ns, "_product", return_value=tiny):
            im = _decode(ns.make_photo(size=(40, 40), share=.1, seed=3, alpha=True, fmt="PNG"))
        left, top = _where((40, 40), .1, 3, tiny)
        self.assertEqual(im.getpixel((left + 1, top + 1)), (200, 100, 50, 128))
        # Actual tilted edge: every visibly covered partial pixel keeps the rotated layer's straight RGB (not darkened).
        for angle in (12, -12):
            with self.subTest(angle=angle):
                want, _, _, _ = _expected(self.SIZE, self.SHARE, self.SEED, angle)
                got = self._photo(angle).load()
                partial = [p for p, v in want.items() if 0 < v[3] < 255]
                bad = [(p, got[p][:3], want[p][:3]) for p in partial if max(abs(a - b) for a, b in zip(got[p][:3], want[p][:3])) > 1]
                self.assertGreater(len(partial), 100)
                self.assertEqual(bad[:3], [])

    def test_partial_alpha_composites_once_on_opaque_control(self):
        bg = (30, 200, 90)
        for angle in (12, -12):
            with self.subTest(angle=angle):
                want, _, _, _ = _expected(self.SIZE, self.SHARE, self.SEED, angle)
                got = self._photo(angle).load()
                picked = [p for p, v in want.items() if 0 < v[3] < 255][::7]
                self.assertGreater(len(picked), 20)
                for p in picked:
                    r, g, b, a = got[p]
                    s = want[p]
                    flat = tuple(round((c * a + k * (255 - a)) / 255) for c, k in zip((r, g, b), bg))
                    once = tuple(round((c * s[3] + k * (255 - s[3])) / 255) for c, k in zip(s[:3], bg))
                    self.assertTrue(all(abs(x - y) <= 1 for x, y in zip(flat, once)), (p, flat, once))

    def test_clipped_tilted_layer_remains_source_over(self):
        size, share, seed, angle = (300, 200), 1.3, 9, 20
        want, item, left, top = _expected(size, share, seed, angle)
        self.assertTrue(left < 0 or top < 0 or left + item.width > size[0] or top + item.height > size[1])  # clipping really occurs
        im = _decode(ns.make_photo(size=size, share=share, angle=angle, seed=seed, alpha=True, fmt="PNG"))
        self.assertEqual(im.size, size)
        got = im.load()
        bad = [(p, got[p][3], v[3]) for p, v in want.items() if got[p][3] != v[3]]
        self.assertEqual(bad[:3], [])
        self.assertTrue(any(0 < v[3] < 255 for v in want.values()))
        self.assertLess(len(want), item.width * item.height)  # part of the layer fell outside the scene


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class Unchanged(unittest.TestCase):
    @staticmethod
    def _old_placement(dest, source, *a, **k):
        """The pre-fix operation (the layer as its own paste mask), standing in for the source-over call."""
        out = dest.copy()
        out.paste(source, (0, 0), source)
        return out

    def test_opaque_path_and_eight_legacy_cases_keep_bytes(self):
        extra = [dict(product="bag", background="dark-wood", size=(600, 450), angle=-17, seed=11),
                 dict(product="bottle", background="grey-wall", size=(500, 500), angle=23, seed=12, fmt="PNG")]
        alpha_names = []
        self.assertEqual(len(ns.cases()), 8)
        for name, kw in [*ns.cases(), *(("opaque", k) for k in extra)]:
            with self.subTest(case=name):
                new = ns.make_photo(**kw)
                if kw.get("alpha"):
                    alpha_names.append(name)
                    with mock.patch.object(Image, "alpha_composite", self._old_placement):
                        old = ns.make_photo(**kw)
                else:  # the opaque path never touches the source-over call
                    with mock.patch.object(Image, "alpha_composite", side_effect=AssertionError("opaque path composites")):
                        old = ns.make_photo(**kw)
                self.assertEqual(new, old)
        self.assertEqual(alpha_names, ["jar-cutout-alpha"])

    def test_untilted_cutout_and_repeated_seed(self):
        kw = dict(ns.cases())["jar-cutout-alpha"]
        data = ns.make_photo(**kw)
        self.assertEqual(data, ns.make_photo(**kw))
        im = _decode(data)
        self.assertEqual(im.size, kw["size"])
        alphas = set(im.getchannel("A").getdata())
        self.assertEqual(alphas, {0, 255})  # binary control: no fractional edge in an untilted cutout
        self.assertEqual(im.getpixel((0, 0))[3], 0)
        self.assertEqual(im.getpixel((kw["size"][0] - 1, kw["size"][1] - 1))[3], 0)
        tilted = dict(kw, angle=12)
        self.assertEqual(ns.make_photo(**tilted), ns.make_photo(**tilted))
