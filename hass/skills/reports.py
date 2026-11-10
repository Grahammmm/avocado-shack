"""SKILLS-SOCIAL-1 part 3 (AV1109-08): the read-only shelf report skill ``report.shelf``.

Spec: reports/hass/SKILLS-SPEC.md section 3.30. Guide: docs/hass/skills/reports.md.

The answer is written by code, never by the model: the text is exactly ``morning_report.render(morning_report.facts(content,
today))`` for the saved content and the Pacific day the dispatcher hands over, with nothing added (no intro, no waiting list,
no clock of its own). The model only picks the skill. Nothing here writes a file, drafts, approves, sends or schedules: the
skill plans no op, and the report command (``report``) alone keeps the once-a-day shelf-check question.

Two asks get a fixed answer instead of the report, found by looking at the owner's own words (code, not a model):
  * a count question about one product ("how many eggs do we have"): Hass keeps no counts, so it says that and gives the
    product's own word from the last shelf check, using the same rule as the report (a word counts only when it is dated
    on the latest check; anything else is "not confirmed");
  * a request to send the report on its own ("email me the report every morning"): Hass sends nothing unasked.

Interface (AV1109-09 builds on it): ``REPORT_SHELF``, ``plan_shelf(slots, ctx) -> []``, ``shelf_reply(slots, ctx) -> str``,
``SKILLS`` and the module-local registration into ``dispatch.READ_ONLY`` and ``dispatch.READ_ONLY_LONG`` (a full report can
be longer than an everyday message, so only this skill's answer is delivered with ``long_ok``).
"""
from __future__ import annotations

import re
from datetime import date, datetime

from hass import morning_report, voice
from hass.content_model import ContentError, iso_day
from hass.skills import kinds
from hass.skills.model import Skill, Trigger, Undo, _fold

NO_PUSH = "I don't send reports on my own. Ask me for the morning report when you want it."
UNREADABLE = "I can't read the shelf report right now, so I can't tell you what's on the shelves. Nothing has changed."  # as the report command says it
NOT_ON_REPORT = "That one isn't in the shelf report right now, so I can't say what the last check found."
COUNTS_LEAD = "I don't keep counts; the last check says "
WORDS = {"yes": "available", "limited": "limited", "no": "sold out", None: "not confirmed"}

MAX_TEXT, MAX_TEXTS = 400, 5  # characters of each message and number of messages read; the rest cannot change which answer he gets
# Reading errors the report command itself answers with UNREADABLE (hass/conversation.py _report).
_UNREADABLE_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, ContentError)

_WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekday|weekend"
_DELIVERY = re.compile(
    r"\b(?:e ?mail|mail|send|sms|whatsapp|notify|remind|schedule|push|ping)\b"
    r"|\b(?:text|message) (?:me|us)\b"
    r"|\b(?:every|each|per) (?:single )?(?:morning|day|night|evening|afternoon|week|" + _WEEKDAYS + r")\b"
    r"|\b(?:automatic|automatically|on (?:its|your) own|by itself|without (?:me )?ask(?:ing)?|unprompted|proactive(?:ly)?)\b")
# 'how many eggs do we have', 'how much honey is left', 'number of eggs', 'stock of eggs'
_COUNT = re.compile(r"\b(?:how (?:many|much)|(?:number|count|quantity|amount|stock) of)\b(?P<rest>.*)$")
_COUNT_STOP = frozenset((
    "do does did have has had are is was were we i you there left remain remaining in on at can could would will should got still "
    "available now today right currently stock sold out low running more".split()))
_FILLER = frozenset("the a an any of all them those these".split())  # leading words that name nothing
_NOT_A_PRODUCT = frozenset((  # a count of these is a question about the whole report, which already holds the counts
    "thing things item items product products stuff kind kinds type types hike hikes guest guests people signup signups "
    "shelf shelves".split()))


# -- helpers -------------------------------------------------------------------------------------------------------
def _today(ctx):
    value = getattr(ctx, "today", None)
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else iso_day(value)


def _texts(ctx) -> list:
    """The owner's messages of this request, oldest first (bounded); [] when the dispatcher passed none. A which-task question
    in between adds a later message, so the ask is read from all of them, not only the last."""
    texts = [t for t in (getattr(ctx, "texts", None) or ()) if isinstance(t, str) and t.strip()]
    return [t[:MAX_TEXT] for t in texts[-MAX_TEXTS:]]


def asks_for_delivery(text) -> bool:
    return bool(_DELIVERY.search(_fold(text)))


def count_query(text):
    """The product words of a count question ('eggs'), '' when it asks for a count but names nothing Hass could look up
    (so the whole report answers), or None when the message is not a count question."""
    found = _COUNT.search(_fold(text))
    if not found:
        return None
    words = []
    for word in found["rest"].split():
        if word in _COUNT_STOP:
            break
        if words or word not in _FILLER:
            words.append(word)
    return "" if not words or all(w in _NOT_A_PRODUCT for w in words) else " ".join(words)


def _product(content, pid):
    return next((p for p in content.products if isinstance(p, dict) and p.get("id") == pid), None)


def _count_reply(content, facts, query, ctx) -> str:
    found = kinds.product_ref(content, query, getattr(ctx, "aliases", None))
    if found.status in ("none", "several"):
        return found.reply  # the resolver's one question; nothing is guessed
    product = _product(content, found.value) if found.status == "one" else None
    if product is None or product.get("status") != "active":
        return NOT_ON_REPORT  # held, hidden or unreadable: the report never shows it either
    fresh = facts["checked_on"] is not None and product.get("available_on") == facts["checked_on"]  # as morning_report.facts
    word = WORDS[product.get("available") if fresh and product.get("available") in ("yes", "limited", "no") else None]
    name = " ".join(str(product.get("name", "")).split())
    text = f"{COUNTS_LEAD}{voice.quote(name)}: {word}"
    if facts["checked_on"] is None or facts["stale"] or facts["future"]:
        text += "\n" + morning_report.check_line(facts)  # a missing, old or future-dated check is said, as in the report
    return text


# -- the plan and the answer -------------------------------------------------------------------------------------
def plan_shelf(slots, ctx) -> list:
    return []  # read only: the owner's answer is ``shelf_reply``; the context is not read


def shelf_reply(slots, ctx) -> str:
    """What the owner gets: the report text, a no-counts answer for one product, or the no-push sentence."""
    texts = _texts(ctx)
    if any(asks_for_delivery(t) for t in texts):
        return NO_PUSH
    try:
        today, content = _today(ctx), getattr(ctx, "content", None)
        if today is None or content is None:
            raise ValueError("no content or day")
        facts = morning_report.facts(content, today)  # raises ValueError on a product record the report cannot read
        query = next((q for q in (count_query(t) for t in reversed(texts)) if q is not None), None)  # the latest count question
        if not query:
            return morning_report.render(facts)
        return _count_reply(content, facts, query, ctx)
    except _UNREADABLE_ERRORS:
        return UNREADABLE


# -- declaration -------------------------------------------------------------------------------------------------------
REPORT_SHELF = Skill(
    name="report.shelf", label="morning shelf report",
    summary="Say what is sold out or running low from the last shelf check, and any hikes. Not stock counts; sends nothing.",
    triggers=(
        Trigger("morning report"),
        Trigger("what's sold out?"),
        Trigger("wat is low today", "typo"),
        Trigger("how are we doing", "vague"),
        Trigger("what's on the shelves"),
        Trigger("what's sold out and what hikes are coming up", "multi"),
        Trigger("anything waiting for me?"),
        Trigger("what did I check last"),
        Trigger("how many eggs do we have"),
        Trigger("email me the report every morning"),
    ),
    slots=(), rules=(), plan=plan_shelf, edits=(), side_effects=("none",), preview="none", approval="none",
    live_class="read-only", undo=Undo("none", "none"),
    refuse=(
        ("a count question: Hass keeps no counts", COUNTS_LEAD + "eggs: limited"),
        ("a request to send the report on its own", NO_PUSH),
    ),
    cases="hass/tests/fixtures/skills/reports/report.shelf.jsonl", version=1)

SKILLS = (REPORT_SHELF,)


def _register() -> None:
    """Hand the answer to the dispatcher (idempotent, like specials.show) and mark it as a long answer. Never raises."""
    try:
        from hass.skills import dispatch
    except ImportError:
        return
    dispatch.READ_ONLY.setdefault(REPORT_SHELF.name, shelf_reply)
    dispatch.READ_ONLY_LONG.add(REPORT_SHELF.name)


_register()
