"""AV1422-02 tests: the published site carries a slot-free 404.html (shop header and footer, links to the food and the
hiking club, root-relative paths, noindex), and it is not part of render(), so --check and the editor pins are unchanged.
Run: python3 -B -m unittest hass.tests.test_publish_404 -v
"""

import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

from hass import sitegen
from hass.content_model import REPO_ROOT, load_and_validate

TEMPLATE = REPO_ROOT / "hass" / "templates" / "404.html"
REF = re.compile(r"""(?:src|href)=["']([^"']*)["']""")


def non_root_relative(html: str) -> list[str]:
    """References that are neither root-relative (/...), absolute https nor a same-page #anchor; a relative one breaks at depth."""
    return [r for r in REF.findall(html)
            if not ((r.startswith("/") and not r.startswith("//")) or r.startswith("https://") or r.startswith("#"))]


class Published404(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / "site"
        with contextlib.redirect_stdout(io.StringIO()):
            sitegen.publish(load_and_validate(), REPO_ROOT, cls.out)
        cls.html = (cls.out / "404.html").read_text("utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_published_with_header_footer_and_message(self):
        self.assertEqual(sitegen.PUBLISH_PAGES, ("404.html",))
        self.assertIn("<header>", self.html)
        self.assertIn("<footer>", self.html)
        self.assertEqual(self.html.count("<h1>"), 1)
        self.assertIn("<h1>That page isn’t here.</h1>", self.html)
        self.assertIn('<link rel="stylesheet" href="/style.css">', self.html)

    def test_noindex(self):
        self.assertIn('<meta name="robots" content="noindex">', self.html)

    def test_links_to_the_food_and_the_hiking_club(self):
        main = self.html.split("<main", 1)[1].split("</main>", 1)[0]
        self.assertRegex(main, r'<a [^>]*href="/#market"[^>]*>See the food</a>')
        self.assertRegex(main, r'<a [^>]*href="/hike/"[^>]*>Meet the hiking club</a>')

    def test_every_reference_is_root_relative_or_https(self):
        self.assertGreater(len(REF.findall(self.html)), 8)
        self.assertEqual(non_root_relative(self.html), [])

    def test_the_relative_link_check_catches_a_relative_link(self):
        for bad in ('<a href="hike/">x</a>', '<img src="assets/logo.png">', '<a href="../style.css">x</a>',
                    '<a href="//evil.example/x">x</a>', '<a href="http://x.example/">x</a>'):
            with self.subTest(bad=bad):
                self.assertEqual(len(non_root_relative(bad)), 1)

    def test_no_slots_and_no_contact_or_form(self):
        self.assertNotRegex(TEMPLATE.read_text("utf-8"), r"\{\{|\}\}")
        self.assertNotRegex(self.html, r"<form|<input|mailto:|tel:|@")

    def test_not_part_of_render_so_check_and_editor_pins_stay(self):
        rendered = sitegen.render(load_and_validate())
        self.assertNotIn("404.html", "".join(rendered))
        self.assertNotIn("404.html", sitegen.TEMPLATES)
        self.assertFalse((REPO_ROOT / "storefront-mockup" / "404.html").exists())

    def test_check_reports_every_generated_file(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sitegen.main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("ok: 10 generated files", out.getvalue())  # six, plus the four fixed template pages (AVB-19-B2)

    def test_a_slot_in_the_page_is_refused(self):
        with self.assertRaises(sitegen.ContentError):
            sitegen.render_template("<p>{{store.addressLine}}</p>", {})


if __name__ == "__main__":
    unittest.main()
