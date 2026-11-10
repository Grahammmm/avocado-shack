"""Slot resolvers (SKILLS-FW-1): turn the owner's words into one checked value, or into the one question to ask.

Pure functions over a loaded ``Content`` (read-only) and ``nl_prep``; no file, network or model. Every resolver
returns a ``Resolved`` whose ``status`` is one of STATUSES. A held product is never resolvable, and a hidden one
is named, not silently skipped. The ``ask`` text is plain words for the owner: no ids, no counts of internals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from hass import nl_prep
from hass.content_model import AVAILABILITY, CATEGORIES
from hass.ops import catalog

STATUSES = ("one", "several", "none", "held", "hidden", "invalid")
MAX_CANDIDATES = catalog.MAX_CANDIDATES
WORDS_FOR_AVAILABILITY = {
    "yes": ("in stock", "in", "back", "have", "got", "restocked", "available", "plenty"),
    "limited": ("low", "limited", "running low", "few", "almost out", "last"),
    "no": ("out", "sold out", "gone", "none", "no more", "unavailable"),
}
NEGATION = re.compile(r" (not|never|without|no longer|\w+n't|isnt|arent|wasnt|werent|dont|doesnt|cant|cannot|hasnt|havent) ")
SHELF_WORDS = {"vegetable": "vegetables", "veggies": "vegetables", "veg": "vegetables", "produce": "vegetables",
               "egg": "eggs", "drink": "drinks", "flower": "flowers", "pantry": "pantry"}
CLOCK_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")


@dataclass(frozen=True)
class Resolved:
    status: str
    value: object = None
    candidates: tuple = ()  # plain names (never ids) the owner can pick from, at most MAX_CANDIDATES
    ids: tuple = ()  # the ids behind ``candidates`` in the same order, for code only
    reply: str = ""  # plain-words question or refusal when status is not "one"
    via: str = ""


def _names_line(names) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def _by_id(content, pid):
    return next((p for p in content.products if p.get("id") == pid), None)


def product_ref(content, query, aliases=None, *, include_hidden=False) -> Resolved:
    """One product the query names. Held: refused naming the state. Hidden: 'restore it first'. Several: a question."""
    if not isinstance(query, str) or not query.strip():
        return Resolved("none", reply="Which product do you mean?")
    found = catalog.lookup(content, "product", query, aliases)
    if "match" in found:
        product = _by_id(content, found["match"])
        name = product["name"]
        if product.get("status") == "held":
            return Resolved("held", reply=f"I can't change {name} right now. It is on hold until someone has looked at it.")
        if product.get("status") != "active" and not (include_hidden and product.get("status") == "hidden"):
            return Resolved("hidden", reply=f"{name} is hidden. Do you want me to bring it back first?")
        return Resolved("one", value=found["match"], via=found.get("via", ""))
    cands = found["candidates"]
    if not cands:
        return Resolved("none", reply="I don't know a product called that. What is it called on the site?")
    usable = [c for c in cands if c["status"] == "active" or (include_hidden and c["status"] == "hidden")]
    if len(usable) == 1 and len(cands) == 1:
        return Resolved("one", value=usable[0]["id"])
    if not usable:
        held = all(c["status"] == "held" for c in cands)
        return Resolved("held" if held else "hidden",
                        reply="I can't change that one right now." if held else "That one is hidden. Do you want me to bring it back first?")
    names = [f"{c['name']} ({c['brand']})" if c.get("brand") else c["name"] for c in usable]
    return Resolved("several", candidates=tuple(names), ids=tuple(c["id"] for c in usable),
                    reply=f"Which one do you mean: {_names_line(names)}?")


def maker_ref(content, query, aliases=None) -> Resolved:
    if not isinstance(query, str) or not query.strip():
        return Resolved("none", reply="Which maker do you mean?")
    found = catalog.lookup(content, "maker", query, aliases)
    if "match" in found:
        maker = content.makers[found["match"]]
        if maker.get("hidden"):
            return Resolved("hidden", reply=f"{maker['name']} is hidden. Do you want me to bring them back first?")
        return Resolved("one", value=found["match"], via=found.get("via", ""))
    cands = found["candidates"]
    if not cands:
        return Resolved("none", reply="I don't know a maker called that. Who is it?")
    usable = [c for c in cands if c["status"] == "visible"]
    if not usable:
        return Resolved("hidden", reply="That maker is hidden. Do you want me to bring them back first?")
    if len(usable) == 1 and len(cands) == 1:
        return Resolved("one", value=usable[0]["id"])
    names = [c["name"] for c in usable]
    return Resolved("several", candidates=tuple(names), ids=tuple(c["id"] for c in usable),
                    reply=f"Which maker do you mean: {_names_line(names)}?")


def _has_run(words, needle) -> bool:
    n = len(needle)
    return any(words[i:i + n] == needle for i in range(len(words) - n + 1))


def _titled(records, query, label):
    """Records whose title holds the query's normalized words as a contiguous run of whole words.

    Whole words only (RF0834-10): 'ridge' must not pick 'Bridge Walk' just because one spelling sits inside the other.
    """
    needle = nl_prep.tokens(query)
    if not needle:
        return Resolved("none", reply=f"Which {label} do you mean?")
    hits = [r for r in records if _has_run(nl_prep.tokens(str(r.get("title", ""))), needle)]
    if len(hits) == 1:
        return Resolved("one", value=hits[0]["id"])
    if not hits:
        return Resolved("none", reply=f"I don't know a {label} called that. What is it called?")
    hits = hits[:MAX_CANDIDATES]
    names = [h["title"] for h in hits]
    return Resolved("several", candidates=tuple(names), ids=tuple(h["id"] for h in hits),
                    reply=f"Which {label} do you mean: {_names_line(names)}?")


def hike_ref(content, query) -> Resolved:
    """A real hike (never a sample): the community events list, matched on the title."""
    events = [e for e in content.community.get("events", []) if isinstance(e, dict) and "id" in e]
    return _titled(events, query, "hike")


def route_ref(content, query) -> Resolved:
    routes = [r for r in content.community.get("routeIdeas", []) if isinstance(r, dict) and "id" in r]
    found = _titled(routes, query, "trail")
    if found.status != "one":
        return found
    route = next((r for r in routes if r["id"] == found.value), {})
    if route.get("status") == "hidden":  # RF1925-12: a hidden trail is never a link target; ask to restore it first
        return Resolved("hidden", reply=f"{route.get('title')} is hidden. Do you want me to bring it back first?")
    return found


def shelf(text) -> Resolved:
    """One of CATEGORIES from the owner's word (one word or a short phrase), else a question that names them."""
    raw = re.findall(r"[a-z]+", nl_prep.fold(text or ""))
    words = {*raw, *(nl_prep.stem(w) for w in raw)}
    hits = {c for c in CATEGORIES if c in words or nl_prep.stem(c) in words}
    hits |= {SHELF_WORDS[w] for w in words if w in SHELF_WORDS}
    if len(hits) == 1:
        return Resolved("one", value=next(iter(hits)))
    names = sorted(hits) if hits else list(CATEGORIES)
    return Resolved("several" if hits else "none", candidates=tuple(names),
                    reply=f"Which shelf is it on: {_names_line(names)}?")


def availability(text) -> Resolved:
    """yes / limited / no from the owner's words ('out', 'low', 'back in'). Mixed words are a question."""
    t = " " + " ".join(re.findall(r"[a-z']+", nl_prep.fold(text or ""))) + " "
    if (text or "").strip() in AVAILABILITY:
        return Resolved("one", value=text.strip())
    found = {k for k, words in WORDS_FOR_AVAILABILITY.items() if any(f" {w} " in t for w in words)}
    if found and NEGATION.search(t):  # 'not available', 'not out': never assert the opposite stock state, ask
        return Resolved("none", reply="Is it in stock, running low, or sold out?")
    if "limited" in found and "no" in found and "almost out" in t:
        found.discard("no")
    if "no" in found and " no more " in t:
        found.discard("yes")
    if len(found) == 1:
        return Resolved("one", value=next(iter(found)))
    return Resolved("none", reply="Is it in stock, running low, or sold out?")


def day(text, today: date) -> Resolved:
    """One Pacific calendar date from words ('tomorrow', 'next saturday', '2026-11-14'). Two readings = a question."""
    text = (text or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return Resolved("one", value=date.fromisoformat(text).isoformat())
        except ValueError:
            return Resolved("invalid", reply="That date doesn't look right. Which day do you mean?")
    rows, _hits = nl_prep.date_hints(text, today)
    dates = {r["date"] for r in rows if "date" in r}
    unclear = [d for r in rows for d in r.get("unclear", ())]
    named = {r["next"] for r in rows if "next" in r}
    pool = dates or named
    if len(pool) == 1 and not unclear and len(rows) == 1:
        return Resolved("one", value=next(iter(pool)))
    return Resolved("none", reply="Which day do you mean?")


def clock(text) -> Resolved:
    """HH:MM from '9', '9am', '3:30 pm', 'noon' or '15:30'. Bare numbers are not guessed between am and pm."""
    text = (text or "").strip()
    if CLOCK_RE.fullmatch(text) and len(text) == 5:
        return Resolved("one", value=text)
    hints = nl_prep.time_hints(text)
    if len(hints) == 1:
        return Resolved("one", value=hints[0]["time"])
    return Resolved("none", reply="What time is it? For example 9am or 3:30pm.")


def attachment(sha) -> Resolved:
    if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha):
        return Resolved("one", value=sha)
    return Resolved("none", reply="Send the photo with your message.")


RESOLVERS = {"product_ref": product_ref, "maker_ref": maker_ref, "hike_ref": hike_ref, "route_ref": route_ref,
             "shelf": shelf, "availability": availability, "day": day, "clock": clock, "attachment": attachment}
