"""RF1406-1: the catalog and /hike pages carry one <noscript> line for visitors without JavaScript.

Reads the generated pages only. Wording is held to test_publish's own regexes (imported, not copied).
Run: python3 -B -m unittest hass.tests.test_noscript -v
"""

import re
import unittest

from hass.content_model import SITE_DIR
from hass.tests.test_publish import COMMERCE_WORDS, PRELAUNCH

NOSCRIPT = re.compile(r"<noscript>(.*?)</noscript>", re.S)
PAGES = ("index.html", "hike/index.html")


class NoscriptLine(unittest.TestCase):
    def test_each_page_has_one_clean_noscript(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                found = NOSCRIPT.findall((SITE_DIR / rel).read_text("utf-8"))
                self.assertEqual(len(found), 1, f"{rel}: noscript count")
                text = re.sub(r"<[^>]+>", "", found[0])
                self.assertIn("JavaScript", text)
                self.assertEqual(len(COMMERCE_WORDS.findall(text)), 0, f"commerce wording in {rel}")
                self.assertEqual(len(PRELAUNCH.findall(text)), 0, f"pre-launch wording in {rel}")

    def test_home_line_points_to_an_existing_visit_id(self):
        html = (SITE_DIR / "index.html").read_text("utf-8")
        target = re.findall(r'href="#([^"]+)"', NOSCRIPT.search(html).group(1))
        self.assertEqual(target, ["visit"])
        self.assertEqual(len(re.findall(r'\bid="visit"', html)), 1)

    def test_shared_word_guards_would_catch_drift(self):
        for bad in ("Place an order here.", "See the prices.", "This is a sandbox."):
            self.assertTrue(COMMERCE_WORDS.search(bad) or PRELAUNCH.search(bad), bad)


if __name__ == "__main__":
    unittest.main()
