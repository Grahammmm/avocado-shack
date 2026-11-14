#!/usr/bin/env python3
"""HASS-CLOVER-2: the operator's Clover commands. READ ONLY. Each takes --host host.json and prints ONE JSON line.

  check   loads the token (ONLY through hass/clover/credential.py) and makes TWO live read-only GETs through the client's allow-list, pacing
          and the real HTTPS transport: the merchant's basic record, and the first page of items with limit=1. It prints redacted facts:
          the HTTP status class of each call, the item count if Clover reports one, elapsed ms, the configured merchant id, and booleans
          (tokenFileOk, tokenAccepted, merchantMatches). It writes nothing.
  sync    pulls every item and stock record into the PRIVATE cache <state>/clover/cache.sqlite3 (folder 0700, file 0600) with paging,
          pacing, retries and a backoff between failing runs. The hass-clover-sync.timer runs it every 15 minutes. --force ignores the backoff.
  status  the cache facts (as of, item count, last result, failures) and the till they belong to (environment, merchantId); no
          network, no token. A cache of another till, or with no identity, prints result "identity" (HASS-CLOVER-1-FIX-2).

  report stock|mismatch [--out DIR] (or report --all) writes private local Markdown files from the cache only.
          No token or network. Stdout remains one redacted JSON status line; details stay in local files.

Exit 0 ok (sync: also "skipped" by the backoff), 1 Clover failed or an unexpected error (class name only), 2 not configured, config,
state, cache or token refused. Output never holds a header, the token, a response body, an item name, a price, a path, or any customer
or sales data. The live `check` and `sync` are run by the operator after review and merge (docs/hass/CLOVER.md, "Go live: read-only").
"""
import argparse
import json
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path[0] = str(Path(__file__).resolve().parents[2])   # run as a file: the repo root, never this folder (its module names are short)

from hass.clover import cache, client as cl, credential, sync as syncmod  # noqa: E402
from hass.clover.config import ConfigProblem, from_settings  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


class Stop(Exception):
    def __init__(self, out, code=2):
        super().__init__(out.get("result"))
        self.out, self.code = out, code


def _now():
    return datetime.now(timezone.utc)


def _status_class(exc):
    status = getattr(exc, "status", None)
    if isinstance(exc, cl.CloverRefused):
        return "refused"
    if type(status) is int and 100 <= status <= 599:
        return f"{status // 100}xx"
    return "unreachable"


def _setup(host_path):
    """(clover config, state Path) from host.json, or Stop. Validation is hass/host.py's load_host (field names only)."""
    from hass import host   # lazy: host.py imports the whole conversation stack
    try:
        cfg = host.load_host(host_path)
    except host.HostConfigError as exc:
        raise Stop({"result": "config", "fields": exc.fields}) from None
    if cfg.get("clover") is None:
        raise Stop({"result": "not-configured"})
    try:
        clover = from_settings(cfg["clover"])
    except ConfigProblem as exc:   # load_host already checked; kept so this module never trusts a caller
        raise Stop({"result": "config", "fields": [f"clover.{f}" for f in exc.fields]}) from None
    return clover, _state_dir(cfg["state"])


def _state_dir(raw):
    """The Hass state folder: an existing folder of this user, mode 0700-ish, outside the repository (so the cache is never in git)."""
    try:
        path = Path(raw).resolve()
        st = os.stat(path)
    except (OSError, ValueError):
        raise Stop({"result": "state", "problem": "missing"}) from None
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise Stop({"result": "state", "problem": "unsafe"})
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise Stop({"result": "state", "problem": "inside-repo"})
    return path


def _token(clover):
    try:
        return credential.load_token(clover.token_file)
    except credential.CredentialError as exc:
        raise Stop({"result": "token", "problem": exc.reason, "tokenFileOk": False}) from None


def _client(clover, token, transport, sleep, monotonic):
    if transport is None:
        from hass.clover.transport import UrllibTransport
        transport = UrllibTransport()
    return cl.CloverClient(clover.merchant_id, token, transport, clover.environment, sleep=sleep, monotonic=monotonic)


def check(args, transport=None, sleep=time.sleep, monotonic=time.monotonic):
    clover, _ = _setup(args.host)
    token = _token(clover)
    client = _client(clover, token, transport, sleep, monotonic)
    out = {"result": "failed", "environment": clover.environment, "merchantId": clover.merchant_id, "readOnly": True, "tokenFileOk": True}
    start, refused_key = monotonic(), False
    try:
        doc = client.get_merchant()
        out["merchant"], out["merchantMatches"] = "2xx", doc.get("id") == clover.merchant_id
    except cl.CloverError as exc:
        out["merchant"], out["merchantMatches"] = _status_class(exc), None
        refused_key = isinstance(exc, cl.CloverAuthError)
    try:
        page = client.first_items(1)
        count = page.get("count", page.get("total"))
        out["items"], out["itemsOnPage"] = "2xx", len(page["elements"])
        out["itemCount"] = count if type(count) is int and count >= 0 else None
    except cl.CloverError as exc:
        out["items"], out["itemsOnPage"], out["itemCount"] = _status_class(exc), None, None
        refused_key = refused_key or isinstance(exc, cl.CloverAuthError)
    out["elapsedMs"] = int(round((monotonic() - start) * 1000))
    # True: Clover answered at least one read with the token; False: Clover said 401 (bad key or no inventory permission); None: no answer
    out["tokenAccepted"] = True if "2xx" in (out["merchant"], out["items"]) else False if refused_key else None
    if out["items"] == "2xx":
        out["result"] = "ok"
    return out, 0 if out["result"] == "ok" else 1


FAILURES = ((cl.CloverAuthError, "refused-key"), (cl.RateLimited, "rate-limited"), (cl.CloverUnavailable, "unreachable"),
            (cl.CloverError, "clover-error"))


def sync(args, transport=None, sleep=time.sleep, monotonic=time.monotonic, clock=_now):
    clover, state = _setup(args.host)
    identity = cache.identity_of(clover)
    now = clock()
    try:
        before = cache.facts(state, identity)
    except cache.CacheUnsafe:
        raise Stop({"result": "cache", "problem": "unsafe"}) from None
    if before is not None and before.get("refused"):
        before = None          # another till's (or an unidentified) backoff is never obeyed; this till's first pull replaces it
    nxt = cache._parse_iso((before or {}).get("nextAttempt"))
    if not args.force and nxt is not None and now < nxt:
        return {"result": "skipped", "reason": "backoff", "nextAttempt": before["nextAttempt"], "failures": before["failures"]}, 0
    try:
        token = _token(clover)
    except Stop as stop:
        stop.out["failures"] = cache.record_failure(state, "token", now, identity=identity)
        raise
    client = _client(clover, token, transport, sleep, monotonic)
    start = monotonic()
    try:
        rows, skipped = syncmod.pull(client)
    except cl.CloverError as exc:
        word = next(w for kind, w in FAILURES if isinstance(exc, kind))
        failures = cache.record_failure(state, word, clock(), getattr(exc, "retry_after", None), identity=identity)
        return {"result": word, "status": _status_class(exc), "failures": failures}, 1
    done = clock()
    cache.write_items(state, rows, done, identity)
    return {"result": "ok", "items": len(rows), "counted": sum(1 for r in rows if r["stock"] is not None), "skipped": skipped,
            "asOf": cache._iso(done), "elapsedMs": int(round((monotonic() - start) * 1000))}, 0


def status(args):
    """The cache facts for the configured till, with its identity (environment, merchantId). A cache of another till, or one with no
    identity, is {"result": "identity"} with the configured identity and what the cache says it holds (cacheEnvironment/cacheMerchantId)."""
    clover, state = _setup(args.host)
    try:
        facts = cache.facts(state, cache.identity_of(clover))
    except cache.CacheUnsafe:
        raise Stop({"result": "cache", "problem": "unsafe"}) from None
    if facts and facts.get("refused"):
        return {"result": facts["refused"], "environment": clover.environment, "merchantId": clover.merchant_id,
                "cacheEnvironment": facts["environment"], "cacheMerchantId": facts["merchantId"]}, 0
    return ({"result": "ok", **facts} if facts else {"result": "no-cache"}), 0


def report(args, clock=_now):
    """Cache only: no client or token loading; stdout contains status/counts only."""
    from hass import editor
    from hass.clover import reports
    clover, state = _setup(args.host)
    snapshot, reachable = cache.read(state, cache.identity_of(clover))
    if snapshot is None:
        raise Stop({"result": "no-cache"})
    worktree = editor._load(str(state))[2] if args.out or args.all or args.kind == "mismatch" else None
    if args.out:
        out = Path(args.out).absolute()
        resolved = out.resolve()
        if any(resolved == root or root in resolved.parents for root in (REPO_ROOT, worktree.resolve())):
            raise Stop({"result": "report", "problem": "inside-repo"})
    now = clock()
    kinds = reports.KINDS if args.all else (args.kind,)
    if not args.all and args.kind is None or args.all and args.kind is not None:
        raise Stop({"result": "report", "problem": "choose-kind-or-all"})
    prepared = []
    for kind in kinds:
        if kind == "stock":
            prepared.append(reports.low_stock(snapshot, clover.low_stock_threshold))
        else:
            content, links = reports.read_inputs(state, worktree)
            prepared.append(reports.till_vs_site(snapshot, content, links))
    for doc in prepared:
        reports.write_report(state, doc, now, reachable, args.out)
    return {"result": "ok", "reports": len(prepared), "asOf": cache._iso(snapshot.fetched_at)}, 0


def main(argv=None, *, transport=None, sleep=time.sleep, monotonic=time.monotonic, clock=_now):
    ap = argparse.ArgumentParser(prog="hass/clover/cli.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "sync", "status"):
        p = sub.add_parser(name)
        p.add_argument("--host", required=True)
        if name == "sync":
            p.add_argument("--force", action="store_true")
    p = sub.add_parser("report")
    p.add_argument("kind", nargs="?", choices=("stock", "mismatch"))
    p.add_argument("--all", action="store_true")
    p.add_argument("--host", required=True)
    p.add_argument("--out")
    args = ap.parse_args(argv)
    os.umask(0o077)
    try:
        if args.cmd == "check":
            out, code = check(args, transport, sleep, monotonic)
        elif args.cmd == "sync":
            out, code = sync(args, transport, sleep, monotonic, clock)
        elif args.cmd == "report":
            out, code = report(args, clock)
        else:
            out, code = status(args)
    except Stop as stop:
        out, code = stop.out, stop.code
    except Exception as exc:  # noqa: BLE001 - the class name only: a foreign message could carry a path or a value
        out, code = {"result": "error", "error": type(exc).__name__}, 1
    print(json.dumps(out, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
