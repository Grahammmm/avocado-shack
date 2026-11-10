"""Hike skills (SKILLS-HIKES-1): add, edit, reschedule, cancel, repeat and recap a hike, plus the post-hike announcement draft.

Six skills (``hike.add``, ``hike.edit``, ``hike.reschedule``, ``hike.cancel``, ``hike.repeat``, ``hike.recap``), each the
data of ``hass.skills.model.Skill`` plus one pure ``plan(slots, ctx)`` that turns slots the dispatcher has already
checked into typed ``hike.*`` ops. Nothing here writes a file, calls a network or touches the editor, the claims gate,
approval, the live boundary or the conversation: every draft still goes through ``editor.prepare`` and ``yes <code>``.
Spec: reports/hass/SKILLS-SPEC.md 3.10 to 3.15 and 4.2 card 9. Guide: docs/hass/skills/hikes.md.

What the plans guarantee (the E2E-HIKE-1 and HIKE-FLOW-1 findings, pinned by the case rows):

* a hike is drafted from what the owner said and nothing else: ``rsvpEnabled`` is ``False`` unless sign-up was said
  (decision D8: the proposal carries the line ``I set: sign-up off``), ``capacity`` is written only with sign-up on, and
  difficulty, distance, duration, bring and the access note are written exactly as given, never filled in;
* a place that is not a route idea is plain meeting-point text; ``trailId`` is set only when the owner named a route idea;
* a start in the past, a twin (same day and title), a hike that is not scheduled, a price: the owner gets one plain reply
  and nothing is drafted;
* guests who signed up, a move or a cancel: the editor's own warning ("nobody is told automatically") stays on the draft.

Interface assumptions about SKILLS-FW-3 (``hass/skills/dispatch.py``, open as PR 526; nothing in this module imports it
unless it is present): rules are ``RULES[id](slots, texts, ctx) -> None | (owner reply, backlog reason)``; a default
``derive:<name>`` is a module-level function of the plan's module or in ``DERIVERS``; ``ctx`` has ``content`` (read-only),
``today`` (a date or an ISO string), ``now`` and ``texts`` (the owner's words of this request). Every name below degrades
without them: the plans work on slots alone and refuse nothing they cannot see. ``SET_PHRASES[skill](slots, ctx)`` is how the
``I set:`` line of D8 is worded (the generic ``name: value`` rendering of a default would read "signup: False"): the test kit
consumes it today (its stand-in dispatcher puts ``set_line(...)`` in front of the proposal, so the owner reply is asserted
end to end); the real dispatcher must call it the same way (docs/hass/skills/hikes.md, "The I set line").
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import nl_prep, voice  # noqa: E402
from hass.ops.hikes import MAX_AHEAD_DAYS, TZ  # noqa: E402
from hass.skills.model import Skill, Slot, Trigger, Undo  # noqa: E402
from hass.social_draft import HIKE_TAGS, MAX_CAPTION  # noqa: E402

TEXT_SLOTS = ("difficulty", "distance", "duration", "bring", "access_note", "description")  # written as the owner gave them
EDIT_TEXT_SLOTS = ("title", "meeting_point") + TEXT_SLOTS
ARG = {"meeting_point": "meetingPoint", "access_note": "accessNote"}  # slot names are snake_case (the lint); ops and content are not

# -- what the owner is told (plain words: docs/hass/VOICE.md) ---------------------------------------------------------
R_PRICE = "The website doesn't show prices, so I haven't changed anything. Could you send it without the price?"
R_PAST_DAY = "That day has already passed. Which day do you mean?"
R_PAST_TIME = "That time has already passed today. What time do you mean?"
R_FAR = "That is more than a year away. Could you check the day?"
R_WHAT_MOVE = "What day or time should it move to?"
R_SIGNUP_NOT_SAID = "You didn't say guests can sign up, so I haven't turned it on. Should guests be able to sign up?"
R_SPOTS_NOT_SAID = "You didn't say how many can come, so I haven't set a limit. How many can come, or is there no limit?"
R_CAP_MAX = "The most I can set is 6."  # G 2026-11-08 "available spots (max 6)"; decision 2 stays open, so 6 is the ceiling
R_NO_RECAP_YET = "Say how it went first, then I can write the post."

R_SIGNUP_UNCLEAR = "I'm not sure if you want guests to be able to sign up. Should they?"

_SIGNUP_WORDS = re.compile(r"\b(sign ?-?ups?|signing up|rsvps?|register(?:ed|ing)?|reserv\w*|how many can|people can (?:join|come|sign))\b", re.I)
# only words about SIGNING UP decide its direction: "limited parking", "no space for dogs" or "a seat cushion" say nothing about it;
# a guest limit ("15 spots", "max 12") is read by _said_limits and counts as the owner asking for sign-up
# "per person"/"per head" is a price only right after a number ("12 per person"); "Bring water per person" is packing advice
_PRICE = re.compile(r"\$\s*\d|\b\d+(?:\.\d\d)?\s*(?:dollars?|bucks|usd)\b|\bper\s+(?:lb|pound|oz|ounce|kg|dozen)\b|\b\d+(?:\.\d+)?\s+per\s+(?:person|head)\b", re.I)
_PLACE_TAIL = re.compile(r"(?:^|\s+)(?:trail ?head|gate|entrance|parking(?:\s+lot)?|lot|staging area|picnic area)\s*$", re.I)
_PLACE_HEAD = re.compile(r"^(?:the|at|by)\s+", re.I)
_TAG_RE = re.compile(r"[#@\uFF03\uFF20\uFE5F\uFE6B]\w")  # as social_draft: no hashtag or account in free text


class Refusal(ValueError):
    """A plan or rule that refuses carries the fixed owner reply (the test kit plays it back as the reply)."""

    def __init__(self, reply):
        super().__init__(reply)
        self.reply = reply


# -- reading the context (all optional: a plan row may give only ``today``) -------------------------------------------
def _iso(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _today(ctx):
    t = getattr(ctx, "today", None)
    if isinstance(t, datetime):
        return t.date()
    return t if isinstance(t, date) else _iso(t)


def _now_local(ctx):
    n = getattr(ctx, "now", None)
    return n.astimezone(TZ) if isinstance(n, datetime) and n.tzinfo else None


def _events(ctx):
    """The hikes on the page, or None when the context carries no content."""
    content = getattr(ctx, "content", None)
    community = content.get("community") if isinstance(content, dict) else getattr(content, "community", None)
    events = community.get("events") if isinstance(community, dict) else None
    return [e for e in events if isinstance(e, dict)] if isinstance(events, list) else None


def _routes(ctx):
    content = getattr(ctx, "content", None)
    community = content.get("community") if isinstance(content, dict) else getattr(content, "community", None)
    ideas = community.get("routeIdeas") if isinstance(community, dict) else None
    return [r for r in ideas if isinstance(r, dict)] if isinstance(ideas, list) else []


def _event(ctx, event_id):
    return next((e for e in _events(ctx) or () if e.get("id") == event_id), None) if event_id else None


def _local(starts_at):
    """(Pacific date, "HH:MM") of an ISO start; (None, None) when it cannot be read."""
    try:
        d = datetime.fromisoformat(str(starts_at).replace("Z", "+00:00")).astimezone(TZ)
    except (ValueError, TypeError):
        return None, None
    return d.date(), d.strftime("%H:%M")


def _fold(text) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(text)).split()).casefold()


def _day_words(d: date) -> str:
    return f"{d:%A, %B} {d.day}"


def _name(event) -> str:
    title = event.get("title") if isinstance(event, dict) else None
    return "the hike " + voice.quote(title) if isinstance(title, str) and title.strip() else "that hike"


def _text(value):
    return value.strip() if isinstance(value, str) else value


def _given(slots, name):
    value = slots.get(name)
    return value if isinstance(value, str) and value.strip() else None


# -- rules: RULES[id](slots, texts, ctx) -> None | (owner reply, backlog reason) -----------------------------------------
def _when_problem(day, clock, ctx):
    d, today = _iso(day), _today(ctx)
    if d is None or today is None:
        return None  # the slot kind check is the dispatcher's; nothing to compare with
    if d < today:
        return R_PAST_DAY
    if (d - today).days > MAX_AHEAD_DAYS:
        return R_FAR
    now = _now_local(ctx)
    if d == today and isinstance(clock, str) and now is not None:
        try:
            if time.fromisoformat(clock) <= now.time():
                return R_PAST_TIME
        except ValueError:
            return None
    return None


def rule_no_price(slots, texts, ctx):
    hit = any(_PRICE.search(v) for k, v in slots.items() if isinstance(v, str) and k in EDIT_TEXT_SLOTS + ("recap", "note"))
    return (R_PRICE, "price") if hit else None


def rule_in_future(slots, texts, ctx):
    event = _event(ctx, slots.get("hike"))
    old_day, old_clock = _local(event.get("startsAt")) if event else (None, None)
    day, clock = slots.get("day") or (old_day.isoformat() if old_day else None), slots.get("clock") or old_clock
    if not (slots.get("day") or slots.get("clock")):
        return None
    reply = _when_problem(day, clock, ctx)
    return (reply, "other") if reply else None


def _twin_reply(ctx, day, title, skip=None):
    wanted = _iso(day)
    for e in _events(ctx) or ():
        if wanted and e.get("status") == "scheduled" and e.get("id") != skip and _fold(e.get("title", "")) == _fold(title) \
                and _local(e.get("startsAt"))[0] == wanted:
            return f"There is already a hike called {voice.quote(e['title'])} on {_day_words(wanted)}. Do you want to change that one instead?"
    return None


def rule_twin(slots, texts, ctx):
    """Adding a hike with the same day and title as a scheduled one."""
    if not (_given(slots, "title") and _iso(slots.get("day"))):
        return None
    reply = _twin_reply(ctx, slots["day"], slots["title"])
    return (reply, "other") if reply else None


def rule_repeat_twin(slots, texts, ctx):
    """Repeating a hike onto a day that already has a scheduled hike of that title."""
    source = _event(ctx, slots.get("hike"))
    if source is None or not _iso(slots.get("day")):
        return None
    reply = _twin_reply(ctx, slots["day"], source.get("title", ""))
    return (reply, "other") if reply else None


def rule_scheduled(slots, texts, ctx):
    """A hike that is cancelled or done cannot be changed or moved (a cancelled hike has its own reply when cancelling)."""
    event = _event(ctx, slots.get("hike"))
    if event is None or event.get("status") == "scheduled":
        return None
    why = "is cancelled" if event.get("status") == "cancelled" else "has already happened"
    return f"{_name(event).capitalize()} {why}, so I can't change it.", "other"


def rule_cancel_state(slots, texts, ctx):
    event = _event(ctx, slots.get("hike"))
    if event is None or event.get("status") == "scheduled":
        return None
    if event.get("status") == "cancelled":
        return f"{_name(event).capitalize()} is already cancelled.", "other"
    return f"{_name(event).capitalize()} has already happened, so I can't cancel it.", "other"


def rule_already_then(slots, texts, ctx):
    """A move to the day and time it already has."""
    event = _event(ctx, slots.get("hike"))
    if event is None or not (slots.get("day") or slots.get("clock")):
        return None
    old_day, old_clock = _local(event.get("startsAt"))
    if old_day is None:
        return None
    new_day, new_clock = slots.get("day") or old_day.isoformat(), slots.get("clock") or old_clock
    return (f"{_name(event).capitalize()} already starts then. Did you mean something else?", "other") \
        if (new_day, new_clock) == (old_day.isoformat(), old_clock) else None


def rule_recap_state(slots, texts, ctx):
    event = _event(ctx, slots.get("hike"))
    if event is None:
        return None
    if event.get("status") == "cancelled":
        return f"{_name(event).capitalize()} was cancelled, so there is no recap to write.", "other"
    start = event.get("startsAt")
    now = getattr(ctx, "now", None)
    if event.get("status") == "scheduled" and isinstance(now, datetime) and now.tzinfo and isinstance(start, str):
        try:
            if datetime.fromisoformat(start.replace("Z", "+00:00")) > now:
                return f"{_name(event).capitalize()} hasn't happened yet, so there is nothing to recap.", "other"
        except ValueError:
            return None
    return None


_CLAUSE_SPLIT = re.compile(r"[.;!?\n,]+|\s+(?:but|however|though)\s+", re.I)
_NEGATED = re.compile(r"\b(?:no|not|never|without|nobody|none|cannot|skip|off|disabled?|closed?)\b|n't\b", re.I)
_NO_LIMIT = re.compile(r"\b(?:no|without\s+a|without\s+any|without)\s+(?:limit|cap|max(?:imum)?)\b|\bunlimited\b", re.I)
_DATE_TIME = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}:\d{2}\s*(?:[ap]\.?m\.?)?|"
                        r"\b\d{1,2}\s*[ap]\.?m\b\.?|\b\d{1,2}(?:st|nd|rd|th)\b|\b(?:19|20)\d\d\b|"
                        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b|"
                        r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b|"
                        r"\b(?:at|around|about|by|from|until|till)\s+\d{1,2}\b|\bo'?clock\b", re.I)
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60}
_UNITS = {w: v for w, v in nl_prep.WORD_NUMBERS.items() if 0 < v < 10}
_NUM_WORD = re.compile(r"\b(?:(" + "|".join(_TENS) + r")[\s-]+(" + "|".join(_UNITS) + r")|(" +
                       "|".join(sorted(nl_prep.WORD_NUMBERS, key=len, reverse=True)) + r"))\b", re.I)
_COUNTED = r"(?:spots?|spaces?|seats?|places?|people|persons?|guests?|hikers?|folks|attendees|participants|rsvps?|sign-?ups?)"
_LIMIT_AFTER = re.compile(r"\b(\d+)\s+(?:(?:more|open|available|total|extra)\s+)?" + _COUNTED + r"\b", re.I)
_LIMIT_BEFORE = re.compile(r"\b(?:max(?:imum)?|limit(?:ed)?(?:\s+to|\s+of)?|capacity(?:\s+of)?|cap(?:ped)?(?:\s+(?:[a-z']+\s+){0,4}?(?:at|to|of))?|"
                           r"up\s+to|at\s+most|no\s+more\s+than)\s*(?:of\s+|to\s+)?(\d+)\b", re.I)  # "cap Cass Hill at 3" too
_UNIT_AFTER = re.compile(r"^\s*(?:liters?|litres?|l|ml|miles?|mi|km|kms|kilometers?|meters?|m|feet|ft|hours?|hrs?|"
                         r"minutes?|mins?|lbs?|kg|oz|degrees?|dollars?|bucks|layers?|bottles?|snacks?|sandwich\w*)\b", re.I)
_REPLACED = re.compile(r"\b(?:not|instead\s+of|rather\s+than|other\s+than|no\s+longer)\s+(?:the\s+)?\d+\b", re.I)


def _clauses(said):
    return [c for c in _CLAUSE_SPLIT.split(said.replace("\u2019", "'")) if c and c.strip()]


def _signup_state(said):
    """What the owner's LATEST sign-up instruction says: True (on), False (off: "no sign up", "don't let people sign up",
    "without rsvps", a later "actually no sign ups" after "sign up please") or None (not mentioned). "no limit on sign ups" is
    about the guest limit, not sign-up, and stays on."""
    state = None
    for clause in _clauses(said):
        clause = _NO_LIMIT.sub(" ", clause)
        if _SIGNUP_WORDS.search(clause):
            state = not _NEGATED.search(clause)
    return state


def _said_signup(said):
    return _signup_state(said) is True


def _words_to_digits(text):
    def one(m):
        if m.group(1):
            return str(_TENS[m.group(1).lower()] + _UNITS[m.group(2).lower()])
        return str(nl_prep.WORD_NUMBERS[m.group(3).lower()])
    return _NUM_WORD.sub(one, text)


_LIMIT_TAIL = re.compile(r"^\s*(?:(?:more|open|available|total|extra|in\s+total|please|thanks|tops|max)\s*)*(?:$|" + _COUNTED + r"\b)", re.I)


def _said_limits(said):
    """The effective guest limit the owner's words state: a number right next to a counted noun ("12 spots", "twelve
    people") or after a limit word that is itself followed by a guest noun or nothing ("max 12", "up to 20 people"), in
    an affirmative clause. A date, a clock time, a year, a quantity of something else ("only 2 liters of water", "at
    most 2 apples") or a rejected number ("not 12 spots, 20 spots") never counts; the latest instruction wins, so
    "12 spots" then "actually make it 20 spots" leaves only 20, and a later "no limit" leaves none. Two different counts
    in the latest instruction ("15 spots or 20 spots") are both kept: the result has several values, which is unresolved."""
    effective = set()
    for clause in _clauses(said):
        if _NO_LIMIT.search(clause):
            effective = set()
        text = re.sub(r"\b(cap(?:ped)?|limit(?:ed)?)\b(?:\s+[a-z']+){0,4}?\s+(?:at|to)\s+(\d+)\b", r"\1 \2", clause.lower())  # "cap Cass Hill at 3": not a time
        text = _words_to_digits(_DATE_TIME.sub(" ", _NO_LIMIT.sub(" ", text)))
        for m in _REPLACED.finditer(text):
            effective.discard(int(re.search(r"\d+", m.group(0)).group(0)))  # a retracted number is no longer said
        text = _REPLACED.sub(" ", text)
        if _NEGATED.search(re.sub(r"\bno\s+more\s+than\b", "at most", text)):
            continue
        hits = []
        for pat in (_LIMIT_AFTER, _LIMIT_BEFORE):
            for m in pat.finditer(text):
                if pat is _LIMIT_AFTER or _LIMIT_TAIL.match(text[m.end():]):
                    hits.append((m.start(), int(m.group(1))))
        if hits:
            effective = {value for _, value in hits}  # alternatives stay alternatives: no first, last, min or max is picked
    return effective


_NO_LIMIT_NEGATED = re.compile(r"(?:\bnot|\bnever|n't|\bno\s+longer)\s+(?:be\s+|really\s+|actually\s+|going\s+to\s+be\s+)?(?:"
                               + _NO_LIMIT.pattern + r")", re.I)


def _said_unlimited(said):
    """Whether the owner's LATEST word on the guest limit is "no limit": \"no limit\" / \"unlimited\" turns it on, a later
    number tied to guests (\"actually limit to 15 spots\") or a negation (\"not unlimited\", \"no longer unlimited\") turns it
    off again, and an earlier \"no limit\" that was withdrawn never counts."""
    state = False
    for clause in _clauses(said):
        if _NO_LIMIT_NEGATED.search(clause):
            state = False
        elif _NO_LIMIT.search(clause):
            state = True
        elif _said_limits(clause):
            state = False
    return state


def rule_no_invention(slots, texts, ctx):
    """The E2E-HIKE-1 finding: the model added sign-up and a guest limit nobody asked for. A word or a number somewhere in
    the text is not evidence: sign-up on needs his latest sign-up instruction to be on ("sign-up off" never turns it on), a
    guest limit needs a number he tied to guests ("12 spots", not the 12 in "December 12"), "no limit" needs his own words, and
    a limit together with "no limit" is unclear. Unclear evidence asks one plain question. Skipped when the owner's words are
    not known. The same rule guards an add and an edit."""
    said = "\n".join(t for t in (texts or ()) if isinstance(t, str))
    if not said.strip():
        return None
    signup, no_limit = slots.get("signup"), slots.get("no_limit") is True
    cap = slots.get("capacity")
    cap = cap if isinstance(cap, int) and not isinstance(cap, bool) else None
    state, limits = _signup_state(said), _said_limits(said)
    if signup is True:
        if state is False:
            return R_SIGNUP_UNCLEAR, "other"  # he said sign-up off
        if state is None and not limits:
            return R_SIGNUP_NOT_SAID, "other"
    elif state is True or (signup is False and "hike" in slots and state is None and not limits):
        return R_SIGNUP_UNCLEAR, "other"  # he said on and the slots say off (or nothing), or an edit turns sign-up off without a word
    if cap is not None or no_limit:
        if state is False:
            return R_SIGNUP_UNCLEAR, "other"
        if cap is not None and (no_limit or limits != {cap}):  # alternatives ("15 spots or 20 spots") support neither: one unequivocal count only
            return R_SPOTS_NOT_SAID, "other"
        if no_limit and cap is None and not _said_unlimited(said):  # latest word wins: a withdrawn or negated "no limit" is not said
            return R_SPOTS_NOT_SAID, "other"
    return None


CAPACITY_CEILING = 6
PAGE_LIMIT_NOTE = "Page will say: Limited to {n} people · availability unconfirmed; ask at the Shack"  # the limit only: never "N spots left"


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def rule_capacity_ceiling(slots, texts, ctx):
    """The most the skill will set is 6 (after the no-invention rule, which keeps priority). An add writes a limit only with
    sign-up on; an edit writes any limit it is given. Zero, negative and non-number values are the editor's to refuse."""
    cap = _count(slots.get("capacity"))
    if cap is None or cap <= CAPACITY_CEILING:
        return None
    if "hike" not in slots and slots.get("signup") is not True:
        return None  # hike.add discards a limit when sign-up is not on
    return R_CAP_MAX, "other"


def default_capacity(slots, ctx):
    """6 when sign-up is explicitly turned on with no number and no "no limit" (his or the slots'), else None. Called only
    AFTER the rules passed, so a model-written 6 he did not say was already refused. With his words known they must show a
    sign-up instruction and no count or "no limit" the model left out (those stay with the editor's question)."""
    if slots.get("signup") is not True or slots.get("capacity") is not None or slots.get("no_limit") is True:
        return None
    said = "\n".join(t for t in (getattr(ctx, "texts", ()) or ()) if isinstance(t, str))
    if said.strip() and (_signup_state(said) is not True or _said_limits(said) or _said_unlimited(said)):
        return None
    return CAPACITY_CEILING


def _with_default(slots, ctx):
    slots = dict(slots)
    cap = default_capacity(slots, ctx)
    if cap is not None:
        slots["capacity"] = cap
    return slots


RULES = {"no-price": rule_no_price, "hike-in-future": rule_in_future, "hike-twin": rule_twin,
         "hike-repeat-twin": rule_repeat_twin, "hike-scheduled": rule_scheduled, "hike-cancel-state": rule_cancel_state,
         "hike-already-then": rule_already_then, "hike-recap-state": rule_recap_state,
         "hike-no-invention": rule_no_invention, "hike-capacity-ceiling": rule_capacity_ceiling}


def _guard(skill, slots, ctx):
    """The same rules the dispatcher runs, run again inside the plan so a plan can never draft what a rule refuses."""
    texts = getattr(ctx, "texts", ()) or ()
    for rule_id in skill.rules:
        hit = RULES[rule_id](slots, texts, ctx)
        if hit:
            raise Refusal(hit[0])


# -- slot helpers --------------------------------------------------------------------------------------------------
def _need(skill, slots, *names):
    for name in names:
        if slots.get(name) in (None, ""):
            slot = next(s for s in skill.slots if s.name == name)
            raise Refusal(slot.ask)


def place_title(slots, ctx):
    """Default title when the owner named a place and no title: "<place> hike" (the named route idea's title, else the
    meeting point without a trailing trailhead / gate / parking lot). None when there is nothing to build it from."""
    place = None
    if slots.get("trail"):
        place = next((r.get("title") for r in _routes(ctx) if r.get("id") == slots["trail"]), None)
    if not place and _given(slots, "meeting_point"):
        place = _PLACE_HEAD.sub("", slots["meeting_point"].strip())
        place = _PLACE_TAIL.sub("", place).strip()
    title = f"{place} hike" if place else None
    return title if title and len(title) <= 80 else None


DERIVERS = {"place_title": place_title}


def add_set_phrases(slots, ctx) -> list:
    """What hike.add chose for the owner, as the plain phrases of the one ``I set:`` line (D8): ``["sign-up off", "the title
    “Mill Creek hike”"]``. ``slots`` are the slots as the owner gave them, BEFORE any default is applied; a slot he gave is
    never listed. Empty when nothing was chosen for him. (The dispatcher's generic default text would read "signup: False".)"""
    out = _add_defaults(slots, ctx)
    if out and default_capacity(slots, ctx) is not None:
        out.append(f"{CAPACITY_CEILING} spots")  # with no other default the skill's notes carry this line instead
    return out


def _add_defaults(slots, ctx) -> list:
    out = []
    if slots.get("signup") is None:
        out.append("sign-up off")  # plan_add writes rsvpEnabled False when sign-up was not said
    if not _given(slots, "title"):
        title = place_title(slots, ctx)
        if title:
            out.append(f"the title {voice.quote(title)}")
    return out


def set_line(phrases) -> str | None:
    """``I set: sign-up off.`` from the phrases of one or several calls (each said once); None when there are none."""
    unique = list(dict.fromkeys(p for p in phrases if p))
    return "I set: " + "; ".join(unique) + "." if unique else None


SET_PHRASES = {"hike.add": add_set_phrases}  # skill name -> fn(slots as the owner gave them, ctx) -> phrases; consumed by the kit and the dispatcher


PAGE_ONLY_NOTE = "Cancelling changes the hike page. Nobody is notified."  # RF2315-12: said before yes, whatever the sign-up state or guest count


def notes(name, slots, ctx) -> dict:
    """Lines shown beside a hike draft: for hike.cancel, that it changes the page and tells nobody; for hike.add / hike.edit,
    ``I set: 6 spots.`` when the code supplied the six (only when no other default already carries it in SET_PHRASES), and the
    capacity-only page note for the hike's own limit."""
    out = {"say": [], "set": [], "warn": []}
    if name == "hike.cancel":
        out["say"].append(PAGE_ONLY_NOTE)  # fixed text: reads no guest data, files or settings
        return out
    if name not in ("hike.add", "hike.edit"):
        return out
    given = dict(slots)
    derived = default_capacity(given, ctx)
    limit = derived if derived is not None else _count(given.get("capacity"))
    if name == "hike.add":
        on = given.get("signup") is True
        if derived is not None and not _add_defaults(given, ctx):
            out["set"].append(set_line([f"{CAPACITY_CEILING} spots"]))
    else:
        event = _event(ctx, given.get("hike")) or {}
        on = given["signup"] if isinstance(given.get("signup"), bool) else event.get("rsvpEnabled") is True
        if derived is not None:
            out["set"].append(set_line([f"{CAPACITY_CEILING} spots"]))
        if limit is None:
            limit = _count(event.get("capacity"))
    if given.get("no_limit") is True:
        limit = None
    if on and limit is not None and limit > 0:
        out["say"].append(PAGE_LIMIT_NOTE.format(n=limit))
    return out


def _signup_args(slots):
    """rsvpEnabled and its guest limit, from the owner's words only: a limit is written only with sign-up on."""
    on = slots.get("signup") is True
    args: dict = {"rsvpEnabled": on}
    if on:
        cap = slots.get("capacity")
        if isinstance(cap, int) and not isinstance(cap, bool):
            args["capacity"] = cap
        if slots.get("no_limit") is True:
            args["noCapacityLimit"] = True
    return args  # sign-up on with neither: the editor asks "how many can come, or no limit?"


# -- plans ---------------------------------------------------------------------------------------------------------
def plan_add(slots, ctx):
    slots = dict(slots)
    if not _given(slots, "title"):
        slots["title"] = place_title(slots, ctx)
    _need(ADD, slots, "title", "day", "clock", "meeting_point")
    _guard(ADD, slots, ctx)
    slots = _with_default(slots, ctx)
    args = {"title": _text(slots["title"]), "date": slots["day"], "time": slots["clock"],
            "meetingPoint": _text(slots["meeting_point"]), **_signup_args(slots)}
    if _given(slots, "trail"):
        args["trailId"] = slots["trail"]
    args.update({ARG.get(f, f): _text(slots[f]) for f in TEXT_SLOTS if _given(slots, f)})
    return [{"op": "hike.create", "args": args}]


def plan_edit(slots, ctx):
    _need(EDIT, slots, "hike")
    _guard(EDIT, slots, ctx)
    slots = _with_default(slots, ctx)
    args = {"id": slots["hike"]}
    args.update({ARG.get(f, f): _text(slots[f]) for f in EDIT_TEXT_SLOTS if _given(slots, f)})
    if isinstance(slots.get("signup"), bool):
        args["rsvpEnabled"] = slots["signup"]
    if isinstance(slots.get("capacity"), int) and not isinstance(slots.get("capacity"), bool):
        args["capacity"] = slots["capacity"]
    if slots.get("no_limit") is True:
        args["noCapacityLimit"] = True
    return [{"op": "hike.update", "args": args}]  # no change given: the editor asks what to change


def plan_reschedule(slots, ctx):
    _need(RESCHEDULE, slots, "hike")
    if not (slots.get("day") or slots.get("clock")):
        raise Refusal(R_WHAT_MOVE)
    _guard(RESCHEDULE, slots, ctx)
    args = {"id": slots["hike"]}
    if slots.get("day"):
        args["date"] = slots["day"]
    if slots.get("clock"):
        args["time"] = slots["clock"]
    return [{"op": "hike.update", "args": args}]


def plan_cancel(slots, ctx):
    _need(CANCEL, slots, "hike")
    _guard(CANCEL, slots, ctx)
    args = {"id": slots["hike"]}
    note = " ".join(slots["note"].split()) if isinstance(slots.get("note"), str) else ""
    if note:  # one plain line, as the owner gave it
        args["note"] = note
    return [{"op": "hike.cancel", "args": args}]


def plan_repeat(slots, ctx):
    _need(REPEAT, slots, "hike", "day", "clock")
    _guard(REPEAT, slots, ctx)
    return [{"op": "hike.repeat", "args": {"id": slots["hike"], "date": slots["day"], "time": slots["clock"]}}]


def plan_recap(slots, ctx):
    _need(RECAP, slots, "hike", "recap")
    _guard(RECAP, slots, ctx)
    event = _event(ctx, slots["hike"])
    op = "hike.recap" if event is not None and event.get("status") == "completed" else "hike.complete"
    return [{"op": op, "args": {"id": slots["hike"], "recap": _text(slots["recap"])}}]


# -- the skills ----------------------------------------------------------------------------------------------------
_CASES = "hass/tests/fixtures/skills/hikes/{}.jsonl"
_COMMUNITY = "hass/content/community.json"
_SITE = (("storefront-mockup/community.json", "events[id]"),)  # the hike page reads this file: it is the only generated file that changes
_HIKE = Slot("hike", "hike_ref", True, ask="Which hike do you mean?")
_TITLE_LIMIT = ("event", "title")


def _text_slot(name, required=False, **kw):
    return Slot(name, "text", required, owner_words=True, limit=("event", ARG.get(name, name)), **kw)


ADD = Skill(
    name="hike.add", label="add a hike",
    summary="Put a new hike on the hike page: day, time and where to meet. Sign-up stays off unless you say so.",
    triggers=(
        Trigger("add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water"),
        Trigger("create a new hike on Fiscalini Ranch this Saturday at 8am, easy, bring water"),
        Trigger("add a hike Saturday", "vague"),
        Trigger("pos a hike at casss hill sat 9am meet at the gate", "typo"),
        Trigger("put a hike on the site for sometime next weekend, somewhere at the beach", "vague"),
        Trigger("Montaña de Oro Sunrise Walk, Saturday Dec 5 at 8, meet at Spooners Cove parking lot, easy, gentle sunrise stroll"),
        Trigger("hike Dec 12 10am Cayucos Pier, sign up with 12 spots"),
        Trigger("two hikes: Cass Hill Nov 21 at 9 and Point Buchon Nov 28 at 8, both meet at the trailhead", "multi"),
        Trigger("hike last Saturday at 9, Cass Hill"),
        Trigger("add a hike on Fiscalini this Saturday, moderate, 5 miles, no dogs allowed"),
    ),
    slots=(Slot("title", "text", True, default="derive:place_title", ask="What should the hike be called?", limit=_TITLE_LIMIT),
           Slot("day", "day", True, ask="What day and time?"),
           Slot("clock", "clock", True, ask="What time does it start?"),
           _text_slot("meeting_point", True, ask="Where do people meet?"),
           Slot("signup", "bool", False, default=False),
           Slot("capacity", "int"), Slot("no_limit", "bool"), Slot("trail", "route_ref"),
           *(_text_slot(f) for f in TEXT_SLOTS)),
    rules=("hike-in-future", "hike-twin", "hike-no-invention", "hike-capacity-ceiling", "no-price"),
    plan=plan_add,
    edits=((_COMMUNITY, "events[id]"), *_SITE),
    side_effects=("none",), preview="hike", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "The hike stays on the page as cancelled: an event cannot be deleted."),
    refuse=(("the day has passed", R_PAST_DAY), ("a scheduled hike has the same day and title", "There is already a hike with that name that day."),
            ("a price is in the text", R_PRICE)),
    cases=_CASES.format("hike.add"), version=1)

EDIT = Skill(
    name="hike.edit", label="change a hike",
    summary="Change a scheduled hike: its name, where to meet, how hard, what to bring, or sign-up.",
    triggers=(
        Trigger("change the Cass Hill meeting point to the upper lot"),
        Trigger("add bing sunscreen to the cass hill hike", "typo"),
        Trigger("make the Point Buchon hike moderate"),
        Trigger("turn on sign-up for Cass Hill, 15 spots"),
        Trigger("update the hike", "vague"),
        Trigger("Cass Hill meet at the gate and bring lunch", "multi"),
        Trigger("rename Cass Hill to Cass Hill Morning Walk"),
        Trigger("cap Cass Hill at 3"),
        Trigger("put the hike difficulty back to easy"),
        Trigger("change the sample hike"),
    ),
    slots=(_HIKE, Slot("title", "text", limit=_TITLE_LIMIT), _text_slot("meeting_point"), *(_text_slot(f) for f in TEXT_SLOTS),
           Slot("signup", "bool"), Slot("capacity", "int"), Slot("no_limit", "bool")),
    rules=("hike-scheduled", "hike-no-invention", "hike-capacity-ceiling", "no-price"),
    plan=plan_edit,
    edits=tuple((_COMMUNITY, f"events[id].{ARG.get(f, f)}") for f in (*EDIT_TEXT_SLOTS, "rsvpEnabled", "capacity")) + _SITE,
    side_effects=("none",), preview="hike", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "none"),
    refuse=(("the hike is cancelled or done", "That hike is cancelled, so I can't change it."), ("a price is in the text", R_PRICE)),
    cases=_CASES.format("hike.edit"), version=1)

RESCHEDULE = Skill(
    name="hike.reschedule", label="move a hike to another day or time",
    summary="Move a scheduled hike to a new day or time. Guests who signed up are not told.",
    triggers=(
        Trigger("can we push the Morro Rock Beach Stroll back to 10am, the tide is lower later"),
        Trigger("move Saturday's hike to 8:30"),
        Trigger("resedule cass hill to the 29th", "typo"),
        Trigger("move the hike", "vague"),
        Trigger("Cass Hill is Sunday instead"),
        Trigger("move Cass Hill to 9 and Point Buchon to the 5th", "multi"),
        Trigger("push the Point Buchon hike a week later"),
        Trigger("move it to yesterday"),
        Trigger("same day, one hour earlier"),
        Trigger("reschedule the Fiscalini hike"),
    ),
    slots=(_HIKE, Slot("day", "day", "unless:clock", ask=R_WHAT_MOVE), Slot("clock", "clock", "unless:day", ask=R_WHAT_MOVE)),
    rules=("hike-scheduled", "hike-in-future", "hike-already-then"),
    plan=plan_reschedule,
    edits=((_COMMUNITY, "events[id].startsAt"), *_SITE),
    side_effects=("none",), preview="hike", approval="owner-yes", live_class="chat-live",
    undo=Undo("revert", "Guests were not told, before or after the move."),
    refuse=(("the new time has passed", R_PAST_DAY), ("the hike is cancelled or done", "That hike is cancelled, so I can't change it.")),
    cases=_CASES.format("hike.reschedule"), version=1)

CANCEL = Skill(
    name="hike.cancel", label="cancel a hike",
    summary="Cancel a scheduled hike, with an optional one-line note on the page. Nobody is told.",
    triggers=(
        Trigger("cancel the Point Buchon hike, rained out - we will pick a new date soon"),
        Trigger("cancel Saturday's hike"),
        Trigger("cancle the cass hill walk its raning", "typo"),
        Trigger("scrap it", "vague"),
        Trigger("cancel both hikes this weekend", "multi"),
        Trigger("call off the Morro Rock stroll, no note"),
        Trigger("we can't do the Cass Hill hike after all"),
        Trigger("cancel the hike and tell everyone who signed up"),
        Trigger("cancel the Cass Hill hike"),
        Trigger("cancel the sample hike"),
    ),
    slots=(_HIKE, Slot("note", "text", owner_words=True, limit=("event", "cancelNote"))),
    rules=("hike-cancel-state", "no-price"),
    plan=plan_cancel,
    edits=((_COMMUNITY, "events[id].status"), (_COMMUNITY, "events[id].cancelNote"), *_SITE),
    side_effects=("none",), preview="hike", approval="owner-yes", live_class="chat-live",
    undo=Undo("revert", "Guests were not told of the cancel, before or after."),
    refuse=(("the hike is already cancelled", "That hike is already cancelled."),),
    cases=_CASES.format("hike.cancel"), version=1)

REPEAT = Skill(
    name="hike.repeat", label="run a hike again",
    summary="Copy a hike onto a new day and time: its name, text, route and sign-up setting.",
    triggers=(
        Trigger("do the Cass Hill hike again on the 29th at 9"),
        Trigger("repeet cass hill next saterday 9am", "typo"),
        Trigger("same hike, December 5, 8am"),
        Trigger("run it again", "vague"),
        Trigger("repeat Cass Hill on the 29th and the 6th, both at 9", "multi"),
        Trigger("again next week, same time"),
        Trigger("run the Morro Rock stroll again in the spring"),
        Trigger("repeat the Fiscalini idea"),
        Trigger("again yesterday"),
        Trigger("copy Point Buchon to Dec 12 at 8"),
    ),
    slots=(_HIKE, Slot("day", "day", True, ask="What day should it be on?"), Slot("clock", "clock", True, ask="What time does it start?")),
    rules=("hike-in-future", "hike-repeat-twin"),
    plan=plan_repeat,
    edits=((_COMMUNITY, "events[id]"), *_SITE),
    side_effects=("none",), preview="hike", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "The new hike stays on the page as cancelled: an event cannot be deleted."),
    refuse=(("the new day has passed", R_PAST_DAY), ("a scheduled hike has the same day and title", "There is already a hike with that name that day.")),
    cases=_CASES.format("hike.repeat"), version=1)

RECAP = Skill(
    name="hike.recap", label="write down how a hike went",
    summary="Mark a hike that has happened as done and keep your words on how it went.",
    triggers=(
        Trigger("recap: 12 people, great morning"),
        Trigger("the Cass Hill hike went well, 9 people, saw whales"),
        Trigger("pont buchon wa amazign, 14 of us", "typo"),
        Trigger("it went fine", "vague"),
        Trigger("Cass Hill and Point Buchon both done, 9 and 14 people", "multi"),
        Trigger("fix the recap on Cass Hill: 10 people not 9"),
        Trigger("the Morro Rock stroll was great, no rain"),
        Trigger("recap the Dec 19 hike"),
        Trigger("recap for a hike called Dune Walk"),
        Trigger("mark Cass Hill as done"),
    ),
    slots=(_HIKE, _text_slot("recap", True, ask="How did it go?")),
    rules=("hike-recap-state", "no-price"),
    plan=plan_recap,
    edits=((_COMMUNITY, "events[id].status"), (_COMMUNITY, "events[id].recap"), *_SITE),
    side_effects=("none",), preview="hike", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "A hike that has already started stays done: undo refuses to reopen it, and a new recap corrects the words."),
    refuse=(("the hike has not happened yet", "That hike hasn't happened yet, so there is nothing to recap."),
            ("the hike was cancelled", "That hike was cancelled, so there is no recap to write.")),
    cases=_CASES.format("hike.recap"), version=1)

SKILLS = (ADD, EDIT, RESCHEDULE, CANCEL, REPEAT, RECAP)


# -- the post-hike announcement draft (text only: nothing is posted, scheduled or saved) ------------------------------
def recap_announcement(content, event_id) -> dict:
    """{"draft": True, "caption"} for a hike that is done and has a recap, else {"draft": False, "reason": plain words}.

    The caption is the title, the Pacific day and the owner's recap exactly as he wrote it (cut at a sentence end only if
    the post would be too long), then the fixed hike tags. Nothing is added: no people count, no thanks, no account, no
    link. Interface assumption: SKILLS-SOCIAL-1 owns ``social.recap`` and ``social_draft.build_recap`` and may delegate
    to this function or replace it; this card does not edit ``social_draft.py``."""
    def no(reason):
        return {"draft": False, "reason": reason}

    community = getattr(content, "community", None)
    events = community.get("events") if isinstance(community, dict) else None
    if not isinstance(events, list):
        return no("I can't read the hikes right now.")
    event = next((e for e in events if isinstance(e, dict) and e.get("id") == event_id), None)
    if event is None:
        return no("I don't know that hike.")
    if event.get("status") == "cancelled":
        return no("That hike was cancelled, so there is nothing to post about.")
    if event.get("status") != "completed":
        return no("That hike hasn't happened yet.")
    recap, title = event.get("recap"), event.get("title")
    day = _local(event.get("startsAt"))[0]
    if not (isinstance(recap, str) and recap.strip()):
        return no(R_NO_RECAP_YET)
    if day is None or not (isinstance(title, str) and title.strip() and "\n" not in title):
        return no("I can't read that hike's details right now.")
    if any(_TAG_RE.search(t) for t in (title, recap)):
        return no("That text has a # or an @ in it, and I don't put those in a post.")
    head = f"{title.strip()}\n{_day_words(day)}\n"
    tail = f"\n\n{HIKE_TAGS}"
    body = recap.strip()
    room = MAX_CAPTION - len(head) - len(tail)
    if len(body) > room:  # cut at the last sentence end that fits, never mid-sentence
        ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", body[:room])]
        body = body[:ends[-1]].strip() if ends else ""
        if not body:
            return no("The recap is too long for one post. Could you shorten it?")
    return {"draft": True, "caption": head + body + tail}


def _register():
    """Hand the rules and the derived default to the dispatcher when it is present (SKILLS-FW-3); otherwise nothing."""
    try:
        from hass.skills import dispatch
    except ImportError:
        return False
    for rule_id, fn in RULES.items():
        dispatch.RULES.setdefault(rule_id, fn)
    for name, fn in DERIVERS.items():
        dispatch.DERIVERS.setdefault(name, fn)
    phrases = getattr(dispatch, "SET_PHRASES", None)  # the D8 wording hook: only when the dispatcher has one (PR 526 has not yet)
    if isinstance(phrases, dict):
        for name, fn in SET_PHRASES.items():
            phrases.setdefault(name, fn)
    return True


_register()


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hikes.py", description="Print the local DRAFT post for a hike that is done (posts nothing).")
    parser.add_argument("announce", choices=["announce"])
    parser.add_argument("hike_id")
    args = parser.parse_args(argv)
    from hass.content_model import ContentError, load_content
    try:
        out = recap_announcement(load_content(), args.hike_id)
    except (ContentError, OSError):
        out = {"draft": False, "reason": "I can't read the hikes right now."}
    print(out["caption"] if out["draft"] else out["reason"])
    return 0 if out["draft"] else 1


if __name__ == "__main__":
    sys.exit(_main())
