"""Queue-wait measurement: one synthetic "fleet" request in flight on the shared model while a Hass call arrives.
The filler is a plain counting prompt through the same router; it is the only extra load (about 35 s of slot time in total)."""
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "wt"))
from hass import interpreter_prompt, nl_eval as ne  # noqa: E402
from hass.interpreter_local import LocalInterpreter  # noqa: E402
from hass.ops import load_registry  # noqa: E402

ROUTER, GPU = "http://127.0.0.1:8010", "qwen3.8:27b-thinkingcap-q6"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def slot_busy():
    with OPENER.open("http://127.0.0.1:8003/slots", timeout=3) as r:
        return any(s.get("is_processing") for s in json.loads(r.read()))


def filler(tokens, out):
    body = {"model": GPU, "messages": [{"role": "user", "content": "Write the whole numbers from 1 upward, separated by single spaces, and nothing else."}],
            "max_tokens": tokens, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(ROUTER + "/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.monotonic()
    with OPENER.open(req, timeout=120) as r:
        d = json.loads(r.read())
    out["seconds"] = round(time.monotonic() - t0, 2)
    out["tokens"] = d.get("usage", {}).get("completion_tokens")


content = ne._content()
registry = load_registry()
prompt = interpreter_prompt.build(registry, content)
corpus = {c["id"]: c for c in ne.load_corpus()}
case = corpus["n110"]
asker = LocalInterpreter(ROUTER, GPU, prompt, timeout=60, api="openai", **ne._improvements(content))


def hass():
    t0 = time.monotonic()
    asker.interpret(case["text"], case["pending"], sent_at=ne.SENT_AT)
    return round(time.monotonic() - t0, 2), asker.last_error


rows = []
hass()  # warm the prompt cache (not recorded)
for n in range(3):
    s, err = hass()
    rows.append({"kind": "idle", "hassSeconds": s, "error": err})
    print(rows[-1], flush=True)
for tokens in (100, 300, 600):
    out = {}
    th = threading.Thread(target=filler, args=(tokens, out))
    t_start = time.monotonic()
    th.start()
    for _ in range(40):  # wait until the slot is really busy
        if slot_busy(): break
        time.sleep(0.05)
    started_after = round(time.monotonic() - t_start, 2)
    s, err = hass()
    th.join()
    rows.append({"kind": "fleet-request-in-flight", "fillerMaxTokens": tokens, "fillerTotalSeconds": out.get("seconds"), "fillerTokens": out.get("tokens"),
                 "hassStartedAfterSeconds": started_after, "hassSeconds": s, "error": err,
                 "impliedWaitSeconds": round(s - 1.3, 1)})
    print(rows[-1], flush=True)
    s, err = hass()  # after the filler: back to normal
    rows.append({"kind": "after", "hassSeconds": s, "error": err})
    print(rows[-1], flush=True)
(HERE / "runs" / "queue.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
