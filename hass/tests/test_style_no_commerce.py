"""AV1222-15: the catalog-only stylesheet carries no dead commerce rules."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "storefront-mockup"
DEAD = re.compile(
    r"\.(?:price|detail-price|cart-lines?|quantity|merch-[\w-]+|weekly-section|box-grid)(?![\w-])")
CLASS_ATTR = re.compile(r"""class\s*=\s*["']([^"']*)["']""")


class StyleNoCommerceTest(unittest.TestCase):
    def test_no_dead_selector_in_style_css(self):
        css = (SITE / "style.css").read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        sels = [s for s in re.findall(r"[^{}]+(?=\{)", css) if not s.lstrip().startswith("@")]
        self.assertTrue(sels)
        bad = [s.strip() for s in sels if DEAD.search(s)]
        self.assertEqual(bad, [])

    def test_live_pages_do_not_use_removed_classes(self):
        token = re.compile(r"^(?:price|detail-price|cart-lines?|quantity|merch-[\w-]+|weekly-section|box-grid)$")
        pages = [SITE / "index.html", SITE / "hike" / "index.html"]
        for page in pages:
            for value in CLASS_ATTR.findall(page.read_text(encoding="utf-8")):
                used = [t for t in value.split() if token.match(t)]
                self.assertEqual(used, [], f"{page.name} uses removed class")


if __name__ == "__main__":
    unittest.main()
