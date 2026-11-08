"""NB-AV-02 (H05): local-model interpreter adapter for the Ollama JSON chat API, behind an injectable transport.

LocalInterpreter(base_url, model, system_prompt).interpret(text, pending) sends one `POST /api/chat` to a loopback
http URL and returns the decoded JSON object the model wrote, or {"unsupported": FAILED} on any failure. The failure
reason is kept only as a short code in `last_error` (never the URL, prompt or owner text; `request` means the text or
pending list could not be encoded); nothing is logged.
RF1240-20: repeated keys and NaN/Infinity in a reply are a failed call (`not-json` in the envelope, `shape` in content).
Not wired into any service: the operator names the existing local model; nothing is pulled or changed here.

HASS-INTERP-OPENAI-1: `api="openai"` speaks OpenAI-style `POST /v1/chat/completions` (the fleet's model router, loopback
only, same checks and limits) instead of Ollama `/api/chat`. It asks for a non-thinking JSON-object reply, never reads a
`reasoning_content` field, removes a `<think>` block if one is in the text, and accepts only a JSON object after that.
FallbackInterpreter(primary, fallback, valid) asks the second interpreter once, never more, when the first one failed or
answered outside the reply contract, and records in `last_backend` / `last_fallback` / `last_primary_error` which one answered.
"""
import json, time, urllib.error, urllib.parse, urllib.request  # noqa: E401
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

LOOPBACK = ("127.0.0.1", "localhost", "::1")
CHAT_PATH, MAX_BODY, MAX_MODEL = "/api/chat", 256 * 1024, 100
MAX_EARLIER = 4  # HASS-HIKE-FLOW-1: owner texts of the open request that go out with an answer (Conversation keeps the same)
APIS, OPENAI_PATH, MAX_TOKENS = ("ollama", "openai"), "/v1/chat/completions", 2000  # HASS-INTERP-OPENAI-1
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
FAILED = "I could not work that out right now, so nothing was drafted. Please try again in a few minutes."
URL_ERROR = "interpreter URL must be loopback http"


def check_url(base_url) -> str:
    """`http://<loopback>[:port]` (port 1-65535), no userinfo, query, fragment or path beyond `/`; else ValueError."""
    try:
        if not isinstance(base_url, str) or "?" in base_url or "#" in base_url or "@" in base_url: raise ValueError
        parts = urllib.parse.urlsplit(base_url)
        port = parts.port  # raises ValueError for a malformed port; 0 is not connectable
        ok = parts.scheme == "http" and parts.hostname in LOOPBACK and parts.path in ("", "/") and port != 0
    except ValueError:
        ok = False
    if not ok: raise ValueError(URL_ERROR)
    return f"http://{parts.netloc}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # a 3xx is a failed call, never followed to another host


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)  # no env proxy, no redirect


def urllib_transport(url, body, headers, timeout):
    """(status, body bytes) for one POST, reading at most MAX_BODY + 1 bytes."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _opener().open(request, timeout=timeout) as response:
            return response.status, response.read(MAX_BODY + 1)
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code, b""


class _Failed(Exception):
    pass


def _pairs(pairs):  # a key repeated in one object is refused, never read as its last value
    if len({key for key, _ in pairs}) != len(pairs): raise ValueError("repeated key")
    return dict(pairs)


def _constant(name): raise ValueError("non-finite constant")  # noqa: E704 - NaN, Infinity, -Infinity


def _strict(text): return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)  # noqa: E704


def strip_reasoning(text) -> str:
    """HASS-INTERP-OPENAI-1: the answer without a reasoning block. Text up to the last `</think>` (with or without an
    opening tag) is reasoning and is dropped; a tag left anywhere else (an unclosed block, a block after the answer) is a
    failed call, never trimmed further."""
    if "</think>" in text:
        *blocks, text = text.split("</think>")
        for i, block in enumerate(blocks):  # each block is only reasoning: no answer text before or between blocks
            block = block.strip()
            if block.count("<think>") > 1 or ("<think>" in block and not block.startswith("<think>")): raise _Failed("shape")
            if i and "<think>" not in block: raise _Failed("shape")  # text between two closed blocks is an answer
    if "<think>" in text or "</think>" in text: raise _Failed("shape")
    return text.strip()


def image_type(image: bytes) -> str:
    if image[:8] == b"\x89PNG\r\n\x1a\n": return "image/png"
    return "image/webp" if image[:4] == b"RIFF" and image[8:12] == b"WEBP" else "image/jpeg"


class LocalInterpreter:
    """The Conversation interpreter contract: interpret(text, pending) -> dict. Transport is
    (url, body_bytes, headers, timeout) -> (status, body_bytes); the default never uses a proxy or follows a redirect."""

    def __init__(self, base_url, model, system_prompt, timeout=30, transport=None, clock=None, think=None,
                 hinter=None, api="ollama"):
        if api not in APIS: raise ValueError("api must be ollama or openai")  # HASS-INTERP-OPENAI-1
        self.url = check_url(base_url) + (OPENAI_PATH if api == "openai" else CHAT_PATH)
        if not (isinstance(model, str) and 0 < len(model) <= MAX_MODEL and not any(c.isspace() for c in model)):
            raise ValueError(f"model must be a name of 1-{MAX_MODEL} characters without spaces")
        if not (isinstance(system_prompt, str) and system_prompt.strip()):
            raise ValueError("system prompt must be non-empty text")
        if type(timeout) is not int or not 1 <= timeout <= 120:
            raise ValueError("timeout must be a whole number of seconds from 1 to 120")
        if think is not None and type(think) is not bool: raise ValueError("think must be true, false or unset")
        if clock is not None and not callable(clock): raise ValueError("clock must be callable")
        if hinter is not None and not callable(hinter): raise ValueError("hinter must be callable")  # HASS-NL-1
        self.model, self.system_prompt, self.timeout, self.think, self.api = model, system_prompt, timeout, think, api
        self.transport = transport or urllib_transport
        self.clock = clock if clock is not None else (lambda: datetime.now(timezone.utc))
        self.hinter = hinter  # HASS-NL-1: hinter(text, date, aliases) -> dict of facts worked out from the owner's words
        self.last_error = None
        self.last_backend, self.last_fallback, self.last_primary_error, self.last_seconds = None, False, None, None

    def _today(self, sent_at=None):
        """(YYYY-MM-DD, weekday) in Pacific time; a raising, naive or non-datetime clock (or an explicit sent_at that is
        naive or not a datetime, AV1352-06) is _Failed("clock"). A supplied sent_at replaces the clock read."""
        try:
            now = self.clock() if sent_at is None else sent_at
            if not isinstance(now, datetime) or now.utcoffset() is None: raise ValueError
            local = now.astimezone(PACIFIC)
        except Exception:  # noqa: BLE001 - the clock's own error text is never kept
            raise _Failed("clock") from None
        return local.date().isoformat(), WEEKDAYS[local.weekday()]

    def _hints(self, text, today, aliases) -> dict:
        """HASS-NL-1: the hinter's facts, or {} (a hint is a convenience: no hinter, a raising one or a non-dict is no hint)."""
        if self.hinter is None: return {}
        try:
            hints = self.hinter(text, date.fromisoformat(today), aliases)
            return hints if isinstance(hints, dict) else {}
        except Exception:  # noqa: BLE001 - the request goes out without hints
            return {}

    def _request(self, text, pending, notes=None, aliases=None, sent_at=None, recent=None) -> bytes:
        today, weekday = self._today(sent_at)
        try:  # a lone surrogate or a non-JSON value is a failed call, never a crash
            fields = {"message": text, "pending": pending, "today": today, "weekday": weekday}
            if isinstance(notes, list) and notes: fields["notes"] = notes  # AV1102-09: owner preferences, never claims
            if isinstance(aliases, list) and aliases: fields["aliases"] = aliases  # AV0007-06: identifiers, never claims
            earlier = recent.get("earlier") if isinstance(recent, dict) else None
            earlier = earlier if isinstance(earlier, list) and 0 < len(earlier) <= MAX_EARLIER and all(isinstance(t, str) and t for t in earlier) else None
            hints = self._hints(" ".join([*(earlier or ()), text]), today, aliases)  # HASS-HIKE-FLOW-1: the whole open request, not only the answer
            if hints: fields["hints"] = hints  # HASS-NL-1: facts, never claims
            if isinstance(recent, dict) and isinstance(recent.get("question"), str) and recent["question"]:
                fields["recent"] = {"question": recent["question"], **({"earlier": earlier} if earlier else {})}  # HASS-NL-1: Hass's last question, which this text answers; HASS-HIKE-FLOW-1: + the owner's texts of that request, oldest first
            user = json.dumps(fields, ensure_ascii=False)
            messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user}]
            if self.api == "openai": return self._openai_body(messages)
            body = {"model": self.model, "messages": messages, "stream": False, "format": "json", "options": {"temperature": 0}}
            if self.think is False: body["think"] = False  # HASS-INTERP-TIMEOUT-1: sent only when the operator set it false
            return json.dumps(body, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise _Failed("request") from None

    def _openai_body(self, messages) -> bytes:
        """HASS-INTERP-OPENAI-1: always a non-thinking, temperature-0, JSON-object request (the `think` setting is Ollama's)."""
        body = {"model": self.model, "messages": messages, "stream": False, "temperature": 0, "max_tokens": MAX_TOKENS,
                "response_format": {"type": "json_object"}, "chat_template_kwargs": {"enable_thinking": False}}
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    def _call(self, body) -> dict:
        try:
            status, raw = self.transport(self.url, body, dict(HEADERS), self.timeout)
        except urllib.error.URLError as exc:
            raise _Failed("timeout" if isinstance(exc.reason, TimeoutError) else "connect") from None
        except TimeoutError:
            raise _Failed("timeout") from None
        except Exception:  # noqa: BLE001 - refused, reset, protocol error: all are "could not reach the model"
            raise _Failed("connect") from None
        if status != 200: raise _Failed(f"http-{status}" if type(status) is int else "shape")
        if not isinstance(raw, (bytes, bytearray)): raise _Failed("shape")
        if len(raw) > MAX_BODY: raise _Failed("too-large")
        try:
            reply = _strict(raw)
        except (ValueError, RecursionError):
            raise _Failed("not-json") from None
        if self.api == "openai":
            content = self._openai_content(reply)
        else:
            if not isinstance(reply, dict) or reply.get("done") is not True: raise _Failed("shape")
            message = reply.get("message")
            content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str): raise _Failed("shape")
        try:
            result = _strict(content)
        except (ValueError, RecursionError):
            raise _Failed("shape") from None
        if not isinstance(result, dict): raise _Failed("shape")
        return result

    @staticmethod
    def _openai_content(reply):
        """The one finished choice's answer text with any reasoning block removed; `reasoning_content` is never read."""
        choices = reply.get("choices") if isinstance(reply, dict) else None
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        if not isinstance(choice, dict) or choice.get("finish_reason") != "stop": raise _Failed("shape")  # "length" is cut off
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str): raise _Failed("shape")
        return strip_reasoning(content)

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None) -> dict:
        """AV1352-06: sent_at (aware, from Conversation) is the day 'today' means; None reads the clock. The model's decoded JSON object as-is (Conversation's checks decide if it is usable), else the fixed
        unsupported reply with the reason code in last_error."""
        self.last_error, self.last_backend, self.last_fallback, self.last_primary_error = None, self.api, False, None
        started = time.monotonic()
        try:
            return self._call(self._request(text, pending, notes, aliases, sent_at, recent))
        except _Failed as failure:
            self.last_error = failure.args[0]
            return {"unsupported": FAILED}
        finally:
            self.last_seconds = round(time.monotonic() - started, 3)


class FallbackInterpreter:
    """HASS-INTERP-OPENAI-1: interpret() as LocalInterpreter, but a first interpreter that failed (last_error), raised or
    answered outside the reply contract (`valid(result)` false) is followed by exactly one call to the second one.
    No third attempt, no loop. The answer is whichever interpreter's; `last_backend` names it ("openai" / "ollama"),
    `last_fallback` says the second one was asked and `last_primary_error` keeps the first one's short reason code."""

    def __init__(self, primary, fallback, valid):
        if not (callable(valid) and hasattr(primary, "interpret") and hasattr(fallback, "interpret")):
            raise ValueError("primary and fallback must interpret and valid must be callable")
        self.primary, self.fallback, self.valid = primary, fallback, valid
        self.last_error, self.last_backend, self.last_fallback, self.last_primary_error, self.last_seconds = None, None, False, None, None

    def _ok(self, result) -> bool:
        try: return bool(self.valid(result))
        except Exception:  # noqa: BLE001 - a checker that cannot decide is a no
            return False

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None) -> dict:
        args, kw = (text, pending, notes, aliases), {"sent_at": sent_at, "recent": recent}
        started = time.monotonic()
        try:
            result = self.primary.interpret(*args, **kw)
            problem = getattr(self.primary, "last_error", None) or (None if self._ok(result) else "contract")
        except Exception:  # noqa: BLE001 - the first interpreter's own error text is never kept
            result, problem = None, "error"
        if problem is None:
            self.last_error, self.last_backend = None, getattr(self.primary, "last_backend", None)
            self.last_fallback, self.last_primary_error = False, None
        else:
            result = self.fallback.interpret(*args, **kw)  # the one retry; its failure is final
            self.last_error = getattr(self.fallback, "last_error", None)
            self.last_backend, self.last_fallback, self.last_primary_error = getattr(self.fallback, "last_backend", None), True, problem
        self.last_seconds = round(time.monotonic() - started, 3)
        return result
