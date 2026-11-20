"""Fixture checks for word boundaries in extracted maker-site text."""

import unittest

from hass.maker_site import extract


class BreakSpacingTests(unittest.TestCase):
    def test_break_separates_words_without_splitting_the_block(self):
        # Dropping the break glues words; treating it as a block splits the quote.
        for separator in ("<br>", "<br/>", " \n<br>\t "):
            with self.subTest(separator=separator):
                self.assertEqual(extract(f"<p>We make{separator}fruit jam.</p>"),
                                 ["We make fruit jam."])

    def test_breaks_outside_readable_text_are_ignored(self):
        # Unscoped break handling can create a block or insert a space mid-word.
        self.assertEqual(
            extract("<br>outside<p>fruit<script><br></script><style><br></style>"
                    "<button><br>hidden</button>cake</p><br/>outside"),
            ["fruitcake"],
        )

    def test_inline_tags_do_not_insert_spaces(self):
        # Applying break spacing to all tags would split a word across emphasis.
        self.assertEqual(extract("<p><em>fruit</em> jam</p><p>fruit<em>cake</em></p>"),
                         ["fruit jam", "fruitcake"])
