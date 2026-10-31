"""Hass private state health check that alerts once per change (H19).

    python3 hass/health.py --state DIR [--backups DIR] [--seen FILE] [--outbox-minutes 15] [--backup-hours 26]

Read-only (sqlite mode=ro, never writer.lock, nothing created). Checks: state (unsafe: stop, exit 2), settings,
db-integrity, outbox-stuck (unsent replies older than --outbox-minutes), apply-stuck (drafts `approved` over 10 min),
paused (info only), backup-age (with --backups: no complete hass-state-* dir within --backup-hours). Problems carry a
check id and short detail only (no message text, sender or number). One JSON line: ok, problems, info, fingerprint
(sha256 of sorted problems), notify. --seen FILE (outside the repo and state dir, not a symlink) keeps the last
fingerprint; notify only when it changed (else notify = not ok). No network or send. Exit 0 ok, 1 problems, 2 unsafe.
"""
import argparse, contextlib, hashlib, json, os, sqlite3, sys, tempfile  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import editor  # noqa: E402
from hass.content_model import REPO_ROOT  # noqa: E402
from hass.conversation import ConfigError, load_settings  # noqa: E402
from hass.editor import UnsafeState  # noqa: E402

DB, MANIFEST, APPLY_MINUTES, STAMP = "conversation.sqlite3", "MANIFEST.json", 10, "hass-state-%Y%m%dT%H%M%SZ"
PAUSED_SQL = "SELECT set_at FROM control WHERE name = 'paused'"  # paused <=> this row (conversation.py H17)

def _problem(check, detail) -> dict:
    return {"check": check, "detail": detail}

def _older(rows, limit: datetime) -> int:
    """How many ISO times lie before limit; an unreadable or zone-less time counts (fail closed)."""
    def old(raw) -> bool:
        try:
            return datetime.fromisoformat(raw) < limit
        except (TypeError, ValueError):
            return True
    return sum(old(raw) for (raw,) in rows)

def _db_checks(sdir: Path, now: datetime, outbox_minutes: int, problems: list, info: list) -> None:
    if not (path := sdir / DB).is_file(): return info.append(_problem("conversation", "no conversation yet"))
    try:
        with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)) as db:
            result = [r[0] for r in db.execute("PRAGMA quick_check").fetchall()]
            if result != ["ok"]: return problems.append(_problem("db-integrity", f"{len(result)} issue(s)"))
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            for check, table, sql, minutes in (
                    ("outbox-stuck", "outbox", "SELECT created_at FROM outbox WHERE sent_at IS NULL", outbox_minutes),
                    ("apply-stuck", "drafts", "SELECT created_at FROM drafts WHERE state = 'approved'", APPLY_MINUTES)):
                if table in tables and (n := _older(db.execute(sql).fetchall(), now - timedelta(minutes=minutes))):
                    problems.append(_problem(check, str(n)))
            if "control" in tables and (row := db.execute(PAUSED_SQL).fetchone()):
                info.append(_problem("paused", str(row[0])))
    except sqlite3.DatabaseError:
        problems.append(_problem("db-integrity", "database unreadable"))

def _backup_check(raw, now: datetime, hours: int, problems: list) -> None:
    newest = None
    try:
        for entry in os.scandir(raw):
            try:
                stamp = datetime.strptime(entry.name, STAMP).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            manifest = os.path.join(entry.path, MANIFEST)
            if entry.is_dir(follow_symlinks=False) and os.path.isfile(manifest) and not os.path.islink(manifest):
                newest = stamp if newest is None else max(newest, stamp)
    except OSError:
        return problems.append(_problem("backup-age", "backup dir unreadable"))
    if newest is None: problems.append(_problem("backup-age", "no complete backup"))
    elif now - newest > timedelta(hours=hours):
        problems.append(_problem("backup-age", f"newest complete backup older than {hours} h"))

def _seen_path(raw, state) -> Path:
    if Path(raw).is_symlink(): raise UnsafeState("--seen must not be a symlink")
    full = Path(raw).resolve()
    if full.is_relative_to(REPO_ROOT.resolve()) or full.is_relative_to(Path(state).resolve()):
        raise UnsafeState("--seen must lie outside the repository and the state dir")
    if not full.parent.is_dir() or (full.exists() and not full.is_file()):
        raise UnsafeState("--seen must be a file in an existing folder")
    return full

def check(state, backups=None, outbox_minutes=15, backup_hours=26, now=None) -> tuple:
    """(problems, info, unsafe) for one state dir; never writes it (open_state would create a missing dir)."""
    now, problems, info = now or datetime.now(timezone.utc), [], []
    try:
        if Path(state).is_symlink() or not Path(state).is_dir():
            raise UnsafeState("state dir must be an existing directory, not a symlink")
        sdir = editor.open_state(state)
    except UnsafeState as exc:
        return [_problem("state", str(exc))], info, True
    try:
        load_settings(sdir)
    except ConfigError as exc:
        problems.append(_problem("settings", str(exc)))
    _db_checks(sdir, now, outbox_minutes, problems, info)
    if backups is not None: _backup_check(backups, now, backup_hours, problems)
    return problems, info, False

def fingerprint(problems) -> str:
    return hashlib.sha256("\n".join(sorted(f"{p['check']}\t{p['detail']}" for p in problems)).encode()).hexdigest()

def _remember(seen: Path, digest: str) -> bool:
    """True when digest differs from the stored one, which it then replaces (0600, fresh mkstemp + os.replace)."""
    with contextlib.suppress(OSError, UnicodeDecodeError):  # a missing or unreadable record counts as a change
        if seen.read_text("utf-8").strip() == digest: return False
    fd, tmp = tempfile.mkstemp(prefix=f".{seen.name}.", dir=seen.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write(digest + "\n")
        os.replace(tmp, seen)
    except BaseException:
        with contextlib.suppress(OSError): os.unlink(tmp)  # only the temp file this call created
        raise
    return True

def _emit(problems, info, notify) -> None:
    print(json.dumps({"ok": not problems, "problems": problems, "info": info, "fingerprint": fingerprint(problems),
                      "notify": notify}, ensure_ascii=False, sort_keys=True))

def main(argv=None, now=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/health.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", required=True)
    for flag in ("--backups", "--seen"): parser.add_argument(flag)
    for flag, default in (("--outbox-minutes", 15), ("--backup-hours", 26)):
        parser.add_argument(flag, type=int, default=default)
    args = parser.parse_args(argv)
    if args.outbox_minutes < 1 or args.backup_hours < 1: parser.error("minutes and hours must be >= 1")
    try:
        seen = _seen_path(args.seen, args.state) if args.seen else None
    except UnsafeState as exc:
        _emit([_problem("seen", str(exc))], [], True)
        return 2
    problems, info, unsafe = check(args.state, args.backups, args.outbox_minutes, args.backup_hours, now)
    _emit(problems, info, _remember(seen, fingerprint(problems)) if seen else bool(problems))
    return 2 if unsafe else 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
