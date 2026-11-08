"""Weekly specials ops (AVO-SPECIALS-1): ``specials.add``, ``specials.edit``, ``specials.remove`` and
``specials.clear_expired`` change ``store.specials``, the list behind the "This week's specials" section at the top
of the home page (which is also the shop page). They go the normal typed-op path: draft, preview, owner approval,
single writer, and ``history.revert`` to undo.

Usage (request ops):
    {"op": "specials.add", "args": {"title": "Fresh strawberries", "deal": "2 for $5", "end": "2026-11-15"}}
    {"op": "specials.add", "args": {"title": "Sample Saturday", "deal": "Free sample Saturday", "start": "2026-11-14",
                                    "end": "2026-11-14", "product": "<product id>", "picture": true, "order": 1}}
    {"op": "specials.edit", "args": {"id": "fresh-strawberries", "deal": "3 for $10", "end": "2026-11-16"}}
    {"op": "specials.remove", "args": {"id": "fresh-strawberries"}}
    {"op": "specials.clear_expired", "args": {}}

An end date is always required on add (its last day counts; the special shows through that day, Pacific, and never
after). ``start`` defaults to today. ``title`` and ``deal`` are shown exactly as typed; at most 60 characters each, no
markup, links, email or phone numbers; only the deal line may hold a price. ``product`` must be a product that is not
held; ``picture: true`` reuses that product's picture (needs a product). A special runs at most 31 days and at most 6
are active on any one day. ``order`` is 0-99 (lower shows first); the default puts a new special last. The id is made
from the title (``fresh-strawberries``) and never changes. ``specials.edit`` gives only the fields to change
(``clearProduct: true`` takes the product link and picture off). Undo of an older specials change is refused when a
later change touched the specials list (the whole list is one saved detail): undo that later change first.
The deal line is the only place a price may appear. Anything with a price or a claim is checked like every other
owner-written text, so it needs owner approval before it goes live.
"""

from __future__ import annotations

import copy
import re

from hass.content_model import (
    MAX_SPECIAL_DAYS, MAX_SPECIAL_DEAL, MAX_SPECIAL_ORDER, MAX_SPECIAL_TITLE, MAX_SPECIALS_AT_ONCE, MAX_SPECIALS_STORED,
    iso_day, shop_today, special_text_problem, validate_specials,
)
from hass.ops import Arg, NeedsDetails, Op, Refused, Touched
from hass.ops.catalog import _product
from hass.ops.store import _spaced, _touch

MAX_ID_BASE = 40


def _slug(title):
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:MAX_ID_BASE].strip("-")
    return base or "special"


def _list(content):
    return content.store.get("specials") or []


def _find(content, sid):
    return next((sp for sp in _list(content) if sp["id"] == sid), None)


def _text_problems(title=None, deal=None):
    for name, value, limit, is_deal in (("title", title, MAX_SPECIAL_TITLE, False), ("deal line", deal, MAX_SPECIAL_DEAL, True)):
        if value is None:
            continue
        if len(value) > limit:
            return Refused(f"the {name} is longer than {limit} characters")
        if (why := special_text_problem(value, deal=is_deal)):
            return Refused(f"the {name} {why}")
    return None


def _product_problem(content, pid, picture):
    if pid is not None:
        product = _product(content, pid)
        if not isinstance(product, dict):
            return Refused(f"{pid} is not a product" if not isinstance(product, Refused) else product.reason)
    if picture and pid is None:
        return Refused("a picture comes from a product; name the product too")
    return None


def _dates_problem(start, end, today, content, *, own=None):
    if end < today:
        return Refused(f"the last day {end.isoformat()} is already past")
    if end < start:
        return Refused(f"the last day {end.isoformat()} is before the first day {start.isoformat()}")
    if (end - start).days + 1 > MAX_SPECIAL_DAYS:
        return Refused(f"a special runs at most {MAX_SPECIAL_DAYS} days")
    others = [(iso_day(sp["start"]), iso_day(sp["end"])) for sp in _list(content) if sp["id"] != own]
    live = [(max(s, today), e) for s, e in [*others, (start, end)] if s is not None and e is not None and e >= today]
    for day in sorted({s for s, _ in live}):
        if sum(s <= day <= e for s, e in live) > MAX_SPECIALS_AT_ONCE:
            return Refused(f"at most {MAX_SPECIALS_AT_ONCE} specials can show at once; more would show on {day.isoformat()}. "
                           "Remove or shorten one first")
    return None


def _save(content, specials, before):
    """Write the list (the key is dropped when empty, so the saved file matches a site that never had specials)."""
    if specials:
        content.store["specials"] = specials
    else:
        content.store.pop("specials", None)
    problems = []
    validate_specials(problems, content.store.get("specials", []), {p["id"] for p in content.products}, shop_today())
    if problems:
        return Refused(problems[0])
    return _touch(before, content.store)


def _add(content, args, ctx):
    today = shop_today(ctx.now)
    title, deal = args["title"], args["deal"]
    if refused := _text_problems(title, deal):
        return refused
    start = iso_day(args["start"]) if "start" in args else today
    end = iso_day(args["end"])
    if refused := _dates_problem(start, end, today, content):
        return refused
    if refused := _product_problem(content, args.get("product"), args.get("picture")):
        return refused
    specials = copy.deepcopy(_list(content))
    live = [sp for sp in specials if (iso_day(sp["end"]) or today) >= today]
    if len(specials) >= MAX_SPECIALS_STORED:
        return Refused(f"there are already {len(specials)} saved specials; clear the finished ones first")
    if any(_spaced(sp["title"]).casefold() == _spaced(title).casefold() and iso_day(sp["end"]) >= today for sp in live):
        return Refused(f"there is already a special called {title}; edit it instead")
    ids = {sp["id"] for sp in specials}
    sid, n = _slug(title), 2
    while sid in ids:
        sid = f"{_slug(title)}-{n}"
        n += 1
    order = args["order"] if "order" in args else min(MAX_SPECIAL_ORDER, max((sp["order"] for sp in live), default=-1) + 1)
    if order > MAX_SPECIAL_ORDER:
        return Refused(f"the order is 0 to {MAX_SPECIAL_ORDER}")
    special = {"id": sid, "title": title, "deal": deal, "start": start.isoformat(), "end": end.isoformat(), "order": order}
    if "product" in args:
        special["product"] = args["product"]
        if args.get("picture"):
            special["picture"] = True
    before = copy.deepcopy(content.store)
    return _save(content, [*specials, special], before)


def _edit(content, args, ctx):
    today = shop_today(ctx.now)
    sp = _find(content, args["id"])
    if sp is None:
        return Refused(f"there is no special {args['id']}")
    changes = {k: v for k, v in args.items() if k != "id"}
    if not changes:
        return NeedsDetails(["title", "deal", "start", "end", "order", "product", "picture"],
                            "What should change on this special?")
    if changes.get("clearProduct") and ("product" in changes or "picture" in changes):
        return Refused("clearProduct cannot go with a product or picture")
    if refused := _text_problems(changes.get("title"), changes.get("deal")):
        return refused
    new = copy.deepcopy(sp)
    for field in ("title", "deal"):
        if field in changes:
            new[field] = changes[field]
    for field in ("start", "end"):
        if field in changes:
            new[field] = changes[field]
    if "order" in changes:
        if changes["order"] > MAX_SPECIAL_ORDER:
            return Refused(f"the order is 0 to {MAX_SPECIAL_ORDER}")
        new["order"] = changes["order"]
    if changes.get("clearProduct"):
        new.pop("product", None)
        new.pop("picture", None)
    if "product" in changes:
        new["product"] = changes["product"]
    if "picture" in changes:
        if changes["picture"]:
            new["picture"] = True
        else:
            new.pop("picture", None)
    if refused := _product_problem(content, new.get("product"), new.get("picture")):
        return refused
    start, end = iso_day(new["start"]), iso_day(new["end"])
    if refused := _dates_problem(start, end, today, content, own=sp["id"]):
        return refused
    if {k: _spaced(v) if isinstance(v, str) else v for k, v in new.items()} == \
            {k: _spaced(v) if isinstance(v, str) else v for k, v in sp.items()}:
        return Refused("that special already says that")
    before = copy.deepcopy(content.store)
    return _save(content, [new if s["id"] == sp["id"] else copy.deepcopy(s) for s in _list(content)], before)


def _remove(content, args, ctx):
    sp = _find(content, args["id"])
    if sp is None:
        return Refused(f"there is no special {args['id']}")
    before = copy.deepcopy(content.store)
    return _save(content, [copy.deepcopy(s) for s in _list(content) if s["id"] != sp["id"]], before)


def _clear_expired(content, args, ctx):
    today = shop_today(ctx.now)
    kept = [copy.deepcopy(s) for s in _list(content) if (iso_day(s["end"]) or today) >= today]
    if len(kept) == len(_list(content)):
        return Refused("there are no finished specials to clear")
    before = copy.deepcopy(content.store)
    return _save(content, kept, before)


OPS = (
    Op("specials.add", {"title": Arg("text"), "deal": Arg("deal"), "end": Arg("date"), "start": Arg("date", required=False),
                        "product": Arg("id", required=False), "picture": Arg("bool", required=False),
                        "order": Arg("int", required=False, minimum=0)}, _add),
    Op("specials.edit", {"id": Arg("id"), "title": Arg("text", required=False), "deal": Arg("deal", required=False),
                         "start": Arg("date", required=False), "end": Arg("date", required=False),
                         "product": Arg("id", required=False), "picture": Arg("bool", required=False),
                         "clearProduct": Arg("bool", required=False), "order": Arg("int", required=False, minimum=0)}, _edit),
    Op("specials.remove", {"id": Arg("id")}, _remove),
    Op("specials.clear_expired", {}, _clear_expired),
)
