"""HASS-CLOUD-CODEX-1: Hass's cloud reads through the Hermes-side runner. Fake runners and a fake HTTP post only: no network.
Run: python3 -m unittest discover -s hass/tests -p 'test_cloud_codex.py' -v
"""
import io
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from hass import answer_reader, cloud_codex, cloud_codex_hermes as hermes, conversation, host, interpreter_local, label_reader
from hass.clover import chat
from hass.tests.test_clover_chat import BLOCK, seed
from hass.tests.test_conversation import ConversationTestCase

TOKEN, SECRET = "tok-SECRET-123", "PROMPT-SECRET-words"
LOCAL = {"url": "http://127.0.0.1:8010", "model": "qwen", "api": "openai", "timeout": 60}
BLOCK_OK = {"api": "codex", "model": "gpt-6.1-sol", "effort": "low", "timeout": 12, "fallback": LOCAL}
SSE = ['data: {"type": "response.output_text.delta", "delta": "{\\"question\\": "}', "",
       'data: {"type": "response.output_text.delta", "delta": "\\"Which day should change?\\"}"}', "",
       'data: {"type": "response.completed"}', "", "data: [DONE]"]


def request(**over):
    return json.dumps({"model": "gpt-6.1-sol", "effort": "low", "instructions": SECRET, "text": "hi", "images": [],
                       "timeout": 12, **over})


def chat_reply(text):
    return 200, json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": text}}]}).encode()


class FakeRunner:
    def __init__(self, *said):
        self.said, self.requests = list(said), []

    def __call__(self, req):
        self.requests.append(req)
        return self.said.pop(0) if len(self.said) > 1 else self.said[0]


OK = {"ok": True, "text": '{"question": "Which day should change?"}', "model": "gpt-6.1-sol", "ms": 2100}
TILL = ["change the price of X to 5", "set X to 7", "change the price of website honey to 5", "honey is $6 now", "jam costs 5 dollars",
        "how many jars of honey do we have", "is honey in stock", "low stock", "give the plum jam a sku", "scan the barcode on the jam",
        "qty 12 eggs", "new item: plum jam", "update the count of eggs to 12", "mark jam down 20%", "add plum jam to the till",
        "we received 12 jars of honey", "make the eggs 4.50 a dozen, set them to 4.5", "what did we sell today"]
CLOUD = ["when should the hours change?", "move saturday's hike to 5pm", "change the hike to 10:30 am", "put the new photo on the website"]
NUMBERS = ["honey is 4.50 a jar", "we have 7 jars of honey", "seven jars of honey left", "honey's four fifty now", "a dozen eggs came in"]
ORDINARY = ["are we open tomorrow", "move the hike to 5pm", "open at 10:30 am on Nov 18", "make the home page photo brighter"]


def codex(runner, prompt=SECRET):
    return interpreter_local.LocalInterpreter(None, "gpt-6.1-sol", prompt, timeout=12, api="codex",
                                              transport=cloud_codex.CodexTransport("low", runner))


class HermesRunnerTests(unittest.TestCase):
    """The real Hermes-side runner, its credential resolution and HTTP post injected by argument."""

    def run_one(self, status=200, lines=SSE, raw=None, token=TOKEN, post=None):
        self.sent = []

        def fake_post(url, headers, payload, timeout):
            self.sent.append((url, headers, payload, timeout))
            return status, lines
        out = io.StringIO()
        hermes.main(["x", "/root"], io.StringIO(raw or request()), out, lambda root: (lambda: (token, "https://cg/x/"), post or fake_post))
        self.assertNotIn(SECRET, out.getvalue())
        self.assertNotIn(TOKEN, out.getvalue())
        return json.loads(out.getvalue())

    def test_one_streamed_responses_request_and_its_text(self):
        said = self.run_one(raw=request(images=["data:image/png;base64,AAAA"]))
        self.assertEqual((said["ok"], said["text"], said["model"]), (True, '{"question": "Which day should change?"}', "gpt-6.1-sol"))
        url, headers, payload, timeout = self.sent[0]
        self.assertEqual((url, headers["Authorization"], timeout), ("https://cg/x/responses", "Bearer " + TOKEN, 12))
        self.assertEqual((payload["stream"], payload["store"], payload["reasoning"], payload["instructions"]), (True, False, {"effort": "low"}, SECRET))
        self.assertEqual(payload["input"][0]["content"], [{"type": "input_text", "text": "hi"},
                                                          {"type": "input_image", "image_url": "data:image/png;base64,AAAA"}])

    def test_every_failure_is_one_short_code(self):
        def timeout(*a): raise TimeoutError
        cases = {"auth": [dict(status=401), dict(status=403), dict(token=None)], "rate": [dict(status=429)],
                 "model": [dict(status=400, lines=['{"error": {"code": "model_not_found"}}'])],
                 "api": [dict(status=500), dict(lines=['data: {"type": "response.failed"}']), dict(lines=["data: {bad"]), dict(lines=[])],
                 "timeout": [dict(post=timeout)], "usage": [dict(raw="{}"), dict(raw=request(timeout=21)), dict(raw=request(text="", images=[]))]}
        for code, kws in cases.items():
            for kw in kws:
                with self.subTest(code=code, kw=kw):
                    said = self.run_one(**kw)
                    self.assertEqual((said["ok"], said["code"], set(said)), (False, code, {"ok", "code", "ms"}))

    def test_no_hermes_is_hermes(self):
        out = io.StringIO()
        hermes.main(["x", "/root"], io.StringIO(request()), out, lambda root: 1 / 0)
        self.assertEqual(json.loads(out.getvalue()), {"ok": False, "code": "hermes", "ms": 0})


class HassSideTests(unittest.TestCase):
    def setUp(self):
        cloud_codex._alerted.clear()

    def test_the_same_parse_as_openai_and_the_request_it_sends(self):
        runner = FakeRunner(OK)
        openai = interpreter_local.LocalInterpreter("http://127.0.0.1:8010", "m", SECRET, api="openai", transport=lambda *a: chat_reply(OK["text"]))
        got = codex(runner).interpret("when?", [])
        self.assertEqual(got, openai.interpret("when?", []))
        req = runner.requests[0]
        self.assertEqual((req["model"], req["effort"], req["instructions"], req["images"], req["timeout"]), ("gpt-6.1-sol", "low", SECRET, [], 12))
        self.assertEqual(json.loads(req["text"])["message"], "when?")

    def test_every_code_falls_back_once_with_one_alert_an_hour(self):
        for code in cloud_codex.CODES:
            local = interpreter_local.LocalInterpreter("http://127.0.0.1:8010", "qwen", SECRET, api="openai", transport=lambda *a: chat_reply(OK["text"]))
            itp = interpreter_local.FallbackInterpreter(codex(FakeRunner({"ok": False, "code": code, "ms": 5})), local, lambda r: True)
            with self.subTest(code=code), self.assertLogs("hass.cloud", "ERROR") as logs:
                self.assertEqual(itp.interpret("when?", []), {"question": "Which day should change?"})
                self.assertEqual(itp.interpret("when?", []), {"question": "Which day should change?"})
            self.assertEqual(logs.output, [f"ERROR:hass.cloud:ALERTS hass-cloud: {code}"])
            self.assertEqual((itp.last_backend, itp.last_fallback, itp.last_primary_error, itp.last_model), ("openai", True, f"codex-{code}", "qwen"))
            self.assertEqual(cloud_codex.transcript(itp)["backend"], "local-fallback")
            self.assertNotIn(SECRET, " ".join(logs.output))

    def test_a_slow_runner_is_stopped_at_its_timeout_then_local_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            slow = Path(tmp) / "python"
            slow.write_text("#!/bin/sh\nexec sleep 30\n")
            os.chmod(slow, 0o700)
            runner = cloud_codex.Runner()
            runner.found = (str(slow), tmp)
            local = interpreter_local.LocalInterpreter("http://127.0.0.1:8010", "q", "p", timeout=60, api="openai", transport=lambda *a: chat_reply(OK["text"]))
            itp = interpreter_local.FallbackInterpreter(codex(runner), local, lambda r: True)
            started = time.monotonic()
            with mock.patch.object(cloud_codex, "SLACK", -11), self.assertLogs("hass.cloud", "ERROR"):
                self.assertEqual(itp.interpret("when?", []), {"question": "Which day should change?"})
        self.assertLess(time.monotonic() - started, 5)  # 12 + SLACK(-11) = 1 s of cloud; the real bound is 12 + 3 = 15 s
        self.assertEqual(itp.last_primary_error, "codex-timeout")

    def test_answer_and_label_readers_use_codex_then_their_local_fallback(self):
        runner = FakeRunner({"ok": True, "text": '{"name": "Wood Glue", "brand": "Gorilla"}', "model": "gpt-6.1-sol", "ms": 9},
                            {"ok": False, "code": "rate", "ms": 1})
        labels = cloud_codex.reader(label_reader.LabelReader, BLOCK_OK, cloud_codex.CodexTransport("low", runner))
        self.assertEqual(labels.read(b"\x89PNG\r\n\x1a\nxx", []), {"name": "Wood Glue", "brand": "Gorilla"})
        req = runner.requests[0]
        self.assertEqual((req["instructions"], req["text"], req["images"][0][:22]), (label_reader.PROMPT, "", "data:image/png;base64,"))
        answers = cloud_codex.reader(answer_reader.AnswerReader, BLOCK_OK, cloud_codex.CodexTransport("low", runner), think=None)
        answers.fallback.transport = lambda *a: chat_reply('{"value": true}')
        with self.assertLogs("hass.cloud", "ERROR"):
            self.assertEqual(answers.read("new_badge", "yes it is new", date(2026, 11, 16)), {"value": True})
        self.assertEqual((answers.last_fallback, answers.last_primary_error, answers.calls), (True, "codex-rate", 2))
        self.assertIsInstance(labels.fallback.transport, cloud_codex.Remaining)  # both readers' fallbacks are inside BUDGET
        sent = len(runner.requests)
        for key, words in (("price", "nine fifty-seven"), ("cost", "4.31"), ("qty", "a dozen jars"), ("low_stock", "3"), ("best_by", "next friday")):
            answers.fallback.transport = lambda *a: chat_reply('{"value": "1"}')
            with self.subTest(key=key):
                self.assertEqual(answers.read(key, words, date(2026, 11, 16)), {"value": "1"})
                self.assertEqual((len(runner.requests), answers.last_primary_error), (sent, "codex-local"))

    def test_till_price_and_stock_texts_never_reach_the_runner(self):
        runner = FakeRunner(OK)
        local = interpreter_local.LocalInterpreter("http://127.0.0.1:8010", "q", "p", api="openai", transport=lambda *a: chat_reply(OK["text"]))
        itp = interpreter_local.FallbackInterpreter(codex(runner), local, lambda r: True)
        for text in TILL:
            with self.subTest(text=text):
                self.assertEqual(itp.interpret(text, []), {"question": "Which day should change?"})
                self.assertEqual((runner.requests, itp.last_fallback, itp.last_primary_error), ([], True, "codex-local"))
        itp.interpret("5", [], recent={"question": "Which day should change?", "earlier": ["change the price of honey"]})
        itp.interpret("ok", [], notes=["honey is $6 a jar"])
        self.assertEqual((runner.requests, cloud_codex._alerted), ([], {}))  # a local route, never an alert
        for text in CLOUD:
            itp.interpret(text, [])
        self.assertEqual([json.loads(r["text"])["message"] for r in runner.requests], CLOUD)

    def test_the_fallback_gets_only_what_is_left_of_the_budget(self):
        seen, codex_side = [], cloud_codex.CodexTransport("low", FakeRunner(OK))
        now = [120.0]
        fallback = cloud_codex.Remaining(codex_side, lambda u, b, h, timeout: seen.append(timeout) or chat_reply("{}"), clock=lambda: now[0])
        codex_side.started = 100.0
        fallback("u", b"", {}, 60)
        fallback("u", b"", {}, 60)  # no codex start since: the whole budget, still capped by its own timeout
        fallback("u", b"", {}, 5)
        self.assertEqual(seen, [cloud_codex.BUDGET - 20, cloud_codex.BUDGET, 5])
        codex_side.started, now[0] = 100.0, 100.0 + cloud_codex.BUDGET - 0.5
        with self.assertRaises(interpreter_local._Failed) as failed:
            fallback("u", b"", {}, 60)
        self.assertEqual((failed.exception.args[0], len(seen)), ("timeout", 3))

    def test_an_expired_active_start_fails_closed_and_never_calls_the_fallback(self):
        called, now, codex_side = [], [0.0], cloud_codex.CodexTransport("low", FakeRunner(OK))
        fallback = cloud_codex.Remaining(codex_side, lambda *a: called.append(a) or chat_reply("{}"), clock=lambda: now[0])
        for at in (129.0, 127.5, 100.0 + cloud_codex.BUDGET, 1000.0):  # over the budget, under 1 s left, exactly spent, long stale
            codex_side.started, now[0] = 100.0, at
            with self.subTest(now=at), self.assertRaises(interpreter_local._Failed) as failed:
                fallback("u", b"", {}, 60)
            self.assertEqual((failed.exception.args[0], called, codex_side.started), ("timeout", [], None))
        fallback("u", b"", {}, 60)  # no active start: the whole budget
        self.assertEqual(len(called), 1)
        local = interpreter_local.LocalInterpreter("http://127.0.0.1:8010", "q", "p", timeout=60, api="openai", transport=lambda *a: called.append(a) or chat_reply(OK["text"]))
        itp = interpreter_local.FallbackInterpreter(codex(FakeRunner({"ok": False, "code": "api"})), local, lambda r: True)
        itp.fallback.transport = cloud_codex.Remaining(itp.primary.transport, local.transport, clock=lambda: 129.0)
        with self.assertLogs("hass.cloud", "ERROR"), mock.patch.object(cloud_codex.time, "monotonic", return_value=100.0):  # the codex start
            self.assertEqual(itp.interpret("when?", []), {"unsupported": interpreter_local.FAILED})
        self.assertEqual((len(called), itp.last_primary_error, itp.last_error), (1, "codex-api", "timeout"))

    def test_only_clock_times_and_dates_are_not_numbers(self):
        for text in ("are we open tomorrow", "at 5pm", "5 pm", "10:30", "10:30am", "at noon", "11/16", "2026-11-16", "nov 16", "the 16th",
                     "open at 10:30 am on nov 18.", "a few jars", "2026-11-16t10:00:00-08:00", "someone often said so"):
            with self.subTest(text=text): self.assertFalse(cloud_codex.numbered(text))
        for text in ("4.50", "7 jars", "seven", "four fifty", "a dozen", "half a jar", "a couple of jars", "maybe 5", "decided 12",
                     "5-7pm", "10:30.5", "2 jars at 5pm", "one", "twenty-two", "hundreds"):
            with self.subTest(text=text): self.assertTrue(cloud_codex.numbered(text))

    def test_a_slow_runner_and_a_slow_fallback_finish_inside_the_worker_deadline(self):
        self.assertEqual((cloud_codex.SLACK, cloud_codex.BUDGET), (3, 28))  # the real bound: 20 + 3 of cloud, then what is left
        release = threading.Event()
        self.addCleanup(release.set)
        seen = []

        def stuck(url, body, headers, timeout):
            seen.append(timeout)
            release.wait(120)
            return chat_reply(OK["text"])
        with tempfile.TemporaryDirectory() as tmp:
            slow = Path(tmp) / "python"
            slow.write_text("#!/bin/sh\nexec sleep 60\n")
            os.chmod(slow, 0o700)
            runner = cloud_codex.Runner()
            runner.found = (str(slow), tmp)
            primary = interpreter_local.LocalInterpreter(None, "gpt-6.1-sol", "p", timeout=20, api="codex", transport=cloud_codex.CodexTransport("low", runner))
            local = interpreter_local.LocalInterpreter("http://127.0.0.1:8010", "q", "p", timeout=120, api="openai", transport=stuck)
            itp = interpreter_local.FallbackInterpreter(primary, cloud_codex.budget(primary.transport, local), lambda r: True)
            started = time.monotonic()
            with self.assertLogs("hass.cloud", "ERROR"):
                self.assertEqual(itp.interpret("when?", []), {"unsupported": interpreter_local.FAILED})
            took = time.monotonic() - started
        self.assertLess(took, 30)
        self.assertGreater(took, 20 + cloud_codex.SLACK)  # the slow fallback was really asked, and stopped at the budget
        self.assertEqual((itp.last_primary_error, itp.last_error), ("codex-timeout", "timeout"))
        self.assertLessEqual(seen[0], cloud_codex.BUDGET - 20 - cloud_codex.SLACK + 0.5)

    def test_check_prints_only_result_model_ms_or_a_code(self):
        self.assertEqual(cloud_codex.check(BLOCK_OK, FakeRunner(OK)), {"result": "ok", "model": "gpt-6.1-sol", "ms": 2100})
        self.assertEqual(cloud_codex.check(BLOCK_OK, FakeRunner({"ok": False, "code": "auth", "ms": 3})), {"result": "auth"})
        self.assertEqual(cloud_codex.check(BLOCK_OK, FakeRunner({"ok": False, "code": "<b>"})), {"result": "hermes"})
        self.assertEqual(cloud_codex.Runner(launcher="/nonexistent/hermes")(json.loads(request())), {"ok": False, "code": "hermes"})


class HostConfigTests(unittest.TestCase):
    def test_codex_block_is_closed_and_needs_a_local_fallback(self):
        ok = lambda itp: host._interpreter_ok(itp)  # noqa: E731
        self.assertTrue(ok(BLOCK_OK))
        self.assertTrue(ok({"api": "codex", "model": "gpt-6.1-sol", "fallback": {"url": "http://127.0.0.1:11434", "model": "q", "think": False}}))
        bad = [{"url": "http://127.0.0.1:8010"}, {"keyFile": "/k"}, {"timeout": 21}, {"timeout": 4}, {"effort": "max"}, {"model": "a b"},
               {"fallback": {**LOCAL, "api": "codex"}}, {"fallback": {**LOCAL, "think": False}}, {"fallback": {"url": "https://x.com", "model": "q"}}]
        for over in bad:
            with self.subTest(over=over): self.assertFalse(ok({**BLOCK_OK, **over}))
        self.assertFalse(ok({k: v for k, v in BLOCK_OK.items() if k != "fallback"}))
        self.assertFalse(ok({**LOCAL, "fallback": {"url": "http://127.0.0.1:11434", "model": "q", "api": "ollama"}}))  # loopback rules unchanged

    def test_builder_makes_codex_with_the_local_block_as_fallback(self):
        with mock.patch.object(host, "load_registry"), mock.patch.object(host, "load_content"), \
                mock.patch.object(host.interpreter_prompt, "build", return_value="p"):
            made = host.interpreter_builder({"interpreter": BLOCK_OK}, "/nonexistent")()
        self.assertEqual((made.primary.api, made.primary.timeout, made.primary.transport.effort), ("codex", 12, "low"))
        self.assertEqual((made.fallback.api, made.fallback.url, made.fallback.timeout), ("openai", "http://127.0.0.1:8010/v1/chat/completions", 60))
        self.assertIsInstance(made.fallback.transport, cloud_codex.Remaining)  # 60 s stays configured; the call gets what is left
        self.assertIs(made.fallback.transport.codex, made.primary.transport)


class CloverAndTranscriptTests(ConversationTestCase):
    def test_till_words_never_reach_the_runner_and_an_interpreted_message_gets_its_row(self):
        cloud_codex._alerted.clear()
        runner = FakeRunner(OK)
        local = interpreter_local.LocalInterpreter("http://127.0.0.1:8010", "q", "p", api="openai", transport=lambda *a: 1 / 0)
        self.conv.interpreter = interpreter_local.FallbackInterpreter(codex(runner), local, lambda r: conversation._checked(r) is r)
        seed(Path(self.repo.state))
        self.conv.till = chat.TillDesk(str(self.repo.state), BLOCK)
        self.assertEqual(self.say("change the price of Hass avocado to 5"), "till-write-refused")
        self.assertEqual(runner.requests, [])
        self.say("when should the hours change?")
        self.assertEqual(len(runner.requests), 1)
        row = self.conv.db.execute("SELECT backend, fallback, primary_error, error FROM interpreter_audit").fetchall()
        self.assertEqual([tuple(r) for r in row], [("codex", 0, None, None)])
        self.assertEqual({k: v for k, v in cloud_codex.transcript(self.conv.interpreter).items() if k != "ms"}, {"backend": "codex", "model": "gpt-6.1-sol"})

    def test_the_returned_till_texts_reach_no_runner_with_or_without_a_till(self):
        runner = FakeRunner(OK)
        local = interpreter_local.LocalInterpreter("http://127.0.0.1:8010", "q", "p", api="openai", transport=lambda *a: 1 / 0)
        self.conv.interpreter = interpreter_local.FallbackInterpreter(codex(runner), local, lambda r: conversation._checked(r) is r)
        self.conv.till = None
        self.say("change the price of X to 5")
        seed(Path(self.repo.state))
        self.conv.till = chat.TillDesk(str(self.repo.state), BLOCK)
        self.say("set X to 7")
        self.say("change the price of website honey to 5")
        self.assertEqual(runner.requests, [])

    def test_a_number_never_reaches_the_runner_with_or_without_a_till_and_ordinary_texts_do(self):
        cloud_codex._alerted.clear()
        seed(Path(self.repo.state))
        for till in (None, chat.TillDesk(str(self.repo.state), BLOCK)):
            runner = FakeRunner(OK)
            local = interpreter_local.LocalInterpreter("http://127.0.0.1:8010", "q", "p", api="openai", transport=lambda *a: 1 / 0)
            self.conv.interpreter = interpreter_local.FallbackInterpreter(codex(runner), local, lambda r: conversation._checked(r) is r)
            self.conv.till = till
            for text in NUMBERS:
                with self.subTest(till=bool(till), text=text):
                    self.say(text)
                    self.assertEqual(runner.requests, [])
            self.assertEqual(cloud_codex._alerted, {})
            for text in ORDINARY:
                self.say(text)
            self.assertEqual([json.loads(r["text"])["message"] for r in runner.requests], ORDINARY)
        photo = FakeRunner({"ok": True, "text": '{"name": "Wood Glue"}', "model": "gpt-6.1-sol", "ms": 9})  # a captionless photo turn
        cloud_codex.reader(label_reader.LabelReader, BLOCK_OK, cloud_codex.CodexTransport("low", photo)).read(b"\x89PNG\r\n\x1a\nxx", [])
        self.assertEqual((len(photo.requests), photo.requests[0]["text"], len(photo.requests[0]["images"])), (1, "", 1))


if __name__ == "__main__":
    unittest.main()
