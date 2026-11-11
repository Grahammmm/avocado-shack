"""HASS-CLOVER-1: read-only answers from a snapshot of the till, with the staleness label and the unreachable behaviour.

A Snapshot is the last items-and-stock pull plus when it was taken. Answers are plain text from fixed templates: no model writes or reads them.
Nothing here asks Clover anything; the scheduler or an on-demand pull fills the snapshot (docs/hass/CLOVER.md, "Sync").

Staleness (design question 6): a count under 20 minutes old is quoted as is; older gets "as of <time>"; when Clover cannot be reached the
answer says so and quotes the last count labelled as old; a snapshot over 24 hours old is not quoted at all.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from hass.clover.mapper import format_quantity, norm_name, suggest

PACIFIC = ZoneInfo("America/Los_Angeles")
FRESH = timedelta(minutes=20)
TOO_OLD = timedelta(hours=24)
LIST_LIMIT = 15


@dataclass(frozen=True)
class Snapshot:
    items: tuple
    fetched_at: datetime       # timezone-aware


def when(moment, now):
    t = moment.astimezone(PACIFIC)
    clock = f"{t.hour % 12 or 12}:{t.minute:02d} {'am' if t.hour < 12 else 'pm'}"
    return clock if t.date() == now.astimezone(PACIFIC).date() else f"{t:%a} {clock}"


def freshness(snapshot, now, reachable=True):
    """(state, label): state is fresh | stale | unreachable | too-old; label is the sentence to put before or after an answer."""
    age = now - snapshot.fetched_at
    if age > TOO_OLD:
        return "too-old", (f"I have not been able to read the till since {when(snapshot.fetched_at, now)}, "
                           "so I will not quote a count that old. Check the till, or ask me again in a few minutes.")
    if not reachable:
        return "unreachable", f"I can't reach the till right now. The last count I have is from {when(snapshot.fetched_at, now)}, so treat it as old."
    if age > FRESH:
        return "stale", f"(till count as of {when(snapshot.fetched_at, now)})"
    return "fresh", ""


def _count(item):
    return "the till keeps no count" if item.stock is None else f"{format_quantity(item.stock)} in the till"


def _wrap(state, label, body):
    if state == "too-old":
        return label
    if state == "unreachable":
        return f"{label} {body}"
    return f"{body} {label}".strip()


def how_many(query, snapshot, now, reachable=True):
    """'how many Sunshine olive oil do we have'."""
    state, label = freshness(snapshot, now, reachable)
    if state == "too-old":
        return label
    exact = [i for i in snapshot.items if norm_name(i.name) == norm_name(query) or (i.sku and i.sku.casefold() == norm_name(query))]
    visible = [i for i in exact if not i.hidden] or exact
    if len(visible) > 1:
        body = "More than one item is called that: " + "; ".join(f"{i.name} (SKU {i.sku or 'none'}): {_count(i)}" for i in visible[:5]) + "."
    elif visible:
        i = visible[0]
        body = f"{i.name}: {_count(i)}." + (" It is hidden on the till." if i.hidden else "")
    else:
        near = suggest(query, snapshot.items)
        if len(near) == 1:
            i = near[0]
            body = f"I can't find exactly that. The closest is {i.name}: {_count(i)}."
        elif near:
            body = "I can't find exactly that. Did you mean " + ", ".join(i.name for i in near) + "?"
        else:
            body = "I can't find anything like that in the till."
    return _wrap(state, label, body)


def low_stock(snapshot, now, threshold, reachable=True):
    """'low stock': counted, visible items at or under `threshold`, sold out ones first."""
    state, label = freshness(snapshot, now, reachable)
    if state == "too-old":
        return label
    counted = [i for i in snapshot.items if not i.hidden and i.stock is not None]
    low = sorted((i for i in counted if i.stock <= threshold), key=lambda i: (i.stock, i.name))
    # One combined limit across both groups (sold out first), so "And N more" counts exactly the items not shown.
    out = [i for i in low if i.stock <= 0][:LIST_LIMIT]
    more = [i for i in low if i.stock > 0][:LIST_LIMIT - len(out)]
    parts = []
    if out:
        parts.append("Sold out: " + ", ".join(i.name for i in out) + ".")
    if more:
        parts.append(f"Low ({threshold} or fewer): " + ", ".join(f"{i.name} {format_quantity(i.stock)}" for i in more) + ".")
    omitted = len(low) - len(out) - len(more)
    if omitted:
        parts.append(f"And {omitted} more.")
    untracked = sum(1 for i in snapshot.items if not i.hidden and i.stock is None)
    body = " ".join(parts) or "Nothing is low."
    if untracked:
        body += f" {untracked} item(s) have no count in the till, so I can't tell."
    return _wrap(state, label, body)
