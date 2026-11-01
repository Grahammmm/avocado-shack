"""Hass retention report (H21, read-only): how much kept data is older than --days N. Deletes nothing.

    python3 hass/retention.py report --state DIR --days N [--media ROOT] [--backups DIR] [--now ISO]  (N: 1-36500)

One JSON line: per data class, the count strictly older than now - N days and the oldest kept UTC date (or null), dated
by inbox/messages received_at, outbox/drafts created_at (closed draft: no further transition), screenshot mtime, the
photo sidecar received_at (none usable: undated, never guessed) and the backup name's stamp (other names ignored).
Zone-less or malformed times, and backup stamps that are no real calendar time, count nowhere. No ids, text or file
names print. SQLite opens mode=ro; nothing is created or written; the owner picks the period (owner action 4). Exit 1:
a store is missing or unreadable (its keys say "unavailable"); exit 2, before anything opens: bad usage (incl. a
--days reaching before year 1 from --now), or a missing/symlinked dir or symlinked database; else 0.
"""
import argparse, contextlib, json, os, sqlite3, stat, sys  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path
if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hass.conversation import TRANSITIONS  # noqa: E402
from hass.media import EXT  # noqa: E402
from hass.statebackup import MANIFEST, NAME_RE  # noqa: E402

CONV, INBOX, UNAVAILABLE = "conversation.sqlite3", "inbox.sqlite3", "unavailable"
MAX_DAYS = 36500  # 100 years

class Unsafe(Exception): """A path the report refuses to open (exit 2)."""

def _when(raw):
    """An aware datetime, or None for a missing, zone-less or malformed time."""
    with contextlib.suppress(TypeError, ValueError):
        if (dt := datetime.fromisoformat(raw)).tzinfo is not None: return dt
    return None

def _tally(cutoff, items, keys) -> dict:
    """items: (key, when). Per key, how many dated items lie strictly before cutoff; plus the oldest dated one."""
    out, oldest = dict.fromkeys(keys, 0), None
    for key, when in items:
        if when is None or key not in out: continue
        oldest = when if oldest is None else min(oldest, when)
        out[key] += when < cutoff
    out["oldest"] = None if oldest is None else oldest.astimezone(timezone.utc).date().isoformat()
    return out

def _rows(path: Path, queries: dict) -> dict:
    """{name: rows} over one read-only connection; a missing table gives no rows. Raises sqlite3.DatabaseError."""
    with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        return {name: db.execute(sql).fetchall() if table in tables else [] for name, (table, sql) in queries.items()}

def _files(folder: Path):
    """Regular files (never followed links) one level below each real subdirectory of folder."""
    if folder.is_symlink() or not folder.is_dir(): return
    for sub in sorted(os.scandir(folder), key=lambda e: e.name):
        if sub.is_dir(follow_symlinks=False):
            yield from (e for e in os.scandir(sub.path) if e.is_file(follow_symlinks=False))

def _sidecar_time(path: Path):
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode): return None
        return _when(json.loads(path.read_bytes().decode("utf-8")).get("received_at"))
    except (OSError, ValueError, AttributeError):
        return None

def _shots(folder: Path, cutoff) -> dict:
    """Screenshot PNGs by file mtime (the only class dated that way); no real screenshots dir counts as none."""
    found = os.scandir(folder) if folder.is_dir() and not folder.is_symlink() else ()
    old = [s.st_size for e in found if e.is_file(follow_symlinks=False)
           and (s := e.stat(follow_symlinks=False)).st_mtime < cutoff.timestamp()]
    return {"files": len(old), "bytes": sum(old)}

def _media(root: Path, cutoff) -> dict:
    """Originals (jpg/png beside a <sha>.json sidecar) and their web copies, dated by the sidecar received_at."""
    dated, undated, size = {}, 0, 0
    for entry in _files(root / "originals"):
        stem, ext = os.path.splitext(entry.name)
        if ext[1:] not in EXT.values(): continue  # the sidecar itself, or a leftover temp file
        when = dated[stem] = _sidecar_time(Path(entry.path).with_suffix(".json"))
        undated += when is None
        size += entry.stat(follow_symlinks=False).st_size if when is not None and when < cutoff else 0
    out = _tally(cutoff, (("originals", w) for w in dated.values()), ("originals",))
    web = sum(1 for e in _files(root / "web") if (w := dated.get(os.path.splitext(e.name)[0])) and w < cutoff)
    return {"originals": out["originals"], "bytes": size, "web": web, "oldest": out["oldest"], "undated": undated}

def _backups(folder: Path, cutoff) -> dict:
    """hass-state-<stamp> entries: complete with a regular MANIFEST.json (statebackup writes it last), else not."""
    items = []
    for entry in os.scandir(folder):
        if not NAME_RE.fullmatch(entry.name): continue
        try: when = datetime.strptime(entry.name, "hass-state-%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError: continue  # stamp-shaped but not a real calendar time (month 13, Feb 30): foreign
        manifest = os.path.join(entry.path, MANIFEST)
        complete = entry.is_dir(follow_symlinks=False) and os.path.isfile(manifest) and not os.path.islink(manifest)
        items.append(("complete" if complete else "incomplete", when))
    return _tally(cutoff, items, ("complete", "incomplete"))

def _dir(raw, what):
    if raw is None: return None
    if Path(raw).is_symlink() or not Path(raw).is_dir(): raise Unsafe(f"{what} must be an existing dir, not a symlink")
    return Path(raw)

def report(state, days: int, media=None, backups=None, now=None) -> dict:
    """The report dict; raises Unsafe before opening anything."""
    try: cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    except OverflowError: raise Unsafe("--days reaches before year 1 from --now") from None
    sdir, mroot, bdir = _dir(state, "state dir"), _dir(media, "media root"), _dir(backups, "backups dir")
    for name in (CONV, INBOX):
        if (sdir / name).is_symlink(): raise Unsafe(f"{name} must not be a symlink")
    doc = {"days": days, "cutoff": cutoff.isoformat()}
    try:
        rows = _rows(sdir / INBOX, {"inbox": ("inbound", "SELECT state, received_at FROM inbound")})
        doc["inbox"] = _tally(cutoff, ((s, _when(t)) for s, t in rows["inbox"]), ("done", "history", "pending"))
    except sqlite3.DatabaseError: doc["inbox"] = UNAVAILABLE
    try:
        rows = _rows(sdir / CONV, {
            "messages": ("messages", "SELECT 'rows', received_at FROM messages"),
            "outbox": ("outbox", "SELECT IIF(sent_at IS NULL, 'unsent', 'sent'), created_at FROM outbox"),
            "drafts": ("drafts", "SELECT state, created_at FROM drafts")})
        doc["messages"] = _tally(cutoff, ((k, _when(t)) for k, t in rows["messages"]), ("rows",))
        doc["outbox"] = _tally(cutoff, ((k, _when(t)) for k, t in rows["outbox"]), ("sent", "unsent"))
        drafts = (("open" if s in TRANSITIONS else "closed", _when(t)) for s, t in rows["drafts"])
        doc["drafts"] = {k: v for k, v in _tally(cutoff, drafts, ("closed", "open")).items() if k != "oldest"}
    except sqlite3.DatabaseError: doc["messages"] = doc["outbox"] = doc["drafts"] = UNAVAILABLE
    for key, folder, scan in (("screenshots", sdir / "screenshots", _shots), ("media", mroot, _media),
                              ("backups", bdir, _backups)):
        try: doc[key] = None if folder is None else scan(folder, cutoff)
        except OSError: doc[key] = UNAVAILABLE
    doc["deletes"] = 0
    return doc

def _days(raw) -> int:
    with contextlib.suppress(ValueError):
        if raw.isdigit() and 1 <= (n := int(raw)) <= MAX_DAYS: return n
    raise argparse.ArgumentTypeError(f"--days must be a whole number from 1 to {MAX_DAYS}")

def _now(raw) -> datetime:
    if (dt := _when(raw)) is None: raise argparse.ArgumentTypeError("--now must be a timezone-aware ISO-8601 time")
    return dt

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="retention.py", description="Read-only retention report (H21).")
    rep = parser.add_subparsers(dest="cmd", required=True).add_parser("report")
    rep.add_argument("--state", required=True)
    rep.add_argument("--days", required=True, type=_days)
    rep.add_argument("--now", type=_now)
    for flag in ("--media", "--backups"): rep.add_argument(flag)
    args = parser.parse_args(argv)
    try:
        doc = report(args.state, args.days, media=args.media, backups=args.backups, now=args.now)
    except Unsafe as exc:
        print(f"retention: unsafe: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(doc))
    return 1 if UNAVAILABLE in doc.values() else 0

if __name__ == "__main__":
    sys.exit(main())
