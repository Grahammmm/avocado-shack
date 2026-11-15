"""AV1052-03: every published home, /hike and 404 page carries one same-origin Content-Security-Policy meta, early,
with no inline executable script, and the runtimes the policy forced out of the pages ship as published files.

Static checks read the published bytes; the browser case (skipped when PLAYWRIGHT_MODULE is unset) loads the pages in
Chromium and also proves the policy blocks injected execution and foreign resources (hass/tests/fixtures/publish_csp_driver.cjs).
Run: PLAYWRIGHT_MODULE=<playwright> python3 -B -m unittest hass.tests.test_publish_csp -v
"""

import contextlib
import copy
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import notice, sitegen, specials
from hass.content_model import REPO_ROOT, load_and_validate, shop_today

POLICY = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
          "object-src 'none'; base-uri 'self'; form-action 'self'")
META = f'<meta http-equiv="Content-Security-Policy" content="{POLICY}">'
PAGES = ("index.html", "hike/index.html", "404.html")
GENERATED = ("storefront-mockup/index.html", "storefront-mockup/hike/index.html")
RUNTIMES = ("notice.js", "specials.js", "banner.js")
HOSTILE = "Closed </p><script>window.__pwn=1</script><img src=x onerror=\"window.__pwn=2\">"


def _publish(content, out):
    with contextlib.redirect_stdout(io.StringIO()):
        sitegen.publish(content, REPO_ROOT, out)


def _synthetic_content():
    """A copy of the real content with an active notice (hostile text), special, banner and one checked product."""
    content = copy.deepcopy(load_and_validate())
    today = shop_today()
    content.store["notice"] = {"text": HOSTILE.replace("", ""), "until": (today + timedelta(days=30)).isoformat()}
    content.store["specials"] = [{"id": "sp-1", "title": "Synthetic special", "deal": "Two for one", "start": (today - timedelta(days=1)).isoformat(),
                                  "end": (today + timedelta(days=5)).isoformat(), "order": 1}]
    content.store["banner"] = {"text": "Come say hello", "start": today.isoformat(), "end": (today + timedelta(days=3)).isoformat(), "link": "visit"}
    product = content.active_products()[0]
    product["available"], product["available_on"] = "yes", today.isoformat()
    content.store["selection_checked_on"] = today.isoformat()
    return content


class PublishedPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / "site"
        cls.synthetic = Path(cls._tmp.name) / "synthetic"
        _publish(load_and_validate(), cls.out)
        _publish(_synthetic_content(), cls.synthetic)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def pages(self):
        for root in (self.out, self.synthetic):
            for rel in PAGES:
                yield root, rel, (root / rel).read_text("utf-8")

    def test_all_published_pages_have_one_early_exact_policy(self):
        for root, rel, text in self.pages():
            with self.subTest(root=root.name, page=rel):
                head = text.split("</head>")[0]
                self.assertEqual(head.count("Content-Security-Policy"), 1)
                self.assertEqual(head.count(META), 1)
                at = head.index(META)
                for later in ("<link", "<script", "<style"):  # nothing can load before the policy applies
                    self.assertTrue(head.find(later) == -1 or head.index(later) > at, f"{later} before the policy")
                self.assertTrue(head.index('<meta charset="utf-8">') < at)
                for bad in ("unsafe-", "*", "data:", "blob:", "nonce-", "sha256-", "http:", "https:"):
                    self.assertNotIn(bad, POLICY)

    def test_no_executable_inline_script_event_handler_or_inline_style(self):
        for root, rel, text in self.pages():
            with self.subTest(root=root.name, page=rel):
                for attrs, body in re.findall(r"<script\b([^>]*)>(.*?)</script>", text, re.S):
                    if 'type="application/ld+json"' in attrs:
                        json.loads(body)  # inert data, still valid JSON under the policy
                    else:
                        self.assertRegex(attrs, r'^ src="[^"]+"$')
                        self.assertEqual(body, "")
                self.assertNotRegex(text, r"(?i)<[a-z][^>]*\son[a-z]+\s*=")
                self.assertNotRegex(text, r"(?i)javascript:")
                self.assertNotRegex(text, r"(?i)<style\b|<[a-z][^>]*\sstyle\s*=")

    def test_every_script_resolves_to_a_published_file_and_deep_404_uses_root_paths(self):
        for root, rel, text in self.pages():
            with self.subTest(root=root.name, page=rel):
                for src in re.findall(r'<script src="([^"]+)"', text):
                    target = src.lstrip("/") if src.startswith("/") else (Path(rel).parent / src).as_posix()
                    self.assertTrue((root / target).is_file(), f"{src} is not published")
        for src in re.findall(r'(?:src|href)="([^"]+)"', (self.out / "404.html").read_text("utf-8")):
            self.assertTrue(src.startswith(("/", "#")), "the 404 page must work at any depth: " + src)
        for rel in ("index.html", "hike/index.html"):  # the active owner states reach the page as external tags, in place
            text = (self.synthetic / rel).read_text("utf-8")
            self.assertEqual(text.count(notice.BANNER_JS), 1)
        home = (self.synthetic / "index.html").read_text("utf-8")
        self.assertIn(notice.NOTICE_JS + specials.SPECIALS_JS + notice.BANNER_JS + "</body>", home)

    def test_hostile_owner_text_is_literal_text_in_the_page(self):
        home = (self.synthetic / "index.html").read_text("utf-8")
        self.assertNotIn("<script>window.__pwn", home)
        self.assertIn("&lt;script&gt;window.__pwn=1&lt;/script&gt;", home)

    def test_publish_external_runtime_manifest_and_refusal(self):
        content = load_and_validate()
        files = sitegen.publish_files(content, REPO_ROOT)
        for name in RUNTIMES:
            self.assertIn(name, sitegen.PUBLISH_STATIC)
            self.assertEqual(files[name], (REPO_ROOT / "storefront-mockup" / name).read_bytes())
            self.assertNotIn(b"<script", files[name])
        self.assertNotIn("availability.js", files)  # the availability rule already lives in shop.js, not inline
        self.assertEqual(files["notice.js"], (self.out / "notice.js").read_bytes())
        for name in RUNTIMES:
            with self.subTest(refused=name, why="symlink"), mock.patch.object(sitegen, "_linked", lambda site, rel, n=name: rel == n):
                with self.assertRaises(OSError) as raised:
                    sitegen.publish_files(content, REPO_ROOT)
                self.assertIn(name, str(raised.exception))
            real = Path.is_file
            with self.subTest(refused=name, why="missing"), mock.patch.object(Path, "is_file", lambda p, n=name: False if p.name == n else real(p)):
                with self.assertRaises(OSError) as raised:
                    sitegen.publish_files(content, REPO_ROOT)
                self.assertIn(name, str(raised.exception))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(sitegen, "_linked", lambda site, rel: rel == "specials.js"):
            with self.assertRaises(OSError):
                sitegen.publish(content, REPO_ROOT, Path(tmp) / "site")
            self.assertFalse((Path(tmp) / "site").exists(), "nothing is written when a runtime is refused")

    def test_check_detects_policy_drift_in_each_generated_page(self):
        content = load_and_validate()
        rendered = sitegen.render(content)
        self.assertEqual([r for r in GENERATED if META.encode() not in rendered[r]], [])
        self.assertEqual(set(rendered) & {"storefront-mockup/404.html"}, set())  # the 404 page stays publish-only
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, data in rendered.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes(data)
            self.assertEqual(sitegen.diff_paths(rendered, root), [])
            for rel in GENERATED:
                original = (root / rel).read_bytes()
                for drifted in (original.replace(META.encode(), b""),
                                original.replace(b"script-src 'self'", b"script-src 'self' 'unsafe-inline'")):
                    with self.subTest(page=rel, removed=drifted != original and len(drifted) < len(original)):
                        self.assertNotEqual(drifted, original)
                        (root / rel).write_bytes(drifted)
                        self.assertEqual(sitegen.diff_paths(rendered, root), [rel])
                (root / rel).write_bytes(original)
        published_404 = (self.out / "404.html").read_text("utf-8")
        self.assertEqual(published_404.count(META), 1)  # publish builds it from the template, so the template carries the policy


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class BrowserPolicy(unittest.TestCase):
    def test_pages_work_under_the_policy_and_it_blocks_injected_execution_and_foreign_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            normal, synthetic = Path(tmp) / "normal", Path(tmp) / "synthetic"
            _publish(load_and_validate(), normal)
            _publish(_synthetic_content(), synthetic)
            out = subprocess.run(["node", str(Path(__file__).with_name("fixtures") / "publish_csp_driver.cjs")],
                                 input=json.dumps({"normal": str(normal), "synthetic": str(synthetic)}), text=True,
                                 capture_output=True, timeout=600)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        for phrase in ("zero CSP violations", "work under the policy", "are blocked with their directives", "control: without the policy"):
            self.assertIn(phrase, out.stdout)
        print(out.stdout.strip())


if __name__ == "__main__":
    unittest.main()
