"""AV2007-11 (CHAT-1 hk-create-voice): a spelled-out day of the month ('saturday the twenty first') is read like '21st' in the date hints.

Fixed dates and clocks only: no wall clock, no socket, no model call. Scripted replies are labelled synthetic.
Run: python3 -B -m unittest hass.tests.test_nl_prep_ordinal_words -q
"""

import copy
import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from hass import nl_prep
from hass.interpreter_local import LocalInterpreter
from hass.skills import kinds
from hass.tests.test_conversation import _ops
from hass.tests.test_hike_flow import FlowCase, MILL
from hass.tests.test_nl_prep import tiny

TODAY = date(2026, 11, 9)  # a Monday
BATTERY = Path(__file__).parent / "fixtures" / "skills" / "qa1" / "owner-battery.jsonl"
UNITS = ("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth "
         "eighteenth nineteenth").split()
WORDS = {n: w for n, w in enumerate(UNITS, 1)}
WORDS.update({20: "twentieth", 30: "thirtieth"})
WORDS.update({20 + i: f"twenty {w}" for i, w in enumerate(UNITS[:9], 1)})
WORDS[31] = "thirty first"
SUFFIX = lambda n: "th" if 10 <= n <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")  # noqa: E731
VOICE = "um so yeah can you add uh a hike for like saturday the twenty first at eight in the morning we're meeting at the um elfin forest boardwalk and it's easy"


def rows(text, today=TODAY):
    return nl_prep.date_hints(text, today)[0]


def dates(text, today=TODAY):
    return [r.get("date") for r in rows(text, today)]


class OrdinalWordTests(unittest.TestCase):
    def test_all_31_ordinals_equal_numeric_calendar_results(self):
        self.assertEqual(sorted(WORDS), list(range(1, 32)))
        for n, word in WORDS.items():
            for spoken in (word, word.replace(" ", "-"), word.upper()):
                for tmpl, num in (("the {}", "the {}"), ("december {}", "december {}"), ("{} of december", "{} of december"), ("{} december", "{} december")):
                    with self.subTest(text=tmpl.format(spoken)):
                        got, want = rows(tmpl.format(spoken)), rows(tmpl.format(f"{n}{SUFFIX(n)}"))
                        self.assertEqual(len(got), len(want))
                        self.assertEqual([(r.get("date"), r.get("weekday")) for r in got], [(r.get("date"), r.get("weekday")) for r in want])
                        self.assertEqual(len(got), 1)
                        self.assertIn(spoken.lower().replace("-", " ").split()[-1], got[0]["said"].replace("-", " "))  # said keeps the words

    def test_the_binding_examples(self):
        self.assertEqual(rows("saturday the twenty first"), [{"said": "twenty first", "date": "2026-11-21", "weekday": "Saturday"}])
        self.assertEqual(dates("the fifth"), ["2026-12-05"])  # next real 5th on/after today, as 'the 5th'
        self.assertEqual(dates("the fifth"), dates("the 5th"))
        self.assertEqual(rows("November thirtieth")[0]["date"], "2026-11-30")
        self.assertEqual(kinds.day("saturday the twenty first", TODAY).value, "2026-11-21")  # not Nov 14

    def test_weekday_ordinal_pair_uses_parent_contract(self):
        for text in ("saturday the twenty first", "saturday twenty-first", "the twenty first saturday", "saturday the 21st"):
            with self.subTest(text=text):
                [row] = rows(text)  # one explicit date row, no second 14th/21st weekday row
                self.assertEqual((row["date"], "weekday_mismatch" in row), ("2026-11-21", False))
        for text in ("friday the twenty first", "the twenty first friday"):
            with self.subTest(text=text):
                [row] = rows(text)
                self.assertTrue(row["weekday_mismatch"])
                ask = "You said Friday, but November 21 is a Saturday. Which day?"
                self.assertEqual(nl_prep.weekday_mismatch_question(row), ask)
                self.assertEqual(kinds.day(text, TODAY).reply, ask)

    def test_ordinal_words_need_day_context_and_whole_tokens(self):
        for text in ("first bread", "second batch", "add twenty first eggs", "a fifth of whiskey", "i came first", "twenty one eggs", "fifthly the plan",
                     "the zeroth", "the zero first", "the thirty second", "thirty second of november", "forty first of november", "the forty first",
                     "the twenty-twenty first", "negative first of november", "the twentyfirst", "the first-rate bread", "the ninth0"):
            with self.subTest(text=text):
                self.assertEqual(rows(text), [], text)
        self.assertEqual(dates("the first bread"), dates("the 1st bread"))  # an explicit 'the' is a day context, as for digits

    def test_short_month_leap_year_and_explicit_year_rules(self):
        self.assertEqual(dates("the thirtieth", date(2027, 1, 31)), ["2027-03-30"])  # February has no 30th
        self.assertEqual(dates("the thirtieth", date(2027, 1, 31)), dates("the 30th", date(2027, 1, 31)))
        self.assertEqual(dates("february twenty ninth", date(2027, 1, 1)), ["2028-02-29"])
        self.assertEqual(dates("february twenty ninth 2027", date(2027, 1, 1)), [])  # no such day: never rolled to another year
        self.assertEqual(dates("november thirtieth 2027"), ["2027-11-30"])
        for text in ("february thirtieth", "april thirty first", "november thirtieth 202", "november thirtieth 20277"):
            with self.subTest(text=text):
                self.assertEqual(rows(text), [])

    def test_calendar_end_keeps_independent_hints(self):
        end = date(9999, 12, 31)
        self.assertEqual(rows("january first", end), [])
        text = "lemons on january first at 9am"
        hinter = nl_prep.make_hinter(tiny())
        before = copy.deepcopy(tiny())
        one, two = hinter(text, end), hinter(text, end)
        self.assertEqual(one, two)
        self.assertEqual(one["times"], [{"said": "9am", "time": "09:00"}])
        self.assertNotIn("dates", one) if "dates" not in one else self.assertEqual(one["dates"], [])
        self.assertEqual(tiny(), before)


class RecordedVoiceTests(unittest.TestCase):
    def test_recorded_voice_request_carries_original_words_and_21st_hint(self):
        [case] = [c for c in (json.loads(line) for line in BATTERY.read_text().splitlines() if line.strip()) if c["id"] == "av2007-11-spoken-ordinal"]
        self.assertEqual(case["texts"], [VOICE])
        seen = []

        def transport(url, body, headers, timeout):
            seen.append(json.loads(body))
            historical = {"question": "Which Saturday is the hike: the 14th (this coming one) or the 21st (the one after)?"}  # the recorded question, replayed only as input
            return 200, json.dumps({"done": True, "message": {"content": json.dumps(historical)}}).encode()
        interp = LocalInterpreter("http://127.0.0.1:11434", "m", "SYSTEM", transport=transport, clock=lambda: datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc),
                                  hinter=nl_prep.make_hinter(tiny()))
        interp.interpret(VOICE, [])
        sent = json.loads(seen[-1]["messages"][1]["content"])
        self.assertEqual(sent["message"], VOICE)  # the words are untouched
        self.assertEqual(sent["hints"]["dates"], [{"said": "twenty first", "date": "2026-11-21", "weekday": "Saturday"}])
        self.assertNotIn("2026-11-14", [r.get("date") for r in sent["hints"]["dates"]])  # (the scheduled-hikes note for 'saturday' is a separate hint)
        # this proves the request only; it does not show that a real model stops asking

    def test_other_hint_families_still_read_the_original_words(self):
        hints = nl_prep.make_hinter(tiny())("lemons on the twenty first at 9am", TODAY)
        self.assertEqual(hints["times"], [{"said": "9am", "time": "09:00"}])
        self.assertEqual(hints["numbers"], [{"said": "twenty", "value": 20}])  # number hints keep reading the spoken words
        self.assertEqual(hints["dates"][0]["date"], "2026-11-21")


class DraftTests(FlowCase):
    def test_real_day_resolver_and_synthetic_draft_do_not_pick_14th(self):
        self.assertEqual(kinds.day(VOICE, TODAY).value, "2026-11-21")
        self.interp.mapping[VOICE] = _ops(("hike.create", {**MILL, "date": "2026-11-21", "title": "Elfin Forest hike", "meetingPoint": "Elfin Forest boardwalk"}))  # synthetic reply
        draft, reply = self.propose(VOICE)
        self.assertIn("Nov 21", reply)
        self.assertNotIn("14", reply)
        self.assertEqual(draft["state"], "proposed")
        self.nothing_written()  # nothing is saved until the owner says yes


if __name__ == "__main__":
    unittest.main()
