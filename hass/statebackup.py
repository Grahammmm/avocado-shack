"""Hass private state backup, verify and isolated restore drill (H20 prep).

    python3 hass/statebackup.py create --state DIR --out DIR [--media DIR] | verify BACKUP
                                | restore BACKUP --into DIR --worktree WT [--paused] [--media-into DIR] | list --out DIR
                                | drill BACKUP --into DIR --worktree WT [--media-into DIR]

create refuses a symlinked or odd config.json/writer.lock before anything opens it, takes the writer lock and copies a
settled state dir (config.json, drafts, changes, screenshots and consistent sqlite snapshots of inbox.sqlite3, then
conversation.sqlite3; never writer.lock, a journal, a symlink or an unknown entry) into a new private
<out>/hass-state-<UTC stamp>/ (out: an existing 0700 user dir; built aside, renamed in) and writes MANIFEST.json last.
verify re-checks every hash and mode, refuses extra entries and symlinks and runs the sqlite integrity check on both
stores; listed photo originals and sidecars must pair one-to-one and match media.originals. restore verifies first,
then builds a NEW state dir bound
to a separate drill worktree (only config.json `worktree` is rewritten). Isolation rule: nothing restores over an existing
dir or onto the recorded writer worktree (an attended operation); backups stay private (0700/0600) and outside the
repository, the worktrees and the state dir. No network, no Git writes, no deletes of source data. One JSON line out;
exit 0 ok, 1 any other result, 2 unsafe dir or usage. list (read-only): a line per hass-state-* entry, complete or not.
"""
import argparse, contextlib, ctypes, errno, hashlib, json, os, re, shutil, sqlite3, stat, sys  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import editor, media as photos  # noqa: E402
from hass.conversation import CONTROL, _iso  # noqa: E402
from hass.content_model import REPO_ROOT  # noqa: E402
from hass.editor import UnsafeState  # noqa: E402

MANIFEST, CONFIG, DB, LOCK = "MANIFEST.json", "config.json", "conversation.sqlite3", "writer.lock"
INBOX = "inbox.sqlite3"  # H16 inbound queue; snapshotted like DB
DIRS = ("drafts", "changes", "screenshots")
ORIG = "media/originals/"  # H10 photo originals <aa>/<sha>.<ext> + <aa>/<sha>.json, aa == sha[:2] (hass/media.py)
FILE_RE = re.compile(r"config\.json|conversation\.sqlite3|inbox\.sqlite3|(drafts|changes)/chg-[0-9A-Za-z_-]+\.json"
                     r"|screenshots/[0-9A-Za-z_-][0-9A-Za-z._-]*\.png"
                     r"|media/originals/(?P<aa>[0-9a-f]{2})/(?P=aa)[0-9a-f]{62}\.(json|%s)"
                     % "|".join(sorted(set(photos.EXT.values()))))
HEX_RE = re.compile(r"[0-9a-f]{64}")
ATTENDED = "restoring onto the recorded writer worktree is an attended operation"

def _read(path: Path) -> bytes:
    """Bytes of a regular file; a symlink is never followed."""
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as fh:
        return fh.read()

def _write_new(path: Path, data: bytes) -> None:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as fh:
        fh.write(data)
    os.chmod(path, 0o600)

def _copy(src: Path, dst: Path) -> None:
    _write_new(dst, _read(src))

def _rename_noreplace(src: Path, dst: Path) -> None:
    """Atomic rename that raises FileExistsError if dst exists, even as an empty dir (os.rename would replace it)."""
    libc, a, b = ctypes.CDLL(None, use_errno=True), os.fsencode(src), os.fsencode(dst)
    if hasattr(libc, "renameat2"): rc = libc.renameat2(-100, a, -100, b, 1)  # AT_FDCWD, RENAME_NOREPLACE (Linux)
    elif hasattr(libc, "renamex_np"): rc = libc.renamex_np(a, b, 4)  # RENAME_EXCL (macOS)
    else: raise OSError(errno.ENOSYS, "no atomic no-replace rename here", str(dst))
    if rc: raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(dst))  # EEXIST: FileExistsError

def _connect_ro(path: Path):
    return contextlib.closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True))

def _snapshot(src: Path, dst: Path) -> None:  # a consistent copy via the sqlite online backup API
    _write_new(dst, b"")
    with _connect_ro(src) as source, contextlib.closing(sqlite3.connect(dst)) as target:
        source.backup(target)
    os.chmod(dst, 0o600)

def _inside(path: Path, roots) -> bool:
    return any(path == root or root in path.parents for root in roots)

def _roots(wt: Path) -> list:
    """The checkout, a worktree and (if it is a Git checkout) its main checkout."""
    roots = [REPO_ROOT.resolve(), wt.resolve()]
    if editor._git(wt, "rev-parse").returncode == 0: roots.append(editor._common_dir(wt).parent)
    return roots

def _private_out(raw, roots) -> Path:
    path = Path(raw).resolve()
    if not path.is_dir(): raise UnsafeState("backup dir must already exist")
    if (st := path.stat()).st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise UnsafeState("backup dir must be owned by the current user with mode 0700")
    if _inside(path, roots):
        raise UnsafeState("backup dir must lie outside the state dir, the repository and the writer worktree")
    return path

def _scan(sdir: Path):
    """(files to copy, problems) for the known layout; symlinks and unknown entries are named, never followed."""
    files, bad = [], []
    for entry in sorted(os.scandir(sdir), key=lambda e: e.name):
        if entry.is_symlink(): bad.append(f"symlink: {entry.name}")
        elif entry.is_dir(follow_symlinks=False) and entry.name in DIRS + ("journal",):
            for sub in sorted(os.scandir(entry.path), key=lambda e: e.name):
                rel = f"{entry.name}/{sub.name}"
                if sub.is_symlink(): bad.append(f"symlink: {rel}")
                elif sub.is_file(follow_symlinks=False) and FILE_RE.fullmatch(rel): files.append(rel)
                else: bad.append(f"unknown entry: {rel}")
        elif entry.is_file(follow_symlinks=False) and entry.name in (CONFIG, DB, INBOX): files.append(entry.name)
        elif not (entry.is_file(follow_symlinks=False) and entry.name == LOCK): bad.append(f"unknown entry: {entry.name}")
    return files, bad

def _media_root(raw, roots) -> Path:  # create --media: the H10 photo store (hass/media.py)
    if os.path.islink(raw) or not os.path.isdir(raw): raise UnsafeState("media dir must be an existing dir, no symlink")
    if (st := os.lstat(raw)).st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise UnsafeState("media dir must be owned by the current user with mode 0700")
    if _inside(path := Path(raw).resolve(), roots):
        raise UnsafeState("media dir must lie outside the repository, the worktrees, the state dir and the backup dir")
    return path

def _scan_media(mroot: Path):
    """(backup rels of settled originals + sidecars, refused names, unsettled names); nothing is followed."""
    orig, pairs = mroot / "originals", {}
    bad = [f"unknown media entry: {e.name}" for e in os.scandir(mroot) if e.name != "originals" or e.is_symlink()
           or not e.is_dir()]
    subs = list(os.scandir(orig)) if orig.is_dir() and not orig.is_symlink() else []
    for entry in [s for s in subs if s.is_symlink() or not s.is_dir()] + [
            e for s in subs if s.is_dir(follow_symlinks=False) for e in os.scandir(s.path)]:
        rel = ORIG + os.path.relpath(entry.path, orig)  # media/originals/<aa>/<sha>.<ext>: the sha is rel[19:83]
        if entry.is_symlink(): bad.append(f"symlink: {rel}")
        elif entry.is_file(follow_symlinks=False) and FILE_RE.fullmatch(rel):
            pairs.setdefault(rel[19:83], []).append(rel)
        else: bad.append(f"unknown entry: {rel}")
    unsettled = [f"unsettled media: {sha[:12]}" for sha, rels in sorted(pairs.items())
                 if sorted(rel.endswith(".json") for rel in rels) != [False, True]]
    return sorted(sum(pairs.values(), [])), sorted(bad), unsettled

def create(state, out, now=None, media=None) -> dict:
    if not state or not Path(state).is_dir(): raise UnsafeState("state dir must already exist")  # open_state creates
    top = [p for p in _scan(editor.open_state(state))[1] if p.split(": ", 1)[1] in (CONFIG, LOCK)]
    if top: return {"result": "refused", "problems": top}  # before _load reads config / _writer_lock creates the lock
    sdir, cfg, wt = editor._load(state)
    dest_root = _private_out(out, _roots(wt) + [sdir])
    mroot = None if media is None else _media_root(media, _roots(wt) + [sdir, dest_root])
    with editor._writer_lock(sdir) as held, contextlib.ExitStack() as undo:
        if not held: return {"result": "busy"}
        if (journal := sdir / "journal").is_dir() and not journal.is_symlink() and any(journal.iterdir()):
            return {"result": "unsettled", "problems": ["an interrupted write is pending; run editor.py recover first"]}
        files, bad = _scan(sdir)
        mfiles, mbad, unsettled = _scan_media(mroot) if mroot else ([], [], [])
        if bad or mbad: return {"result": "refused", "problems": bad + mbad}
        if unsettled: return {"result": "unsettled", "problems": unsettled}  # a photo write may be in flight
        now = now or datetime.now(timezone.utc)
        final = dest_root / f"hass-state-{now.strftime('%Y%m%dT%H%M%SZ')}"
        if os.path.lexists(final): return {"result": "exists", "backup": str(final)}
        dest = dest_root / f".{final.name}.partial-{os.getpid()}"  # built aside (dot name), renamed to final last
        dest.mkdir(mode=0o700)
        undo.callback(shutil.rmtree, dest, ignore_errors=True)  # any failure: only the folder this call created
        os.chmod(dest, 0o700)
        hashes = {}
        for sub in ("media", ORIG) if mfiles else (): (dest / sub).mkdir(mode=0o700)
        # The inbox goes first: a row it shows `done` was handled before, so the later DB snapshot holds its effect;
        # one handled in between stays `pending` here and a later drain answers it `duplicate` (no second write).
        for rel in sorted(files + mfiles, key=lambda rel: rel != INBOX):
            (dest / rel).parent.mkdir(mode=0o700, exist_ok=True)
            src = mroot / rel[len("media/"):] if rel.startswith(ORIG) else sdir / rel
            (_snapshot if rel in (DB, INBOX) else _copy)(src, dest / rel)
            hashes[rel] = hashlib.sha256(_read(dest / rel)).hexdigest()
        doc = {"schemaVersion": 1, "createdAt": now.isoformat(), "worktree": cfg["worktree"], "files": hashes}
        if mroot: doc["media"] = {"originals": len(mfiles) // 2}
        _write_new(dest / (MANIFEST + ".tmp"), json.dumps(doc, indent=2, sort_keys=True).encode("utf-8"))
        os.replace(dest / (MANIFEST + ".tmp"), dest / MANIFEST)  # last: a backup without it is incomplete
        _rename_noreplace(dest, final)  # a final dir that appeared meanwhile (even empty) is refused, never replaced
        undo.pop_all()  # renamed in: nothing left to clean up
    extra = {"media": len(mfiles) // 2} if mroot else {}  # settled: one sidecar per original
    return {"result": "ok", "backup": str(final), "files": len(hashes), **extra}

def _manifest(bdir: Path):
    try:
        doc = json.loads(_read(bdir / MANIFEST).decode("utf-8"))
        files = doc["files"]
        valid = doc.get("schemaVersion") == 1 and isinstance(doc.get("worktree"), str) and isinstance(files, dict) \
            and CONFIG in files and all(isinstance(rel, str) and FILE_RE.fullmatch(rel) and isinstance(digest, str)
                                        and HEX_RE.fullmatch(digest) for rel, digest in files.items())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return doc if valid else None

def _intact(path: Path) -> bool:
    try:
        with _connect_ro(path) as db:
            return db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    except sqlite3.DatabaseError:
        return False

def verify(backup) -> dict:
    bdir = Path(backup).absolute()
    if bdir.is_symlink() or not bdir.is_dir(): return {"result": "corrupt", "problems": ["not a backup dir"]}
    doc = _manifest(bdir)
    if doc is None: return {"result": "corrupt", "problems": [f"{MANIFEST} missing or invalid"]}
    files, seen, problems = doc["files"], set(), []
    walkable = set(DIRS) | ({"media", ORIG[:-1]} if "media" in doc else set())  # + media/originals/<aa> below
    if bdir.stat().st_mode & 0o777 != 0o700: problems.append("mode: backup dir")
    def walk(path: Path, prefix: str) -> None:
        for entry in sorted(os.scandir(path), key=lambda e: e.name):
            rel, mode = prefix + entry.name, entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode): problems.append(f"symlink: {rel}")
            elif stat.S_ISDIR(mode) and (rel in walkable
                                         or prefix == ORIG and re.fullmatch("[0-9a-f]{2}", entry.name)):
                if mode & 0o777 != 0o700: problems.append(f"mode: {rel}")
                walk(Path(entry.path), rel + "/")
            elif not stat.S_ISREG(mode) or (rel not in files and rel != MANIFEST): problems.append(f"unlisted: {rel}")
            else:
                seen.add(rel)
                if mode & 0o777 != 0o600: problems.append(f"mode: {rel}")
    walk(bdir, "")
    for rel, digest in sorted(files.items()):
        if rel not in seen: problems.append(f"missing: {rel}")
        elif hashlib.sha256(_read(bdir / rel)).hexdigest() != digest: problems.append(f"hash mismatch: {rel}")
        elif rel in (DB, INBOX) and not _intact(bdir / rel): problems.append(f"integrity check failed: {rel}")
        elif rel.startswith(ORIG) and not rel.endswith(".json"):  # the content address and the sidecar both hold
            sha, side = rel[19:83], rel[:84] + "json"  # media/originals/<aa>/<sha>.<ext>
            if hashlib.sha256(_read(bdir / rel)).hexdigest() != sha: problems.append(f"content mismatch: {rel}")
            if not (side in seen and _sidecar_sha(bdir / side) == sha): problems.append(f"sidecar mismatch: {rel}")
    problems += _pair_problems(doc)
    return {"result": "corrupt", "problems": problems} if problems else {"result": "ok", "files": len(files)}

def _pair_problems(doc) -> list:
    """Listed media in both directions: every sha has exactly one original and one sidecar, and media.originals
    equals the number of those complete pairs (a listed orphan sidecar or original is never restored as a store)."""
    pairs, problems, complete = {}, [], 0
    for rel in doc["files"]:
        if rel.startswith(ORIG): pairs.setdefault(rel[19:83], []).append(rel)
    for _, rels in sorted(pairs.items()):
        if sorted(rel.endswith(".json") for rel in rels) == [False, True]: complete += 1
        else: problems += [f"unpaired: {rel}" for rel in sorted(rels)]
    if "media" not in doc and not pairs: return problems
    count = doc["media"].get("originals") if isinstance(doc.get("media"), dict) else None
    if type(count) is not int or count != complete: problems.append("media count mismatch")
    return problems

def _sidecar_sha(path: Path):
    try: return json.loads(_read(path).decode("utf-8")).get("sha256")
    except (OSError, ValueError, AttributeError): return None

def _pause(path: Path, now) -> str:  # restore --paused, before the dir appears; an older pause keeps its set_at
    if not path.exists(): _write_new(path, b"")
    with contextlib.closing(sqlite3.connect(path)) as db, db:
        db.execute(CONTROL)
        db.execute("INSERT OR IGNORE INTO control(name, value, set_at, provider_id) VALUES ('paused', '1', ?, "
                   "'statebackup-restore')", (_iso(now or datetime.now(timezone.utc)),))
        since = db.execute("SELECT set_at FROM control WHERE name = 'paused'").fetchone()[0]
    os.chmod(path, 0o600)
    return since

def restore(backup, into, worktree, paused=False, now=None, media_into=None) -> dict:
    checked = verify(backup)
    if checked["result"] != "ok": return {"result": "corrupt", "problems": checked["problems"]}
    bdir = Path(backup).absolute()
    doc = _manifest(bdir)
    mrels = [rel for rel in doc["files"] if rel.startswith(ORIG)]
    if os.path.lexists(into): return {"result": "refused", "problems": ["restore dir already exists; left untouched"]}
    if not worktree: return {"result": "refused", "problems": ["--worktree (a separate drill worktree) is required"]}
    if media_into is not None and (not mrels or os.path.lexists(os.path.abspath(media_into))):
        return {"result": "refused", "problems": ["media restore dir already exists; left untouched" if mrels
                                                  else "no media in backup"]}
    target, wt, recorded = Path(into).resolve(), Path(worktree).resolve(), Path(doc["worktree"]).resolve()
    if wt == recorded: return {"result": "refused", "problems": [ATTENDED]}
    if problems := editor.worktree_problems(wt, recovering=True): return {"result": "refused", "problems": problems}
    if _inside(target, _roots(wt) + [recorded, bdir.resolve()]):
        raise UnsafeState("restore dir must lie outside the backup, the repository and the worktrees")
    mtarget = None if media_into is None else Path(media_into).resolve()
    if mtarget and _inside(mtarget, _roots(wt) + [recorded, bdir.resolve(), target]):
        raise UnsafeState("media restore dir must lie outside the backup, the repository, the worktrees and the state")
    tmp = target.parent / f".{target.name}.restore-{os.getpid()}"
    mtmp = mtarget and mtarget.parent / f".{mtarget.name}.restore-{os.getpid()}"
    tmp.mkdir(mode=0o700)
    made, renamed = [tmp], False
    try:
        os.chmod(tmp, 0o700)
        if mtmp:
            mtmp.mkdir(mode=0o700)
            made.append(mtmp)
            (mtmp / "originals").mkdir(mode=0o700)
        for rel in sorted(doc["files"]):
            if rel.startswith(ORIG) and not mtmp: continue  # reported below as mediaRestored: false
            dst = mtmp / rel[len("media/"):] if rel.startswith(ORIG) else tmp / rel
            dst.parent.mkdir(mode=0o700, exist_ok=True)
            if rel != CONFIG:
                _copy(bdir / rel, dst)
                continue
            cfg = {**json.loads(_read(bdir / CONFIG).decode("utf-8")), "worktree": str(wt)}
            _write_new(tmp / CONFIG, json.dumps(cfg, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        extra = {"paused": True, "pausedSince": _pause(tmp / DB, now)} if paused else {}
        if os.path.lexists(target): raise FileExistsError(f"restore dir appeared during restore: {target}")
        os.rename(tmp, target)
        renamed = True
        if mtmp and os.path.lexists(mtarget): raise FileExistsError(f"media restore dir appeared: {mtarget}")
        if mtmp: os.rename(mtmp, mtarget)
    except BaseException:
        if renamed: os.rename(target, tmp)  # take back the state dir this call made: leave neither target
        for path in made: shutil.rmtree(path, ignore_errors=True)  # only the temp dirs this call created
        raise
    if mrels: extra.update({"mediaRestored": bool(mtarget), "media": len(mrels) // 2})
    return {"result": "ok", "state": str(target), "worktree": str(wt), "files": len(doc["files"]), **extra}

STRUCTURAL = ("state", "settings", "db-integrity", "inbox-integrity")  # a drill fails on these health checks

def drill(backup, into, worktree, media_into=None, now=None) -> dict:
    """verify, restore --paused into a NEW dir, then the read-only health check and history on it; ids/counts only."""
    checked = verify(backup)
    if checked["result"] != "ok": return {"result": "corrupt", "step": "verify", "problems": checked["problems"]}
    out = restore(backup, into, worktree, paused=True, now=now, media_into=media_into)
    if out["result"] != "ok": return {**out, "step": "restore"}
    from hass import health  # lazy: health imports this module at its top
    problems, info, unsafe = health.check(out["state"], now=now)
    ids = sorted({p["check"] for p in problems})
    try: hist = editor.history(5, state=out["state"])
    except UnsafeState: hist = {"result": "unsafe-state"}
    step = "health" if unsafe or set(ids) & set(STRUCTURAL) else None if hist.get("result") == "ok" else "history"
    return ({"result": "drill-failed", "step": step} if step else {"result": "ok"}) | {
        "state": out["state"], "worktree": out["worktree"], "files": out["files"], "paused": out["paused"],
        "health_problems": ids, "health_info": sorted({p["check"] for p in info}),
        "history": len(hist.get("history") or []), **{k: out[k] for k in ("media", "mediaRestored") if k in out}}

NAME_RE = re.compile(r"hass-state-[0-9]{8}T[0-9]{6}Z")  # create()'s folder name; the name is the UTC time
def _listed(entry):  # (manifest doc or None, problem or None); a symlink is never followed
    if entry.is_symlink(): return None, "symlink"
    if not entry.is_dir(follow_symlinks=False): return None, "not a folder"
    try: os.lstat(Path(entry.path, MANIFEST))
    except FileNotFoundError: return None, "no manifest (interrupted)"  # create() writes MANIFEST.json last
    except OSError: return None, "manifest invalid"
    return (doc := _manifest(Path(entry.path))), None if doc else "manifest invalid"

def list_backups(out):
    """list: one dict per hass-state-* entry, newest first. Read-only; no content hashing (that is verify)."""
    if not out or os.path.islink(re.sub(r"(/\.?)+$", "", out) or "/") or not os.path.isdir(out):  # 'link/' = link
        return {"result": "refused", "problems": ["--out must be a folder, not a link"]}
    rows = []
    for entry in sorted((e for e in os.scandir(out) if NAME_RE.fullmatch(e.name)), key=lambda e: e.name, reverse=True):
        doc, problem = _listed(entry)
        created = (doc or {}).get("createdAt")
        rows.append({"backup": entry.name, "createdAt": created if isinstance(created, str) else None,
                     "files": len(doc["files"]) if doc else None, "complete": doc is not None, "problem": problem})
    return rows

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/statebackup.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, params in (("create", ["--state", "--out"]), ("verify", ["backup"]), ("list", ["--out"]),
                         ("drill", ["backup", "--into", "--worktree"]),  # before restore: --paused stays restore's
                         ("restore", ["backup", "--into", "--worktree"])):
        cmd = sub.add_parser(name)
        for param in params: cmd.add_argument(param, **({"required": True} if param.startswith("--") else {}))
    cmd.add_argument("--paused", action="store_true")  # restore only (the last parser)
    cmd.add_argument("--media-into")
    sub.choices["drill"].add_argument("--media-into")
    sub.choices["create"].add_argument("--media")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "list":
            rows = list_backups(args.out)
            for row in [rows] if isinstance(rows, dict) else rows: print(json.dumps(row, ensure_ascii=False))
            return 2 if isinstance(rows, dict) else 0  # refused: --out missing or a link
        out = create(args.state, args.out, media=args.media) if args.cmd == "create" else verify(args.backup) \
            if args.cmd == "verify" else drill(args.backup, args.into, args.worktree, media_into=args.media_into) \
            if args.cmd == "drill" else restore(args.backup, args.into, args.worktree, paused=args.paused,
                                                media_into=args.media_into)
    except UnsafeState as exc:
        print(json.dumps({"result": "unsafe-state", "problems": [str(exc)]}))
        return 2
    except OSError as exc:
        out = {"result": "error", "problems": [f"{type(exc).__name__}: {exc.strerror or exc}"]}
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0 if out["result"] == "ok" else 1

if __name__ == "__main__":
    sys.exit(main())
