"""RF2340-11: the cast-shadow step keeps a product's own neutral foot (same colour as the body above it in that column)
and still drops a distinguishable cast shadow. In-memory synthetic images only; geometry is written out literally."""
import io
import unittest
from unittest import mock

from hass import house_style as hs, newitem_render as nr

try:
    from PIL import Image
    from hass import newitem_synthetic as syn
    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

BG = (240, 240, 240)


def scene(*rects, size=(320, 320)):
    """RGB image on BG; each rect is (x0, y0, x1, y1, colour) with inclusive corners."""
    img = Image.new("RGB", size, BG)
    for x0, y0, x1, y1, colour in rects:
        img.paste(colour, (x0, y0, x1 + 1, y1 + 1))
    return img


def coarse(img):
    """(coarse mask, shade mask, report) from the real _coarse at analysis size (a 320 square is analysed 1:1)."""
    m, _plane, shade, _size, _delta, report = nr._coarse(img)
    return m, shade, report


def old_rule():
    """The pre-RF2340-11 behaviour: no candidate is ever vetoed by body continuity."""
    return mock.patch.object(nr, "_continues", return_value=False)


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class ShadowContinuityTests(unittest.TestCase):
    def test_neutral_product_foot_is_not_its_own_shadow(self):
        img = scene((100, 40, 219, 279, (120, 120, 120)))
        m, shade, report = coarse(img)
        self.assertEqual(report["isolation"], "cutout")
        self.assertEqual(m.getbbox(), (100, 40, 220, 280))
        self.assertEqual((m.getpixel((160, 100)), m.getpixel((160, 270))), (255, 255))
        self.assertIsNone(shade.getbbox())
        with old_rule():  # RED on the old rule: the bottom band was moved into the shadow mask
            m_old, shade_old, _ = coarse(img)
        self.assertEqual(m_old.getpixel((160, 270)), 0)
        self.assertEqual(shade_old.getpixel((160, 270)), 255)
        mask, _ = nr.isolate(img)
        for p in ((160, 270), (110, 275), (210, 250), (160, 100)):
            self.assertGreater(mask.getpixel(p), 240, p)
        for p in ((160, 300), (50, 270), (260, 270), (160, 15)):
            self.assertLess(mask.getpixel(p), 10, p)

    def test_neutral_tones_with_body_continuity_survive(self):
        for colour in ((100, 100, 100), (150, 150, 150), (200, 200, 200), (150, 150, 160)):
            with self.subTest(colour):
                self.assertTrue(nr._shadowlike(colour, BG))  # the old rule would take its foot as shadow
                m, shade, _ = coarse(scene((100, 40, 219, 279, colour)))
                self.assertEqual(m.getbbox(), (100, 40, 220, 280))
                self.assertIsNone(shade.getbbox())
        for colour in ((120, 60, 30), (0, 0, 0)):  # controls the old rule never touched: unchanged
            with self.subTest(colour):
                img = scene((100, 40, 219, 279, colour))
                new = coarse(img)
                with old_rule():
                    old = coarse(img)
                self.assertEqual(new[0].getbbox(), (100, 40, 220, 280))
                self.assertEqual((new[0].tobytes(), new[1].tobytes()), (old[0].tobytes(), old[1].tobytes()))

    def test_distinct_cast_shadow_still_removed(self):
        # red product rows 40..259, a wider grey cast shadow rows 260..279 joined to its bottom edge
        img = scene((90, 260, 229, 279, (150, 150, 150)), (100, 40, 219, 259, (200, 40, 40)))
        m, shade, report = coarse(img)
        self.assertEqual(report["isolation"], "cutout")
        self.assertEqual(m.getbbox(), (100, 40, 220, 260))
        self.assertEqual(shade.getbbox(), (90, 260, 230, 280))
        self.assertEqual(m.getpixel((160, 255)), 255)
        mask, _ = nr.isolate(img)
        for p in ((160, 270), (120, 275), (200, 266)):
            self.assertLess(mask.getpixel(p), 10, p)
        for p in ((160, 100), (160, 250)):
            self.assertGreater(mask.getpixel(p), 240, p)

    def test_continuity_tolerance_is_inclusive_and_column_local(self):
        self.assertTrue(nr._continues((132, 120, 108), (120, 120, 120)))
        self.assertFalse(nr._continues((133, 120, 120), (120, 120, 120)))
        self.assertFalse(nr._continues((120, 120, 120), None))
        # band starts at 279 - round(.16 * 239) = 241; columns 100..159 differ from the body by 12, 160..219 by 13
        img = scene((100, 40, 219, 240, (120, 120, 120)), (100, 241, 159, 279, (132, 132, 132)), (160, 241, 219, 279, (133, 133, 133)))
        m, shade, _ = coarse(img)
        self.assertEqual(m.getpixel((130, 270)), 255)
        self.assertEqual(shade.getpixel((130, 270)), 0)
        self.assertEqual(shade.getpixel((190, 270)), 255)
        self.assertEqual(shade.getbbox(), (160, 241, 220, 280))
        # body only over columns 100..159; the same grey in the band under 160..219 has no reference of its own, so
        # the matching colour next door does not save it and the band itself is never its own reference
        m, shade, _ = coarse(scene((100, 40, 159, 240, (120, 120, 120)), (100, 241, 219, 279, (120, 120, 120))))
        self.assertEqual(shade.getbbox(), (160, 241, 220, 280))
        self.assertEqual(m.getpixel((130, 270)), 255)

    def test_reference_selection_does_not_depend_on_removal_order(self):
        # columns 100..159: grey body, a gap, then a red block nearest the band -> red is the reference, grey foot goes
        # columns 160..219: grey body, a long gap down to the band -> that grey is the nearest reference, foot stays
        img = scene((100, 40, 219, 100, (120, 120, 120)), (100, 201, 159, 230, (200, 40, 40)), (100, 241, 219, 279, (120, 120, 120)))
        before = img.tobytes()
        m, shade, _ = coarse(img)
        self.assertEqual(shade.getbbox(), (100, 241, 160, 280))
        self.assertEqual(m.getpixel((190, 270)), 255)
        again = coarse(img)
        self.assertEqual((again[0].tobytes(), again[1].tobytes()), (m.tobytes(), shade.tobytes()))
        self.assertEqual(img.tobytes(), before)
        calls = []
        real = nr._continues
        with mock.patch.object(nr, "_continues", side_effect=lambda c, b: calls.append(b) or real(c, b)):
            coarse(img)
        self.assertEqual(len(calls), 120 * 39)  # one O(1) decision per shadow-like foot candidate, no rescans
        self.assertEqual(set(calls), {(200, 40, 40), (120, 120, 120)})

    def test_render_preserves_corrected_body_and_other_photo_contracts(self):
        spec = hs.load_spec()

        def png(img):
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return buf.getvalue()
        grey = png(scene((100, 40, 219, 279, (120, 120, 120))))
        a, b = nr.render(grey, spec), nr.render(grey, spec)
        self.assertEqual(a["jpeg"], b["jpeg"])
        x0, y0, x1, y1 = a["report"]["box"]
        self.assertAlmostEqual((y1 - y0) / (x1 - x0), 2.0, delta=.05)  # the whole 120x240 body, not 120x201
        out = Image.open(io.BytesIO(a["jpeg"]))
        self.assertEqual((out.format, out.mode, out.size), ("JPEG", "RGB", (800, 800)))
        self.assertFalse(out.getexif())
        self.assertNotIn("icc_profile", out.info)
        controls = [png(scene((100, 40, 219, 279, c))) for c in ((120, 60, 30), (0, 0, 0))]
        alpha = Image.new("L", (320, 320), 0)
        alpha.paste(255, (100, 40, 220, 280))  # a supplied cut-out bypasses _coarse altogether
        controls.append(png(Image.merge("RGBA", (*scene((100, 40, 219, 279, (120, 120, 120))).split(), alpha))))
        corpus = [(name, syn.make_photo(**kw)) for name, kw in syn.cases()]
        new = [nr.render(d, spec) for d in controls] + [nr.render(d, spec) for _, d in corpus]
        with old_rule():
            old = [nr.render(d, spec) for d in controls] + [nr.render(d, spec) for _, d in corpus]
        for i in range(len(controls)):
            self.assertEqual(new[i]["jpeg"], old[i]["jpeg"], i)
        self.assertEqual(len(corpus), 8)
        for (name, _), n, o in zip(corpus, new[len(controls):], old[len(controls):]):
            with self.subTest(name):
                self.assertEqual((n["report"]["isolation"], n["check"]["pass"], len(n["report"]["review"])),
                                 (o["report"]["isolation"], o["check"]["pass"], len(o["report"]["review"])))


if __name__ == "__main__":
    unittest.main()
