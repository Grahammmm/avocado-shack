"""Hass store ops (H13): ``store.set_hours`` and ``store.set_address`` change the opening-hours lines and the
street address / town shown on the site, through the normal typed-op path (draft, approval, single writer).

Usage (request ops):
    {"op": "store.set_hours", "args": {"hours": ["Monday–Saturday 9am–6pm", "Closed Sunday"]}}
    {"op": "store.set_address", "args": {"streetAddress": "1023 Example Street"}}   # town kept; give either or both

Limits: at most 7 hours lines of at most 60 characters, no repeated line; street and town at most 80 characters.
Text kinds already reject markup, ``$`` and control characters. ``name`` and ``schemaVersion`` are not editable.

Selective-undo limit: the store is ONE record, so ``history.revert`` of an older store change after a later store
change is refused as a conflict (``conflict: store store changed after <id>``). Undo the newest store change first.
"""

from __future__ import annotations

import copy

from hass.ops import Arg, NeedsDetails, Op, Refused, Touched

MAX_HOURS_LINES, MAX_HOURS_LINE, MAX_ADDRESS_PART = 7, 60, 80


def _touch(before, store):
    return [Touched("store", "store", before, copy.deepcopy(store))]


def _set_hours(content, args, ctx):
    hours = list(args["hours"])
    if len(hours) > MAX_HOURS_LINES:
        return Refused(f"at most {MAX_HOURS_LINES} hours lines")
    for i, line in enumerate(hours):
        if len(line) > MAX_HOURS_LINE:
            return Refused(f"hours line {i} is longer than {MAX_HOURS_LINE} characters")
    if len(set(hours)) != len(hours):
        return Refused("hours lines must not repeat")
    if hours == content.store["hours"]:
        return Refused("store hours are already " + " / ".join(hours))
    before = copy.deepcopy(content.store)
    content.store["hours"] = hours
    return _touch(before, content.store)


def _set_address(content, args, ctx):
    given = {f: args[f] for f in ("streetAddress", "town") if f in args}
    if not given:
        return NeedsDetails(["streetAddress", "town"], "Which street address or town should the site show?")
    for field, value in given.items():
        if len(value) > MAX_ADDRESS_PART:
            return Refused(f"{field} is longer than {MAX_ADDRESS_PART} characters")
    store = content.store
    if all(store[f] == v for f, v in given.items()):
        return Refused(f"store address is already {store['streetAddress']}, {store['town']}")
    before = copy.deepcopy(store)
    store.update(given)
    return _touch(before, store)


OPS = (
    Op("store.set_hours", {"hours": Arg("text_list")}, _set_hours),
    Op("store.set_address", {"streetAddress": Arg("text", required=False), "town": Arg("text", required=False)},
       _set_address),
)
