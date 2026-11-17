"""HASS-CLOUD-CODEX-1: interpreter, answer and label reads on OpenAI through G's Codex sign-in in Hermes. Hass sees no credential
and makes no cloud connection: CodexTransport hands the chat request to cloud_codex_hermes.py (run by the Hermes Python) and the
text back in the chat shape for the unchanged openai parser. A failure is _Failed("codex-<code>") plus `ALERTS hass-cloud: <code>`
(once per code per hour); never a prompt, image, body or credential. Check: python3 -B hass/cloud_codex.py check --host H."""
import json, logging, os, re, shutil, subprocess, sys, threading, time  # noqa: E401
from pathlib import Path
if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hass.clover import chat  # noqa: E402
from hass.interpreter_local import _Failed  # noqa: E402
LOG = logging.getLogger("hass.cloud")
KEYS, EFFORTS, CODES = {"api", "model", "effort", "timeout", "fallback"}, ("low", "medium"), ("auth", "rate", "model", "timeout", "api", "hermes", "usage")
SLACK, _alerted = 3, {}  # SLACK: Hermes start-up on top of the call's own timeout; the cloud costs at most timeout + SLACK
BUDGET = 28  # s: a codex call AND its local fallback together, inside Hass's 30 s worker deadline (PLAN-v2); 20 + SLACK leaves >= 5 s
# PLAN-v2 finance-local: price/cost/money, stock/count/qty, sku/barcode, till and item words, "set X to N": local only, till or no till
FINANCE = re.compile(r"\$ ?\d|\d ?(?:dollars?|bucks|cents?|%)|\b(?:prices?|priced|pricing|costs?|money|sku|skus|barcodes?|upcs?|qty|quantit(?:y|ies)"
                     r"|stock\w*|inventory|counts?|till|clover|register|pos|point of sale|on hand|sold|sell(?:s|ing)?|sales?|revenue|takings|margins?|wholesale"
                     r"|invoices?|refunds?|payments?|discounts?|percent|items?|low_stock|received)\b"
                     r"|\b(?:set|change|update|make|mark|raise|lower|drop|bump|put|move)\b.{0,80}?\bto \$?\d+(?:[.,]\d+)?(?![\d.:,]|\s*(?:am|pm|a\.m|p\.m|o'?clock))")
CHAT = (chat.PRICE_WRITE, chat.TILL_WRITE, chat.STOCK_WRITE, chat.STOCKISH, chat.LOW)  # the till desk's own forms, read-only
# PLAN-v2 line 70, fail closed: a price or count never reaches the cloud, so ANY number stays local (over-blocking accepted). Only
# clock times (5pm, 10:30, 10:30am) and calendar dates (11/16, 2026-11-16, Nov 16th, 16th of Nov) are cut out first; a bare ordinal
# ("the 7th jar") is a number; "a few" is not.
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_END, _AMPM = r"(?!\d|[.,:/-]\d)", r"\s*(?:am|pm|a\.m\.?|p\.m\.?)(?![a-z])"  # a time/date ends where no digit continues it
WHEN = re.compile(rf"\b\d{{4}}-\d\d-\d\d(?:[t ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:z|[+-]\d\d:\d\d)?)?{_END}|\b\d{{1,2}}:\d\d(?:{_AMPM})?{_END}"
                  rf"|\b\d{{1,2}}{_AMPM}|\b(?:1[0-2]|0?[1-9])/(?:3[01]|[12]\d|0?[1-9])(?:/(?:\d{{4}}|\d\d))?{_END}"
                  rf"|\b{_MON}\.? \d{{1,2}}(?:st|nd|rd|th)?(?:,? \d{{4}})?{_END}|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}\b(?:,?\s+\d{{4}})?")
NUMBER = re.compile(r"\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen"
                    r"|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|dozen|couple"
                    r"|zero|million|billion|trillion|grand|score|pair|quarter|gross|nil|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth"
                    r"|tenth|eleventh|twelfth|(?:thir|four|fif|six|seven|eigh|nine)teenth|(?:twen|thir|for|fif|six|seven|eigh|nine)tieth"
                    r"|hundredth|thousandth|millionth)s?\b|\bhal(?:f|ves)\b")


def numbered(t) -> bool:
    """True when a (cleaned) text holds a digit or a spelled count/money word once its clock times and dates are cut out."""
    return bool(NUMBER.search(WHEN.sub(" ", t)))


def till_like(text) -> bool:
    """True when any string in the request text (each JSON string value, or the raw text) looks like a till/price/stock message."""
    try: stack = [json.loads(text)]
    except ValueError: stack = [text]
    while stack:
        x = stack.pop()
        if isinstance(x, dict): stack.extend(x.values())
        elif isinstance(x, list): stack.extend(x)
        elif isinstance(x, str) and (FINANCE.search(t := chat._clean(x)) or numbered(t) or any(p.search(t) for p in CHAT)): return True
    return False

def alert(code, clock=time.monotonic):
    if code in _alerted and clock() - _alerted[code] < 3600: return
    _alerted[code] = clock()
    LOG.error("ALERTS hass-cloud: %s", code)

def block_ok(itp, nested_ok) -> bool:
    """No url or keyFile; effort low|medium; timeout 5-20; a required local fallback (api ollama|openai, nested_ok)."""
    if not (isinstance(itp, dict) and {"api", "model", "fallback"} <= set(itp) <= KEYS and isinstance(itp["fallback"], dict)): return False
    fb, timeout = dict(itp["fallback"]), itp.get("timeout", 12)
    api = fb.pop("api", "ollama")
    return (isinstance(itp["model"], str) and 0 < len(itp["model"]) <= 100 and not any(c.isspace() for c in itp["model"])
            and itp.get("effort", "low") in EFFORTS and type(timeout) is int and 5 <= timeout <= 20
            and api in ("ollama", "openai") and not (api == "openai" and "think" in fb) and nested_ok(fb))

class Runner:
    """runner(request) -> the runner's one JSON line as a dict (one subprocess per call; request on stdin, never argv)."""
    def __init__(self, launcher=None):
        self.launcher, self.found = launcher, None
    def __call__(self, request):
        from hass.photo_polish import find_hermes
        self.found = self.found or find_hermes(self.launcher or shutil.which("hermes") or os.path.expanduser("~/.local/bin/hermes"))
        if self.found is None: return {"ok": False, "code": "hermes"}
        try:
            done = subprocess.run([self.found[0], str(Path(__file__).with_name("cloud_codex_hermes.py")), self.found[1]], input=json.dumps(request),
                                  capture_output=True, text=True, timeout=request["timeout"] + SLACK, check=False)
            return json.loads(done.stdout.strip().splitlines()[-1])
        except subprocess.TimeoutExpired: return {"ok": False, "code": "timeout"}
        except (OSError, ValueError, IndexError): return {"ok": False, "code": "hermes"}

class CodexTransport:
    """The LocalInterpreter transport for api "codex": (url, body, headers, timeout) -> (200, chat-shaped body). A till-like text never
    reaches the runner: it is _Failed("codex-local") with no alert, so the one local fallback answers it."""
    def __init__(self, effort="low", runner=None):
        self.effort, self.runner, self.started = effort, runner or Runner(), None
    def __call__(self, url, body, headers, timeout):
        self.started = time.monotonic()  # what Remaining counts the fallback's share of BUDGET from
        messages = json.loads(body)["messages"]
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        parts = [p for m in messages if m["role"] == "user" for p in (m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}])]
        text = "\n".join(p["text"] for p in parts if p["type"] == "text")
        if till_like(text): raise _Failed("codex-local")
        said = self.runner({"model": json.loads(body)["model"], "effort": self.effort, "instructions": system or text, "text": text if system else "",
                            "images": [p["image_url"]["url"] for p in parts if p["type"] == "image_url"], "timeout": min(timeout, 20)})
        if not (isinstance(said, dict) and said.get("ok") is True and isinstance(said.get("text"), str)):
            code = said.get("code") if isinstance(said, dict) and said.get("code") in CODES else "hermes"
            alert(code)
            raise _Failed(f"codex-{code}")
        return 200, json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": said["text"]}}]}, ensure_ascii=False).encode()

class Remaining:
    """A codex call's local fallback transport, given only what is left of BUDGET since that call began (never more than its own
    timeout) and stopped there: _Failed("timeout") whatever the local server does. Qwen's own settings are not changed."""
    def __init__(self, codex, transport, clock=time.monotonic):
        self.codex, self.transport, self.clock = codex, transport, clock
    def __call__(self, url, body, headers, timeout):
        began, self.codex.started = self.codex.started, None
        # no active codex start: the whole budget; an active start keeps counting, so an expired one is refused, never reset
        left = BUDGET if began is None else min(BUDGET, BUDGET - (self.clock() - began))
        if left < 1: raise _Failed("timeout")  # fail closed: the local transport is not called
        box, done = [], threading.Event()
        def run():
            try: box.append((True, self.transport(url, body, headers, min(timeout, left))))
            except Exception as exc: box.append((False, exc))  # noqa: BLE001 - handed back to the interpreter's own mapping
            finally: done.set()
        threading.Thread(target=run, daemon=True).start()
        if not done.wait(left) or not box: raise _Failed("timeout")
        if not box[0][0]: raise box[0][1]
        return box[0][1]

def budget(codex, fallback):
    """Give a codex primary's local fallback (interpreter or reader) only what is left of BUDGET; returns the fallback."""
    fallback.transport = Remaining(codex, fallback.transport)
    return fallback

def reader(cls, itp, transport=None, **local):
    """An AnswerReader/LabelReader on codex whose one fallback is the same class on the block's local fallback, inside BUDGET."""
    fb, transport = itp["fallback"], transport or CodexTransport(itp.get("effort", "low"))
    return cls(None, itp["model"], timeout=itp.get("timeout", 12), api="codex", transport=transport,
               fallback=budget(transport, cls(fb["url"], fb["model"], timeout=fb.get("timeout", 30), api=fb.get("api", "ollama"), **local)))

def transcript(itp) -> dict:
    """HASS-TRANSCRIPT-1's backend/model/latency of the last interpreted message (never a prompt, image or credential)."""
    seconds = getattr(itp, "last_seconds", None)
    backend = "local-fallback" if getattr(itp, "last_fallback", False) is True else "codex" if getattr(itp, "last_backend", None) == "codex" else "local"
    return {"backend": backend, "model": getattr(itp, "last_model", None), "ms": round(seconds * 1000) if isinstance(seconds, (int, float)) else None}

def check(itp, runner=None) -> dict:
    said = (runner or Runner())({"model": itp["model"], "effort": itp.get("effort", "low"), "timeout": itp.get("timeout", 12),
                                 "instructions": 'Answer only with the JSON object {"ok": true}.', "text": "ok?", "images": []})
    if isinstance(said, dict) and said.get("ok") is True: return {"result": "ok", "model": said.get("model"), "ms": said.get("ms")}
    return {"result": said.get("code") if isinstance(said, dict) and said.get("code") in CODES else "hermes"}

def main(argv=None) -> int:
    args, itp = list(sys.argv[1:] if argv is None else argv), None
    if len(args) == 3 and args[:2] == ["check", "--host"]:
        from hass import host
        try: itp = host.load_host(args[2])["interpreter"]
        except host.HostConfigError: pass
    print(json.dumps(out := check(itp) if isinstance(itp, dict) and itp.get("api") == "codex" else {"result": "usage"}))
    return 0 if out["result"] == "ok" else 1

if __name__ == "__main__":
    sys.exit(main())
