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
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.content_model import CONTENT_DIR, DATE_RE, INVISIBLE_RE, TEXT_LIMITS, ContentError, checked_on, load_content, shop_today  # noqa: E402
from hass.ops import hikes  # noqa: E402
from hass.sitegen import STALE_AFTER_DAYS, _day_text  # noqa: E402

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


def _hikes(content, today: date, guests) -> list[dict]:
    """Scheduled hikes starting today or tomorrow (Pacific); confirmed is None unless the guests DB was read (AV1322-06)."""
    events, found = content.community.get("events"), []
    for e in events if isinstance(events, list) else ():
        try:
            day, clock = hikes._local_parts(e["startsAt"]) if e.get("status") == "scheduled" else (None, None)
        except (KeyError, TypeError, ValueError, AttributeError):  # an unparseable start is skipped
            continue
        if day in (today.isoformat(), (today + timedelta(days=1)).isoformat()):
            cap, eid = (e.get("capacity") if type(e.get("capacity")) is int else None), str(e.get("id", ""))
            found.append({"id": eid, "title": " ".join(str(e.get("title", "")).split()), "day": day, "time": clock,
                          "confirmed": guests.get(eid, 0) if isinstance(guests, dict) else None, "capacity": cap})
    return sorted(found, key=lambda h: (h["day"], h["time"], h["title"].casefold()))


def _hike_text(h: dict, cut: int) -> str:
    title = h["title"] if len(h["title"]) <= cut else h["title"][:cut - 1].rstrip() + "…"
    n, cap, (hh, mm) = h["confirmed"], h["capacity"], map(int, h["time"].split(":"))
    seats = ("guest count unavailable" if n is None else f"{n} of {cap} confirmed" if cap is not None else f"{n} confirmed")
    return f"{date.fromisoformat(h['day']):%A} {(hh - 1) % 12 + 1}:{mm:02d} {'am' if hh < 12 else 'pm'} {title} ({seats})"


def facts(content, today: date, guests=None) -> dict:
    found = _hikes(content, today, guests)
    day = checked_on(content.store)
    names, counts = {"limited": [], "no": []}, {"yes": 0, "limited": 0, "no": 0, "none": 0}
    for p in _products(content):  # hidden and held products never appear
        fresh = day is not None and p.get("available_on") == day.isoformat()  # AV1102-01: confirmed on the latest check
        key = p.get("available") if fresh and p.get("available") in ("yes", "limited", "no") else "none"
        counts[key] += 1
        if key in names:
            names[key].append(" ".join(str(p.get("name", "")).split()))
    future = day is not None and day > today  # a wrong clock or a hand-edited store: never a fresh check
    stale = day is not None and not future and (today - day).days > STALE_AFTER_DAYS
    return {"checked_on": day.isoformat() if day else None, "stale": stale, "future": future,
            "available": counts["yes"], "limited": counts["limited"], "sold_out": counts["no"],
            "not_confirmed": counts["none"], "limited_names": sorted(names["limited"], key=str.casefold),
            "sold_out_names": sorted(names["no"], key=str.casefold)} | ({"hikes": found} if found else {})


def check_line(f: dict, stale_tail: str = " - more than a week ago") -> str:
    """The 'Shelf check: ...' line from facts(); `status` passes its own stale tail (AV1102-05)."""
    day = f["checked_on"]
    head = "Shelf check: not done yet" if day is None else f"Shelf check: {_day_text(date.fromisoformat(day))}"
    return head + (" - dated after today, check the clock" if f["future"] else stale_tail if f["stale"] else "")


def render(f: dict) -> str:
    counts = f"Available {f['available']} · Limited {f['limited']} · Sold out {f['sold_out']} · Not confirmed {f['not_confirmed']}"
    lists = [(label, [g[0] if len(g) == 1 else f"{g[0]} ({len(g)})"  # one entry per shared name, in sorted order
                      for g in (list(v) for _, v in groupby(f[key], key=str.casefold))])
             for label, key in (("Limited", "limited_names"), ("Sold out", "sold_out_names"))]
    hike_list, cuts = f.get("hikes", []), (TEXT_LIMITS["event"]["title"], 40, 20, 8)
    steps = [(MAX_NAMES, c) for c in cuts] + [(cap, cuts[-1]) for cap in range(MAX_NAMES - 1, -1, -1)]
    for cap, cut in steps:  # hike titles cut with … first, then fewer names and hikes, never a longer reply
        lines = [check_line(f), counts]
        for label, found, sep in [(label, found, ", ") for label, found in lists] + [
                ("Hikes", [_hike_text(h, cut) for h in hike_list], "; ")]:
            shown = found[:cap] + ([f"+{len(found) - cap} more"] if len(found) > cap else [])
            lines += [f"{label}: {sep.join(shown)}"] if found else []
        lines.append("These are your last shelf checks, not stock counts.")
        if len("\n".join(lines)) <= MAX_CHARS:
            break
    return "\n".join(lines)


def main(argv=None, content_dir: Path = CONTENT_DIR, out=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/morning_report.py", description=__doc__)
    parser.add_argument("--today", type=_date)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--guests", help="RSVP database (read-only) for confirmed guest counts")
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
    print(json.dumps(f, ensure_ascii=False) if args.json else render(f), file=out or sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
