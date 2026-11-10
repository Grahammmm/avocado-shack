"""Hass private state health check that alerts once per change (H19).

    python3 hass/health.py --state DIR [--backups DIR] [--seen FILE] [--outbox-minutes 15] [--backup-hours 26]
                           [--inbox-minutes 15] [--paused-hours 24] [--writer] [--model URL [--model-name NAME] [--label-model NAME]]
                           [--media DIR] [--min-free-mb MB]   (minutes/hours windows: each 1 to 100 years)

Read-only (sqlite mode=ro, never writer.lock, nothing created). Checks: state (unsafe: stop, exit 2), settings,
state-db (conversation.sqlite3 or inbox.sqlite3 is a symlink or not a regular file; lstat only, never opened),
db-integrity, outbox-stuck (unsent replies older than --outbox-minutes), apply-stuck (drafts `approved` over 10 min),
unverified (applied drafts, undone or not, whose preview check failed within --unverified-hours; count only),
guest-counts (guestCountsDb set but unreadable, or unset while an upcoming hike takes RSVPs; no path printed),
inbox-stuck (pending inbound older than --inbox-minutes), inbox-unreadable (inbound marked unreadable within
--inbox-unreadable-hours; count only), inbox-integrity, writer (--writer: one per reason editor
apply would refuse the recorded writer worktree; git runs with GIT_OPTIONAL_LOCKS=0, no path printed; info
photo-unused: photo-<sha> copies in assets/products no product's image uses, file names only, never deleted),
paused (info; problem paused-long when set over --paused-hours ago or unreadable), memory-invariant (owner memory
rows breaking its rules: two active rows for one key, or text left on a forgotten key; count only), backup-age
(--backups: no complete hass-state-* within --backup-hours), backup-verify (info backup-content: that newest
backup lists no content bundle; content restores from Git only), media-store (--media DIR: media.py
verify of the photo store, read-only, never inside the state dir; count only), disk-low (--min-free-mb: the state
or --backups filesystem has under that many MB free; `<store>: <n> MB free` in 50-MB steps, no path), model (--model:
one loopback GET /api/tags, 3 s; --model-name must be listed; no URL or reply printed). Problems carry a
check id and short detail only (no message text, sender or number). One JSON line: ok, problems, info, fingerprint
(sha256 of sorted problems), notify. --host-dir DIR (HASS-SVC-1, read-only, no secret opened): relay-stuck,
mac-silent, release-open, release-books, live-unconfirmed, host-config, publishing-stopped / stopped-long; with a host.json `clover` block
(HASS-CLOVER-2) also clover-token (one problem word for the token file, lstat only, never opened) and clover-sync (no good till pull for
over 2 h). --alert-log FILE
appends `<UTC> HASS-HEALTH <fp12> <check ids>` when notify and problems. --seen FILE (outside the repo and state dir, not a symlink) keeps the last
fingerprint; notify only when it changed (else notify = not ok). No send; the only network use is --model's loopback
GET. Exit 0 ok, 1 problems, 2 unsafe.
"""
import argparse, contextlib, hashlib, json, os, re, sqlite3, stat, sys, tempfile, urllib.error  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import bridge, editor, interpreter_local, statebackup  # noqa: E402
from hass import release_journal as journal  # noqa: E402
from hass.content_model import REPO_ROOT  # noqa: E402
from hass.conversation import ConfigError, load_settings  # noqa: E402
from hass.editor import UnsafeState  # noqa: E402
from hass.media import verify_store  # noqa: E402

DB, MANIFEST, APPLY_MINUTES, STAMP = "conversation.sqlite3", "MANIFEST.json", 10, "hass-state-%Y%m%dT%H%M%SZ"
MAX_WINDOW_HOURS = 100 * 365 * 24  # 100 years, as retention.MAX_DAYS; larger windows overflow datetime (RF0050-2)
SEEN_MAX = 128  # --seen holds a 64-hex fingerprint + newline; a larger record counts as changed (RF1920-9)
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

def _regular(path) -> bool | None:  # RF1520-12: lstat only, a link is never followed; None means absent
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError as exc:
        return None if isinstance(exc, FileNotFoundError) else False

def _db_checks(sdir: Path, now: datetime, outbox_minutes: int, problems: list, info: list, unverified_hours=72,
               paused_hours=24) -> None:
    if (kind := _regular(path := sdir / DB)) is None:
        return info.append(_problem("conversation", "no conversation yet"))
    if not kind: return problems.append(_problem("state-db", f"{DB} is not a regular file"))
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
    if (kind := _regular(path := sdir / "inbox.sqlite3")) is None: return
    if not kind: return problems.append(_problem("state-db", "inbox.sqlite3 is not a regular file"))
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

def _backup_content(path, info: list) -> None:  # AV1322-15: that same newest backup only; fixed words, never a path
    doc = statebackup._manifest(Path(path))  # read-only; None (unreadable or invalid) is backup-verify's problem
    if doc is not None and statebackup.BUNDLE not in doc["files"]:  # FAV-07: no content.bundle listed
        info.append(_problem("backup-content", "content restores from Git only"))

def _media_check(raw, sdir: Path, problems: list) -> None:  # RF1710-6 (H10): count only, never verify_store's text
    try:  # the state-dir rule is added here; verify_store refuses a missing or in-repo root before opening anything
        full, sdir = Path(os.path.abspath(raw)).resolve(), sdir.resolve()
        result = {"result": "unsafe"} if full == sdir or sdir in full.parents else verify_store(raw)
    except OSError:
        return problems.append(_problem("media-store", "media store unreadable"))
    if result["result"] == "unsafe": problems.append(_problem("media-store", "media store unsafe"))
    elif result["result"] != "ok": problems.append(_problem("media-store", f"{len(result['problems'])} problem(s)"))

def _disk_check(label, path, floor_mb, problems: list, statvfs=None) -> None:  # AV1737-14: free MB, never the path
    try:
        st = (statvfs or os.statvfs)(path)  # looked up per call so a test can patch os.statvfs
    except OSError:
        return problems.append(_problem("disk-low", f"{label}: free space unreadable"))
    if (free_mb := st.f_bavail * st.f_frsize // 2**20) < floor_mb:  # 50-MB steps keep the fingerprint stable
        problems.append(_problem("disk-low", f"{label}: {free_mb // 50 * 50} MB free"))

def _seen_path(raw, state, flag="--seen") -> Path:
    if Path(raw).is_symlink(): raise UnsafeState(f"{flag} must not be a symlink")
    full = Path(raw).resolve()
    if full.is_relative_to(REPO_ROOT.resolve()) or full.is_relative_to(Path(state).resolve()):
        raise UnsafeState(f"{flag} must lie outside the repository and the state dir")
    if not full.parent.is_dir() or (full.exists() and not full.is_file()):
        raise UnsafeState(f"{flag} must be a file in an existing folder")
    return full

RELAY_MIN, MAC_MIN, RELEASE_MIN, STOP_HOURS = 15, 10, 15, 24  # HASS-SVC-1 windows
IN_PROGRESS = frozenset({"intent", "applied", "built", "committed", "pushing", "pushed"})

def _relay_checks(hdir: Path, now: datetime, problems: list) -> None:
    if (kind := _regular(path := hdir / "relay.sqlite3")) is None: return
    if not kind: return problems.append(_problem("relay-stuck", "relay store is not a regular file"))
    try:
        with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)) as db:
            secs = int(now.timestamp())
            if n := db.execute("SELECT COUNT(*) FROM relay WHERE acked_at IS NULL AND created_at < ?",
                               (secs - RELAY_MIN * 60,)).fetchone()[0]: problems.append(_problem("relay-stuck", str(n)))
            if row := db.execute("SELECT value FROM meta WHERE name = 'last_pull_at'").fetchone():
                if (age := (secs - int(row[0])) // 60) > MAC_MIN:
                    problems.append(_problem("mac-silent", "over 2 h" if age > 120 else f"over {age // 10 * 10} min"))
    except (sqlite3.DatabaseError, ValueError, TypeError):
        problems.append(_problem("relay-stuck", "relay store unreadable"))

def _release_checks(hdir: Path, now: datetime, problems: list) -> None:  # state names only; lstat, never followed
    rdir, anchor = hdir / "releases", hdir / "publish.json"
    if not (os.path.lexists(rdir) or os.path.lexists(anchor)): return
    try:
        entries = []
        if os.path.lexists(rdir):
            st = os.lstat(rdir)
            if not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o700: raise journal.BooksError("release-books")
            for entry in sorted(os.scandir(rdir), key=lambda e: e.name):
                if entry.name.startswith(".release-"): continue
                j = journal.validate(journal.read(Path(entry.path)))
                if entry.name != j["change_id"] + ".json": raise journal.BooksError("release-books")
                entries.append(j)
        journal.derive(journal.read(anchor), entries)
    except (journal.BooksError, OSError):
        return problems.append(_problem("release-books", "release books failed their checks"))
    limit = now - timedelta(minutes=RELEASE_MIN)
    open_states = {j["state"] for j in entries if j["state"] not in journal.CLOSED
                   and (j["state"] not in IN_PROGRESS or journal.instant(j["at"]) < limit)}
    if open_states: problems.append(_problem("release-open", ",".join(sorted(open_states))))
    if n := sum(j["state"] in ("unconfirmed", "unknown") for j in entries): problems.append(_problem("live-unconfirmed", str(n)))

CLOVER_STALE_HOURS = 2  # HASS-CLOVER-2: the 15-minute sync has not worked for this long


def _clover_checks(cfg, now: datetime, problems: list) -> None:
    """HASS-CLOVER-2 (only with a `clover` block): clover-token = one credential.REASONS word for the token file (lstat only, never
    opened, never the path); clover-sync = the private till cache's last good pull is over CLOVER_STALE_HOURS old, or the pulls are
    failing (the fixed result word). No cache yet = no problem (the timer may not have run)."""
    from hass.clover import cache as clover_cache
    from hass.clover.credential import inspect
    if (word := inspect(cfg["clover"].get("tokenFile", ""))): problems.append(_problem("clover-token", word))
    try: facts = clover_cache.facts(cfg["state"])
    except (clover_cache.CacheUnsafe, OSError, sqlite3.Error): return problems.append(_problem("clover-sync", "cache not private or unreadable"))
    if not facts: return
    as_of = clover_cache._parse_iso(facts["asOf"])
    if as_of is None or now - as_of > timedelta(hours=CLOVER_STALE_HOURS):
        last = facts["lastResult"] if facts["lastResult"] in clover_cache.RESULTS else "unknown"
        problems.append(_problem("clover-sync", f"no good pull for over {CLOVER_STALE_HOURS} h (last: {last})"))


def _host_config(hdir: Path, now: datetime, problems: list, info: list) -> None:  # mode or type only; the key is never opened
    from hass import host  # lazy: only --host-dir needs it
    try:
        cfg = host.load_host(hdir / "host.json")
    except host.HostConfigError:
        return problems.append(_problem("host-config", "host.json refused"))
    try:
        st = os.lstat(cfg["secretFile"])
    except (OSError, ValueError):  # ValueError: an embedded NUL in the path
        problems.append(_problem("host-config", "secret file missing"))
    else:
        bad = ("type" if not stat.S_ISREG(st.st_mode) else "owner" if st.st_uid != os.getuid()
               else "mode" if st.st_mode & 0o177 else "size" if st.st_size > 128 else None)
        if bad: problems.append(_problem("host-config", f"secret file {bad}"))
    if isinstance(cfg.get("clover"), dict): _clover_checks(cfg, now, problems)
    if isinstance(rel := cfg.get("release"), dict) and isinstance(stop := rel.get("stopFile"), str):
        try: mtime = datetime.fromtimestamp(os.lstat(stop).st_mtime, timezone.utc)
        except (OSError, ValueError): return
        if now - mtime > timedelta(hours=STOP_HOURS): problems.append(_problem("stopped-long", f"over {STOP_HOURS} h"))
        else: info.append(_problem("publishing-stopped", "stop file set"))

def _alert(path: Path, problems, digest: str, now: datetime) -> None:  # ids only: no detail, text or path
    ids = " ".join(sorted({p["check"] for p in problems}))
    line = f"{now.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} HASS-HEALTH {digest[:12]} {ids}\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise OSError("alert log is not a regular file")
        os.write(fd, line.encode("utf-8"))
    finally: os.close(fd)

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

PHOTO_RE = re.compile(r"photo-[0-9a-f]{16}\.(jpg|png)")  # product.set_photo's web copy (hass/ops/photos.py)
def _unused_photos(sdir, info: list) -> None:  # AV0022-14 (H21): file names only; read-only, never deletes
    try:  # no worktree, bad products.json or no products dir: no entry (the `writer` check owns those)
        wt = editor._load(sdir)[2]
        products = json.loads((wt / "hass" / "content" / "products.json").read_text("utf-8"))["products"]
        used = {p["image"] for p in products if isinstance(p, dict) and isinstance(p.get("image"), str)}
        with os.scandir(wt / "storefront-mockup" / "assets" / "products") as entries:  # symlinks never followed
            names = sorted(e.name for e in entries if PHOTO_RE.fullmatch(e.name)
                           and e.is_file(follow_symlinks=False) and f"assets/products/{e.name}" not in used)
    except (OSError, ValueError, KeyError, TypeError, RecursionError, UnsafeState): return
    if n := len(names):  # five sorted names, then a count
        more = f" and {n - 5} more" if n > 5 else ""
        info.append(_problem("photo-unused", f"{n} unused: {', '.join(names[:5])}{more}"))

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
        if not isinstance(events, list): raise TypeError("events is not a list")
        found = {_upcoming_rsvp(e, now) for e in events}  # RF1230-25: each event on its own
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, UnsafeState):
        return info.append(_problem("guest-counts", "hikes unreadable"))
    if True in found: problems.append(_problem("guest-counts", "unset"))  # one bad row never hides a real hike
    if None in found: info.append(_problem("guest-counts", "hikes unreadable"))

def _upcoming_rsvp(e, now) -> bool | None:  # None = unreadable; the time is read only for a scheduled RSVP hike
    if not isinstance(e, dict): return None
    if e.get("status") != "scheduled" or not e.get("rsvpEnabled"): return False
    try: return datetime.fromisoformat(e["startsAt"]) > now
    except (KeyError, TypeError, ValueError): return None  # missing, not text, garbled, or zone-less (naive vs aware)

def _model_get(url, timeout) -> tuple:  # (status, body) via bridge's opener: no env proxy, no redirect, capped read
    try:
        with bridge._OPENER.open(url, timeout=timeout) as r: return r.status, r.read(interpreter_local.MAX_BODY + 1)
    except urllib.error.HTTPError as exc:  # also an unfollowed 3xx
        exc.close()
        return exc.code, b""

def _model_check(url, name, problems: list, transport, label=None) -> None:  # fixed details, never the URL or reply
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
    names = {m["name"] for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)}  # skip malformed
    missing = [role for role, want in (("interpreter", name), ("label", label))
               if want and (want if ":" in want else f"{want}:latest") not in names]
    if missing:
        detail = " and ".join(missing) + (" models not installed" if len(missing) == 2 else " model not installed")
        problems.append(_problem("model", detail if label is not None else "model not installed"))

def check(state, backups=None, outbox_minutes=15, backup_hours=26, now=None, inbox_minutes=15, writer=False,
          inbox_unreadable_hours=24, *, model=None, model_name=None, transport=None, unverified_hours=72,
          paused_hours=24, media=None, min_free_mb=None, label_model=None, host_dir=None) -> tuple:
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
        _backup_content(newest, info)
    if writer:
        _writer_check(sdir, problems)
        _unused_photos(sdir, info)
    if model: _model_check(model, model_name, problems, transport, label_model)
    if media is not None: _media_check(media, sdir, problems)
    if host_dir is not None:
        _relay_checks(hdir := Path(host_dir), now, problems)
        _release_checks(hdir, now, problems)
        _host_config(hdir, now, problems, info)
    if min_free_mb is not None:  # a missing backups dir is backup-age's problem only
        _disk_check("state", sdir, min_free_mb, problems)
        if backups is not None and os.path.isdir(backups): _disk_check("backups", backups, min_free_mb, problems)
    return problems, info, False

def fingerprint(problems) -> str:
    return hashlib.sha256("\n".join(sorted(f"{p['check']}\t{p['detail']}" for p in problems)).encode()).hexdigest()

def _remember(seen: Path, digest: str) -> bool:
    """True when digest differs from the stored one, which it then replaces (0600, fresh mkstemp + os.replace)."""
    with contextlib.suppress(OSError, UnicodeDecodeError):  # missing, unreadable, link, FIFO or oversize: a change
        fd = os.open(seen, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)  # RF1920-9: one bounded open, never a swap
        try:
            raw = os.read(fd, SEEN_MAX + 1) if stat.S_ISREG(os.fstat(fd).st_mode) else b""
        finally:
            os.close(fd)
        if len(raw) <= SEEN_MAX and raw.decode("utf-8").strip() == digest: return False
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
    for flag in ("--backups", "--seen", "--model", "--model-name", "--label-model", "--media", "--host-dir", "--alert-log"):
        parser.add_argument(flag)
    for flag, default in (("--outbox-minutes", 15), ("--backup-hours", 26), ("--inbox-minutes", 15)):
        parser.add_argument(flag, type=int, default=default)
    parser.add_argument("--inbox-unreadable-hours", type=int, default=24)
    parser.add_argument("--unverified-hours", type=int, default=72)
    parser.add_argument("--paused-hours", type=int, default=24)
    parser.add_argument("--writer", action="store_true")
    parser.add_argument("--min-free-mb", type=int)  # default off: output unchanged without it
    args = parser.parse_args(argv)
    if args.min_free_mb is not None and args.min_free_mb < 1: parser.error("--min-free-mb must be >= 1")
    hours = (args.backup_hours, args.inbox_unreadable_hours, args.unverified_hours, args.paused_hours)
    if min(args.outbox_minutes, args.inbox_minutes, *hours) < 1:
        parser.error("minutes and hours must be >= 1")
    if max(args.outbox_minutes, args.inbox_minutes) > MAX_WINDOW_HOURS * 60 or max(hours) > MAX_WINDOW_HOURS:
        parser.error(f"minutes must be at most {MAX_WINDOW_HOURS * 60} and hours at most {MAX_WINDOW_HOURS} (100 years)")
    if args.model_name is not None and not (args.model and args.model_name): parser.error("--model-name needs --model")
    if args.label_model is not None and not (args.model and args.label_model): parser.error("--label-model needs --model")
    try:
        model = None if args.model is None else interpreter_local.check_url(args.model)
    except ValueError:
        parser.error(interpreter_local.URL_ERROR)  # a usage error naming no URL; nothing was read
    try:
        seen = _seen_path(args.seen, args.state) if args.seen else None
    except UnsafeState as exc:
        _emit([_problem("seen", str(exc))], [], True)
        return 2
    try:
        alert_log = _seen_path(args.alert_log, args.state, "--alert-log") if args.alert_log else None
    except UnsafeState as exc:
        _emit([_problem("alert-log", str(exc))], [], True)
        return 2
    problems, info, unsafe = check(args.state, args.backups, args.outbox_minutes, args.backup_hours, now,
                                   args.inbox_minutes, args.writer, args.inbox_unreadable_hours, model=model,
                                   model_name=args.model_name, label_model=args.label_model, transport=transport, media=args.media,
                                   unverified_hours=args.unverified_hours, paused_hours=args.paused_hours,
                                   min_free_mb=args.min_free_mb, host_dir=args.host_dir)
    try:
        notify = _remember(seen, fingerprint(problems)) if seen else bool(problems)
    except OSError:  # fail open: an unrecorded fingerprint must not silence an alert; the detail names no path
        notify = True
        info.append(_problem("seen", "seen file not updated"))
    if alert_log and notify and problems:
        try: _alert(alert_log, problems, fingerprint(problems), now or datetime.now(timezone.utc))
        except OSError: info.append(_problem("alert-log", "alert log not written"))
    _emit(problems, info, notify)
    return 2 if unsafe else 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
