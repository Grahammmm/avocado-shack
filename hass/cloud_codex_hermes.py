"""HASS-CLOUD-CODEX-1: the Hermes side of Hass's cloud reads, run by the HERMES Python (hass/cloud_codex.py), never imported
by Hass. argv: HERMES_ROOT; stdin: {"model", "effort", "instructions", "text", "images", "timeout"}; stdout: one line {"ok": true,
"text", "model", "ms"} or {"ok": false, "code", "ms"}. No prompt, body, path, header, credential or error text is printed."""
import json, os, sys, time  # noqa: E401
KEYS, EFFORTS = {"model", "effort", "instructions", "text", "images", "timeout"}, ("low", "medium")
class _Code(Exception): pass  # noqa: E701,E302
def _request(raw):  # noqa: E302
    try: req = json.loads(raw)
    except ValueError: raise _Code("usage") from None
    ok = (isinstance(req, dict) and set(req) == KEYS and isinstance(req["model"], str) and 0 < len(req["model"]) <= 100
          and req["effort"] in EFFORTS and isinstance(req["instructions"], str) and req["instructions"].strip()
          and isinstance(req["text"], str) and isinstance(req["images"], list) and (req["text"] or req["images"])
          and all(isinstance(i, str) and i.startswith("data:image/") for i in req["images"])
          and type(req["timeout"]) is int and 5 <= req["timeout"] <= 20)
    if not ok: raise _Code("usage")
    return req

def run(raw, resolve, post, clock=time.monotonic) -> dict:
    """One call. ``resolve() -> (token or None, base_url)`` (Hermes' one resolution); ``post(url, headers, payload, timeout)
    -> (status, text lines)`` (SSE lines, or the error body); a raised TimeoutError is ``timeout``, any other error ``api``."""
    started = clock()
    try:
        req = _request(raw)
        try: token, base = resolve()
        except Exception: raise _Code("hermes") from None  # noqa: BLE001 - its text could name a path
        if not token: raise _Code("auth")
        content = [{"type": "input_text", "text": req["text"]}] * bool(req["text"]) + [{"type": "input_image", "image_url": u} for u in req["images"]]
        payload = {"model": req["model"], "store": False, "stream": True, "instructions": req["instructions"],
                   "reasoning": {"effort": req["effort"]}, "input": [{"type": "message", "role": "user", "content": content}]}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "text/event-stream"}
        text = _stream(post, base.strip().rstrip("/") + "/responses", headers, payload, req["timeout"], lambda: clock() - started)
        return {"ok": True, "text": text, "model": req["model"], "ms": round((clock() - started) * 1000)}
    except _Code as code:
        return {"ok": False, "code": code.args[0], "ms": round((clock() - started) * 1000)}

def _stream(post, url, headers, payload, timeout, spent) -> str:
    parts, done = [], False
    try:
        status, lines = post(url, headers, payload, timeout)
        if status in (401, 403) or status == 429: raise _Code("rate" if status == 429 else "auth")
        if status != 200: raise _Code("model" if status in (400, 404) and "model_not_found" in "".join(lines) else "api")
        for line in lines:
            if spent() > timeout: raise TimeoutError
            if not line.startswith("data:") or line[5:].strip() in ("", "[DONE]"): continue
            event = json.loads(line[5:])
            kind = event.get("type") if isinstance(event, dict) else None
            if kind == "response.output_text.delta" and isinstance(event.get("delta"), str): parts.append(event["delta"])
            done = done or kind == "response.completed"
            if kind in ("response.failed", "response.incomplete", "error"): raise _Code("api")
    except _Code: raise
    except TimeoutError: raise _Code("timeout") from None
    except Exception: raise _Code("api") from None  # noqa: BLE001 - a broken stream is a failed call; its text is never kept
    if not done or not parts: raise _Code("api")
    return "".join(parts)

def _hermes(root):
    """(resolve, post) of the Hermes install at ``root``: its bootstrap, its credential resolution, its httpx."""
    sys.path[0:1] = [root]  # this script's folder (hass/) never shadows a Hermes module
    os.chdir(root)
    sys._hermes_pin_default_home = True  # type: ignore[attr-defined]
    import hermes_bootstrap  # noqa: F401  (the dependency bootstrap the hermes launcher runs)
    import httpx
    from agent.auxiliary_client import _resolve_codex_credential_and_base
    def post(url, headers, payload, timeout):  # noqa: E306
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=5)) as http, http.stream("POST", url, headers=headers, json=payload) as resp:
                return resp.status_code, list(resp.iter_lines())
        except httpx.TimeoutException: raise TimeoutError from None
    return _resolve_codex_credential_and_base, post

def main(argv, stdin=sys.stdin, stdout=sys.stdout, hermes=_hermes) -> int:
    raw, post = stdin.read(16 * 1024 * 1024), None
    try: resolve, post = hermes(argv[1]) if len(argv) == 2 else (None, None)
    except Exception: resolve = False  # noqa: BLE001 - no traceback: it could carry paths
    out = run(raw, resolve, post) if resolve else {"ok": False, "code": "usage" if resolve is None else "hermes", "ms": 0}
    print(json.dumps(out, sort_keys=True), file=stdout, flush=True)
    return 0 if out["ok"] else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv))
