"""Hass private state health check that alerts once per change (H19).

    python3 hass/health.py --state DIR [--backups DIR] [--seen FILE] [--outbox-minutes 15] [--backup-hours 26]
                           [--inbox-minutes 15] [--paused-hours 24] [--writer] [--model URL [--model-name NAME]]

Read-only (sqlite mode=ro, never writer.lock, nothing created). Checks: state (unsafe: stop, exit 2), settings,
db-integrity, outbox-stuck (unsent replies older than --outbox-minutes), apply-stuck (drafts `approved` over 10 min),
unverified (applied drafts, undone or not, whose preview check failed within --unverified-hours; count only),
guest-counts (guestCountsDb set but unreadable, or unset while an upcoming hike takes RSVPs; no path printed),
inbox-stuck (pending inbound older than --inbox-minutes), inbox-unreadable (inbound marked unreadable within
--inbox-unreadable-hours; count only), inbox-integrity, writer (--writer: one per reason editor
apply would refuse the recorded writer worktree; git runs with GIT_OPTIONAL_LOCKS=0, no path printed),
paused (info; problem paused-long when set over --paused-hours ago or unreadable), memory-invariant (owner memory
rows breaking its rules: two active rows for one key, or text left on a forgotten key; count only), backup-age
(--backups: no complete hass-state-* within --backup-hours), backup-verify, model (--model:
one loopback GET /api/tags, 3 s; --model-name must be listed; no URL or reply printed). Problems carry a
check id and short detail only (no message text, sender or number). One JSON line: ok, problems, info, fingerprint
(sha256 of sorted problems), notify. --seen FILE (outside the repo and state dir, not a symlink) keeps the last
fingerprint; notify only when it changed (else notify = not ok). No send; the only network use is --model's loopback
GET. Exit 0 ok, 1 problems, 2 unsafe.
"""
import argparse, contextlib, hashlib, json, os, sqlite3, sys, tempfile, urllib.error  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import bridge, editor, interpreter_local, statebackup  # noqa: E402
from hass.content_model import REPO_ROOT  # noqa: E402
from hass.conversation import ConfigError, load_settings  # noqa: E402
from hass.editor import UnsafeState  # noqa: E402

DB, MANIFEST, APPLY_MINUTES, STAMP = "conversation.sqlite3", "MANIFEST.json", 10, "hass-state-%Y%m%dT%H%M%SZ"
PAUSED_SQL = "SELECT set_at FROM control WHERE name = 'paused'"  # paused <=> this row (conversation.py H17)
UNVERIFIED_SQL = ("SELECT checked_at FROM drafts WHERE checked_at IS NOT NULL AND (state = 'applied' AND reason LIKE"
                  " 'not verified: %' OR state = 'reverted' AND screenshot IS NULL)")  # failed check (_verify_pending);
# an undo (_outcome) rewrites the reason, but only a passed check stores a screenshot, so the window alone clears it
MEMORY_SQL = ("SELECT (SELECT COUNT(*) FROM memory m WHERE superseded_at IS NULL AND forgotten_at IS NULL AND (SELECT"
              " COUNT(*) FROM memory m2 WHERE m2.key = m.key AND m2.superseded_at IS NULL AND m2.forgotten_at IS NULL)"
              " > 1) + (SELECT COUNT(*) FROM memory m WHERE value != '' AND EXISTS (SELECT 1 FROM memory m2 WHERE"
              " m2.key = m.key AND m2.forgotten_at >= m.created_at))")  # hass/memory.py: one active row per key;
# forget blanks every row of the key, so only a row created after the forget (re-remembered) may hold text

def _problem(check, detail) -> dict:
    return {"check": check, "detail": detail}

def _older(rows, limit: datetime, newer=False) -> int:
    """How many ISO times lie before limit (newer: at/after it); unreadable or zone-less times count (fail closed)."""
    def old(raw) -> bool:
        try:
            return (datetime.fromisoformat(raw) < limit) != newer
        except (TypeError, ValueError):
            return True
    return sum(old(raw) for (raw,) in rows)

def _db_checks(sdir: Path, now: datetime, outbox_minutes: int, problems: list, info: list, unverified_hours=72,
               paused_hours=24) -> None:
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
            if {"checked_at", "screenshot"} <= {r[1] for r in db.execute("PRAGMA table_info(drafts)")}:  # none: no table
                rows = db.execute(UNVERIFIED_SQL).fetchall()  # an H05 database without checked_at is skipped
                if n := _older(rows, now - timedelta(hours=unverified_hours), newer=True):
                    problems.append(_problem("unverified", str(n)))
            if "control" in tables and (row := db.execute(PAUSED_SQL).fetchone()):
                info.append(_problem("paused", str(row[0])))
                if _older([row], limit := now - timedelta(hours=paused_hours)):  # RF1650-12; only an unreadable
                    unreadable = _older([row], limit, newer=True)  # time counts as both older and newer
                    detail = "unreadable time" if unreadable else f"over {paused_hours} h"
                    problems.append(_problem("paused-long", detail))
            if "memory" in tables:  # RF1710-5: hass/memory.py rules, count only (no key, value or source)
                try:
                    if n := db.execute(MEMORY_SQL).fetchone()[0]:
                        problems.append(_problem("memory-invariant", f"{n} row(s)"))
                except sqlite3.DatabaseError:
                    problems.append(_problem("memory-invariant", "memory table unreadable"))
    except sqlite3.DatabaseError:
        problems.append(_problem("db-integrity", "database unreadable"))

def _inbox_check(sdir: Path, now: datetime, minutes: int, problems: list, unreadable_hours=24) -> None:
    """H16 queue: pending inbound enqueued (this box's clock) over `minutes` ago; no inbox file -> nothing to check."""
    if not (path := sdir / "inbox.sqlite3").is_file(): return
    try:
        with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)) as db:
            result = [r[0] for r in db.execute("PRAGMA quick_check").fetchall()]
            if result != ["ok"]: return problems.append(_problem("inbox-integrity", f"{len(result)} issue(s)"))
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'inbound'").fetchone(): return
            rows = db.execute("SELECT enqueued_at FROM inbound WHERE state = 'pending'").fetchall()
            if n := _older(rows, now - timedelta(minutes=minutes)): problems.append(_problem("inbox-stuck", str(n)))
            if "disposition" in {r[1] for r in db.execute("PRAGMA table_info(inbound)")}:  # count only (RF1230-11)
                rows = db.execute("SELECT done_at FROM inbound WHERE state = 'done' AND disposition = 'unreadable'")
                if n := _older(rows.fetchall(), now - timedelta(hours=unreadable_hours), newer=True):
                    problems.append(_problem("inbox-unreadable", str(n)))
    except sqlite3.DatabaseError:
        problems.append(_problem("inbox-integrity", "database unreadable"))

def _backup_check(raw, now: datetime, hours: int, problems: list):
    newest = None
    try:
        for entry in os.scandir(raw):
            try:
                stamp = datetime.strptime(entry.name, STAMP).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            manifest = os.path.join(entry.path, MANIFEST)
            if entry.is_dir(follow_symlinks=False) and os.path.isfile(manifest) and not os.path.islink(manifest):
                newest = (stamp, entry.path) if newest is None else max(newest, (stamp, entry.path))
    except OSError:
        return problems.append(_problem("backup-age", "backup dir unreadable"))
    if newest is None: problems.append(_problem("backup-age", "no complete backup"))
    elif now - newest[0] > timedelta(hours=hours):
        problems.append(_problem("backup-age", f"newest complete backup older than {hours} h"))
    else: return newest[1]  # the newest complete backup within the window: the only one verified

def _verify_backup(path, problems: list) -> None:  # H20, read-only; the detail is a count, never a file name
    try:
        result = statebackup.verify(path)
    except (OSError, sqlite3.DatabaseError):
        return problems.append(_problem("backup-verify", "verify failed"))
    if result["result"] != "ok": problems.append(_problem("backup-verify", f"{len(result['problems'])} problem(s)"))

def _seen_path(raw, state) -> Path:
    if Path(raw).is_symlink(): raise UnsafeState("--seen must not be a symlink")
    full = Path(raw).resolve()
    if full.is_relative_to(REPO_ROOT.resolve()) or full.is_relative_to(Path(state).resolve()):
        raise UnsafeState("--seen must lie outside the repository and the state dir")
    if not full.parent.is_dir() or (full.exists() and not full.is_file()):
        raise UnsafeState("--seen must be a file in an existing folder")
    return full

def _writer_check(state, problems: list) -> None:
    old = os.environ.get("GIT_OPTIONAL_LOCKS")
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"  # this call only: git status must not refresh the writer's index
    try:
        wt = editor._load(state)[2]
    except UnsafeState as exc:
        problems.append(_problem("writer", str(exc)))
    except (OSError, ValueError, KeyError, TypeError):
        problems.append(_problem("writer", "writer config unreadable"))
    else:
        problems.extend(_problem("writer", detail) for detail in editor.worktree_problems(wt))
    finally:
        if old is None: os.environ.pop("GIT_OPTIONAL_LOCKS", None)
        else: os.environ["GIT_OPTIONAL_LOCKS"] = old

def _guest_check(sdir, settings, now, problems: list, info: list) -> None:  # AV1537-12: fixed words, never the path
    from hass.ops import hikes  # lazy, as in status; reads seat totals only (mode=ro, query_only)
    if (path := settings.get("guestCountsDb")) not in (None, ""):  # a set path that does not open is always a problem
        try:
            hikes.guest_counts(path)
        except (sqlite3.Error, OSError, ValueError, TypeError):
            problems.append(_problem("guest-counts", "unreadable"))
        return
    try:  # unset: a problem only while an upcoming scheduled hike takes RSVPs (the filter status uses)
        if not (wt := editor._load(sdir)[2]).is_dir(): return  # no worktree, no hikes to read: `writer` owns that
        events = json.loads((wt / "hass" / "content" / "community.json").read_text("utf-8"))["events"]
        if any(e.get("status") == "scheduled" and e.get("rsvpEnabled") and datetime.fromisoformat(e["startsAt"]) > now
               for e in events): problems.append(_problem("guest-counts", "unset"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnsafeState):
        info.append(_problem("guest-counts", "hikes unreadable"))

def _model_get(url, timeout) -> tuple:  # (status, body) via bridge's opener: no env proxy, no redirect, capped read
    try:
        with bridge._OPENER.open(url, timeout=timeout) as r: return r.status, r.read(interpreter_local.MAX_BODY + 1)
    except urllib.error.HTTPError as exc:  # also an unfollowed 3xx
        exc.close()
        return exc.code, b""

def _model_check(url, name, problems: list, transport) -> None:  # NB-AV-06: fixed details, never the URL or reply
    try:
        status, raw = (transport or _model_get)(url + "/api/tags", 3)
    except Exception:  # noqa: BLE001 - refused, reset, timeout: the model cannot be reached
        return problems.append(_problem("model", "unreachable"))
    try:
        if type(status) is not int or type(raw) is not bytes or len(raw) > interpreter_local.MAX_BODY: raise ValueError
        if status != 200: return problems.append(_problem("model", f"http {status}"))
        if not isinstance(models := json.loads(raw)["models"], list): raise ValueError
    except (ValueError, TypeError, KeyError, RecursionError):
        return problems.append(_problem("model", "bad reply"))
    want = name if not name or ":" in name else f"{name}:latest"  # a name without a tag means :latest
    names = {m["name"] for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)}  # skip malformed
    if want and want not in names:
        problems.append(_problem("model", "model not installed"))

def check(state, backups=None, outbox_minutes=15, backup_hours=26, now=None, inbox_minutes=15, writer=False,
          inbox_unreadable_hours=24, *, model=None, model_name=None, transport=None, unverified_hours=72,
          paused_hours=24) -> tuple:
    """(problems, info, unsafe) for one state dir; never writes it (open_state would create a missing dir)."""
    now, problems, info = now or datetime.now(timezone.utc), [], []
    try:
        if Path(state).is_symlink() or not Path(state).is_dir():
            raise UnsafeState("state dir must be an existing directory, not a symlink")
        sdir = editor.open_state(state)
    except UnsafeState as exc:
        return [_problem("state", str(exc))], info, True
    try:
        settings = load_settings(sdir)
    except ConfigError as exc:
        problems.append(_problem("settings", str(exc)))
    else:
        _guest_check(sdir, settings, now, problems, info)
    _db_checks(sdir, now, outbox_minutes, problems, info, unverified_hours, paused_hours)
    _inbox_check(sdir, now, inbox_minutes, problems, inbox_unreadable_hours)
    if backups is not None and (newest := _backup_check(backups, now, backup_hours, problems)):
        _verify_backup(newest, problems)
    if writer: _writer_check(sdir, problems)
    if model: _model_check(model, model_name, problems, transport)
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

def main(argv=None, now=None, transport=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/health.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", required=True)
    for flag in ("--backups", "--seen", "--model", "--model-name"): parser.add_argument(flag)
    for flag, default in (("--outbox-minutes", 15), ("--backup-hours", 26), ("--inbox-minutes", 15)):
        parser.add_argument(flag, type=int, default=default)
    parser.add_argument("--inbox-unreadable-hours", type=int, default=24)
    parser.add_argument("--unverified-hours", type=int, default=72)
    parser.add_argument("--paused-hours", type=int, default=24)
    parser.add_argument("--writer", action="store_true")
    args = parser.parse_args(argv)
    hours = (args.backup_hours, args.inbox_unreadable_hours, args.unverified_hours, args.paused_hours)
    if min(args.outbox_minutes, args.inbox_minutes, *hours) < 1:
        parser.error("minutes and hours must be >= 1")
    if args.model_name is not None and not (args.model and args.model_name): parser.error("--model-name needs --model")
    try:
        model = None if args.model is None else interpreter_local.check_url(args.model)
    except ValueError:
        parser.error(interpreter_local.URL_ERROR)  # a usage error naming no URL; nothing was read
    try:
        seen = _seen_path(args.seen, args.state) if args.seen else None
    except UnsafeState as exc:
        _emit([_problem("seen", str(exc))], [], True)
        return 2
    problems, info, unsafe = check(args.state, args.backups, args.outbox_minutes, args.backup_hours, now,
                                   args.inbox_minutes, args.writer, args.inbox_unreadable_hours, model=model,
                                   model_name=args.model_name, transport=transport,
                                   unverified_hours=args.unverified_hours, paused_hours=args.paused_hours)
    try:
        notify = _remember(seen, fingerprint(problems)) if seen else bool(problems)
    except OSError:  # fail open: an unrecorded fingerprint must not silence an alert; the detail names no path
        notify = True
        info.append(_problem("seen", "seen file not updated"))
    _emit(problems, info, notify)
    return 2 if unsafe else 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
