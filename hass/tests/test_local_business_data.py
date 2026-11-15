"""AV1422-11: the home page carries schema.org local-business JSON-LD built from store.json by sitegen.
Run: python3 -m unittest hass.tests.test_local_business_data -v
"""

import copy
import dataclasses
import json
import re
import unittest

from hass import sitegen
from hass.content_model import load_content

CONTENT = load_content()
HOME, HIKE = (sitegen.SITE_PREFIX + n for n in ("index.html", "hike/index.html"))
BLOCK = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _render(**store_changes) -> dict[str, str]:
    store = {**copy.deepcopy(CONTENT.store), **store_changes}
    files = sitegen.render(dataclasses.replace(CONTENT, store=store))
    return {rel: data.decode("utf-8") for rel, data in files.items() if rel.endswith(".html")}


def _block(page: str) -> str:
    found = BLOCK.findall(page)
    assert len(found) == 1, found
    return found[0]


class LocalBusinessJsonLd(unittest.TestCase):
    def test_repo_store_parses_to_expected_object_without_phone(self):
        store = CONTENT.store
        expected = {"@context": "https://schema.org", "@type": "GroceryStore", "name": store["name"],
                    "address": {"@type": "PostalAddress", "streetAddress": store["streetAddress"],
                                "addressLocality": store["town"], "addressRegion": "CA", "addressCountry": "US"}}
        expected["openingHoursSpecification"] = [  # AV1922-05: the two canonical hours lines, pinned in test_opening_hours_data
            {"@type": "OpeningHoursSpecification", "dayOfWeek": "https://schema.org/" + day,
             "opens": "09:00", "closes": "17:00" if day == "Saturday" else "18:00"}
            for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")]
        self.assertEqual(json.loads(_block(_render(phone=None)[HOME])), expected)

    def test_phone_set_and_cleared(self):
        data = json.loads(_block(_render(phone="8055550123")[HOME]))
        self.assertEqual(data["telephone"], "+1-805-555-0123")
        self.assertIn('"telephone":"+1-805-555-0123"', _block(_render(phone="8055550123")[HOME]))
        self.assertNotIn("telephone", json.loads(_block(_render(phone=None)[HOME])))
        self.assertNotIn("hours", _block(_render(hours=["Open when we are"])[HOME]))  # AV1922-05: unreadable hours add nothing

    def test_hostile_store_text_cannot_close_the_script(self):
        name = "</script><script>alert(1)</script>"
        street = "1 A &amp; B St\u2028x\u2029y"
        page = _render(name=name, streetAddress=street)[HOME]
        block = _block(page)
        for raw in "<>&\u2028\u2029":
            self.assertNotIn(raw, block)
        data = json.loads(block)
        self.assertEqual(data["name"], name)
        self.assertEqual(data["address"]["streetAddress"], street)
        after = page[page.index(block) + len(block):]
        self.assertTrue(after.startswith("</script>\n</head>"))  # the block's own closer is the only one left in <head>

    def test_only_the_home_page_has_a_block(self):
        pages = _render()
        self.assertEqual(len(BLOCK.findall(pages[HOME])), 1)
        self.assertNotIn("ld+json", pages[HIKE])  # 404.html is hand-written, not generated


if __name__ == "__main__":
    unittest.main()
