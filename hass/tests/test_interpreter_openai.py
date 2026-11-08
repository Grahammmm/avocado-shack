"""HASS-INTERP-OPENAI-1 tests: the OpenAI-style interpreter backend, the one-retry fallback to the Ollama model, the audit
row, and the host.json keys. Fake transports only: no model is called and no socket is opened (one test proves it).
Run: python3 -B -m unittest hass.tests.test_interpreter_openai -v
"""

import json
import socket
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from unittest import mock

from hass import conversation, host, interpreter_local, label_reader
from hass.interpreter_local import FAILED, FallbackInterpreter, LocalInterpreter, strip_reasoning
from hass.label_reader import LabelReader
from hass.tests.test_conversation import SETTINGS, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS
from hass.tests.test_host import HostCase
from hass.tests.test_photo_draft import JPG

ROUTER, OLLAMA = "http://127.0.0.1:8010", "http://127.0.0.1:11434"
GPU, CPU = "qwen3.8:27b-thinkingcap-q6", "qwen3.6:35b-a3b-64k"
PROMPT = "SYSTEM-PROMPT-MARKER: reply with JSON."
OWNER_TEXT = "Change the hours, señora — OWNER-TEXT-MARKER"
GOOD = _ops((HOURS, {"hours": NEW_HOURS}))
CLOCK = lambda: datetime(2026, 11, 7, 17, 0, tzinfo=timezone.utc)  # noqa: E731
THINK = "We need to decide. The owner wants hours; OWNER-TEXT-MARKER SECRET-THOUGHT."


def oa(content, finish="stop", **message):
    """An OpenAI-style /v1/chat/completions reply around the model's text."""
    return 200, json.dumps({"id": "x", "object": "chat.completion", "choices": [
        {"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": content, **message}}]}).encode()


def ol(content):
    """An Ollama /api/chat reply."""
    return 200, json.dumps({"done": True, "message": {"role": "assistant", "content": content}}).encode()


def js(value): return json.dumps(value)  # noqa: E704


class Fake:
    """A transport that records each call and returns (or raises) the configured result."""

    def __init__(self, result): self.result, self.calls = result, []  # noqa: E704

    def __call__(self, url, body, headers, timeout):
        self.calls.append((url, json.loads(body), timeout))
        if isinstance(self.result, BaseException): raise self.result
        return self.result


def gpu(result, **kw): return LocalInterpreter(ROUTER, GPU, PROMPT, transport=(f := Fake(result)), clock=CLOCK, api="openai", **kw), f  # noqa: E704
def cpu(result, **kw): return LocalInterpreter(OLLAMA, CPU, PROMPT, transport=(f := Fake(result)), clock=CLOCK, **kw), f  # noqa: E704
def valid(r): return conversation._checked(r) is r  # noqa: E704


def pair(first, second):
    (a, fa), (b, fb) = gpu(first), cpu(second)
    return FallbackInterpreter(a, b, valid), fa, fb


class OpenAIBackendTests(unittest.TestCase):
    def test_backend_selection_and_urls(self):
        self.assertEqual(gpu(oa(js(GOOD)))[0].url, f"{ROUTER}/v1/chat/completions")
        self.assertEqual(cpu(ol(js(GOOD)))[0].url, f"{OLLAMA}/api/chat")
        default = LocalInterpreter(OLLAMA, CPU, PROMPT)
        self.assertEqual((default.api, default.url), ("ollama", f"{OLLAMA}/api/chat"))  # ollama stays the default
        for bad in ("OpenAI", "", None, "openai ", 1):
            with self.subTest(api=bad), self.assertRaises(ValueError):
                LocalInterpreter(ROUTER, GPU, PROMPT, api=bad)

    def test_openai_request_is_non_thinking_json_only_and_carries_the_same_user_fields(self):
        interp, fake = gpu(oa(js(GOOD)), timeout=45)
        self.assertEqual(interp.interpret(OWNER_TEXT, [], aliases=["a"]), GOOD)
        self.assertIsNone(interp.last_error)
        [(url, sent, timeout)] = fake.calls
        self.assertEqual((url, timeout), (f"{ROUTER}/v1/chat/completions", 45))
        self.assertEqual(sent["model"], GPU)
        self.assertEqual((sent["temperature"], sent["stream"], sent["chat_template_kwargs"], sent["response_format"]),
                         (0, False, {"enable_thinking": False}, {"type": "json_object"}))
        self.assertEqual(sent["max_tokens"], interpreter_local.MAX_TOKENS)
        for ollama_only in ("format", "options", "think"):
            self.assertNotIn(ollama_only, sent)
        system, user = sent["messages"]
        self.assertEqual(system, {"role": "system", "content": PROMPT})
        self.assertEqual(json.loads(user["content"]), {"message": OWNER_TEXT, "pending": [], "today": "2026-11-07",
                                                         "weekday": "Saturday", "aliases": ["a"]})

    def test_think_setting_cannot_turn_thinking_on_for_the_openai_backend(self):
        for think in (None, False, True):
            with self.subTest(think=think):
                interp, fake = gpu(oa(js(GOOD)), think=think)
                interp.interpret("x", [])
                sent = fake.calls[0][1]
                self.assertEqual((sent["chat_template_kwargs"], "think" in sent), ({"enable_thinking": False}, False))

    def test_the_ollama_request_is_unchanged(self):
        interp, fake = cpu(ol(js(GOOD)), think=False)
        interp.interpret("x", [])
        sent = fake.calls[0][1]
        self.assertEqual({k: sent[k] for k in ("model", "stream", "format", "options", "think")},
                         {"model": CPU, "stream": False, "format": "json", "options": {"temperature": 0}, "think": False})
        for openai_only in ("response_format", "chat_template_kwargs", "max_tokens", "temperature"):
            self.assertNotIn(openai_only, sent)

    def test_thinking_text_is_stripped_and_never_reaches_the_answer(self):
        answer = js(GOOD)
        for content in (answer, f"<think>{THINK}</think>\n\n{answer}", f"{THINK}</think>\n{answer}",
                        f"<think>\n{THINK}\n</think>{answer}  \n", f"<think>a</think><think>b</think>{answer}"):
            with self.subTest(content=content[:30]):
                interp, _ = gpu(oa(content))
                out = interp.interpret(OWNER_TEXT, [])
                self.assertEqual((out, interp.last_error), (GOOD, None))
                self.assertNotIn("SECRET-THOUGHT", json.dumps(out))
        self.assertEqual(strip_reasoning(f"<think>x</think> {answer}\n"), answer)

    def test_a_reasoning_block_after_an_answer_is_a_failed_call_not_the_second_answer(self):
        for content in ('{"question":"first?"}<think>reason</think>{"question":"second?"}',
                        '{"question":"first?"}</think>{"question":"second?"}'[:0] + 'x<think>r</think>{"question":"s?"}'):
            with self.subTest(content=content[:30]):
                with self.assertRaises(interpreter_local._Failed): strip_reasoning(content)
        interp, fake = gpu(oa('{"question":"first?"}<think>reason</think>{"question":"second?"}'))
        interp.interpret(OWNER_TEXT, [])
        self.assertEqual(interp.last_error, "shape")

    def test_the_separate_reasoning_field_is_ignored_even_when_it_looks_like_json(self):
        interp, _ = gpu(oa(js({"question": "Which day?"}), reasoning_content=js(GOOD)))
        self.assertEqual(interp.interpret("x", []), {"question": "Which day?"})
        interp, _ = gpu(oa("", reasoning_content=js(GOOD)))  # an empty answer is not rescued from the reasoning
        self.assertEqual((interp.interpret("x", []), interp.last_error), ({"unsupported": FAILED}, "shape"))
        interp, _ = gpu(oa(None, reasoning_content=js(GOOD)))
        self.assertEqual(interp.interpret("x", [])["unsupported"], FAILED)

    def test_replies_outside_the_contract_are_rejected(self):
        answer = js(GOOD)
        bad_envelopes = [
            (200, b"not json"), (200, b"[1]"), (200, js({}).encode()), (200, js({"choices": []}).encode()),
            (200, js({"choices": "x"}).encode()), (200, js({"choices": [{}]}).encode()),
            (200, js({"choices": [{"finish_reason": "stop", "message": "x"}]}).encode()),
            (200, js({"choices": [{"finish_reason": "stop", "message": {}}]}).encode()),
            (200, js({"choices": [{"finish_reason": "stop", "message": {"content": 5}}]}).encode()),
            (200, js({"choices": [{"finish_reason": "stop", "message": {"content": answer}},
                                  {"finish_reason": "stop", "message": {"content": answer}}]}).encode()),
            (200, js({"done": True, "message": {"content": answer}}).encode()),  # an Ollama reply from the wrong endpoint
            oa(answer, finish="length"), oa(answer, finish=None), oa(answer, finish="tool_calls"),
        ]
        bad_contents = [
            "", "   ", "Sure! Here is the JSON: " + answer, "```json\n" + answer + "\n```", "[1, 2]", "42", "null", '"text"',
            answer + " trailing words", answer + answer, '{"a": 1, "a": 2}', '{"x": NaN}', '{"x": Infinity}',
            f"<think>{THINK}", f"{answer}<think>{THINK}</think>", f"{answer}</think>", f"<think>{THINK}</think>{THINK}",
            f"<think>{THINK}</think>Thinking... {answer}", "{" + answer,
        ]
        for result in bad_envelopes + [oa(c) for c in bad_contents]:
            with self.subTest(result=repr(result)[:80]):
                interp, _ = gpu(result)
                out = interp.interpret(OWNER_TEXT, [])
                self.assertEqual(out, {"unsupported": FAILED})
                self.assertIn(interp.last_error, ("shape", "not-json"))
                for secret in ("SECRET-THOUGHT", "OWNER-TEXT-MARKER", PROMPT, ROUTER):
                    self.assertNotIn(secret, json.dumps(out) + interp.last_error)

    def test_transport_failures_have_the_same_short_codes(self):
        for result, code in ((TimeoutError("t"), "timeout"), (urllib.error.URLError(TimeoutError("t")), "timeout"),
                             (ConnectionRefusedError(111, "x"), "connect"), ((500, b""), "http-500"), ((503, b""), "http-503"),
                             ((302, b""), "http-302"), ((200, b" " * (300 * 1024)), "too-large")):
            with self.subTest(code=code):
                interp, _ = gpu(result)
                self.assertEqual((interp.interpret("x", []), interp.last_error, interp.last_backend),
                                 ({"unsupported": FAILED}, code, "openai"))

    def test_the_timeout_is_passed_to_the_transport_and_bounded(self):
        for seconds in (1, 60, 120):
            interp, fake = gpu(oa(js(GOOD)), timeout=seconds)
            interp.interpret("x", [])
            self.assertEqual(fake.calls[0][2], seconds)
        for bad in (0, 121, 5.0, True, "60"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                gpu(oa(js(GOOD)), timeout=bad)

    def test_default_transport_for_openai_goes_to_the_router_without_proxy_or_redirect(self):
        seen = []

        class Opener:
            def open(self, request, timeout=None):
                seen.append((request.get_method(), request.full_url, timeout))
                raise urllib.error.URLError(TimeoutError("timed out"))
        with mock.patch.object(interpreter_local, "_opener", return_value=Opener()):
            interp = LocalInterpreter(ROUTER, GPU, PROMPT, api="openai", timeout=7, clock=CLOCK)
            self.assertEqual(interp.interpret("x", []), {"unsupported": FAILED})
        self.assertEqual((seen, interp.last_error), ([("POST", f"{ROUTER}/v1/chat/completions", 7)], "timeout"))

    def test_only_loopback_http_urls_are_accepted_for_both_backends(self):
        for url in ("http://8.8.8.8:8010", "https://127.0.0.1:8010", "http://example.com", "http://127.0.0.1.evil.com",
                    "http://user@127.0.0.1:8010", "http://127.0.0.1:8010/v1", "http://127.0.0.1:8010?x=1", "http://0.0.0.0:8010",
                    "http://127.0.0.1:0", "", None):
            for api in ("openai", "ollama"):
                with self.subTest(url=url, api=api), self.assertRaises(ValueError):
                    LocalInterpreter(url, GPU, PROMPT, api=api)

    def test_a_full_fallback_round_opens_no_socket(self):
        opened = []
        with mock.patch.object(socket.socket, "connect", lambda s, addr: opened.append(addr)), \
                mock.patch.object(socket, "create_connection", lambda *a, **k: opened.append(a)), \
                mock.patch.object(urllib.request, "urlopen", lambda *a, **k: opened.append(a)):
            both, _, _ = pair((500, b""), ol(js(GOOD)))
            self.assertEqual(both.interpret("x", []), GOOD)
        self.assertEqual(opened, [])


class FallbackTests(unittest.TestCase):
    def test_a_good_first_answer_never_calls_the_second(self):
        both, first, second = pair(oa(js(GOOD)), ol(js(GOOD)))
        self.assertEqual(both.interpret("x", []), GOOD)
        self.assertEqual((len(first.calls), len(second.calls)), (1, 0))
        self.assertEqual((both.last_backend, both.last_fallback, both.last_primary_error, both.last_error),
                         ("openai", False, None, None))
        self.assertIsInstance(both.last_seconds, float)

    def test_an_honest_unsupported_or_question_is_an_answer_not_a_failure(self):
        for answer in ({"unsupported": "I can't do that."}, {"question": "Which day?"}):
            with self.subTest(answer=answer):
                both, first, second = pair(oa(js(answer)), ol(js(GOOD)))
                self.assertEqual(both.interpret("x", []), answer)
                self.assertEqual((len(second.calls), both.last_fallback), (0, False))

    def test_each_first_failure_retries_once_on_the_cpu_model_and_names_it(self):
        cases = [(TimeoutError("t"), "timeout"), (urllib.error.URLError(TimeoutError("t")), "timeout"),
                 (ConnectionRefusedError(111, "x"), "connect"), ((500, b""), "http-500"), ((200, b"not json"), "not-json"),
                 (oa("Here you go: " + js(GOOD)), "shape"), (oa("```json\n" + js(GOOD) + "\n```"), "shape"),
                 (oa(js(GOOD), finish="length"), "shape"), (oa(f"<think>{THINK}"), "shape")]
        for first_result, code in cases:
            with self.subTest(code=code, result=repr(first_result)[:50]):
                both, first, second = pair(first_result, ol(js(GOOD)))
                out = both.interpret(OWNER_TEXT, [])
                self.assertEqual(out, GOOD)
                self.assertEqual((len(first.calls), len(second.calls)), (1, 1))
                self.assertEqual((both.last_backend, both.last_fallback, both.last_primary_error, both.last_error),
                                 ("ollama", True, code, None))
                self.assertEqual(second.calls[0][0], f"{OLLAMA}/api/chat")
                self.assertEqual(second.calls[0][1]["model"], CPU)

    def test_a_valid_json_object_outside_the_reply_contract_also_falls_back(self):
        for wrong in ({"ops": []}, {"ops": "x", "revises": None}, {"ops": [], "revises": 3}, {"question": ""}, {"unsupported": 5},
                      {"question": "a", "ops": []}, {"answer": "4"}, {}):
            with self.subTest(wrong=wrong):
                both, first, second = pair(oa(js(wrong)), ol(js(GOOD)))
                self.assertEqual(both.interpret("x", []), GOOD)
                self.assertEqual((len(first.calls), len(second.calls), both.last_primary_error, both.last_backend),
                                 (1, 1, "contract", "ollama"))

    def test_the_retry_is_the_last_attempt_even_when_it_fails_too(self):
        for second_result, code in (((500, b""), "http-500"), (TimeoutError("t"), "timeout"), (ol("not json"), "shape")):
            with self.subTest(code=code):
                both, first, second = pair((500, b""), second_result)
                self.assertEqual(both.interpret("x", []), {"unsupported": FAILED})
                self.assertEqual((len(first.calls), len(second.calls)), (1, 1))  # one retry: no loop, no third call
                self.assertEqual((both.last_error, both.last_backend, both.last_fallback, both.last_primary_error),
                                 (code, "ollama", True, "http-500"))
        # the second answer is final even when it is valid JSON outside the contract: the host's own check turns it into
        # the unreadable reply, and nothing asks a third time
        both, first, second = pair((500, b""), ol(js({"ops": []})))
        self.assertEqual(both.interpret("x", []), {"ops": []})
        self.assertEqual((len(first.calls), len(second.calls), both.last_error), (1, 1, None))
        self.assertEqual(conversation._checked({"ops": []}), conversation.UNREADABLE)

    def test_the_second_call_gets_the_same_owner_fields(self):
        both, first, second = pair(TimeoutError("t"), ol(js(GOOD)))
        both.interpret(OWNER_TEXT, [{"code": "beef", "state": "proposed", "summary": "s"}], notes=["n"], aliases=["a"],
                       sent_at=datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc), recent={"question": "Which?"})
        a = json.loads(first.calls[0][1]["messages"][1]["content"])
        b = json.loads(second.calls[0][1]["messages"][1]["content"])
        self.assertEqual(a, b)
        self.assertEqual((a["today"], a["notes"], a["recent"]), ("2026-11-09", ["n"], {"question": "Which?"}))

    def test_a_first_interpreter_that_raises_or_a_checker_that_raises_is_handled(self):
        class Raises:
            last_error = last_backend = None

            def interpret(self, *a, **k): raise RuntimeError("OWNER-TEXT-MARKER boom")  # noqa: E704
        second, fake = cpu(ol(js(GOOD)))
        both = FallbackInterpreter(Raises(), second, valid)
        self.assertEqual(both.interpret("x", []), GOOD)
        self.assertEqual((both.last_primary_error, both.last_backend, len(fake.calls)), ("error", "ollama", 1))
        first, _ = gpu(oa(js(GOOD)))
        second, fake = cpu(ol(js(GOOD)))

        def broken(_): raise ValueError("x")  # noqa: E704
        both = FallbackInterpreter(first, second, broken)
        self.assertEqual((both.interpret("x", []), both.last_primary_error, len(fake.calls)), (GOOD, "contract", 1))

    def test_constructor_refusals(self):
        first, _ = gpu(oa(js(GOOD)))
        second, _ = cpu(ol(js(GOOD)))
        for args in ((first, second, None), (first, second, "x"), (None, second, valid), (first, object(), valid)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                FallbackInterpreter(*args)


class ConversationAuditTests(ConversationTestCase):
    def use(self, first, second):
        self.interp, self.first, self.second = pair(first, second)
        self.conv = self.open()

    def audit(self):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'interpreter_audit'").fetchone(): return None
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM interpreter_audit ORDER BY at, provider_id")]

    def test_the_backend_that_answered_is_recorded_per_message(self):
        self.use(oa(js(GOOD)), ol(js(GOOD)))
        self.assertEqual(self.say("please change the hours", pid="p1"), "proposed")
        [row] = self.audit()
        self.assertEqual((row["provider_id"], row["backend"], row["fallback"], row["primary_error"], row["error"]),
                         ("p1", "openai", 0, None, None))
        self.assertIsInstance(row["seconds"], float)
        self.first.result = (500, b"")
        self.assertEqual(self.say("change them again", pid="p2"), "proposed")
        row = self.audit()[-1]
        self.assertEqual((row["provider_id"], row["backend"], row["fallback"], row["primary_error"], row["error"]),
                         ("p2", "ollama", 1, "http-500", None))
        self.assertEqual(len(self.first.calls), 2)
        self.assertEqual(len(self.second.calls), 1)

    def test_both_backends_failing_replies_the_fixed_line_and_records_the_final_error(self):
        self.use((500, b""), TimeoutError("t"))
        self.assertEqual(self.say("please change the hours", pid="p1"), "reader-failed")
        self.assertEqual(self.replies(), [FAILED])
        self.assertEqual(self.drafts(), [])
        [row] = self.audit()
        self.assertEqual((row["backend"], row["fallback"], row["primary_error"], row["error"]), ("ollama", 1, "http-500", "timeout"))

    def test_audit_rows_never_hold_owner_text_prompts_urls_or_replies(self):
        self.use(oa(f"<think>{THINK}</think>{js(GOOD)}"), ol(js(GOOD)))
        self.say(OWNER_TEXT, pid="p1")
        self.first.result = oa("nonsense " + THINK)
        self.say(OWNER_TEXT + " again", pid="p2")
        dump = json.dumps(self.audit(), ensure_ascii=False)
        for secret in ("OWNER-TEXT-MARKER", "señora", "SECRET-THOUGHT", PROMPT, "127.0.0.1", "qwen", "/v1/"):
            self.assertNotIn(secret, dump)

    def test_an_interpreter_that_names_no_backend_creates_no_audit_table(self):
        self.conv = self.open()  # the fixture interpreter of the base case
        self.propose("hours")
        self.assertIsNone(self.audit())

    def test_a_fallback_message_counts_once_against_the_daily_cap(self):
        self.set_settings({**SETTINGS, "interpreterDailyCap": 2})
        self.use((500, b""), ol(js(GOOD)))
        self.assertEqual(self.say("one", pid="p1"), "proposed")
        self.assertEqual(self.conv._calls(self.now)[1], 1)  # the retry on the CPU model is not a second counted call
        self.assertEqual(self.say("two", pid="p2"), "proposed")
        self.assertEqual(self.say("three", pid="p3"), "daily-limit")
        self.assertEqual((len(self.first.calls), len(self.second.calls)), (2, 2))  # no model call for the refused third


class LabelReaderOpenAITests(unittest.TestCase):
    LION = {"name": "Lion's Mane", "brand": "Far West Fungi", "category": "mushrooms"}
    CATS = ["fruit", "mushrooms", "vegetables"]

    def reader(self, result, **kw):
        fake = Fake(result)
        return LabelReader(ROUTER, GPU, transport=fake, api="openai", **kw), fake

    def test_the_photo_goes_as_a_data_uri_with_the_same_prompt_and_a_non_thinking_request(self):
        labels, fake = self.reader(oa(js(self.LION)))
        self.assertEqual(labels.read(JPG, self.CATS), self.LION)
        [(url, sent, _)] = fake.calls
        self.assertEqual(url, f"{ROUTER}/v1/chat/completions")
        self.assertEqual((sent["chat_template_kwargs"], sent["response_format"], sent["temperature"]),
                         ({"enable_thinking": False}, {"type": "json_object"}, 0))
        [message] = sent["messages"]
        text, image = message["content"]
        self.assertEqual(text, {"type": "text", "text": label_reader.PROMPT})
        self.assertTrue(image["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("images", message)
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 8
        labels.read(png, self.CATS)
        self.assertTrue(fake.calls[1][1]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_thinking_is_stripped_and_unparseable_output_is_a_failed_read(self):
        labels, _ = self.reader(oa(f"<think>{THINK}</think>{js(self.LION)}"))
        self.assertEqual(labels.read(JPG, self.CATS), self.LION)
        for content in ("The label says Lion's Mane", "```json\n" + js(self.LION) + "\n```", f"<think>{THINK}"):
            labels, _ = self.reader(oa(content))
            self.assertEqual((labels.read(JPG, self.CATS), labels.last_error), ({}, "shape"))

    def test_claims_are_still_dropped_on_the_openai_backend(self):
        labels, _ = self.reader(oa(js({**self.LION, "origin": "Moss Landing", "organic": True, "name": "Organic Lion's Mane"})))
        self.assertEqual(labels.read(JPG, self.CATS), {"brand": "Far West Fungi", "category": "mushrooms"})

    def test_a_failed_read_retries_once_on_the_ollama_reader(self):
        second_fake = Fake(ol(js(self.LION)))
        second = LabelReader(OLLAMA, "vision-cpu", transport=second_fake)
        labels, fake = self.reader((500, b""), fallback=second)
        self.assertEqual(labels.read(JPG, self.CATS), self.LION)
        self.assertEqual((len(fake.calls), len(second_fake.calls)), (1, 1))
        self.assertEqual((labels.last_backend, labels.last_fallback, labels.last_primary_error, labels.last_error),
                         ("ollama", True, "http-500", None))
        self.assertIn("images", second_fake.calls[0][1]["messages"][0])  # the Ollama request shape
        failing = LabelReader(OLLAMA, "vision-cpu", transport=Fake(TimeoutError("t")))
        labels, fake = self.reader((500, b""), fallback=failing)
        self.assertEqual((labels.read(JPG, self.CATS), labels.last_error, len(fake.calls)), ({}, "timeout", 1))
        with self.assertRaises(ValueError):
            self.reader(oa(js(self.LION)), fallback="x")

    def test_a_fallback_chain_is_refused_and_only_one_retry_is_ever_made(self):
        inner_fake = Fake(ol(js(self.LION)))
        inner = LabelReader(OLLAMA, "vision-cpu", transport=inner_fake)
        with self.assertRaises(ValueError):
            LabelReader(OLLAMA, "vision-cpu", fallback=LabelReader(OLLAMA, "vision-cpu", fallback=inner))
        middle = LabelReader(OLLAMA, "vision-cpu", transport=Fake((500, b"")))
        labels, fake = self.reader((500, b""), fallback=middle)
        middle.fallback = inner  # a chain forced in by hand still costs one retry only
        self.assertEqual((labels.read(JPG, self.CATS), labels.last_error, len(fake.calls), len(inner_fake.calls)),
                         ({}, "http-500", 1, 0))
        middle.fallback = middle  # a cycle ends after the one retry too
        self.assertEqual((labels.read(JPG, self.CATS), labels.last_error), ({}, "http-500"))

    def test_without_a_fallback_a_failure_stays_a_plain_failed_read(self):
        labels, _ = self.reader((500, b""))
        self.assertEqual((labels.read(JPG, self.CATS), labels.last_error, labels.last_fallback), ({}, "http-500", False))


class HostConfigTests(HostCase):
    OPENAI = {"url": ROUTER, "model": GPU, "api": "openai", "timeout": 60,
              "fallback": {"url": OLLAMA, "model": CPU, "timeout": 120, "think": False}}

    def test_api_and_fallback_keys_are_accepted_as_documented(self):
        loaded = host.load_host(self.host_json(interpreter=self.OPENAI))["interpreter"]
        self.assertEqual(loaded, self.OPENAI)
        host.load_host(self.host_json(interpreter={"url": ROUTER, "model": GPU, "api": "openai"}))  # no fallback block
        host.load_host(self.host_json(interpreter={"url": OLLAMA, "model": CPU, "api": "ollama", "think": False}))
        host.load_host(self.host_json(interpreter={"url": OLLAMA, "model": CPU}))  # the existing form still loads

    def test_bad_interpreter_blocks_are_refused(self):
        base = {"url": ROUTER, "model": GPU, "api": "openai"}
        fb = self.OPENAI["fallback"]
        bad = [{**base, "api": "gemini"}, {**base, "api": None}, {**base, "api": True}, {**base, "think": False},
               {**base, "fallback": {"url": "http://8.8.8.8:11434", "model": CPU}},
               {**base, "fallback": {"url": "https://127.0.0.1:11434", "model": CPU}},
               {**base, "fallback": {"url": OLLAMA}}, {**base, "fallback": {**fb, "timeout": 0}},
               {**base, "fallback": {**fb, "timeout": 121}}, {**base, "fallback": {**fb, "think": "no"}},
               {**base, "fallback": {**fb, "api": "openai"}}, {**base, "fallback": {**fb, "fallback": fb}},
               {**base, "fallback": [fb]}, {**base, "fallback": None}, {**base, "extra": 1},
               {"url": OLLAMA, "model": CPU, "fallback": fb},  # a fallback only makes sense behind the openai backend
               {"url": OLLAMA, "model": CPU, "api": "ollama", "fallback": fb},
               {**base, "url": "http://8.8.8.8:8010"}, {**base, "url": "http://127.0.0.1:8010/v1"}]
        for block in bad:
            with self.subTest(block=block), self.assertRaises(host.HostConfigError) as ctx:
                host.load_host(self.host_json(interpreter=block))
            self.assertEqual(ctx.exception.fields, ["interpreter"])

    def build(self, block):
        cfg = {"interpreter": block}
        with mock.patch.object(host, "load_registry"), mock.patch.object(host, "load_content"), \
                mock.patch.object(host.interpreter_prompt, "build", return_value="p"), \
                mock.patch.object(host.nl_prep, "make_hinter", return_value=lambda *a: {}):
            return host.interpreter_builder(cfg, "/nonexistent")()

    def test_builder_selects_the_backend_from_the_config(self):
        plain = self.build({"url": OLLAMA, "model": CPU})
        self.assertEqual((type(plain), plain.api, plain.url), (LocalInterpreter, "ollama", f"{OLLAMA}/api/chat"))
        single = self.build({"url": ROUTER, "model": GPU, "api": "openai", "timeout": 60})
        self.assertEqual((type(single), single.api, single.url, single.timeout), (LocalInterpreter, "openai", f"{ROUTER}/v1/chat/completions", 60))
        both = self.build(self.OPENAI)
        self.assertIsInstance(both, FallbackInterpreter)
        self.assertEqual((both.primary.api, both.primary.model, both.primary.timeout), ("openai", GPU, 60))
        self.assertEqual((both.fallback.api, both.fallback.model, both.fallback.timeout, both.fallback.think),
                         ("ollama", CPU, 120, False))
        self.assertIs(both.primary.hinter, both.fallback.hinter)
        self.assertEqual(both.primary.system_prompt, both.fallback.system_prompt)
        self.assertTrue(both.valid({"question": "ok?"}) and not both.valid({"ops": []}))


if __name__ == "__main__":
    unittest.main()
