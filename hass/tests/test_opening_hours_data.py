"""AV1922-05: the home page's schema.org data carries openingHoursSpecification read by AV1104-03's sitegen.parse_hours.
Run: python3 -B -m unittest hass.tests.test_opening_hours_data -v
"""

import copy
import dataclasses
import json
import re
import unittest
from unittest import mock

from hass import sitegen
from hass.content_model import load_content

CONTENT = load_content()
HOME = sitegen.SITE_PREFIX + "index.html"
BLOCK = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
MAIN = ["Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday"]


def _spec(day, opens, closes):
    return {"@type": "OpeningHoursSpecification", "dayOfWeek": "https://schema.org/" + day, "opens": opens, "closes": closes}


MAIN_SPECS = [_spec(d, "09:00", "18:00") for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")] + \
    [_spec("Saturday", "09:00", "17:00")]


def _page(hours) -> str:
    store = {**copy.deepcopy(CONTENT.store), "hours": hours}
    return sitegen.render(dataclasses.replace(CONTENT, store=store))[HOME].decode("utf-8")


def _data(page: str) -> dict:
    found = BLOCK.findall(page)
    assert len(found) == 1, found
    return json.loads(found[0])


class OpeningHoursData(unittest.TestCase):
    def test_both_hours_lines_on_main_give_six_specifications_and_no_sunday(self):
        self.assertEqual(CONTENT.store["hours"], MAIN)
        page = _page(MAIN)
        self.assertEqual(_data(page)["openingHoursSpecification"], MAIN_SPECS)
        self.assertIn("Monday–Friday 9am–6pm<br>Saturday 9am–5pm · Closed Sunday", page)  # visible text unchanged

    def test_an_unreadable_line_adds_nothing_and_visible_text_stays(self):
        for hours in (["Monday–Friday 9am–6pm", "Saturday when the sun is up"],
                      ["Open most days", "Saturday 9am–5pm · Closed Sunday"],
                      ["Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday", "Monday 10am–2pm"]):  # a day named twice
            with self.subTest(hours=hours):
                page = _page(hours)
                self.assertNotIn("openingHoursSpecification", _data(page))
                self.assertIn("<br>".join(hours), page)

    def test_closed_days_are_left_out_and_an_all_closed_week_adds_nothing(self):
        self.assertEqual(_data(_page(["Monday 9:05am–12pm · Closed Tuesday-Sunday"]))["openingHoursSpecification"],
                         [_spec("Monday", "09:05", "12:00")])
        self.assertNotIn("openingHoursSpecification", _data(_page(["Closed Monday-Sunday"])))
        self.assertEqual(_data(_page(["Tuesday 12am–11:59pm"]))["openingHoursSpecification"],
                         [_spec("Tuesday", "00:00", "23:59")])

    def test_the_rule_is_parse_hours_not_a_copy(self):
        week = [{"opens": 600, "closes": 780}] + [None] * 5 + [{"closed": True}]
        with mock.patch.object(sitegen, "parse_hours", return_value={"days": week, "errors": []}):
            self.assertEqual(_data(_page(MAIN))["openingHoursSpecification"], [_spec("Monday", "10:00", "13:00")])
        with mock.patch.object(sitegen, "parse_hours", return_value={"days": None, "errors": [{"line": 1, "text": "x"}]}):
            self.assertNotIn("openingHoursSpecification", _data(_page(MAIN)))


if __name__ == "__main__":
    unittest.main()
