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
from datetime import datetime
from pathlib import Path

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
PRODUCT_INTERNAL_FIELDS = ("status", "hold")
PRODUCT_STATUSES = ("active", "hidden", "held")
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

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
IMAGE_RE = re.compile(r"^assets/products/[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(webp|jpg|jpeg|png)$")
# Exact start time with seconds optional and a mandatory offset (matched in full).
STARTS_AT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})")
# Characters never allowed in short display text: markup and currency.
FORBIDDEN_TEXT = ("<", ">", "$", "{{", "}}")


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
    with path.open("r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            raise ContentError([f"{path.name}: invalid JSON at line {exc.lineno}"]) from None


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


def _text(problems, where, value, *, allow_empty=False, plain=True):
    if not isinstance(value, str):
        problems.append(f"{where}: must be a string")
        return
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
        if not _closed_keys(problems, where, rec, PRODUCT_PUBLIC_FIELDS + PRODUCT_INTERNAL_FIELDS,
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
        for field in ("name", "brand"):
            _text(problems, f"{where}.{field}", rec.get(field))
        if rec.get("category") not in CATEGORIES:
            problems.append(f"{where}: category {rec.get('category')!r} not in {CATEGORIES}")
        image = rec.get("image")
        if not isinstance(image, str) or not IMAGE_RE.fullmatch(image):
            problems.append(f"{where}: image must be assets/products/<file> ({image!r})")
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
        _text(problems, f"{where}.description", rec.get("description"))
        _text(problems, f"{where}.displayBrand", rec.get("displayBrand"))
        key = rec.get("producerKey")
        if key is not None and (not isinstance(key, str) or key not in makers):
            problems.append(f"{where}: producerKey {key!r} is not a maker in makers.json")
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
        if not _closed_keys(problems, where, rec, MAKER_FIELDS, MAKER_FIELDS):
            continue
        for field in ("name", "place", "story"):
            _text(problems, f"{where}.{field}", rec.get(field))
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


def validate_community(problems, community):
    if not _closed_keys(problems, "community", community, ("club", "events", "routeIdeas"),
                        ("club", "events", "routeIdeas")):
        return
    club = community.get("club")
    if _closed_keys(problems, "community.club", club, CLUB_FIELDS, CLUB_FIELDS):
        for field in ("clubName", "organizer", "intendedSender"):
            _text(problems, f"community.club.{field}", club.get(field))
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
                _text(problems, f"{where}.{field}", idea.get(field))
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
        _text(problems, f"{where}.title", ev.get("title"))
        _offset_datetime(problems, f"{where}.startsAt", ev.get("startsAt"))
        if ev.get("timezone") != "America/Los_Angeles":
            problems.append(f"{where}: timezone must be America/Los_Angeles")
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
                _text(problems, f"{where}.{field}", ev[field])


def validate_store(problems, store):
    if not _closed_keys(problems, "store", store, STORE_FIELDS, STORE_FIELDS):
        return
    for field in ("name", "streetAddress", "town"):
        _text(problems, f"store.{field}", store.get(field))
    hours = store.get("hours")
    if not isinstance(hours, list) or not hours:
        problems.append("store.hours: must be a non-empty list of lines")
        return
    for i, line in enumerate(hours):
        _text(problems, f"store.hours[{i}]", line)


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
