"""RF1831-13: TillDesk.parse refuses every str.splitlines line boundary inside a message, not only LF.
Run: python3 -B -m unittest hass.tests.test_clover_chat_line_separators
"""
import tempfile
import unittest

from hass.clover import chat
from hass.tests.test_clover_chat import BLOCK

SEPARATORS = ("\n", "\r", "\r\n", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")


class LineSeparatorTests(unittest.TestCase):
    def setUp(self):
        self.reads = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.desk = chat.TillDesk(self.tmp.name, BLOCK, read=lambda *a, **k: (self.reads.append(a), (None, True))[1])

    def test_internal_line_boundaries_are_not_till_requests(self):
        for sep in SEPARATORS:
            with self.subTest(sep=sep):
                self.assertIsNone(self.desk.parse(f"how many synthetic{sep}apples do we have"))
        self.assertEqual(self.reads, [])

    def test_all_parser_branches_share_the_raw_line_guard(self):
        for sep in SEPARATORS:
            for text in (f"what's{sep}low stock", f"is anything{sep}low", f"add apples{sep}to the till", f"received{sep}12 apples"):
                with self.subTest(sep=sep, text=text):
                    self.assertIsNone(self.desk.parse(text))
        self.assertEqual(self.reads, [])

    def test_horizontal_tabs_and_single_line_controls_still_parse(self):
        self.assertEqual(self.desk.parse("how many\tsynthetic  apples do we have"), ("how_many", "synthetic apples"))
        self.assertEqual(self.desk.parse("what's low stock"), ("low",))
        self.assertEqual(self.desk.parse("add apples to the till"), ("write",))
        self.assertEqual(self.desk.parse("is synthetic apples sold out"), ("sold_out", "synthetic apples"))

    def test_outer_strip_and_cleaned_length_contract_survive(self):
        for pad in ("\n", "\r\n", "\u2028", " \t"):
            with self.subTest(pad=pad):
                self.assertEqual(self.desk.parse(f"{pad}how many synthetic apples do we have{pad}"), ("how_many", "synthetic apples"))
        self.assertIsNone(self.desk.parse("how many " + "a" * 200))


if __name__ == "__main__":
    unittest.main()
