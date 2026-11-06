"""NB-AV-02 tests: the local-model interpreter adapter (Ollama JSON chat) with a fake transport only.

No test opens a socket or calls a model. The conversation tests reuse the H05 fixture conversation (ConversationTestCase,
test-only fixture ops registry) with LocalInterpreter in place of the FixtureInterpreter.
Run: python3 -m unittest hass.tests.test_interpreter_local -v
"""

import json
import os
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from unittest import mock

from hass import interpreter_local
from hass.interpreter_local import FAILED, MAX_BODY, LocalInterpreter
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS

URL, MODEL, PROMPT = "http://127.0.0.1:11434", "qwen-local-test", "SYSTEM-PROMPT-MARKER: reply with JSON."
OWNER_TEXT = "Change the hours, señora — OWNER-TEXT-MARKER"
PENDING = [{"code": "beef", "state": "proposed", "summary": "Hours → Daily 8am–7pm"}]
GOOD = _ops((HOURS, {"hours": NEW_HOURS}))


def chat_reply(content, done=True):
    return json.dumps({"model": MODEL, "message": {"role": "assistant", "content": content}, "done": done}).encode()


class FakeTransport:
    """Records each call; returns (status, body) or raises the configured exception."""

    def __init__(self, result=(200, chat_reply(json.dumps(GOOD)))):
        self.result, self.calls = result, []

    def __call__(self, url, body, headers, timeout):
        self.calls.append((url, body, headers, timeout))
        if isinstance(self.result, BaseException): raise self.result
        return self.result


FAILURES = [  # (transport result, reason code)
    (TimeoutError("timed out"), "timeout"),
    (urllib.error.URLError(TimeoutError("timed out")), "timeout"),
    (ConnectionRefusedError(111, "Connection refused"), "connect"),
    (urllib.error.URLError(ConnectionRefusedError(111, "refused")), "connect"),
    (RuntimeError(f"{URL}/api/chat {OWNER_TEXT} {PROMPT}"), "connect"),
    ((500, b'{"error": "boom"}'), "http-500"),
    ((302, b""), "http-302"),
    ((200, b" " * (300 * 1024)), "too-large"),
    ((200, b"not json"), "not-json"),
    ((200, b"\xff\xfe"), "not-json"),
    ((200, json.dumps({"message": {}, "done": True}).encode()), "shape"),
    ((200, json.dumps({"done": True}).encode()), "shape"),
    ((200, b"[1, 2]"), "shape"),
    ((200, chat_reply("[1,2]")), "shape"),
    ((200, chat_reply("not json")), "shape"),
    ((200, chat_reply(json.dumps(GOOD), done=False)), "shape"),
    ((200, chat_reply(json.dumps(GOOD), done=None)), "shape"),
]


class AdapterTests(unittest.TestCase):
    def make(self, result=None, **kw):
        self.fake = FakeTransport() if result is None else FakeTransport(result)
        kw.setdefault("clock", lambda: datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc))
        return LocalInterpreter(URL, MODEL, PROMPT, transport=self.fake, **kw)

    def test_request_shape(self):
        interp = self.make(timeout=45)
        self.assertEqual(interp.interpret(OWNER_TEXT, PENDING), GOOD)
        self.assertIsNone(interp.last_error)
        [(url, body, headers, timeout)] = self.fake.calls
        self.assertEqual((url, timeout, headers["Content-Type"]), (f"{URL}/api/chat", 45, "application/json"))
        sent = json.loads(body.decode("utf-8"))
        self.assertEqual({k: sent[k] for k in ("model", "stream", "format", "options")},
                         {"model": MODEL, "stream": False, "format": "json", "options": {"temperature": 0}})
        system, user = sent["messages"]
        self.assertEqual(system, {"role": "system", "content": PROMPT})
        self.assertEqual(user["role"], "user")
        self.assertEqual(json.loads(user["content"]),
                         {"message": OWNER_TEXT, "pending": PENDING, "today": "2026-11-07", "weekday": "Saturday"})
        self.assertIn("señora", user["content"])  # non-ASCII kept, not \u-escaped
        self.assertIn("señora".encode("utf-8"), body)

    def test_good_replies_are_returned_as_is(self):
        for result in (GOOD, {"question": "Which day?"}, {"unsupported": "No."}, {"anything": 1}):
            with self.subTest(result=result):
                self.assertEqual(self.make((200, chat_reply(json.dumps(result)))).interpret("x", []), result)
        padded = chat_reply(json.dumps(GOOD))
        padded += b" " * (MAX_BODY - len(padded))  # exactly the limit is still read
        self.assertEqual(self.make((200, padded)).interpret("x", []), GOOD)

    def test_each_failure_is_the_fixed_unsupported_reply(self):
        for result, code in FAILURES:
            with self.subTest(code=code, result=repr(result)[:60]):
                interp = self.make(result)
                out = interp.interpret(OWNER_TEXT, PENDING)
                self.assertEqual((out, interp.last_error), ({"unsupported": FAILED}, code))
                for secret in (URL, "127.0.0.1", "/api/chat", PROMPT, "OWNER-TEXT-MARKER", "señora"):
                    self.assertNotIn(secret, json.dumps(out, ensure_ascii=False) + str(interp.last_error))

    def test_last_error_clears_after_a_good_call(self):
        interp = self.make((500, b""))
        interp.interpret("x", [])
        self.assertEqual(interp.last_error, "http-500")
        self.fake.result = (200, chat_reply(json.dumps(GOOD)))
        self.assertEqual(interp.interpret("x", []), GOOD)
        self.assertIsNone(interp.last_error)

    def test_constructor_refusals(self):
        bad_urls = ["https://127.0.0.1", "http://10.0.0.5", "http://user@localhost", "http://user:pw@127.0.0.1:11434",
                    "http://localhost/api?x=1", "http://localhost/?", "http://localhost#x", "http://localhost/api",
                    "http://127.0.0.1.example.com", "http://localhost:99999", "http://localhost:abc", "ftp://localhost",
                    "localhost:11434", "", None, b"http://localhost"]
        for url in bad_urls:
            with self.subTest(url=url), self.assertRaises(ValueError) as caught:
                LocalInterpreter(url, MODEL, PROMPT, transport=FakeTransport())
            self.assertEqual(str(caught.exception), "interpreter URL must be loopback http")
        for kw in ({"model": ""}, {"model": "qwen local"}, {"model": "qwen\t"}, {"model": "m" * 101}, {"model": None},
                   {"system_prompt": ""}, {"system_prompt": "  \n"}, {"system_prompt": None}, {"timeout": 0},
                   {"timeout": 121}, {"timeout": True}, {"timeout": 30.0}, {"timeout": "30"}):
            args = {"base_url": URL, "model": MODEL, "system_prompt": PROMPT, "transport": FakeTransport(), **kw}
            with self.subTest(kw=kw), self.assertRaises(ValueError) as caught:
                LocalInterpreter(**args)
            self.assertNotIn("127.0.0.1", str(caught.exception))
        for url, chat in (("http://localhost:11434/", "http://localhost:11434/api/chat"),
                          ("http://[::1]:11434", "http://[::1]:11434/api/chat"), ("http://LOCALHOST", None)):
            interp = LocalInterpreter(url, "m" * 100, PROMPT, timeout=120)
            self.assertEqual(interp.url, chat or "http://LOCALHOST/api/chat")
            self.assertIs(interp.transport, interpreter_local.urllib_transport)
        self.assertEqual(interpreter_local.check_url("http://127.0.0.1:11434/"), URL)

    def test_default_transport_ignores_env_proxy_and_redirects(self):
        env = {"HTTP_PROXY": "http://proxy.invalid:3128", "http_proxy": "http://proxy.invalid:3128"}
        with mock.patch.dict(os.environ, env):
            default = urllib.request.build_opener().handlers  # a plain opener picks the env proxy up
            handlers = interpreter_local._opener().handlers
        self.assertIn("http://proxy.invalid:3128",
                      [getattr(h, "proxies", {}).get("http") for h in default if isinstance(h, urllib.request.ProxyHandler)])
        proxies = [h for h in handlers if isinstance(h, urllib.request.ProxyHandler)]
        self.assertTrue(all(h.proxies == {} for h in proxies), [h.proxies for h in proxies])
        redirects = [h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
        self.assertEqual([type(h) for h in redirects], [interpreter_local._NoRedirect])
        self.assertIsNone(redirects[0].redirect_request(None, None, 302, "Found", {}, "http://elsewhere.invalid/"))

    def test_default_transport_reports_http_errors_as_status(self):
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError(f"{URL}/api/chat", 302, "Found", {}, None)
        with mock.patch.object(interpreter_local, "_opener", return_value=opener):
            self.assertEqual(interpreter_local.urllib_transport(f"{URL}/api/chat", b"{}", {}, 5), (302, b""))
        [(request,), kwargs] = opener.open.call_args
        self.assertEqual((request.get_method(), request.full_url, kwargs), ("POST", f"{URL}/api/chat", {"timeout": 5}))


class ConversationWithLocalInterpreterTests(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeTransport()
        self.interp = LocalInterpreter(URL, MODEL, PROMPT, transport=self.fake)
        self.conv = self.open()

    def test_good_reply_becomes_a_proposal(self):
        draft, reply = self.propose("please change the hours")
        self.assertEqual(draft["state"], "proposed")
        self.assertIn(draft["code"], reply)
        self.fake.result = (200, chat_reply(json.dumps({"question": "Which day should change?"})))
        self.assertEqual(self.say("and the other thing"), "question")
        self.assertEqual(self.replies(), ["Which day should change?"])
        sent = json.loads(json.loads(self.fake.calls[-1][1])["messages"][1]["content"])
        self.assertEqual([p["code"] for p in sent["pending"]], [draft["code"]])

    def test_failures_reply_fixed_text_and_draft_nothing(self):
        for result, code in FAILURES:
            with self.subTest(code=code, result=repr(result)[:60]):
                self.fake.result = result
                self.assertEqual(self.say(OWNER_TEXT), "reader-failed")
                self.assertEqual(self.replies(), [FAILED])
                self.assertEqual(self.interp.last_error, code)
                self.assertEqual(self.drafts(), [])
                self.assertEqual(sorted((self.repo.state / "drafts").glob("*.json")), [])
        self.assertEqual(self.commits(), 0)


if __name__ == "__main__":
    unittest.main()
