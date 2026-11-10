"""Shop skills (SKILLS-SHOP-1): store hours, the home-page notice, phone and street address.

    shop.hours    change the opening hours (the whole list; days he did not name stay exactly as they are)
    shop.notice   put up, replace or take down the one dated notice at the top of the home page
    shop.contact  the store phone and the street address / town (private-only: a live release needs Graham)

Each skill is data plus a pure ``plan(slots, ctx)``. The plan returns only the typed ops that already exist
(``store.set_hours``, ``store.set_notice`` ...); it never writes, never reads a file, never uses the network. A plan that
cannot draft raises ``SkillStop``: its ``reply`` is the owner's words (plain, one next step), ``kind`` says whether the
open request should stay (``question``) or the request ends (``refused``), ``reason`` is the backlog reason.

What the plan reads: ``ctx.content.store`` (or ``ctx.store``), ``ctx.today`` and ``ctx.texts`` (the owner's texts of this
request). Every one is optional: a plan called with ``ctx=None`` (the lint's golden call) or without texts keeps its
structural checks and skips only the checks that need the owner's own words (``hours-untouched-lines``). Spec:
reports/hass/SKILLS-SPEC.md 3.20 to 3.22. Owner guide: docs/hass/skills/shop.md.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

from hass.content_model import (MAX_ADDRESS_PART, MAX_HOURS_LINE, MAX_HOURS_LINES, MAX_NOTICE, MAX_NOTICE_DAYS, PHONE_DIGITS,
                                PHONE_RE, shop_today)
from hass.interpret_check import PRICE_REPLY
from hass.ops.store import _line_key, _spaced
from hass.skills.model import Skill, Slot, Trigger, Undo

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ADDRESS_KEYS = {"street_address": "streetAddress", "town": "town"}  # slot name -> the store field
EXAMPLE_PHONE = "805 555 0100"  # the 555-01xx range is reserved for make-believe numbers


class SkillStop(ValueError):
    """A plan that cannot draft. ``reply`` is for the owner; ``kind`` is "question" (the request stays open and the next
    message answers it) or "refused" (the request ends, nothing changes); ``reason`` is the backlog reason."""

    def __init__(self, reply, kind="refused", reason="policy"):
        super().__init__(reply)
        self.reply, self.kind, self.reason = reply, kind, reason


# -- what the plan may read ---------------------------------------------------------------------------------------
def store_of(ctx):
    """The saved store record (a dict) from ``ctx.content.store`` or ``ctx.store``; None when the plan was given no content."""
    if ctx is None:
        return None
    content = ctx.get("content") if isinstance(ctx, dict) else getattr(ctx, "content", None)
    for holder in (content, ctx):
        store = holder.get("store") if isinstance(holder, dict) else getattr(holder, "store", None)
        if isinstance(store, dict):
            return store
    return None


def texts_of(ctx) -> list:
    texts = ctx.get("texts") if isinstance(ctx, dict) else getattr(ctx, "texts", None)
    return [t for t in (texts or []) if isinstance(t, str)]


def today_of(ctx) -> date:
    """Today in the shop's calendar. ``ctx.today`` may be a date or an ISO string; else ``ctx.now``; else the clock."""
    value = (ctx.get("today") if isinstance(ctx, dict) else getattr(ctx, "today", None)) if ctx is not None else None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    now = getattr(ctx, "now", None) if ctx is not None else None
    return shop_today(now if isinstance(now, datetime) else None)


def say_day(day: date) -> str:
    return f"{MONTHS[day.month - 1]} {day.day}"


def letters(text) -> int:
    return sum(c.isalpha() for c in text)


# -- price and deal words (a notice or a line of text is never a price list) ---------------------------------------
DEAL_RE = re.compile(r"\d\s*%|\bpercent\b|\bsale\b|\bdiscounts?\b|\bhalf[- ]price\b|\bbogo\b|\bdeals?\b|\bcoupons?\b|"
                     r"\bper (?:lb|pound|dozen|ounce|oz|kg|each)\b|\bprices?\b|\bcents?\b|\bdollars?\b|\d\s*¢", re.I)
DEAL_REPLY = "A price or a deal can't go in there, so nothing changed. Could you send it without the price?"


def price_problem(text):
    """The owner's reply when ``text`` carries a price or a deal, else None."""
    if "$" in text:
        return PRICE_REPLY
    return DEAL_REPLY if DEAL_RE.search(text) else None


# -- days of the week ---------------------------------------------------------------------------------------------
_DAY_WORD = {}
for _i, _names in enumerate((("mon", "monday"), ("tue", "tues", "tuesday"), ("wed", "weds", "wednesday"),
                             ("thu", "thur", "thurs", "thursday"), ("fri", "friday"), ("sat", "saturday"),
                             ("sun", "sunday"))):
    for _n in _names:
        _DAY_WORD[_n] = _i
ALL_DAYS = frozenset(range(7))
GROUPS = {"weekdays": frozenset(range(5)), "weekday": frozenset(range(5)), "weekends": frozenset({5, 6}),
          "weekend": frozenset({5, 6}), "daily": ALL_DAYS, "everyday": ALL_DAYS}
RANGE_WORDS = {"to", "through", "thru", "till", "until", "-", "–", "—"}
JOINERS = RANGE_WORDS | {",", "&", "and"}
TOKEN = re.compile(r"[A-Za-z]+|\d+|[–—-]|,|&|\S")
EVERY_DAY = re.compile(r"\b(?:every ?day|each day|all week|seven days(?: a week)?|7 days(?: a week)?)\b", re.I)


def _day(word):
    word = word.lower()
    if word in _DAY_WORD:
        return _DAY_WORD[word]
    return _DAY_WORD.get(word[:-1]) if word.endswith("s") else None  # "fridays"


def _span(a, b):
    return frozenset(range(a, b + 1)) if a <= b else frozenset(list(range(a, 7)) + list(range(0, b + 1)))


def _days_of(words) -> frozenset:
    """The days a run of lower-case words names: single days, ranges ("mon to fri"), weekdays / weekends / daily."""
    out, i = set(), 0
    while i < len(words):
        d = _day(words[i])
        if d is not None:
            if i + 2 < len(words) and words[i + 1] in RANGE_WORDS and _day(words[i + 2]) is not None:
                out |= _span(d, _day(words[i + 2]))
                i += 3
                continue
            out.add(d)
        elif words[i] in GROUPS:
            out |= GROUPS[words[i]]
        i += 1
    return frozenset(out)


def days_in_text(text) -> frozenset:
    """Every day of the week the owner's words name ("fridays", "mon to sat", "weekdays", "every day")."""
    text = EVERY_DAY.sub(" daily ", unicodedata.normalize("NFKC", str(text)))
    return _days_of([m.group(0).lower() for m in TOKEN.finditer(text)])


def parse_segment(segment):
    """(days, what is said about them) for "Monday–Friday 9am–6pm", "Closed Sunday" or "Daily 10–4"; None when the segment
    does not start with (or is not just) days and a statement, so it is kept as one opaque piece."""
    toks = [(m.group(0), m.start(), m.end()) for m in TOKEN.finditer(EVERY_DAY.sub(lambda m: "daily".ljust(len(m.group(0))), segment))]
    i = 1 if toks and toks[0][0].lower() == "closed" else 0
    j, last = i, None
    while j < len(toks):
        w = toks[j][0].lower()
        if _day(w) is not None or w in GROUPS:
            last = j
        elif w not in JOINERS:
            break
        j += 1
    if last is None or (i == 0 and _day(toks[0][0]) is None and toks[0][0].lower() not in GROUPS):
        return None
    days = _days_of([t[0].lower() for t in toks[i:last + 1]])
    rest = segment[toks[last][2]:].strip(" ,:–—-")
    if i == 1:
        rest = ("closed " + rest).strip()
    elif not rest:
        return None
    return days, rest


def schedule_pieces(line):
    """Split separators and independent comma or "and" schedules, not those joining days or ordinary prose."""
    out = []
    for piece in re.split(r"\s*[·;]\s*", line):
        piece = piece.strip()
        for cut in re.finditer(r",|\band\b", piece, re.I):
            left, right = piece[:cut.start()].strip(), piece[cut.end():].strip()
            # "Closed Mon and Fri, Fri 9–5": when the left is only a closed-day list and the right's first comma part is
            # only days, that part continues the closed list, so the "and" is not the boundary; the comma after it is.
            # An open-hours left ("Mon 9–5 and Fri, Sat 10–4") is an independent schedule, so the "and" still splits.
            if (cut.group(0) != "," and "," in right and parse_segment(right.split(",", 1)[0]) is None
                    and (parse_segment(left) or (None, None))[1] == "closed"):
                continue
            if parse_segment(left) is not None and parse_segment(right) is not None:
                out.append(left)
                out.extend(schedule_pieces(right))
                break
        else:
            if piece:
                out.append(piece)
    return out


def segments_of(lines):
    """[(line index, text, parsed or None)] for every schedule piece, without rewriting the stored lines."""
    return [(n, piece, parse_segment(piece)) for n, line in enumerate(lines) for piece in schedule_pieces(line)]


def hours_by_day(lines):
    """({day: [what is said, ...]}, [opaque pieces]) for an hours list."""
    by_day, opaque = {}, []
    for _n, piece, parsed in segments_of(lines):
        if parsed is None:
            opaque.append(piece)
            continue
        days, rest = parsed
        for d in days:
            by_day.setdefault(d, []).append(rest)
    return by_day, opaque


def day_names(days) -> str:
    days = sorted(days)
    if len(days) == 1:
        return DAY_NAMES[days[0]]
    if len(days) >= 3 and days == list(range(days[0], days[-1] + 1)):
        return f"{DAY_NAMES[days[0]]} to {DAY_NAMES[days[-1]]}"
    names = [DAY_NAMES[d] for d in days]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _same(a, b) -> bool:
    return [_line_key(x) for x in a] == [_line_key(x) for x in b]


def _stay_phrase(what):
    return "closed" if _line_key(what) == "closed" else what


# -- shop.hours ---------------------------------------------------------------------------------------------------
HOURS_ASK = "Which days, and what hours?"
NO_EMPTY_HOURS = "I can't take the hours off the site. What should they say?"
HOURS_TOO_MANY = f"I can show {MAX_HOURS_LINES} lines of hours at most. Could you put some days together?"
HOURS_TWICE = "Two of those lines say the same thing. Could you send the hours again with each day once?"
HOLIDAY_REPLY = ("A closed day on a date is a notice, not the usual hours. What should the notice say, "
                 "and what is the last day it should stay up?")
HOLIDAY_RE = re.compile(r"\b(?:thanksgiving|christmas|xmas|new years?|easter|memorial day|labor day|independence day|"
                        r"july (?:4|4th|fourth)|fourth of july|veterans day|holiday|holidays)\b", re.I)
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|"
          r"nov(?:ember)?|dec(?:ember)?)")
# a day on the calendar: "November 12", "Nov. 12th", "12 November", "11/12", "the 12th" (never a weekday: "closed Sundays" is the hours)
DATE_RE = re.compile(rf"\b{_MONTH}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}\b|"
                     r"(?<![\d:/])\d{1,2}/\d{1,2}(?:/\d{2,4})?(?![\d:/])|\bthe\s+\d{1,2}(?:st|nd|rd|th)\b|"
                     r"(?<![\d-])\d{4}-\d{1,2}-\d{1,2}(?![\d-])", re.I)
RELATIVE_DAY_RE = re.compile(r"\b(?:today|tonight|tomorrow|this (?:week|weekend|coming)|next (?:week|weekend))\b", re.I)
_WEEKDAY = r"(?:mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
# one day only, with no date: "closed this Thursday", "closed next Friday", "closed Thursday only", "just this once"
ONE_OFF_RE = re.compile(rf"\b(?:this|next|coming)\s+{_WEEKDAY}\b|\b{_WEEKDAY}(?:\s+\S+){{0,2}}\s+only\b|"
                        r"\b(?:one[- ]?off|one[- ]?time|just once|this once|for one day|just for the day)\b", re.I)
EVERY_RE = re.compile(r"\b(?:every|each|always|weekly|permanent(?:ly)?|from now on|all year|going forward|"
                      rf"{_WEEKDAY}s)\b", re.I)
CLOSED_RE = re.compile(r"\b(?:closed?|closing|closures?|shut|off|not open)\b", re.I)
# the parts of one clause: a weekly word only counts for the one-off day in its own part ("closed this Thursday only, open
# every Friday" stays a one-off Thursday)
_PART_RE = re.compile(r"[,&]|\b(?:and|but|then|while|plus|though|although|whereas)\b", re.I)


def _line_problem(i, line):
    if len(line) > MAX_HOURS_LINE:
        return f"Line {i} of the hours is too long. Could you keep each line under {MAX_HOURS_LINE} characters?"
    if not any(c.isalnum() for c in line):
        return f"Line {i} of the hours has no day or time in it. What should it say?"
    return None


def check_hours_conflict(slots, texts, ctx):
    """hours-no-conflict: one day with two different statements in the new list is a question, never a guess."""
    by_day, _opaque = hours_by_day(slots["hours"])
    for d in sorted(by_day):
        if len({_line_key(r) for r in by_day[d]}) > 1:
            return SkillStop(f"I see two different hours for {DAY_NAMES[d]}. Which one do you want?", "question")
    return None


def check_hours_untouched(slots, texts, ctx):
    """hours-untouched-lines: a day the owner did not name keeps exactly what the site says now, or he is asked."""
    store = store_of(ctx)
    if store is None or not texts or not isinstance(store.get("hours"), list):
        return None  # without the saved hours or his words this rule cannot judge; the structural checks still ran
    named = days_in_text(" ".join(texts))
    old, new = hours_by_day(store["hours"]), hours_by_day(slots["hours"])
    kept = {_line_key(piece) for line in slots["hours"] for piece in schedule_pieces(line) if piece.strip()}
    for opaque in old[1]:  # a piece of the current hours that names no day: it stays unless he rewrote the whole list around it
        if _line_key(opaque) not in kept:
            return SkillStop(f"Do you want to keep “{opaque}” in the hours?", "question")
    lost = [d for d in range(7) if d not in named and d in old[0] and not _same(old[0][d], new[0].get(d, []))]
    if lost:
        first = lost[0]
        same = [d for d in lost if _same(old[0][d], old[0][first])]
        return SkillStop(f"Do you want {day_names(same)} to stay {_stay_phrase(old[0][first][0])}?", "question")
    return None


def check_hours_already(slots, texts, ctx):
    """not-already-true: the same lines as now (spacing aside) draft nothing."""
    store = store_of(ctx)
    if store is None or not isinstance(store.get("hours"), list):
        return None
    if [_spaced(h) for h in slots["hours"]] != [_spaced(h) for h in store["hours"]]:
        return None
    named = days_in_text(" ".join(texts))
    by_day, _o = hours_by_day(store["hours"])
    say = [f"{DAY_NAMES[d]} {by_day[d][0]}" if _line_key(by_day[d][0]) != "closed" else f"{DAY_NAMES[d]} closed"
           for d in sorted(named) if d in by_day]
    shown = "; ".join(say) if say and len(say) <= 3 else "; ".join(store["hours"])
    return SkillStop(f"It already says that: {shown}. Did you mean something else?", "question")


def check_hours_price(slots, texts, ctx):
    """no-price: a price or a deal in an hours line."""
    for line in slots["hours"]:
        if (problem := price_problem(line)):
            return SkillStop(problem, "refused", "price")
    return None


def check_hours_holiday(slots, texts, ctx):
    """holiday-is-notice: a closed day on a date or holiday is a notice, not the weekly hours."""
    store = store_of(ctx)
    old = (store or {}).get("hours") or []
    old_pieces = {_line_key(p) for line in old for p in schedule_pieces(line)}
    for line in slots["hours"]:  # a date in an hours line is never weekly hours (a piece the site already has is left alone)
        for piece in schedule_pieces(line):
            if piece.strip() and _line_key(piece) not in old_pieces and DATE_RE.search(piece):
                return SkillStop(HOLIDAY_REPLY, "question")
    if store is None or _same(slots["hours"], old):
        return None
    said = " ".join(texts)
    if HOLIDAY_RE.search(said):
        return SkillStop(HOLIDAY_REPLY, "question")
    for clause in re.split(r"[.!?;\n]", said):
        if CLOSED_RE.search(clause) and (DATE_RE.search(clause) or RELATIVE_DAY_RE.search(clause)):
            return SkillStop(HOLIDAY_REPLY, "question")
        one_off = [p for p in _PART_RE.split(clause) if ONE_OFF_RE.search(p)] or ([clause] if ONE_OFF_RE.search(clause) else [])
        if CLOSED_RE.search(clause) and any(not EVERY_RE.search(p) for p in one_off):
            return SkillStop(HOLIDAY_REPLY, "question")
    return None


HOURS_CHECKS = {"no-price": check_hours_price, "hours-no-conflict": check_hours_conflict, "not-already-true": check_hours_already,
                "holiday-is-notice": check_hours_holiday, "hours-untouched-lines": check_hours_untouched}


def plan_hours(slots, ctx):
    hours = slots.get("hours")
    if isinstance(hours, str):
        hours = [hours]
    hours = [" ".join(h.split()) for h in hours if isinstance(h, str)] if isinstance(hours, (list, tuple)) else []
    hours = [h for h in hours if h]
    if not hours:
        raise SkillStop(NO_EMPTY_HOURS if isinstance(slots.get("hours"), (list, tuple)) else HOURS_ASK, "question")
    if len(hours) > MAX_HOURS_LINES:
        raise SkillStop(HOURS_TOO_MANY)
    for i, line in enumerate(hours, 1):
        if (problem := _line_problem(i, line)):
            raise SkillStop(problem, "question")
    if len({_line_key(h) for h in hours}) != len(hours):
        raise SkillStop(HOURS_TWICE, "question")
    clean, texts = {"hours": hours}, texts_of(ctx)
    for rule in ("no-price", "hours-no-conflict", "not-already-true", "holiday-is-notice", "hours-untouched-lines"):
        if (stop := HOURS_CHECKS[rule](clean, texts, ctx)):
            raise stop
    return [{"op": "store.set_hours", "args": {"hours": hours}}]


# -- shop.notice --------------------------------------------------------------------------------------------------
NOTICE_ASK, UNTIL_ASK = "What should the notice say?", "Until what day?"
NOTICE_PAST = "That day has already passed. What is the last day for the notice?"
NOTICE_LONG = f"A notice can stay up for {MAX_NOTICE_DAYS} days at the most. Could you pick an earlier last day?"
NOTICE_TEXT_LONG = f"That notice is too long. Could you shorten it to {MAX_NOTICE} characters or fewer?"
NOTICE_SHORT = "That notice is too short to mean anything. What should it say?"
NO_NOTICE = "There is no notice up right now, so there is nothing to take down."


def _iso(value):
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def check_notice_price(slots, texts, ctx):
    """no-price: a price or a deal in a notice is refused and written down."""
    problem = price_problem(slots["text"])
    return SkillStop(problem, "refused", "price") if problem else None


def check_notice_dates(slots, texts, ctx):
    """notice-dates: the last day is today or at most MAX_NOTICE_DAYS days ahead (Pacific)."""
    today, until = today_of(ctx), _iso(slots["until"])
    if until is None:
        return SkillStop(UNTIL_ASK, "question")
    if until < today:
        return SkillStop(NOTICE_PAST, "question")
    if until > today + timedelta(days=MAX_NOTICE_DAYS):
        return SkillStop(NOTICE_LONG)
    return None


def check_notice_already(slots, texts, ctx):
    """not-already-true: the same words with the same last day draft nothing."""
    store = store_of(ctx)
    current = (store or {}).get("notice") or {}
    if current and _spaced(current.get("text", "")) == _spaced(slots["text"]) and current.get("until") == slots["until"]:
        return SkillStop(f"It already says that: {current['text']} (until {say_day(date.fromisoformat(current['until']))}). "
                         "Did you mean something else?", "question")
    return None


NOTICE_CHECKS = {"no-price": check_notice_price, "notice-dates": check_notice_dates, "not-already-true": check_notice_already}


def plan_notice(slots, ctx):
    store = store_of(ctx)
    if slots.get("clear"):
        if store is not None and not store.get("notice"):
            raise SkillStop(NO_NOTICE)
        return [{"op": "store.clear_notice", "args": {}}]
    text = " ".join(str(slots.get("text") or "").split())
    if not text:
        raise SkillStop(NOTICE_ASK, "question")
    if len(text) > MAX_NOTICE:
        raise SkillStop(NOTICE_TEXT_LONG, "question")
    if letters(text) < 3:
        raise SkillStop(NOTICE_SHORT, "question")
    until = slots.get("until")
    if not until:
        raise SkillStop(UNTIL_ASK, "question")
    clean = {"text": text, "until": until.strip() if isinstance(until, str) else until}
    for rule in ("no-price", "notice-dates", "not-already-true"):
        if (stop := NOTICE_CHECKS[rule](clean, texts_of(ctx), ctx)):
            raise stop
    return [{"op": "store.set_notice", "args": {"text": text, "until": clean["until"]}}]


# -- shop.contact -------------------------------------------------------------------------------------------------
CONTACT_ASK = "What is the new phone number, or the new street and town?"
PHONE_SHAPE = f"That doesn't look like a full phone number. I need the area code and seven more digits, like {EXAMPLE_PHONE}."
PHONE_REAL = "That doesn't look like a real US phone number. Could you check it and send it again?"
BOTH_PHONE = "Do you want a new phone number or no phone number on the site? I can only do one."


def phone_digits(text):
    """The ten digits of a US phone number written with spaces, dashes, dots or brackets (a leading 1 or +1 is dropped)."""
    digits = re.sub(r"[ \-.()]", "", str(text))
    if len(digits) == 12 and digits.startswith("+1"):
        digits = digits[2:]
    elif len(digits) == PHONE_DIGITS + 1 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def say_phone(digits) -> str:
    return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def check_contact_phone(slots, texts, ctx):
    """phone-ten-digits: ten US digits that can be a real number (area code and exchange do not start with 0 or 1)."""
    digits = phone_digits(slots["phone"])
    if not digits.isdigit() or len(digits) != PHONE_DIGITS:
        return SkillStop(PHONE_SHAPE, "question")
    if not PHONE_RE.fullmatch(digits):
        return SkillStop(PHONE_REAL, "question")
    return None


def check_contact_already(slots, texts, ctx):
    """not-already-true: the phone, street or town the site already shows."""
    store = store_of(ctx)
    if store is None:
        return None
    same = []
    if "phone" in slots and store.get("phone") == phone_digits(slots["phone"]):
        same.append(f"the phone is {say_phone(store['phone'])}")
    given = {ADDRESS_KEYS[f]: slots[f] for f in ADDRESS_KEYS if slots.get(f)}
    if given and all(_spaced(store.get(f, "")) == _spaced(v) for f, v in given.items()):
        same.append("the address is " + ", ".join(store[f] for f in ("streetAddress", "town") if f in given))
    wanted = int("phone" in slots) + int(bool(given)) + int(bool(slots.get("clear")))  # a removal is never already true
    if same and len(same) == wanted:
        return SkillStop("It already says that: " + " and ".join(same) + ". Did you mean something else?", "question")
    return None


CONTACT_CHECKS = {"phone-ten-digits": check_contact_phone, "not-already-true": check_contact_already}


def plan_contact(slots, ctx):
    phone, clear = slots.get("phone"), bool(slots.get("clear"))
    street = " ".join(str(slots.get("street_address") or "").split())
    town = " ".join(str(slots.get("town") or "").split())
    if phone and clear:
        raise SkillStop(BOTH_PHONE, "question")
    if not (phone or clear or street or town):
        raise SkillStop(CONTACT_ASK, "question")
    for value in (street, town):
        if len(value) > MAX_ADDRESS_PART:
            raise SkillStop(f"That is too long. Could you keep it under {MAX_ADDRESS_PART} characters?", "question")
        if value and not any(c.isalpha() for c in value):
            raise SkillStop("The street and the town each need some letters. What should it say?", "question")
        if "$" in value:
            raise SkillStop(PRICE_REPLY, "refused", "price")
    clean = {k: v for k, v in (("phone", phone), ("street_address", street), ("town", town)) if v}
    if clear:
        clean["clear"] = True  # the not-already-true rule must see that a removal is asked for, not only the address
    store = store_of(ctx)
    if phone:
        if (stop := CONTACT_CHECKS["phone-ten-digits"](clean, texts_of(ctx), ctx)):
            raise stop
        clean["phone"] = phone_digits(phone)
    if clear and store is not None and not store.get("phone"):
        raise SkillStop("There is no phone number on the site, so there is nothing to take off.")
    if (stop := CONTACT_CHECKS["not-already-true"](clean, texts_of(ctx), ctx)):
        raise stop
    ops = []
    if phone and not (store is not None and store.get("phone") == clean["phone"]):
        ops.append({"op": "store.set_phone", "args": {"phone": clean["phone"]}})
    if clear:
        ops.append({"op": "store.clear_phone", "args": {}})
    new_address = {k: v for k, v in (("streetAddress", street), ("town", town))
                   if v and not (store is not None and _spaced(store.get(k, "")) == _spaced(v))}  # a part that is already there is left out
    if new_address:
        ops.append({"op": "store.set_address", "args": new_address})
    return ops


# -- the skills ---------------------------------------------------------------------------------------------------
_CASES = "hass/tests/fixtures/skills/shop/{}.jsonl"
_INDEX, _HIKE = "storefront-mockup/index.html", "storefront-mockup/hike/index.html"

SHOP_HOURS = Skill(
    name="shop.hours", label="change the store hours",
    summary="Change the opening hours. Days he did not name keep exactly what the site says now.",
    triggers=(
        Trigger("we're open till 7 on fridays now"),
        Trigger("winter hours: 10 to 4 every day"),
        Trigger("chnage sat hours to 9 to 5", "typo"),
        Trigger("update the hours", "vague"),
        Trigger("Friday till 7, Saturday 9 to 6, closed Sundays", "multi"),
        Trigger("open Mondays now, 9 to 3"),
        Trigger("Mon to Sun 9 to 6 and Mon to Fri 8 to 5"),
        Trigger("remove the hours"),
    ),
    slots=(Slot("hours", "text_list", True, ask=HOURS_ASK, limit=("store", "hoursLine")),),
    rules=tuple(HOURS_CHECKS), plan=plan_hours,
    edits=(("hass/content/store.json", "hours"), (_INDEX, "the hours in the Visit block")),
    side_effects=("none",), preview="home", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "none"),
    refuse=(("the hours would be empty", NO_EMPTY_HOURS),
            ("a day he did not name would change", "Do you want Saturday to stay 9am–5pm?"),
            ("the same hours are already there", "It already says that. Did you mean something else?"),
            ("a closed day on a date or holiday", HOLIDAY_REPLY)),
    cases=_CASES.format("shop.hours"), version=1)

SHOP_NOTICE = Skill(
    name="shop.notice", label="put up a notice on the home page",
    summary="Put up, replace or take down the one dated notice at the top of the home page.",
    triggers=(
        Trigger("put a notice up: we're closed Thanksgiving, back Friday"),
        Trigger("notise: closed fri for inventory", "typo"),
        Trigger("take down the notice"),
        Trigger("tell people about the holiday", "vague"),
        Trigger("notice: closed Thursday. also hours Friday 10 to 4", "multi"),
        Trigger("new notice: parking is behind the store until Dec 1"),
        Trigger("notice: all produce 20% off"),
        Trigger("notice until next year"),
        Trigger("notice: call 805 555 0100 for orders"),
    ),
    slots=(Slot("clear", "bool", False),
           Slot("text", "text", "unless:clear", ask=NOTICE_ASK, owner_words=True),
           Slot("until", "day", "unless:clear", ask=UNTIL_ASK)),
    rules=tuple(NOTICE_CHECKS), plan=plan_notice,
    edits=(("hass/content/store.json", "notice"), (_INDEX, "the notice at the top of the page")),
    side_effects=("none",), preview="home", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "After the last day the notice also disappears by itself, with no change."),
    refuse=(("a price or a deal is in the notice", DEAL_REPLY),
            ("the last day is more than 60 days away", NOTICE_LONG),
            ("the last day has passed", NOTICE_PAST),
            ("there is no notice to take down", NO_NOTICE)),
    cases=_CASES.format("shop.notice"), version=1)

SHOP_CONTACT = Skill(
    name="shop.contact", label="change the phone number or the address",
    summary="Change or remove the store phone number, or change the street address and town.",
    triggers=(
        Trigger("our new number is 805-555-0100"),
        Trigger("chang the phoen to 805 555 0100", "typo"),
        Trigger("take the phone number off the site"),
        Trigger("we moved: 1023 Example Street, Morro Bay"),
        Trigger("update our address", "vague"),
        Trigger("new phone and new street", "multi"),
        Trigger("phone 555-0100"),
        Trigger("the number is 123-456-7890"),
        Trigger("just fix the town to Los Osos"),
    ),
    slots=(Slot("phone", "text"), Slot("clear", "bool", False),
           Slot("street_address", "text", False, limit=("store", "streetAddress")),
           Slot("town", "text", False, limit=("store", "town"))),
    rules=tuple(CONTACT_CHECKS), plan=plan_contact,
    edits=(("hass/content/store.json", "phone"), ("hass/content/store.json", "streetAddress"), ("hass/content/store.json", "town"),
           (_INDEX, "the Visit block and the shop details"), (_HIKE, "the address line")),
    side_effects=("none",), preview="home", approval="owner-yes", live_class="private-only",
    undo=Undo("revert", "none"),
    refuse=(("the number is not ten digits", PHONE_SHAPE), ("the number cannot be a real one", PHONE_REAL),
            ("a number and no number are both asked for", BOTH_PHONE)),
    cases=_CASES.format("shop.contact"), version=1)

SKILLS = (SHOP_HOURS, SHOP_NOTICE, SHOP_CONTACT)
