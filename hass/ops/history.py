"""Hass history op (H06): ``history.revert`` undoes one applied change as a new, conflict-checked inverse change.

Only the records that change touched are set back, and only when each still holds the value that change wrote, so
later edits to other records are kept. The store is one record, but undo is field-selective: only the store fields
that change wrote (hours, streetAddress, town, intro, headline, story, homeImage, notice, phone, selection_checked_on)
are set back and checked, so later edits to other store fields are kept; a later differing value in one of those
fields is a conflict. A field's value (a notice with its dates, the hours list) is one indivisible unit. A record the change created is hidden/cancelled, never deleted, except an added
route idea (no hidden state), which is removed. An added product is hidden without the stock word and day the change
gave it (SKILLS-ITEMADD-1: a new item and today's shelf check undo together). The A2 writer
sets ``revertedBy`` on the original change record once the revert is committed.
An undo of an undo is refused, so the original keeps ``revertedBy``; to bring a change back, send ``again <code>`` with the original draft's code.
An undo that cancels a hike, moves its start or turns its RSVPs off carries the forward op's guest warning, never a
refusal, and only when the undo is drafted; so does one that changes its meeting place, meet time or route.
"""

from __future__ import annotations

import copy
import json
import os
import stat
from datetime import datetime
from pathlib import Path

from hass.ops import COLLECTIONS, Arg, Op, Refused, Touched
from hass.ops.catalog import _maker_problem, _restore_image_problem
from hass.ops.hikes import _guest_warning, _meeting_warning, _move_warning, _seats

# What "undo an addition" means per collection: hide or cancel, never delete.
UNDO_ADDITION = {"products": ("status", "hidden"), "events": ("status", "cancelled"), "makers": ("hidden", True)}


def _items(content, collection):
    return {"products": content.products, "events": content.community["events"],
            "routeIdeas": content.community["routeIdeas"]}[collection]


def _current(content, collection, key):
    if collection == "store":
        return content.store
    if collection == "club":
        return content.community["club"]
    if collection == "makers":
        return content.makers.get(key)
    return next((item for item in _items(content, collection) if item.get("id") == key), None)


def _put(content, collection, key, value):
    if collection in ("store", "club"):
        target = content.store if collection == "store" else content.community["club"]
        target.clear()
        target.update(value)
    elif collection == "makers":
        content.makers[key] = value
    else:
        items = _items(content, collection)
        index = next(i for i, item in enumerate(items) if item.get("id") == key)
        if value is None:  # only an added route idea (UNDO_ADDITION has no hidden state for it)
            del items[index]
        else:
            items[index] = value


_MISSING = object()  # a store key that is absent (distinct from an explicit null)


def _store_write_set(records):
    """Top-level store keys whose presence or value differs between before and after, over one change's store records."""
    keys = set()
    for record in records:
        before, after = record["before"], record["after"]
        keys |= {k for k in before.keys() | after.keys() if before.get(k, _MISSING) != after.get(k, _MISSING)}
    return keys


def _store_shape_ok(record):
    return record["key"] == "store" and isinstance(record["before"], dict) and isinstance(record["after"], dict)


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


def _before_ok(collection, before):
    """RF0310-5: a stored ``before`` undo can put back: None, a dict, and for a hike a text status, a text start that
    parses with its zone and (if present) an int capacity, so the seat and past-start checks never raise."""
    if before is None or (isinstance(before, dict) and collection != "events"):
        return True
    if not isinstance(before, dict) or not isinstance(before.get("status"), str) or (
            "capacity" in before and type(before["capacity"]) is not int):
        return False
    try:
        return datetime.fromisoformat(before["startsAt"].replace("Z", "+00:00")).utcoffset() is not None
    except (KeyError, AttributeError, TypeError, ValueError):
        return False


def _draft_ops(ctx, change_id):
    """Ops of ``<state>/drafts/<id>.json`` ([] when absent); False for a symlink or an unreadable/malformed draft."""
    path = Path(ctx.state_dir) / "drafts" / f"{change_id}.json"  # state_dir is set: ctx.change found the record
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):  # link, FIFO, socket, folder: never opened
            return False
    except FileNotFoundError:
        return []
    except OSError:
        return False
    try:
        ops = json.loads(path.read_text("utf-8")).get("ops")
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
    if current.get("rsvpEnabled") and before.get("status") == "scheduled":  # as hike.update: no RSVPs, no warning
        def warn():  # the move warning, then the meeting place, meet time and route ones (AV2137-02)
            if before.get("startsAt") != current.get("startsAt"):
                _move_warning(ctx, current, before["startsAt"])
            _meeting_warning(ctx, current, before)
        return warn
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
        return Refused(f"{change_id} is an undo; to bring the change back, use again <code> with the original draft code")
    first, last = {}, {}  # per record: the value before the change and the value the change finally wrote
    store_records = [r for r in change.get("records") or [] if r["collection"] == "store"]
    if not all(_store_shape_ok(r) for r in store_records):
        return Refused(f"{change_id} record is malformed")
    write_set = _store_write_set(store_records)
    for record in change.get("records") or []:
        ref = (record["collection"], record["key"])
        first.setdefault(ref, record["before"])
        last[ref] = record["after"]
    if not first:
        return Refused(f"{change_id} touched no records")
    if not all(_before_ok(collection, before) for (collection, _), before in first.items()):
        return Refused(f"{change_id} record is malformed")
    for (collection, key), after in last.items():
        if collection == "store":
            if any(content.store.get(k, _MISSING) != after.get(k, _MISSING) for k in write_set):
                return Refused(f"conflict: {collection} {key} changed after {change_id}")
        elif _current(content, collection, key) != after:
            return Refused(f"conflict: {collection} {key} changed after {change_id}")
    touched, pending = [], []  # pending: guest warnings, added only once the whole undo is drafted
    for (collection, key), before in first.items():
        current = copy.deepcopy(_current(content, collection, key))
        if collection == "store":  # only the fields this change wrote; every other current field stays
            value = copy.deepcopy(current)
            for k in write_set:
                if k in before:
                    value[k] = copy.deepcopy(before[k])
                else:
                    value.pop(k, None)
        elif before is not None:
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
            elif collection == "products" and value.get("status") == "active" and (current or {}).get("status") != "active":
                # making a product active again: the same checks as product.restore (_set_status)
                if refused := _maker_problem(content, value.get("producerKey")):
                    return refused
                if refused := _restore_image_problem(ctx, key, value.get("image")):
                    return refused
        elif collection in UNDO_ADDITION:
            field, hidden = UNDO_ADDITION[collection]
            value = {**(current or {}), field: hidden}
            if collection == "products":  # its stock word and day came with this change: they go with it, so the
                value.pop("available", None)  # day never outlives the shelf-check day the same undo sets back
                value.pop("available_on", None)
        elif collection == "routeIdeas":  # an added route idea is removed (hide is a separate op)
            hike = next((e for e in content.community["events"] if e.get("trailId") == key), None)
            if hike is not None:  # any status: the validator checks every hike's trailId
                return Refused(f"{hike['id']} ({hike['title']}) uses this route; change that hike first")
            value = None
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
