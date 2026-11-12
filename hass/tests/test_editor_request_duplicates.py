"""RF0540-10 tests: editor prepare refuses a serialized request with a repeated JSON member at any depth.

A repeated member (equal or conflicting, literal or escaped) used to decode last-key-wins and be drafted silently.
Now it is the one generic "request is not valid JSON" result: no compute, no draft, no echo of the key or value.
Reuses the throwaway writer repo from test_editor_request_limits (aliased, so its TestCases are not rediscovered).
Run: python3 -m unittest hass.tests.test_editor_request_duplicates -v
"""

import json
import unittest
from unittest import mock

from hass import editor
from hass.tests import test_editor_request_limits as limits
from hass.tests.test_editor import HOURS, NEW_HOURS

NOT_JSON = limits.NOT_JSON
CANARY_KEY, CANARY_VALUE = "canary-key-9f3a", "canary-value-7c1d"
CALL = '{"op": "test.set_store_hours", "args": {"hours": ["Closed Sunday"]}}'


def _ops(*calls):
    return ('{"ops": [' + ", ".join(calls) + "]}").encode("utf-8")


class ParserTests(unittest.TestCase):
    def test_duplicate_members_refuse_at_each_depth(self):
        cases = {
            "top ops, equal": '{"ops": [], "ops": []}',
            "top ops, reversed": '{"ops": [' + CALL + '], "ops": []}',
            "call op": '{"ops": [{"op": "a.b", "op": "c.d", "args": {}}]}',
            "call args": '{"ops": [{"op": "a.b", "args": {}, "args": {"x": 1}}]}',
            "argument text": '{"ops": [{"op": "a.b", "args": {"text": "First", "text": "Last"}}]}',
            "nested object": '{"ops": [{"op": "a.b", "args": {"o": {"k": 1, "k": 1}}}]}',
            "nested in list": '{"ops": [{"op": "a.b", "args": {"l": [{"k": 1}, {"k": 1, "k": 2}]}}]}',
            "first operation": '{"ops": [{"op": "a.b", "args": {"k": 1, "k": 2}}, ' + CALL + "]}",
            "last operation": "{\"ops\": [" + CALL + ', {"op": "a.b", "args": {"k": 1, "k": 2}}]}',
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                self.assertEqual(editor._parse_request(text), (None, NOT_JSON["problems"]))

    def test_escaped_keys_compare_after_json_decoding(self):
        same = ['{"ops": [], "\\u006fps": []}', '{"ops": [{"op": "a.b", "args": {"caf\\u00e9": 1, "café": 2}}]}',
                '{"ops": [{"op": "a.b", "args": {"\\u0041": 1, "A": 2}}]}']
        for text in same:
            with self.subTest(case=text):
                self.assertEqual(editor._parse_request(text), (None, NOT_JSON["problems"]))
        distinct = '{"ops": [{"op": "a.b", "args": {"A": 1, "a": 2, "e\\u0301": 3, "\\u00e9": 4}}]}'
        ops, problems = editor._parse_request(distinct)  # no casefold, no Unicode normalization
        self.assertEqual(problems, [])
        self.assertEqual((ops or [{}])[0]["args"], {"A": 1, "a": 2, "e\u0301": 3, "\u00e9": 4})
        text = '{"ops": [{"op": "a.b", "args": {"%s": "%s", "%s": "x"}}]}' % (CANARY_KEY, CANARY_VALUE, CANARY_KEY)
        self.assertEqual(editor._parse_request(text), (None, NOT_JSON["problems"]))
        self.assertNotIn(CANARY_KEY, repr(editor._parse_request(text)))

    def test_existing_size_depth_utf8_control_and_surrogate_precedence(self):
        dup_pad = b'{"ops": [], "ops": [], "pad": "' + b"x" * editor.MAX_REQUEST + b'"}'
        self.assertEqual(editor._parse_request(dup_pad), (None, ["request is larger than 64 KiB"]))
        exact = b'{"a": 1, "a": 2}'.ljust(editor.MAX_REQUEST)
        self.assertEqual(editor._parse_request(exact), (None, NOT_JSON["problems"]))  # at the cap: parsed, then refused
        self.assertEqual(editor._parse_request(b"[" * 60000), (None, NOT_JSON["problems"]))
        self.assertEqual(editor._parse_request(b'{"ops": [], "\xff": 1}'), (None, NOT_JSON["problems"]))
        self.assertEqual(editor._parse_request(b'{"ops": ["\\ud800"]}'),
                         (None, ["request has unpaired surrogate characters"]))
        control = '{"ops": [{"op": "a.b", "args": {"t": "x\\u0000"}}]}'
        self.assertEqual(editor._parse_request(control), (None, ["control characters are not allowed"]))


class DuplicatePrepareTests(limits.RequestLimitTestCase):
    def test_prepare_duplicate_request_never_computes_or_writes_draft(self):
        good = self.r.prepare({"ops": [{"op": HOURS, "args": {"hours": NEW_HOURS}}]})["draft"]  # an existing draft must be retained untouched
        before = (self.r.drafts(), self.r.head(), self.r.status(),
                  (self.r.state / "drafts" / f"{good['change_id']}.json").read_bytes())
        late = _ops(CALL, '{"op": "%s", "args": {"hours": ["A"], "hours": ["%s"]}}' % (HOURS, CANARY_VALUE))
        for name, request in {"str": late.decode(), "bytes": late,
                              "top ops": b'{"ops": [' + CALL.encode() + b'], "ops": [' + CALL.encode() + b"]}"}.items():
            with self.subTest(case=name), mock.patch.object(editor, "_compute") as compute, \
                    mock.patch.object(editor, "apply") as apply:
                self.assertEqual(self.r.prepare(request), NOT_JSON)
                compute.assert_not_called()
                apply.assert_not_called()
        self.assertEqual((self.r.drafts(), self.r.head(), self.r.status(),
                          (self.r.state / "drafts" / f"{good['change_id']}.json").read_bytes()), before)

    def test_cli_duplicate_file_is_one_invalid_json_line(self):
        text = '{"ops": [{"op": "%s", "args": {"hours": ["x"], "%s": "%s", "%s": "y"}}]}' % (
            HOURS, CANARY_KEY, CANARY_VALUE, CANARY_KEY)
        code, line = self.run_cli(self.write("dup.json", text.encode()))  # run_cli asserts empty stderr, one line
        self.assertEqual((code, line), (1, NOT_JSON))
        self.assertNotIn(CANARY_KEY, json.dumps(line))
        self.assertEqual(self.r.drafts(), [])
        self.assertEqual(self.r.status(), "")


class UniqueRequestTests(limits.RequestLimitTestCase):
    def test_unique_requests_keep_identity_and_array_semantics(self):
        as_dict = {"ops": [{"op": HOURS, "args": {"hours": NEW_HOURS}}]}
        text = json.dumps(as_dict, ensure_ascii=False)
        first = self.r.prepare(as_dict)
        self.assertEqual(first["result"], "ok", first)
        for request in (text, text.encode("utf-8")):
            self.assertEqual(self.r.prepare(request), first)  # same draft, hash and id
        self.assertEqual(self.r.drafts(), [first["draft"]["change_id"] + ".json"])
        code, line = self.run_cli(self.write("same.json", limits.VALID))  # CLI: real registry, so the real op
        self.assertEqual(code, 0, line)
        self.assertEqual(line, editor.prepare(json.loads(limits.VALID), state=str(self.r.state)))  # dict == file
        # the same key in distinct call objects is legal; repeated operations stay ordered
        ops, problems = editor._parse_request(_ops(CALL, CALL))
        self.assertEqual((problems, [c["op"] for c in ops or []]), ([], [HOURS, HOURS]))
        # a nested unique object passes parse admission even though typed validation refuses it afterwards
        nested = {"ops": [{"op": HOURS, "args": {"hours": {"a": {"a": 1}}}}]}
        self.assertEqual(editor._parse_request(json.dumps(nested))[1], [])
        refused = self.r.prepare(nested)
        self.assertEqual(refused["result"], "invalid")
        self.assertNotEqual(refused, NOT_JSON)


if __name__ == "__main__":
    unittest.main()
