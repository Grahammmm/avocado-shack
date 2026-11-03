"""FAV-02 (H10): score LabelReader on a label-photo case set. `score --cases C --replies R` prints one JSON summary of
right / wrong / none per field (name, brand, category), case ids only, never a label value or photo name. Each reply is
the model's JSON object (or {} for a failed read), put through label_reader.keep with the catalog categories. Exit 0
when every case was scored; 2 for an unreadable file, malformed line, duplicate id, a reply for no case, a case with no
reply, U+2028/2029 in a value, or an expected value that is neither string nor null. `--live --url U --model M --photos
DIR --out FILE` is OPERATOR ONLY, never run in CI or tests (they inject a fake transport): it asks the loopback vision
model once per photo and stores the RAW reply ({"id", "reply"} lines) in a new 0600 FILE outside the repo. No label
photo is committed; cases name a file only."""
import argparse, contextlib, json, os, stat, sys, tempfile  # noqa: E401
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import claims  # noqa: E402
from hass.content_model import ContentError, load_and_validate  # noqa: E402
from hass.interpreter_eval import EvalError, _id, _rows  # noqa: E402
from hass.interpreter_local import _Failed  # noqa: E402
from hass.label_reader import FIELDS, LabelReader, keep  # noqa: E402

REPO, MAX_PHOTO, SEPARATORS = Path(__file__).resolve().parents[1], 12_000_000, "\u2028\u2029\u0085"
CASES = REPO / "hass" / "tests" / "fixtures" / "label-eval.jsonl"


def _rows_checked(path, label):
    for n, row in _rows(path, label):
        try:
            if any(c in SEPARATORS for c in json.dumps(row, ensure_ascii=False)): raise EvalError(f"{label} line {n}: line separator")
        except RecursionError:
            raise EvalError(f"{label} line {n}: not valid JSON") from None
        yield n, row


def load_cases(path) -> list:
    cases, seen = [], set()
    for n, row in _rows_checked(path, "cases"):
        _id(row, n, "cases", seen)
        photo, expected = row.get("photo"), row.get("expected")
        if not (set(row) == {"id", "photo", "expected"} and isinstance(photo, str) and photo not in ("", ".", "..")
                and not set(photo) & set("/\\\x00") and isinstance(expected, dict) and set(expected) == set(FIELDS)):
            raise EvalError(f"cases line {n}: not a case")
        if not all(v is None or isinstance(v, str) for v in expected.values()):
            raise EvalError(f"cases line {n}: expected value is neither text nor null")
        cases.append({**row, "_line": n})
    return cases


def load_replies(path, cases) -> dict:
    """id -> reply object; a reply for no case or a case with no reply is refused naming a line."""
    replies, seen, known = {}, set(), {c["id"] for c in cases}
    for n, row in _rows_checked(path, "replies"):
        if set(row) != {"id", "reply"} or not isinstance(row["reply"], dict): raise EvalError(f"replies line {n}: not a reply")
        replies[_id(row, n, "replies", seen)] = row["reply"]
        if row["id"] not in known: raise EvalError(f"replies line {n}: no such case")
    for case in cases:
        if case["id"] not in replies: raise EvalError(f"cases line {case['_line']}: no reply")
    return replies


def catalog_categories() -> list:
    try:
        return sorted({p["category"] for p in load_and_validate().products if isinstance(p.get("category"), str)})
    except ContentError as exc:
        raise EvalError(f"catalog: {len(exc.problems)} problems") from None


def score(cases, replies, categories) -> dict:
    """``replies`` id -> recorded reply object; per field right (equal after claims.fold), wrong, or none (not kept)."""
    fields, wrong = {f: {"right": 0, "wrong": 0, "none": 0} for f in FIELDS}, {f: [] for f in FIELDS}
    for case in cases:
        found = keep(replies[case["id"]], categories)
        for field in FIELDS:
            want, got = case["expected"][field], found.get(field)
            verdict = "none" if got is None else "right" if want is not None and claims.fold(got) == claims.fold(want) else "wrong"
            fields[field][verdict] += 1
            if verdict == "wrong": wrong[field].append(case["id"])
    return {"cases": len(cases), "fields": fields, "wrongIds": wrong}


def _read_photo(folder_fd, name) -> bytes:
    """Bytes of a regular, non-link file directly in the photos folder (the open itself refuses a link)."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder_fd)
    except OSError:
        raise EvalError("a photo is missing or is a link") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PHOTO: raise EvalError("a photo is not a usable regular file")
        with os.fdopen(fd, "rb", closefd=False) as fh: return fh.read(MAX_PHOTO + 1)
    finally:
        os.close(fd)


def live(cases, url, model, photos, out, transport=None) -> dict:
    """OPERATOR ONLY, never run in CI or tests (they inject a fake transport): record the raw reply per photo."""
    target = Path(out).expanduser().resolve()
    if target == REPO or REPO in target.parents: raise EvalError("--out must be outside the repository")
    if os.path.lexists(Path(out).expanduser()) or target.exists(): raise EvalError("--out already exists")
    try:
        reader = LabelReader(url, model, transport=transport)
        folder_fd = os.open(photos, os.O_RDONLY | os.O_DIRECTORY)
    except (ValueError, OSError):
        raise EvalError("--url, --model or --photos is not usable") from None
    try:
        images = [_read_photo(folder_fd, c["photo"]) for c in cases]  # every photo is checked before anything is sent
    finally:
        os.close(folder_fd)
    rows = []
    for case, image in zip(cases, images):
        try: rows.append({"id": case["id"], "reply": reader._call(reader._label_request(image)), "failed": False})
        except _Failed: rows.append({"id": case["id"], "reply": {}, "failed": True})
    tmp = None
    try:  # a private temp file beside the target (0600 by construction), linked into place only when complete
        fd, tmp = tempfile.mkstemp(prefix=".label-eval-", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps({"id": r["id"], "reply": r["reply"]}) + "\n" for r in rows)
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
    return {"recorded": len(rows), "failedCalls": sum(r["failed"] for r in rows)}


def main(argv=None, transport=None) -> int:
    parser = argparse.ArgumentParser(description="FAV-02 label eval: offline scorer; --live is operator only")
    parser.add_argument("command", nargs="?", choices=("score",))
    parser.add_argument("--live", action="store_true", help="operator only: record replies from the loopback vision model")
    for flag in ("--cases", "--replies", "--url", "--model", "--photos", "--out"): parser.add_argument(flag)
    args = parser.parse_args(argv)
    if not (args.live and not args.command and args.url and args.model and args.photos and args.out
            or not args.live and args.command == "score" and args.replies):
        parser.error("use: score --cases C --replies R, or --live --url U --model M --photos DIR --out FILE --cases C")
    try:
        cases = load_cases(args.cases or CASES)
        summary = (live(cases, args.url, args.model, args.photos, args.out, transport=transport) if args.live
                   else score(cases, load_replies(args.replies, cases), catalog_categories()))
    except EvalError as exc:
        print(f"label_eval: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
