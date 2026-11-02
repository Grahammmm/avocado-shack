"""Hass history op (H06): ``history.revert`` undoes one applied change as a new, conflict-checked inverse change.

Only the records that change touched are set back, and only when each still holds the value that change wrote, so
later edits to other records are kept. A record the change created is hidden/cancelled, never deleted. The A2 writer
sets ``revertedBy`` on the original change record once the revert is committed.
An undo of an undo is refused, so the original keeps ``revertedBy``; to bring a change back, ask for it again.
An undo that cancels a hike, moves its start or turns its RSVPs off carries the forward op's guest warning, never a
refusal, and only when the undo is drafted.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

from hass.ops import COLLECTIONS, Arg, Op, Refused, Touched
from hass.ops.hikes import _guest_warning, _move_warning, _seats

# What "undo an addition" means per collection: hide or cancel, never delete.
UNDO_ADDITION = {"products": ("status", "hidden"), "events": ("status", "cancelled"), "makers": ("hidden", True)}


def _items(content, collection):
    return {"products": content.products, "events": content.community["events"],
            "routeIdeas": content.community["routeIdeas"]}[collection]


def _current(content, collection, key):
    if collection == "store":
        return content.store
    if collection == "makers":
        return content.makers.get(key)
    return next((item for item in _items(content, collection) if item.get("id") == key), None)


def _put(content, collection, key, value):
    if collection == "store":
        content.store.clear()
        content.store.update(value)
    elif collection == "makers":
        content.makers[key] = value
    else:
        items = _items(content, collection)
        items[next(i for i, item in enumerate(items) if item.get("id") == key)] = value


def _well_formed(change):
    """Shape check before any use: a dict whose ``records`` (if any) are dicts naming a known collection and str key."""
    if not isinstance(change, dict):
        return False
    records = change.get("records")
    if records is None:
        return True
    return isinstance(records, list) and all(
        isinstance(r, dict) and r.get("collection") in COLLECTIONS and isinstance(r.get("key"), str)
        and "before" in r and "after" in r for r in records)


def _draft_ops(ctx, change_id):
    """Ops of ``<state>/drafts/<id>.json`` ([] when absent); False for a symlink or an unreadable/malformed draft."""
    path = Path(ctx.state_dir) / "drafts" / f"{change_id}.json"  # state_dir is set: ctx.change found the record
    if not (path.is_symlink() or path.exists()):
        return []
    try:
        ops = None if path.is_symlink() else json.loads(path.read_text("utf-8")).get("ops")
    except (OSError, UnicodeDecodeError, ValueError, AttributeError, RecursionError):
        return False
    return ops if isinstance(ops, list) and all(isinstance(call, dict) for call in ops) else False


def _event_warning(ctx, current, before):
    """The forward op's guest warning for undoing a scheduled hike back to ``before`` (a callable), or None."""
    if not isinstance(current, dict) or current.get("status") != "scheduled":
        return None
    if before is None or before.get("status") == "cancelled" or (current.get("rsvpEnabled")
                                                                    and not before.get("rsvpEnabled")):
        return lambda: _guest_warning(ctx, current)  # cancels the hike or turns RSVPs off: one warning
    if (current.get("rsvpEnabled") and before.get("status") == "scheduled"  # as hike.update: no RSVPs, no move warning
            and before.get("startsAt") != current.get("startsAt")):
        return lambda: _move_warning(ctx, current, before["startsAt"])
    return None


def _revert(content, args, ctx):
    change_id = args["changeId"]
    try:
        change = ctx.change(change_id)
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return Refused(f"{change_id} record is unreadable")
    if change is None:
        return Refused(f"unknown change {change_id}")
    if not _well_formed(change):
        return Refused(f"{change_id} record is malformed")
    if change.get("state") != "applied":
        return Refused(f"{change_id} is not an applied change")
    if change.get("revertedBy"):
        return Refused(f"{change_id} was already undone by {change['revertedBy']}")
    if (ops := _draft_ops(ctx, change_id)) is False:
        return Refused(f"{change_id} draft is unreadable")
    if any(call.get("op") == "history.revert" for call in ops):
        return Refused(f"{change_id} is an undo; to bring the change back, ask for it again")
    first, last = {}, {}  # per record: the value before the change and the value the change finally wrote
    for record in change.get("records") or []:
        ref = (record["collection"], record["key"])
        first.setdefault(ref, record["before"])
        last[ref] = record["after"]
    if not first:
        return Refused(f"{change_id} touched no records")
    for (collection, key), after in last.items():
        if _current(content, collection, key) != after:
            return Refused(f"conflict: {collection} {key} changed after {change_id}")
    touched, pending = [], []  # pending: guest warnings, added only once the whole undo is drafted
    for (collection, key), before in first.items():
        current = copy.deepcopy(_current(content, collection, key))
        if before is not None:
            value = copy.deepcopy(before)
            if collection == "events":
                if "capacity" in value:
                    seats = _seats(ctx, key)
                    if isinstance(seats, Refused):
                        return seats
                    if value["capacity"] < seats:
                        return Refused(f"capacity {value['capacity']} is below {seats} confirmed guests")
                if (value["status"] == "scheduled"
                        and datetime.fromisoformat(value["startsAt"].replace("Z", "+00:00")) <= ctx.now):
                    return Refused("start is in the past")
        elif collection in UNDO_ADDITION:
            field, hidden = UNDO_ADDITION[collection]
            value = {**(current or {}), field: hidden}
        else:
            return Refused(f"undo cannot remove the added {collection} {key}")
        if value != current:
            _put(content, collection, key, value)
            touched.append(Touched(collection, key, current, copy.deepcopy(value)))
            if collection == "events" and (warn := _event_warning(ctx, current, before)):
                pending.append(warn)
    for warn in pending:  # only reached when nothing was refused; non-empty pending means touched is non-empty
        warn()
    return touched or Refused(f"undoing {change_id} changes nothing")


OPS = (Op("history.revert", {"changeId": Arg("id")}, _revert),)
