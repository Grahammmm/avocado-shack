"""Hass history op (H06): ``history.revert`` undoes one applied change as a new, conflict-checked inverse change.

Only the records that change touched are set back, and only when each still holds the value that change wrote, so
later edits to other records are kept. A record the change created is hidden/cancelled, never deleted. The A2 writer
sets ``revertedBy`` on the original change record once the revert is committed.
"""

from __future__ import annotations

import copy
from datetime import datetime

from hass.ops import Arg, Op, Refused, Touched
from hass.ops.hikes import _seats

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


def _revert(content, args, ctx):
    change_id = args["changeId"]
    change = ctx.change(change_id)
    if change is None:
        return Refused(f"unknown change {change_id}")
    if change.get("state") != "applied":
        return Refused(f"{change_id} is not an applied change")
    if change.get("revertedBy"):
        return Refused(f"{change_id} was already undone by {change['revertedBy']}")
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
    touched = []
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
    return touched or Refused(f"undoing {change_id} changes nothing")


OPS = (Op("history.revert", {"changeId": Arg("id")}, _revert),)
