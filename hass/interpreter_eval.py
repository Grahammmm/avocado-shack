"""NB-AV-04 (H09): interpreter eval set and offline scorer (AV1322-14: eval set v3 adds the home-page ops, route.add/hide/
restore and a no-source route.add question; AV1102-10: v4 adds brand, home-text, design and saved-note cases, and a
case may carry `notes`). `score --cases C --replies R` prints one JSON summary (ids
and short reasons, never a case text or reply); exit 0 when every case was scored, even if some failed; 2 for an
unreadable file, malformed line, duplicate id, a case file without exactly 63 cases or an unscorable case (RF0550-4:
bad/repeated pending code, `revises` naming no pending draft, > MAX_OPS expected ops). `--live --url U --model M
--out FILE` is OPERATOR ONLY, never run in CI or tests (they inject a fake transport): it builds the NB-AV-03 prompt
from the real registry and catalog, asks the existing local model (NB-AV-02, loopback only) once per case and writes
{"id", "reply"} lines to a new FILE outside the repo."""
import argparse, contextlib, json, os, re, sys, tempfile  # noqa: E401
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import interpret_check, interpreter_prompt  # noqa: E402
from hass.content_model import ContentError, load_content  # noqa: E402
from hass.conversation import _checked  # noqa: E402
from hass.interpreter_local import LocalInterpreter  # noqa: E402
from hass.ops import load_registry  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CASES = REPO / "hass" / "tests" / "fixtures" / "interpreter-eval.jsonl"
CASE_COUNT, ID_RE, NOTE_KEY = 63, re.compile(r"[A-Za-z0-9_-]{1,16}"), "_note"
CLAIM_ARGS = frozenset({"organic", "producerKey"})  # an extra arg the case did not expect fails only for these


class EvalError(Exception): """An input the scorer refuses (exit 2); the message names a line number, never content."""


def _rows(path, label):
    try:
        lines = Path(path).read_text("utf-8").split("\n")  # not splitlines: U+2028 is not a line end
    except (OSError, UnicodeDecodeError):
        raise EvalError(f"{label}: unreadable") from None
    for n, line in ((n, text) for n, text in enumerate(lines, 1) if text.strip()):
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):
            raise EvalError(f"{label} line {n}: not valid JSON") from None
        if not isinstance(row, dict): raise EvalError(f"{label} line {n}: not a JSON object")
        yield n, row


def _id(row, n, label, seen):
    ident = row.get("id")
    if not (isinstance(ident, str) and ID_RE.fullmatch(ident)): raise EvalError(f"{label} line {n}: bad id")
    if ident in seen: raise EvalError(f"{label} line {n}: duplicate id")
    seen.add(ident)
    return ident


def _expect_ok(expect) -> bool:
    if expect in ({"question": True}, {"unsupported": True}): return True
    if not (isinstance(expect, dict) and set(expect) == {"ops", "revises"}): return False
    return (isinstance(expect["ops"], list) and bool(expect["ops"]) and isinstance(expect["revises"], (str, type(None)))
            and all(isinstance(c, dict) and set(c) == {"op", "args"} and isinstance(c["op"], str)
                    and isinstance(c["args"], dict) for c in expect["ops"]))


def _pending_codes(pending, n) -> set:  # each a 1-16 char str without whitespace or control characters, none repeated
    codes = [p.get("code") for p in pending]
    if not all(isinstance(c, str) and 1 <= len(c) <= 16 and c.isprintable() and " " not in c for c in codes):
        raise EvalError(f"cases line {n}: bad pending code")
    if len(set(codes)) != len(codes): raise EvalError(f"cases line {n}: repeated pending code")
    return set(codes)


def _notes_ok(notes) -> bool:  # AV1102-10: optional saved notes, at most 20 {"key", "text"} string objects
    return (isinstance(notes, list) and len(notes) <= 20 and all(isinstance(x, dict) and set(x) == {"key", "text"}
            and isinstance(x["key"], str) and isinstance(x["text"], str) for x in notes))


def load_cases(path) -> list:
    cases, seen = [], set()
    for n, row in _rows(path, "cases"):
        _id(row, n, "cases", seen)
        if not (set(row) - {"notes"} == {"id", "text", "pending", "expect"} and isinstance(row["text"], str)
                and isinstance(row["pending"], list) and all(isinstance(p, dict) for p in row["pending"])
                and _expect_ok(row["expect"])):
            raise EvalError(f"cases line {n}: not a case")
        if "notes" in row and not _notes_ok(row["notes"]): raise EvalError(f"cases line {n}: bad notes")
        codes, expect, most = _pending_codes(row["pending"], n), row["expect"], interpret_check.MAX_OPS
        if "ops" in expect and expect["revises"] not in (None, *codes):
            raise EvalError(f"cases line {n}: revises names no pending draft")
        if len(expect.get("ops", ())) > most: raise EvalError(f"cases line {n}: more than {most} expected ops")
        cases.append(row)
    if len(cases) != CASE_COUNT: raise EvalError(f"cases: {len(cases)} cases, expected {CASE_COUNT}")
    return cases


def load_replies(path) -> dict:
    replies, seen = {}, set()
    for n, row in _rows(path, "replies"):
        if set(row) == {NOTE_KEY}: continue  # the synthetic-fixture label line
        if set(row) != {"id", "reply"}: raise EvalError(f"replies line {n}: not a reply")
        replies[_id(row, n, "replies", seen)] = row["reply"]
    return replies


def _kind(r) -> str: return "ops" if "ops" in r else "question" if "question" in r else "unsupported"


def _why(case, reply, registry):
    """None when the reply, after the Conversation checks, matches the case; else a short reason without text."""
    got = interpret_check.check(_checked(reply), registry, {p.get("code") for p in case["pending"]})
    expect, same = case["expect"], lambda a, b: json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    if _kind(got) != _kind(expect): return f"expected {_kind(expect)}, got {_kind(got)}"
    if "ops" not in expect: return None
    names, wanted = [c["op"] for c in got["ops"]], [c["op"] for c in expect["ops"]]
    if names != wanted: return f"ops {','.join(names)} but expected {','.join(wanted)}"
    for n, (have, call) in enumerate(zip(got["ops"], expect["ops"]), 1):
        for name, value in call["args"].items():
            if name not in have["args"]: return f"op {n} {call['op']}: missing arg {name}"
            if not same(have["args"][name], value): return f"op {n} {call['op']}: arg {name} differs"  # true is not 1
        claims = sorted((set(have["args"]) & CLAIM_ARGS) - set(call["args"]))
        if claims: return f"op {n} {call['op']}: unexpected claim arg {claims[0]}"
    return None if got["revises"] == expect["revises"] else "revises differs"


def score(cases, replies, registry) -> dict:
    """``cases`` from load_cases, ``replies`` id -> recorded reply, ``registry`` name -> Op."""
    whys = {c["id"]: _why(c, replies[c["id"]], registry) for c in cases if c["id"] in replies}
    failed = [{"id": ident, "why": why} for ident, why in whys.items() if why]
    return {"cases": len(cases), "passed": len(whys) - len(failed), "failed": failed,
            "missing": [c["id"] for c in cases if c["id"] not in replies],
            "extra": sorted(set(replies) - {c["id"] for c in cases})}


def live(cases, url, model, out, transport=None, registry=None, content=None) -> dict:
    """Record one fresh reply per case into a new file ``out`` outside the repository (operator only);
    the replies file is created 0600 and only when complete."""
    target = Path(out).expanduser().resolve()
    if target == REPO or REPO in target.parents: raise EvalError("--out must be outside the repository")
    if os.path.lexists(Path(out).expanduser()) or target.exists(): raise EvalError("--out already exists")
    try:
        prompt = interpreter_prompt.build(registry or load_registry(), content or load_content())
        model_call = LocalInterpreter(url, model, prompt, transport=transport)
    except (ContentError, ValueError) as exc:
        raise EvalError(str(exc)) from None
    notes = lambda c: {"notes": c["notes"]} if c.get("notes") else {}  # noqa: E731 - AV1102-10: only when it has some
    rows = [{"id": c["id"], "reply": model_call.interpret(c["text"], c["pending"], **notes(c)),
             "failed": model_call.last_error} for c in cases]
    tmp = None
    try:  # a private temp file beside the target (0600 by construction), linked into place only when complete
        fd, tmp = tempfile.mkstemp(prefix=".interpreter-eval-", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps({"id": r["id"], "reply": r["reply"]}) + "\n" for r in rows)  # ASCII lines
            fh.flush()
            os.fsync(fh.fileno())
        os.link(tmp, target)  # never replaces a file another writer made meanwhile
    except FileExistsError:
        raise EvalError("--out already exists") from None
    except OSError:
        raise EvalError("--out could not be created") from None
    finally:
        if tmp:
            with contextlib.suppress(OSError): os.unlink(tmp)
    return {"recorded": len(rows), "failedCalls": sum(r["failed"] is not None for r in rows)}


def main(argv=None, transport=None) -> int:
    parser = argparse.ArgumentParser(description="NB-AV-04 interpreter eval: offline scorer; --live is operator only")
    parser.add_argument("command", nargs="?", choices=("score",))
    parser.add_argument("--cases", default=str(CASES))
    parser.add_argument("--live", action="store_true", help="operator only: record replies from the local model")
    for flag in ("--replies", "--url", "--model", "--out"): parser.add_argument(flag)
    args = parser.parse_args(argv)
    if not (args.live and not args.command and args.url and args.model and args.out
            or not args.live and args.command == "score" and args.replies):
        parser.error("use: score --replies R [--cases C], or --live --url U --model M --out FILE [--cases C]")
    try:
        cases = load_cases(args.cases)
        summary = (live(cases, args.url, args.model, args.out, transport=transport) if args.live
                   else score(cases, load_replies(args.replies), load_registry()))
    except EvalError as exc:
        print(f"interpreter_eval: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
