"""HASS-INTERP-OPENAI-1 measurement (operator-style script, outside the repo). Synthetic inputs only, real local router.

  python3 measure.py text    20 NL corpus items through LocalInterpreter(api=openai) -> runs/gpu_text.jsonl + runs/text_summary.json
  python3 measure.py labels  10 synthetic label photos through LabelReader(api=openai) -> runs/gpu_labels.jsonl + runs/labels_summary.json
Agreement is against recorded CPU (Ollama qwen3.6) answers; no CPU call is made here (that would load a model).
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE / "wt"
sys.path.insert(0, str(WT))

from hass import interpreter_prompt, label_eval, nl_eval as ne  # noqa: E402
from hass.interpreter_local import LocalInterpreter  # noqa: E402
from hass.label_reader import LabelReader, keep  # noqa: E402
from hass.ops import load_registry  # noqa: E402

ROUTER, GPU = "http://127.0.0.1:8010", "qwen3.8:27b-thinkingcap-q6"
CPU_TEXT = HERE.parent / "t_20e5f635" / "runs" / "after_qwen.jsonl"
CPU_PHOTOS = Path.home() / "agent-work/reports/hass/hass-model-1/res/q36-photos-nothink.jsonl"
PHOTOS = Path.home() / "agent-work/reports/hass/hass-model-1/synthetic-photos"
RUNS = HERE / "runs"


def pct(values, q):
    s = sorted(values)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def canon(reply):
    """Order-insensitive form of a reply for exact agreement."""
    if isinstance(reply, dict) and isinstance(reply.get("ops"), list):
        ops = sorted((json.dumps(o, sort_keys=True, ensure_ascii=False) for o in reply["ops"]))
        return json.dumps({"ops": ops, "revises": reply.get("revises")}, sort_keys=True, ensure_ascii=False)
    return json.dumps(reply, sort_keys=True, ensure_ascii=False)


def kind(reply):
    return next((k for k in ("ops", "question", "unsupported") if isinstance(reply, dict) and k in reply), "other")


def brief(reply):
    if not isinstance(reply, dict): return repr(reply)[:80]
    if "ops" in reply: return "ops " + ", ".join(f"{o.get('op')}({json.dumps(o.get('args'), ensure_ascii=False)[:90]})" for o in reply["ops"]) + (f" revises={reply['revises']}" if reply.get("revises") else "")
    if "question" in reply: return "question: " + str(reply["question"])[:90]
    if "unsupported" in reply: return "unsupported: " + str(reply["unsupported"])[:90]
    return json.dumps(reply, ensure_ascii=False)[:90]


def text():
    corpus = ne.load_corpus()
    registry = load_registry()
    cpu = ne.load_replies(CPU_TEXT)
    pool = [c for c in corpus if c["id"] in cpu and not cpu[c["id"]]["failed"]]
    chosen = ne.stratified(pool, 20)
    while len(chosen) > 20:  # stratified keeps one per intent (22 intents): drop from the intents with the most cases
        counts = {}
        for c in chosen: counts[c["intent"]] = counts.get(c["intent"], 0) + 1
        big = max(counts, key=lambda k: (counts[k], k))
        chosen.pop(max(i for i, c in enumerate(chosen) if c["intent"] == big))
    content = ne._content()
    prompt = interpreter_prompt.build(registry, content)
    asker = LocalInterpreter(ROUTER, GPU, prompt, timeout=60, api="openai", **ne._improvements(content))
    RUNS.mkdir(exist_ok=True)
    out = RUNS / "gpu_text.jsonl"
    rows = {}
    with open(out, "w", encoding="utf-8") as fh:
        for case in chosen:
            extras = {k: case[k] for k in ("notes", "aliases") if case.get(k)}
            if case.get("recent"): extras["recent"] = case["recent"]
            t0 = time.monotonic()
            reply = asker.interpret(case["text"], case["pending"], sent_at=ne.SENT_AT, **extras)
            wall = time.monotonic() - t0
            row = {"id": case["id"], "reply": reply, "failed": asker.last_error, "ms": round(wall * 1000), "seconds": asker.last_seconds}
            rows[case["id"]] = row
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            print(case["id"], round(wall, 2), asker.last_error or "ok", flush=True)
    gpu_scored = {i: {"reply": r["reply"], "failed": r["failed"], "ms": r["ms"], "firstMs": r["ms"], "firstFailed": r["failed"]} for i, r in rows.items()}
    cpu_scored = {i: cpu[i] for i in rows}
    cases = {c["id"]: c for c in chosen}
    detail, differ = [], []
    for i, row in rows.items():
        jg, jc = ne.judge(cases[i], gpu_scored[i], registry), ne.judge(cases[i], cpu_scored[i], registry)
        same = canon(row["reply"]) == canon(cpu[i]["reply"])
        entry = {"id": i, "intent": cases[i]["intent"], "text": cases[i]["text"], "gpuSeconds": round(row["ms"] / 1000, 2),
                 "cpuSeconds": round((cpu[i]["firstMs"] or 0) / 1000, 1), "cpuFirstFailed": cpu[i]["firstFailed"], "sameAnswer": same,
                 "sameKind": kind(row["reply"]) == kind(cpu[i]["reply"]), "kind": kind(row["reply"]), "gpuVerdict": jg["verdict"], "cpuVerdict": jc["verdict"],
                 "gpu": brief(row["reply"]), "cpu": brief(cpu[i]["reply"]), "gpuFailed": row["failed"]}
        detail.append(entry)
        if not same: differ.append(entry)
    secs = [r["ms"] / 1000 for r in rows.values()]
    warm = secs[1:]
    summary = {
        "model": GPU, "url": ROUTER, "n": len(rows), "failedCalls": sum(bool(r["failed"]) for r in rows.values()),
        "seconds": {"first": secs[0], "p50": pct(secs, 0.5), "p95": pct(secs, 0.95), "max": max(secs), "min": min(secs), "mean": round(sum(secs) / len(secs), 2),
                    "warmP50": pct(warm, 0.5), "warmP95": pct(warm, 0.95), "warmMax": max(warm)},
        "sameAnswer": sum(d["sameAnswer"] for d in detail), "sameKind": sum(d["sameKind"] for d in detail), "samePassVerdict": sum((d["gpuVerdict"] == "pass") == (d["cpuVerdict"] == "pass") for d in detail),
        "gpuScore": ne.score(chosen, gpu_scored, registry), "cpuScore": ne.score(chosen, cpu_scored, registry),
        "cpuSecondsP50": pct([d["cpuSeconds"] for d in detail], 0.5), "ids": [c["id"] for c in chosen], "detail": detail, "differ": [d["id"] for d in differ],
    }
    (RUNS / "text_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("n", "failedCalls", "seconds", "sameAnswer", "samePassVerdict", "differ")}, ensure_ascii=False))


def labels():
    cases = label_eval.load_cases(label_eval.CASES)
    cats = label_eval.catalog_categories()
    reader = LabelReader(ROUTER, GPU, timeout=60, api="openai")
    cpu_rows = {}
    for line in CPU_PHOTOS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "id" in row: cpu_rows[row["id"]] = row
    rows, gpu_replies, detail = [], {}, []
    for case in cases:
        image = (PHOTOS / case["photo"]).read_bytes()
        t0 = time.monotonic()
        found = reader.read(image, cats)
        wall = time.monotonic() - t0
        raw = None
        gpu_replies[case["id"]] = found
        cpu_found = keep(cpu_rows[case["id"]]["reply"], cats) if cpu_rows[case["id"]].get("reply") else {}
        detail.append({"id": case["id"], "seconds": round(wall, 2), "failed": reader.last_error, "gpu": found, "cpu": cpu_found,
                       "cpuSeconds": cpu_rows[case["id"]].get("wall_s"), "expected": case["expected"], "same": found == cpu_found})
        rows.append({"id": case["id"], "reply": found, "seconds": round(wall, 2), "failed": reader.last_error})
        print(case["id"], round(wall, 2), reader.last_error or "ok", found, flush=True)
    (RUNS / "gpu_labels.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    secs = [d["seconds"] for d in detail]
    summary = {"model": GPU, "n": len(detail), "failedCalls": sum(bool(d["failed"]) for d in detail),
               "seconds": {"first": secs[0], "p50": pct(secs, 0.5), "p95": pct(secs, 0.95), "max": max(secs)},
               "sameAsCpu": sum(d["same"] for d in detail), "gpuScore": label_eval.score(cases, gpu_replies, cats),
               "cpuScore": label_eval.score(cases, {i: (keep(r["reply"], cats) if r.get("reply") else {}) for i, r in cpu_rows.items() if i in gpu_replies}, cats),
               "cpuSecondsP50": pct([d["cpuSeconds"] for d in detail if d["cpuSeconds"]], 0.5), "detail": detail}
    (RUNS / "labels_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("n", "failedCalls", "seconds", "sameAsCpu")}))


if __name__ == "__main__":
    {"text": text, "labels": labels}[sys.argv[1]]()
