"""Hass real-hike ops (H04): create, update, cancel, complete, plus a read-only guest count.

Every event field comes from an argument: nothing is copied from a route idea or the labelled sample file, the
start is computed from a local date and time in America/Los_Angeles, and capacity never drops below the confirmed
guests counted (read-only) from an isolated RSVP database. No op notifies anyone or touches ``club.emailConnected``.
"""

from __future__ import annotations

import copy
import re
import sqlite3
import unicodedata
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from hass.content_model import EVENT_TEXT_FIELDS
from hass.ops import Arg, NeedsDetails, NotFound, Op, Refused, Touched

TZ = ZoneInfo("America/Los_Angeles")
# Event text fields an owner may give; recap is written only by hike.complete.
TEXT_FIELDS = tuple(f for f in EVENT_TEXT_FIELDS if f != "recap")
MAX_ID_BASE = 56  # leaves room for a "-NNN" suffix inside the 64-character id limit


def guest_counts(db_path) -> dict[str, int]:
    """{event_id: confirmed seats} from a read-only open of the RSVP database. Never selects email or name."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("SELECT event_id, SUM(party_size) FROM rsvps GROUP BY event_id").fetchall()
    finally:
        db.close()
    return {event_id: int(seats) for event_id, seats in rows}


def _seats(ctx, event_id):
    """Confirmed guests for the event, or a Refused when the count cannot be read (fail closed)."""
    path = ctx.settings.get("guestCountsDb")
    if not isinstance(path, str) or not path:
        return Refused("guest count unavailable")
    try:
        return guest_counts(path).get(event_id, 0)
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return Refused("guest count unavailable")


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


def _touch(before, event):
    return [Touched("events", event["id"], before, copy.deepcopy(event))]


CAPACITY_QUESTION = ("RSVPs are on: give either a capacity (a number of guests) or noCapacityLimit true for no limit, "
                     "but not both.")


def _off_capacity(event_id, capacity):  # a capacity stored on an event that takes no RSVPs (warning, never refused)
    return f"{event_id}: RSVPs are off, so capacity {capacity} has no effect until RSVPs are turned on"


def _hike_create(content, args, ctx):
    if args["rsvpEnabled"] and ("capacity" in args) == bool(args.get("noCapacityLimit")):
        return NeedsDetails(["capacity", "noCapacityLimit"], CAPACITY_QUESTION)
    starts = _start(args["date"], args["time"], ctx.now)
    if not isinstance(starts, str):
        return starts
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


def _hike_update(content, args, ctx):
    event = _scheduled(content, args["id"])
    if not isinstance(event, dict):
        return event
    given = {f: args[f] for f in UPDATE_FIELDS if f in args and not (f == "noCapacityLimit" and not args[f])}
    if not given:
        return NeedsDetails(list(UPDATE_FIELDS), f"What should change on {args['id']}? Give at least one of: "
                            + ", ".join(UPDATE_FIELDS))
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
    if "capacity" in given:
        seats = _seats(ctx, event["id"])
        if isinstance(seats, Refused):
            return seats
        if given["capacity"] < seats:
            return Refused(f"capacity {given['capacity']} is below {seats} confirmed guests")
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


_OPTIONAL_TEXT = {f: Arg("text", required=False) for f in TEXT_FIELDS if f != "meetingPoint"}
_CAPACITY = {"capacity": Arg("int", required=False, minimum=1), "noCapacityLimit": Arg("bool", required=False)}
_ID = {"id": Arg("id")}

OPS = (
    Op("hike.create", {"title": Arg("text"), "date": Arg("date"), "time": Arg("time"), "meetingPoint": Arg("text"),
                       "rsvpEnabled": Arg("bool"), **_CAPACITY, "trailId": Arg("id", required=False),
                       **_OPTIONAL_TEXT}, _hike_create),
    Op("hike.update", {**_ID, "title": Arg("text", required=False), "date": Arg("date", required=False),
                       "time": Arg("time", required=False), "meetingPoint": Arg("text", required=False),
                       "rsvpEnabled": Arg("bool", required=False), **_CAPACITY,
                       "trailId": Arg("id", required=False), **_OPTIONAL_TEXT}, _hike_update),
    Op("hike.cancel", _ID, _hike_cancel),
    Op("hike.complete", {**_ID, "recap": Arg("text", required=False)}, _hike_complete),
)
