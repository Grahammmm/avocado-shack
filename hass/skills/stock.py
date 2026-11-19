"""SKILLS-STOCK-1: what is on the shelf. Three skills over the one inventory word a product carries (in stock, low,
sold out) and the day the shelves were checked: ``stock.set``, ``stock.checked`` and ``stock.clear``.

Spec: reports/hass/SKILLS-SPEC.md 3.6, 3.7 and 3.9. Owner words: docs/hass/VOICE.md. Authoring guide: docs/hass/SKILLS.md.
Per skill page: docs/hass/skills/stock.md.

Each plan is a pure function of the resolved slots (product ids, the words ``yes`` / ``limited`` / ``no``, ISO days) and
an optional ``ctx`` (``ctx.today`` as an ISO Pacific day, ``ctx.content`` as the loaded content). It returns the ops of
the existing editor; it never touches a file, the network or its arguments. A rule the plan cannot judge without
``ctx.content`` is left to the editor, which repeats every one of them.

Today's shelf check is NOT planned here. A change of a product's word needs a check dated today; when there is none the
editor refuses it and Conversation asks the one question of HASS-SHELFCHECK-FLOW-1 (``open_asks``), then drafts the check
and the change together after the owner's yes. ``stock.set`` therefore plans only ``product.set_availability``.
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.content_model import AVAILABILITY, ID_RE  # noqa: E402
from hass.interpret_check import PRICE_REPLY  # noqa: E402
from hass.skills import kinds  # noqa: E402
from hass.skills.model import Slot, Skill, Trigger, Undo  # noqa: E402
from hass.sitegen import STALE_AFTER_DAYS  # noqa: E402

MAX_ITEMS = 6  # whole-shelf-max-6: one change each up to six; more asks first, never a bulk change
CARD_WORDS = {"yes": "Available today", "limited": "Limited", "no": "Sold out"}  # what the product card says
OWNER_WORDS = {"yes": "in stock", "limited": "low", "no": "sold out"}  # what the owner says

TOO_MANY = "That is {count} products, and I change six at a time. Which ones should I do first?"
HIDDEN = "{name} is hidden. Do you want me to bring it back first?"
HELD = "I can't change {name} right now. It is on hold until someone has looked at it."
ALREADY = "{name} already says {word}. Nothing to change."
TWICE = "I heard {name} twice with different answers. Which one is right?"
NO_WORD = "{name} has no label to clear."
FUTURE = "I can't record a shelf check for a day that hasn't happened yet."
TOO_OLD = "That was more than a week ago, so the site would already call it out of date. Check the shelves today and tell me."
AFTER = "The shelves were already checked after that day."
DONE_TODAY = "The shelf check is already recorded for that day. Nothing to change."
BAD_ITEM = "I didn't understand which product and which word you meant. Which products, and in, low or out?"
NONE_NAMED = "Which products should I clear?"


class Refusal(ValueError):
    """A plan that refuses carries the fixed owner reply (the test kit and the dispatcher read ``.reply``)."""

    def __init__(self, reply, kind="refuse"):
        super().__init__(reply)
        self.reply = reply
        self.kind = kind


def _content(ctx):
    return getattr(ctx, "content", None)


def _find(ctx, pid):
    content = _content(ctx)
    return next((p for p in getattr(content, "products", ()) if p.get("id") == pid), None) if content is not None else None


def _name(ctx, pid) -> str:
    product = _find(ctx, pid)
    return product["name"] if product else "one of those products"


def _usable(ctx, pid):
    """Held and hidden products are named and refused; unknown to the content (or no content): the editor decides."""
    product = _find(ctx, pid)
    if product is None or product.get("status") == "active":
        return
    raise Refusal((HELD if product.get("status") == "held" else HIDDEN).format(name=product["name"]))


def _today(ctx):
    raw = getattr(ctx, "today", None)
    if type(raw) is date:  # production dispatch supplies the Pacific date object; a datetime is not a date here
        return raw
    try:
        return date.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None


def _refs(value, ctx) -> list:
    """RF2135-10: the product ids a list of references names, in the owner's order, repeats kept.

    An exact id of a product in the content keeps the id path. Any other string is a product name or alias (even a
    lowercase one-word one that fits ID_RE), resolved with the existing ``kinds.product_ref``; only one active product
    is accepted, so an ambiguous, held or hidden name refuses the whole plan with the resolver's own plain reply. An
    unknown id-shaped string is kept for the editor to judge; with no content only id syntax passes.
    """
    if not isinstance(value, (list, tuple)) or not all(isinstance(x, str) and x.strip() for x in value):
        raise Refusal(BAD_ITEM)
    content = _content(ctx)
    out = []
    for ref in value:
        if content is None:
            if not ID_RE.fullmatch(ref):
                raise Refusal(BAD_ITEM)
            out.append(ref)
        elif _find(ctx, ref) is not None:  # an exact existing id wins over any name or alias
            out.append(ref)
        else:
            found = kinds.product_ref(content, ref, getattr(ctx, "aliases", None))
            if found.status == "none" and ID_RE.fullmatch(ref):
                out.append(ref)  # id-shaped but unknown: the editor judges it
            elif found.status != "one":
                raise Refusal(found.reply)
            else:
                out.append(found.value)
    return out


def _ids(value, ctx, cap: int | None = MAX_ITEMS) -> list:
    """Resolved product ids, in the owner's order, each once; the whole-shelf cap applies unless ``cap`` is None."""
    out = list(dict.fromkeys(_refs(value, ctx)))
    if cap is not None and len(out) > cap:
        raise Refusal(TOO_MANY.format(count=len(out)))
    return out


# -- stock.set ----------------------------------------------------------------------------------------------------
def _set_plan(slots, ctx) -> list:
    items = slots.get("items")
    if not isinstance(items, (list, tuple)) or not items or not all(
            isinstance(i, dict) and isinstance(i.get("product"), str) and ID_RE.fullmatch(i["product"])
            and i.get("availability") in AVAILABILITY for i in items):
        raise Refusal(BAD_ITEM)
    chosen: dict = {}
    for item in items:  # the same product twice with the same word is one change; two words is a question
        pid, word = item["product"], item["availability"]
        if chosen.setdefault(pid, word) != word:
            raise Refusal(TWICE.format(name=_name(ctx, pid)), kind="question")
    if len(chosen) > MAX_ITEMS:
        raise Refusal(TOO_MANY.format(count=len(chosen)))
    today = _today(ctx)
    ops = []
    for pid, word in chosen.items():
        _usable(ctx, pid)  # held-or-hidden-refused
        product = _find(ctx, pid)
        if product and today and product.get("available") == word and product.get("available_on") == today.isoformat():
            raise Refusal(ALREADY.format(name=product["name"], word=CARD_WORDS[word]))  # not-already-true
        ops.append({"op": "product.set_availability", "args": {"id": pid, "available": word}})
    return ops


# -- stock.checked ------------------------------------------------------------------------------------------------
def _checked_plan(slots, ctx) -> list:
    today, content = _today(ctx), _content(ctx)
    day = slots.get("day")
    if day is not None:
        try:
            day = date.fromisoformat(day) if isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) else None
        except ValueError:
            day = None
        if day is None:
            raise Refusal("Which day did you check the shelves?")
    lists = {"yes": slots.get("in") or [], "limited": slots.get("limited") or [], "no": slots.get("out") or []}
    seen: dict = {}
    args: dict = {}
    for word, ids in lists.items():
        ids = _refs(ids, ctx)  # a morning check may name any number of products: one change, not one per product
        if len(set(ids)) != len(ids):
            raise Refusal(TWICE.format(name=_name(ctx, next(x for x in ids if ids.count(x) > 1))))  # each product once, same list too
        for pid in ids:
            _usable(ctx, pid)
            if pid in seen:
                raise Refusal(TWICE.format(name=_name(ctx, pid)), kind="question")
            seen[pid] = word
        if ids:
            args[word] = ids
    if today and day:
        if day > today:
            raise Refusal(FUTURE)
        if (today - day).days > STALE_AFTER_DAYS:
            raise Refusal(TOO_OLD)
    last = None
    if content is not None:
        from hass.content_model import checked_on
        last = checked_on(content.store)
    effective = day or today
    if last and effective and effective < last:
        raise Refusal(AFTER)
    if last and effective and effective == last and not any(
            (_find(ctx, pid) or {}).get("available") != word or (_find(ctx, pid) or {}).get("available_on") != effective.isoformat()
            for pid, word in seen.items()):
        raise Refusal(DONE_TODAY)  # not-already-true: the day is recorded and every named word already says so
    if day and (today is None or day != today):
        args = {"date": day.isoformat(), **args}
    return [{"op": "store.confirm_selection", "args": args}]


PLAIN_SHELF_CHECKS = frozenset({"did the shelf check, all good", "shelf check done", "shelf check: all good"})


def plain_shelf_check(text) -> bool:
    """AV2007-15: True only for a whole message that is one of the three plain 'shelf check done' sentences (case, spacing and one
    closing . or ! aside). Anything else (a question, a negation, a date, a name, an `except` tail) is False and goes the usual way."""
    if not isinstance(text, str):
        return False
    return re.sub(r"[.!]$", "", " ".join(text.lower().split())) in PLAIN_SHELF_CHECKS


# -- stock.clear --------------------------------------------------------------------------------------------------
def _clear_plan(slots, ctx) -> list:
    raw = slots.get("items")
    if not raw:
        raise Refusal(NONE_NAMED)
    ids = _ids(raw, ctx)
    ops = []
    for pid in ids:
        _usable(ctx, pid)
        product = _find(ctx, pid)
        if product is not None and "available" not in product:
            raise Refusal(NO_WORD.format(name=product["name"]))
        ops.append({"op": "product.clear_availability", "args": {"id": pid}})
    return ops


_CASES = "hass/tests/fixtures/skills/stock/{}.jsonl"
_PRODUCTS = "hass/content/products.json"
_STORE = "hass/content/store.json"
_GENERATED = (("storefront-mockup/catalog-products.js", "products[id].availability"),
              ("storefront-mockup/index.html", "products[id].availability"))
_WORD_EDITS = ((_PRODUCTS, "products[id].available"), (_PRODUCTS, "products[id].available_on"))
_PRODUCT_PREVIEW = "product:the first product named"

STOCK_SET = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='full', logs=('subjects', 'fields'), who='owner',
    name="stock.set", label="change what's in stock",
    summary="Mark one or more products in stock, low, or sold out after today's shelf check.",
    triggers=(
        Trigger("eggs are out"),
        Trigger("egs r sold out again lol", "typo"),
        Trigger("avocados limited today"),
        Trigger("got more honey in"),
        Trigger("no more strawberries, peppers running low, lemons are back", "multi"),
        Trigger("bread is gone", "multi"),
        Trigger("honey is sold out", "vague"),
        Trigger("we're low on stuff", "vague"),
        Trigger("everything is sold out"),
    ),
    slots=(Slot("items", "stock_items", True, ask="Which products, and in, low or out?"),),
    rules=("shelf-check-today", "not-already-true", "whole-shelf-max-6", "held-or-hidden-refused", "no-price"),
    plan=_set_plan, edits=_WORD_EDITS + ((_STORE, "selection_checked_on"),) + _GENERATED,
    side_effects=("inventory-word", "shelf-check-day"), preview=_PRODUCT_PREVIEW, approval="owner-yes",
    live_class="chat-live", undo=Undo("revert", "none"),
    refuse=(("a price is in the message", PRICE_REPLY),
            ("a product is hidden", HIDDEN),
            ("a product is on hold", HELD),
            ("more than six products", TOO_MANY),
            ("the product already says it", ALREADY)),
    cases=_CASES.format("stock.set"), version=2)

STOCK_CHECKED = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='full', logs=('subjects', 'fields'), who='owner',
    name="stock.checked", label="record the shelf check",
    summary="Record that the shelves were checked today (or a day this week), with what was found.",
    triggers=(
        Trigger("I checked the selection today: the avocados are in, the eggs are limited, the sourdough is sold out"),
        Trigger("chekced shelves, avos in eggs low bread out", "typo"),
        Trigger("checked everything this morning, all good"),
        Trigger("checked: lemons in, plums in, figs out, honey limited", "multi"),
        Trigger("did the rounds", "vague"),
        Trigger("I checked the shelves yesterday, eggs are out"),
        Trigger("I'll check tomorrow, eggs will be out"),
        Trigger("checked on Monday last month"),
        Trigger("checked, nothing changed"),
        Trigger("shelf chek done. milk in, cheese out", "typo"),
        Trigger("did the shelf check, all good"),
        Trigger("shelf check done"),
        Trigger("shelf check: all good"),
    ),
    slots=(Slot("day", "day"), Slot("in", "text_list"), Slot("limited", "text_list"), Slot("out", "text_list")),
    rules=("check-day-window", "each-product-once", "not-already-true", "held-or-hidden-refused"),
    plan=_checked_plan, edits=_WORD_EDITS + ((_STORE, "selection_checked_on"),) + _GENERATED,
    side_effects=("inventory-word", "shelf-check-day"), preview="home", approval="owner-yes",
    live_class="chat-live", undo=Undo("revert", "none"),
    refuse=(("the day is in the future", FUTURE),
            ("the day is more than a week ago", TOO_OLD),
            ("the day is before the last check", AFTER),
            ("a product is named twice", TWICE),
            ("the check is already recorded", DONE_TODAY)),
    cases=_CASES.format("stock.checked"), version=3)

STOCK_CLEAR = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='full', logs=('subjects', 'fields'), who='owner',
    name="stock.clear", label="stop showing a word on a product",
    summary="Take the in stock, low or sold out label off a product's card. Never sets sold out.",
    triggers=(
        Trigger("stop showing the eggs as sold out"),
        Trigger("remvoe the sold out tag from honey", "typo"),
        Trigger("take the limited label off the peppers"),
        Trigger("clear the words on eggs and honey", "multi"),
        Trigger("clear the labels", "vague"),
        Trigger("no label on the bread"),
        Trigger("the lemons shouldn't say anything"),
        Trigger("clear every product's word"),
        Trigger("undo the sold out on eggs"),
        Trigger("clear the plums"),
    ),
    slots=(Slot("items", "text_list", True, ask="Which products?"),),
    rules=("has-a-word", "held-or-hidden-refused", "whole-shelf-max-6"),
    plan=_clear_plan, edits=_WORD_EDITS + _GENERATED,
    side_effects=("inventory-word",), preview=_PRODUCT_PREVIEW, approval="owner-yes",
    live_class="chat-live", undo=Undo("revert", "none"),
    refuse=(("a product has no label", NO_WORD), ("a product is hidden", HIDDEN), ("a product is on hold", HELD),
            ("more than six products", TOO_MANY)),
    cases=_CASES.format("stock.clear"), version=1)

SKILLS = (STOCK_SET, STOCK_CHECKED, STOCK_CLEAR)
