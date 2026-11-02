"""AV2022-03 tests (H04/H05): each interpreter request carries today's Pacific date and weekday from an injectable clock.

Fake transport and fixed clocks only: no socket, no model call, no real date pinned.
Run: python3 -m unittest hass.tests.test_interpreter_today -v
"""

import json
import re
import unittest
from datetime import datetime, timezone

from hass.interpreter_local import FAILED, WEEKDAYS, LocalInterpreter
from hass.interpreter_prompt import build
from hass.tests.test_interpreter_local import GOOD, MODEL, OWNER_TEXT, PENDING, PROMPT, URL, FakeTransport
from hass.tests.test_interpreter_prompt import FIXTURE, TEST_REGISTRY, tiny_content

RULE = ('The user message gives "today" (Pacific date) and "weekday". Work out words like "next Saturday" or "tomorrow" '
        "from them and write the exact date; if the day is still unclear, ask.")


def utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class TodayTests(unittest.TestCase):
    def make(self, clock):
        self.fake = FakeTransport()
        return LocalInterpreter(URL, MODEL, PROMPT, transport=self.fake, clock=clock)

    def sent_user(self, clock, text=OWNER_TEXT, pending=PENDING):
        interp = self.make(clock)
        self.assertEqual(interp.interpret(text, pending), GOOD)
        self.assertIsNone(interp.last_error)
        [(_, body, _, _)] = self.fake.calls
        return json.loads(body.decode("utf-8"))["messages"][1]["content"]

    def today(self, clock):
        sent = json.loads(self.sent_user(clock))
        return sent["today"], sent["weekday"]

    def test_pacific_date_and_weekday_not_utc(self):
        cases = [("2026-11-07T17:00Z", ("2026-11-07", "Saturday")),
                 ("2026-11-07T07:30Z", ("2026-11-06", "Friday")),  # 23:30 PST Friday, already Saturday in UTC
                 ("2026-11-01T08:30Z", ("2026-11-01", "Sunday")),  # 01:30 PDT, before fall-back
                 ("2026-11-01T09:30Z", ("2026-11-01", "Sunday")),  # 01:30 PST, after fall-back
                 ("2026-11-01T06:30Z", ("2026-10-31", "Saturday"))]  # 23:30 PDT
        for when, expected in cases:
            with self.subTest(when=when):
                self.assertEqual(self.today(lambda w=when: utc(w)), expected)

    def test_any_aware_zone_is_read_in_pacific(self):
        tokyo = datetime.fromisoformat("2026-11-07T08:00+09:00")  # 2026-11-06 23:00Z = 15:00 PST Friday
        self.assertEqual(self.today(lambda: tokyo), ("2026-11-06", "Friday"))

    def test_key_order_and_raw_utf8(self):
        user = self.sent_user(lambda: utc("2026-11-07T17:00Z"))
        self.assertEqual(list(json.loads(user)), ["message", "pending", "today", "weekday"])
        self.assertIn("señora", user)
        self.assertNotIn("\\u00f1", user)
        self.assertTrue(user.endswith('"today": "2026-11-07", "weekday": "Saturday"}'))

    def test_bad_clock_is_fixed_failure_without_request(self):
        def raises():
            raise RuntimeError(f"CLOCK-SECRET {URL} {OWNER_TEXT}")

        bad = {"naive": lambda: datetime(2026, 11, 7, 9, 0), "string": lambda: "2026-11-07T17:00Z",
               "none": lambda: None, "date-like int": lambda: 1793594148, "raises": raises}
        for name, clock in bad.items():
            with self.subTest(clock=name):
                interp = self.make(clock)
                out = interp.interpret(OWNER_TEXT, PENDING)
                self.assertEqual((out, interp.last_error), ({"unsupported": FAILED}, "clock"))
                self.assertEqual(self.fake.calls, [])
                self.assertNotIn("CLOCK-SECRET", json.dumps(out) + str(interp.last_error))

    def test_failure_does_not_stick_after_clock_recovers(self):
        readings = iter([None, utc("2026-11-07T17:00Z")])
        interp = self.make(lambda: next(readings))
        self.assertEqual(interp.interpret("x", []), {"unsupported": FAILED})
        self.assertEqual(interp.last_error, "clock")
        self.assertEqual(interp.interpret("x", []), GOOD)
        self.assertIsNone(interp.last_error)
        self.assertEqual(len(self.fake.calls), 1)

    def test_clock_read_once_per_request(self):
        reads = []
        interp = self.make(lambda: reads.append(1) or utc("2026-11-07T17:00Z"))
        interp.interpret("x", [])
        interp.interpret("y", [])
        self.assertEqual((len(reads), len(self.fake.calls)), (2, 2))

    def test_non_callable_clock_refused_at_construction(self):
        for clock in ("x", utc("2026-11-07T17:00Z"), 0):
            fake = FakeTransport()
            with self.subTest(clock=repr(clock)), self.assertRaises(ValueError) as caught:
                LocalInterpreter(URL, MODEL, PROMPT, transport=fake, clock=clock)
            self.assertEqual(str(caught.exception), "clock must be callable")
            self.assertEqual(fake.calls, [])

    def test_default_clock_gives_a_valid_date_and_weekday(self):
        fake = FakeTransport()
        LocalInterpreter(URL, MODEL, PROMPT, transport=fake).interpret("x", [])
        sent = json.loads(json.loads(fake.calls[0][1])["messages"][1]["content"])
        self.assertRegex(sent["today"], r"^\d{4}-\d{2}-\d{2}$")
        datetime.strptime(sent["today"], "%Y-%m-%d")
        self.assertIn(sent["weekday"], WEEKDAYS)
        self.assertEqual(len(WEEKDAYS), 7)


class PromptRuleTests(unittest.TestCase):
    def test_rule_appears_once_and_never_guess_stays(self):
        prompt = build(TEST_REGISTRY, tiny_content())
        self.assertEqual(prompt.count(RULE), 1)
        self.assertEqual(prompt.count(f"- {RULE}\n"), 1)
        self.assertIn("- Never guess dates, times, prices or quantities; ask a question instead.\n", prompt)
        self.assertEqual(len(re.findall(r"next Saturday", prompt)), 1)

    def test_snapshot_matches(self):
        self.assertEqual(build(TEST_REGISTRY, tiny_content()), FIXTURE.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
