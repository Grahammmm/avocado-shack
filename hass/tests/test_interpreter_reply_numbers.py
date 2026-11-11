"""RF0755-13 tests: exponent-overflow numbers (1e999) in an interpreter reply are a failed call at both JSON layers.

Fake transports returning fixed bytes and fixed aware clocks only; no socket, no model.
Run: python3 -B -m unittest hass.tests.test_interpreter_reply_numbers -q
"""

import contextlib
import io
import json
import unittest
from datetime import datetime, timezone

from hass.interpreter_local import FAILED, FallbackInterpreter, LocalInterpreter
from hass.label_reader import LabelReader

URL, MODEL, PROMPT = "http://127.0.0.1:11434", "qwen-local-test", "SYSTEM-PROMPT-MARKER"
UNSUPPORTED = {"unsupported": FAILED}
OVERFLOW = ("1e999", "-1e999", "1.7976931348623159e308")
CLOCK = lambda: datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc)  # noqa: E731
IMAGE = b"\xff\xd8\xff\xe0label"


def wrap(api, content: str, extra: str = "") -> bytes:
    """Raw reply bytes for the API around content; extra is raw JSON member text (e.g. '"usage": {"n": 1e999}')."""
    tail = f", {extra}" if extra else ""
    if api == "openai":
        return ('{"choices": [{"finish_reason": "stop", "message": {"content": %s}}]%s}' % (json.dumps(content), tail)).encode()
    return ('{"done": true, "message": {"role": "assistant", "content": %s}%s}' % (json.dumps(content), tail)).encode()


class Fake:
    def __init__(self, *raws):
        self.raws, self.calls = list(raws), 0

    def __call__(self, url, body, headers, timeout):
        self.calls += 1
        return 200, self.raws.pop(0) if len(self.raws) > 1 else self.raws[0]


def make(api, *raws):
    transport = Fake(*raws)
    return LocalInterpreter(URL, MODEL, PROMPT, transport=transport, clock=CLOCK, api=api), transport


class ReplyNumberTests(unittest.TestCase):
    def test_overflow_envelope_refused_for_both_backends(self):
        for api in ("ollama", "openai"):
            for token in OVERFLOW:
                for extra in (f'"usage": {{"n": {token}}}', f'"x": [1, [{token}]]'):
                    with self.subTest(api=api, extra=extra):
                        interp, transport = make(api, wrap(api, '{"question": "Which day?"}', extra))
                        self.assertEqual(interp.interpret("hi", []), UNSUPPORTED)
                        self.assertEqual((interp.last_error, transport.calls), ("not-json", 1))

    def test_overflow_content_refused_for_both_backends(self):
        err = io.StringIO()
        with contextlib.redirect_stdout(err), contextlib.redirect_stderr(err):
            for api in ("ollama", "openai"):
                for token in OVERFLOW:
                    for content in (f'{{"price": {token}}}', f'{{"args": {{"l": [1, {{"p": {token}}}]}}}}'):
                        for prefix in ("", "<think>reasoning</think>") if api == "openai" else ("",):
                            with self.subTest(api=api, content=content, prefix=prefix):
                                interp, transport = make(api, wrap(api, prefix + content))
                                self.assertEqual(interp.interpret("hi", []), UNSUPPORTED)
                                self.assertEqual((interp.last_error, transport.calls), ("shape", 1))
        self.assertEqual(err.getvalue(), "")

    def test_finite_integer_and_string_controls_unchanged(self):
        content = ('{"a": 1e308, "b": 1.7976931348623157e308, "c": -0.0, "d": 1e-999, "e": -1e-999, "f": 4.5, "g": 12345678901234567890123, '
                   '"h": "1e999", "i": "Infinity", "j": 7}')
        for api in ("ollama", "openai"):
            with self.subTest(api=api):
                interp, _ = make(api, wrap(api, content, '"usage": {"n": 1e308}'))
                result = interp.interpret("hi", [])
                self.assertIsNone(interp.last_error)
                self.assertEqual(result, json.loads(content))
                self.assertEqual(result["a"], 1e308)
                self.assertEqual(result["b"], 1.7976931348623157e308)
                self.assertEqual(str(result["c"]), "-0.0")
                self.assertEqual(str(result["e"]), "-0.0")
                self.assertIs(type(result["g"]), int)
                self.assertIs(type(result["j"]), int)
                self.assertEqual((result["h"], result["i"]), ("1e999", "Infinity"))

    def test_overflow_triggers_exactly_one_configured_fallback(self):
        good = wrap("ollama", '{"question": "Which day?"}')
        bad = wrap("openai", '{"question": "x"}', '"usage": {"n": 1e999}')
        primary, pt = make("openai", bad)
        fallback, ft = make("ollama", good)
        both = FallbackInterpreter(primary, fallback, lambda r: "question" in r)
        self.assertEqual(both.interpret("hi", []), {"question": "Which day?"})
        self.assertEqual((pt.calls, ft.calls), (1, 1))
        self.assertEqual((both.last_backend, both.last_fallback, both.last_primary_error, both.last_error),
                         ("ollama", True, "not-json", None))
        primary, pt = make("openai", bad)
        fallback, ft = make("ollama", wrap("ollama", '{"price": 1e999}'))
        both = FallbackInterpreter(primary, fallback, lambda r: "question" in r)
        self.assertEqual(both.interpret("hi", []), UNSUPPORTED)
        self.assertEqual((pt.calls, ft.calls, both.last_error, both.last_primary_error), (1, 1, "shape", "not-json"))
        primary, pt = make("openai", wrap("openai", '{"question": "ok"}', '"usage": {"n": 1e308}'))
        fallback, ft = make("ollama", good)
        both = FallbackInterpreter(primary, fallback, lambda r: "question" in r)
        self.assertEqual(both.interpret("hi", []), {"question": "ok"})
        self.assertEqual((pt.calls, ft.calls, both.last_fallback), (1, 0, False))

    def test_inherited_label_reader_refuses_overflow(self):
        label = '{"name": "Lion\'s Mane", "brand": "Far West Fungi", "category": "mushrooms"'
        for api in ("ollama", "openai"):
            with self.subTest(api=api):
                for raw, code in ((wrap(api, label + "}", '"usage": {"n": 1e999}'), "not-json"),
                                  (wrap(api, label + ', "conf": -1e999}'), "shape")):
                    transport = Fake(raw)
                    reader = LabelReader(URL, MODEL, transport=transport, api=api)
                    self.assertEqual(reader.read(IMAGE, ["mushrooms"]), {})
                    self.assertEqual((reader.last_error, transport.calls), (code, 1))
                transport = Fake(wrap(api, label + ', "conf": 0.9}', '"usage": {"n": 1e308}'))
                reader = LabelReader(URL, MODEL, transport=transport, api=api)
                self.assertEqual(reader.read(IMAGE, ["mushrooms"]),
                                 {"name": "Lion's Mane", "brand": "Far West Fungi", "category": "mushrooms"})
                self.assertIsNone(reader.last_error)

    def test_good_response_after_failure_clears_error(self):
        for api in ("ollama", "openai"):
            with self.subTest(api=api):
                interp, _ = make(api, wrap(api, '{"a": 1}', '"u": 1e999'), wrap(api, '{"a": 1e999}'), wrap(api, '{"a": 1}'))
                self.assertEqual(interp.interpret("hi", []), UNSUPPORTED)
                self.assertEqual(interp.last_error, "not-json")
                self.assertEqual(interp.interpret("hi", []), UNSUPPORTED)
                self.assertEqual(interp.last_error, "shape")
                self.assertEqual(interp.interpret("hi", []), {"a": 1})
                self.assertIsNone(interp.last_error)
                self.assertEqual(interp.last_backend, api)


if __name__ == "__main__":
    unittest.main()
