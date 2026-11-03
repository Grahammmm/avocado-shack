"""RF1240-20 tests: LocalInterpreter refuses repeated keys and NaN/Infinity in the Ollama envelope and the model's JSON.

Fake transport returning fixed bytes and a fixed aware clock only; no socket, no model.
Run: python3 -m unittest hass.tests.test_interpreter_local_strict -v
"""

import json
import unittest
from datetime import datetime, timezone

from hass.interpreter_local import FAILED, LocalInterpreter

URL, MODEL, PROMPT = "http://127.0.0.1:11434", "qwen-local-test", "SYSTEM-PROMPT-MARKER: reply with JSON."
OWNER_TEXT = "Change the price — OWNER-TEXT-MARKER"
UNSUPPORTED = {"unsupported": FAILED}


def envelope(content: str) -> bytes:
    return json.dumps({"model": MODEL, "message": {"role": "assistant", "content": content}, "done": True}).encode()


class StrictReplyTests(unittest.TestCase):
    def run_reply(self, raw: bytes):
        self.interp = LocalInterpreter(URL, MODEL, PROMPT, transport=lambda url, body, headers, timeout: (200, raw),
                                       clock=lambda: datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc))
        return self.interp.interpret(OWNER_TEXT, [])

    def assert_failed(self, raw: bytes, code: str):
        self.assertEqual(self.run_reply(raw), UNSUPPORTED)
        self.assertEqual(self.interp.last_error, code)

    def test_envelope_repeated_key_is_not_json(self):
        content = json.dumps({"op": "a"})
        msg = json.dumps({"role": "assistant", "content": content})
        for raw in (f'{{"done": true, "done": false, "message": {msg}}}',
                    f'{{"done": false, "done": true, "message": {msg}}}',  # the last value alone would be accepted
                    f'{{"done": true, "message": {{"content": {json.dumps(content)}, "content": "{{}}"}}}}',
                    f'{{"done": true, "d\\u006fne": true, "message": {msg}}}'):  # same key spelled with an escape
            with self.subTest(raw=raw):
                self.assert_failed(raw.encode(), "not-json")

    def test_envelope_non_finite_constant_is_not_json(self):
        msg = json.dumps({"role": "assistant", "content": json.dumps({"op": "a"})})
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                self.assert_failed(f'{{"done": true, "eval_count": {constant}, "message": {msg}}}'.encode(), "not-json")

    def test_content_repeated_key_or_constant_is_shape(self):
        for content in ('{"op": "a", "op": "b"}', '{"op":"a" ,  "op" : "a"}', '{"op": "a", "\\u006fp": "b"}',
                        '{"args": {"item": {"price": 1, "price": 2}}}', '{"ops": [{"op": "a"}, {"x": 1, "x": 2}]}',
                        '{"price": -Infinity}', '{"price": Infinity}', '{"args": {"price": NaN}}'):
            with self.subTest(content=content):
                self.assert_failed(envelope(content), "shape")

    def test_case_variants_and_sibling_keys_are_accepted(self):
        for content in ('{"a": 1, "A": 2}', '{"x": {"op": "a"}, "y": {"op": "b"}}', '{"ops": [{"p": 1}, {"p": 2}]}',
                        '{"price": "NaN", "note": "Infinity"}'):
            with self.subTest(content=content):
                self.assertEqual(self.run_reply(envelope(content)), json.loads(content))
                self.assertIsNone(self.interp.last_error)

    def test_well_formed_reply_decodes_as_before(self):
        content = json.dumps({"ops": [{"op": "set_price", "args": {"item": "Hass", "price": 4.5}}], "count": 1})
        self.assertEqual(self.run_reply(envelope(content)), json.loads(content))
        self.assertIsNone(self.interp.last_error)
        content = '{"price": 1e308, "note": "-Infinity"}'  # large finite numbers and constant-like strings are fine
        self.assertEqual(self.run_reply(envelope(content)), json.loads(content))
        self.assertIsNone(self.interp.last_error)

    def test_last_error_is_a_code_only(self):
        for raw in (envelope('{"REPLY-MARKER": 1, "REPLY-MARKER": 2}'), b'{"done": true, "OWNER-TEXT-MARKER": NaN}'):
            self.run_reply(raw)
            self.assertIn(self.interp.last_error, ("not-json", "shape"))
            for marker in ("MARKER", URL, "127.0.0.1", "REPLY", "NaN"):
                self.assertNotIn(marker, self.interp.last_error)


if __name__ == "__main__":
    unittest.main()
