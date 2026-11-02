"""Canonical Hass content: loading and validation (H01).

hass/content/*.json is the single editable source for catalog products, maker
profiles, community events/route ideas and store information. The site files
under storefront-mockup/ are generated from it by hass/sitegen.py.

Standard library only. Validation is strict and closed: unknown fields are
rejected, so commerce fields (prices, units, baskets) cannot enter the source.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "hass" / "content"
SITE_DIR = REPO_ROOT / "storefront-mockup"

SCHEMA_VERSION = 1

# Category values offered by the catalog filter buttons in index.html.
CATEGORIES = ("fruit", "vegetables", "dairy", "eggs", "meat", "pantry", "drinks", "bread", "flowers")

# Public product fields, emitted to catalog-products.js. Records keep their own
# key order (the migrated records use three historical orders; the generator
# preserves each record's order so output stays byte-identical).
PRODUCT_PUBLIC_FIELDS = ("id", "name", "brand", "category", "image", "description", "producerKey", "displayBrand")
PRODUCT_OPTIONAL_PUBLIC = ("imageAlt",)  # public when present; never required (any status)
PRODUCT_INTERNAL_FIELDS = ("status", "hold", "available")  # "available": owner-set, absent = not confirmed (SHOP-1)
PRODUCT_STATUSES = ("active", "hidden", "held")
AVAILABILITY = ("yes", "limited", "no")
SHOP_TZ = ZoneInfo("America/Los_Angeles")
HOLD_FIELDS = ("reason", "source", "evidence", "record")

MAKER_FIELDS = ("name", "place", "story", "url")
CLUB_FIELDS = ("clubName", "organizer", "intendedSender", "emailConnected")
ROUTE_IDEA_FIELDS = (
    "id", "title", "place", "character", "distance", "difficulty", "elevation", "elevationLabel",
    "duration", "routeType", "terrain", "description", "sourceUrl", "sourceName", "status", "rsvpEnabled",
)
# Real events (storefront-mockup/README.md "To add a hike"; optional fields are
# the ones community.js / community-server.py read).
EVENT_REQUIRED = ("id", "title", "startsAt", "timezone", "status")
EVENT_TEXT_FIELDS = (
    "meetingPoint", "meetingAddress", "distance", "difficulty", "duration", "description", "recap",
    "meetTime", "walkTime", "returnTime", "invitation", "bring", "accessNote",
)
EVENT_OPTIONAL = EVENT_TEXT_FIELDS + ("rsvpEnabled", "capacity", "trailId")
EVENT_STATUSES = ("scheduled", "completed", "cancelled")
STORE_FIELDS = ("schemaVersion", "name", "streetAddress", "town", "hours")
STORE_OPTIONAL = ("selection_checked_on", "intro")  # ISO date of Michael's last check; home-page intro line; both absent by default
MAX_INTRO = 160  # characters in the optional store.intro (ops/store.py imports this)
DEFAULT_INTRO = "Good food nourishes more than a body. It brings people together."  # shown when store.intro is absent
MAX_HOURS_LINES, MAX_HOURS_LINE, MAX_ADDRESS_PART = 7, 60, 80  # H13 store limits (ops/store.py imports these)
# Maximum length (Python len: code points, so "é" written as e + combining accent counts 2) of every owner-editable
# text field. Each limit is at least 1.5x the longest current value (test_text_limits checks the real content).
# Store limits are the constants above, listed here so one table documents every limit.
TEXT_LIMITS = {
    "product": {"name": 80, "brand": 60, "displayBrand": 60, "category": 40, "description": 600, "imageAlt": 200},
    "maker": {"name": 80, "place": 60, "story": 600},
    "event": {f: 400 for f in EVENT_TEXT_FIELDS} | {"title": 80, "description": 800, "meetingPoint": 160, "recap": 2000},
    "routeIdea": {f: 600 for f in ROUTE_IDEA_FIELDS if f not in ("id", "sourceUrl", "status", "rsvpEnabled")},
    "club": {f: 400 for f in ("clubName", "organizer", "intendedSender")},
    "store": {"streetAddress": MAX_ADDRESS_PART, "town": MAX_ADDRESS_PART, "hoursLine": MAX_HOURS_LINE},
}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
IMAGE_RE = re.compile(r"^assets/products/[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(webp|jpg|jpeg|png)$")
# Exact start time with seconds optional and a mandatory offset (matched in full).
STARTS_AT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Characters never allowed in short display text: markup and currency.
FORBIDDEN_TEXT = ("<", ">", "$", "{{", "}}")
# Control, zero-width and direction-changing characters never allowed in any content text.
INVISIBLE_RE = re.compile("[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")


class ContentError(ValueError):
    """Raised with every validation problem found, one per line."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


@dataclass
class Content:
    products: list[dict]
    makers: dict[str, dict]
    community: dict
    store: dict

    def active_products(self) -> list[dict]:
        return [p for p in self.products if p.get("status") == "active"]


def _read_json(path: Path):
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise ContentError([f"{path.name}: not UTF-8 text"]) from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContentError([f"{path.name}: invalid JSON at line {exc.lineno}"]) from None
    except RecursionError:
        raise ContentError([f"{path.name}: JSON nested too deeply"]) from None


def load_content(content_dir: Path = CONTENT_DIR) -> Content:
    content_dir = Path(content_dir)
    products = _read_json(content_dir / "products.json")
    makers = _read_json(content_dir / "makers.json")
    community = _read_json(content_dir / "community.json")
    store = _read_json(content_dir / "store.json")
    problems: list[str] = []
    for name, doc in (("products.json", products), ("makers.json", makers),
                      ("community.json", community), ("store.json", store)):
        if not isinstance(doc, dict) or doc.get("schemaVersion") != SCHEMA_VERSION:
            problems.append(f"{name}: schemaVersion must be {SCHEMA_VERSION}")
    # products.json and makers.json have closed root envelopes: only the schema
    # version and the payload. Anything else (a stray price or private note) is
    # rejected here rather than silently dropped on extraction.
    for name, doc, payload in (("products.json", products, "products"), ("makers.json", makers, "makers")):
        if isinstance(doc, dict):
            _closed_keys(problems, name, doc, ("schemaVersion", payload), ("schemaVersion", payload))
    if problems:
        raise ContentError(problems)
    return Content(
        products=products.get("products"),
        makers=makers.get("makers"),
        community={k: v for k, v in community.items() if k != "schemaVersion"},
        store=store,
    )


def _text(problems, where, value, *, allow_empty=False, plain=True, limit=None):
    if not isinstance(value, str):
        problems.append(f"{where}: must be a string")
        return
    if limit is not None and len(value) > limit:
        problems.append(f"{where}: longer than {limit} characters")
    if (m := INVISIBLE_RE.search(value)):
        problems.append(f"{where}: contains invisible or control character U+{ord(m.group()):04X}")
    if not allow_empty and not value.strip():
        problems.append(f"{where}: must not be empty")
    if value != value.strip():
        problems.append(f"{where}: leading/trailing whitespace")
    if plain:
        for bad in FORBIDDEN_TEXT:
            if bad in value:
                problems.append(f"{where}: contains forbidden text {bad!r}")


def _https(problems, where, value):
    if not isinstance(value, str) or not value.startswith("https://") or any(c.isspace() for c in value) \
            or any(c in value for c in "<>\"'"):
        problems.append(f"{where}: must be an https:// URL without spaces or quotes")
    elif reason := _not_public(value):
        problems.append(f"{where}: must be a public https:// web address ({reason})")


HOST_RE = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*")  # plain ASCII labels; IDNs must be written as xn--
NUMBER_LABEL_RE = re.compile(r"[0-9]+|0x[0-9a-f]*")  # a browser reads a host ending in one of these as IPv4


def _not_public(value):  # reason an https:// string is not a public web address, else None; never echoes it
    if "\\" in value:  # a browser reads \ as / (so the host ends there); urlsplit keeps it inside the hostname
        return "backslash"
    try:
        parts = urlsplit(value)
    except ValueError:  # bad [IPv6] brackets
        return "no host"
    host = (parts.hostname or "").rstrip(".")
    try:
        port = parts.port
    except ValueError:  # outside 0-65535
        port = 0
    for reason, bad in (("too long", len(value) > 500), ("no host", not host),
                        ("user or password", parts.username is not None or parts.password is not None),
                        ("port", port is not None),
                        ("IP address", ":" in host or NUMBER_LABEL_RE.fullmatch(host.rsplit(".", 1)[-1])),
                        # ^ incl. 127.1, 2130706433, 127.0.0.0x1
                        ("host characters", not HOST_RE.fullmatch(host)),  # %2e, 。, _ etc. a browser may rewrite
                        ("private name", host == "localhost" or host.endswith(
                            (".localhost", ".local", ".internal", ".invalid", ".test", ".example"))),
                        ("host has no dot", "." not in host)):
        if bad:
            return reason


def _closed_keys(problems, where, rec, allowed, required=()):
    if not isinstance(rec, dict):
        problems.append(f"{where}: must be an object")
        return False
    for key in rec:
        if key not in allowed:
            problems.append(f"{where}: unknown field {key!r}")
    for key in required:
        if key not in rec:
            problems.append(f"{where}: missing field {key!r}")
    return True


def validate_products(problems, products, makers, site_dir: Path | None):
    if not isinstance(products, list):
        problems.append("products: must be a list")
        return
    seen = set()
    for i, rec in enumerate(products):
        where = f"products[{i}]"
        if not _closed_keys(problems, where, rec, PRODUCT_PUBLIC_FIELDS + PRODUCT_OPTIONAL_PUBLIC + PRODUCT_INTERNAL_FIELDS,
                            ("id", "name", "brand", "category", "image", "status")):
            continue
        pid = rec.get("id")
        if not isinstance(pid, str) or not ID_RE.fullmatch(pid):
            problems.append(f"{where}: invalid id {pid!r}")
        elif pid in seen:
            problems.append(f"{where}: duplicate id {pid}")
        else:
            seen.add(pid)
            where = f"product {pid}"
        status = rec.get("status")
        if status not in PRODUCT_STATUSES:
            problems.append(f"{where}: status must be one of {PRODUCT_STATUSES}")
        limits = TEXT_LIMITS["product"]
        for field in ("name", "brand"):
            _text(problems, f"{where}.{field}", rec.get(field), limit=limits[field])
        category = rec.get("category")
        if isinstance(category, str) and len(category) > limits["category"]:
            problems.append(f"{where}.category: longer than {limits['category']} characters")
        elif category not in CATEGORIES:
            problems.append(f"{where}: category {category!r} not in {CATEGORIES}")
        image = rec.get("image")
        if not isinstance(image, str) or not IMAGE_RE.fullmatch(image):
            problems.append(f"{where}: image must be assets/products/<file> ({image!r})")
        if "imageAlt" in rec:
            _text(problems, f"{where}.imageAlt", rec["imageAlt"], limit=limits["imageAlt"])
        if "available" in rec and rec["available"] not in AVAILABILITY:
            problems.append(f"{where}.available: must be one of {AVAILABILITY}")
        if status == "held":
            hold = rec.get("hold")
            if _closed_keys(problems, f"{where}.hold", hold, HOLD_FIELDS, ("reason", "source")):
                _text(problems, f"{where}.hold.reason", hold.get("reason"))
                _https(problems, f"{where}.hold.source", hold.get("source"))
                for field in ("evidence", "record"):
                    if field in hold:
                        _text(problems, f"{where}.hold.{field}", hold[field])
            continue
        if "hold" in rec:
            problems.append(f"{where}: 'hold' only allowed on held products")
        # Active and hidden products carry every public field (a hidden product can be restored).
        for field in PRODUCT_PUBLIC_FIELDS:
            if field not in rec:
                problems.append(f"{where}: missing field {field!r}")
        for field in ("description", "displayBrand"):
            _text(problems, f"{where}.{field}", rec.get(field), limit=limits[field])
        key = rec.get("producerKey")
        if key is not None and (not isinstance(key, str) or key not in makers):
            problems.append(f"{where}: producerKey {key!r} is not a maker in makers.json")
        elif status == "active" and key is not None and isinstance(makers[key], dict) \
                and makers[key].get("hidden") is True:
            problems.append(f"{where}: active product names hidden maker {key!r}")
        if status == "active" and site_dir is not None and isinstance(image, str) and IMAGE_RE.fullmatch(image):
            if not (Path(site_dir) / image).is_file():
                problems.append(f"{where}: image file {image} does not exist")


def validate_makers(problems, makers):
    if not isinstance(makers, dict) or not makers:
        problems.append("makers: must be a non-empty object keyed by maker key")
        return
    for key, rec in makers.items():
        where = f"maker {key!r}"
        _text(problems, f"{where} key", key)
        if not _closed_keys(problems, where, rec, MAKER_FIELDS + ("hidden",), MAKER_FIELDS):
            continue
        if "hidden" in rec and rec["hidden"] is not True:
            problems.append(f"{where}.hidden: must be true when present")
        for field in ("name", "place", "story"):
            _text(problems, f"{where}.{field}", rec.get(field), limit=TEXT_LIMITS["maker"][field])
        _https(problems, f"{where}.url", rec.get("url"))


def _offset_datetime(problems, where, value):
    if not isinstance(value, str) or not STARTS_AT_RE.fullmatch(value):
        problems.append(f"{where}: must be an ISO date-time with a UTC offset")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        problems.append(f"{where}: not a valid ISO date-time")
        return None
    return parsed


def validate_community(problems, community):
    if not _closed_keys(problems, "community", community, ("club", "events", "routeIdeas"),
                        ("club", "events", "routeIdeas")):
        return
    club = community.get("club")
    if _closed_keys(problems, "community.club", club, CLUB_FIELDS, CLUB_FIELDS):
        for field in ("clubName", "organizer", "intendedSender"):
            _text(problems, f"community.club.{field}", club.get(field), limit=TEXT_LIMITS["club"][field])
        if club.get("emailConnected") is not False:
            problems.append("community.club.emailConnected: email delivery is not connected; must be false")
    ideas = community.get("routeIdeas")
    idea_ids = set()
    if not isinstance(ideas, list):
        problems.append("community.routeIdeas: must be a list")
        ideas = []
    for i, idea in enumerate(ideas):
        where = f"routeIdeas[{i}]"
        if not _closed_keys(problems, where, idea, ROUTE_IDEA_FIELDS, ROUTE_IDEA_FIELDS):
            continue
        rid = idea.get("id")
        if not isinstance(rid, str) or not ID_RE.fullmatch(rid) or rid in idea_ids:
            problems.append(f"{where}: invalid or duplicate id {rid!r}")
        else:
            idea_ids.add(rid)
        for field in ROUTE_IDEA_FIELDS:
            if field not in ("sourceUrl", "status", "rsvpEnabled", "id"):
                _text(problems, f"{where}.{field}", idea.get(field), limit=TEXT_LIMITS["routeIdea"][field])
        _https(problems, f"{where}.sourceUrl", idea.get("sourceUrl"))
        # Route ideas are undated suggestions; they never take RSVPs.
        if idea.get("status") != "idea":
            problems.append(f"{where}: status must be 'idea'")
        if idea.get("rsvpEnabled") is not False:
            problems.append(f"{where}: rsvpEnabled must be false for a route idea")
    events = community.get("events")
    if not isinstance(events, list):
        problems.append("community.events: must be a list")
        return
    event_ids = set()
    for i, ev in enumerate(events):
        where = f"events[{i}]"
        if not _closed_keys(problems, where, ev, EVENT_REQUIRED + EVENT_OPTIONAL, EVENT_REQUIRED):
            continue
        eid = ev.get("id")
        if not isinstance(eid, str) or not ID_RE.fullmatch(eid) or eid in event_ids or eid in idea_ids:
            problems.append(f"{where}: invalid or duplicate id {eid!r}")
        else:
            event_ids.add(eid)
        if isinstance(eid, str) and eid.startswith(("preview-", "idea-")):
            problems.append(f"{where}: sample/route-idea ids cannot become real events")
        _text(problems, f"{where}.title", ev.get("title"), limit=TEXT_LIMITS["event"]["title"])
        starts = _offset_datetime(problems, f"{where}.startsAt", ev.get("startsAt"))
        if ev.get("timezone") != "America/Los_Angeles":
            problems.append(f"{where}: timezone must be America/Los_Angeles")
        elif starts is not None:
            try:
                local = starts.astimezone(ZoneInfo("America/Los_Angeles"))
            except OverflowError:  # e.g. year 1 or 9999 near the datetime range limit
                local = None
                problems.append(f"{where}.startsAt: {ev.get('startsAt')!r} is outside the supported date range")
            if local is not None and starts.utcoffset() != local.utcoffset():  # %:z shows Z as +00:00
                problems.append(f"{where}.startsAt: offset {starts.strftime('%:z')} is not Pacific time on "
                                f"{local.date().isoformat()} (expected {local.strftime('%:z')})")
        if ev.get("status") not in EVENT_STATUSES:
            problems.append(f"{where}: status must be one of {EVENT_STATUSES}")
        if "rsvpEnabled" in ev and not isinstance(ev["rsvpEnabled"], bool):
            problems.append(f"{where}: rsvpEnabled must be true or false")
        if ev.get("rsvpEnabled") is True:
            _text(problems, f"{where}.meetingPoint", ev.get("meetingPoint"))
        if "capacity" in ev:
            cap = ev["capacity"]
            if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
                problems.append(f"{where}: capacity must be a positive integer")
        if "trailId" in ev and (not isinstance(ev["trailId"], str) or ev["trailId"] not in idea_ids):
            problems.append(f"{where}: trailId {ev['trailId']!r} is not a route idea")
        for field in EVENT_TEXT_FIELDS:
            if field in ev:
                _text(problems, f"{where}.{field}", ev[field], limit=TEXT_LIMITS["event"][field])


def shop_today(now: datetime | None = None) -> date:
    """The shop's calendar date (Pacific) at ``now`` (default: the current time)."""
    return (now or datetime.now(SHOP_TZ)).astimezone(SHOP_TZ).date()


def checked_on(store) -> date | None:
    """The stored selection-check date, or None when absent or not a real YYYY-MM-DD date."""
    value = store.get("selection_checked_on") if isinstance(store, dict) else None
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate_store(problems, store, today: date | None = None):
    if not _closed_keys(problems, "store", store, STORE_FIELDS + STORE_OPTIONAL, STORE_FIELDS):
        return
    if "selection_checked_on" in store:
        day = checked_on(store)
        if day is None:
            problems.append("store.selection_checked_on: must be a real date YYYY-MM-DD")
        elif day > (today or shop_today()):
            problems.append(f"store.selection_checked_on: {day.isoformat()} is in the future")
    if "intro" in store:
        _text(problems, "store.intro", store["intro"], limit=MAX_INTRO)
        if isinstance(store["intro"], str) and sum(c.isalpha() for c in store["intro"]) < 3:
            problems.append("store.intro: needs at least 3 letters")
    for field in ("name", "streetAddress", "town"):
        _text(problems, f"store.{field}", store.get(field))
    for field in ("streetAddress", "town"):
        if isinstance(store.get(field), str) and len(store[field]) > MAX_ADDRESS_PART:
            problems.append(f"store.{field}: longer than {MAX_ADDRESS_PART} characters")
    hours = store.get("hours")
    if not isinstance(hours, list) or not hours:
        problems.append("store.hours: must be a non-empty list of lines")
        return
    if len(hours) > MAX_HOURS_LINES:
        problems.append(f"store.hours: at most {MAX_HOURS_LINES} lines")
    for i, line in enumerate(hours):
        _text(problems, f"store.hours[{i}]", line)
        if isinstance(line, str) and len(line) > MAX_HOURS_LINE:
            problems.append(f"store.hours[{i}]: longer than {MAX_HOURS_LINE} characters")
        if isinstance(line, str) and line in hours[:i]:
            problems.append(f"store.hours[{i}]: repeats an earlier line")


def validate(content: Content, site_dir: Path | None = SITE_DIR) -> None:
    """Raise ContentError listing every problem; return None when valid."""
    problems: list[str] = []
    makers = content.makers if isinstance(content.makers, dict) else {}
    validate_makers(problems, content.makers)
    validate_products(problems, content.products, makers, site_dir)
    validate_community(problems, content.community)
    validate_store(problems, content.store)
    if problems:
        raise ContentError(problems)


def load_and_validate(content_dir: Path = CONTENT_DIR, site_dir: Path | None = SITE_DIR) -> Content:
    content = load_content(content_dir)
    validate(content, site_dir)
    return content
