"""AV1104-03 (H13): the weekly hours rule (``sitegen.parse_hours``) and the data slot the page script reads.

The Open now / Closed now sentence itself is worked out in the visitor's browser (storefront-mockup/script.js) and is
checked there by storefront-mockup/catalog-only-qa.cjs against pages from hass/tests/visit_hours_fixtures.py.
Run: python3 -B -m unittest hass.tests.test_visit_hours -v
"""

import dataclasses
import html
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from hass import notice, sitegen
from hass.content_model import REPO_ROOT, load_content
from hass.tests import visit_hours_fixtures

INDEX, HIKE = sitegen.SITE_PREFIX + "index.html", sitegen.SITE_PREFIX + "hike/index.html"
MAIN = ["Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday"]
WORK = {"opens": 540, "closes": 1080}
MAIN_WEEK = [WORK] * 5 + [{"opens": 540, "closes": 1020}, {"closed": True}]


class ParseHoursTests(unittest.TestCase):
    def test_parse_hours_main_and_dash_variants(self):
        self.assertEqual(sitegen.parse_hours(MAIN), {"days": MAIN_WEEK, "errors": []})
        self.assertEqual(sitegen.parse_hours(load_content().store["hours"]), {"days": MAIN_WEEK, "errors": []})
        for lines in (["Monday-Friday 9am-6pm", "Saturday 9am-5pm · Closed Sunday"],
                      ["Monday – Friday  9am – 6pm", "  Saturday 9am–5pm  ·  Closed   Sunday  "],
                      ["Monday–Friday 9am–6pm · Saturday 9am–5pm", "Closed Sunday"],
                      ["Closed Sunday", "Saturday 9am-5pm", "Monday-Friday 9am-6pm"]):
            with self.subTest(lines=lines):
                self.assertEqual(sitegen.parse_hours(lines), {"days": MAIN_WEEK, "errors": []})
        self.assertEqual(sitegen.parse_hours(["Monday 9:30am-12pm · Tuesday 12am-11:59pm · Wednesday 12pm-12:30pm",
                                              "Closed Thursday-Friday"])["days"],
                         [{"opens": 570, "closes": 720}, {"opens": 0, "closes": 1439}, {"opens": 720, "closes": 750},
                          {"closed": True}, {"closed": True}, None, None])
        self.assertEqual(sitegen.parse_hours(["Closed Monday–Sunday"])["days"], [{"closed": True}] * 7)

    def test_parse_hours_rejects_whole_lines_without_partial_schedule(self):
        good = MAIN[0]
        bad = ["Saturday by appointment", "Mon–Fri 9am–6pm", "Monday & Tuesday 9am–6pm", "Monday, Tuesday 9am–6pm", "Monday–Friday",
               "Monday 9am–6pm ·", "· Monday 9am–6pm", "Monday 9am–6pm · · Tuesday 9am–6pm", "Monday 9am–6pm.", "Monday 9am–6pm (all week)",
               "<b>Monday</b> 9am–6pm", "monday 9am–6pm", "Monday 9AM–6PM", "Monday 9 am–6pm", "Monday 9am–6 pm", "Monday 09am–6pm",
               "Monday 9:5am–6pm", "Monday 9:60am–6pm", "Monday 13am–6pm", "Monday 0am–6pm", "Monday 9–6pm", "Monday 09:00–18:00",
               "Monday 9am to 6pm", "Monday 9am–6pm Tuesday 9am–6pm", "Monday9am–6pm", "Closed", "closed Sunday", "Closed Sun",
               "Closed Sunday today", "Monday 6pm–9am", "Monday 9am–9am", "Monday 10pm–2am", "Monday 12pm–12am", "Friday–Monday 9am–6pm",
               "Monday–Monday 9am–6pm", "Sunday–Monday 9am–6pm", "Monday ٩am–6pm", "Monday 9am—6pm"]
        for text in bad:
            with self.subTest(text=text):
                self.assertEqual(sitegen.parse_hours([text]), {"days": None, "errors": [{"line": 1, "text": text}]})
                self.assertEqual(sitegen.parse_hours([good, text, "Saturday 9am–5pm"])["days"], None)  # never the valid remainder
        self.assertEqual(sitegen.parse_hours(["Monday 9am-5pm", "Monday 9am-5pm"]),  # even an equal repeat; the later line is blamed
                         {"days": None, "errors": [{"line": 2, "text": "Monday 9am-5pm"}]})
        self.assertEqual(sitegen.parse_hours([good, "Friday 9am–6pm"])["errors"], [{"line": 2, "text": "Friday 9am–6pm"}])
        self.assertEqual(sitegen.parse_hours(["Monday 9am–5pm · Closed Monday"])["errors"], [{"line": 1, "text": "Monday 9am–5pm · Closed Monday"}])
        self.assertEqual(sitegen.parse_hours(["Closed Monday–Tuesday", "Tuesday 9am–5pm"])["errors"], [{"line": 2, "text": "Tuesday 9am–5pm"}])
        self.assertEqual(sitegen.parse_hours(["nope", good, "Monday 9am–5pm", "also nope"])["errors"],  # every bad line, in order
                         [{"line": 1, "text": "nope"}, {"line": 3, "text": "Monday 9am–5pm"}, {"line": 4, "text": "also nope"}])

    def test_parse_hours_never_raises_on_odd_input(self):
        for odd in (None, "Monday 9am-5pm", 5, {}, ("Monday 9am-5pm",), []):
            with self.subTest(odd=odd):
                self.assertEqual(sitegen.parse_hours(odd), {"days": None, "errors": []})
        result = sitegen.parse_hours([None, 7, MAIN[0]])
        self.assertEqual((result["days"], result["errors"]), (None, [{"line": 1, "text": None}, {"line": 2, "text": 7}]))


def pages():
    return visit_hours_fixtures.build()


def node(page):
    found = re.findall(r'<p class="micro visit-open-status" hidden data-weekly-hours="([^"]*)"></p>', page)
    return json.loads(html.unescape(found[0])) if found else None


class RenderPublishTests(unittest.TestCase):
    def test_hours_data_render_publish_and_no_inline(self):
        content = load_content()
        files = sitegen.render(content)
        page = files[INDEX].decode("utf-8")
        self.assertEqual(node(page), MAIN_WEEK)  # the weekly times as data, through entity decoding and JSON
        self.assertEqual(page.count("visit-open-status"), 1)
        self.assertNotRegex(page, r"Open now|Closed now")  # never a finished sentence at generation
        status = re.search(r'<p class="micro visit-open-status"[^>]*></p>', page).group(0)
        self.assertNotRegex(status, r"\son\w+=|<script")
        self.assertIn("<p>Monday–Friday 9am–6pm<br>Saturday 9am–5pm · Closed Sunday</p>" + status, page)  # hours bytes kept, status directly below
        self.assertEqual(HIKE in files and b"visit-open-status" in files[HIKE], False)  # the hike page has no slot
        self.assertEqual(sorted(k for k, v in files.items() if b"visit-open-status" in v), [INDEX])
        self.assertIn("script.js", sitegen.PUBLISH_STATIC)  # the runtime already ships; no new public file or allowlist entry
        executable = re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*ld\+json)[^>]*>", page)
        self.assertEqual(executable, [])  # no inline code at all on the canonical page
        self.assertEqual((REPO_ROOT / INDEX).read_bytes(), files[INDEX])  # the committed page is the generated one
        self.assertEqual((REPO_ROOT / HIKE).read_bytes(), files[HIKE])

    def test_unreadable_hours_publish_no_status_and_render_safely(self):
        cases = pages()
        for name in ("unreadable", "unreadable_first"):
            with self.subTest(name=name):
                self.assertNotIn("visit-open-status", cases[name])
                self.assertNotIn("data-weekly-hours", cases[name])
        self.assertIn("Saturday by appointment · Closed Sunday", cases["unreadable"])  # the owner's words still show
        store = dict(load_content().store, hours=['Monday "9am" <b>–</b> 6pm & more', MAIN[1]])
        page = sitegen.render(dataclasses.replace(load_content(), store=store))[INDEX].decode("utf-8")
        self.assertNotIn("visit-open-status", page)
        self.assertIn("&lt;b&gt;", page)

    def test_fixture_pages_cover_every_named_case(self):
        cases = pages()
        self.assertEqual(sorted(cases), sorted(visit_hours_fixtures.CASES))
        self.assertEqual([k for k, v in cases.items() if node(v) is None], ["unreadable", "unreadable_first"])
        self.assertIn('class="home-notice" hidden data-from="2026-11-26" data-until="2026-11-26"', cases["holiday_notice"])
        self.assertIn('class="home-notice" data-until="2026-11-28"', cases["legacy_notice"])  # no first day: already started
        self.assertIn('data-until="soon"', cases["bad_notice_dates"])
        self.assertEqual(node(cases["all_closed"]), [{"closed": True}] * 7)
        self.assertEqual(node(cases["no_sunday"])[6], None)

    def test_check_catches_tampered_schedule_and_keeps_notice_history(self):
        content = load_content()
        with tempfile.TemporaryDirectory(prefix="av1104-03-", dir=os.environ.get("TMPDIR")) as tmp:
            root = Path(tmp)
            (root / "hass").mkdir()
            os.symlink(REPO_ROOT / "hass" / "templates", root / "hass" / "templates")
            files = sitegen.render(content)
            for rel, data in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes(data)
            self.assertEqual(sitegen.diff_paths(files, root), [])
            self.assertEqual(notice.stale_paths(content, root), [])
            page = files[INDEX].decode("utf-8")
            evil = page.replace('{&quot;opens&quot;:540,&quot;closes&quot;:1080}', '{&quot;opens&quot;:0,&quot;closes&quot;:1439}', 1)
            self.assertNotEqual(evil, page)
            (root / INDEX).write_text(evil, encoding="utf-8")
            self.assertEqual(sitegen.diff_paths(files, root), [INDEX])
            self.assertEqual(notice.stale_paths(content, root), [INDEX])  # not mistaken for an earlier notice phase


if __name__ == "__main__":
    unittest.main()
