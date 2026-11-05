"""AV1222-14: the catalog has exactly one hidden Clear filters button, and the generated page matches the template.

Run: python3 -m unittest hass.tests.test_catalog_clear_filters -v
"""

import re
import unittest
from pathlib import Path

from hass import sitegen

ROOT = Path(__file__).resolve().parents[2]
BUTTON = re.compile(r"<button\b[^>]*\bid=\"clear-filters\"[^>]*>")


class ClearFiltersTests(unittest.TestCase):
    def test_template_and_generated_page_have_one_hidden_button(self):
        for path in ("hass/templates/index.html", "storefront-mockup/index.html"):
            tags = BUTTON.findall((ROOT / path).read_text(encoding="utf-8"))
            self.assertEqual(len(tags), 1, path)
            self.assertIn('type="button"', tags[0], path)
            self.assertRegex(tags[0], r"\shidden[\s>]", path)

    def test_generated_index_is_current(self):
        self.assertEqual(sitegen.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
