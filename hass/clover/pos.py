"""HASS-POS-1: plain-English till views from the PRIVATE cache only: fixed templates, no model, no network, no token (docs/hass/POS.md).
Staleness is reads.freshness. "Sold" is the sum of the positive count drops between consecutive per-read snapshots of the cache (a count
that went up is a restock, never a negative sale). Nothing is added back: a stock edit (Hass's own or a hand edit at the register) between
two reads shows as a drop too, so every sold number says "includes stock edits".
"""
import json
import os
import re
import stat
import tempfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from hass.clover import cache, reads, reports
from hass.clover.mapper import format_quantity

LABEL = "includes stock edits"
NOTE = "(count drops between till reads, not exact sales)"
DATED = re.compile(r"(\d{4}-\d{2}-\d{2})-pos\.md")
low = reads.low_stock


def _say(snapshot, now, reachable, body):
    state, label = reads.freshness(snapshot, now, reachable)
    return reads._wrap(state, label, body)


def since_day(now, days):
    return now.astimezone(reads.PACIFIC).date() - timedelta(days=days - 1)


def drop_rows(snapshot, snaps, now, days, unsure=None):
    """[(item, units)] biggest first, or None when no earlier count covers the period. units = the sum of the positive drops of the item's count
    between consecutive reads from one hour before Pacific midnight of the first day up to the read now (a rise is a restock: ignored, never
    negative). An item seen in an earlier read that is missing a count in any read, the latest included, of the period has no number and is appended to `unsure`: never guessed."""
    start = datetime.combine(since_day(now, days), time.min, reads.PACIFIC) - timedelta(hours=1)
    series = [c for t, c in sorted(snaps, key=lambda s: s[0]) if start <= t < snapshot.fetched_at]
    if not series:
        return None
    series.append({i.id: i.stock for i in snapshot.items if i.stock is not None})
    rows, vague = [], []
    for item in snapshot.items:
        if not any(item.id in c for c in series[:-1]):
            continue
        if not all(item.id in c for c in series):   # also the case when the latest read has no count (item.stock is None)
            vague.append(item.name)
            continue
        counts = [c[item.id] for c in series]
        rows.append((item, sum((a - b for a, b in zip(counts, counts[1:]) if a > b), Decimal(0))))
    if unsure is not None:
        unsure += sorted(vague)
    return sorted(((i, n) for i, n in rows if n > 0), key=lambda r: (-r[1], r[0].name))


def drops(snapshot, snaps, now, reachable=True, days=1, show=reads._as_is):
    """'what sold today' (days=1) or 'this week' (days=7): count drops between reads, labelled as including stock edits."""
    left = []
    when, rows = ("today" if days == 1 else "this week"), drop_rows(snapshot, snaps, now, days, left)
    head = f"Sold {when} ({LABEL})"
    if rows is None:
        body = f"I don't have an earlier till count to compare with yet, so I can't say what sold {when} ({LABEL}) {NOTE}"
    elif not rows:
        body = f"{head}: nothing, no count dropped {NOTE}"
    else:
        body = f"{head}: " + ", ".join(f"{show(i.name)} {format_quantity(n)}" for i, n in rows[:5]) + f" {NOTE}"
    if left:
        body += f" Left out: {', '.join(show(n) for n in left)} (a count was missing in one of the reads)."
    return _say(snapshot, now, reachable, body)


def _units(rows):
    return format_quantity(sum((n for _, n in rows), Decimal(0)))


def _incomplete(left):
    return f"incomplete: {len(left)} item{'' if len(left) == 1 else 's'} left out" if left else ""


def summary(snapshot, snaps, now, content, links, reachable=True, threshold=5):
    sold, few, none = (len(r) for r in reports.low_stock(snapshot, threshold)["sections"].values())
    sec = reports.till_vs_site(snapshot, content, links)["sections"]
    left = []
    rows = drop_rows(snapshot, snaps, now, 1, left)
    tail = "not enough history yet" if rows is None else f"{len(rows)} items, {_units(rows)} units" + (f", {_incomplete(left)}" if left else "")
    return _say(snapshot, now, reachable, f"Till at {reads.when(snapshot.fetched_at, now)}: {len(snapshot.items)} items, {sold} sold out, "
                f"{few} running low, {none} with no count. Website: {len(links) - len(sec['Broken links'])} linked, "
                f"stock words waiting: not available yet. Sold today ({LABEL}): {tail}.")


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


def build(snapshot, snaps, now, content, links, reachable=True, threshold=5):
    """(markdown, totals): the private daily report, and the totals-only dict (counts, flags and a date: no name, price or SKU)."""
    left = []
    today = drop_rows(snapshot, snaps, now, 1, left)
    sold, few, none = (len(r) for r in reports.low_stock(snapshot, threshold)["sections"].values())
    totals = {"asOf": snapshot.fetched_at.isoformat(), "items": len(snapshot.items), "soldOut": sold, "low": few, "noCount": none,
              "stockWordsWaiting": None,   # unavailable until the STOCK-SITE totals integration: a till/site mismatch is not a pending count
              "countDropItems": None if today is None else len(today),
              "countDropUnits": None if today is None else _units(today), "countDropNote": LABEL, "countDropLeftOut": len(left),
              "countDropIncomplete": _incomplete(left) or None, "tillReachable": bool(reachable),
              "snapshot": reads.freshness(snapshot, now, reachable)[0]}
    a, safe = (snapshot, snaps, now, reachable), reports._safe
    lines = ["# Till summary", "", summary(snapshot, snaps, now, content, links, reachable, threshold), "",
             f"## Sold today ({LABEL})", "", drops(*a, 1, safe), "", f"## Sold this week ({LABEL})", "", drops(*a, 7, safe), "",
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
