"""RF0111-10 tests: a damaged community.club container is treated as absent, never raises, keeps other rows.

Run: python3 -B -m unittest hass.tests.test_interpreter_prompt_club_shape -q
"""

import copy
import unittest

from hass.interpreter_prompt import PROMPT_MAX_BYTES, build
from hass.skills import model
from hass.tests.test_interpreter_prompt import FIXTURE, TEST_REGISTRY, _section, tiny_content
from hass.tests.test_interpreter_prompt_skills import _skill

HIDDEN = "\nsamples | hidden"
EVENT = {"id": "buchon-nov", "title": "Buchon", "startsAt": "2026-11-07T08:30:00-08:00",
         "timezone": "America/Los_Angeles", "status": "scheduled", "meetingPoint": "Gate", "capacity": 12}
ROUTE = {"id": "idea-a", "title": "Coast walk"}
TRUTHY_DAMAGED = ("bad", [1], ["x", {"showSamples": False}], 1, -3, 2.5, True)
FALSY = (None, False, 0, "", [], {})
MISSING = object()


def _content(club=MISSING, rows=False):
    content = tiny_content()
    content.community = {"events": [copy.deepcopy(EVENT)], "routeIdeas": [copy.deepcopy(ROUTE)]} if rows else {}
    if club is not MISSING:
        content.community["club"] = club
    return content


def _prompt(club=MISSING, rows=False, skills=None):
    return build(TEST_REGISTRY, _content(club, rows), skills)


class ClubShapeTests(unittest.TestCase):
    def test_truthy_non_dict_club_is_absent(self):
        absent = _prompt()
        for club in TRUTHY_DAMAGED:
            with self.subTest(club=club):
                self.assertEqual(_prompt(club), absent)
                self.assertNotIn(HIDDEN, _prompt(club))

    def test_falsy_and_missing_club_keep_existing_bytes(self):
        golden = FIXTURE.read_text("utf-8")
        self.assertEqual(_prompt(), golden)
        for club in FALSY:
            with self.subTest(club=club):
                self.assertEqual(_prompt(club).encode("utf-8"), golden.encode("utf-8"))

    def test_only_literal_false_flag_emits_hidden_marker(self):
        hidden = _prompt({"showSamples": False})
        self.assertEqual(hidden.count(HIDDEN), 1)
        self.assertEqual(hidden.replace(HIDDEN, "", 1), _prompt())
        for flag in (True, None, 0, 1, "", "false", [], [False], {}, {"x": False}):
            with self.subTest(flag=flag):
                self.assertEqual(_prompt({"showSamples": flag}), _prompt())
        self.assertEqual(_prompt({}), _prompt())  # a dict without the flag stays the absent-club output

    def test_damaged_club_preserves_other_community_rows(self):
        valid = _prompt(rows=True)
        self.assertEqual(_section(valid, "Hikes (id | title | starts at | status):"),
                         ['"buchon-nov" | "Buchon" | "2026-11-07T08:30:00-08:00" | "scheduled"'])
        self.assertEqual(_section(valid, "Route ideas (id | title):"), ['"idea-a" | "Coast walk"'])
        self.assertIn('"buchon-nov" | "Gate" | "12" | "" | ""', valid)
        for club in TRUTHY_DAMAGED:
            with self.subTest(club=club):
                self.assertEqual(_prompt(club, rows=True), valid)
        self.assertEqual(_prompt({"showSamples": False}, rows=True), valid.replace(
            '"idea-a" | "Coast walk"', '"idea-a" | "Coast walk"' + HIDDEN, 1))

    def test_input_unchanged_repeat_build_and_skills(self):
        skills = model.Registry({"a.b": _skill("a.b")})
        for club in TRUTHY_DAMAGED + ({"showSamples": False},):
            with self.subTest(club=club):
                content = _content(club, rows=True)
                before = copy.deepcopy(content.community)
                first = build(TEST_REGISTRY, content, skills)
                self.assertEqual(content.community, before)
                self.assertEqual(build(TEST_REGISTRY, content, skills), first)
                self.assertEqual(first, _prompt({"showSamples": False} if isinstance(club, dict) else MISSING,
                                                rows=True, skills=skills))
                self.assertTrue(first.startswith(_prompt(club, rows=True).rstrip("\n")))
                self.assertLessEqual(len(first.encode("utf-8")), PROMPT_MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
