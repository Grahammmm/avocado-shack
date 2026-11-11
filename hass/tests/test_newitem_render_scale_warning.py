"""RF1255-12: the small-photo warning names the required enlargement and the renderer's actual cap separately."""
import io
import unittest
from unittest import mock

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

from hass import house_style as hs

if HAVE_PIL:
    from hass import newitem_render, newitem_synthetic as syn

SPEC = hs.load_spec()


def small_warnings(out):
    return [r for r in out["report"]["review"] if r.startswith("The photo is small")]


@unittest.skipUnless(HAVE_PIL, "Pillow needed")
class ScaleWarning(unittest.TestCase):
    def test_small_photo_names_required_and_limited_enlargement(self):
        raw = syn.make_photo(**dict(syn.cases())["bag-bench-small"])
        out = newitem_render.render(raw, SPEC)
        (msg,) = small_warnings(out)
        cap = newitem_render.MAX_UPSCALE
        required = out["report"]["scale"]
        self.assertGreater(required, cap)
        self.assertIn(f"would need {required:.1f} times enlargement", msg)
        self.assertIn(f"I limited it to {cap:.1f} times", msg)
        self.assertNotIn("enlarged", msg)

    def test_applied_resize_is_capped_at_the_limit(self):
        raw = syn.make_photo(**dict(syn.cases())["bag-bench-small"])
        real, seen = Image.Image.resize, []

        def spy(self, size, *a, **k):
            seen.append((self.size, tuple(size)))
            return real(self, size, *a, **k)

        with mock.patch.object(Image.Image, "resize", spy):
            out = newitem_render.render(raw, SPEC)
        cap, required = newitem_render.MAX_UPSCALE, out["report"]["scale"]
        # the product crop was resized by the cap, not by the larger requested factor
        self.assertTrue(any(abs(dst[0] - src[0] * cap) <= 1 for src, dst in seen), seen)
        self.assertFalse(any(abs(dst[0] - src[0] * required) <= 1 for src, dst in seen if src[0] > 100), seen)

    def test_tiny_alpha_cutout_does_not_claim_eightfold_applied_scale(self):
        im = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        im.paste((200, 60, 40, 255), (40, 30, 90, 100))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        out = newitem_render.render(buf.getvalue(), SPEC)
        (msg,) = small_warnings(out)
        required = out["report"]["scale"]
        self.assertGreater(required, 5)
        self.assertIn(f"would need {required:.1f} times enlargement", msg)
        self.assertIn(f"I limited it to {newitem_render.MAX_UPSCALE:.1f} times", msg)

    def test_cap_boundary_only_strictly_above_warns(self):
        raw = syn.make_photo(**dict(syn.cases())["bag-bench-small"])
        required = newitem_render.render(raw, SPEC)["report"]["scale"]
        for cap, warns in ((required + .5, False), (required - .5, True)):
            with self.subTest(cap=cap), mock.patch.object(newitem_render, "MAX_UPSCALE", cap):
                self.assertEqual(bool(small_warnings(newitem_render.render(raw, SPEC))), warns)

    def test_report_scale_stays_uncapped(self):
        raw = syn.make_photo(**dict(syn.cases())["bag-bench-small"])
        self.assertGreater(newitem_render.render(raw, SPEC)["report"]["scale"], newitem_render.MAX_UPSCALE)


if __name__ == "__main__":
    unittest.main()
