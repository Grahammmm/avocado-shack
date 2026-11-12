"""RF0421-13 tests: an interpreter reply holding an unpaired Unicode surrogate (after JSON escape decoding) is a failed call.

Fake transports returning ASCII-escaped JSON only; no socket, no model. Fixture helpers are imported by module alias so
no foreign TestCase is discovered here.
Run: python3 -B -m unittest hass.tests.test_interpreter_reply_unicode -q
"""

import json
import unittest
from datetime import datetime, timezone

from hass.interpreter_local import FAILED, FallbackInterpreter, LocalInterpreter
from hass.label_reader import LabelReader
from hass.tests import test_conversation as tc
from hass.tests import test_photo_draft as tp

URL, MODEL, PROMPT = "http://127.0.0.1:11434", "qwen-local-test", "SYSTEM-PROMPT-MARKER: reply with JSON."
UNSUPPORTED = {"unsupported": FAILED}
CLOCK = lambda: datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc)  # noqa: E731
LONE_HI, LONE_LO, PAIR = "\\ud800", "\\udc00", "\\ud83d\\ude00"  # raw JSON escapes, kept as 6-character tokens


def ollama(content_raw: str) -> bytes:  # content_raw is JSON text of the answer; embedded as a JSON string, ASCII only
    return ('{"done": true, "message": {"role": "assistant", "content": %s}}' % json.dumps(content_raw)).encode("ascii")


def openai(content_raw: str) -> bytes:
    return ('{"choices": [{"finish_reason": "stop", "message": {"content": %s}}]}' % json.dumps(content_raw)).encode("ascii")


def make(raw, api="ollama", cls=LocalInterpreter):
    transport = lambda url, body, headers, timeout: (200, raw)  # noqa: E731
    if cls is LabelReader: return LabelReader(URL, MODEL, transport=transport, api=api)
    return LocalInterpreter(URL, MODEL, PROMPT, transport=transport, clock=CLOCK, api=api)


def wrap(api, content_raw): return (ollama if api == "ollama" else openai)(content_raw)


class SurrogateReplyTests(unittest.TestCase):
    def test_each_api_refuses_surrogate_at_both_json_layers(self):
        for api in ("ollama", "openai"):
            for lone in (LONE_HI, LONE_LO):
                for content in ('{"question": "Which day? %s"}', '{"%s": 1}', '{"args": {"x": ["a", "b%s"]}}',
                                '{"op": "a", "note": "%s"}', '"%s"'):
                    with self.subTest(api=api, lone=lone, content=content):  # inner layer -> shape
                        interp = make(wrap(api, content % lone), api)
                        self.assertEqual(interp.interpret("when?", []), UNSUPPORTED)
                        self.assertEqual(interp.last_error, "shape")
                outer = (b'{"done": true, "extra": "%s", "message": {"content": "{}"}}' % lone.encode() if api == "ollama" else
                         b'{"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}], "extra": "%s"}' % lone.encode())
                with self.subTest(api=api, lone=lone, layer="outer"):  # even an unused envelope field -> not-json
                    interp = make(outer, api)
                    self.assertEqual(interp.interpret("when?", []), UNSUPPORTED)
                    self.assertEqual(interp.last_error, "not-json")

    def test_double_escaped_surrogate_is_decoded_only_at_the_inner_layer(self):
        for api in ("ollama", "openai"):
            interp = make(wrap(api, '{"question": "Which? \\ud800"}'), api)  # outer decoding leaves \ud800 for the inner JSON
            self.assertEqual(interp.interpret("when?", []), UNSUPPORTED)
            self.assertEqual(interp.last_error, "shape")

    def test_pairs_are_decoded_before_scalar_validation(self):
        for api in ("ollama", "openai"):
            interp = make(wrap(api, '{"question": "Hi %s", "b": "caf\\u00e9 e\\u0301 \U0001F600 \\\\ud800", "a": 1}' % PAIR), api)
            result = interp.interpret("when?", [])
            self.assertIsNone(interp.last_error)
            self.assertEqual(result, {"question": "Hi \U0001F600", "b": "caf\u00e9 e\u0301 \U0001F600 \\ud800", "a": 1})
            self.assertEqual(list(result), ["question", "b", "a"])  # key order kept
        for bad in (LONE_HI, LONE_LO, LONE_LO + LONE_HI, PAIR + LONE_LO, LONE_HI + PAIR):
            with self.subTest(bad=bad):
                interp = make(ollama('{"question": "x%s"}' % bad))
                self.assertEqual(interp.interpret("when?", []), UNSUPPORTED)
                self.assertEqual(interp.last_error, "shape")

    def test_refusal_preserves_status_size_and_shape_precedence(self):
        bad = ollama('{"question": "%s"}' % LONE_HI)
        for status, raw, code in ((503, bad, "http-503"), (200, b" " * (1 << 20) + bad, "too-large"), (200, b"[]", "not-json"),
                                  (200, b'{"done": true, "done": true}', "not-json"), (200, b'{"done": NaN}', "not-json"),
                                  (200, b'{"done": 1e999}', "not-json")):
            with self.subTest(code=code):
                interp = LocalInterpreter(URL, MODEL, PROMPT, transport=lambda u, b, h, t: (status, raw), clock=CLOCK)
                self.assertEqual(interp.interpret("when?", []), UNSUPPORTED)
                self.assertIn(interp.last_error, (code, "shape") if code == "not-json" else (code,))
        good = make(bytearray(ollama('{"question": "ok"}')))
        self.assertEqual(good.interpret("when?", []), {"question": "ok"})

    def test_conversation_bad_question_is_a_consumed_reader_failure(self):
        class Case(tc.ConversationTestCase):
            def runTest(self): pass

        case = Case()
        case.setUp()
        self.addCleanup(case.repo.cleanup)
        case.interp = make(ollama('{"question": "Which day? %s"}' % LONE_HI))
        case.conv = case.open()
        head = case.count()
        self.assertEqual(case.say("when?", pid="u1"), "reader-failed")
        self.assertEqual(case.replies(), [FAILED])
        self.assertEqual(case.drafts(), [])
        self.assertEqual(case.count(), head)
        self.assertEqual(case.interp.last_error, "shape")

    def test_one_fallback_recovers_from_bad_unicode(self):
        bad, good = ollama('{"question": "x%s"}' % LONE_HI), ollama('{"question": "Which day?"}')
        calls = []

        def pair(first, second):
            def transport(raw, name):
                def call(url, body, headers, timeout): calls.append(name); return 200, raw
                return call
            return FallbackInterpreter(LocalInterpreter(URL, MODEL, PROMPT, transport=transport(first, "primary"), clock=CLOCK),
                                       LocalInterpreter(URL, MODEL, PROMPT, transport=transport(second, "second"), clock=CLOCK),
                                       lambda r: isinstance(r, dict))
        wrapper = pair(bad, good)
        self.assertEqual(wrapper.interpret("when?", []), {"question": "Which day?"})
        self.assertEqual((calls, wrapper.last_fallback, wrapper.last_primary_error), (["primary", "second"], True, "shape"))
        calls.clear()
        wrapper = pair(bad, bad)
        self.assertEqual(wrapper.interpret("when?", []), UNSUPPORTED)
        self.assertEqual((calls, wrapper.last_error), (["primary", "second"], "shape"))

    def test_label_reader_uses_same_refusal_and_valid_unicode_recovers(self):
        for api in ("ollama", "openai"):
            for content, code in (('{"name": "Lion%s", "brand": "Far West Fungi", "category": "mushrooms"}' % LONE_HI, "shape"),
                                  ('{"%s": 1, "name": "Lion", "category": "mushrooms"}' % LONE_LO, "shape")):
                with self.subTest(api=api, content=content):
                    labels = make(wrap(api, content), api, LabelReader)
                    self.assertEqual(labels.read(tp.JPG, ["mushrooms"]), {})
                    self.assertEqual(labels.last_error, code)
        ok = '{"name": "Lion\\u0027s Mane %s", "category": "mushrooms"}' % PAIR
        labels = make(ollama(ok), cls=LabelReader)
        self.assertEqual(labels.read(tp.JPG, ["mushrooms"]), {"name": "Lion's Mane \U0001F600", "category": "mushrooms"})
        self.assertIsNone(labels.last_error)

    def test_failure_is_private_and_deterministic(self):
        canary = "OWNER-CANARY-7"
        interp = make(ollama('{"question": "%s %s"}' % (canary, LONE_HI)))
        first = interp.interpret(canary, [])
        self.assertEqual((first, interp.last_error), (UNSUPPORTED, "shape"))
        self.assertEqual(interp.interpret(canary, []), first)
        blob = json.dumps([first, interp.last_error, interp.last_seconds], default=str)
        self.assertNotIn(canary, blob)
        self.assertNotIn("ud800", blob.lower())


if __name__ == "__main__":
    unittest.main()
