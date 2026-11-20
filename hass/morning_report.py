"""Morning shelf report from the owner's last confirmed availability (AVB-23): never stock counts. Read-only.
    python3 hass/morning_report.py [--today YYYY-MM-DD] [--json] [--guests RSVP_DB]
    (exit 0 ok, 1 content unreadable, 2 bad usage)
A product record it cannot read is named, exit 1. Hikes today or tomorrow (Pacific) are listed; without a readable
--guests database their guest count is "unavailable", never 0.
Names are shown with spacing collapsed; products sharing a name (case ignored) are listed once, as "Salt (2)".
"""

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from itertools import groupby
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import voice  # noqa: E402
from hass.content_model import CONTENT_DIR, DATE_RE, INVISIBLE_RE, TEXT_LIMITS, ContentError, checked_on, iso_day, load_content, shop_today  # noqa: E402
from hass.ops import hikes  # noqa: E402
from hass.sitegen import STALE_AFTER_DAYS, _day_text, availability_state  # noqa: E402

MAX_NAMES, MAX_CHARS = 10, 1200
UNAVAILABLE = object()  # --guests given but the database could not be read


def _date(text: str) -> date:
    if not DATE_RE.fullmatch(text):
        raise ValueError(text)  # argparse reports a ValueError from a type function as a usage error (exit 2)
    return date.fromisoformat(text)


def _products(content) -> list[dict]:
    """Active product dicts; a record the report cannot read raises ValueError naming its position (from 1)."""
    if not isinstance(content.products, list):
        raise ValueError("products.json: products is not a list")
    limit = TEXT_LIMITS["product"]["name"]
    for n, p in enumerate(content.products, 1):
        name = p.get("name") if isinstance(p, dict) else None
        what = ("not an object" if not isinstance(p, dict) else "" if p.get("status") != "active"  # only active names are shown
                else "name is not text" if not isinstance(name, str) else "name is empty" if not name.strip()
                else "name has a line break or control character" if INVISIBLE_RE.search(name) or {"\u2028", "\u2029"} & set(name)
                else f"name longer than {limit} characters" if len(name) > limit else "")
        if what:
            raise ValueError(f"products.json product {n}: {what}")
    return content.active_products()


def _report_local_parts(starts_at) -> tuple[str, str]:
    """Pacific (date, HH:MM) of an instant with an explicit UTC offset; a start without one raises ValueError."""
    if not isinstance(starts_at, str):
        raise TypeError("start is not text")
    parsed = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:  # date-only or naive: never guess a zone from the host machine
        raise ValueError("start has no UTC offset")
    local = parsed.astimezone(hikes.TZ)
    return local.date().isoformat(), local.strftime("%H:%M")


def _hikes(content, today: date, guests) -> list[dict]:
    """Scheduled hikes starting today or tomorrow (Pacific); confirmed is None unless the guests DB was read (AV1322-06).
    Starts without a UTC offset are skipped. On date.max there is no tomorrow: only today is listed."""
    events, found = content.community.get("events"), []
    window = {today.isoformat()} | ({(today + timedelta(days=1)).isoformat()} if today < date.max else set())
    for e in events if isinstance(events, list) else ():
        try:
            day, clock = _report_local_parts(e["startsAt"]) if e.get("status") == "scheduled" else (None, None)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):  # an unusable start is skipped
            continue
        if day in window:
            cap, eid = (e.get("capacity") if type(e.get("capacity")) is int else None), str(e.get("id", ""))
            found.append({"id": eid, "title": " ".join(str(e.get("title", "")).split()), "day": day, "time": clock,
                          "confirmed": guests.get(eid, 0) if isinstance(guests, dict) else None, "capacity": cap})
    return sorted(found, key=lambda h: (h["day"], h["time"], h["title"].casefold()))


def _hike_text(h: dict, cut: int) -> str:
    title = h["title"] if len(h["title"]) <= cut else h["title"][:cut - 1].rstrip() + "…"
    n, cap, (hh, mm) = h["confirmed"], h["capacity"], map(int, h["time"].split(":"))
    seats = ("I can't see how many guests have signed up" if n is None else f"{n} {'guest has' if n == 1 else 'guests have'} signed up"
             + (f", room for {cap}" if cap is not None else ""))
    when = f"{(hh - 1) % 12 + 1}{':%02d' % mm if mm else ''} {'am' if hh < 12 else 'pm'}"
    return f"{FULL_WEEKDAYS[date.fromisoformat(h['day']).weekday()]} at {when}, {voice.quote(title)} ({seats})"


WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")  # fixed English tables: never the host's locale
FULL_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")  # not strftime %A: that follows LC_TIME
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def restock_day(day) -> str:
    """AV1109-04: a restock day (ISO text or date) as 'Thu Nov 12'. A date-only value has no zone, so its weekday is its own."""
    when = date.fromisoformat(day) if isinstance(day, str) else day
    return f"{WEEKDAYS[when.weekday()]} {MONTHS[when.month - 1]} {when.day}"


def restock_text(name, day) -> str:
    """AV1109-04: the one wording of a restock line, in the report and in the note shown before the owner's yes."""
    return f"{voice.quote(' '.join(str(name).split()))}: more expected {restock_day(day)}"


def _restocks(content, today: date) -> list[dict]:
    """AV1109-04: one entry per active product whose private restock day is today or later (past days are never shown). A
    malformed day on an active product raises ValueError naming its position, like any record the report cannot read."""
    found = []
    for n, p in enumerate(content.products, 1):
        if not isinstance(p, dict) or p.get("status") != "active" or "restock_on" not in p:
            continue
        day = iso_day(p["restock_on"])
        if day is None:
            raise ValueError(f"products.json product {n}: restock_on is not a real date")
        if day >= today:
            found.append({"id": str(p.get("id", "")), "name": " ".join(str(p.get("name", "")).split()), "day": day.isoformat()})
    return sorted(found, key=lambda r: (r["day"], r["name"].casefold(), r["id"]))


def facts(content, today: date, guests=None) -> dict:
    found = _hikes(content, today, guests)
    day = checked_on(content.store)
    names, counts = {"limited": [], "no": []}, {"yes": 0, "limited": 0, "no": 0, "none": 0}
    for p in _products(content):  # hidden and held products never appear
        key = availability_state(p, content.store, today) or "none"  # AV1922-02: the same rule as the cards
        counts[key] += 1
        if key in names:
            names[key].append(" ".join(str(p.get("name", "")).split()))
    future = day is not None and day > today  # a wrong clock or a hand-edited store: never a fresh check
    stale = day is not None and not future and (today - day).days > STALE_AFTER_DAYS
    restocks = _restocks(content, today)
    return {"checked_on": day.isoformat() if day else None, "stale": stale, "future": future,
            "available": counts["yes"], "limited": counts["limited"], "sold_out": counts["no"],
            "not_confirmed": counts["none"], "limited_names": sorted(names["limited"], key=str.casefold),
            "sold_out_names": sorted(names["no"], key=str.casefold)} | ({"hikes": found} if found else {}) \
        | ({"restocks": restocks} if restocks else {})


def check_line(f: dict, stale_tail=None) -> str:
    """The shelf-check sentence from facts(); `stale_tail` is kept for old callers and ignored."""
    day = f["checked_on"]
    if day is None: return "I still need your shelf check."
    when = _day_text(date.fromisoformat(day))
    if f["future"]: return f"Your last shelf check is dated {when}, which is still to come. Please check the date on the computer."
    if f["stale"]: return f"Your last shelf check was {when}. That was more than a week ago, so the website says to call to confirm."
    return f"Your last shelf check was {when}."


def count_line(f: dict) -> str:
    return (f"On the shelves: {f['available']} available, {f['limited']} running low, {f['sold_out']} sold out, "
            f"{f['not_confirmed']} not confirmed.")


def render(f: dict) -> str:
    counts = count_line(f)
    lists = [(label, [g[0] if len(g) == 1 else f"{g[0]} ({len(g)})"  # one entry per shared name, in sorted order
                      for g in (list(v) for _, v in groupby(f[key], key=str.casefold))])
             for label, key in (("Running low", "limited_names"), ("Sold out", "sold_out_names"))]
    hike_list, cuts = f.get("hikes", []), (TEXT_LIMITS["event"]["title"], 40, 20, 8)
    steps = [(MAX_NAMES, c) for c in cuts] + [(cap, cuts[-1]) for cap in range(MAX_NAMES - 1, -1, -1)]
    for cap, cut in steps:  # hike titles cut with … first, then fewer names and hikes, never a longer reply
        lines = [check_line(f), counts]
        for label, found, sep in [(label, found, ", ") for label, found in lists] + [
                ("Hikes", [_hike_text(h, cut) for h in hike_list], "; ")]:
            shown = [voice.quote(x) if label != "Hikes" else x for x in found[:cap]] + ([f"and {len(found) - cap} more"] if len(found) > cap else [])
            lines += [f"{label}: {sep.join(shown)}"] if found else []
        lines.append("These come from your last shelf check, so they are not stock counts.")
        if len(voice.plain("\n".join(lines))) <= MAX_CHARS:
            break
    # AV1109-04: one line per product with a restock day, after the unchanged shelf block; complete, never cut or merged
    return "\n".join(lines + [restock_text(r["name"], r["day"]) for r in f.get("restocks", [])])


def main(argv=None, content_dir: Path = CONTENT_DIR, out=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/morning_report.py", description=__doc__)
    parser.add_argument("--today", type=_date)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--guests", help="RSVP database (read-only) for confirmed guest counts")
    parser.add_argument("--for-g", metavar="STATE", help="HASS-VOICE-1: also print the weekly correspondence line from this state folder (G only; never sent to the owner)")
    args = parser.parse_args(argv)  # a usage error exits 2
    guests = None
    if args.guests is not None:  # unreadable is not exit 1: the shelf part is still good, the hikes say so
        try:
            guests = hikes.guest_counts(args.guests)
        except (sqlite3.Error, OSError, ValueError, TypeError):
            guests = UNAVAILABLE
    try:
        f = facts(load_content(content_dir), args.today or shop_today(), guests)
    except (ContentError, OSError):
        print("morning_report: cannot read content", file=sys.stderr)
        return 1
    except ValueError as exc:  # a product record the report cannot read, named (ContentError is caught above)
        print(f"morning_report: cannot read content ({exc})", file=sys.stderr)
        return 1
    print(json.dumps(f, ensure_ascii=False) if args.json else voice.plain(render(f)), file=out or sys.stdout)
    if args.for_g and not args.json:
        from hass import corrlog  # noqa: E402 - lazily: only G's run reads the log
        print("\n" + corrlog.weekly_line(corrlog.CorrLog(args.for_g, lambda: datetime.now().astimezone())), file=out or sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
