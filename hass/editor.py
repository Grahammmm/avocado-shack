"""Hass private typed editing service (H02): drafts, revision hash, single writer.

    python3 hass/editor.py init --state DIR --worktree WT | prepare REQUEST.json
    python3 hass/editor.py apply CHANGE_ID --hash DRAFT_HASH | show CHANGE_ID | recover | ops
prepare turns typed ops into a draft bound to the content revision; apply (internal caller only) takes the writer
lock, re-checks worktree and revision, writes only hass/content and generated site files, runs the H01 checks and
commits with a sign-off. No listener, no push. State: --state DIR or HASS_STATE_DIR. Output: one JSON object.
"""
from __future__ import annotations

import argparse, contextlib, copy, fcntl, hashlib, json, os, re, subprocess, sys  # noqa: E401
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import migration_check, sitegen  # noqa: E402
from hass.content_model import REPO_ROOT, ContentError, load_and_validate, validate  # noqa: E402
from hass.ops import (  # noqa: E402
    NeedsDetails, NotFound, OpContext, Refused, check_args, has_control_chars, load_registry)

CONTENT_PATHS = tuple(f"hass/content/{n}.json" for n in ("products", "makers", "community", "store"))
REVISION_PATHS = tuple(sorted(CONTENT_PATHS + ("hass/templates/index.html", "hass/templates/hike/index.html")))
GENERATED_PATHS = tuple(sitegen.SITE_PREFIX + n for n in (
    "catalog-products.js", "producers.js", "producers.json", "community.json", "index.html", "hike/index.html"))
OWNED_PATHS = CONTENT_PATHS + GENERATED_PATHS
COLLECTION_FILE = dict(products="products", makers="makers", events="community", routeIdeas="community", store="store")
MAX_REQUEST, MAX_OPS = 64 * 1024, 20
CHANGE_ID_RE = re.compile(r"chg-[0-9a-f]{12}")

class UnsafeState(Exception):
    """The state dir is missing, shared, foreign-owned or inside a checkout (CLI exit 2)."""

def content_revision(root) -> str:
    digest = hashlib.sha256()
    for rel in REVISION_PATHS:
        data = (Path(root) / rel).read_bytes()
        digest.update(rel.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    return "sha256:" + digest.hexdigest()

def _now(now=None) -> str:
    return (now if now is not None else datetime.now(timezone.utc)).isoformat()

def _git(wt, *args):
    return subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True)

def _out(wt, *args) -> str:
    return _git(wt, *args).stdout.strip()

def _read(path: Path):
    return json.loads(path.read_text("utf-8"))

def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(mode=0o700, exist_ok=True)
    data = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    sitegen.write_files({path.name: data}, path.parent)
    os.chmod(path, 0o600)

def _common_dir(wt: Path) -> Path:
    return (wt / _out(wt, "rev-parse", "--git-common-dir")).resolve()

def open_state(state=None, worktree=None) -> Path:
    raw = state or os.environ.get("HASS_STATE_DIR")
    if not raw: raise UnsafeState("a state dir is required (--state DIR or HASS_STATE_DIR)")
    path = Path(raw).resolve()
    if not path.exists(): path.mkdir(mode=0o700, parents=True)
    st = path.stat()
    if not path.is_dir() or st.st_uid != os.getuid(): raise UnsafeState("state dir must be owned by the current user")
    if st.st_mode & 0o077: raise UnsafeState("state dir must not be group/other accessible (use mode 0700)")
    roots = [REPO_ROOT.resolve()]
    if worktree is not None:
        wt = Path(worktree).resolve()
        roots += [wt, _common_dir(wt).parent] if _git(wt, "rev-parse").returncode == 0 else [wt]
    if any(path == root or root in path.parents for root in roots):
        raise UnsafeState("state dir must lie outside the repository and the writer worktree")
    return path

def _load(state):
    sdir = open_state(state)
    if not (sdir / "config.json").is_file(): raise UnsafeState("state dir is not initialised; run init first")
    cfg = _read(sdir / "config.json")
    open_state(str(sdir), cfg["worktree"])
    return sdir, cfg, Path(cfg["worktree"])

def worktree_problems(wt: Path) -> list[str]:
    """Fail-closed writer preconditions: linked worktree, named non-main branch, clean, identity configured."""
    wt = Path(wt)
    top = _git(wt, "rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != wt.resolve() or not (wt / "hass/content").is_dir():
        return ["writer worktree is not the top of a Hass Git checkout"]
    if Path(_out(wt, "rev-parse", "--absolute-git-dir")).resolve() == _common_dir(wt):
        return ["the main checkout is refused; use a linked writer worktree"]
    branch = _git(wt, "symbolic-ref", "-q", "--short", "HEAD")
    problems = ["detached HEAD is refused"] if branch.returncode else \
        ["branch main is refused"] if branch.stdout.strip() == "main" else []
    if _out(wt, "status", "--porcelain"): problems.append("writer worktree has uncommitted changes")
    problems += [f"git {key} is not configured" for key in ("user.name", "user.email") if not _out(wt, "config", key)]
    return problems

def init(state, worktree) -> dict:
    wt = Path(worktree).resolve()
    sdir = open_state(state, wt)
    problems = worktree_problems(wt)
    if problems: return {"result": "refused", "problems": problems}
    _write_json(sdir / "config.json", {"worktree": str(wt), "settings": {}})
    return {"result": "ok", "worktree": str(wt)}

def _parse_request(request):
    raw = request if isinstance(request, (bytes, str)) else json.dumps(request, ensure_ascii=False)
    raw = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(raw) > MAX_REQUEST: return None, ["request is larger than 64 KiB"]
    try:
        doc = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None, ["request is not valid JSON"]
    if not isinstance(doc, dict) or set(doc) != {"ops"}: return None, ['request must be {"ops": [...]} only']
    ops = doc["ops"]
    if not isinstance(ops, list) or not 1 <= len(ops) <= MAX_OPS:
        return None, [f"ops must be a list of 1-{MAX_OPS} operations"]
    if has_control_chars(doc): return None, ["control characters are not allowed"]
    return ops, [f'ops[{i}]: must be {{"op": name, "args": {{...}}}}' for i, call in enumerate(ops)
                 if not isinstance(call, dict) or set(call) != {"op", "args"} or not isinstance(call["op"], str)
                 or not isinstance(call["args"], dict)]

def _serialize(content, name: str) -> bytes:
    doc = {"products": {"schemaVersion": 1, "products": content.products},
           "makers": {"schemaVersion": 1, "makers": content.makers},
           "community": {"schemaVersion": 1, **content.community}, "store": content.store}[name]
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

def _compute(ops, wt: Path, settings, registry, now) -> dict:
    site, registry = wt / "storefront-mockup", load_registry() if registry is None else registry
    content = load_and_validate(wt / "hass" / "content", site)
    problems, missing = [], []
    for i, call in enumerate(ops):
        op = registry.get(call["op"])
        found, absent = check_args(op, call["args"], content.makers, site) if op else (["unknown op"], [])
        problems += [f"ops[{i}] {call['op']!r}: {p}" for p in found]
        missing += [name for name in absent if name not in missing]
    if problems: return {"result": "invalid", "problems": problems}
    if missing:
        return {"result": "needs-details", "missing": missing, "question": "Please provide: " + ", ".join(missing)}
    base, new = content_revision(wt), copy.deepcopy(content)
    ctx = OpContext(now or datetime.now(timezone.utc), site, MappingProxyType(dict(settings)))
    records, summary = [], []
    for call in ops:
        out = registry[call["op"]].apply(new, copy.deepcopy(call["args"]), ctx)
        if isinstance(out, NeedsDetails):
            return {"result": "needs-details", "missing": list(out.missing), "question": out.question}
        if isinstance(out, NotFound): return {"result": "not-found", "key": out.key}
        if isinstance(out, Refused): return {"result": "refused", "reason": out.reason}
        records += [asdict(t) for t in out]
        summary.append(f"{call['op']}: " + (", ".join(f"{t.collection}/{t.key}" for t in out) or "no records"))
    validate(new, site)
    files = sitegen.render(new, wt / "hass" / "templates")
    generated = sitegen.diff_paths(files, wt)
    names = sorted({COLLECTION_FILE[r["collection"]] for r in records})
    writes = {f"hass/content/{n}.json": _serialize(new, n) for n in names}
    writes = {p: data for p, data in writes.items() if (wt / p).read_bytes() != data}
    writes.update({p: files[p] for p in generated})
    if not writes: return {"result": "refused", "reason": "the operations change nothing"}
    return {"result": "ok", "base": base, "records": records, "generated": generated,
            "warnings": list(ctx.warnings), "summary": summary, "writes": writes}

def prepare(request, *, state=None, registry=None, now=None) -> dict:
    sdir, cfg, wt = _load(state)
    ops, problems = _parse_request(request)
    if problems: return {"result": "invalid", "problems": problems}
    try:
        out = _compute(ops, wt, cfg.get("settings", {}), registry, now)
    except ContentError as exc:
        return {"result": "invalid", "problems": exc.problems}
    if out["result"] != "ok": return out
    core = json.dumps({"base": out["base"], "ops": ops}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    draft_hash = "sha256:" + hashlib.sha256(core.encode("utf-8")).hexdigest()
    change_id = "chg-" + draft_hash[7:19]
    path = sdir / "drafts" / f"{change_id}.json"
    if path.is_file() and _read(path).get("draft_hash") == draft_hash: return {"result": "ok", "draft": _read(path)}
    draft = {"change_id": change_id, "draft_hash": draft_hash, "base": out["base"], "ops": ops,
             "records": out["records"], "generated": out["generated"], "warnings": out["warnings"],
             "created_at": _now(now)}
    _write_json(path, draft)
    return {"result": "ok", "draft": draft}

@contextlib.contextmanager
def _writer_lock(sdir: Path):
    fd = os.open(sdir / "writer.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)

def _recover_locked(sdir: Path, wt: Path, now) -> list[dict]:
    """Resolve every journal: committed -> applied; HEAD still at base -> restore and failed. Never re-apply."""
    done = []
    for jpath in sorted((sdir / "journal").glob("chg-*.json")):
        cid, journal, head = jpath.stem, _read(jpath), _out(wt, "rev-parse", "HEAD")
        draft = _read(sdir / "drafts" / f"{cid}.json") if (sdir / "drafts" / f"{cid}.json").is_file() else {}
        if CHANGE_ID_RE.fullmatch(cid) and _out(wt, "log", "-1", "--format=%s") == f"hass content: {cid}":
            rec = {"state": "applied", "change_id": cid, "commit": head, "revision": content_revision(wt),
                   "recovered": True, "applied_at": _now(now), **{k: draft.get(k) for k in ("base", "records", "generated")}}
        elif CHANGE_ID_RE.fullmatch(cid) and head == journal.get("base_commit"):
            _git(wt, "checkout", "HEAD", "--", *OWNED_PATHS)
            rec = {"state": "failed", "change_id": cid, "problems": ["interrupted; needs a new approval"],
                   "failed_at": _now(now)}
        else:
            done.append({"change_id": cid, "state": "unresolved"})
            continue
        _write_json(sdir / "changes" / f"{cid}.json", rec)
        jpath.unlink()
        done.append({"change_id": cid, "state": rec["state"]})
    return done

def recover(*, state=None, now=None) -> dict:
    sdir, _cfg, wt = _load(state)
    with _writer_lock(sdir) as held:
        return {"result": "ok", "recovered": _recover_locked(sdir, wt, now)} if held else {"result": "busy"}

def _post_checks(wt: Path) -> list[str]:
    try:
        content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
        stale = sitegen.diff_paths(sitegen.render(content, wt / "hass" / "templates"), wt)
    except ContentError as exc:
        return list(exc.problems)
    return [f"generated file out of date: {p}" for p in stale] + migration_check.run_checks(wt)[0]

def apply(change_id, draft_hash, *, state=None, registry=None, now=None) -> dict:
    sdir, cfg, wt = _load(state)
    if not CHANGE_ID_RE.fullmatch(str(change_id)): return {"result": "invalid", "problems": ["malformed change id"]}
    with _writer_lock(sdir) as held:
        if not held: return {"result": "busy"}
        if any(r["state"] == "unresolved" for r in _recover_locked(sdir, wt, now)):
            return {"result": "refused", "problems": ["an interrupted change needs reconciliation"]}
        return _apply_locked(sdir, cfg, wt, change_id, draft_hash, registry, now)

def _apply_locked(sdir, cfg, wt, change_id, draft_hash, registry, now) -> dict:
    draft_path, rec_path = sdir / "drafts" / f"{change_id}.json", sdir / "changes" / f"{change_id}.json"
    if not draft_path.is_file(): return {"result": "not-found", "key": change_id}
    draft = _read(draft_path)
    if draft.get("draft_hash") != draft_hash:
        return {"result": "invalid", "problems": ["draft hash does not match the stored draft"]}
    if rec_path.is_file() and _read(rec_path).get("state") == "applied":
        return {"result": "already-applied", "change_id": change_id, "commit": _read(rec_path)["commit"]}
    problems = worktree_problems(wt)
    if problems: return {"result": "refused", "problems": problems}
    if content_revision(wt) != draft["base"]:
        return {"result": "stale", "base": draft["base"], "current": content_revision(wt)}
    try:
        out = _compute(draft["ops"], wt, cfg.get("settings", {}), registry, now)
    except ContentError as exc:
        return {"result": "invalid", "problems": exc.problems}
    if out["result"] != "ok" or out["records"] != draft["records"] or out["generated"] != draft["generated"]:
        return {"result": "stale", "problems": ["re-running the operations gave a different result"]}
    paths, journal = sorted(out["writes"]), sdir / "journal" / f"{change_id}.json"
    _write_json(journal, {"phase": "writing", "change_id": change_id, "paths": paths,
                          "base_commit": _out(wt, "rev-parse", "HEAD")})
    sitegen.write_files(out["writes"], wt)
    problems = _post_checks(wt)
    if not problems:
        _git(wt, "add", "--", *paths)
        message = ["-m", f"hass content: {change_id}", "-m", "\n".join(out["summary"])]
        if _git(wt, "commit", "-q", "-s", *message).returncode: problems = ["git commit failed"]
    if problems:
        _git(wt, "checkout", "HEAD", "--", *OWNED_PATHS)
        _write_json(rec_path, {"state": "failed", "change_id": change_id, "problems": problems, "failed_at": _now(now)})
        journal.unlink()
        return {"result": "failed", "problems": problems}
    rec = {"state": "applied", "change_id": change_id, "commit": _out(wt, "rev-parse", "HEAD"), "applied_at": _now(now),
           "revision": content_revision(wt), **{k: draft[k] for k in ("base", "records", "generated")}}
    _write_json(rec_path, rec)
    journal.unlink()
    return {"result": "applied", **rec}

def show(change_id, *, state=None) -> dict:
    sdir, _cfg, _wt = _load(state)
    if not CHANGE_ID_RE.fullmatch(str(change_id)): return {"result": "invalid", "problems": ["malformed change id"]}
    for kind in ("changes", "drafts"):
        if (sdir / kind / f"{change_id}.json").is_file():
            return {"result": "ok", kind[:-1]: _read(sdir / kind / f"{change_id}.json")}
    return {"result": "not-found", "key": change_id}

def list_ops(registry=None) -> dict:
    registry = load_registry() if registry is None else registry
    return {"result": "ok", "ops": {name: {arg: asdict(spec) for arg, spec in op.args.items()}
                                    for name, op in sorted(registry.items())}}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/editor.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state", help="private state dir (default: HASS_STATE_DIR)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, params in (("init", ["--worktree"]), ("prepare", ["request"]), ("apply", ["change_id", "--hash"]),
                         ("show", ["change_id"]), ("recover", []), ("ops", [])):
        cmd = sub.add_parser(name, parents=[common])
        for param in params:
            cmd.add_argument(param, **({"required": True} if param.startswith("--") else {}))
    args = parser.parse_args(argv)
    commands = {"ops": lambda: list_ops(), "init": lambda: init(args.state, args.worktree),
                "prepare": lambda: prepare(Path(args.request).read_bytes(), state=args.state),
                "apply": lambda: apply(args.change_id, args.hash, state=args.state),
                "show": lambda: show(args.change_id, state=args.state), "recover": lambda: recover(state=args.state)}
    try:
        out = commands[args.cmd]()
    except UnsafeState as exc:
        print(json.dumps({"result": "unsafe-state", "problems": [str(exc)]}))
        return 2
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0 if out["result"] in ("ok", "applied", "already-applied") else 1

if __name__ == "__main__":
    sys.exit(main())
