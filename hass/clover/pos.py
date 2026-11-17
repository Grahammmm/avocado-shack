"""HASS-POS-1: plain-English till views from the PRIVATE cache only: fixed templates, no model, no network, no token (docs/hass/POS.md).
Staleness is reads.freshness. Count drops come from the cache's per-read snapshots; Hass's own journalled receipts are added back, a hand edit
at the register is not, so every drops reply says "count drops, not exact sales".
"""
import json
import os
import re
import sqlite3
import stat
import tempfile
from contextlib import closing
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from hass.clover import cache, reads, reports
from hass.clover.mapper import format_quantity

NOTE = "(count drops, not exact sales: a recount or a till edit also shows here)"
DATED = re.compile(r"(\d{4}-\d{2}-\d{2})-pos\.md")
low = reads.low_stock


def _say(snapshot, now, reachable, body):
    state, label = reads.freshness(snapshot, now, reachable)
    return reads._wrap(state, label, body)


def since_day(now, days):
    return now.astimezone(reads.PACIFIC).date() - timedelta(days=days - 1)


def journal_deltas(state, identity, since):
    """[(day, item id, change)]: Hass's own applied count changes on or after `since` (ISO day); [] when there is no journal."""
    path = Path(state) / "clover" / "journal.sqlite3"
    try:
        if not cache._private_dir(path.parent, False) or not cache._private_file(path, False):
            return []
        with closing(sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=5)) as db:
            if db.execute("SELECT v FROM meta WHERE k='identity'").fetchone()[0] != json.dumps(list(identity)):
                return []
            rows = db.execute("SELECT day, result FROM changes WHERE status='applied' AND day >= ?", (since,)).fetchall()
        entries = [(day, json.loads(result)) for day, result in rows]
        return [(day, e["item_id"], Decimal(e["after"]["stock"]) - Decimal(e["before"]["stock"]))
                for day, e in entries if e["kind"] == "set_stock" and e["before"]["stock"] is not None]
    except (cache.CacheUnsafe, sqlite3.Error, ValueError, KeyError, TypeError, ArithmeticError):
        return []


def drop_rows(snapshot, snaps, deltas, now, days):
    """[(item, units)] biggest first, or None when no earlier count covers the period. units = count before - count now + Hass's own change."""
    first = since_day(now, days)
    start = datetime.combine(first, time.min, reads.PACIFIC) - timedelta(hours=1)
    base = next((c for t, c in snaps if start <= t < snapshot.fetched_at), None)
    if base is None:
        return None
    own = {}
    for day, iid, change in deltas:
        if day >= first.isoformat():
            own[iid] = own.get(iid, 0) + change
    rows = [(i, base[i.id] - i.stock + own.get(i.id, 0)) for i in snapshot.items if i.stock is not None and i.id in base]
    return sorted(((i, n) for i, n in rows if n > 0), key=lambda r: (-r[1], r[0].name))


def drops(snapshot, snaps, deltas, now, reachable=True, days=1, show=reads._as_is):
    """'what sold today' (days=1) or 'this week' (days=7): the biggest count drops, never claimed as sales."""
    label, rows = ("today" if days == 1 else "this week"), drop_rows(snapshot, snaps, deltas, now, days)
    if rows is None:
        body = f"I don't have an earlier till count to compare with yet, so no count drops {label} {NOTE}"
    elif not rows:
        body = f"No count drops {label} {NOTE}"
    else:
        body = f"Biggest count drops {label}: " + ", ".join(f"{show(i.name)} {format_quantity(n)}" for i, n in rows[:5]) + f" {NOTE}"
    return _say(snapshot, now, reachable, body)


def _units(rows):
    return format_quantity(sum((n for _, n in rows), Decimal(0)))


def summary(snapshot, snaps, deltas, now, content, links, reachable=True, threshold=5):
    sold, few, none = (len(r) for r in reports.low_stock(snapshot, threshold)["sections"].values())
    sec = reports.till_vs_site(snapshot, content, links)["sections"]
    rows = drop_rows(snapshot, snaps, deltas, now, 1)
    tail = "not enough history yet" if rows is None else f"{len(rows)} items, {_units(rows)} units"
    return _say(snapshot, now, reachable, f"Till at {reads.when(snapshot.fetched_at, now)}: {len(snapshot.items)} items, {sold} sold out, "
                f"{few} running low, {none} with no count. Website: {len(links) - len(sec['Broken links'])} linked, "
                f"{len(sec['Stock word disagreements'])} stock words waiting. Count drops today: {tail}.")


def price_of(query, snapshot, now, reachable=True, show=reads._as_is):
    """'price of honey': price and count, with the time of the till read."""
    hits = reads.exact(query, snapshot)
    if not hits:
        return _say(snapshot, now, reachable, reads._not_exact(query, snapshot, show))
    each = [f"{show(i.name)}: " + ("no price set" if i.price_cents is None else f"${i.price_cents // 100}.{i.price_cents % 100:02d} "
            + (f"per {i.unit_name}" if i.unit_name else "each")) + f", {reads._count(i)}" + ("; hidden on the till" if i.hidden else "") for i in hits[:5]]
    as_of = f" (as of {reads.when(snapshot.fetched_at, now)})" if reads.freshness(snapshot, now, reachable)[0] in ("fresh", "stale") else ""
    return _say(snapshot, now, reachable, "; ".join(each) + as_of + ".")


def website_vs_till(snapshot, content, links, now, reachable=True, show=reads._as_is):
    """The existing mismatch report as text: each heading with up to five rows."""
    parts = [f"{h}: " + ("; ".join(show(r) for r in rows[:5]) + (f"; and {len(rows) - 5} more" if len(rows) > 5 else "") if rows else "none")
             for h, rows in reports.till_vs_site(snapshot, content, links)["sections"].items()]
    return _say(snapshot, now, reachable, "Website vs till. " + ". ".join(parts) + ".")


def build(snapshot, snaps, deltas, now, content, links, reachable=True, threshold=5):
    """(markdown, totals): the private daily report, and the totals-only dict (counts, flags and a date: no name, price or SKU)."""
    today = drop_rows(snapshot, snaps, deltas, now, 1)
    sold, few, none = (len(r) for r in reports.low_stock(snapshot, threshold)["sections"].values())
    totals = {"asOf": snapshot.fetched_at.isoformat(), "items": len(snapshot.items), "soldOut": sold, "low": few, "noCount": none,
              "stockWordsWaiting": len(reports.till_vs_site(snapshot, content, links)["sections"]["Stock word disagreements"]),
              "countDropItems": None if today is None else len(today),
              "countDropUnits": None if today is None else _units(today), "tillReachable": bool(reachable),
              "snapshot": reads.freshness(snapshot, now, reachable)[0]}
    a, safe = (snapshot, snaps, deltas, now, reachable), reports._safe
    lines = ["# Till summary", "", summary(snapshot, snaps, deltas, now, content, links, reachable, threshold), "",
             "## Count drops today", "", drops(*a, 1, safe), "", "## Count drops this week", "", drops(*a, 7, safe), "",
             "## Low stock", "", low(snapshot, now, threshold, reachable, safe), "", "## Website versus till", "",
             website_vs_till(snapshot, content, links, now, reachable, safe), ""]
    return "\n".join(lines), totals


def _put(folder, name, text):
    target = folder / name
    if target.exists() or target.is_symlink():
        st = target.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1:
            raise cache.CacheUnsafe("file")
    fd, tmp = tempfile.mkstemp(prefix=".report-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_files(state, built, now, out=None):
    """`<day>-pos.md` and `pos-totals.json` (0600, folder 0700, atomic); dated pos files of 90 days or more are pruned, as reports.py does."""
    root = Path(state) / "clover"
    cache._private_dir(root, create=True)
    folder = Path(out).absolute() if out is not None else root / "reports"
    if any(p.is_symlink() for p in (folder, *folder.parents)):
        raise cache.CacheUnsafe("folder")
    cache._private_dir(folder, create=True)
    today = now.astimezone(reads.PACIFIC).date()
    _put(folder, f"{today.isoformat()}-pos.md", built[0])
    _put(folder, "pos-totals.json", json.dumps(built[1], sort_keys=True) + "\n")
    for path in folder.iterdir():
        match = DATED.fullmatch(path.name)
        try:
            old = bool(match) and date.fromisoformat(match[1]) <= today - timedelta(days=90)
        except ValueError:
            continue
        st = path.lstat()
        if old and stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and st.st_nlink == 1:
            path.unlink()
