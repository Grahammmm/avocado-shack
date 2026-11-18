"""AV2007-09 (QA2-04): the interpreter hints carry the exact coming date of a US holiday the message names.

Fixed dates and clocks only: no wall clock, no socket, no model call.
Run: python3 -B -m unittest hass.tests.test_nl_prep_calendar -q
"""

import copy
import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from hass import nl_prep
from hass.interpreter_local import LocalInterpreter
from hass.skills import kinds
from hass.tests.test_nl_prep import tiny

BATTERY = Path(__file__).parent / "fixtures" / "skills" / "qa1" / "owner-battery.jsonl"
NOTICE = "put a notice up: closed thanksgiving day"


def rows(text, today):
    return nl_prep.date_hints(text, today)[0]


def row(said, iso, weekday):
    return {"said": said, "date": iso, "weekday": weekday}


class HolidayHintTests(unittest.TestCase):
    def test_thanksgiving_fourth_thursday(self):
        self.assertEqual(rows(NOTICE, date(2026, 11, 15)), [row("thanksgiving day", "2026-11-26", "Thursday")])
        self.assertEqual(rows("thanksgiving", date(2026, 11, 27)), [row("thanksgiving", "2027-11-25", "Thursday")])
        # 2025 has four Thursdays; Nov 2029 has five, so the fourth is not the last
        self.assertEqual(rows("thanksgiving", date(2025, 11, 2))[0]["date"], "2025-11-27")  # Thursdays 6 13 20 27
        self.assertEqual(rows("thanksgiving", date(2029, 11, 1))[0]["date"], "2029-11-22")  # Thursdays 1 8 15 22 29

    def test_all_fixed_and_monday_holidays(self):
        today = date(2026, 1, 2)
        want = {"christmas": "2026-12-25", "christmas day": "2026-12-25", "christmas eve": "2026-12-24", "new year's eve": "2026-12-31",
                "new year's day": "2027-01-01", "memorial day": "2026-05-25", "labor day": "2026-09-07"}
        for said, iso in want.items():
            with self.subTest(said=said):
                self.assertEqual(rows(said, today), [row(said, iso, nl_prep.WEEKDAY_NAMES[date.fromisoformat(iso).weekday()])])
        self.assertEqual(rows("memorial day", date(2026, 5, 26)), [row("memorial day", "2027-05-31", "Monday")])
        self.assertEqual(rows("labor day", date(2026, 9, 8)), [row("labor day", "2027-09-06", "Monday")])

    def test_today_and_passed_rollover(self):
        cases = [("thanksgiving", date(2026, 11, 25), "2026-11-26"), ("thanksgiving", date(2026, 11, 26), "2026-11-26"), ("thanksgiving", date(2026, 11, 27), "2027-11-25"),
                 ("memorial day", date(2026, 5, 24), "2026-05-25"), ("memorial day", date(2026, 5, 25), "2026-05-25"), ("memorial day", date(2026, 5, 26), "2027-05-31"),
                 ("labor day", date(2026, 9, 6), "2026-09-07"), ("labor day", date(2026, 9, 7), "2026-09-07"), ("labor day", date(2026, 9, 8), "2027-09-06"),
                 ("christmas day", date(2026, 12, 24), "2026-12-25"), ("christmas day", date(2026, 12, 25), "2026-12-25"), ("christmas day", date(2026, 12, 26), "2027-12-25")]
        for text, today, iso in cases:
            with self.subTest(text=text, today=today):
                self.assertEqual(rows(text, today)[0]["date"], iso)

    def test_eve_day_and_two_holidays(self):
        self.assertEqual(rows("New Year's Eve and New Year's Day", date(2026, 12, 31)),
                         [row("new year's eve", "2026-12-31", "Thursday"), row("new year's day", "2027-01-01", "Friday")])
        self.assertEqual(rows("new year's eve and new year's day", date(2027, 1, 1)),
                         [row("new year's eve", "2027-12-31", "Friday"), row("new year's day", "2027-01-01", "Friday")])
        self.assertEqual(rows("Christmas Eve and Christmas Day", date(2026, 11, 15)),
                         [row("christmas eve", "2026-12-24", "Thursday"), row("christmas day", "2026-12-25", "Friday")])

    def test_whole_words_and_qualifiers(self):
        today = date(2026, 11, 15)
        self.assertEqual(rows("THANKSGIVING", today)[0]["date"], "2026-11-26")
        self.assertEqual(rows("new year\u2019s day", date(2026, 12, 1))[0]["date"], "2027-01-01")
        for text in ("", "new year", "new years day", "prethanksgivingpost", "christmaseve", "thanksgivings", "labour day",
                     "last thanksgiving", "past christmas day", "thanksgiving 2025", "2027 thanksgiving", "thanksgiving of 2027", "thanksgiving '27"):
            with self.subTest(text=text):
                self.assertEqual(rows(text, today), [])

    def test_july_one_row_and_idempotence(self):
        today = date(2026, 11, 15)
        for text in ("July 4th", "closed july 4", "4th of july"):
            with self.subTest(text=text):
                self.assertEqual(len(rows(text, today)), 1)
        self.assertEqual(kinds.day("July 4th", date(2026, 6, 1)).value, "2026-07-04")
        self.assertEqual(rows("July 4th", date(2026, 6, 1)), [row("july 4th", "2026-07-04", "Saturday")])  # the day itself, not the observed Friday
        self.assertEqual(rows("july 4 2028", today), [row("july 4 2028", "2028-07-04", "Tuesday")])
        text, once = "thanksgiving and christmas eve", rows("thanksgiving and christmas eve", today)
        self.assertEqual(rows(text, today), once)

    def test_calendar_end_preserves_other_hints(self):
        self.assertEqual(rows("new year's day", date.max), [])
        self.assertEqual(rows("new year's day", date(9999, 12, 31)), [])
        self.assertEqual(rows("new year's eve", date(9999, 12, 31)), [row("new year's eve", "9999-12-31", "Friday")])
        hints = nl_prep.make_hinter(tiny())("lemons on new year's day at 9am", date(9999, 12, 31))
        self.assertEqual(hints["times"], [{"said": "9am", "time": "09:00"}])
        self.assertEqual(hints["products"][0]["said"] if "products" in hints else "lemons", "lemons")
        many = " ".join(["christmas eve", "christmas day", "thanksgiving", "memorial day", "labor day", "new year's eve", "new year's day"] + ["july 4", "dec 3", "dec 4"])
        self.assertEqual(len(rows(many, date(2026, 1, 1))), nl_prep.MAX_LIST)


class HolidayRequestTests(unittest.TestCase):
    def request(self, text, clock=None, sent_at=None, pending=()):
        seen = []

        def transport(url, body, headers, timeout):
            seen.append(json.loads(body))
            return 200, json.dumps({"done": True, "message": {"content": json.dumps({"question": "ok"})}}).encode()
        interp = LocalInterpreter("http://127.0.0.1:11434", "m", "SYSTEM", transport=transport, clock=clock or (lambda: datetime(2026, 11, 15, 20, 0, tzinfo=timezone.utc)),
                                  hinter=nl_prep.make_hinter(tiny()))
        reply = interp.interpret(text, list(pending), sent_at=sent_at)
        self.assertEqual(reply, {"question": "ok"})
        return json.loads(seen[-1]["messages"][1]["content"])

    def test_pacific_midnight_both_offsets(self):
        def thanks(when):
            return self.request("thanksgiving", clock=lambda: datetime.fromisoformat(when))["hints"]["dates"][0]["date"]
        self.assertEqual(thanks("2026-11-27T07:59:59+00:00"), "2026-11-26")  # 23:59:59 PST Thursday
        self.assertEqual(thanks("2026-11-27T08:00:00+00:00"), "2027-11-25")  # Friday 00:00 PST
        def memorial(when):
            return self.request("memorial day", sent_at=datetime.fromisoformat(when))["hints"]["dates"][0]["date"]
        self.assertEqual(memorial("2026-05-26T06:59:59+00:00"), "2026-05-25")  # 23:59:59 PDT Monday
        self.assertEqual(memorial("2026-05-26T07:00:00+00:00"), "2027-05-31")
        # sent_at wins over the clock
        sent = self.request("thanksgiving", sent_at=datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc))
        self.assertEqual(sent["hints"]["dates"][0]["date"], "2027-11-25")

    def test_recorded_text_reaches_real_request(self):
        recorded = [json.loads(line) for line in BATTERY.read_text().splitlines() if line.strip()]
        [case] = [c for c in recorded if c["id"] == "qa2-04-holiday-date-hint"]
        self.assertEqual(case["texts"], [NOTICE])
        pending = [{"code": "beef", "state": "proposed", "summary": "Hours \u2192 Daily 8am\u20137pm"}]
        before = copy.deepcopy(pending)
        sent = self.request(case["texts"][0], pending=pending)
        self.assertEqual(pending, before)
        self.assertEqual(sent["message"], NOTICE)
        self.assertEqual(sent["pending"], before)
        self.assertEqual(sent["today"], "2026-11-15")
        self.assertEqual(sent["hints"]["dates"], [row("thanksgiving day", "2026-11-26", "Thursday")])
        self.assertEqual(case["expect"]["disposition"], "question")  # the recorded wrong question, no draft
        self.assertIn("Friday, November 27", case["replies"][0]["question"])


if __name__ == "__main__":
    unittest.main()
