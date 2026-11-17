"""photo_polish.words: malformed OCR TSV is unreadable (None), never an empty label. Synthetic data, patched subprocess."""
import io
import unittest
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from hass import photo_polish

HEAD = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
WORD = "5\t1\t1\t1\t1\t1\t10\t20\t80\t24\t91\tHoney\n"

REAL_WORDS = photo_polish.words


def read(stdout, scale=2):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "PNG")
    done = SimpleNamespace(returncode=0, stdout=stdout)
    with mock.patch.object(photo_polish.shutil, "which", return_value="/usr/bin/tesseract"), \
            mock.patch.object(photo_polish.subprocess, "run", return_value=done):
        return REAL_WORDS(buf.getvalue(), scale)


class OcrTsvTests(unittest.TestCase):
    def test_truncated_tsv_row_is_unreadable_not_exception(self):
        for row in ("5\t1\t1\t1\t1\t1\t10\t20\t80\t24\t91\n", "5\t1\t1\n", "5\n"):
            with self.subTest(row=row):
                self.assertIsNone(read(HEAD + row))

    def test_invalid_numeric_tsv_is_unreadable_not_empty(self):
        for row in ("5\t1\t1\t1\t1\t1\tbad\t20\t80\t24\t91\tHoney\n", "5\t1\t1\t1\t1\t1\t10\t20\t80\t24\tnan\tHoney\n",
                    "5\t1\t1\t1\t1\t1\t10\t20\t80\t24\tinf\tHoney\n", "5\t1\t1\t1\t1\t1\t10\t20\t80\t24\t-inf\tHoney\n"):
            with self.subTest(row=row):
                self.assertIsNone(read(HEAD + row))
                self.assertIsNone(read(HEAD + WORD + row))  # no partial evidence from the valid word

    def test_tsv_header_and_empty_controls(self):
        self.assertIsNone(read("level\tpage_num\tblock_num\n" + WORD))
        self.assertIsNone(read(HEAD.replace("text", "txt") + WORD))
        self.assertEqual(read(HEAD), [])
        rows = "1\t1\t0\t0\t0\t0\t0\t0\t800\t600\t-1\t\n\n2\t1\t1\t0\t0\t0\t0\t0\t80\t60\t-1\t\n"
        self.assertEqual(read(HEAD + rows + "5\t1\t1\t1\t1\t1\t10\t20\t80\t24\t12\tHoney\n"), [])

    def test_valid_word_keeps_token_and_scaled_box(self):
        self.assertEqual(read(HEAD + WORD), [("HONEY", (5, 10, 40, 12))])
        self.assertEqual(read(HEAD + WORD, 1), [("HONEY", (10, 20, 80, 24))])

    def test_malformed_tsv_rejects_gate_as_ocr(self):
        bad = HEAD + "5\t1\t1\t1\t1\t1\t10\t20\t80\t24\t91\n"
        made = {"jpeg": b"framed", "check": {"pass": True, "hard_failures": []}}
        fake = SimpleNamespace(size=(800, 800))
        with mock.patch.object(photo_polish.media, "sniff", return_value="png"), \
                mock.patch.object(photo_polish.newitem_render, "_decode", return_value=fake), \
                mock.patch.object(photo_polish, "frame", return_value=made), \
                mock.patch.object(photo_polish, "match", return_value={"match": 1.0, "hue_shift": 0, "chroma": 0,
                                                                        "_map": None}), \
                mock.patch.object(photo_polish, "photo_words", return_value=[]), \
                mock.patch.object(photo_polish, "words", lambda framed, scale=2: read(bad, scale)):
            out = photo_polish.gate(b"orig", b"edit")
        self.assertEqual((out["ok"], out["code"], out["jpeg"]), (False, "ocr", None))


if __name__ == "__main__":
    unittest.main()
