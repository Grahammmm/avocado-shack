"""AVO-LAUNCH-1 tests: ``sitegen.py --publish DIR`` builds only the website, and the PUBLISHED output carries no
commerce surface, pre-launch copy, private files, contact data or location metadata.

These checks read every file in the published folder, not just the home page: the archived commerce preview passed
the home-page-only catalog check because nothing looked anywhere else. Failure messages name files and counts only,
never matched values (the private research files hold third-party contact details).
Run: python3 -B -m unittest hass.tests.test_publish -v
"""

import contextlib
import hashlib
import io
import json
import re
import struct
import tempfile
import unittest
from pathlib import Path

from hass import sitegen
from hass.content_model import REPO_ROOT, SITE_DIR, load_and_validate

TEXT_EXT = {".html", ".js", ".json", ".css"}
ALLOWED_EXT = TEXT_EXT | {".jpg", ".png", ".webp"}
# Files that exist in storefront-mockup/ and must never be published (named, not just "anything else").
PRIVATE = ("producer-research-log.json", "held-products.json", "community-server.py", "community-qa.py",
           "catalog-only-qa.cjs", "community-ui-qa.cjs", "qa-env.cjs", "README.md", "catalog.js", "catalog.json",
           "shop-data.json", "catalog-extraction.csv", "new-products.json", "completion-new-products.json",
           "producers.json", "desktop.png", "mobile.png", "archive/commerce-preview/index.html",
           "assets/share.jpg", "assets/vegetables.jpg", "assets/pantry.jpg")
# Selectors catalog-only-qa.cjs refuses on the home page, as markup, plus the archived page's surface.
COMMERCE_MARKUP = re.compile(r"""(?:id|class)=["'][^"']*\b(?:bag|boxes|merch|owner|order-preview|price|basket|cart|"""
                             r"""checkout|subtotal)\b|data-add(?![-\w])|data-product(?![-\w])""", re.I)
COMMERCE_WORDS = re.compile(r"\$\s?\d|\bbasket\b|\bcheck ?out\b|\bcart\b|add to (?:bag|basket|cart)|weekly box|"
                            r"\bmerch|\bsubtotal\b|\bpickup\b|online shop|\bprices?\b|\bpricing\b|\bstripe\b|"
                            r"\bpaypal\b|\bshipping\b|\bsku\b|stock & orders|\borders?\b|\bbuy now\b", re.I)
PRELAUNCH = re.compile(r"sandbox|before (?:a public )?launch|during setup|not been checked|not connected|"
                       r"saved locally|local service|local signup|unsubscribe|proposed mailbox|lorem|ipsum|"
                       r"\bTODO\b|\bFIXME\b", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")
PLACEHOLDER_EMAILS = {"you@example.com"}
LOGO_SHA256 = "f958d2890a56b07894f0f53a2826cc9a57fe9c9fcfcef1a91098e419f0277387"  # assets/logo.png, kept unchanged
# Hosts a published page may link to or name (outbound links only; nothing is loaded from them).
SITE_LINK = re.compile(r"""(?:src|href)=["']([^"'#][^"']*)["']""")
JS_PATH = re.compile(r"""['"`(](/(?:assets/[A-Za-z0-9_./-]+|[A-Za-z0-9_-]+\.json))['"`)]""")


def _publish(out):
    content = load_and_validate()
    with contextlib.redirect_stdout(io.StringIO()):
        written = sitegen.publish(content, REPO_ROOT, out)
    return content, written


class PublishedSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / "site"
        cls.content, cls.written = _publish(cls.out)
        cls.files = sorted(p.relative_to(cls.out).as_posix() for p in cls.out.rglob("*") if p.is_file())
        cls.text = {rel: (cls.out / rel).read_text("utf-8") for rel in cls.files if Path(rel).suffix in TEXT_EXT}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_only_the_allowlist_is_published(self):
        images = sorted({p["image"] for p in self.content.active_products()})
        expected = sorted(set(sitegen.PUBLISH_GENERATED + sitegen.PUBLISH_PAGES + sitegen.PUBLISH_STATIC + sitegen.PUBLISH_ASSETS)
                          | set(images) | {"community.json"})
        self.assertEqual(self.files, expected)
        self.assertEqual(sorted(self.written), expected)
        self.assertEqual(len(images), 170)
        self.assertEqual({Path(rel).suffix for rel in self.files} - ALLOWED_EXT, set())
        for rel in PRIVATE:
            with self.subTest(rel=rel):
                self.assertTrue((SITE_DIR / rel).is_file(), "fixture: the private file exists in the working folder")
                self.assertFalse((self.out / rel).exists())
        self.assertFalse((self.out / "archive").exists())

    def test_no_commerce_surface_in_any_published_file(self):
        # Positive control: the same patterns find the archived commerce page in the working folder.
        archived = (SITE_DIR / "archive/commerce-preview/index.html").read_text("utf-8")
        self.assertTrue(COMMERCE_MARKUP.search(archived) and COMMERCE_WORDS.search(archived))
        for rel, text in self.text.items():
            if rel.endswith(".css"):
                continue  # stylesheet selectors are not a visitor surface; markup and copy are checked below
            with self.subTest(rel=rel):
                self.assertEqual(len(COMMERCE_MARKUP.findall(text)), 0, f"commerce markup in {rel}")
                self.assertEqual(len(COMMERCE_WORDS.findall(text)), 0, f"commerce wording in {rel}")

    def test_no_foreign_share_tags_or_retired_domain(self):
        self.assertIn("slofishreport", (SITE_DIR / "archive/commerce-preview/index.html").read_text("utf-8"))
        for rel, text in self.text.items():
            with self.subTest(rel=rel):
                self.assertNotIn("slofishreport", text)
                self.assertNotRegex(text, r"og:url|og:image")

    def test_no_pre_launch_or_internal_copy(self):
        self.assertTrue(PRELAUNCH.search((SITE_DIR / "community-server.py").read_text("utf-8")))  # control
        for rel, text in self.text.items():
            with self.subTest(rel=rel):
                self.assertEqual(len(PRELAUNCH.findall(text)), 0, f"pre-launch or internal wording in {rel}")

    def test_no_contact_details_published(self):
        log = (SITE_DIR / "producer-research-log.json").read_text("utf-8")
        self.assertTrue(EMAIL.search(log) and PHONE.search(log))  # control: the private log is caught
        for rel, text in self.text.items():
            with self.subTest(rel=rel):
                emails = set(EMAIL.findall(text)) - PLACEHOLDER_EMAILS
                self.assertEqual(len(emails), 0, f"{len(emails)} email address(es) in {rel}")
                self.assertEqual(len(PHONE.findall(text)), 0, f"phone number(s) in {rel}")
        club = json.loads(self.text["community.json"])
        self.assertEqual(sorted(club), sorted(sitegen.PUBLIC_COMMUNITY_KEYS))
        self.assertEqual(len(club["routeIdeas"]), 3)

    def test_images_carry_no_camera_or_location_metadata(self):
        for rel in self.files:
            data = (self.out / rel).read_bytes()
            with self.subTest(rel=rel):
                if rel.endswith(".jpg"):
                    self.assertNotIn(b"Exif\x00\x00", data)
                elif rel.endswith(".png"):
                    self.assertNotIn(b"eXIf", data)
                elif rel.endswith(".webp"):
                    self.assertNotIn(b"EXIF", data[:4096])

    def test_hero_image_is_phone_sized(self):
        self.assertLess((self.out / "assets/store.jpg").stat().st_size, 500_000)

    def test_every_local_reference_resolves(self):
        published = set(self.files)
        checked = 0
        for rel, text in self.text.items():
            refs = []
            if rel.endswith(".html"):
                refs = [r for r in SITE_LINK.findall(text) if not re.match(r"[a-z]+:", r)]
            elif rel.endswith(".js"):
                refs = JS_PATH.findall(text)
            for ref in refs:
                if ref.startswith("/api/") or "${" in ref:
                    continue
                path = ref.split("#")[0].split("?")[0]
                target = path.lstrip("/") if path.startswith("/") else (Path(rel).parent / path).as_posix()
                target = target.removeprefix("./")
                if target in ("", "hike") or target.endswith("/"):
                    target = target + "index.html" if target != "hike" else "hike/index.html"
                with self.subTest(ref=ref, page=rel):
                    self.assertTrue(target in published, f"{target} is not published")
                checked += 1
        self.assertGreater(checked, 15)

    def test_header_logo_and_favicon_are_small_copies_and_logo_png_is_unchanged(self):
        def ihdr(path):  # width, height from the PNG header, no image library
            data = path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            return struct.unpack(">II", data[16:24]), len(data)
        self.assertEqual(ihdr(self.out / "assets/logo-header.png")[0], (148, 116))
        self.assertLess(ihdr(self.out / "assets/logo-header.png")[1], 40_960)
        self.assertEqual(ihdr(self.out / "assets/favicon.png")[0], (48, 48))
        self.assertLess(ihdr(self.out / "assets/favicon.png")[1], 8_192)
        self.assertEqual(hashlib.sha256((SITE_DIR / "assets/logo.png").read_bytes()).hexdigest(), LOGO_SHA256)

    def test_pages_use_the_header_logo_and_link_one_resolving_favicon(self):
        self.assertNotIn("assets/logo.png", self.files)
        pages = [rel for rel in self.files if rel.endswith(".html")]
        self.assertEqual(sorted(pages), ["404.html", "hike/index.html", "index.html"])
        for rel in pages:
            with self.subTest(page=rel):
                self.assertNotIn("logo.png", self.text[rel])
                self.assertIn("assets/logo-header.png", self.text[rel])
                icons = re.findall(r"<link rel=\"icon\"[^>]*>", self.text[rel])
                self.assertEqual(len(icons), 1)
                href = re.search(r'href="([^"]+)"', icons[0]).group(1)
                target = href.lstrip("/") if href.startswith("/") else (Path(rel).parent / href).as_posix()
                self.assertEqual(target, "assets/favicon.png")
                self.assertIn(target, self.files)

    def test_publish_refuses_a_folder_inside_the_repo_or_one_with_files(self):
        content = load_and_validate()
        with self.assertRaises(ValueError):
            sitegen.publish(content, REPO_ROOT, REPO_ROOT / "storefront-mockup" / "published")
        self.assertFalse((REPO_ROOT / "storefront-mockup" / "published").exists())
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "stale.txt").write_text("old")
            with self.assertRaises(OSError):
                sitegen.publish(content, REPO_ROOT, Path(tmp))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["stale.txt"])

    def test_cli_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = sitegen.main(["--publish", str(Path(tmp) / "site")])
            self.assertEqual(code, 0)
            self.assertIn(f"published {len(self.files)} files", out.getvalue())


if __name__ == "__main__":
    unittest.main()
