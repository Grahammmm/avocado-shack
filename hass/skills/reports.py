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
import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

from hass import morning_report, voice
from hass.content_model import ContentError, iso_day
from hass.skills import kinds
from hass.skills.model import Skill, Slot, Trigger, Undo, _fold

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
    words, rest = [], found["rest"].split()
    for i, word in enumerate(rest):
        if word in _COUNT_STOP:
            # 'low' is a stock state ('how many eggs low'), but it is part of a name when a product word follows
            # ('low fat milk'): one token of lookahead, no adjective list.
            following = rest[i + 1] if i + 1 < len(rest) else None
            if word != "low" or following is None or following in _COUNT_STOP or following in _FILLER:
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
    pack='reports', targets=(), approval_class='A0', sandbox='none-needed', logs=(), who='owner',
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

# -- deterministic site answers (AV1109-09) -----------------------------------------------------------------------
KINDS = ("hours", "next_hike", "product", "product_maker", "maker_story", "hike_count", "hike_signups")
SUBJECTS = {"product": "product", "product_maker": "product", "maker_story": "maker", "hike_signups": "hike"}
_SUBJECT_NAMES = {"product": "the product's name", "maker": "the maker's name", "hike": "the hike's name"}
# The interpreter prompt shows these (hass/skills/prompt.py), built from KINDS and SUBJECTS so they cannot drift.
KIND_HINT = "exactly one of (" + " | ".join(KINDS) + "), spelled that way"
SUBJECT_HINT = "(" + ", ".join(
    f"{_SUBJECT_NAMES[fam]} for {' or '.join(k for k in KINDS if SUBJECTS.get(k) == fam)}" for fam in dict.fromkeys(SUBJECTS.values())
) + "), left out for other kinds"
DAY_HINT = "only for hours"
SITE_ASK = "What would you like to know about the site?"
SITE_UNREADABLE = "I can't read that from the site right now. Nothing has changed."
NO_MAKER = "I can't see who makes that on the site."
NO_STORY = "I can't see a story for that maker on the site."
NO_HOURS = "I can't see the opening hours on the site."
NO_HIKE = "There are no upcoming hikes on the site."
PACIFIC = ZoneInfo("America/Los_Angeles")
_DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DAY_WORDS = {word: i for i, name in enumerate(_DAY_NAMES) for word in (name, name[:3])}
_DAY_WORDS.update({"tues": 1, "weds": 2, "thur": 3, "thurs": 3})
_DAY_TOKEN = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|thurs|tues|weds|thur|mon|tue|wed|thu|fri|sat|sun)\b"
_DAY_RANGE = re.compile(r"\b(" + _DAY_TOKEN + r")\s*[–—-]\s*(" + _DAY_TOKEN + r")", re.I)
_DAY_MATCH = re.compile(r"\b" + _DAY_TOKEN, re.I)
_PRICE_ASK = re.compile(r"\b(?:prices?|costs?|dollars?|bucks|usd)\b|\$|\bhow much (?:is|are|does)\b", re.I)
_SALES_ASK = re.compile(r"\b(?:sales|revenue|profit|profits|earnings|turnover)\b|\bhow (?:many|much).*\bsold\b", re.I)
_STOCK_ASK = re.compile(r"\b(?:stock (?:count|quantity)|inventory count|quantity|units|pieces)\b", re.I)


def _site_resolve(slots, ctx):
    """One safe problem or one record; shared by the rule and formatter, with no chat state."""
    kind = slots.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        return SITE_ASK, None
    if (slots.get("day") is not None and kind != "hours") or (slots.get("subject") is not None and kind not in SUBJECTS):
        return SITE_ASK, None
    if kind == "hours" and slots.get("day") is not None:
        day = kinds.day(slots["day"], _today(ctx)) if isinstance(slots["day"], str) else None
        if day is None or day.status != "one":
            return "Which day do you mean?", None
    family = SUBJECTS.get(kind)
    if family is None:
        return None, None
    subject = slots.get("subject")
    if family == "hike":
        found = kinds.hike_ref(ctx.content, subject)
    else:
        found = getattr(kinds, family + "_ref")(ctx.content, subject, getattr(ctx, "aliases", None))
    if found.status != "one":
        return found.reply, None
    if family == "product":
        record = _product(ctx.content, found.value)
    elif family == "maker":
        record = ctx.content.makers.get(found.value)
    else:
        record = next((e for e in ctx.content.community.get("events", []) if e.get("id") == found.value), None)
    return (None, record) if record else (SITE_UNREADABLE, None)


def site_guard(slots, texts, ctx):
    """Closed kinds and unsupported owner requests go to the existing one-row backlog path."""
    from hass.interpret_check import PRICE_REPLY
    text = "\n".join(t for t in texts if isinstance(t, str))
    if _PRICE_ASK.search(text):
        return PRICE_REPLY, "price"
    if _SALES_ASK.search(text):
        return "I can't see sales from the site.", "other"
    query = count_query(text)
    if re.search(r"\b(?:hikes?|guests?|people|signups?|signed up|sign-ups?)\b", text, re.I):
        query = None
    if _STOCK_ASK.search(text) or query is not None:
        try:
            facts = morning_report.facts(ctx.content, _today(ctx))
            reply = _count_reply(ctx.content, facts, query, ctx) if query else "I don't keep stock counts."
        except _UNREADABLE_ERRORS:
            reply = "I don't keep stock counts."
        return reply, "other"
    try:
        problem, _record = _site_resolve(slots, ctx)
    except _UNREADABLE_ERRORS:
        problem = SITE_UNREADABLE
    return (problem, "other") if problem else None


def _hours_reply(slots, ctx):
    lines = ctx.content.store.get("hours") or []
    if not isinstance(lines, list) or not lines or not all(isinstance(s, str) and s.strip() for s in lines):
        return NO_HOURS
    raw_day = slots.get("day")
    target = date.fromisoformat(kinds.day(raw_day, _today(ctx)).value) if raw_day else _today(ctx)
    matches, uncertain = [], False
    for line in lines:
        for clause in re.split(r"[·;\n]+", line):
            clause = clause.strip()
            days = set()
            ranges = list(_DAY_RANGE.finditer(clause))
            for match in ranges:
                start, end = (_DAY_WORDS[w.lower()] for w in match.groups())
                days.update((start + n) % 7 for n in range((end - start) % 7 + 1))
            remainder = _DAY_RANGE.sub("", clause)
            days.update(_DAY_WORDS[m.group().lower()] for m in _DAY_MATCH.finditer(remainder))
            if re.search(r"\b(?:daily|every day)\b", clause, re.I):
                days.update(range(7))
            if not days:
                uncertain = True
            if target.weekday() in days:
                matches.append(clause)
    if len(matches) == 1 and not uncertain:
        return "The site says: " + voice.quote(matches[0])
    return "I can't tell which hours apply that day. The site lists:\n" + "\n".join(voice.quote(s) for s in lines)


def _upcoming(ctx):
    now = ctx.now
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("aware clock required")
    upcoming = []
    for event in ctx.content.community.get("events", []):
        if not isinstance(event, dict) or event.get("status") != "scheduled" or event.get("sample") is True:
            continue
        try:
            start = datetime.fromisoformat(event.get("startsAt", ""))
        except (TypeError, ValueError):
            continue
        if start.utcoffset() is not None and start > now:
            upcoming.append((start, str(event.get("id", "")), event))
    return sorted(upcoming, key=lambda row: (row[0], row[1]))


def plan_site(slots, ctx):
    return []


def site_reply(slots, ctx):
    """Only content and confirmed RSVP totals supply answers, never undeclared model prose."""
    if not isinstance(slots, dict):
        return SITE_ASK
    try:
        hit = site_guard(slots, _texts(ctx), ctx)
        if hit:
            return hit[0]
        _problem, record = _site_resolve(slots, ctx)
        kind, content = slots["kind"], ctx.content
        if kind == "hours":
            return _hours_reply(slots, ctx)
        if kind in ("next_hike", "hike_count"):
            events = _upcoming(ctx)
            if kind == "hike_count":
                return f"Upcoming hikes on the site: {len(events)}."
            if not events:
                return NO_HIKE
            start, _eid, event = events[0]
            if not all(isinstance(event.get(f), str) and event[f].strip() for f in ("title", "meetingPoint")):
                return "I can't see all the details for the next hike on the site."
            local = start.astimezone(PACIFIC)
            when = local.strftime("%A, %B %-d at %-I:%M %p").replace(":00", "").lower()
            return f"Next hike: {voice.quote(event['title'])}, {when}. Meet at {voice.quote(event['meetingPoint'])}."
        if kind == "product":
            facts = morning_report.facts(content, _today(ctx))
            shelf = _count_reply(content, facts, slots["subject"], ctx).removeprefix(COUNTS_LEAD)
            return "On the saved site; the last check says " + shelf
        if kind == "product_maker":
            maker = content.makers.get(record.get("producerKey"))
            if not maker or maker.get("hidden") or not maker.get("name"):
                return NO_MAKER
            name = voice.quote(maker["name"])
            return f"Made by {name} in {voice.quote(maker['place'])}." if maker.get("place") else f"Made by {name}. I can't see where on the site."
        if kind == "maker_story":
            return voice.quote(record["story"]) if record.get("story") else NO_STORY
        if kind == "hike_signups":
            count = "unavailable"
            path = getattr(ctx, "guest_counts_db", None)
            if path:
                from hass.ops.hikes import guest_counts_checked
                try:
                    counts, bad = guest_counts_checked(path)
                    if record["id"] not in bad:
                        count = counts.get(record["id"], 0)
                except (sqlite3.Error, OSError, ValueError, TypeError):
                    pass
            return f"Confirmed sign-ups for {voice.quote(record['title'])}: {count}."
    except _UNREADABLE_ERRORS:
        return SITE_UNREADABLE
    return SITE_ASK


ANSWER_SITE = Skill(
    pack='core', targets=(), approval_class='A0', sandbox='none-needed', logs=(), who='owner',
    name="answer.site", label="answer a site question",
    summary="Answer hours, products, makers and hikes from saved site content; confirmed sign-ups only, never prices or sales.",
    triggers=(Trigger("what time do we close Saturday"), Trigger("when is the next hike"),
              Trigger("is honey on the site"), Trigger("who makes the honey and where"),
              Trigger("tell me the maker's story"), Trigger("how many upcoming hikes are scheduled"),
              Trigger("how many signed up for Cass Hill"), Trigger("wat are the hours", "typo"),
              Trigger("what does the site say", "vague"), Trigger("when and where is our next hike", "multi")),
    slots=(Slot("kind", "enum", True, ask=SITE_ASK, hint=KIND_HINT), Slot("subject", "text", hint=SUBJECT_HINT),
           Slot("day", "day", hint=DAY_HINT)),
    rules=("site-guard",), plan=plan_site, edits=(), side_effects=("none",), preview="none", approval="none",
    live_class="read-only", undo=Undo("none", "none"),
    refuse=(("prices", "The website doesn't show prices."), ("sales", "I can't see sales from the site.")),
    cases="hass/tests/fixtures/skills/reports/answer.site.jsonl", version=1)


SKILLS = (REPORT_SHELF,)  # core-pack export lives in answer_site.py


def _register() -> None:
    """Hand the answer to the dispatcher (idempotent, like specials.show) and mark it as a long answer. Never raises."""
    try:
        from hass.skills import dispatch
    except ImportError:
        return
    dispatch.READ_ONLY.setdefault(REPORT_SHELF.name, shelf_reply)
    dispatch.READ_ONLY_LONG.add(REPORT_SHELF.name)
    dispatch.READ_ONLY.setdefault(ANSWER_SITE.name, site_reply)
    dispatch.RULES.setdefault("site-guard", site_guard)


_register()
