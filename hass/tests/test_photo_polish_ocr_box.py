"""Synthetic OCR rows: invalid word geometry is unreadable, not label evidence."""
import unittest

from hass.tests.test_photo_polish_ocr_tsv import HAVE_PIL, HEAD, WORD, read


def word_at(left, top, width, height):
    return f"5\t1\t1\t1\t1\t1\t{left}\t{top}\t{width}\t{height}\t91\tHoney\n"


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class OcrBoxTests(unittest.TestCase):
    def test_impossible_word_geometry_invalidates_entire_read(self):
        # Inverted extents used to reach the image crop. Dropping a bad row
        # would still leave earlier tokens looking like trustworthy evidence.
        for box in ((10, 10, -8, 24), (10, 10, 80, -8), (10, 10, 0, 24),
                    (10, 10, 80, 0), (-1, 10, 80, 24), (10, -1, 80, 24)):
            for prefix in ("", WORD):
                with self.subTest(box=box, after_valid_word=bool(prefix)):
                    self.assertIsNone(read(HEAD + prefix + word_at(*box)))

    def test_valid_word_at_origin_keeps_floor_scaled_box(self):
        # Zero offsets are legal; odd dimensions keep their existing rounding.
        self.assertEqual(read(HEAD + word_at(0, 0, 81, 25)), [("HONEY", (0, 0, 40, 12))])
