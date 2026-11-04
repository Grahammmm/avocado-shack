"""NB-AV-03 (H05): the interpreter system prompt, generated from the ops registry and the catalog names/ids.

build(registry, content) -> str returns a deterministic plain-text prompt: role, reply contract, rules, one line per
op (sorted by name) and the catalog's product ids/names/status and maker keys/names. A registry or catalog change
changes the prompt. Pure: no clock, no env, no I/O. Catalog values are JSON-string-escaped (line separators too), so
a name can never break a line or a section. Not wired into any service (NB-AV-02's LocalInterpreter takes the text).
AV2022-01: a Community section lists every hike (id | title | starts at | status) and route idea (id | title).
AV2022-02: a last Store section lists the street address, town and every hours line (field | value), because
store.set_hours replaces the whole list.
RF1100-7: damaged catalog rows are skipped, like hikes and route ideas (a non-object maker keeps its key, empty name).
"""
from __future__ import annotations

import json

from hass.content_model import MAX_HOURS_LINES

MAX_PRODUCTS, MAX_MAKERS, MAX_OPS = 400, 200, 20
MAX_HIKES, MAX_ROUTES = 60, 60
PROMPT_MAX_BYTES = 64 * 1024
_LINE_BREAKS = {"\x85": "\\u0085", "\u2028": "\\u2028", "\u2029": "\\u2029"}  # json.dumps keeps these raw

ROLE = ("You turn one owner text message into typed changes for the Avocado Shack shop site.\n"
        "You only propose changes; you never approve or apply anything.")

CONTRACT = (
    "Reply with exactly one JSON object and nothing else, in one of these shapes:\n"
    '{"ops": [{"op": "<name>", "args": {...}}], "revises": "<code>" or null}\n'
    '{"question": "<one short question for the owner>"}\n'
    '{"unsupported": "<one short reason>"}\n'
    '"revises" may only be a code from the "pending" list in the user message; otherwise it is null.')

RULES = (
    'A correction to a pending draft resends every op of that draft in full with "revises" set to its code; '
    'copy each unchanged arg from its "ops" exactly.',
    "Use only the product ids, maker keys, hike ids and route idea ids listed below, exactly as written.",
    "If a product or maker is not clearly one listed entry, ask a question naming the candidates.",
    "Never add organic, origin, local or maker claims the owner did not write.",
    "Never guess dates, times, prices or quantities; ask a question instead.",
    'The user message gives "today" (Pacific date) and "weekday". Work out words like "next Saturday" or "tomorrow" '
    "from them and write the exact date; if the day is still unclear, ask.",
    f"One message may hold several ops (at most {MAX_OPS}).",
    "store.set_hours replaces every hours line: send the whole new list, repeating the lines the owner did not change, "
    "in the order shown.",
    "When a pending draft is a photo question (product.set_photo), answer with product.set_photo for a listed product, "
    "or product.add with imageAlt when the owner says it is a new product; never both.",
)


def _q(value) -> str:
    """A JSON string literal that always stays on one line."""
    text = json.dumps("" if value is None else str(value), ensure_ascii=False)
    for raw, escaped in _LINE_BREAKS.items():
        text = text.replace(raw, escaped)
    return text


def _arg(name, arg) -> str:
    parts = [f"{name}: {arg.kind}"]
    if arg.required:
        parts.append("required")
    if arg.choices:
        parts.append("one of " + "|".join(str(c) for c in arg.choices))
    if arg.minimum is not None:
        parts.append(f">= {arg.minimum}")
    return ", ".join(parts)


def _op_lines(registry) -> list:
    lines = [f"{name}({'; '.join(_arg(a, spec) for a, spec in registry[name].args.items())})"
             for name in sorted(registry)]
    return lines or ["(none)"]


def _capped(rows, cap) -> list:
    if not rows:
        return ["(none)"]
    return rows[:cap] + ([f"… and {len(rows) - cap} more (ask the owner)"] if len(rows) > cap else [])


def _product_lines(products) -> list:
    rows = sorted(products, key=lambda p: str(p.get("id", "")))
    return _capped([f"{_q(p.get('id'))} | {_q(p.get('name'))} | {_q(p.get('status'))}" for p in rows],
                   MAX_PRODUCTS)


def _maker_lines(makers) -> list:
    rows = [f"{_q(key)} | {_q(m.get('name') if isinstance(m := makers[key], dict) else None)}"
            for key in sorted(makers, key=str)]
    return _capped(rows, MAX_MAKERS)


def _dicts(items) -> list:
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _hike_lines(events) -> list:
    rows = sorted(sorted(_dicts(events), key=lambda e: str(e.get("id", ""))),
                  key=lambda e: str(e.get("startsAt", "")), reverse=True)  # newest first, ties by id
    return _capped([f"{_q(e.get('id'))} | {_q(e.get('title'))} | {_q(e.get('startsAt'))} | {_q(e.get('status'))}"
                    for e in rows], MAX_HIKES)


def _route_lines(ideas) -> list:
    rows = sorted(_dicts(ideas), key=lambda r: str(r.get("id", "")))
    return _capped([f"{_q(r.get('id'))} | {_q(r.get('title'))}" for r in rows], MAX_ROUTES)


def _store_lines(store) -> list:
    store = store if isinstance(store, dict) else {}
    rows = [f"{_q(key)} | {_q(store[key])}" for key in ("streetAddress", "town") if store.get(key) is not None]
    hours = store.get("hours") if isinstance(store.get("hours"), list) else []
    rows += _capped([f"{_q('hours')} | {_q(line)}" for line in hours], MAX_HOURS_LINES) if hours else []
    return rows or ["(none)"]


def build(registry, content) -> str:
    """The system prompt for ``registry`` (name -> Op) and ``content`` (.products, .makers, .community, .store)."""
    community = getattr(content, "community", None) or {}
    community = community if isinstance(community, dict) else {}
    makers = content.makers if isinstance(content.makers, dict) else {}
    sections = [
        ROLE,
        CONTRACT,
        "Rules:\n" + "\n".join(f"- {rule}" for rule in RULES),
        "Operations (name(arg: kind[, required][, one of ...][, >= n]; ...)):\n" + "\n".join(_op_lines(registry)),
        "Catalog.\nProducts (id | name | status):\n" + "\n".join(_product_lines(_dicts(content.products)))
        + "\nMakers (key | name):\n" + "\n".join(_maker_lines(makers)),
        "Community.\nHikes (id | title | starts at | status):\n" + "\n".join(_hike_lines(community.get("events")))
        + "\nRoute ideas (id | title):\n" + "\n".join(_route_lines(community.get("routeIdeas"))),
        "Store.\nStore (field | value):\n" + "\n".join(_store_lines(getattr(content, "store", None) or {})),
    ]
    prompt = "\n\n".join(sections) + "\n"
    if len(prompt.encode("utf-8")) > PROMPT_MAX_BYTES:
        raise ValueError("prompt too large")
    return prompt
