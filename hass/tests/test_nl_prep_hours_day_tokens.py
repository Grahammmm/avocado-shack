"""RF0600-11 tests: a stored hours line is calendar evidence only when its day word is a whole weekday word (hass/nl_prep.py).
Synthetic catalog and texts only; recording fake transport, no model, no socket.
Run: python3 -B -m unittest hass.tests.test_nl_prep_hours_day_tokens -q
"""

import json
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from hass import nl_prep
from hass.interpreter_local import LocalInterpreter

MONDAY = date(2026, 11, 9)
NINE_TO_FIVE = ("9am", "5pm")
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def store(*hours):
    return SimpleNamespace(products=[{"id": "photo-product-001", "name": "Lemons", "category": "fruit", "producerKey": None,
                                      "status": "active", "description": ""}],
                           makers={}, community={}, store={"hours": list(hours)})


def shows(wd, *hours):
    return nl_prep._day_shows(nl_prep._Index(store(*hours)), wd, NINE_TO_FIVE)


def hint(text, *hours):
    return nl_prep.make_hinter(store(*hours))(text, MONDAY)


class StoredDayTokenTests(unittest.TestCase):
    def test_arbitrary_stored_weekday_prefix_is_not_calendar_evidence(self):
        cases = ((MON, "monday", ("Monster", "MONSTER", "monster", "Mondayish", "M", "Mo", "mo", "Mon.")),
                 (SAT, "saturday", ("Saturnday", "Sa", "S")), (THU, "thursday", ("Thursdayish", "Th", "Thu\u00e9")))
        for wd, name, words in cases:
            for word in words:
                line = f"{word} 9am\u20135pm"
                before = line
                self.assertIsNone(shows(wd, line), line)
                self.assertNotIn("alreadyTrue", hint(f"{name} 9 to 5", line), line)
                self.assertEqual(line, before)

    def test_recognized_full_abbreviated_and_plural_names_keep_exact_noop(self):
        for word, wd in nl_prep.WEEKDAYS.items():
            for spelling in (word, word.upper(), word.title(), word + "s", word.title() + "S"):
                line = f"{spelling} 9am\u20135pm"
                self.assertEqual(shows(wd, line), "9am\u20135pm", line)
                self.assertEqual(hint(f"{word} 9 to 5", line)["alreadyTrue"], [f"{nl_prep.WEEKDAY_NAMES[wd]} already 9am\u20135pm"], line)
        for spelling, wd in (("Weds", WED), ("Tues", TUE), ("Thur", THU), ("Thurs", THU), ("Mondays", MON)):
            self.assertEqual(shows(wd, f"{spelling} 9am\u20135pm"), "9am\u20135pm", spelling)
        for word in ("Mondayish", "Monday1", "Mondayss", "Weds2", "Tuesdayy"):  # an extension never inherits the real day's meaning
            self.assertIsNone(shows(MON, f"{word} 9am\u20135pm"), word)
            self.assertIsNone(shows(WED, f"{word} 9am\u20135pm"), word)
            self.assertIsNone(shows(TUE, f"{word} 9am\u20135pm"), word)

    def test_unknown_range_endpoint_cannot_prove_known_endpoint(self):
        for line, wd in (("Monday\u2013Freelance 9am\u20135pm", MON), ("Monster\u2013Friday 9am\u20135pm", FRI),
                         ("Monday-Freelance 9am-5pm", MON), ("Monster-Friday 9am-5pm", FRI), ("Mon\u2013Fridayish 9am\u20135pm", WED)):
            self.assertIsNone(shows(wd, line), line)
        self.assertEqual(shows(WED, "Monday\u2013Friday 9am\u20135pm"), "9am\u20135pm")
        self.assertEqual(shows(FRI, "Mondays\u2013Fri 9am\u20135pm"), "9am\u20135pm")
        self.assertIsNone(shows(MON, "Friday\u2013Monday 9am\u20135pm"))  # reversed: omitted as before
        self.assertIsNone(shows(SAT, "Monday\u2013Friday 9am\u20135pm"))

    def test_unrelated_unknown_clause_does_not_destroy_known_fact(self):
        line = "Monster 9am\u20135pm \u00b7 Freelance by chat \u00b7 Saturday 9am\u20135pm"
        self.assertEqual(shows(SAT, line), "9am\u20135pm")
        self.assertEqual(hint("saturday 9 to 5", line)["alreadyTrue"], ["Saturday already 9am\u20135pm"])
        self.assertIsNone(shows(MON, line))
        self.assertNotIn("alreadyTrue", hint("monday 9 to 5", line))
        self.assertIsNone(shows(SAT, "Monster 9am\u20135pm \u00b7 Saturday 10am\u20134pm"))
        self.assertIsNone(shows(SAT, "Monster 9am\u20135pm \u00b7 Saturday closed"))
        self.assertNotIn("alreadyTrue", hint("saturday 9 to 5", "Monster 9am\u20135pm \u00b7 Saturday 10am\u20134pm"))

    def test_mixed_request_requires_every_named_day_to_have_real_evidence(self):
        self.assertNotIn("alreadyTrue", hint("Saturday and Monday 9 to 5", "Monster 9am\u20135pm \u00b7 Saturday 9am\u20135pm"))
        self.assertEqual(hint("Saturday and Monday 9 to 5", "Monday 9am\u20135pm \u00b7 Saturday 9am\u20135pm")["alreadyTrue"],
                         ["Saturday already 9am\u20135pm", "Monday already 9am\u20135pm"])

    def test_fake_request_omits_only_unproven_noop(self):
        def request(*hours):
            seen = []

            def transport(url, body, headers, timeout):
                seen.append(json.loads(body))
                return 200, json.dumps({"done": True, "message": {"content": json.dumps({"question": "ok"})}}).encode()
            interp = LocalInterpreter("http://127.0.0.1:11434", "m", "SYSTEM", transport=transport,
                                      clock=lambda: datetime(2026, 11, 9, 17, 40, tzinfo=timezone.utc), hinter=nl_prep.make_hinter(store(*hours)))
            interp.interpret(text, [])
            return json.loads(seen[-1]["messages"][1]["content"])
        text = "monday 9 to 5"
        fake, real = request("Monster 9am\u20135pm"), request("Monday 9am\u20135pm")
        self.assertEqual(fake["message"], text)
        self.assertNotIn("alreadyTrue", fake["hints"])
        self.assertEqual(real["hints"]["alreadyTrue"], ["Monday already 9am\u20135pm"])
        rest = {k: v for k, v in real["hints"].items() if k != "alreadyTrue"}
        self.assertTrue(rest.get("dates") and rest == fake["hints"], "the weekday date and every other hint are identical")


if __name__ == "__main__":
    unittest.main()
