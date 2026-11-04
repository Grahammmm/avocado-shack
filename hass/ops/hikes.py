"""Hass real-hike ops (H04): create, update, cancel, complete, plus a read-only guest count.

Every event field comes from an argument: nothing is copied from a route idea or the labelled sample file, the
start is computed from a local date and time in America/Los_Angeles, and capacity never drops below the confirmed
guests counted (read-only) from an isolated RSVP database. No op notifies anyone or touches ``club.emailConnected``.
A ``trailId`` that is not a route idea is refused: "unknown route idea <id>" or "<id> is a hike, not a route idea".
AV1937-05: ``hike.repeat`` drafts a new scheduled hike on a new date and time from a real hike (REPEAT_FIELDS, RSVP
setting and capacity); never its id, status, recap or guests, and never from a route idea or the sample file.
A text over its content_model.TEXT_LIMITS limit is refused with one reply: "<field> is longer than <n> characters".
"""

from __future__ import annotations

import copy
import re
import sqlite3
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from hass.claims import REPEAT_FIELDS
from hass.content_model import EVENT_REQUIRED, EVENT_TEXT_FIELDS, TEXT_LIMITS
from hass.ops import Arg, NeedsDetails, NotFound, Op, Refused, Touched

TZ = ZoneInfo("America/Los_Angeles")
# Event text fields an owner may give; recap is written only by hike.complete and hike.recap.
TEXT_FIELDS = tuple(f for f in EVENT_TEXT_FIELDS if f != "recap")
MAX_AHEAD_DAYS = 400  # a start further out is a question ("check the year"), never a draft
MAX_ID_BASE = 56  # leaves room for a "-NNN" suffix inside the 64-character id limit
LIMITED = tuple(dict.fromkeys(("title", "meetingPoint", *TEXT_FIELDS)))  # the order the first over-long text is named


# Seats per event plus a count of rows whose party size is missing, not a stored integer, or below 1 (a SUM over
# such rows would skip, coerce or subtract them and under-count). Never selects email or name.
GUEST_QUERY = ("SELECT event_id, SUM(party_size), SUM(party_size IS NULL OR typeof(party_size) != 'integer' "
               "OR party_size < 1) FROM rsvps GROUP BY event_id")


def guest_counts_checked(db_path) -> tuple[dict[str, int], set[str]]:
    """({event_id: confirmed seats}, {event ids with a bad party_size row}) from a read-only open; bad events are
    left out of the counts, so a caller can say "unavailable" instead of a smaller number."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(GUEST_QUERY).fetchall()
    finally:
        db.close()
    bad = {event_id for event_id, _seats, n_bad in rows if n_bad}
    return {event_id: int(seats) for event_id, seats, _n in rows if event_id not in bad}, bad


def guest_counts(db_path) -> dict[str, int]:
    """{event_id: confirmed seats}; raises ValueError when any event has a bad party_size row, so callers without
    per-event handling say "unavailable" (as for an unreadable database) instead of a smaller number."""
    counts, bad = guest_counts_checked(db_path)
    if bad:
        raise ValueError("bad party_size row")
    return counts


def _seats(ctx, event_id):
    """Confirmed guests for the event, or a Refused when the count cannot be read or has a bad row (fail closed)."""
    path = ctx.settings.get("guestCountsDb")
    if not isinstance(path, str) or not path:
        return Refused("guest count unavailable")
    try:
        counts, bad = guest_counts_checked(path)
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return Refused("guest count unavailable")
    return Refused("guest count unavailable") if event_id in bad else counts.get(event_id, 0)


def _guest_warning(ctx, event):
    """Draft warning (never a refusal) when a cancel or RSVPs off leaves confirmed guests untold."""
    if not event.get("rsvpEnabled"):
        return
    seats, eid = _seats(ctx, event["id"]), event["id"]
    if isinstance(seats, Refused):
        ctx.warnings.append(f"{eid} guest count unavailable; check RSVPs before approving")
    elif seats > 0:
        ctx.warnings.append(f"{eid} has {seats} confirmed guest{'s' * (seats != 1)}; nobody is notified automatically")


def _move_warning(ctx, event, starts_at):
    """Draft warning (never a refusal) when a new start leaves confirmed guests expecting the old one."""
    day, clock = _local_parts(starts_at)
    if (day, clock) == _local_parts(event["startsAt"]):
        return
    seats, eid = _seats(ctx, event["id"]), event["id"]
    if isinstance(seats, Refused):
        ctx.warnings.append(f"{eid} guest count unavailable; check RSVPs before approving")
    elif seats > 0:
        ctx.warnings.append(f"{eid} moves to {day} {clock} Pacific; {seats} confirmed guest{'s' * (seats != 1)} "
                            f"{'are' if seats != 1 else 'is'} not told automatically")


def _fmt(offset) -> str:
    minutes = int(offset.total_seconds() // 60)
    sign, minutes = ("-" if minutes < 0 else "+"), abs(minutes)
    return "%s%02d:%02d" % (sign, minutes // 60, minutes % 60)


def _start(day: str, clock: str, now):
    """ISO start with offset for a local date + time, or NeedsDetails (repeated/missing time) or Refused (past)."""
    naive = datetime.combine(date.fromisoformat(day), time.fromisoformat(clock))
    first, second = naive.replace(tzinfo=TZ, fold=0), naive.replace(tzinfo=TZ, fold=1)
    if first.utcoffset() != second.utcoffset():
        gap = first.astimezone(timezone.utc).astimezone(TZ).replace(tzinfo=None) != naive
        question = (f"{day} {clock} does not exist in Pacific time (clocks jump forward); what time should it start?"
                    if gap else f"{day} {clock} happens twice in Pacific time ({_fmt(first.utcoffset())} and "
                    f"{_fmt(second.utcoffset())}); which one do you mean?")
        return NeedsDetails(["time"], question)
    if first <= now:
        return Refused("start is in the past")
    if first - now > timedelta(days=MAX_AHEAD_DAYS):
        return NeedsDetails(["date"], f"{day} is more than {MAX_AHEAD_DAYS} days away; check the year. "
                                      "What date should it be?")
    return first.isoformat(timespec="seconds")


def _local_parts(starts_at: str):
    local = datetime.fromisoformat(starts_at.replace("Z", "+00:00")).astimezone(TZ)
    return local.date().isoformat(), local.strftime("%H:%M")


def _events(content):
    return content.community["events"]


def _event(content, event_id):
    return next((e for e in _events(content) if e["id"] == event_id), None)


def _slug_id(content, day, title):
    plain = "".join(c for c in unicodedata.normalize("NFKD", title) if not unicodedata.combining(c))  # ñ→n, é→e, ﬁ→fi
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    base = f"hike-{day}-{slug}"[:MAX_ID_BASE].rstrip("-")
    taken = {e["id"] for e in _events(content)} | {i["id"] for i in content.community["routeIdeas"]}
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _same(a, b) -> bool:  # same rule as catalog._same: whitespace collapsed, case folded
    return " ".join(str(a).split()).casefold() == " ".join(str(b).split()).casefold()


def _local_day(event):
    try:
        return _local_parts(event["startsAt"])[0]
    except (KeyError, TypeError, ValueError, AttributeError):  # an unparseable start is skipped, never raised
        return None


def _hike_twin(content, day, title, skip=None):
    """The first scheduled event, other than id skip, with an equal title on the same local (Pacific) date."""
    return next((e for e in _events(content) if e.get("status") == "scheduled" and _local_day(e) == day
                 and e.get("id") != skip and _same(e.get("title", ""), title)), None)


def _touch(before, event):
    return [Touched("events", event["id"], before, copy.deepcopy(event))]


CAPACITY_QUESTION = ("RSVPs are on: give either a capacity (a number of guests) or noCapacityLimit true for no limit, "
                     "but not both.")


def _off_capacity(event_id, capacity):  # a capacity stored on an event that takes no RSVPs (warning, never refused)
    return f"{event_id}: RSVPs are off, so capacity {capacity} has no effect until RSVPs are turned on"


def _trail_problem(content, trail_id):
    """Refused when trailId is a hidden idea (AV1322-03), a hike or no route idea at all (RF1530-3), else None."""
    if trail_id is None:
        return None
    if trail_id in [i["id"] for i in content.community["routeIdeas"] if i["status"] == "hidden"]:
        return Refused(f"route idea {trail_id} is hidden; restore it first")
    if any(e["id"] == trail_id for e in _events(content)):
        return Refused(f"{trail_id} is a hike, not a route idea")
    if all(i["id"] != trail_id for i in content.community["routeIdeas"]):
        return Refused(f"unknown route idea {trail_id}")
    return None


def _too_long(args, fields):
    """Refused naming the first of fields whose string is over its event limit (code points, as the validator
    counts; the value is never echoed), else None. The validator stays the backstop for hand edits."""
    limits = TEXT_LIMITS["event"]
    return next((Refused(f"{f} is longer than {limits[f]} characters") for f in fields
                 if isinstance(args.get(f), str) and len(args[f]) > limits[f]), None)


def _hike_create(content, args, ctx):
    if (problem := _too_long(args, LIMITED)) is not None:
        return problem
    if args["rsvpEnabled"] and ("capacity" in args) == bool(args.get("noCapacityLimit")):
        return NeedsDetails(["capacity", "noCapacityLimit"], CAPACITY_QUESTION)
    starts = _start(args["date"], args["time"], ctx.now)
    if not isinstance(starts, str):
        return starts
    if (problem := _trail_problem(content, args.get("trailId"))) is not None:
        return problem
    twin = _hike_twin(content, args["date"], args["title"])
    if twin is not None:
        return Refused(f"{twin['id']} is already scheduled with this title on {args['date']}; update it instead")
    event = {"id": _slug_id(content, args["date"], args["title"]), "title": args["title"], "startsAt": starts,
             "timezone": "America/Los_Angeles", "status": "scheduled", "meetingPoint": args["meetingPoint"]}
    event.update({f: args[f] for f in TEXT_FIELDS if f in args and f != "meetingPoint"})
    event["rsvpEnabled"] = args["rsvpEnabled"]
    for field in ("capacity", "trailId"):
        if field in args:
            event[field] = args[field]
    _events(content).append(event)
    if not args["rsvpEnabled"] and "capacity" in args:
        ctx.warnings.append(_off_capacity(event["id"], args["capacity"]))
    return _touch(None, event)


def _hike_repeat(content, args, ctx):
    """A new scheduled hike on args date/time with the title, text, route link and RSVP settings of a real hike."""
    source = _event(content, args["id"])
    if source is None:
        if any(i["id"] == args["id"] for i in content.community["routeIdeas"]):
            return Refused(f"{args['id']} is a route idea, not a real hike")
        return NotFound(args["id"])
    missing = [f for f in ("meetingPoint", "rsvpEnabled") if f not in source]
    if missing:  # a legacy hike: nothing is invented for it
        return NeedsDetails(missing, f"{args['id']} has no {' or '.join(missing)} on record; update that hike first, "
                                     "then repeat it.")
    copied = {f: copy.deepcopy(source[f]) for f in (*REPEAT_FIELDS, "rsvpEnabled", "capacity") if f in source}
    if copied["rsvpEnabled"] and "capacity" not in copied:
        copied["noCapacityLimit"] = True  # the source had no limit
    return _hike_create(content, {**copied, "date": args["date"], "time": args["time"]}, ctx)


def _scheduled(content, event_id):
    """The scheduled event dict, or NotFound / Refused naming its state."""
    event = _event(content, event_id)
    if event is None:
        return NotFound(event_id)
    if event["status"] != "scheduled":
        return Refused(f"{event_id} is {event['status']}, not scheduled")
    return event


UPDATE_FIELDS = ("title", "date", "time", "meetingPoint", "rsvpEnabled", "capacity", "noCapacityLimit", "trailId") \
    + TEXT_FIELDS
# Optional fields hike.update may delete; title, date, time, meetingPoint, RSVPs and capacity are never cleared.
CLEARABLE = tuple(f for f in TEXT_FIELDS if f != "meetingPoint") + ("trailId",)
_KNOWN = set(UPDATE_FIELDS) | set(EVENT_REQUIRED) | {"recap"}
_CLEAR_CHECKS = ((lambda n, a: n not in _KNOWN, "clear: {} is not a hike field"),  # checked in this order
                 (lambda n, a: n not in CLEARABLE, "clear: {} cannot be removed"),
                 (lambda n, a: n in a, "{} cannot be set and cleared together"))


def _spaced(v):
    return " ".join(v.split()) if isinstance(v, str) else v


def _hike_update(content, args, ctx):
    if (problem := _too_long(args, LIMITED)) is not None:
        return problem
    event = _scheduled(content, args["id"])
    if not isinstance(event, dict):
        return event
    if (problem := _trail_problem(content, args.get("trailId"))) is not None:
        return problem
    clear = list(dict.fromkeys(args.get("clear", ())))  # duplicates collapse
    for test, why in _CLEAR_CHECKS:
        bad = next((n for n in clear if test(n, args)), None)
        if bad is not None:
            return Refused(why.format(bad))
    given = {f: args[f] for f in UPDATE_FIELDS if f in args and not (f == "noCapacityLimit" and not args[f])}
    if not given and not clear:
        return NeedsDetails(list(UPDATE_FIELDS), f"What should change on {args['id']}? Give at least one of: "
                            + ", ".join(UPDATE_FIELDS))
    given = {f: v for f, v in given.items() if not (f in ("title", "meetingPoint") + TEXT_FIELDS
                                                    and isinstance(event.get(f), str) and _spaced(event[f]) == _spaced(v))}
    if not given and not clear:  # only spacing differs from the stored text: the page would render it identically
        return Refused(f"hike {args['id']} already says that")
    if "capacity" in given and "noCapacityLimit" in given:
        return NeedsDetails(["capacity", "noCapacityLimit"], "Give either a new capacity or noCapacityLimit true, not both.")
    turning_on = given.get("rsvpEnabled") is True and not event.get("rsvpEnabled")
    if turning_on and "capacity" not in given and "noCapacityLimit" not in given and event.get("capacity") is None:
        return NeedsDetails(["capacity", "noCapacityLimit"], CAPACITY_QUESTION)
    changes = {f: v for f, v in given.items() if f not in ("date", "time", "noCapacityLimit")}
    if "date" in given or "time" in given:
        old_day, old_clock = _local_parts(event["startsAt"])
        starts = _start(given.get("date", old_day), given.get("time", old_clock), ctx.now)
        if not isinstance(starts, str):
            return starts
        changes["startsAt"] = starts
    if "title" in given or "date" in given:  # a time-only change cannot move the local day
        day = given.get("date") or _local_parts(event["startsAt"])[0]
        twin = _hike_twin(content, day, given.get("title", event.get("title", "")), skip=event["id"])
        if twin is not None:
            return Refused(f"{twin['id']} is already scheduled with this title on {day}")
    if "capacity" in given:
        seats = _seats(ctx, event["id"])
        if isinstance(seats, Refused):
            return seats
        if given["capacity"] < seats:
            return Refused(f"capacity {given['capacity']} is below {seats} confirmed guests")
    if turning_on and "capacity" not in given and "noCapacityLimit" not in given and event.get("capacity") is not None:
        seats = _seats(ctx, event["id"])  # RSVP rows survive RSVPs off, so the stored capacity may be stale
        if isinstance(seats, Refused):
            return seats
        if event["capacity"] < seats:
            return Refused(f"stored capacity {event['capacity']} is below {seats} confirmed guests; "
                           "give a new capacity or noCapacityLimit true")
    if given.get("rsvpEnabled") is False:
        _guest_warning(ctx, event)
    elif "startsAt" in changes and event.get("rsvpEnabled"):
        _move_warning(ctx, event, changes["startsAt"])
    if "capacity" in given and not given.get("rsvpEnabled", event.get("rsvpEnabled")):
        ctx.warnings.append(_off_capacity(event["id"], given["capacity"]))
    elif turning_on and "capacity" not in given and "noCapacityLimit" not in given and event.get("capacity") is not None:
        ctx.warnings.append(f"{event['id']}: RSVPs turned on with the stored capacity {event['capacity']}")
    before = copy.deepcopy(event)
    event.update(changes)
    if "noCapacityLimit" in given:
        event.pop("capacity", None)
    for name in clear:  # deleted, never set to ""; an absent field is no change
        event.pop(name, None)
    return _touch(before, event)


def _hike_cancel(content, args, ctx):
    event = _scheduled(content, args["id"])
    if not isinstance(event, dict):
        return event
    _guest_warning(ctx, event)
    before = copy.deepcopy(event)
    event["status"] = "cancelled"
    return _touch(before, event)


def _hike_complete(content, args, ctx):
    if (problem := _too_long(args, ("recap",))) is not None:
        return problem
    event = _scheduled(content, args["id"])
    if not isinstance(event, dict):
        return event
    if datetime.fromisoformat(event["startsAt"].replace("Z", "+00:00")) > ctx.now:
        return Refused(f"{event['id']} has not started yet; it can be completed after its start")
    before = copy.deepcopy(event)
    event["status"] = "completed"
    if "recap" in args:
        event["recap"] = args["recap"]
    return _touch(before, event)


def _hike_recap(content, args, ctx):
    """Set or correct the recap of a completed hike; no other field changes."""
    if (problem := _too_long(args, ("recap",))) is not None:
        return problem
    event = _event(content, args["id"])
    if event is None:
        return NotFound(args["id"])
    if event["status"] == "scheduled":
        return Refused(f"{event['id']} is scheduled; use hike.complete with a recap")
    if event["status"] != "completed":
        return Refused(f"{event['id']} is {event['status']}")
    if isinstance(event.get("recap"), str) and _spaced(event["recap"]) == _spaced(args["recap"]):
        return Refused(f"hike {args['id']} already says that")
    before = copy.deepcopy(event)
    event["recap"] = args["recap"]  # an equal recap (spacing ignored) is refused above
    return _touch(before, event)


_OPTIONAL_TEXT = {f: Arg("text", required=False) for f in TEXT_FIELDS if f != "meetingPoint"}
_CAPACITY = {"capacity": Arg("int", required=False, minimum=1), "noCapacityLimit": Arg("bool", required=False)}
_ID = {"id": Arg("id")}

OPS = (
    Op("hike.create", {"title": Arg("text"), "date": Arg("date"), "time": Arg("time"), "meetingPoint": Arg("text"),
                       "rsvpEnabled": Arg("bool"), **_CAPACITY, "trailId": Arg("id", required=False),
                       **_OPTIONAL_TEXT}, _hike_create),
    Op("hike.repeat", {**_ID, "date": Arg("date"), "time": Arg("time")}, _hike_repeat),
    Op("hike.update", {**_ID, "title": Arg("text", required=False), "date": Arg("date", required=False),
                       "time": Arg("time", required=False), "meetingPoint": Arg("text", required=False),
                       "rsvpEnabled": Arg("bool", required=False), **_CAPACITY,
                       "trailId": Arg("id", required=False), **_OPTIONAL_TEXT,
                       "clear": Arg("text_list", required=False)}, _hike_update),
    Op("hike.cancel", _ID, _hike_cancel),
    Op("hike.complete", {**_ID, "recap": Arg("text", required=False)}, _hike_complete),
    Op("hike.recap", {**_ID, "recap": Arg("text")}, _hike_recap),
)
