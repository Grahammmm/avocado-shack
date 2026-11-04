"""Hass store ops (H13): ``store.set_hours`` and ``store.set_address`` change the opening-hours lines and the
street address / town shown on the site, through the normal typed-op path (draft, approval, single writer).

Usage (request ops):
    {"op": "store.set_hours", "args": {"hours": ["Monday–Saturday 9am–6pm", "Closed Sunday"]}}
    {"op": "store.set_address", "args": {"streetAddress": "1023 Example Street"}}   # town kept; give either or both
    {"op": "store.confirm_selection", "args": {"yes": ["photo-product-001"], "no": ["photo-product-002"]}}   # an earlier "date" at most 7 days ago
    {"op": "store.set_intro", "args": {"text": "Fresh from the coast."}}   # home-page intro line, at most 160 characters; undo restores the default

``store.confirm_selection``: a product may appear once across yes/limited/no.
Limits: at most 7 hours lines of at most 60 characters, no repeated line (case, spacing and dash style
ignored; the refusal names both line numbers); street and town at most 80 characters.
Each hours line needs a letter or digit, and street and town each need a letter (the refusal names the line or field).
Text kinds already reject markup, ``$`` and control characters. ``name`` and ``schemaVersion`` are not editable.

Selective-undo limit: the store is ONE record, so ``history.revert`` of an older store change after a later store
change is refused as a conflict (``conflict: store store changed after <id>``). Undo the newest store change first.
"""

from __future__ import annotations

import copy
import unicodedata
from datetime import date

from hass.content_model import (
    AVAILABILITY, DEFAULT_INTRO, MAX_ADDRESS_PART, MAX_HOURS_LINE, MAX_HOURS_LINES, MAX_INTRO, checked_on, shop_today,
)
from hass.ops import Arg, NeedsDetails, Op, Refused, Touched
from hass.ops.catalog import _product
from hass.sitegen import STALE_AFTER_DAYS


_DASHES = {c: "-" for c in [*range(0x2010, 0x2016), 0x2212]}


def _line_key(line):
    """Repeat key for an hours line: case, spacing and dash style ignored; accents kept (never stored)."""
    return " ".join(unicodedata.normalize("NFKC", line).translate(_DASHES).split()).casefold()


def _spaced(text):
    """Already-check key: spacing only; case and characters kept (the page renders runs of spaces as one)."""
    return " ".join(text.split())


def _touch(before, store):
    return [Touched("store", "store", before, copy.deepcopy(store))]


def _set_hours(content, args, ctx):
    hours = list(args["hours"])
    if len(hours) > MAX_HOURS_LINES:
        return Refused(f"at most {MAX_HOURS_LINES} hours lines (you sent {len(hours)})")
    for i, line in enumerate(hours):
        if len(line) > MAX_HOURS_LINE:
            return Refused(f"hours line {i + 1} is longer than {MAX_HOURS_LINE} characters")
    for i, line in enumerate(hours):
        if not any(c.isalnum() for c in line):
            return Refused(f"hours line {i + 1} needs a day or time")
    first_seen = {}
    for i, line in enumerate(hours):
        j = first_seen.setdefault(_line_key(line), i)
        if j != i:
            return Refused(f"hours lines {j + 1} and {i + 1} say the same thing")
    if [_spaced(h) for h in hours] == [_spaced(h) for h in content.store["hours"]]:
        return Refused("store hours are already " + " / ".join(content.store["hours"]))
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
    for field, value in given.items():
        if not any(c.isalpha() for c in value):
            return Refused(f"{field} needs at least one letter")
    store = content.store
    if all(_spaced(store[f]) == _spaced(v) for f, v in given.items()):
        return Refused(f"store address is already {store['streetAddress']}, {store['town']}")
    before = copy.deepcopy(store)
    store.update(given)
    return _touch(before, store)


def _set_intro(content, args, ctx):
    text = args["text"]
    if len(text) > MAX_INTRO:
        return Refused(f"the intro is longer than {MAX_INTRO} characters")
    if sum(c.isalpha() for c in text) < 3:
        return Refused("the intro needs at least 3 letters")
    if _spaced(text) == _spaced(content.store.get("intro", DEFAULT_INTRO)):
        return Refused("the intro already says that")
    before = copy.deepcopy(content.store)
    content.store["intro"] = text
    return _touch(before, content.store)


def _confirm_selection(content, args, ctx):
    """SHOP-1: record that Michael checked the selection (today, or an earlier ``date``) and, optionally, which
    products are available (``yes``), limited or sold out (``no``): lists of exact product ids."""
    today = shop_today(ctx.now)
    day = date.fromisoformat(args["date"]) if "date" in args else today
    if day > today:
        return Refused(f"{day.isoformat()} is in the future; the selection can only be checked today or earlier")
    if (today - day).days > STALE_AFTER_DAYS:
        return Refused(f"{day.isoformat()} is more than {STALE_AFTER_DAYS} days ago, so the site would already call it "
                       "out of date; check the selection today instead")
    last = checked_on(content.store)
    if last is not None and day < last:
        return Refused(f"the selection was already checked on {last.isoformat()}, after {day.isoformat()}")
    wanted, touched = {}, []
    for value in AVAILABILITY:
        for pid in args.get(value, ()):
            if pid in wanted:
                same = wanted[pid] == value
                return Refused(f"{pid} is listed twice in {value}" if same
                               else f"{pid} is listed twice ({wanted[pid]} and {value})")
            wanted[pid] = value
    for pid, value in wanted.items():
        product = _product(content, pid)
        if not isinstance(product, dict):
            return product
        if product["status"] != "active":
            return Refused(f"{pid} is {product['status']}; restore it before marking it available")
        if product.get("available") != value:
            before = copy.deepcopy(product)
            product["available"] = value
            touched.append(Touched("products", pid, before, copy.deepcopy(product)))
    if day == last and not touched:
        return Refused(f"the selection was already checked on {day.isoformat()}; nothing to change")
    if day != last:
        before = copy.deepcopy(content.store)
        content.store["selection_checked_on"] = day.isoformat()
        touched = _touch(before, content.store) + touched
    return touched


OPS = (
    Op("store.set_hours", {"hours": Arg("text_list")}, _set_hours),
    Op("store.confirm_selection", {"date": Arg("date", required=False),
                                   **{v: Arg("text_list", required=False) for v in AVAILABILITY}}, _confirm_selection),
    Op("store.set_address", {"streetAddress": Arg("text", required=False), "town": Arg("text", required=False)},
       _set_address),
    Op("store.set_intro", {"text": Arg("text")}, _set_intro),
)
