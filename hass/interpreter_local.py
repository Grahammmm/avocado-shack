"""NB-AV-02 (H05): local-model interpreter adapter for the Ollama JSON chat API, behind an injectable transport.

LocalInterpreter(base_url, model, system_prompt).interpret(text, pending) sends one `POST /api/chat` to a loopback
http URL and returns the decoded JSON object the model wrote, or {"unsupported": FAILED} on any failure. The failure
reason is kept only as a short code in `last_error` (never the URL, prompt or owner text; `request` means the text or
pending list could not be encoded); nothing is logged.
RF1240-20: repeated keys and NaN/Infinity in a reply are a failed call (`not-json` in the envelope, `shape` in content).
Not wired into any service: the operator names the existing local model; nothing is pulled or changed here.
"""
import json, urllib.error, urllib.parse, urllib.request  # noqa: E401
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

LOOPBACK = ("127.0.0.1", "localhost", "::1")
CHAT_PATH, MAX_BODY, MAX_MODEL = "/api/chat", 256 * 1024, 100
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


class LocalInterpreter:
    """The Conversation interpreter contract: interpret(text, pending) -> dict. Transport is
    (url, body_bytes, headers, timeout) -> (status, body_bytes); the default never uses a proxy or follows a redirect."""

    def __init__(self, base_url, model, system_prompt, timeout=30, transport=None, clock=None):
        self.url = check_url(base_url) + CHAT_PATH
        if not (isinstance(model, str) and 0 < len(model) <= MAX_MODEL and not any(c.isspace() for c in model)):
            raise ValueError(f"model must be a name of 1-{MAX_MODEL} characters without spaces")
        if not (isinstance(system_prompt, str) and system_prompt.strip()):
            raise ValueError("system prompt must be non-empty text")
        if type(timeout) is not int or not 1 <= timeout <= 120:
            raise ValueError("timeout must be a whole number of seconds from 1 to 120")
        if clock is not None and not callable(clock): raise ValueError("clock must be callable")
        self.model, self.system_prompt, self.timeout = model, system_prompt, timeout
        self.transport = transport or urllib_transport
        self.clock = clock if clock is not None else (lambda: datetime.now(timezone.utc))
        self.last_error = None

    def _today(self):
        """(YYYY-MM-DD, weekday) in Pacific time; a raising, naive or non-datetime clock is _Failed("clock")."""
        try:
            now = self.clock()
            if not isinstance(now, datetime) or now.utcoffset() is None: raise ValueError
            local = now.astimezone(PACIFIC)
        except Exception:  # noqa: BLE001 - the clock's own error text is never kept
            raise _Failed("clock") from None
        return local.date().isoformat(), WEEKDAYS[local.weekday()]

    def _request(self, text, pending, notes=None, aliases=None) -> bytes:
        today, weekday = self._today()
        try:  # a lone surrogate or a non-JSON value is a failed call, never a crash
            fields = {"message": text, "pending": pending, "today": today, "weekday": weekday}
            if isinstance(notes, list) and notes: fields["notes"] = notes  # AV1102-09: owner preferences, never claims
            if isinstance(aliases, list) and aliases: fields["aliases"] = aliases  # AV0007-06: identifiers, never claims
            user = json.dumps(fields, ensure_ascii=False)
            return json.dumps({"model": self.model, "messages": [{"role": "system", "content": self.system_prompt},
                                                                 {"role": "user", "content": user}],
                               "stream": False, "format": "json", "options": {"temperature": 0}},
                              ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise _Failed("request") from None

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

    def interpret(self, text, pending, notes=None, aliases=None) -> dict:
        """The model's decoded JSON object as-is (Conversation's checks decide if it is usable), else the fixed
        unsupported reply with the reason code in last_error."""
        self.last_error = None
        try:
            return self._call(self._request(text, pending, notes, aliases))
        except _Failed as failure:
            self.last_error = failure.args[0]
            return {"unsupported": FAILED}
