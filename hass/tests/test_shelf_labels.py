"""AV0222-02: SHELF_LABELS is the one shelf-name table and matches the real filter buttons on the site pages.

Run: python3 -m unittest hass.tests.test_shelf_labels -v
"""

import unittest
from html.parser import HTMLParser

from hass.content_model import CATEGORIES, REPO_ROOT, SHELF_LABELS


class _Buttons(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found, self._id = [], None

    def handle_starttag(self, tag, attrs):
        self._id = dict(attrs).get("data-filter") if tag == "button" else None
        if self._id is not None and self._id != "all": self.found.append([self._id, ""])

    def handle_data(self, data):
        if self._id not in (None, "all"): self.found[-1][1] += data

    def handle_endtag(self, tag):
        if tag == "button": self._id = None


class ShelfLabelTests(unittest.TestCase):
    def test_shelf_labels_match_real_filter_buttons(self):
        expected = list(SHELF_LABELS.items())
        for page in ("hass/templates/home/market.html", "storefront-mockup/index.html"):  # AVB-19-B1: the food part's template
            with self.subTest(page=page):
                parser = _Buttons()
                parser.feed((REPO_ROOT / page).read_text(encoding="utf-8"))
                self.assertEqual([tuple(b) for b in parser.found], expected)

    def test_shelf_ids_and_availability_words_are_in_sync(self):
        from hass import sitegen
        from hass.content_model import AVAILABILITY
        self.assertEqual(tuple(SHELF_LABELS), CATEGORIES)
        self.assertTrue(all(SHELF_LABELS.values()))
        self.assertEqual(len(set(SHELF_LABELS.values())), len(SHELF_LABELS))
        self.assertEqual([sitegen.AVAILABILITY_WORDS[a] for a in AVAILABILITY], ["Available today", "Limited", "Sold out"])


if __name__ == "__main__":
    unittest.main()
