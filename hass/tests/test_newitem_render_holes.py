"""RF0755-11: the renderer fills only ENCLOSED mask holes; every border-connected background region stays background.

Binary-mask fixtures are literal and written by hand (no expected mask comes from the production helper). Picture tests need Pillow.
"""
import io
import unittest

from hass import house_style as hs, newitem_render

try:
    from PIL import Image
    from hass import newitem_synthetic as syn
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

BG, RED = (245, 245, 245), (200, 40, 35)


def mask_of(*rows):
    """L image from rows of '#' (subject, 255) and '.' (background, 0)."""
    w = len(rows[0])
    return Image.frombytes("L", (w, len(rows)), bytes(255 if c == "#" else 0 for row in rows for c in row))


def rows_of(m):
    return ["".join("#" if m.getpixel((x, y)) else "." for x in range(m.width)) for y in range(m.height)]


def photo(box, size=(400, 400)):
    """PNG bytes: plain background with one red rectangle (inclusive pixel box)."""
    img = Image.new("RGB", size, BG)
    img.paste(RED, (box[0], box[1], box[2] + 1, box[3] + 1))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def samples(mask, points):
    return [mask.getpixel(p) for p in points]


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class HoleFillTests(unittest.TestCase):
    def test_two_border_background_components_are_both_exterior(self):
        for box, pts in (((180, 0, 219, 399), [(20, 200), (200, 200), (380, 200)]),  # stripe crossing top and bottom
                         ((0, 180, 399, 219), [(200, 20), (200, 200), (200, 380)])):  # transposed
            with self.subTest(box=box):
                data = photo(box)
                mask, report = newitem_render.isolate(Image.open(io.BytesIO(data)).convert("RGB"))
                self.assertEqual(report["isolation"], "cutout")
                left, mid, right = samples(mask, pts)
                self.assertLess(left, 10)
                self.assertGreater(mid, 240)
                self.assertLess(right, 10)  # the second exterior region is not the product
                self.assertLess(report["area"], .2)
                out = newitem_render.render(data, hs.load_spec())
                self.assertEqual(out["report"]["isolation"], "cutout")
                self.assertEqual(out["jpeg"], newitem_render.render(data, hs.load_spec())["jpeg"])

    def test_horizontal_split_and_all_border_seeds(self):
        def notched(*sides):  # all subject, a 3x2 background notch on each named border, one enclosed pocket in the middle
            g = [["#"] * 9 for _ in range(9)]
            for x in (3, 4, 5):
                for y in (0, 1):
                    if "top" in sides: g[y][x] = "."
                    if "bottom" in sides: g[8 - y][x] = "."
                    if "left" in sides: g[x][y] = "."
                    if "right" in sides: g[x][8 - y] = "."
            g[4][4] = "."
            return ["".join(r) for r in g]
        for sides in (("top",), ("bottom",), ("left",), ("right",), ("top", "bottom", "left", "right")):
            with self.subTest(sides=sides):
                src = notched(*sides)
                got = rows_of(newitem_render._fill_holes(mask_of(*src)))
                want = [r for r in src]
                want[4] = want[4][:4] + "#" + want[4][5:]  # only the pocket fills
                self.assertEqual(got, want)

    def test_foreground_at_top_left_does_not_disable_hole_fill(self):
        got = rows_of(newitem_render._fill_holes(mask_of(
            "##.....",
            "##.###.",
            "...#.#.",
            "...###.",
            ".......")))
        self.assertEqual(got, ["##.....",
                               "##.###.",
                               "...###.",
                               "...###.",
                               "......."])

    def test_enclosed_hole_fills_but_open_channel_does_not(self):
        closed = [".......",
                  ".#####.",
                  ".#...#.",
                  ".#...#.",
                  ".#...#.",
                  ".#####.",
                  "......."]
        filled = [".......", ".#####."] + [".#####."] * 3 + [".#####.", "......."]
        self.assertEqual(rows_of(newitem_render._fill_holes(mask_of(*closed))), filled)
        opened = list(closed)
        opened[3] = ".....#."  # a one-cell four-connected channel from the border into the interior
        self.assertEqual(rows_of(newitem_render._fill_holes(mask_of(*opened))), opened)

    def test_diagonal_contact_uses_four_connectivity(self):
        got = rows_of(newitem_render._fill_holes(mask_of(
            ".....",
            "..#..",
            ".#.#.",
            "..#..",
            ".....")))
        self.assertEqual(got, [".....", "..#..", ".###.", "..#..", "....."])  # the pocket meets the exterior only diagonally: filled

    def test_existing_single_exterior_and_photo_contracts_unchanged(self):
        data = photo((140, 20, 259, 379))
        mask, report = newitem_render.isolate(Image.open(io.BytesIO(data)).convert("RGB"))
        self.assertEqual(report["isolation"], "cutout")
        left, mid, right = samples(mask, [(20, 200), (200, 200), (380, 200)])
        self.assertLess(left, 10)
        self.assertGreater(mid, 240)
        self.assertLess(right, 10)
        spec = hs.load_spec()
        for name, kwargs in syn.cases():
            with self.subTest(name):
                raw = syn.make_photo(**kwargs)
                out = newitem_render.render(raw, spec)
                busy = name in ("jar-dark-wood", "bag-red-cloth")
                self.assertEqual(out["report"]["isolation"], "fallback" if busy else "cutout")
                self.assertEqual(out["jpeg"], newitem_render.render(raw, spec)["jpeg"])
                got = Image.open(io.BytesIO(out["jpeg"]))
                self.assertEqual((got.mode, got.size), ("RGB", (800, 800)))
                self.assertFalse(syn.has_exif_location(out["jpeg"]))


if __name__ == "__main__":
    unittest.main()
