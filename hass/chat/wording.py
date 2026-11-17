"""How a change is told to the owner: proposal text, record lines and the one-phrase summary of a draft.

AVB-12: moved verbatim out of hass/conversation.py, which imports every name back (hass.conversation.<name> is
unchanged). Pure functions; no state.
"""
import json, re  # noqa: E401
from datetime import date, datetime

from hass import live_policy, sitegen, voice
from hass.chat.shared import q
from hass.content_model import AVAILABILITY, PHONE_RE

PHOTO_PATH_RE = re.compile(r"assets/products/photo-[0-9a-f]{16}\.(jpg|png)")

VALUE_CUT = 120


def _value(v) -> str:
    text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, dict) else voice.value_words(v)
    return text if len(text) <= VALUE_CUT else text[:VALUE_CUT - 3] + "..."


def _full(v) -> str:
    """AV1537-06 (H05): a proposal's new value uncut (TEXT_LIMITS bound it); a list of strings joins with "; ".
    Anything else (None, numbers, whole JSON records) keeps the _value cut."""
    if isinstance(v, list) and v and all(isinstance(i, str) for i in v): return "; ".join(v)
    return v if isinstance(v, str) else _value(v)


def _changes(record: dict):
    before, after = record.get("before"), record.get("after")
    if isinstance(before, dict) and isinstance(after, dict):
        return [(k, before.get(k), after.get(k)) for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
    return [("record", before, after)]


COLLECTION_WORDS = {"products": "product", "makers": "maker", "events": "hike", "routeIdeas": "route idea"}
WHOLE_WORDS = {"store": "the shop details", "home": "the home page"}


def _side_name(side):
    for key in ("name", "title"):
        if isinstance(side, dict) and isinstance(side.get(key), str) and side[key].strip(): return " ".join(side[key].split())
    return None


def _name(record: dict):
    """The record's own name or title as the shop writes it (spacing folded), or None. AV0007-05: the new name wins over the old one."""
    name = _side_name(record.get("after")) or _side_name(record.get("before"))
    return name or (record.get("key") if record.get("collection") == "makers" and isinstance(record.get("key"), str) else None)


def _was(record: dict):
    """AV0007-05: the old name of a renamed record (both sides named, and differently); else None."""
    old, new = _side_name(record.get("before")), _side_name(record.get("after"))
    return old if old and new and old != new else None


def _day(record: dict):
    """AV0007-05: a hike's Pacific day (`Saturday, Nov 7`) from the snapshot that names it; None when the start is missing, naive or unreadable."""
    if record.get("collection") != "events": return None
    for side in (record.get("after"), record.get("before")):
        if isinstance(side, dict) and _side_name(side) and isinstance(side.get("startsAt"), str):
            try: start = datetime.fromisoformat(side["startsAt"])
            except ValueError: return None
            if start.tzinfo is None: return None
            local = start.astimezone(voice.LOCAL_TZ)
            return f"{local.strftime('%A, %b')} {local.day}"
    return None


def _label(record: dict):
    """AV0007-05: the record as the site names it: `Ridge walk (Saturday, Nov 7) (was Dawn walk)`; None when it has no name."""
    name = _name(record)
    if not name: return None
    return name + (f" ({_day(record)})" if _day(record) else "") + (f" (was {_was(record)})" if _was(record) else "")


def _subject(record: dict) -> str:
    """Who or what a change is about, for Mike: the name he knows (marked as his words) or the part of the shop."""
    label = _label(record)
    return q(label) if label else WHOLE_WORDS.get(record.get("collection"), "this")


def _is_phone(r: dict, k) -> bool:
    return r.get("collection") == "store" and k == "phone"


def _phone_site(v):
    """AV2007-07: a stored ten-digit store phone as the site spells it ('(805) 555-0142'); None for anything else."""
    return sitegen.phone_text(v) if isinstance(v, str) and PHONE_RE.fullmatch(v) else None


def _phone_phrase(r: dict, b, a) -> str:
    """The summary fragment for a store phone change; carries the numbers, since history shows only the summary."""
    old, new = _phone_site(b), _phone_site(a)
    if not (old or new): return voice.field_phrase("phone")
    return f"{voice.field_phrase('phone')} from {old or _shown('phone', b)} to {new or _shown('phone', a)}"


BULK_AVAILABILITY, BULK_NAMES = "product.set_availability_all", 10  # AV1052-04


def _bulk_groups(draft: dict):
    """AV1052-04: for a draft holding product.set_availability_all, ({word: [(id, name), ...] by id}, {ids}) from the records'
    net first-before/last-after change of `available`; None for any other draft (full detail, unchanged)."""
    if not any(isinstance(c, dict) and c.get("op") == BULK_AVAILABILITY for c in draft.get("ops") or []): return None
    groups = {}
    for r in draft.get("records") or []:
        b, a = r.get("before"), r.get("after")
        if r.get("collection") != "products" or not (isinstance(b, dict) and isinstance(a, dict)): continue
        if a.get("available") in AVAILABILITY and b.get("available") != a.get("available"):
            groups.setdefault(a["available"], []).append((str(r.get("key")), _side_name(a) or str(r.get("key"))))
    groups = {w: sorted(groups[w]) for w in AVAILABILITY if w in groups}
    return (groups, {pid for g in groups.values() for pid, _ in g}) if groups else None


def _bulk_lines(groups: dict) -> list:
    lines = []
    for word, items in groups.items():
        lines.append(f"{len(items)} product{'s' if len(items) != 1 else ''} marked available={word}:")
        lines += [f"  {name} ({pid})" for pid, name in items[:BULK_NAMES]]
        if len(items) > BULK_NAMES: lines.append(f"  ... and {len(items) - BULK_NAMES} more")
    return lines


def _fields(r: dict, bulk) -> list:
    """The record's changed fields, without `available` when a bulk group already tells it."""
    return [c for c in _changes(r) if not (bulk and r.get("key") in bulk[1] and c[0] == "available" and r.get("collection") == "products")]


def _summary(draft: dict) -> str:
    """One plain phrase for a draft, stored with it and shown in status and history: `the description for Hass avocado`."""
    bulk = _bulk_groups(draft)
    parts = [f"{len(items)} product{'s' if len(items) != 1 else ''} marked available={word}" for word, items in bulk[0].items()] if bulk else []
    for r in draft["records"]:
        name, word = _name(r), COLLECTION_WORDS.get(r.get("collection"), "")
        if r.get("before") is None and isinstance(r.get("after"), dict):
            parts.append(f"a new {word or 'entry'}" + (f": {name}" if name else ""))
            continue
        if _removed(r):
            parts.append(f"taking away the {word or 'entry'}" + (f": {name}" if name else ""))
            continue
        changes = _fields(r, bulk)
        if bulk and not changes: continue
        fields = list(dict.fromkeys(_phone_phrase(r, b, a) if _is_phone(r, f) else voice.field_phrase(f) for f, b, a in changes))
        what = ", ".join(fields[:3]) + (" and more" if len(fields) > 3 else "")
        parts.append(f"{what} for {_label(r) or WHOLE_WORDS.get(r.get('collection'), 'this')}")
    return _value("; ".join(parts) or "no changes")


def _when(field, value):
    """A start or end time is written as a day and time; any other value is None here."""
    return voice.natural_iso(value) if field in ("startsAt", "endsAt") and isinstance(value, str) else None


def _shown(field, v, cut=True) -> str:
    """A stored value in Mike's words (a time as a day and time, yes/no, status words); long text is cut unless cut is False."""
    if v is None: return "nothing"
    if (w := _when(field, v)): return w
    if isinstance(v, str) and field != "status": return v if not cut or len(v) <= VALUE_CUT else v[:VALUE_CUT - 3] + "..."
    return voice.value_words(v, field)


UNREADABLE_TIME = voice.natural_iso("soon")  # the words voice gives a time it cannot read
EVENT_ORDER = ("title", "startsAt", "meetingPoint", "trailId", "description", "difficulty", "distance", "duration", "bring",
               "accessNote", "rsvpEnabled", "capacity")  # HASS-CHAT-1: a new hike reads name, when, where first


STORE_LABELS = {"notice": "Home notice", "selection_checked_on": "Shelf check"}  # AV0222-08


def _iso_day(v):
    """AV0222-08: a strict real YYYY-MM-DD string as a date, else None (compact/basic forms and datetimes are not days)."""
    try: d = date.fromisoformat(v) if isinstance(v, str) else None
    except ValueError: return None
    return d if d is not None and d.isoformat() == v else None


def _notice_value(v):
    """AV0222-08: a {text, until} or {text, from, until} notice as 'Closed - [from <day> ]through <day>' in sitegen's day words; None if not that shape."""
    if not isinstance(v, dict) or set(v) not in ({"text", "until"}, {"text", "from", "until"}): return None
    text, until, first = v["text"], _iso_day(v["until"]), _iso_day(v["from"]) if "from" in v else None
    if not isinstance(text, str) or not text.strip() or until is None or ("from" in v and (first is None or first > until)): return None
    return f"{text} - " + (f"from {sitegen._day_text(first)} " if first else "") + f"through {sitegen._day_text(until)}"


def _store_value(r: dict, k, v):
    """AV0222-08: the store's notice window / shelf-check day in words, uncut; None for anything else (the generic wording applies)."""
    if r.get("collection") != "store" or v is None: return None
    if k == "notice": return _notice_value(v)
    day = _iso_day(v) if k == "selection_checked_on" else None
    return sitegen._day_text(day) if day else None


def _phrase(r: dict, k) -> str:
    return STORE_LABELS[k] if r.get("collection") == "store" and k in STORE_LABELS else voice.field_phrase(k)


def _shown_in(r: dict, k, v, routes=None, cut=True) -> str:
    """HASS-CHAT-1: _shown for one record: a hike's start says its time zone, and a route link is the route's name, never its id."""
    if (word := _store_value(r, k, v)) is not None: return word
    if k == "trailId" and isinstance(v, str):
        route = (routes or {}).get(v)
        return route["title"] if isinstance(route, dict) and isinstance(route.get("title"), str) and route["title"].strip() else "a saved route"
    if r.get("collection") == "products" and k == "available" and isinstance(v, str) and v in sitegen.AVAILABILITY_WORDS:
        return sitegen.AVAILABILITY_WORDS[v]  # AV0007-05: the words the product card shows (yes/limited/no only on this field)
    if _is_phone(r, k) and (site := _phone_site(v)):
        return site  # AV2007-07: the number as the site shows it; storage stays ten digits
    shown = _shown(k, v, cut)
    return shown + " (Pacific time)" if r.get("collection") == "events" and k == "startsAt" and _when(k, v) and \
        isinstance(v, str) and _when(k, v) != UNREADABLE_TIME else shown


def _added(r: dict, routes=None) -> list:  # AV1737-06 (H05/H06): an added record's visible fields, one per line (at most 40)
    rows = [(k, v) for k, v in sorted(r["after"].items()) if v not in (None, "", []) and k not in voice.SKIP_FIELDS and k in voice.FIELDS]
    if r.get("collection") == "events":  # HASS-CHAT-1: name, when, where first; a new hike is scheduled, so that line says nothing
        rank = {k: i for i, k in enumerate(EVENT_ORDER)}
        rows = sorted((kv for kv in rows if kv != ("status", "scheduled")), key=lambda kv: (rank.get(kv[0], len(rank)), kv[0]))
    word, name = COLLECTION_WORDS.get(r.get("collection"), "entry"), _label(r)
    lines = [f"A new {word}" + (f": {q(name)}" if name else "")]
    for k, v in rows[:40]:
        photo = k == "image" and PHOTO_PATH_RE.fullmatch(str(v))
        lines.append(f"  {_phrase(r, k)}: " + ("the photo from your message" if photo else q(_shown_in(r, k, v, routes, False)).replace("\n", "\n    ")))
    return lines + (["  and a few more details"] if len(rows) > 40 else [])


def _aware(v):
    """AV2007-17: the instant of a timezone-aware ISO time string, else None."""
    try: t = datetime.fromisoformat(v) if isinstance(v, str) else None
    except ValueError: return None
    return t if t is not None and t.tzinfo is not None else None


def _change_line(r: dict, field, b, a, undo: bool, full_before: bool, routes=None) -> str:
    who, phrase = _subject(r), voice.field_phrase(field)
    if r.get("collection") == "events" and field == "status":  # AV2007-17: a hike says what happens to it, not the field
        if a == "cancelled" and b != "cancelled": return f"{who}: cancelled"
        if b == "cancelled" and a == "scheduled": return f"{who}: scheduled again"
    if r.get("collection") == "events" and field == "startsAt" and _aware(b) and _aware(a) and _aware(b) != _aware(a):
        return f"{who}: rescheduled\n" + _plain_change(r, field, b, a, undo, full_before, routes)
    return _plain_change(r, field, b, a, undo, full_before, routes)


def _plain_change(r: dict, field, b, a, undo: bool, full_before: bool, routes=None) -> str:
    who, phrase = _subject(r), _phrase(r, field)
    if field == "image" and (PHOTO_PATH_RE.fullmatch(str(a)) or undo and PHOTO_PATH_RE.fullmatch(str(b))):
        return f"{who}: the photo goes back to the previous one" if undo else f"{who}: the photo will be the one from your message"
    old, new = _shown_in(r, field, b, routes, not full_before), _shown_in(r, field, a, routes, False)
    if "\n" in new or "\n" in old or len(old) + len(new) > 70:
        return f"{who}, {phrase}:\n  was: " + q(old).replace("\n", "\n    ") + "\n  now: " + q(new).replace("\n", "\n    ")
    return f"{who}, {phrase}: from {q(old)} to {q(new)}"


def _removed(r: dict) -> bool:
    return isinstance(r.get("before"), dict) and r.get("after") is None


def _removal(r: dict, done: bool = False) -> str:
    """A whole record going away (an undo of something added) is said as that, never as a list of fields going to nothing."""
    word, name = COLLECTION_WORDS.get(r.get("collection"), "entry"), _label(r)
    if done: return f"The {word} {q(name)} was removed." if name else f"That {word} was removed."
    return f"Remove the {word} {q(name)}." if name else f"Remove this {word}."


def _record_lines(draft: dict, undo: bool = False, full_before=False, done: bool = False, routes=None) -> list:  # AV0022-08: proposal_text and show
    bulk = _bulk_groups(draft)
    lines = _bulk_lines(bulk[0]) if bulk else []
    for r in draft["records"]:
        lines += [_removal(r, done)] if _removed(r) else _added(r, routes) if r.get("before") is None and isinstance(r.get("after"), dict) else [
            _change_line(r, f, b, a, undo, full_before, routes) for f, b, a in _fields(r, bulk)]
    return lines + [f"Heads up: {voice.explain_warning(w)}" for w in draft.get("warnings") or []]


def proposal_text(code: str, draft: dict, expires_at: str, repeat: bool = False, head: str = "", undo: bool = False, live_site=None, now=None,
                  notes=(), routes=None, reasons=None) -> str:
    """notes (HASS-CHAT-1): plain lines on what Hass chose so the change can go live (sign-up, a detail left out), shown under
    the change; routes: route ideas by id, so a route link is shown by its name."""
    lines = [head or "Here's the change I'd make:"] + _record_lines(draft, undo, full_before=bool(live_site), routes=routes) + list(notes)
    wait = f"I'll hold this for you until {voice.natural_iso(expires_at, now)}."
    if live_site:
        reasons = live_policy.check(draft) if reasons is None else reasons  # HASS-SEC-2 (M1): the conversation's own reasons
        that_way = " that way" if notes else ""
        return "\n".join(lines + [wait, live_policy.refusal(reasons) if reasons else
                                 f"Reply {q('yes ' + code)} to put it on the website{that_way} (it should show within a few minutes), "
                                 f"or {q('no ' + code)} to cancel." + (" To change something, just tell me." if notes else "")])
    yes = f"yes {code}" if repeat else "yes"  # a repeat of a closed draft needs its new code
    lines += [wait, f"Reply {q(yes)} to save it, or no to cancel. If something's wrong, tell me what to fix."]
    return "\n".join(lines)
