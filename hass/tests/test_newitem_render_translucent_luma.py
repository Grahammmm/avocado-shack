"""RF0211-13: a cut-out that is translucent all over (no pixel above 200/255 coverage) is measured, not given grey 128.

The nearly-opaque mean stays exactly as before whenever such pixels exist; only the empty-sample fallback now uses the
coverage-weighted mean of the visible pixels, so a black, dim or light subject gets its real exposure and dark verdict.
Real in-memory PNGs and the real renderer; no network, no files written.
"""
import io
import statistics
import unittest
from fractions import Fraction
from unittest import mock

from hass import house_style as hs, newitem_render as nr
from hass.ops import photos

try:
    from PIL import Image
    from hass import newitem_synthetic as syn
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

BOX = (150, 80, 449, 719)  # inclusive rectangle on a 600x800 transparent canvas
# Uniform coverage 150: after the ~1.1x Lanczos enlargement no pixel exceeds 200 (at 180..200 edge ringing does, which
# already takes the nearly-opaque path), so this is the shape that used to report the invented 128.
TRANSLUCENT = 150


def cutout(grey, alpha, size=(600, 800), box=BOX):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    if box:
        im.paste((grey, grey, grey, alpha), (box[0], box[1], box[2] + 1, box[3] + 1))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class TranslucentLuma(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = hs.load_spec()
        cls.luma = cls.spec["pictures"]["catalog"]["metrics"]["subject_luma"]

    def render(self, data):
        return nr.render(data, self.spec)

    def test_fallback_weights_coverage_not_sample_count(self):
        gray, cover = [10, 100, 250, 7], [50, 150, 0, 0]  # 250 and 7 are invisible: they must not count
        expected = Fraction(10 * 50 + 100 * 150, 200)  # 77.5; the plain mean of the visible values would be 55
        self.assertEqual(nr._visible_luma(gray, cover), float(expected))
        self.assertNotEqual(nr._visible_luma(gray, cover), statistics.fmean([10, 100]))
        self.assertEqual(nr._visible_luma(gray, [m * 3 for m in cover]), float(expected))  # uniform scaling cancels

    def test_zero_coverage_refuses_without_neutral_default(self):
        with self.assertRaises(nr.Refused) as caught:
            nr._visible_luma([128, 40], [0, 0])
        self.assertEqual(caught.exception.code, "blank")
        for data in (cutout(0, 0, box=None), cutout(0, 80)):  # all transparent, and the existing low-opacity refusal
            with self.subTest(len=len(data)), self.assertRaises(nr.Refused) as caught:
                self.render(data)
            self.assertEqual(caught.exception.code, "blank")

    def test_black_translucent_subject_is_zero_not_midgray(self):
        data = cutout(0, TRANSLUCENT)
        before = bytes(data)
        with mock.patch.object(nr, "_visible_luma", wraps=nr._visible_luma) as seen:
            out = self.render(data)
        seen.assert_called_once()
        self.assertEqual(Image.open(io.BytesIO(data)).getchannel("A").getextrema(), (0, TRANSLUCENT))
        self.assertEqual(out["report"]["subject_luma"], 0.0)
        self.assertEqual(out["report"]["exposure_gain"], 1.25)
        im = Image.open(io.BytesIO(out["jpeg"]))
        self.assertEqual((im.format, im.mode, im.size), ("JPEG", "RGB", (800, 800)))
        self.assertFalse(im.getexif())
        self.assertEqual(self.render(data)["jpeg"], out["jpeg"])  # deterministic
        self.assertEqual(data, before)

    def test_dim_and_light_translucent_subjects_use_measured_exposure(self):
        for grey in (20, 220):
            with self.subTest(grey=grey):
                with mock.patch.object(nr, "_visible_luma", wraps=nr._visible_luma) as seen:
                    report = self.render(cutout(grey, TRANSLUCENT))["report"]
                seen.assert_called_once()
                self.assertAlmostEqual(report["subject_luma"], grey, delta=2.5)  # resampling and straight-colour rounding
                gain = report["exposure_gain"]
                if grey < self.luma["p05"]:
                    self.assertEqual(gain, 1.25)  # the cap
                else:
                    self.assertGreater(grey, self.luma["p95"])
                    self.assertEqual(gain, round(max(.8, self.luma["p95"] / report["subject_luma"]), 2))
                    self.assertLess(gain, 1)

    def test_nonempty_solid_path_retains_original_mean(self):
        for alpha in (201, 255):  # 201 is the first nearly-opaque coverage
            with self.subTest(alpha=alpha), mock.patch.object(nr, "_visible_luma", side_effect=AssertionError("fallback")):
                self.assertAlmostEqual(self.render(cutout(20, alpha))["report"]["subject_luma"], 20, delta=2.5)
        im = Image.new("RGBA", (600, 800), (0, 0, 0, 0))  # mostly translucent dark, one opaque light core: the old mean
        im.paste((20, 20, 20, 150), (150, 80, 450, 720))
        im.paste((180, 180, 180, 255), (250, 300, 350, 500))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        with mock.patch.object(nr, "_visible_luma", side_effect=AssertionError("fallback")):
            self.assertGreater(self.render(buf.getvalue())["report"]["subject_luma"], 150)
        for name, kw in list(syn.cases())[:4]:  # ordinary photos never reach the fallback
            with self.subTest(case=name), mock.patch.object(nr, "_visible_luma", side_effect=AssertionError("fallback")):
                try:
                    self.render(syn.make_photo(**kw))
                except nr.Refused:
                    pass

    def test_read_only_dark_verdict_inherits_true_black_luma(self):
        photos._house.cache_clear()
        try:
            verdict = photos.house_picture(cutout(0, TRANSLUCENT))
        finally:
            photos._house.cache_clear()
        self.assertEqual(verdict["report"]["subject_luma"], 0.0)
        self.assertIn("dark", verdict["problems"])
        self.assertIn("blurry", verdict["problems"])

    def test_inputs_geometry_and_unrelated_refusals_unchanged(self):
        report = self.render(cutout(0, TRANSLUCENT))["report"]
        opaque = self.render(cutout(0, 255))["report"]
        for key in ("input", "isolation", "source", "scale", "box", "rotation_applied"):
            self.assertEqual(report[key], opaque[key], key)
        for data, code in ((cutout(0, TRANSLUCENT, size=(1000, 1)), "too-narrow"), (b"\x89PNG\r\n\x1a\nnot really", None)):
            with self.subTest(code=code), self.assertRaises(Exception) as caught:
                self.render(data)
            if code:
                self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
