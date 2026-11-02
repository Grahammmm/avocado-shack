"""Morning shelf report from the owner's last confirmed availability (AVB-23): never stock counts. Read-only.
    python3 hass/morning_report.py [--today YYYY-MM-DD] [--json]     (exit 0 ok, 1 content unreadable, 2 bad usage)
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.content_model import CONTENT_DIR, DATE_RE, ContentError, checked_on, load_content, shop_today  # noqa: E402
from hass.sitegen import STALE_AFTER_DAYS, _day_text  # noqa: E402

MAX_NAMES, MAX_CHARS = 10, 1200


def _date(text: str) -> date:
    if not DATE_RE.fullmatch(text):
        raise ValueError(text)  # argparse reports a ValueError from a type function as a usage error (exit 2)
    return date.fromisoformat(text)


def facts(content, today: date) -> dict:
    day = checked_on(content.store)
    names, counts = {"limited": [], "no": []}, {"yes": 0, "limited": 0, "no": 0, "none": 0}
    for p in content.active_products():  # hidden and held products never appear
        key = p.get("available") if day is not None and p.get("available") in ("yes", "limited", "no") else "none"  # no check: none confirmed
        counts[key] += 1
        if key in names:
            names[key].append(str(p.get("name", "")).strip())
    return {"checked_on": day.isoformat() if day else None, "stale": day is not None and (today - day).days > STALE_AFTER_DAYS,
            "available": counts["yes"], "limited": counts["limited"], "sold_out": counts["no"],
            "not_confirmed": counts["none"], "limited_names": sorted(names["limited"], key=str.casefold),
            "sold_out_names": sorted(names["no"], key=str.casefold)}


def render(f: dict) -> str:
    day = f["checked_on"]
    head = "Shelf check: not done yet" if day is None else f"Shelf check: {_day_text(date.fromisoformat(day))}"
    counts = f"Available {f['available']} · Limited {f['limited']} · Sold out {f['sold_out']} · Not confirmed {f['not_confirmed']}"
    for cap in range(MAX_NAMES, -1, -1):  # fewer names, never a longer reply, when names are long
        lines = [head + (" - more than a week ago" if f["stale"] else ""), counts]
        for label, found in (("Limited", f["limited_names"]), ("Sold out", f["sold_out_names"])):
            shown = found[:cap] + ([f"+{len(found) - cap} more"] if len(found) > cap else [])
            lines += [f"{label}: {', '.join(shown)}"] if found else []
        lines.append("These are your last shelf checks, not stock counts.")
        if len("\n".join(lines)) <= MAX_CHARS:
            break
    return "\n".join(lines)


def main(argv=None, content_dir: Path = CONTENT_DIR, out=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/morning_report.py", description=__doc__)
    parser.add_argument("--today", type=_date)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)  # a usage error exits 2
    try:
        f = facts(load_content(content_dir), args.today or shop_today())
    except (ContentError, OSError):
        print("morning_report: cannot read content", file=sys.stderr)
        return 1
    print(json.dumps(f, ensure_ascii=False) if args.json else render(f), file=out or sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
