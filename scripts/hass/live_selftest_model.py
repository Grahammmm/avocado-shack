#!/usr/bin/env python3
"""HASS-LIVE-AUDIT-1: the live-model draft round trip of scripts/hass/live_selftest.sh (operator only, never in CI).

    python3 -B scripts/hass/live_selftest_model.py --url http://127.0.0.1:11434 --model NAME [--ids e01,e03,e25]

Takes a few SYNTHETIC cases from hass/tests/fixtures/interpreter-eval.jsonl (never owner text), asks the existing
local model once per case through hass/interpreter_eval.live (the same prompt builder and LocalInterpreter, with the
production default timeout), scores the replies with hass/interpreter_eval.score and prints one JSON line:
cases, failedCalls (timeouts or connection failures), passed, failed ids, seconds (wall time). The replies file is
written 0600 to a fresh temp dir outside the repository and removed afterwards. No model is pulled or changed.
Exit 0 every call answered and every case passed, 1 otherwise, 2 bad input.
"""
import argparse, json, sys, tempfile, time  # noqa: E401
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from hass import interpreter_eval as ev  # noqa: E402
from hass.ops import load_registry  # noqa: E402

DEFAULT_IDS = "e01,e03,e25"  # add a product, edit a description, a request that must become a question


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--ids", default=DEFAULT_IDS)
    args = ap.parse_args(argv)
    try:
        cases = {c["id"]: c for c in ev.load_cases(ev.CASES)}
        wanted = [i for i in args.ids.split(",") if i]
        if not wanted or any(i not in cases for i in wanted): raise ev.EvalError("--ids: unknown case id")
        subset = [cases[i] for i in wanted]
        with tempfile.TemporaryDirectory(prefix="hass-selftest-model-") as tmp:
            out = Path(tmp) / "replies.jsonl"
            start = time.monotonic()
            recorded = ev.live(subset, args.url, args.model, str(out))
            seconds = round(time.monotonic() - start, 1)
            summary = ev.score(subset, ev.load_replies(out), load_registry())
    except ev.EvalError as exc:
        print(json.dumps({"result": "error", "error": str(exc)}))
        return 2
    report = {"cases": len(subset), "failedCalls": recorded["failedCalls"], "passed": summary["passed"],
              "failed": [f["id"] for f in summary["failed"]], "seconds": seconds}
    print(json.dumps(report, sort_keys=True))
    return 0 if recorded["failedCalls"] == 0 and summary["passed"] == len(subset) else 1


if __name__ == "__main__":
    sys.exit(main())
