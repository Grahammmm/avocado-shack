"""SKILLS-SPECIALS-1: the weekly specials skills (add, edit, remove, clear the finished ones, and show what is on).

Built on the AVO-SPECIALS-1 ops ``specials.add``, ``specials.edit``, ``specials.remove`` and ``specials.clear_expired``
(hass/ops/specials.py) and the model in hass/skills/model.py. The model reads the sentence and fills the slots; this
module checks them, plans the typed ops and writes the plain-words replies. Nothing here writes a file, touches the
network, approves, previews or publishes anything: the editor, the claims gate, the preview and ``yes <code>`` approval
are unchanged. Spec: reports/hass/SKILLS-SPEC.md section 2. Guide: docs/hass/skills/specials.md.

The deal line is the one place a price may appear (decision D9 keeps every other price out). It is shown exactly as the
owner typed it: the ``specials-deal-as-typed`` rule refuses a deal the model reworded, and the plan never edits it.
The end date is required: a missing one is the one short question ``Until what day should it run?``.

Interface assumptions (the dispatcher that calls these, SKILLS-FW-3, is not on main yet):
  * ``plan(slots, ctx)``: ``ctx.today`` (a date or YYYY-MM-DD), optionally ``ctx.content`` (hass.content_model.Content,
    read only) and ``ctx.texts`` (the owner's texts of this request). Without ``content`` the plan still works from ids.
  * A refusal is ``Refusal`` (a ValueError whose ``.reply`` is the plain-words text for the owner); the test kit shows it.
  * ``RULES[id](slots, texts, ctx) -> None | (owner reply, backlog reason)`` and ``READ_ONLY["specials.show"](slots, ctx)``
    are registered into ``hass.skills.dispatch`` when that module exists (rule ids start with ``specials-``: the table
    is shared). Registration is skipped silently before it exists.
  * Slot values arrive already resolved by the dispatcher for ``day`` (an ISO date) and ``product_ref`` (a product id);
    ``special`` is plain words (the owner's words for the special) and is resolved here, against ``ctx.content``.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from hass import nl_prep, voice
from hass.content_model import (ID_RE, MAX_SPECIAL_DAYS, MAX_SPECIAL_DEAL, MAX_SPECIAL_TITLE, MAX_SPECIALS_AT_ONCE,
                                MAX_SPECIALS_STORED, SPECIAL_EMAIL_RE, SPECIAL_LINK_RE, SPECIAL_PHONE_RE, active_specials,
                                iso_day, special_text_problem)
from hass.skills.model import Skill, Slot, Trigger, Undo


class Refusal(ValueError):
    """A plan that cannot go ahead: ``reply`` is the plain-words text for the owner (a question or a no)."""

    def __init__(self, reply):
        super().__init__(reply)
        self.reply = reply


# -- small helpers -------------------------------------------------------------------------------------------------
def _q(text) -> str:
    return voice.quote(text)  # the owner's own words (a title, a deal line) are shown as he typed them


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else iso_day(value)


def _today(ctx):
    return _day(getattr(ctx, "today", None))


def _store(ctx):
    store = getattr(getattr(ctx, "content", None), "store", None)
    return store if isinstance(store, dict) else None


def _stored(ctx):
    """Every saved special, or None when the plan has no content to look at (plan golden rows)."""
    store = _store(ctx)
    return None if store is None else [sp for sp in (store.get("specials") or []) if isinstance(sp, dict)]


def _products(ctx) -> dict:
    products = getattr(getattr(ctx, "content", None), "products", None) or []
    return {p["id"]: p for p in products if isinstance(p, dict) and "id" in p}


def pretty(day: date, today: date | None = None) -> str:
    """'Friday, November 13' (the year only when it is not this year)."""
    text = f"{day.strftime('%A, %B')} {day.day}"
    return text if today is None or day.year == today.year else f"{text}, {day.year}"


def _names(items) -> str:
    items = [_q(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def _folded(text) -> str:
    return " ".join(str(text).split()).casefold()


def _is_live(sp, today) -> bool:
    end = iso_day(sp.get("end"))
    return end is not None and (today is None or end >= today)


# -- reply texts ----------------------------------------------------------------------------------------------------
ASK_END = "Until what day should it run?"
ASK_ON = "What is the special on?"
ASK_DEAL = "What should the deal say? I'll show it just as you type it."
ASK_WHICH = "Which special do you mean?"
ASK_CHANGE = "What should change on that special?"
NOT_AS_TYPED = "I show the deal exactly as you type it. Could you type the deal the way it should read?"
PRICE_ONLY_IN_DEAL = "A price can only go in the deal line. Could you put it there and keep the title plain?"
ALREADY_SAYS = "That special already says that. Nothing changed."
NOTHING_FINISHED = "There are no finished specials to clear. Nothing changed."
LIST_FULL = "The list of saved specials is full. Do you want me to clear the finished ones first?"
NOT_AVAILABLE = "I can't see the specials right now. Could you ask again in a minute?"
NO_SPECIALS_NOW = "There are no specials on right now."

_WHY_WORDS = (("web address", "a web address"), ("email address", "an email address"), ("phone number", "a phone number"))
_NUMBER_WORDS = ("a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
                 "seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|half|"
                 "couple|few|several|dozen|zero")
_CURRENCY_WORDS = "dollars?|bucks?|cents?|pennies|penny|nickels?|dimes?|euros?|quid|usd|eur|gbp|cad"
# A price in a title: a currency sign, a figure or a spelled-out amount before a money word ('5 dollars', 'five bucks',
# 'twenty five cents', 'a buck'). 'pound' is left out on purpose: 'a five pound jar' is a weight, not a price.
_MONEY = re.compile(
    r"[$£€¥¢]"
    r"|\d\s*(?:" + _CURRENCY_WORDS + r"|¢)(?![a-z])"
    r"|(?<![a-z])(?:" + _NUMBER_WORDS + r")(?:[\s-]+(?:and|" + _NUMBER_WORDS + r"))*[\s-]+(?:" + _CURRENCY_WORDS + r")(?![a-z])",
    re.I)


# -- the rules (each id is one named, tested function) --------------------------------------------------------------
def _fields(slots):
    return (("title", "title", MAX_SPECIAL_TITLE), ("deal", "deal line", MAX_SPECIAL_DEAL))


def rule_text_limits(slots, texts, ctx):
    for field, label, limit in _fields(slots):
        value = slots.get(field)
        if not isinstance(value, str):
            continue
        value = value.strip()
        if len(value) > limit:
            return f"The {label} can be at most {limit} characters. Could you make it shorter?", "other"
        why = special_text_problem(value, deal=field == "deal")
        if why and not any(word in why for word, _ in _WHY_WORDS) and "price" not in why:
            return f"The {label} has something I can't use. Could you retype it in plain words?", "other"
    return None


def rule_no_links_or_contact(slots, texts, ctx):
    for field, label, _limit in _fields(slots):
        value = slots.get(field)
        if not isinstance(value, str):
            continue
        value = value.strip()
        for found, plain in ((SPECIAL_EMAIL_RE.search(value), "an email address"),  # before the web check: an email holds a domain
                             (SPECIAL_PHONE_RE.search(value), "a phone number"), (SPECIAL_LINK_RE.search(value), "a web address")):
            if found:
                return f"I can't put {plain} in the {label}. Could you send it without?", "policy"
    return None


def rule_price_in_deal_only(slots, texts, ctx):
    title = slots.get("title")
    if isinstance(title, str) and _MONEY.search(title):
        return PRICE_ONLY_IN_DEAL, "price"
    return None


# The deal as typed is one whole clause of his text, never a piece found inside it. A text is cut into clauses at his
# separators (commas, colons, brackets, a full stop, a dash); in each clause the words about the special come off the
# front ('put honey on special', 'change the honey special to', the special's own name) and the end date comes off the
# back ('until Friday', 'this week only', 'on the jam'). What is left, from the first clause with words in it to the last
# one, is the deal he typed. The model's deal must be equal to it (runs of spaces folded, nothing else), or he is asked.
# A text with two deals in it, or no clear deal, is asked about too: when in doubt, ask; never save a shortened deal.
_SEPARATOR = re.compile(r"(?<!\d),|,(?!\d)|[;:\n()\[\]\"\u201c\u201d\u2014\u2013!?|]|\s-+\s|\.(?!\d)")
_WHEN = (r"(?:this|next|the)\s+(?:week(?:end)?|month)(?:'?s)?(?:\s+only)?|today(?:\s+only)?|tonight|all\s+(?:week(?:end)?|month)"
         r"|for\s+(?:the|this)\s+(?:week(?:end)?|month)|(?:only\s+)?this\s+week(?:end)?")
_SPECIAL_WORD = r"(?:special|specials|deal|deals|sale)"
_JOIN = r"(?:to|is|at|for|of|on|now|will\s+be|should\s+(?:be|say|read)|reads?|says?)"
_VERBS = r"(?:please\s+)?(?:put|make|add|change|update|rename)"
# The end date at the back of a clause: a date word and a day, and nothing else after it ('till Friday with any purchase'
# is not cut: the words after the day may be part of the deal).
_ONE_DAY = (r"(?:(?:the|this|next|coming)\s+)?(?:(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day|today|tomorrow|tonight|week(?:end)?|month)"
            r"(?:\s+(?:night|morning|evening))?|end\s+of\s+(?:the\s+)?(?:week|month)"
            r"|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?"
            r"|nov(?:ember)?|dec(?:ember)?)\.?(?:\s+\d{1,2}(?:st|nd|rd|th)?)?"
            r"|\d{1,2}(?:st|nd|rd|th)|\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{2}-\d{2})")
_A_DATE = _ONE_DAY + r"(?:\s+(?:the\s+)?" + _ONE_DAY + r")*(?:\s+only)?"
_DATE_TAIL = re.compile(r"(?:^|\s+)(?:(?:good|valid|runs?|running|on|and)\s+)?(?:until|till|til|'til|thru|through|ending|ends|expires)\s+"
                        + _A_DATE + r"$"
                        r"|(?:^|\s+)(?:from|starting|beginning|on)\s+" + _A_DATE + r"(?:\s+(?:until|till|til|to|thru|through)\s+"
                        + _A_DATE + r")?$"
                        r"|(?:^|\s+)(?:" + _WHEN + r")$", re.I)


def _special_names(slots, ctx):
    """The special's own names he may type around the deal: its title, the words for it in an edit, its product's name,
    the saved special's title, each also by its last words ('strawberries' of 'Fresh strawberries'), longest first."""
    names = [slots.get("title"), slots.get("special"), (_products(ctx).get(slots.get("product")) or {}).get("name")]
    try:
        names.append((_own(slots, ctx) or {}).get("title"))
    except Exception:  # an odd context: no saved title to add
        pass
    out = set()
    for name in names:
        words = str(name).split() if isinstance(name, str) else []
        out |= {" ".join(words[i:]) for i in range(len(words))}
    return sorted(out, key=len, reverse=True)


def _cutters(names):
    """(front patterns, back patterns) for one special's names."""
    name = r"(?:(?:the|our|my|this|that|new)\s+)*(?:" + "|".join(r"\s+".join(map(re.escape, n.split())) for n in names) + r")\b" if names else None
    fronts = [re.compile(r".*\bon\s+(?:special|sale)\b(?:\s+" + _JOIN + r"\b)?", re.I | re.S),
              re.compile(r".*\b" + _SPECIAL_WORD + r"(?:\s+" + _JOIN + r"\b|\s*$)", re.I | re.S),
              re.compile(_VERBS + r"\b", re.I), re.compile(r"(?:" + _WHEN + r")\b", re.I)]
    if name:
        fronts.append(re.compile(name + r"(?:\s+" + _JOIN + r"\b)?", re.I))
    backs = [_DATE_TAIL] + ([re.compile(r"\s+(?:on|for)\s+" + name + r"$", re.I)] if name else [])
    return fronts, backs


def _clause_core(clause: str, cutters) -> tuple:
    """(start, end) of what is left of a clause once the words about the special are cut off its front and the end date
    off its back; start == end when nothing is left."""
    fronts, backs = cutters
    lo, hi, before = 0, len(clause), None
    while (lo, hi) != before:
        before = (lo, hi)
        lo, hi = _trim(clause, lo, hi)
        for front in fronts:
            found = front.match(clause, lo, hi)
            if found:
                lo, hi = _trim(clause, found.end(), hi)
        for back in backs:
            found = back.search(clause[lo:hi])
            if found:
                lo, hi = _trim(clause, lo, lo + found.start())
    return lo, hi


def _trim(text, lo, hi):
    while lo < hi and (text[lo].isspace() or text[lo] == "."):
        lo += 1
    while hi > lo and (text[hi - 1].isspace() or text[hi - 1] == "."):
        hi -= 1
    return lo, hi


def deals_typed(text, slots=None, ctx=None) -> list:
    """Each deal he typed in one text, as it stands in the text: the clauses left with words in them, run together.
    A clause with nothing left (only the special's words or the end date) ends a deal."""
    cutters = _cutters(_special_names(slots or {}, ctx))
    text, deals, start, end, cut = str(text), [], None, None, 0
    for sep in list(_SEPARATOR.finditer(text)) + [None]:
        stop = sep.start() if sep else len(text)
        lo, hi = _clause_core(text[cut:stop], cutters)
        if lo < hi:
            start = cut + lo if start is None else start
            end = cut + hi
        elif start is not None:
            deals.append(text[start:end])
            start = None
        cut = sep.end() if sep else len(text)
    if start is not None:
        deals.append(text[start:end])
    return deals


def _spaced(text) -> str:
    return " ".join(str(text).split())


def rule_deal_as_typed(slots, texts, ctx):
    deal = slots.get("deal")
    if not texts or not isinstance(deal, str) or not deal.strip():
        return None
    for text in texts:
        found = deals_typed(text, slots, ctx)
        if len(found) == 1 and _spaced(found[0]) == _spaced(deal):  # one deal in the text, and it is the whole of it
            return None
    return NOT_AS_TYPED, "other"


def rule_end_date_required(slots, texts, ctx):
    return None if slots.get("end") else (ASK_END, "other")


def _own(slots, ctx):
    """The saved special an edit is about (None for an add, or when there is nothing to look at)."""
    if not slots.get("special"):
        return None
    status, sp, _reply = resolve_special(ctx, slots["special"])
    return sp if status == "one" else None


def _span(slots, ctx):
    """(start, end, own id, whether the owner gave a date) for the special that would result."""
    today, own = _today(ctx), _own(slots, ctx)
    if slots.get("special") and own is None:  # an edit whose special cannot be looked up: no dates to judge
        return None, None, None, False, None
    start = _day(slots.get("start")) or (_day(own.get("start")) if own else None) or (None if own else today)
    end = _day(slots.get("end")) or (_day(own.get("end")) if own else None)
    return start, end, (own or {}).get("id"), bool(slots.get("start") or slots.get("end")), own


def rule_dates(slots, texts, ctx):
    today = _today(ctx)
    start, end, _own_id, gave, own = _span(slots, ctx)
    if today is None or end is None or start is None:
        return None
    if end < today:
        if own is not None and not gave:
            return f"That special finished on {pretty(end, today)}. Give me a new last day if you want to run it again.", "other"
        return f"{pretty(end, today)} has already passed. What is the last day?", "other"
    if end < start:
        return "The last day is before the first day. Which days should it run?", "other"
    if (end - start).days + 1 > MAX_SPECIAL_DAYS:
        return f"A special can run for at most {MAX_SPECIAL_DAYS} days. Could you pick an earlier last day?", "other"
    return None


def rule_max_six_active(slots, texts, ctx):
    stored, today = _stored(ctx), _today(ctx)
    start, end, own_id, _gave, _own_sp = _span(slots, ctx)
    if stored is None or today is None or start is None or end is None or end < today:
        return None
    others = [(max(_day(sp.get("start")) or today, today), _day(sp.get("end")), sp) for sp in stored
              if sp.get("id") != own_id and _day(sp.get("end")) and _day(sp.get("end")) >= today]
    for day in sorted({max(start, today), *(s for s, _e, _sp in others)}):
        running = [sp for s, e, sp in others if s <= day <= e]
        if len(running) + (1 if max(start, today) <= day <= end else 0) > MAX_SPECIALS_AT_ONCE:
            names = [sp.get("title", "") for sp in running][:MAX_SPECIALS_AT_ONCE]
            return (f"That would be more than six specials on {pretty(day, today)}. "
                    f"Which one should I take off first: {_names(names)}?"), "other"
    return None


def rule_twin(slots, texts, ctx):
    stored, title, today = _stored(ctx), slots.get("title"), _today(ctx)
    if stored is None or not isinstance(title, str):
        return None
    for sp in stored:
        if _folded(sp.get("title", "")) == _folded(title) and _is_live(sp, today) and sp.get("id") != (_own(slots, ctx) or {}).get("id"):
            return f"There is already a special called {_q(sp['title'])}. Do you want to change that one instead?", "other"
    return None


def rule_room(slots, texts, ctx):
    stored = _stored(ctx)
    if stored is not None and len(stored) >= MAX_SPECIALS_STORED:
        return LIST_FULL, "other"
    return None


def rule_something_to_change(slots, texts, ctx):
    given = any(slots.get(k) not in (None, "") for k in ("title", "deal", "start", "end", "product")) or slots.get("clear_product") is True
    return None if given else (ASK_CHANGE, "other")


def rule_which(slots, texts, ctx):
    status, _sp, reply = resolve_special(ctx, slots.get("special"))
    return None if status == "one" else (reply, "other")


def rule_not_already_true(slots, texts, ctx):
    own = _own(slots, ctx)
    if own is None or rule_something_to_change(slots, texts, ctx):
        return None
    return (ALREADY_SAYS, "other") if not _changes(slots, own) else None


def rule_finished_to_clear(slots, texts, ctx):
    stored, today = _stored(ctx), _today(ctx)
    if stored is not None and today is not None and all(_is_live(sp, today) for sp in stored):
        return NOTHING_FINISHED, "other"
    return None


RULES = {
    "specials-deal-as-typed": rule_deal_as_typed,
    "specials-text-limits": rule_text_limits,
    "specials-no-links-or-contact": rule_no_links_or_contact,
    "specials-price-in-deal-only": rule_price_in_deal_only,
    "specials-end-date-required": rule_end_date_required,
    "specials-dates": rule_dates,
    "specials-max-six-active": rule_max_six_active,
    "specials-twin": rule_twin,
    "specials-room": rule_room,
    "specials-something-to-change": rule_something_to_change,
    "specials-which": rule_which,
    "specials-not-already-true": rule_not_already_true,
    "specials-finished-to-clear": rule_finished_to_clear,
}


def _run(rule_ids, slots, ctx):
    """The plan runs the same rules the dispatcher does: the first hit becomes a refusal with its plain-words reply."""
    texts = getattr(ctx, "texts", None)
    for rule_id in rule_ids:
        hit = RULES[rule_id](slots, texts, ctx)
        if hit:
            raise Refusal(hit[0])


# -- finding a special the owner talks about -------------------------------------------------------------------------
_GENERIC = {nl_prep.stem(w) for w in ("the", "a", "an", "special", "specials", "deal", "deals", "sale", "on", "for", "this", "that",
                                      "one", "my", "it", "please", "week", "current", "same", "from", "off", "of")}
_ALL = {"all", "every", "everything", "each", "both"}


def _words(text) -> list:
    return [nl_prep.stem(w) for w in re.findall(r"[a-z0-9]+", nl_prep.fold(text or ""))]


def resolve_special(ctx, query):
    """(status, special, reply). status: 'one', 'several', 'none' or 'all'. ``special`` is the saved record when status is
    'one'. Without content (plan golden rows) only an exact id resolves. Finished specials are found only when no running
    or coming one fits, so 'the honey special' means the one on the page."""
    stored, today = _stored(ctx), _today(ctx)
    text = str(query or "").strip()
    if stored is None:
        return ("one", {"id": text}, "") if ID_RE.fullmatch(text) else ("none", None, ASK_WHICH)
    live = [sp for sp in stored if _is_live(sp, today)]

    def ask(pool):
        return f"Which special do you mean: {_names([sp['title'] for sp in pool][:10])}?"

    exact = [sp for sp in stored if sp.get("id") == text]
    if exact:
        return "one", exact[0], ""
    words = _words(text)
    if any(w in _ALL for w in words):
        pool = live
        return ("all", None, f"I take specials off one at a time. {ask(pool)}") if pool else ("none", None, NO_SPECIALS_NOW)
    terms = [w for w in words if w not in _GENERIC]
    if not terms:  # 'the special', 'it', nothing at all
        if len(live) == 1:
            return "one", live[0], ""
        return ("several", None, ask(live)) if live else ("none", None, NO_SPECIALS_NOW)
    products = _products(ctx)

    def hits(pool):
        out = []
        for sp in pool:
            hay = set(_words(sp.get("title", ""))) | set(_words((products.get(sp.get("product")) or {}).get("name", "")))
            if all(t in hay for t in terms):
                out.append(sp)
        return out

    found = hits(live) or hits(stored)
    if len(found) > 1:
        same = [sp for sp in found if _folded(sp.get("title", "")) == _folded(text)]
        found = same if len(same) == 1 else found
    if len(found) == 1:
        return "one", found[0], ""
    if found:
        return "several", None, ask(found)
    return "none", None, (f"I don't see a special like that. Right now there is {_names([sp['title'] for sp in live][:10])}. Which one do you mean?"
                          if live else NO_SPECIALS_NOW)


# -- plans -----------------------------------------------------------------------------------------------------------
def _clean(value):
    return value.strip() if isinstance(value, str) else value


def _product_title(slots, ctx):
    name = (_products(ctx).get(slots.get("product")) or {}).get("name")
    if isinstance(name, str) and len(name) <= MAX_SPECIAL_TITLE and not special_text_problem(name) and not _MONEY.search(name):
        return name
    return None


def _plan_add(slots, ctx):
    slots = {k: _clean(v) for k, v in dict(slots).items()}
    if not slots.get("title") and slots.get("product"):
        slots["title"] = _product_title(slots, ctx)  # the product's own name, unless it is too long or not plain
    for key, ask in (("title", ASK_ON), ("deal", ASK_DEAL), ("end", ASK_END)):
        if not slots.get(key):
            raise Refusal(ask)
    _run(ADD_RULES, slots, ctx)
    today = _today(ctx)
    args = {"title": slots["title"], "deal": slots["deal"], "end": slots["end"]}
    if slots.get("start") or today:
        args["start"] = slots.get("start") or today.isoformat()
    if slots.get("product"):
        args["product"] = slots["product"]
        if slots.get("picture") is not False:
            args["picture"] = True  # the product's own picture on the special, unless he said no
    return [{"op": "specials.add", "args": args}]


def _changes(slots, current) -> dict:
    """The fields the owner gave that differ from the saved special (``clearProduct`` only when there is a product)."""
    out = {}
    for field in ("title", "deal", "start", "end", "product"):
        value = _clean(slots.get(field))
        if value not in (None, "") and current.get(field) != value:
            out[field] = value
    if slots.get("clear_product") is True and ("product" in current or set(current) <= {"id"}):  # {id} only: nothing to compare against
        out["clearProduct"] = True
    return out


def _plan_edit(slots, ctx):
    slots = {k: _clean(v) for k, v in dict(slots).items()}
    status, current, reply = resolve_special(ctx, slots.get("special"))
    if status != "one":
        raise Refusal(reply)
    if slots.get("clear_product") is True and slots.get("product"):
        raise Refusal("Do you want a different product on that special, or none? Tell me which.")
    _run(EDIT_RULES, slots, ctx)
    changes = _changes(slots, current)
    if not changes:  # only reachable without content to compare against
        raise Refusal(ASK_CHANGE)
    return [{"op": "specials.edit", "args": {"id": current["id"], **changes}}]


def _plan_remove(slots, ctx):
    status, current, reply = resolve_special(ctx, _clean(slots.get("special")))
    if status != "one":
        raise Refusal(reply)
    return [{"op": "specials.remove", "args": {"id": current["id"]}}]


def _plan_clear(slots, ctx):
    _run(CLEAR_RULES, dict(slots), ctx)
    return [{"op": "specials.clear_expired", "args": {}}]


def _plan_show(slots, ctx) -> list:
    return []  # read only: the owner's answer is ``show_reply``


# -- the read-only answer -------------------------------------------------------------------------------------------
def show_reply(slots, ctx) -> str:
    """What the page shows today, in plain words, with every deal line exactly as it was typed."""
    store, today = _store(ctx), _today(ctx)
    if store is None or today is None:
        return NOT_AVAILABLE
    live = active_specials(store, today)
    coming = sorted((sp for sp in store.get("specials") or [] if isinstance(sp, dict) and (_day(sp.get("start")) or today) > today
                     and _day(sp.get("end"))), key=lambda sp: _day(sp["start"]))
    lines = []
    if live:
        lines.append("On now:")
        lines += [f"{_q(sp['title'])}: {_q(sp['deal'])}, through {pretty(_day(sp['end']), today)}" for sp in live]
    if coming:
        lines.append("Coming up:")
        lines += [f"{_q(sp['title'])}: {_q(sp['deal'])}, from {pretty(_day(sp['start']), today)}" for sp in coming[:3]]
    return "\n".join(lines) if lines else NO_SPECIALS_NOW


# -- declarations ----------------------------------------------------------------------------------------------------
_CASES = "hass/tests/fixtures/skills/specials/{}.jsonl"
_EDITS = (("hass/content/store.json", "specials"),)
_RESIDUE = "none"
_TEXT_RULES = ("specials-text-limits", "specials-no-links-or-contact", "specials-price-in-deal-only")
ADD_RULES = ("specials-deal-as-typed", *_TEXT_RULES, "specials-end-date-required", "specials-dates", "specials-twin",
             "specials-max-six-active", "specials-room")
EDIT_RULES = ("specials-which", "specials-something-to-change", "specials-deal-as-typed", *_TEXT_RULES, "specials-dates",
              "specials-twin", "specials-max-six-active", "specials-not-already-true")
REMOVE_RULES = ("specials-which",)
CLEAR_RULES = ("specials-finished-to-clear",)

SPECIALS_ADD = Skill(
    name="specials.add", label="put something on special",
    summary="Put an item or a deal in this week's specials box on the home page, shown until a last day.",
    triggers=(
        Trigger("put the avocado honey on special this week, 2 for 5 dollars"),
        Trigger("special on jam till Friday", "vague"),
        Trigger("new special: free sample Saturday, through the 14th"),
        Trigger("put the strawberries on special, 3 for $10, until Sunday"),
        Trigger("speical on the lemons, 2 for 3 dollers till sunday", "typo"),
        Trigger("add two specials: eggs 2 for 7 dollars till Friday and honey buy one get one till Sunday", "multi"),
        Trigger("make a special for the weekend", "vague"),
        Trigger("this week only: figs buy one get one free, through Saturday"),
    ),
    slots=(
        Slot("product", "product_ref", False),
        Slot("title", "text", "unless:product", ask=ASK_ON, owner_words=True),
        Slot("deal", "deal", True, ask=ASK_DEAL, owner_words=True),
        Slot("end", "day", True, ask=ASK_END),
        Slot("start", "day", False),
        Slot("picture", "bool", False),
    ),
    rules=ADD_RULES, plan=_plan_add, edits=_EDITS, side_effects=("none",), preview="home", approval="owner-yes",
    live_class="private-only", undo=Undo("revert", _RESIDUE),
    refuse=(
        ("the deal was reworded instead of shown as typed", NOT_AS_TYPED),
        ("a price in the title", PRICE_ONLY_IN_DEAL),
        ("six specials would already be showing", "That would be more than six specials. Which one should I take off first?"),
    ),
    cases=_CASES.format("specials.add"), version=1)

SPECIALS_EDIT = Skill(
    name="specials.edit", label="change a special",
    summary="Change one special: its title, deal line, product, first day or last day (for example extend it).",
    triggers=(
        Trigger("extend the honey special to next Sunday"),
        Trigger("change the jam special to 2 for 6 dollars"),
        Trigger("make the strawberry special run through Saturday"),
        Trigger("chnage the lemon speical to 3 for 4 dollers", "typo"),
        Trigger("update the special", "vague"),
        Trigger("extend the honey special to Sunday and the egg special to Friday", "multi"),
        Trigger("rename the sample special to Free sample Sunday"),
        Trigger("the honey special should start Monday"),
    ),
    slots=(
        Slot("special", "text", True, ask="Which special should I change?"),
        Slot("title", "text", False, owner_words=True),
        Slot("deal", "deal", False, owner_words=True),
        Slot("end", "day", False),
        Slot("start", "day", False),
        Slot("product", "product_ref", False),
        Slot("clear_product", "bool", False),
    ),
    rules=EDIT_RULES, plan=_plan_edit, edits=_EDITS, side_effects=("none",), preview="home", approval="owner-yes",
    live_class="private-only", undo=Undo("revert", _RESIDUE),
    refuse=(
        ("the special is not found or several fit", "Which special do you mean?"),
        ("nothing would change", ALREADY_SAYS),
        ("a price in the title", PRICE_ONLY_IN_DEAL),
    ),
    cases=_CASES.format("specials.edit"), version=1)

SPECIALS_REMOVE = Skill(
    name="specials.remove", label="take a special off",
    summary="Take one special off the home page before its last day.",
    triggers=(
        Trigger("take the special off"),
        Trigger("remove the honey special"),
        Trigger("end the jam special today"),
        Trigger("tke the strawbery special off", "typo"),
        Trigger("get rid of that special", "vague"),
        Trigger("take off the honey special and the egg special", "multi"),
        Trigger("we're out of figs, stop the special"),
        Trigger("cancel the sample special"),
    ),
    slots=(Slot("special", "text", True, ask="Which special should I take off?"),),
    rules=REMOVE_RULES, plan=_plan_remove, edits=_EDITS, side_effects=("none",), preview="home", approval="owner-yes",
    live_class="private-only", undo=Undo("revert", _RESIDUE),
    refuse=(
        ("several specials fit", "Which special do you mean?"),
        ("take them all off", "I take specials off one at a time. Which one do you mean?"),
    ),
    cases=_CASES.format("specials.remove"), version=1)

SPECIALS_CLEAR = Skill(
    name="specials.clear_expired", label="clear the finished specials",
    summary="Tidy the saved list by dropping specials whose last day has passed. They no longer show on the page.",
    triggers=(
        Trigger("clear out the old specials"),
        Trigger("clean up the finished specials"),
        Trigger("delete the expired specials"),
        Trigger("clera the old speicals", "typo"),
        Trigger("tidy up the specials", "vague"),
        Trigger("clear the old specials and tell me what's left", "multi"),
        Trigger("get rid of last week's specials"),
    ),
    slots=(), rules=CLEAR_RULES, plan=_plan_clear, edits=_EDITS, side_effects=("none",), preview="home",
    approval="owner-yes", live_class="private-only", undo=Undo("revert", _RESIDUE),
    refuse=(("no special has finished", NOTHING_FINISHED),), cases=_CASES.format("specials.clear_expired"), version=1)

SPECIALS_SHOW = Skill(
    name="specials.show", label="show this week's specials",
    summary="Say which specials are on now and which are coming up, with each deal as it was typed.",
    triggers=(
        Trigger("what are this week's specials"),
        Trigger("what specials do we have on"),
        Trigger("anything on special right now"),
        Trigger("wat specals r runing", "typo"),
        Trigger("how are the specials looking", "vague"),
        Trigger("what's on special and when does it end", "multi"),
        Trigger("is the honey special still on"),
    ),
    slots=(), rules=(), plan=_plan_show, edits=(), side_effects=("none",), preview="none", approval="none",
    live_class="read-only", undo=Undo("none", "none"),
    refuse=(("there are no specials", NO_SPECIALS_NOW),), cases=_CASES.format("specials.show"), version=1)

SKILLS = (SPECIALS_ADD, SPECIALS_EDIT, SPECIALS_REMOVE, SPECIALS_CLEAR, SPECIALS_SHOW)


def _register() -> None:
    """Hand the rules and the read-only answer to the dispatcher when it exists (SKILLS-FW-3). Never raises."""
    try:
        from hass.skills import dispatch
    except ImportError:
        return
    for rule_id, fn in RULES.items():
        dispatch.RULES.setdefault(rule_id, fn)
    dispatch.READ_ONLY.setdefault("specials.show", show_reply)


_register()
