"""HASS-NL-1: natural-language corpus scorer and live runner for the Hass interpreter.

The corpus (hass/tests/fixtures/nl-corpus.jsonl) is SYNTHETIC: invented texts in the voice of a busy shop owner texting
from a phone (typos, fragments, slang, voice-to-text slips, several asks at once, vague asks, corrections, short answers
to a question, questions that are not change requests, jokes). Each row says what Hass must do with it:
  {"id", "text", "intent", "expect", "ask", "refuse", "pending": [...]}   plus optional
  "also": [expect, ...]   other acceptable outcomes (for example a question OR the exact-name draft),
  "recent": {"question": "..."}   Hass's last question, when the text is the owner's short answer to it,
  "notes", "aliases"   the saved context interpreter_eval cases may carry, "mustContain": [str], "tags": [str].
`expect` is the interpreter_eval shape: {"ops": [...], "revises": code|None}, {"question": true} or {"unsupported": true}.
`ask` is true when the right outcome is one short question, `refuse` when it is a plain refusal (nothing drafted).
Ops args listed in `expect` must match; args it does not list are not checked (hours and descriptions are free text and
are checked with `mustContain`, words that must appear in the drafted args, or in the question / refusal text).
Op order does not matter. Everything runs after the same `_checked` and registry checks the conversation applies.

Verdicts per case: pass | wrong-draft (a draft that is not an accepted outcome: the unsafe one) | over-cautious (asked or
refused where a draft was right) | kind-mismatch (asked where a refusal was right, or the reverse; nothing drafted) |
content-miss (right kind, a required word missing) | call-failed (no usable model reply).

Commands (offline unless --live):
  score --replies R [--corpus C]          one JSON summary: metrics, per-intent counts, failing ids with a short reason
  report --run LABEL=R [--run ...]        a markdown table, one column per run
  compare --before R1 --after R2          ids that regressed or were fixed
  --live --url U --model M --out FILE     OPERATOR ONLY, never in CI: asks the local model once per case, appends
                                          {"id","reply","failed","ms","firstMs","firstFailed"} lines to FILE.partial and
                                          links FILE when complete. --retry-timeout S asks a failed call once more with
                                          that longer limit (a shared CPU model can be swapped out between cases); the
                                          first attempt's time and failure are kept, so latency and timeouts stay honest
Case text is never printed by score, report or compare.
"""
import argparse, dataclasses, json, os, re, sys, time  # noqa: E401
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import interpret_check, interpreter_eval as ie, interpreter_prompt  # noqa: E402
from hass.content_model import ContentError, load_content  # noqa: E402
from hass.conversation import _checked  # noqa: E402
from hass.interpreter_local import FAILED, HEADERS, LocalInterpreter  # noqa: E402
from hass.ops import load_registry  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "hass" / "tests" / "fixtures" / "nl-corpus.jsonl"
EVENTS = CORPUS.with_name("nl-corpus-events.json")  # hikes laid over the prompt content, never written
SENT_AT = datetime(2026, 11, 9, 9, 40, tzinfo=ZoneInfo("America/Los_Angeles"))  # a Monday: every corpus date is relative to it
MIN_CASES = 200
INTENTS = frozenset({"availability", "hide", "restore", "maker", "product", "hike", "store", "price", "design", "undo", "status",
                     "info", "outside", "chitchat", "vague", "photo", "alias", "notes", "multi", "correction", "two-drafts", "answer"})
KEYS = frozenset({"id", "text", "intent", "expect", "ask", "refuse", "pending", "also", "recent", "notes", "aliases", "mustContain", "tags"})
AVAILABILITY_LISTS = ("yes", "limited", "no")
EvalError = ie.EvalError


def _strs(value) -> bool: return isinstance(value, list) and all(isinstance(x, str) and x for x in value)  # noqa: E704


def load_corpus(path=CORPUS) -> list:
    """The validated corpus rows; EvalError (a line number, never content) for anything malformed."""
    rows, seen = [], set()
    for n, row in ie._rows(path, "corpus"):
        ie._id(row, n, "corpus", seen)
        if not (set(row) <= KEYS and {"id", "text", "intent", "expect", "ask", "refuse", "pending"} <= set(row)):
            raise EvalError(f"corpus line {n}: not a case")
        bad = lambda why: EvalError(f"corpus line {n}: {why}")  # noqa: E731
        if not (isinstance(row["text"], str) and row["text"].strip() and len(row["text"]) <= 4000): raise bad("bad text")
        if row["intent"] not in INTENTS: raise bad("unknown intent")
        if not (isinstance(row["pending"], list) and all(isinstance(p, dict) for p in row["pending"])): raise bad("bad pending")
        codes = ie._pending_codes(row["pending"], n)
        expects = [row["expect"], *row.get("also", [])]
        if not isinstance(row.get("also", []), list) or not all(ie._expect_ok(e) for e in expects): raise bad("bad expect")
        if any("ops" in e and e["revises"] not in (None, *codes) for e in expects): raise bad("revises names no pending draft")
        if row["ask"] is not ("question" in row["expect"]) or row["refuse"] is not ("unsupported" in row["expect"]): raise bad("ask/refuse disagree with expect")
        if "notes" in row and not ie._notes_ok(row["notes"]): raise bad("bad notes")
        if "aliases" in row and not (isinstance(row["aliases"], list) and all(isinstance(a, dict) and set(a) == {"name", "kind", "id"}
                                                                               and all(isinstance(v, str) for v in a.values()) for a in row["aliases"])):
            raise bad("bad aliases")
        if "recent" in row and not (isinstance(row["recent"], dict) and set(row["recent"]) == {"question"} and isinstance(row["recent"]["question"], str)): raise bad("bad recent")
        if "mustContain" in row and not _strs(row["mustContain"]): raise bad("bad mustContain")
        if "tags" in row and not _strs(row["tags"]): raise bad("bad tags")
        rows.append(row)
    if len(rows) < MIN_CASES: raise EvalError(f"corpus: {len(rows)} cases, expected at least {MIN_CASES}")
    return rows


def load_replies(path) -> dict:
    """id -> {"reply", "failed", "ms"} (the live file; failed and ms may be absent in a hand-made file)."""
    replies, seen = {}, set()
    for n, row in ie._rows(path, "replies"):
        if set(row) == {ie.NOTE_KEY}: continue
        if not ({"id", "reply"} <= set(row) <= {"id", "reply", "failed", "ms", "firstMs", "firstFailed"}): raise EvalError(f"replies line {n}: not a reply")
        failed, ms, first_failed, first_ms = row.get("failed"), row.get("ms"), row.get("firstFailed"), row.get("firstMs", row.get("ms"))
        whole = lambda v: v is None or (isinstance(v, int) and not isinstance(v, bool) and v >= 0)  # noqa: E731
        if not (failed is None or isinstance(failed, str)) or not (first_failed is None or isinstance(first_failed, str)) or not (whole(ms) and whole(first_ms)):
            raise EvalError(f"replies line {n}: bad failed or ms")
        if failed is None and row["reply"] == {"unsupported": FAILED}: failed = "unknown"  # a hand-made file with the fixed failure reply
        if first_failed is None and "firstMs" not in row: first_failed = failed
        replies[ie._id(row, n, "replies", seen)] = {"reply": row["reply"], "failed": failed, "ms": ms, "firstMs": first_ms, "firstFailed": first_failed}
    return replies


def _order(calls):
    """Ops in a fixed order (op name, then the id or key it targets) and availability lists sorted: order never matters to the site."""
    if not (isinstance(calls, list) and all(isinstance(c, dict) and isinstance(c.get("args"), dict) for c in calls)): return calls
    fixed = [{**c, "args": {k: sorted(v) if k in AVAILABILITY_LISTS and isinstance(v, list) and all(isinstance(x, str) for x in v) else v
                            for k, v in c["args"].items()}} for c in calls]
    return sorted(fixed, key=lambda c: (str(c.get("op")), str(c["args"].get("id") or c["args"].get("key") or "")))


def _ordered(reply):
    return {**reply, "ops": _order(reply["ops"])} if isinstance(reply, dict) and isinstance(reply.get("ops"), list) else reply


def _text_of(got) -> str:
    kind = ie._kind(got)
    return json.dumps(got["ops"], ensure_ascii=False).lower() if kind == "ops" else str(got.get(kind, "")).lower()


def judge(case, record, registry) -> dict:
    """{"verdict", "kind", "intent": bool, "why"} for one case and its recorded reply row."""
    codes = {p.get("code") for p in case["pending"]}
    if record.get("failed"): return {"verdict": "call-failed", "kind": "none", "intent": False, "why": f"call failed: {record['failed']}"}
    got = interpret_check.check(_checked(_ordered(record["reply"])), registry, codes)
    kind = ie._kind(got)
    expects = [case["expect"], *case.get("also", [])]
    accepted = {ie._kind(e) for e in expects}
    must = [m.lower() for m in case.get("mustContain", [])]
    problems, intent_ok = [], False
    for expect in expects:
        if ie._kind(expect) != kind: continue
        wanted = {**case, "expect": {**expect, "ops": _order(expect["ops"])} if "ops" in expect else expect}
        why = ie._why(wanted, got, registry)
        if kind == "ops":
            names = [c["op"] for c in got["ops"]]
            intent_ok = intent_ok or (names == [c["op"] for c in wanted["expect"]["ops"]] and got["revises"] == expect["revises"])
        else:
            intent_ok = True
        if why is None and all(m in _text_of(got) for m in must):
            return {"verdict": "pass", "kind": kind, "intent": True, "why": None}
        problems.append(why or "required words missing")
    if kind == "ops":
        return {"verdict": "wrong-draft", "kind": kind, "intent": intent_ok, "why": problems[0] if problems else f"drafted where {'/'.join(sorted(accepted))} was right"}
    if kind in accepted: return {"verdict": "content-miss", "kind": kind, "intent": True, "why": problems[0] if problems else "required words missing"}
    if "ops" in accepted: return {"verdict": "over-cautious", "kind": kind, "intent": False, "why": f"{kind} where a draft was right"}
    return {"verdict": "kind-mismatch", "kind": kind, "intent": False, "why": f"{kind} where {'/'.join(sorted(accepted))} was right"}


def _pct(part, whole): return round(part / whole, 3) if whole else None  # noqa: E704


def _percentile(values, p):
    values = sorted(values)
    return values[max(0, -(-len(values) * p // 100) - 1)] if values else None  # nearest rank


def score(corpus, replies, registry) -> dict:
    """Metrics over the cases that have a reply row; ids and short reasons only."""
    done = [(c, judge(c, replies[c["id"]], registry)) for c in corpus if c["id"] in replies]
    n = len(done)
    count = lambda verdict: sum(j["verdict"] == verdict for _, j in done)  # noqa: E731
    ask = [(c, j) for c, j in done if c["ask"]]
    refuse = [(c, j) for c, j in done if c["refuse"]]
    nodraft = [(c, j) for c, j in done if not any("ops" in e for e in [c["expect"], *c.get("also", [])])]
    wants_draft = [(c, j) for c, j in done if "ops" in c["expect"]]
    calls = [replies[c["id"]] for c, _ in done]
    ok_ms = [r.get("firstMs", r["ms"]) for r in calls if r.get("firstMs", r["ms"]) is not None and not r.get("firstFailed", r["failed"])]  # first attempts that finished in time
    raw_ok = [r for r in calls if not r["failed"] and isinstance(r["reply"], dict)]
    schema_ok = [r for r in raw_ok if any(k in r["reply"] for k in ("ops", "question", "unsupported"))]
    per = {}
    for c, j in done:
        row = per.setdefault(c["intent"], {"cases": 0, "pass": 0, "wrongDraft": 0})
        row["cases"] += 1
        row["pass"] += j["verdict"] == "pass"
        row["wrongDraft"] += j["verdict"] == "wrong-draft"
    return {
        "cases": len(corpus), "scored": n, "missing": [c["id"] for c in corpus if c["id"] not in replies],
        "intentAccuracy": _pct(sum(j["intent"] for _, j in done), n),
        "strictAccuracy": _pct(count("pass"), n),
        "wrongDraftRate": _pct(count("wrong-draft"), n), "wrongDrafts": count("wrong-draft"),
        "draftWhenShouldNotRate": _pct(sum(j["kind"] == "ops" for _, j in nodraft), len(nodraft)),
        "questionWhenUnsureRate": _pct(sum(j["kind"] == "question" for _, j in ask), len(ask)), "askCases": len(ask),
        "refusalRate": _pct(sum(j["kind"] == "unsupported" for _, j in refuse), len(refuse)), "refuseCases": len(refuse),
        "overCautiousRate": _pct(sum(j["verdict"] == "over-cautious" for _, j in wants_draft), len(wants_draft)), "draftCases": len(wants_draft),
        "jsonValidRate": _pct(len(raw_ok), n), "schemaValidRate": _pct(len(schema_ok), n),
        "callsFailed": count("call-failed"), "timeouts": sum(r["failed"] == "timeout" for r in calls),
        "firstAttemptFailures": sum(bool(r.get("firstFailed", r["failed"])) for r in calls), "firstAttemptTimeouts": sum(r.get("firstFailed", r["failed"]) == "timeout" for r in calls),
        "latencyMs": {"p50": _percentile(ok_ms, 50), "p95": _percentile(ok_ms, 95), "max": max(ok_ms) if ok_ms else None, "calls": len(ok_ms)},
        "verdicts": {v: count(v) for v in ("pass", "wrong-draft", "over-cautious", "kind-mismatch", "content-miss", "call-failed")},
        "byIntent": dict(sorted(per.items())),
        "failed": [{"id": c["id"], "verdict": j["verdict"], "why": j["why"]} for c, j in done if j["verdict"] != "pass"],
    }


def compare(corpus, before, after, registry) -> dict:
    """Ids present in both reply sets: passed before and not now (regressed), the reverse (fixed), and new wrong drafts."""
    both = [c for c in corpus if c["id"] in before and c["id"] in after]
    one = {c["id"]: (judge(c, before[c["id"]], registry), judge(c, after[c["id"]], registry)) for c in both}
    return {"regressed": [{"id": i, "why": a["why"]} for i, (b, a) in one.items() if b["verdict"] == "pass" and a["verdict"] != "pass"],
            "fixed": [i for i, (b, a) in one.items() if b["verdict"] != "pass" and a["verdict"] == "pass"],
            "newWrongDrafts": [i for i, (b, a) in one.items() if a["verdict"] == "wrong-draft" and b["verdict"] != "wrong-draft"],
            "stillWrongDrafts": [i for i, (b, a) in one.items() if a["verdict"] == "wrong-draft" and b["verdict"] == "wrong-draft"],
            "compared": len(both)}


ROWS = (("Cases scored", "scored", "{}"), ("Intent accuracy", "intentAccuracy", "{:.1%}"), ("Strict accuracy (right ops, args, words)", "strictAccuracy", "{:.1%}"),
        ("Wrong-draft rate (unsafe)", "wrongDraftRate", "{:.1%}"), ("Drafted where a draft was NOT right", "draftWhenShouldNotRate", "{:.1%}"),
        ("Asked a question when it should ask", "questionWhenUnsureRate", "{:.1%}"), ("Refused when it should refuse", "refusalRate", "{:.1%}"),
        ("Over-cautious (asked or refused a clear request)", "overCautiousRate", "{:.1%}"), ("JSON valid", "jsonValidRate", "{:.1%}"),
        ("Calls failed at the end", "callsFailed", "{}"), ("First attempts that timed out", "firstAttemptTimeouts", "{}"))


def report(summaries) -> str:
    """A markdown table, one column per (label, summary)."""
    labels = [label for label, _ in summaries]
    lines = ["| Measure | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for title, key, fmt in ROWS:
        lines.append(f"| {title} | " + " | ".join("n/a" if s[key] is None else fmt.format(s[key]) for _, s in summaries) + " |")
    for title, key in (("Latency p50 (s)", "p50"), ("Latency p95 (s)", "p95")):
        lines.append(f"| {title} | " + " | ".join("n/a" if s["latencyMs"][key] is None else f"{s['latencyMs'][key] / 1000:.1f}" for _, s in summaries) + " |")
    return "\n".join(lines)


# -- live (operator only) ----------------------------------------------------------------------------------------------
def _content():
    content = load_content()
    community = dict(content.community or {})
    have = {e.get("id") for e in community.get("events") or [] if isinstance(e, dict)}
    extra = json.loads(EVENTS.read_text("utf-8"))
    if clash := next((e["id"] for e in extra if e["id"] in have), None): raise EvalError(f"event {clash} is already in the content")
    return dataclasses.replace(content, community={**community, "events": [*ie._room_for(community.get("events") or [], extra), *extra]})


def live(corpus, url, model, out, timeout=120, think=None, baseline=False, warmup_timeout=900, transport=None, registry=None,
         content=None, clock=time.monotonic, progress=None, retry_timeout=0) -> dict:
    """Ask the local model once per case. FILE.partial is appended (and resumed) one fsynced line per case and linked to FILE
    only when complete. baseline=True sends exactly what the service sends today (no hints, no recent question)."""
    target = Path(out).expanduser().resolve()
    if target == REPO or REPO in target.parents: raise EvalError("--out must be outside the repository")
    if os.path.lexists(target): raise EvalError("--out already exists")
    if not target.parent.is_dir(): raise EvalError("--out folder does not exist")
    partial = target.with_name(target.name + ".partial")
    try:
        content = content or _content()
        prompt = interpreter_prompt.build(registry or load_registry(), content)
        kwargs = {} if baseline else _improvements(content)
        asker = LocalInterpreter(url, model, prompt, timeout=timeout, transport=transport, think=think, **kwargs)
    except (ContentError, ValueError, OSError) as exc:
        raise EvalError(str(exc)) from None
    done = set(load_replies(partial)) if partial.exists() else set()
    if warmup_timeout and not done:  # a cold prompt can take minutes on a CPU; a timed-out call never warms the cache
        body = asker._request("hello", [], sent_at=SENT_AT)
        try: asker.transport(asker.url, body, dict(HEADERS), warmup_timeout)
        except Exception: pass  # noqa: BLE001,E701 - the measured calls report their own failures
    fd = os.open(partial, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        for case in corpus:
            if case["id"] in done: continue
            extras = {k: case[k] for k in ("notes", "aliases") if case.get(k)}
            if case.get("recent") and not baseline: extras["recent"] = case["recent"]
            start = clock()
            reply = asker.interpret(case["text"], case["pending"], sent_at=SENT_AT, **extras)
            ms = first_ms = round((clock() - start) * 1000)
            first_failed = asker.last_error
            if first_failed in ("timeout", "connect") and retry_timeout > timeout:  # the model was busy or swapped out: ask once more, patiently
                asker.timeout = retry_timeout
                try:
                    start = clock()
                    reply = asker.interpret(case["text"], case["pending"], sent_at=SENT_AT, **extras)
                    ms = round((clock() - start) * 1000)
                finally:
                    asker.timeout = timeout
            row = {"id": case["id"], "reply": reply, "failed": asker.last_error, "ms": ms, "firstMs": first_ms, "firstFailed": first_failed}
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            if progress: progress(case["id"], first_ms, first_failed, asker.last_error)
    os.link(partial, target)
    os.unlink(partial)
    rows = load_replies(target)
    return {"recorded": len(rows), "failedCalls": sum(bool(r["failed"]) for r in rows.values())}


def _improvements(content) -> dict:
    """What the service now adds to a request (hints from the catalog); lazily imported so the baseline checkout does not need it."""
    from hass import nl_prep  # noqa: PLC0415
    return {"hinter": nl_prep.make_hinter(content)}


def subset(corpus, every=None, limit=None):
    rows = corpus[::every] if every else corpus
    return rows[:limit] if limit else rows


def main(argv=None, transport=None) -> int:
    parser = argparse.ArgumentParser(description="HASS-NL-1 natural-language interpreter eval; --live is operator only")
    parser.add_argument("command", nargs="?", choices=("score", "report", "compare"))
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--baseline", action="store_true", help="live: send what the service sent before HASS-NL-1")
    for flag in ("--replies", "--url", "--model", "--out", "--before", "--after"): parser.add_argument(flag)
    parser.add_argument("--run", action="append", default=[], help="report: LABEL=REPLIES_FILE")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--retry-timeout", type=int, default=0, help="live: ask a timed-out call once more with this many seconds (0 = off)")
    parser.add_argument("--think", choices=("true", "false"))
    parser.add_argument("--every", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--warmup-timeout", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        corpus = load_corpus(args.corpus)
        registry = load_registry()
        if args.live:
            if not (args.url and args.model and args.out and not args.command): parser.error("use: --live --url U --model M --out FILE")
            think = None if args.think is None else args.think == "true"
            say = lambda i, ms, err, final: print(f"{i} {ms}ms {err or 'ok'}{'' if final == err else ' -> ' + (final or 'ok')}", file=sys.stderr, flush=True)  # noqa: E731 - no case text
            summary = live(subset(corpus, args.every, args.limit), args.url, args.model, args.out, timeout=args.timeout, think=think,
                           baseline=args.baseline, warmup_timeout=args.warmup_timeout, transport=transport, registry=registry, progress=say,
                           retry_timeout=args.retry_timeout)
        elif args.command == "score" and args.replies:
            summary = score(corpus, load_replies(args.replies), registry)
        elif args.command == "report" and args.run:
            runs = []
            for item in args.run:
                label, _, path = item.partition("=")
                if not (label and path): parser.error("--run LABEL=FILE")
                runs.append((label, score(corpus, load_replies(path), registry)))
            print(report(runs))
            return 0
        elif args.command == "compare" and args.before and args.after:
            summary = compare(corpus, load_replies(args.before), load_replies(args.after), registry)
        else:
            parser.error("use: score --replies R, report --run LABEL=R, compare --before R1 --after R2, or --live --url U --model M --out FILE")
    except EvalError as exc:
        print(f"nl_eval: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 1 if args.command == "compare" and summary["regressed"] else 0


if __name__ == "__main__":
    sys.exit(main())
