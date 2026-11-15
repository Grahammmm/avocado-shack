"""AV1937-06 (H05) tests: maker place/story and route place/description in the interpreter prompt, whole or <omitted>.

A partial edit ("add goat cheese to the Etto story") resends the whole field, so the prompt lists each value whole or marks it
unquoted <omitted>, never cut. Over the byte cap, stories go first, then route descriptions, maker places, route places.
No model call.

Run: python3 -B -m unittest hass.tests.test_interpreter_prompt_text -v
"""

import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from hass.interpreter_local import LocalInterpreter
from hass.interpreter_prompt import MAX_MAKERS, MAX_PRODUCTS, OMITTED, PROMPT_MAX_BYTES, RULES, build
from hass.tests.test_interpreter_prompt import TEST_REGISTRY, _section

MAKERS = "Makers (key | name | place | story):"
ROUTES = "Route ideas (id | title | place | description):"


def _content(makers=None, routes=None, products=None):
    return SimpleNamespace(products=products or [], makers=makers or {}, community={"routeIdeas": routes or []}, store={})


def _prompt(makers=None, routes=None, products=None):
    return build(TEST_REGISTRY, _content(makers, routes, products))


def _size(prompt):
    return len(prompt.encode("utf-8"))


def _json(text):
    """The expected literal, written independently of the module: JSON, with the three raw line separators escaped."""
    out = json.dumps(text, ensure_ascii=False)
    return out.replace("\x85", "\\u0085").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _maker_row(key, name, place, story):
    return f"{_json(key)} | {_json(name)} | {place} | {story}"


class WholeTextTest(unittest.TestCase):
    def test_maker_place_story_and_route_place_description_whole(self):
        story = ("Etto makes fresh pasta in Paso Robles: “semolina, eggs, patience” — ñandú & crème. " * 6) + "THE-END-OF-THE-STORY"
        description = "A gentle coastal walk with café stops and Tūī birds. " * 8 + "ROUTE-TAIL"
        makers = {"Etto": {"name": "Etto Pastificio", "place": "Paso Robles, CA", "story": story}}
        routes = [{"id": "idea-cass", "title": "Cass Hill", "place": "Cayucos", "description": description}]
        prompt = _prompt(makers, routes)
        self.assertEqual(_section(prompt, MAKERS), [_maker_row("Etto", "Etto Pastificio", '"Paso Robles, CA"', _json(story))])
        self.assertEqual(_section(prompt, ROUTES), [f'"idea-cass" | "Cass Hill" | "Cayucos" | {_json(description)}'])
        self.assertIn("THE-END-OF-THE-STORY", prompt)
        self.assertIn("ROUTE-TAIL", prompt)
        self.assertNotIn(OMITTED, "\n".join(_section(prompt, MAKERS) + _section(prompt, ROUTES)))

    def test_partial_edit_rules_require_full_field(self):
        rule = next(r for r in RULES if r.startswith("maker.edit"))
        for phrase in ("maker.edit (name, place, story)", "route.edit (title, place, description)", "whole new text built from",
                       "Makers or Route ideas", f'"" is empty; {OMITTED} is unseen here', "ask the owner for the full new text",
                       f"never send {OMITTED} as an argument", "A full replacement the owner wrote is fine"):
            self.assertIn(phrase, rule)
        self.assertIn("- " + rule, _prompt())

    def test_omitted_marker_is_not_owner_text(self):
        makers = {"a": {"name": "A", "story": OMITTED}, "b": {"name": "B", "story": {"k": "v"}}, "c": {"name": "C", "place": 7}}
        rows = _section(_prompt(makers), MAKERS)
        self.assertEqual(rows, ['"a" | "A" | "" | "<omitted>"',  # the owner's literal text stays quoted
                                '"b" | "B" | "" | <omitted>',  # not a string: the unquoted marker, never str(dict)
                                '"c" | "C" | <omitted> | ""'])
        self.assertNotIn("{", "\n".join(rows))

    def test_fake_transport_preserves_system_prompt(self):
        story = "Fresh pasta, made daily. " * 20 + "END-OF-ETTO-STORY"
        prompt = _prompt({"Etto": {"name": "Etto Pastificio", "place": "Paso Robles", "story": story}})
        sent = []

        def transport(url, body, headers, timeout):
            sent.append(json.loads(body)["messages"][0]["content"])
            return 200, json.dumps({"done": True, "message": {"content": '{"unsupported": "x"}'}}).encode()

        LocalInterpreter("http://127.0.0.1:11434", "m", prompt, transport=transport,
                         clock=lambda: datetime(2026, 11, 5, tzinfo=timezone.utc)).interpret("add goat cheese to the Etto story", [])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].encode("utf-8"), prompt.encode("utf-8"))  # the whole system text, unchanged
        self.assertIn(_json(story), sent[0])


class EscapeAndBudgetTest(unittest.TestCase):
    def test_utf8_and_json_escape_budget(self):
        hostile = 'Zoë “q” \\ "x" | y\nline\r2\u2028sep\u2029par\x85nel 🥑 ñ'
        makers = {"k|\n1": {"name": hostile, "place": hostile, "story": hostile}}
        routes = [{"id": "r\u20281", "title": hostile, "place": hostile, "description": hostile}]
        prompt = _prompt(makers, routes)
        self.assertEqual(len(prompt.splitlines()), len(_prompt({"k": {}}, [{"id": "r"}]).splitlines()))  # one row per record
        self.assertEqual(_section(prompt, MAKERS), [" | ".join(_json(v) for v in ("k|\n1", hostile, hostile, hostile))])
        self.assertEqual(_section(prompt, ROUTES), [" | ".join(_json(v) for v in ("r\u20281", hostile, hostile, hostile))])
        for raw in ("\u2028", "\u2029", "\x85", "\r"):
            self.assertNotIn(raw, prompt)
        prompt.encode("utf-8")  # strictly encodable

    def test_exact_cap_and_one_byte_over(self):
        def make(story_bytes):  # a story of exactly story_bytes escaped bytes (without quotes); "é" is 2 bytes
            k = story_bytes // 4
            return {"Etto": {"name": "Etto", "story": "é" * k + "x" * (story_bytes - 2 * k)}}

        room = PROMPT_MAX_BYTES - _size(_prompt(make(0)))
        exact = _prompt(make(room))
        self.assertEqual(_size(exact), PROMPT_MAX_BYTES)
        self.assertNotIn(OMITTED, "\n".join(_section(exact, MAKERS)))  # fits exactly: nothing left out
        over = _prompt(make(room + 1))
        self.assertEqual(_section(over, MAKERS), ['"Etto" | "Etto" | "" | ' + OMITTED])  # whole value out, no fragment
        self.assertLessEqual(_size(over), PROMPT_MAX_BYTES)


class OmissionOrderTest(unittest.TestCase):
    def _stories(self, per_story):
        return {key: {"name": key.upper(), "story": "x" * per_story} for key in ("a", "b", "c")}

    def _room(self, makers, routes):
        return PROMPT_MAX_BYTES - _size(_prompt(makers, routes))

    def test_story_omission_precedes_route_description(self):
        routes = [{"id": f"r{i}", "title": "T", "place": "P" * 50, "description": "d" * 400} for i in (1, 2)]
        room = self._room(self._stories(0), routes)
        total = room + 1
        first = {"a": total // 3, "b": total // 3, "c": total - 2 * (total // 3)}
        makers = {key: {"name": key.upper(), "story": "x" * n} for key, n in first.items()}
        prompt = _prompt(makers, routes)
        rows = _section(prompt, MAKERS)
        self.assertEqual([r.endswith(OMITTED) for r in rows], [False, False, True])
        self.assertEqual(rows[2], '"c" | "C" | "" | ' + OMITTED)
        self.assertEqual(_section(prompt, ROUTES),
                         [f'"r{i}" | "T" | "{"P" * 50}" | "{"d" * 400}"' for i in (1, 2)])  # descriptions and places intact
        # about twice the room: c then b go, a stays, and still no route text is touched
        n = room // 3 * 2
        prompt = _prompt({key: {"name": key.upper(), "story": "x" * n} for key in "abc"}, routes)
        rows = _section(prompt, MAKERS)
        self.assertEqual([r.endswith(OMITTED) for r in rows], [False, True, True])
        self.assertEqual(rows[0], f'"a" | "A" | "" | "{"x" * n}"')
        self.assertNotIn("x" * 20, "\n".join(rows[1:]))  # no story fragment survives
        self.assertNotIn(OMITTED, "\n".join(_section(prompt, ROUTES)))
        self.assertLessEqual(_size(prompt), PROMPT_MAX_BYTES)

    def _scenario(self, place, route_place, description):
        makers = {"m1": {"name": "M1", "place": "p" * place, "story": "ab"},
                  "m2": {"name": "M2", "place": "p" * place, "story": "1234567"},  # 9 escaped bytes: no gain, never listed
                  "m3": {"name": "M3", "place": "p" * place}}
        routes = [{"id": f"r{i}", "title": "T", "place": "q" * route_place, "description": "d" * description} for i in (1, 2)]
        routes.append({"id": "r3", "title": "T", "description": "ab"})
        return makers, routes

    def _state(self, prompt):
        """(maker place omitted, route description omitted, route place omitted) per row, in row order."""
        mrows = [r.split(" | ") for r in _section(prompt, MAKERS)]
        rrows = [r.split(" | ") for r in _section(prompt, ROUTES)]
        return ([m[2] == OMITTED for m in mrows], [r[3] == OMITTED for r in rrows], [r[2] == OMITTED for r in rrows])

    def test_description_then_place_fallback(self):
        room = self._room(*self._scenario(0, 0, 0))
        # a: about 500 bytes over: only the last long description goes (reverse id order); r1 keeps its text
        a_place = (room - 1500) // 5
        prompt = _prompt(*self._scenario(a_place, a_place, 1000))
        self.assertEqual(self._state(prompt), ([False] * 3, [False, True, False], [False] * 3))
        self.assertEqual(_section(prompt, ROUTES)[2], '"r3" | "T" | "" | "ab"')  # a short value is never replaced by the marker
        self.assertEqual([r.split(" | ")[3] for r in _section(prompt, MAKERS)], ['"ab"', '"1234567"', '""'])  # nor these
        # b: descriptions are not enough, so maker places go last key first (m3, m2), and m1 keeps its place
        prompt = _prompt(*self._scenario(room * 3 // 10, room * 3 // 10, 1000))
        self.assertEqual(self._state(prompt), ([False, True, True], [True, True, False], [False] * 3))
        self.assertEqual(_section(prompt, MAKERS)[0], '"m1" | "M1" | "' + "p" * (room * 3 // 10) + '" | "ab"')  # whole
        # c: still too big, so route places go after the maker places, r2 first; r1 keeps its whole place
        prompt = _prompt(*self._scenario(room * 3 // 10, room * 6 // 10, 1000))
        self.assertEqual(self._state(prompt), ([True] * 3, [True, True, False], [False, True, False]))
        self.assertEqual(_section(prompt, ROUTES)[0].split(" | ")[2], '"' + "q" * (room * 6 // 10) + '"')
        self.assertEqual(_section(prompt, MAKERS)[0], '"m1" | "M1" | ' + OMITTED + ' | "ab"')
        self.assertLessEqual(_size(prompt), PROMPT_MAX_BYTES)

    def test_no_pressure_keeps_every_value_and_is_deterministic(self):
        makers = {"b": {"name": "B", "place": "Here", "story": "Story b"}, "a": {"name": "A", "place": "There", "story": "Story a"}}
        routes = [{"id": "z", "title": "Z", "place": "Zed", "description": "Dz"}, {"id": "y", "title": "Y", "place": "Why",
                                                                                "description": "Dy"}]
        prompt = _prompt(makers, routes)
        self.assertNotIn(OMITTED, "\n".join(_section(prompt, MAKERS) + _section(prompt, ROUTES)))
        self.assertEqual(_section(prompt, MAKERS), ['"a" | "A" | "There" | "Story a"', '"b" | "B" | "Here" | "Story b"'])
        self.assertEqual(_section(prompt, ROUTES), ['"y" | "Y" | "Why" | "Dy"', '"z" | "Z" | "Zed" | "Dz"'])
        self.assertEqual(_prompt(dict(reversed(list(makers.items()))), routes[::-1]), prompt)
        room = self._room(*self._scenario(0, 0, 0))  # and the same result under pressure, whatever the input order
        makers, routes = self._scenario(room * 3 // 10, room * 6 // 10, 100)
        self.assertEqual(_prompt(dict(reversed(list(makers.items()))), routes[::-1]), _prompt(makers, routes))


class ShapesAndCapsTest(unittest.TestCase):
    def test_empty_none_malformed_and_caps(self):
        makers = {"m1": {"name": "One", "place": None, "story": ""}, "m2": "damaged", "m3": {"name": "Three"},
                  "m4": {"place": ["x"], "story": 7}}
        routes = [{"id": "r1", "title": "One", "place": None, "description": ""}, "junk", None,
                  {"id": "r2", "title": "Two", "description": {"k": 1}}, {"id": "r3"}]
        prompt = _prompt(makers, routes)
        self.assertEqual(_section(prompt, MAKERS), ['"m1" | "One" | "" | ""', '"m2" | "" | "" | ""', '"m3" | "Three" | "" | ""',
                                                    '"m4" | "" | <omitted> | <omitted>'])
        self.assertEqual(_section(prompt, ROUTES), ['"r1" | "One" | "" | ""', '"r2" | "Two" | "" | <omitted>', '"r3" | "" | "" | ""'])
        self.assertEqual(_section(_prompt({}, []), ROUTES) + _section(_prompt({}, []), MAKERS), ["(none)", "(none)"])
        self.assertEqual(_section(_prompt(["m"], "nope"), MAKERS), ["(none)"])
        big = {f"m{i:03d}": {"name": "M", "story": "s"} for i in range(MAX_MAKERS + 2)}
        for key in ("m200", "m201"):  # past the cap: not displayed, so their huge stories force nothing
            big[key]["story"] = "z" * 50000
        rows = _section(_prompt(big), MAKERS)
        self.assertEqual((len(rows), rows[-1]), (MAX_MAKERS + 1, "… and 2 more (ask the owner)"))
        self.assertNotIn(OMITTED, "\n".join(rows))
        story_notice = {"m": {"name": "M", "story": "… and 2 more (ask the owner)"}}
        self.assertEqual(_section(_prompt(story_notice), MAKERS), ['"m" | "M" | "" | "… and 2 more (ask the owner)"'])  # quoted

    def test_core_oversize_still_refuses(self):
        products = [{"id": f"p-{i:03d}", "name": "n" * 200, "status": "active"} for i in range(MAX_PRODUCTS)]
        makers = {"a": {"name": "A", "place": "p" * 500, "story": "s" * 500}}
        routes = [{"id": "r", "title": "T", "place": "q" * 500, "description": "d" * 500}]
        with self.assertRaisesRegex(ValueError, r"^prompt too large$"):
            _prompt(makers, routes, products)
        huge = {"a": {"name": "N" * 70000, "story": "s" * 500}}  # a name is never omitted, so no fallback can fit
        with self.assertRaisesRegex(ValueError, r"^prompt too large$"):
            _prompt(huge)


if __name__ == "__main__":
    unittest.main()
