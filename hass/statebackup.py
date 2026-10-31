"""Hass private state backup, verify and isolated restore drill (H20 prep).

    python3 hass/statebackup.py create --state DIR --out DIR | verify BACKUP | restore BACKUP --into DIR --worktree WT [--paused]

create refuses a symlinked or odd config.json/writer.lock before anything opens it, takes the writer lock and copies a
settled state dir (config.json, drafts, changes, screenshots and consistent sqlite snapshots of inbox.sqlite3, then
conversation.sqlite3; never writer.lock, a journal, a symlink or an unknown entry) into a new private
<out>/hass-state-<UTC stamp>/ (out: an existing 0700 dir of the user) and writes MANIFEST.json (sha256 per file) last.
verify re-checks every hash and mode, refuses extra entries and symlinks and runs the sqlite integrity check on both
stores. restore verifies first, then builds a NEW state dir bound
to a separate drill worktree (only config.json `worktree` is rewritten). Isolation rule: nothing restores over an existing
dir or onto the recorded writer worktree (an attended operation); backups stay private (0700/0600) and outside the
repository, the worktrees and the state dir. No network, no Git writes, no deletes of source data. One JSON line out;
exit 0 ok, 1 any other result, 2 unsafe dir or usage.
"""
import argparse, contextlib, hashlib, json, os, re, shutil, sqlite3, stat, sys  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import editor  # noqa: E402
from hass.conversation import CONTROL, _iso  # noqa: E402
from hass.content_model import REPO_ROOT  # noqa: E402
from hass.editor import UnsafeState  # noqa: E402

MANIFEST, CONFIG, DB, LOCK = "MANIFEST.json", "config.json", "conversation.sqlite3", "writer.lock"
INBOX = "inbox.sqlite3"  # H16 inbound queue; snapshotted like DB
DIRS = ("drafts", "changes", "screenshots")
FILE_RE = re.compile(r"config\.json|conversation\.sqlite3|inbox\.sqlite3|(drafts|changes)/chg-[0-9A-Za-z_-]+\.json"
                     r"|screenshots/[0-9A-Za-z_-][0-9A-Za-z._-]*\.png")
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

def create(state, out, now=None) -> dict:
    if not state or not Path(state).is_dir(): raise UnsafeState("state dir must already exist")  # open_state creates
    top = [p for p in _scan(editor.open_state(state))[1] if p.split(": ", 1)[1] in (CONFIG, LOCK)]
    if top: return {"result": "refused", "problems": top}  # before _load reads config / _writer_lock creates the lock
    sdir, cfg, wt = editor._load(state)
    dest_root = _private_out(out, _roots(wt) + [sdir])
    with editor._writer_lock(sdir) as held:
        if not held: return {"result": "busy"}
        if (journal := sdir / "journal").is_dir() and not journal.is_symlink() and any(journal.iterdir()):
            return {"result": "unsettled", "problems": ["an interrupted write is pending; run editor.py recover first"]}
        files, bad = _scan(sdir)
        if bad: return {"result": "refused", "problems": bad}
        now = now or datetime.now(timezone.utc)
        dest = dest_root / f"hass-state-{now.strftime('%Y%m%dT%H%M%SZ')}"
        try:
            dest.mkdir(mode=0o700)
        except FileExistsError:
            return {"result": "exists", "backup": str(dest)}
        os.chmod(dest, 0o700)
        hashes = {}
        # The inbox goes first: a row it shows `done` was handled before, so the later DB snapshot holds its effect;
        # one handled in between stays `pending` here and a later drain answers it `duplicate` (no second write).
        for rel in sorted(files, key=lambda rel: rel != INBOX):
            (dest / rel).parent.mkdir(mode=0o700, exist_ok=True)
            (_snapshot if rel in (DB, INBOX) else _copy)(sdir / rel, dest / rel)
            hashes[rel] = hashlib.sha256(_read(dest / rel)).hexdigest()
        doc = {"schemaVersion": 1, "createdAt": now.isoformat(), "worktree": cfg["worktree"], "files": hashes}
        _write_new(dest / (MANIFEST + ".tmp"), json.dumps(doc, indent=2, sort_keys=True).encode("utf-8"))
        os.replace(dest / (MANIFEST + ".tmp"), dest / MANIFEST)  # last: a backup without it is incomplete
    return {"result": "ok", "backup": str(dest), "files": len(hashes)}

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
    if bdir.stat().st_mode & 0o777 != 0o700: problems.append("mode: backup dir")
    def walk(path: Path, prefix: str) -> None:
        for entry in sorted(os.scandir(path), key=lambda e: e.name):
            rel, mode = prefix + entry.name, entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode): problems.append(f"symlink: {rel}")
            elif stat.S_ISDIR(mode) and not prefix and entry.name in DIRS:
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
    return {"result": "corrupt", "problems": problems} if problems else {"result": "ok", "files": len(files)}

def _pause(path: Path, now) -> str:  # restore --paused, before the dir appears; an older pause keeps its set_at
    if not path.exists(): _write_new(path, b"")
    with contextlib.closing(sqlite3.connect(path)) as db, db:
        db.execute(CONTROL)
        db.execute("INSERT OR IGNORE INTO control(name, value, set_at, provider_id) VALUES ('paused', '1', ?, "
                   "'statebackup-restore')", (_iso(now or datetime.now(timezone.utc)),))
        since = db.execute("SELECT set_at FROM control WHERE name = 'paused'").fetchone()[0]
    os.chmod(path, 0o600)
    return since

def restore(backup, into, worktree, paused=False, now=None) -> dict:
    checked = verify(backup)
    if checked["result"] != "ok": return {"result": "corrupt", "problems": checked["problems"]}
    bdir = Path(backup).absolute()
    doc = _manifest(bdir)
    if os.path.lexists(into): return {"result": "refused", "problems": ["restore dir already exists; left untouched"]}
    if not worktree: return {"result": "refused", "problems": ["--worktree (a separate drill worktree) is required"]}
    target, wt, recorded = Path(into).resolve(), Path(worktree).resolve(), Path(doc["worktree"]).resolve()
    if wt == recorded: return {"result": "refused", "problems": [ATTENDED]}
    if problems := editor.worktree_problems(wt, recovering=True): return {"result": "refused", "problems": problems}
    if _inside(target, _roots(wt) + [recorded, bdir.resolve()]):
        raise UnsafeState("restore dir must lie outside the backup, the repository and the worktrees")
    tmp = target.parent / f".{target.name}.restore-{os.getpid()}"
    tmp.mkdir(mode=0o700)
    try:
        os.chmod(tmp, 0o700)
        for rel in sorted(doc["files"]):
            (tmp / rel).parent.mkdir(mode=0o700, exist_ok=True)
            if rel != CONFIG:
                _copy(bdir / rel, tmp / rel)
                continue
            cfg = {**json.loads(_read(bdir / CONFIG).decode("utf-8")), "worktree": str(wt)}
            _write_new(tmp / CONFIG, json.dumps(cfg, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        extra = {"paused": True, "pausedSince": _pause(tmp / DB, now)} if paused else {}
        if os.path.lexists(target): raise FileExistsError(f"restore dir appeared during restore: {target}")
        os.rename(tmp, target)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)  # only the temp dir this call created
        raise
    return {"result": "ok", "state": str(target), "worktree": str(wt), "files": len(doc["files"]), **extra}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/statebackup.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, params in (("create", ["--state", "--out"]), ("verify", ["backup"]),
                         ("restore", ["backup", "--into", "--worktree"])):
        cmd = sub.add_parser(name)
        for param in params: cmd.add_argument(param, **({"required": True} if param.startswith("--") else {}))
    cmd.add_argument("--paused", action="store_true")  # restore only (the last parser)
    args = parser.parse_args(argv)
    try:
        out = create(args.state, args.out) if args.cmd == "create" else verify(args.backup) \
            if args.cmd == "verify" else restore(args.backup, args.into, args.worktree, paused=args.paused)
    except UnsafeState as exc:
        print(json.dumps({"result": "unsafe-state", "problems": [str(exc)]}))
        return 2
    except OSError as exc:
        out = {"result": "error", "problems": [f"{type(exc).__name__}: {exc.strerror or exc}"]}
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0 if out["result"] == "ok" else 1

if __name__ == "__main__":
    sys.exit(main())
