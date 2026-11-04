"""RF1050-6 (H10) tests: the label confirm line does not say the brand twice when the read name already begins with
the read brand as whole words (case and spacing ignored); the maker and twin lines still use the brand.
Run: python3 -m unittest hass.tests.test_label_question_brand -v
"""

import unittest

from hass.label_reader import question

TAIL = ". Is that right? Say which product it is either way."


def line(words):
    return f"The label looks like: {words}{TAIL}"


class QuestionBrandTests(unittest.TestCase):
    def test_name_starting_with_the_brand_is_shown_alone(self):
        found = {"name": "Sierra Nevada Pale Ale", "brand": "Sierra Nevada"}
        self.assertEqual(question(found), line("Sierra Nevada Pale Ale"))
        with_category = {**found, "category": "beer"}
        self.assertEqual(question(with_category), line("Sierra Nevada Pale Ale (beer)"))

    def test_case_and_spacing_are_ignored(self):
        for brand in ("sierra  NEVADA", "SIERRA NEVADA", " Sierra\tNevada "):
            with self.subTest(brand):
                found = {"name": "Sierra Nevada Pale Ale", "brand": brand}
                self.assertEqual(question(found), line("Sierra Nevada Pale Ale"))
        self.assertEqual(question({"name": "sierra   nevada Pale Ale", "brand": "Sierra Nevada"}),
                         line("sierra   nevada Pale Ale"))

    def test_whole_words_only(self):
        self.assertEqual(question({"name": "Sierras Best", "brand": "Sierra"}), line("Sierra Sierras Best"))
        self.assertEqual(question({"name": "Sierra NevadaX Ale", "brand": "Sierra Nevada"}),
                         line("Sierra Nevada Sierra NevadaX Ale"))
        # brand inside or at the end of the name is out of scope: unchanged
        self.assertEqual(question({"name": "Pale Ale Sierra", "brand": "Sierra"}), line("Sierra Pale Ale Sierra"))

    def test_other_forms_unchanged(self):
        self.assertEqual(question({"name": "Pale Ale", "brand": "Linn's"}), line("Linn's Pale Ale"))
        self.assertEqual(question({"name": "Pale Ale"}), line("Pale Ale"))
        self.assertEqual(question({"brand": "Linn's"}), line("Linn's"))
        self.assertEqual(question({"category": "beer"}), line("beer"))
        self.assertEqual(question({"brand": "Linn's", "category": "beer"}), line("Linn's (beer)"))
        # a name equal to the brand is not a prefix-plus-more: both words stay (keep() already drops that brand)
        self.assertEqual(question({"name": "Sierra", "brand": "sierra"}), line("sierra Sierra"))

    def test_maker_and_twin_lines_still_use_the_brand(self):
        found = {"name": "Sierra Nevada Pale Ale", "brand": "Sierra Nevada"}
        makers = {"sn": {"name": "Sierra Nevada", "place": "Chico"}}
        products = [{"id": "p-9", "name": "Sierra Nevada Pale Ale", "brand": "Sierra Nevada", "status": "active"}]
        self.assertEqual(question(found, makers, products),
                         line("Sierra Nevada Pale Ale") + " Maker on file: Sierra Nevada."
                         " Already listed: p-9 (Sierra Nevada Pale Ale); reply with that id to update it instead.")
        self.assertEqual(question(found, makers), line("Sierra Nevada Pale Ale") + " Maker on file: Sierra Nevada.")
        held = [{**products[0], "status": "held"}]
        self.assertEqual(question(found, None, held), line("Sierra Nevada Pale Ale"))
        self.assertEqual(found, {"name": "Sierra Nevada Pale Ale", "brand": "Sierra Nevada"})  # found not changed


if __name__ == "__main__":
    unittest.main()
