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
# Shelf names as the filter buttons in index.html show them (AV0222-02); a test ties this table to those buttons.
SHELF_LABELS = {"fruit": "Fruit", "vegetables": "Vegetables", "dairy": "Dairy & cheese", "eggs": "Eggs", "meat": "Meat",
                "pantry": "Pantry", "drinks": "Drinks & coffee", "bread": "Bread", "flowers": "Flowers"}

# Public product fields, emitted to catalog-products.js. Records keep their own
# key order (the migrated records use three historical orders; the generator
# preserves each record's order so output stays byte-identical).
PRODUCT_PUBLIC_FIELDS = ("id", "name", "brand", "category", "image", "description", "producerKey", "displayBrand")
PRODUCT_OPTIONAL_PUBLIC = ("imageAlt", "addedOn")  # public when present; never required (any status)
PRODUCT_INTERNAL_FIELDS = ("status", "hold", "available", "available_on",  # owner-set word + its check day (SHOP-1)
                           "restock_on", "labelSource")  # private provenance, never emitted to the site
PRODUCT_STATUSES = ("active", "hidden", "held")
AVAILABILITY = ("yes", "limited", "no")
SHOP_TZ = ZoneInfo("America/Los_Angeles")
HOLD_FIELDS = ("reason", "source", "evidence", "record")

MAKER_FIELDS = ("name", "place", "story", "url")
CLUB_FIELDS = ("clubName", "organizer", "intendedSender", "emailConnected")
CLUB_OPTIONAL = ("showSamples", "intro")  # AV1422-10: false hides the sample hikes; absent = shown. AV2152-09: intro = /hike manifesto
MAX_CLUB_INTRO = 400  # characters in the optional community.club.intro (the /hike opening paragraph; ops/club.py imports this)
DEFAULT_CLUB_INTRO = "A good morning doesn’t need much. Something fresh to eat, a stretch of coast, and time to get to know the people walking beside you."  # shown when club.intro is absent
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
# cancelNote (AV2152-07) is optional one-line text on a cancelled hike; it stays out of EVENT_TEXT_FIELDS, which feeds
# hike.create/update and the hike.repeat copied-text allowlist.
EVENT_OPTIONAL = EVENT_TEXT_FIELDS + ("rsvpEnabled", "capacity", "trailId", "cancelNote")
LINE_SEPARATORS = "\u2028\u2029"  # not caught by INVISIBLE_RE but they break a line like CR/LF
EVENT_STATUSES = ("scheduled", "completed", "cancelled")
PHONE_DIGITS = 10  # US number: area code, exchange, line; LIMITS.md cites it
PHONE_RE = re.compile(rf"[2-9][0-9]{{2}}[2-9][0-9]{{{PHONE_DIGITS - 4}}}", re.ASCII)
STORE_FIELDS = ("schemaVersion", "name", "streetAddress", "town", "hours")
STORE_OPTIONAL = ("selection_checked_on", "intro", "headline", "story", "homeImage", "notice", "phone", "specials", "homeSections", "banner",
                  "pageAbout", "pageGettingHere", "pagePolicies", "pageFaq")  # all absent by default
# AVO-SPECIALS-1: store.specials, a list of weekly specials (absent = none; the saved files do not change).
SPECIAL_FIELDS = ("id", "title", "deal", "start", "end", "order")
SPECIAL_OPTIONAL = ("product", "picture")  # product: an existing product id; picture: true reuses that product's picture
MAX_SPECIALS_AT_ONCE, MAX_SPECIALS_STORED, MAX_SPECIAL_DAYS = 6, 20, 31  # active on one day / kept in the file / start to end
MAX_SPECIAL_TITLE, MAX_SPECIAL_DEAL, MAX_SPECIAL_ORDER = 60, 60, 99
MAX_NOTICE, MAX_NOTICE_DAYS = 160, 60  # store.notice text characters; its last day at most this many days ahead (set)
HOME_IMAGE_RE = re.compile(r"^assets/products/photo-[0-9a-f]{16}\.(jpg|png)$")  # the path photos.install writes
MAX_STORY = 400  # characters in the optional store.story (the "COME ON IN" paragraph)
DEFAULT_STORY = "Michael Wolfe brings a produce buyer’s curiosity and long-standing grower relationships to the Shack. The idea is simple: connect friends and neighbors with good food and the people who grow and make it."  # shown when store.story is absent
MAX_HEADLINE_LINE, DEFAULT_HEADLINE = 40, ("A little market.", "A lot to discover.")  # per line; <h1> when absent
MAX_INTRO = 160  # characters in the optional store.intro (ops/store.py imports this)
DEFAULT_INTRO = "Good food nourishes more than a body. It brings people together."  # shown when store.intro is absent
MAX_HOURS_LINES, MAX_HOURS_LINE, MAX_ADDRESS_PART = 7, 60, 80  # H13 store limits (ops/store.py imports these)
MAX_EVENT_CAPACITY = 1000  # H14 typo guard on events[].capacity (a sanity ceiling, not a business rule; raise if needed)
# Maximum length (Python len: code points, so "é" written as e + combining accent counts 2) of every owner-editable
# text field. Each limit is at least 1.5x the longest current value (test_text_limits checks the real content).
# Store limits are the constants above, listed here so one table documents every limit.
TEXT_LIMITS = {
    "product": {"name": 80, "brand": 60, "displayBrand": 60, "category": 40, "description": 600, "imageAlt": 200},
    "maker": {"name": 80, "place": 60, "story": 600},
    "event": {f: 400 for f in EVENT_TEXT_FIELDS} | {"title": 80, "description": 800, "meetingPoint": 160, "recap": 2000,
              "cancelNote": 160},
    "routeIdea": {f: 600 for f in ROUTE_IDEA_FIELDS if f not in ("id", "sourceUrl", "status", "rsvpEnabled")},
    "club": {f: 400 for f in ("clubName", "organizer", "intendedSender")} | {"intro": MAX_CLUB_INTRO},
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
    # Reader contract: a decoded object key repeated within one object is ambiguous
    # (last-wins would silently flip e.g. hidden -> active), so refuse it by basename only.
    def no_duplicates(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ContentError([f"{path.name}: duplicate JSON object key"])
            out[key] = value
        return out

    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise ContentError([f"{path.name}: not UTF-8 text"]) from None
    try:
        return json.loads(text, object_pairs_hook=no_duplicates)
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


def validate_products(problems, products, makers, site_dir: Path | None, checked: date | None = None):
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
        if "labelSource" in rec:
            from hass.product_claims import valid_source
            if not valid_source(rec["labelSource"]):
                problems.append(f"{where}.labelSource: invalid label provenance")
        if isinstance(category, str) and len(category) > limits["category"]:
            problems.append(f"{where}.category: longer than {limits['category']} characters")
        elif category not in CATEGORIES:
            problems.append(f"{where}: category {category!r} not in {CATEGORIES}")
        image = rec.get("image")
        if not isinstance(image, str) or not IMAGE_RE.fullmatch(image):
            problems.append(f"{where}: image must be assets/products/<file> ({image!r})")
        if "imageAlt" in rec:
            _text(problems, f"{where}.imageAlt", rec["imageAlt"], limit=limits["imageAlt"])
        if "addedOn" in rec:  # AV1622-06: the Pacific day Hass added the product; never in the future
            added = iso_day(rec["addedOn"])
            if added is None:
                problems.append(f"{where}.addedOn: must be a real date YYYY-MM-DD")
            elif added > shop_today():
                problems.append(f"{where}.addedOn: {rec['addedOn']} is in the future")
        if "available" in rec and rec["available"] not in AVAILABILITY:
            problems.append(f"{where}.available: must be one of {AVAILABILITY}")
        if "available_on" in rec and ("available" not in rec or iso_day(rec["available_on"]) is None):
            problems.append(f"{where}.available_on: must be a real date YYYY-MM-DD, set only together with available")
        elif "available_on" in rec and (checked is None or iso_day(rec["available_on"]) > checked):
            problems.append(f"{where}.available_on: {rec['available_on']} is after store.selection_checked_on")
        if "restock_on" in rec and iso_day(rec["restock_on"]) is None:  # AV1109-03: shape only; any past/far day loads
            problems.append(f"{where}.restock_on: must be a real date YYYY-MM-DD")
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
        if not _closed_keys(problems, where, rec, MAKER_FIELDS + ("hidden",), MAKER_FIELDS[:2]):
            continue
        if "hidden" in rec and rec["hidden"] is not True:
            problems.append(f"{where}.hidden: must be true when present")
        for field in ("name", "place", "story"):
            if field == "story" and "story" not in rec:  # AV0222-10: no story is written by leaving story out; a present one stays strict
                continue
            _text(problems, f"{where}.{field}", rec.get(field), limit=TEXT_LIMITS["maker"][field])
        if "url" in rec:  # AV1937-04: no website is written by leaving url out; a present url must still be public https
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
    if _closed_keys(problems, "community.club", club, CLUB_FIELDS + CLUB_OPTIONAL, CLUB_FIELDS):
        for field in ("clubName", "organizer", "intendedSender"):
            _text(problems, f"community.club.{field}", club.get(field), limit=TEXT_LIMITS["club"][field])
        if club.get("emailConnected") is not False:
            problems.append("community.club.emailConnected: email delivery is not connected; must be false")
        if "showSamples" in club and not isinstance(club["showSamples"], bool):
            problems.append("community.club.showSamples: must be true or false")
        if "intro" in club:  # AV2152-09: one paragraph of plain text, 20 letters to MAX_CLUB_INTRO characters
            _text(problems, "community.club.intro", club["intro"], limit=MAX_CLUB_INTRO)
            if isinstance(club["intro"], str) and (sum(c.isalpha() for c in club["intro"]) < 20 or club["intro"].splitlines() != [club["intro"]]):
                problems.append("community.club.intro: needs one paragraph with at least 20 letters")
    ideas = community.get("routeIdeas")
    idea_ids, hidden = set(), []  # hidden: AV1322-03 ideas left out of the generated route list
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
        if idea.get("status") not in ("idea", "hidden"):
            problems.append(f"{where}: status must be 'idea' or 'hidden'")
        elif idea["status"] == "hidden":
            hidden.append(rid)
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
            if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= MAX_EVENT_CAPACITY:
                problems.append(f"{where}: capacity must be a positive integer of at most {MAX_EVENT_CAPACITY}")
        if "trailId" in ev and (not isinstance(ev["trailId"], str) or ev["trailId"] not in idea_ids):
            problems.append(f"{where}: trailId {ev['trailId']!r} is not a route idea")
        elif ev.get("status") == "scheduled" and ev.get("trailId") in hidden:
            problems.append(f"{where}: trailId {ev['trailId']} is hidden")
        for field in EVENT_TEXT_FIELDS:
            if field in ev:
                _text(problems, f"{where}.{field}", ev[field], limit=TEXT_LIMITS["event"][field])
        if "cancelNote" in ev:
            _text(problems, f"{where}.cancelNote", ev["cancelNote"], limit=TEXT_LIMITS["event"]["cancelNote"])
            if isinstance(ev["cancelNote"], str) and any(c in ev["cancelNote"] for c in LINE_SEPARATORS):
                problems.append(f"{where}.cancelNote: must be one line")


def shop_today(now: datetime | None = None) -> date:
    """The shop's calendar date (Pacific) at ``now`` (default: the current time)."""
    return (now or datetime.now(SHOP_TZ)).astimezone(SHOP_TZ).date()


def checked_on(store) -> date | None:
    """The stored selection-check date, or None when absent or not a real YYYY-MM-DD date."""
    return iso_day(store.get("selection_checked_on") if isinstance(store, dict) else None)


def notice_days(notice) -> tuple[date | None, date] | None:
    """AV2152-08: a saved notice's (first day or None for a legacy record, last day), or None when the record is not a
    valid {text, until} / {text, from, until} object. Never compared with today's clock (an expired notice is valid)."""
    if not isinstance(notice, dict) or set(notice) not in ({"text", "until"}, {"text", "from", "until"}) \
            or not isinstance(notice["text"], str):
        return None
    last = iso_day(notice["until"])
    first = iso_day(notice["from"]) if "from" in notice else None
    if last is None or ("from" in notice and (first is None or first > last)):
        return None
    return first, last


def iso_day(value) -> date | None:
    """``value`` as a date when it is a real YYYY-MM-DD string, else None."""
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


SPECIAL_LINK_RE = re.compile(r"https?:|www\.|\b[a-z0-9-]+\.[a-z]{2,24}\b|//|\bdot\s?com\b", re.I)
SPECIAL_EMAIL_RE = re.compile(r"[\w.+-]@|@\s*[A-Za-z]|\b\w+\s+(?:at|\(at\))\s+\w+\s+dot\s+\w+", re.I)  # a real email; "2 @ $5" and "3 @ 2 for $5" price notation is not
SPECIAL_PHONE_RE = re.compile(r"\d(?:[\s().+-]*\d){9,}")  # ten or more DIGITS with only separators between: a phone number (not 10 - 15 - 20 or 2026 - 2027)
SPECIAL_FORBIDDEN = tuple(c for c in FORBIDDEN_TEXT if c != "$") + ("&lt", "&gt", "&#", "&amp")


def special_text_problem(value, *, deal=False) -> str | None:
    """Why a special's title or deal line is not allowed, else None. Both: no markup, links, email or phone
    numbers. Only the deal line may carry a price (``$``); the title may not."""
    if not isinstance(value, str):
        return "must be a string"
    if (m := INVISIBLE_RE.search(value)):
        return f"contains invisible or control character U+{ord(m.group()):04X}"
    if not value.strip() or value != value.strip():
        return "must not be empty or start or end with a space"
    if any(c in value for c in LINE_SEPARATORS):
        return "must be one line"
    if sum(c.isalpha() for c in value) < 3:
        return "needs at least 3 letters"
    for bad in SPECIAL_FORBIDDEN:
        if bad in value:
            return f"contains forbidden text {bad!r}"
    if "$" in value and not deal:
        return "may not contain a price; put it in the deal line"
    if SPECIAL_LINK_RE.search(value):
        return "may not contain a web address"
    if SPECIAL_EMAIL_RE.search(value):
        return "may not contain an email address"
    if SPECIAL_PHONE_RE.search(value):
        return "may not contain a phone number"
    return None


def active_specials(store, today: date | None = None) -> list[dict]:
    """The specials whose first day <= Pacific today <= last day, in show order (order, then title). The one rule
    the page, the preview and the editor all use; an unreadable entry is never active."""
    day = today or shop_today()
    out = []
    for sp in (store.get("specials") if isinstance(store, dict) else None) or []:
        start, end = iso_day(sp.get("start")), iso_day(sp.get("end"))
        if start is not None and end is not None and start <= day <= end:
            out.append(sp)
    return sorted(out, key=lambda sp: (sp.get("order", 0), sp.get("title", ""), sp.get("id", "")))


def validate_specials(problems, specials, product_ids, today: date | None = None):
    """Shape and limits of store.specials. ``product_ids``: every product id (any status) or None to skip that check.
    Active-at-once limit: on no single day from today on may more than MAX_SPECIALS_AT_ONCE be active, so content
    that is valid today cannot become invalid tomorrow. Expired specials are valid and are not counted."""
    if not isinstance(specials, list):
        problems.append("store.specials: must be a list")
        return
    if len(specials) > MAX_SPECIALS_STORED:
        problems.append(f"store.specials: at most {MAX_SPECIALS_STORED} saved (remove the expired ones)")
    seen, spans = set(), []
    for i, sp in enumerate(specials):
        where = f"store.specials[{i}]"
        if not _closed_keys(problems, where, sp, SPECIAL_FIELDS + SPECIAL_OPTIONAL, SPECIAL_FIELDS):
            continue
        sid = sp.get("id")
        if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
            problems.append(f"{where}: invalid id {sid!r}")
        elif sid in seen:
            problems.append(f"{where}: duplicate id {sid}")
        else:
            seen.add(sid)
            where = f"store.specials {sid}"
        for field, limit in (("title", MAX_SPECIAL_TITLE), ("deal", MAX_SPECIAL_DEAL)):
            value = sp.get(field)
            if isinstance(value, str) and len(value) > limit:
                problems.append(f"{where}.{field}: longer than {limit} characters")
            elif (why := special_text_problem(value, deal=field == "deal")):
                problems.append(f"{where}.{field}: {why}")
        start, end = iso_day(sp.get("start")), iso_day(sp.get("end"))
        for field, day in (("start", start), ("end", end)):
            if day is None:
                problems.append(f"{where}.{field}: must be a real date YYYY-MM-DD" + ("; an end date is required" if field == "end" else ""))
        if start is not None and end is not None:
            if end < start:
                problems.append(f"{where}: end date {sp['end']} is before the start date {sp['start']}")
            elif (end - start).days + 1 > MAX_SPECIAL_DAYS:
                problems.append(f"{where}: runs longer than {MAX_SPECIAL_DAYS} days")
            else:
                spans.append((start, end))
        order = sp.get("order")
        if isinstance(order, bool) or not isinstance(order, int) or not 0 <= order <= MAX_SPECIAL_ORDER:
            problems.append(f"{where}.order: must be a whole number 0 to {MAX_SPECIAL_ORDER}")
        if "product" in sp:
            pid = sp["product"]
            if not isinstance(pid, str) or not ID_RE.fullmatch(pid):
                problems.append(f"{where}.product: invalid id")
            elif product_ids is not None and pid not in product_ids:
                problems.append(f"{where}.product: {pid} is not a product")
        if "picture" in sp and (sp["picture"] is not True or "product" not in sp):
            problems.append(f"{where}.picture: only true, and only together with a product")
    day = today or shop_today()
    live = [(max(s, day), e) for s, e in spans if e >= day]  # nothing expired counts
    for start in {s for s, _ in live}:
        if sum(s <= start <= e for s, e in live) > MAX_SPECIALS_AT_ONCE:
            problems.append(f"store.specials: more than {MAX_SPECIALS_AT_ONCE} would be active on {start.isoformat()}")
            break


HOME_SECTIONS = ("market", "our-way", "visit", "newsletter")
BANNER_LINKS = {"visit": "/#visit", "market": "/#market", "hike": "/hike",
                "about": "/about/", "getting-here": "/getting-here/", "policies": "/policies/", "faq": "/faq/"}
BANNER_PAGES = {"about": "pageAbout", "getting-here": "pageGettingHere", "policies": "pagePolicies", "faq": "pageFaq"}
MAX_BANNER, MAX_BANNER_DAYS, MAX_BANNER_AHEAD = 80, 31, 60


def default_sections():
    return [{"id": part, "shown": True} for part in HOME_SECTIONS]


def validate_sections(problems, rows):
    if not isinstance(rows, list) or len(rows) != 4 or any(
            not isinstance(r, dict) or set(r) != {"id", "shown"} or not isinstance(r["id"], str)
            or type(r["shown"]) is not bool for r in rows):
        problems.append("store.homeSections: exactly four id/shown rows are required")
    elif set(r["id"] for r in rows) != set(HOME_SECTIONS):
        problems.append("store.homeSections: each home part must occur exactly once")
    elif any(not r["shown"] and r["id"] in ("market", "visit") for r in rows):
        problems.append("The food list and the visit block always stay on the home page.")


def validate_banner(problems, banner):
    if not _closed_keys(problems, "store.banner", banner, ("text", "start", "end", "link"), ("text", "start", "end")):
        return
    # _closed_keys reports missing required fields but still returns True for an object, so read every field with .get.
    if "text" in banner:
        _text(problems, "store.banner.text", banner["text"], limit=MAX_BANNER)
    text = banner.get("text")
    if isinstance(text, str):
        from hass.live_policy import URL, EMAIL, HANDLE
        if len(text) < 3 or sum(c.isalpha() for c in text) < 3 or len(text.splitlines()) != 1:
            problems.append("The banner needs one line with at least 3 letters.")
        if any(rx.search(text) for rx in (URL, EMAIL, HANDLE)):
            problems.append("The banner cannot contain a web address, email or handle.")
    if "start" in banner and "end" in banner:  # a missing one is already reported by _closed_keys
        start, end = iso_day(banner["start"]), iso_day(banner["end"])
        if start is None or end is None:
            problems.append("The banner needs real dates YYYY-MM-DD.")
        elif end < start or (end - start).days > MAX_BANNER_DAYS:
            problems.append("The banner end must be on or after its start, at most 31 days apart.")
    if "link" in banner and (not isinstance(banner["link"], str) or banner["link"] not in BANNER_LINKS):
        problems.append("The banner link must be one of the shop's own places.")


# Fixed routes only. Each optional value validates independently, including after selective undo.
INFO_PAGES = {"about": ("pageAbout", "About"), "getting-here": ("pageGettingHere", "Getting here"),
              "policies": ("pagePolicies", "Our policies"), "faq": ("pageFaq", "Questions")}


def front_text(problems, where, value, low, high):
    _text(problems, where, value, allow_empty=low == 0, limit=high)
    if isinstance(value, str):
        from hass.live_policy import URL, EMAIL, HANDLE
        from hass.skills.shop import price_problem
        if len(value) < low or len(value.splitlines()) > 1:
            problems.append(f"{where}: needs one line of {low} to {high} characters")
        if any(rx.search(value) for rx in (URL, EMAIL, HANDLE)):
            problems.append("Page words cannot contain a web address, email or handle.")
        if why := price_problem(value):
            problems.append(why)


def validate_page(problems, key, page):
    faq = key == "pageFaq"
    required = ("shown", "title", "entries") if faq else ("shown", "title", "intro", "paragraphs")
    if not _closed_keys(problems, f"store.{key}", page, required + (("intro",) if faq else ()), required):
        return
    if type(page.get("shown")) is not bool:
        problems.append(f"store.{key}.shown: must be true or false")
    front_text(problems, f"store.{key}.title", page.get("title"), 3, 60)
    if not faq or "intro" in page:
        front_text(problems, f"store.{key}.intro", page.get("intro"), 0, 300)
    if faq:
        entries = page.get("entries")
        if not isinstance(entries, list) or len(entries) > 20:
            problems.append("Questions: at most 20 entries are allowed.")
            return
        seen = set()
        for entry in entries:
            if not _closed_keys(problems, "Questions entry", entry, ("q", "a"), ("q", "a")):
                continue
            q = entry.get("q")
            front_text(problems, "Question", q, 5, 120)
            front_text(problems, "Answer", entry.get("a"), 2, 600)
            if isinstance(q, str):
                folded = " ".join(q.casefold().split())
                if not q.endswith("?"):
                    problems.append("A question must end in ?")
                if folded in seen:
                    problems.append("That question occurs more than once.")
                seen.add(folded)
    else:
        paragraphs = page.get("paragraphs")
        if not isinstance(paragraphs, list) or not 1 <= len(paragraphs) <= 6:
            problems.append("A page needs 1 to 6 paragraphs.")
            return
        for paragraph in paragraphs:
            front_text(problems, "Page paragraph", paragraph, 20, 600)


def validate_store(problems, store, today: date | None = None, product_ids=None):
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
    if "story" in store:
        _text(problems, "store.story", store["story"], limit=MAX_STORY)
        if isinstance(store["story"], str) and (sum(c.isalpha() for c in store["story"]) < 20 or len(store["story"].splitlines()) > 1):
            problems.append("store.story: needs one paragraph with at least 20 letters")
    if "headline" in store:
        lines = store["headline"]
        if not isinstance(lines, list) or len(lines) != 2:
            problems.append("store.headline: must be a list of exactly 2 lines")
        for i, line in enumerate(lines if isinstance(lines, list) else []):
            _text(problems, f"store.headline[{i}]", line, limit=MAX_HEADLINE_LINE)
            if isinstance(line, str) and sum(c.isalpha() for c in line) < 2:
                problems.append(f"store.headline[{i}]: needs at least 2 letters")
    if "homeImage" in store:
        home = store["homeImage"]
        if not isinstance(home, dict) or set(home) != {"image", "imageAlt"}:
            problems.append("store.homeImage: must be an object with exactly image and imageAlt")
        elif not isinstance(home["image"], str) or not HOME_IMAGE_RE.fullmatch(home["image"]):
            problems.append("store.homeImage.image: must be assets/products/photo-<16 hex>.<jpg|png>")
        if isinstance(home, dict) and "imageAlt" in home:
            _text(problems, "store.homeImage.imageAlt", home["imageAlt"], limit=TEXT_LIMITS["product"]["imageAlt"])
            if isinstance(home["imageAlt"], str) and sum(c.isalpha() for c in home["imageAlt"]) < 3:
                problems.append("store.homeImage.imageAlt: needs at least 3 letters")
    if "phone" in store and not (isinstance(store["phone"], str) and PHONE_RE.fullmatch(store["phone"])):
        problems.append("store.phone: must be 10 digits")  # AV1222-04: stored as exactly 10 ASCII digits, never coerced
    if "notice" in store:
        notice = store["notice"]
        if not isinstance(notice, dict) or set(notice) not in ({"text", "until"}, {"text", "from", "until"}):
            problems.append("store.notice: must be an object with exactly text and until, or text, from and until")  # AV2152-08
        else:
            _text(problems, "store.notice.text", notice["text"], limit=MAX_NOTICE)
            if isinstance(notice["text"], str) and sum(c.isalpha() for c in notice["text"]) < 3:
                problems.append("store.notice.text: needs at least 3 letters")
            for name in ("from", "until"):
                if name in notice and iso_day(notice[name]) is None:  # a real calendar date
                    problems.append(f"store.notice.{name}: must be a real date YYYY-MM-DD")
            first, last = iso_day(notice.get("from")), iso_day(notice["until"])
            if first and last and first > last:  # never compared with today's clock: expired records must load
                problems.append("store.notice.from: must not be after until")
    for key, _ in INFO_PAGES.values():
        if key in store:
            validate_page(problems, key, store[key])
    if "homeSections" in store:
        validate_sections(problems, store["homeSections"])
    if "banner" in store:
        validate_banner(problems, store["banner"])
    if "specials" in store:
        validate_specials(problems, store["specials"], product_ids, today)
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
    validate_products(problems, content.products, makers, site_dir, checked_on(content.store))
    validate_community(problems, content.community)
    validate_store(problems, content.store, product_ids={p.get("id") for p in content.products if isinstance(p, dict)})
    if problems:
        raise ContentError(problems)


def load_and_validate(content_dir: Path = CONTENT_DIR, site_dir: Path | None = SITE_DIR) -> Content:
    content = load_content(content_dir)
    validate(content, site_dir)
    return content
