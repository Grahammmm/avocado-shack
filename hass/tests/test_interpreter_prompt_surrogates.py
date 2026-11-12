"""RF0421-11 tests: prompt JSON literals escape surrogate code points only. No model call.

Run: python3 -B -m unittest hass.tests.test_interpreter_prompt_surrogates -v
"""

import copy
import json
import unittest
from unittest import mock

from hass import interpreter_prompt as ip
from hass.tests.test_interpreter_prompt import FIXTURE, TEST_REGISTRY, tiny_content

HI, LO = "\ud800", "\udfff"


class LiteralTest(unittest.TestCase):
    def test_q_high_low_endpoints_and_mixed_surrogates_are_json_escapes(self):
        cases = {
            "\ud800": '"\\ud800"', "\udbff": '"\\udbff"', "\udc00": '"\\udc00"', "\udfff": '"\\udfff"',
            "a\ud800": '"a\\ud800"', "a\udfffb": '"a\\udfffb"', "\udc00\ud800": '"\\udc00\\ud800"',
            "\ud800\ud800": '"\\ud800\\ud800"', "\ud83d\ude00": '"\\ud83d\\ude00"',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=ascii(raw)):
                out = ip._q(raw)
                self.assertEqual(out, expected)
                out.encode("utf-8")
                self.assertEqual(json.loads(out), json.loads(expected))
        self.assertEqual(json.loads(ip._q(HI)), HI)
        self.assertEqual(json.loads(ip._q("\ud83d\ude00")), "\U0001F600")

    def test_scalar_unicode_and_existing_escape_bytes_are_identical(self):
        for raw in ("Café 🥑", "e\u0301", "牛油果", 'q"b\\n\nz', "\x85\u2028\u2029", "\\ud800 text"):
            with self.subTest(raw=raw):
                legacy = json.dumps(raw, ensure_ascii=False)
                for k, v in ip._LINE_BREAKS.items():
                    legacy = legacy.replace(k, v)
                self.assertEqual(ip._q(raw).encode("utf-8"), legacy.encode("utf-8"))
        self.assertEqual(ip._q("\\ud800"), '"\\\\ud800"')
        self.assertEqual(ip._q(None), '""')
        self.assertEqual(ip._q(12), '"12"')


class BuildTest(unittest.TestCase):
    def test_build_surrogate_data_in_each_q_formatted_section(self):
        bad = f"bad{HI}x{LO}"
        esc = "bad\\ud800x\\udfff"
        content = tiny_content(
            products=[{"id": f"p{HI}", "name": bad, "brand": bad, "status": bad, "description": bad},
                      {"id": "ok", "name": "Fine", "status": "active", "description": "fine"}],
            makers={f"k{LO}": {"name": bad}})
        content.community = {"events": [{"id": f"e{HI}", "title": bad, "startsAt": bad, "status": "scheduled",
                                         "meetingPoint": bad, "bring": bad, "accessNote": bad, "capacity": 3}],
                             "routeIdeas": [{"id": f"r{LO}", "title": bad}]}
        content.store = {"streetAddress": bad, "town": bad, "hours": [bad], "intro": bad, "headline": [bad],
                         "story": bad, "notice": {"text": bad, "until": bad}}
        snapshot = copy.deepcopy(content.__dict__)
        prompt = ip.build(TEST_REGISTRY, content)
        prompt.encode("utf-8")
        self.assertEqual(prompt, ip.build(TEST_REGISTRY, content))
        self.assertEqual(content.__dict__, snapshot)
        self.assertGreaterEqual(prompt.count(f'"{esc}"'), 10)
        self.assertNotIn(HI, prompt)
        self.assertNotIn(LO, prompt)
        self.assertIn('"ok" | "Fine" | "" | "active" | "fine"', prompt)

    def test_existing_golden_and_skills_block_unchanged(self):
        self.assertEqual(ip.build(TEST_REGISTRY, tiny_content()), FIXTURE.read_text("utf-8"))


class CapTest(unittest.TestCase):
    def _products(self):
        return [{"id": f"p{i}", "name": "n", "status": "active", "description": HI * 40 + f"{i}"} for i in range(3)]

    def test_description_escaped_bytes_drive_whole_omission(self):
        content = tiny_content(products=self._products(), makers={})
        full = ip.build(TEST_REGISTRY, content)
        one = len(ip._q(HI * 40 + "0").encode("utf-8"))
        self.assertGreater(one, 40 * 6)
        cap = len(full.encode("utf-8")) - 1
        with mock.patch.object(ip, "PROMPT_MAX_BYTES", cap):
            prompt = ip.build(TEST_REGISTRY, content)
        prompt.encode("utf-8")
        self.assertLessEqual(len(prompt.encode("utf-8")), cap)
        self.assertIn(ip.OMITTED, prompt)
        for i in range(3):  # every description is whole or omitted, never cut
            whole = ip._q(HI * 40 + f"{i}") in prompt
            self.assertTrue(whole or f'"p{i}" | "n" | "" | "active" | {ip.OMITTED}' in prompt)

    def test_non_description_overcap_still_refuses(self):
        content = tiny_content(products=[{"id": "a", "name": HI * 200, "status": "active"}], makers={})
        with mock.patch.object(ip, "PROMPT_MAX_BYTES", len(ip.build(TEST_REGISTRY, tiny_content(products=[], makers={})
                                                                    ).encode("utf-8")) + 300):
            with self.assertRaisesRegex(ValueError, "prompt too large"):
                ip.build(TEST_REGISTRY, content)


if __name__ == "__main__":
    unittest.main()
