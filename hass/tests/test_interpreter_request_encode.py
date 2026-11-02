"""RF0250-2 tests (H05): an owner text or pending list that cannot be encoded is a failed call, never a crash.

Fake transport and fixed clock only: no socket, no model call.
Run: python3 -m unittest hass.tests.test_interpreter_request_encode -v
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass import interpreter_eval
from hass.interpreter_local import FAILED, LocalInterpreter
from hass.tests.test_interpreter_local import GOOD, MODEL, PENDING, PROMPT, URL, FakeTransport

NOW = datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc)  # Saturday 09:00 PST


def old_body(text, pending):
    """The request body exactly as the unmodified formula built it."""
    user = json.dumps({"message": text, "pending": pending, "today": "2026-11-07", "weekday": "Saturday"},
                      ensure_ascii=False)
    return json.dumps({"model": MODEL, "messages": [{"role": "system", "content": PROMPT},
                                                    {"role": "user", "content": user}],
                       "stream": False, "format": "json", "options": {"temperature": 0}},
                      ensure_ascii=False).encode("utf-8")


class RequestEncodeTests(unittest.TestCase):
    def make(self, clock=lambda: NOW):
        self.fake = FakeTransport()
        return LocalInterpreter(URL, MODEL, PROMPT, transport=self.fake, clock=clock)

    def assert_request_failed(self, interp, text, pending):
        self.assertEqual(interp.interpret(text, pending), {"unsupported": FAILED})
        self.assertEqual(interp.last_error, "request")
        self.assertEqual(self.fake.calls, [])

    def test_lone_surrogate_text_is_a_failed_request_with_no_call(self):
        for text in ("add \ud83d plums", "\udc80"):
            with self.subTest(text=ascii(text)):
                self.assert_request_failed(self.make(), text, PENDING)

    def test_non_json_pending_value_is_a_failed_request(self):
        self.assert_request_failed(self.make(), "hide the plums", [{"code": "D1", "when": object()}])

    def test_nan_pending_is_still_sent_unchanged(self):
        pending = [{"code": "D1", "n": float("nan")}]
        interp = self.make()
        self.assertEqual((interp.interpret("hide the plums", pending), interp.last_error), (GOOD, None))
        [(_, body, _, _)] = self.fake.calls
        self.assertEqual(body, old_body("hide the plums", pending))
        self.assertIn(b"NaN", body)

    def test_paired_emoji_and_accented_text_build_todays_exact_bytes(self):
        for text in ("add 🍑 peaches", "Crème brûlée, señora — ¿mañana?"):
            with self.subTest(text=text):
                interp = self.make()
                self.assertEqual((interp.interpret(text, PENDING), interp.last_error), (GOOD, None))
                [(_, body, _, _)] = self.fake.calls
                self.assertEqual(body, old_body(text, PENDING))
                self.assertIn(text.encode("utf-8"), body)

    def test_raising_clock_wins_over_a_surrogate_text(self):
        def broken():
            raise RuntimeError("clock down")
        interp = self.make(clock=broken)
        self.assertEqual(interp.interpret("add \ud83d plums", [{"when": object()}]), {"unsupported": FAILED})
        self.assertEqual((interp.last_error, self.fake.calls), ("clock", []))

    def test_good_call_after_a_request_failure_clears_last_error(self):
        interp = self.make()
        self.assert_request_failed(interp, "\udc80", PENDING)
        self.assertEqual((interp.interpret("add plums", PENDING), interp.last_error), (GOOD, None))
        self.assertEqual(len(self.fake.calls), 1)


class EvalLiveTests(unittest.TestCase):
    def test_live_records_the_surrogate_case_as_a_failed_call(self):
        fake = FakeTransport()
        cases = [{"id": "g1", "text": "add plums", "pending": []},
                 {"id": "s1", "text": "add \ud83d plums", "pending": []}]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "replies.jsonl"
            summary = interpreter_eval.live(cases, URL, "m", out, transport=fake)
            rows = [json.loads(line) for line in out.read_text("utf-8").splitlines()]
        self.assertEqual(summary, {"recorded": 2, "failedCalls": 1})
        self.assertEqual(rows, [{"id": "g1", "reply": GOOD}, {"id": "s1", "reply": {"unsupported": FAILED}}])
        self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__":
    unittest.main()
