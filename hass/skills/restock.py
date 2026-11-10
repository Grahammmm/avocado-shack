"""AV1109-04 (SKILLS-STOCK-2 part 2): when more of a product is coming. One skill, ``stock.restock``, over the private
product day ``restock_on`` that AV1109-03's ``product.set_restock`` keeps.

Spec: reports/hass/SKILLS-SPEC.md 3.8. Owner words: docs/hass/VOICE.md. Page: docs/hass/skills/restock.md.

Slots: ``item`` (a product, asked "Which product?"), ``day`` (asked "What day is more coming?"; not needed to clear) and
``clear`` ("never mind the restock"). Two products in one message are two calls of this skill, not a new slot.

* Rules: the day is today or later and at most 60 days ahead; only an active product; a restock day is never a count and
  never sets the shelf word (this skill plans only ``product.set_restock``); nothing is ever counted ("I don't keep counts
  yet"); a day that is already set, or a clear with nothing set, changes nothing.
* The plan is a pure function of the resolved slots (a product id, an ISO day) and an optional ``ctx`` (``ctx.today`` as an
  ISO Pacific day or a date, ``ctx.content`` as the loaded content, ``ctx.texts`` as the owner's words). Without
  ``ctx.content`` the product's existence and state are left to the typed op, which repeats every rule. A day it cannot
  judge (no ``ctx.today``) is asked for, never guessed.
* ``question`` and ``notes`` are the dispatcher's optional hooks: the counts sentence goes in front of the one question
  asked, and the date shown before the owner's yes is the report's own wording (``morning_report.restock_text``).
* ``live_class`` is ``private-only``: ``product.set_restock`` is in neither live table yet (``hass/live_policy.py``), so a
  real draft stays refused until the operator lists it. Nothing here widens that.
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import voice  # noqa: E402
from hass.content_model import ID_RE, iso_day  # noqa: E402
from hass.morning_report import restock_day, restock_text  # noqa: E402
from hass.ops.restock import FIELD, MAX_AHEAD  # noqa: E402
from hass.skills.model import Skill, Slot, Trigger, Undo  # noqa: E402

ASK_ITEM, ASK_DAY = "Which product?", "What day is more coming?"
ASKS = {"item": ASK_ITEM, "day": ASK_DAY}
COUNTS = "I don't keep counts yet."
COUNTS_REFUSED = COUNTS + " Tell me the product and day without a count."
HIDDEN = "{name} is hidden. Do you want me to bring it back first?"
HELD = "I can't change {name} right now. It is on hold until someone has looked at it."
UNKNOWN = "I don't know a product called that. Which product?"
PAST = "{when} has already passed. Tell me a day from today on."
TOO_FAR = f"I only note a restock up to {MAX_AHEAD} days ahead. Tell me an earlier day."
ALREADY = "{name} already says more is expected {when}. Nothing to change."
NOTHING_SET = "{name} has no restock day to clear. Nothing to change."
NOT_BOTH = "A restock day and clearing it are two different things. Which one do you want?"
SHELF_SAME = "This does not change what the shelf says."

# a number with a unit of goods: "40 jars", "2 dozen", "12 lbs", "x40". A date ("the 14th") or a wait ("in 2 weeks") is not one.
UNITS = ("jars?|bottles?|boxes|box|bags?|cartons?|dozens?|cases?|crates?|units?|pieces?|pcs|packs?|packets?|loaves|loaf|cans?|tubs?|"
         "trays?|pints?|quarts?|gallons?|liters?|litres?|lbs?|pounds?|oz|ounces?|kg|kilos?|kilograms?|grams?|items?|bunch(?:es)?")
QUANTITY = re.compile(rf"(?<![\w.])\d[\d,]*(?:\.\d+)?\s*(?:x\s*)?(?:{UNITS})\b|\b[x×]\s*\d+\b|\b\d+\s*[x×](?!\w)", re.IGNORECASE)


class Refusal(ValueError):
    """A plan that cannot go on. ``reply`` is the owner's sentence; ``kind`` is "question" when one answer fixes it, else
    "refuse"; ``backlog`` names a backlog reason, or None."""

    def __init__(self, reply, kind="refuse", backlog=None):
        super().__init__(reply)
        self.reply, self.kind, self.backlog = reply, kind, backlog


# -- plain helpers ------------------------------------------------------------------------------------------------
def _texts(ctx) -> list:
    texts = getattr(ctx, "texts", None)
    return [t for t in texts if isinstance(t, str)] if isinstance(texts, (list, tuple)) else []


def _counted(ctx) -> bool:
    """True when the owner's words carry a quantity (a number with a unit of goods), never a date or a wait."""
    return any(QUANTITY.search(t) for t in _texts(ctx))


def _today(ctx):
    """ctx.today as a date, from the dispatcher's date or the kit's ISO text; None when absent or unreadable (no ambient clock)."""
    raw = getattr(ctx, "today", None)
    return raw if type(raw) is date else iso_day(raw)


def _product(ctx, pid):
    content = getattr(ctx, "content", None)
    if content is None:
        return None
    return next((p for p in getattr(content, "products", ()) if isinstance(p, dict) and p.get("id") == pid), None)


def _q(text) -> str:
    return voice.quote(" ".join(str(text).split()))


def _ask(slot, ctx) -> str:
    return (COUNTS + " " if _counted(ctx) else "") + ASKS[slot]


# -- the plan -----------------------------------------------------------------------------------------------------
def _plan(slots, ctx=None) -> list:
    """One ``product.set_restock`` call (a day, or ``clear``), or a Refusal. Reads only: nothing is written."""
    slots = slots if isinstance(slots, dict) else {}
    pid, clear, day = slots.get("item"), slots.get("clear") is True, slots.get("day")
    if not (isinstance(pid, str) and ID_RE.fullmatch(pid)):
        raise Refusal(_ask("item", ctx), "question")
    if clear and day is not None:
        raise Refusal(NOT_BOTH, "question")
    when = None if clear else iso_day(day)
    if not clear and when is None:  # missing or not a real YYYY-MM-DD: ask, never guess
        raise Refusal(_ask("day", ctx), "question")
    if _counted(ctx):  # a complete request that carries a quantity: nothing is written, not even the date
        raise Refusal(COUNTS_REFUSED)
    product = _product(ctx, pid)
    if getattr(ctx, "content", None) is not None:
        if product is None:
            raise Refusal(UNKNOWN, "question")
        if product.get("status") != "active":  # hidden and held products are named and refused, never restored here
            raise Refusal((HELD if product.get("status") == "held" else HIDDEN).format(name=_q(product.get("name", ""))))
    name = _q(product.get("name", "")) if product else ""
    if clear:
        if product is not None and FIELD not in product:
            raise Refusal(NOTHING_SET.format(name=name))
        return [{"op": "product.set_restock", "args": {"id": pid, "clear": True}}]
    today = _today(ctx)
    if today is None:  # the window cannot be judged without today: ask rather than guess
        raise Refusal(ASK_DAY, "question")
    if when < today:
        raise Refusal(PAST.format(when=restock_day(when)))
    if when > today + timedelta(days=MAX_AHEAD):
        raise Refusal(TOO_FAR)
    if product is not None and product.get(FIELD) == when.isoformat():
        raise Refusal(ALREADY.format(name=name, when=restock_day(when)))
    return [{"op": "product.set_restock", "args": {"id": pid, FIELD: when.isoformat()}}]


# -- the dispatcher's hooks ---------------------------------------------------------------------------------------
def question(slot_name, slots, ctx):
    """The one question for a missing slot, with the counts sentence in front when the owner gave a quantity; None keeps the ask."""
    return _ask(slot_name, ctx) if slot_name in ASKS and _counted(ctx) else None


def notes(name, slots, ctx) -> dict:
    """Lines shown beside the draft, before the owner's yes: the date exactly as the report will say it (a day computed from
    'in 2 weeks' is shown here), and that the shelf word stays as it is."""
    try:
        args = _plan(dict(slots), ctx)[0]["args"]
    except Refusal:
        return {}
    product = _product(ctx, args["id"])
    if product is None:
        return {}
    if args.get("clear"):
        return {"say": [f"I'll take the restock day off {_q(product.get('name', ''))}."]}
    return {"say": [restock_text(product.get("name", ""), args[FIELD]) + ".", SHELF_SAME]}


# -- the skill ----------------------------------------------------------------------------------------------------
_PRODUCTS = "hass/content/products.json"

STOCK_RESTOCK = Skill(
    name="stock.restock", label="record when more is coming", version=1,
    summary="Note the day more of one product is expected. A day only; never a count, never the shelf word.",
    triggers=(
        Trigger("more honey coming Thursday"),
        Trigger("egs back on firday", "typo"),
        Trigger("restock the lemons on the 14th"),
        Trigger("honey and eggs both back Thursday", "multi"),
        Trigger("more soon", "vague"),
        Trigger("the bread truck comes Monday"),
        Trigger("more honey last Tuesday"),
        Trigger("never mind about the honey restock"),
        Trigger("eggs back in 2 weeks"),
        Trigger("restock 40 jars of honey"),
    ),
    slots=(
        Slot("item", "product_ref", required=True, ask=ASK_ITEM),
        Slot("day", "day", required="unless:clear", ask=ASK_DAY),
        Slot("clear", "bool"),
    ),
    rules=("active-product-only", "restock-window", "no-quantity", "never-sets-shelf-word", "not-already-true"),
    plan=_plan, edits=((_PRODUCTS, "products[id].restock_on"),),
    side_effects=("restock-date",), preview="none", approval="owner-yes",
    live_class="private-only",  # product.set_restock is not in the live boundary (hass/live_policy.py); its owner lists it
    undo=Undo("revert", "none"),
    refuse=(
        ("the day has already passed", PAST),
        ("the day is more than 60 days ahead", TOO_FAR),
        ("the message carries a quantity", COUNTS_REFUSED),
        ("the product is hidden", HIDDEN),
        ("the product is on hold", HELD),
        ("the product already has that day", ALREADY),
        ("there is no restock day to clear", NOTHING_SET),
    ),
    cases="hass/tests/fixtures/skills/restock/stock.restock.jsonl",
)

SKILLS = (STOCK_RESTOCK,)
