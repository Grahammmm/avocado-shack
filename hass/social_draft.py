"""Local Instagram post draft from one product photo (AVB-22), or one hike announcement (F07 "prepare" half only).

    python3 hass/social_draft.py PRODUCT_ID
    python3 hass/social_draft.py --hike EVENT_ID
    python3 hass/social_draft.py --maker KEY
    python3 hass/social_draft.py --recap EVENT_ID

Prints one JSON object. Success: {"draft": true, "image", "alt", "caption"} built only from the product's
stored name, description, image, imageAlt and its maker's name and place (caption <= 2200 characters, at most
5 hashtags: #AvocadoShack plus one fixed tag per category, never derived from free text). Refusal (exit 1):
{"draft": false, "reason"}: "cannot read content" | "no such product" | "not on the site" | "no photo on the site" |
"product record incomplete" (name/description not non-empty text, or blank, or a line break/control character
where one line is expected; the description may hold a plain \\n) | "free text has a hashtag or account name" (a # or @
(full-width and small-form # and @ too) followed by a letter, digit or _ in name, description or maker name/place; nothing is stripped) | "caption too long".
A malformed maker (incl. blank or control-character name/place) is no maker. A non-text, empty, multi-line,
control-character or tagged imageAlt is not used (alt = name); a products
list that is not a list of records is 'cannot read content'.
--hike prints {"draft": true, "caption"}: title, Pacific weekday date and time, meeting point, linked route idea title,
then fixed #AvocadoShack #NorthCoastHikingClub. Refusal (exit 1): "cannot read content" | "no such hike" | "hike is
cancelled" | "hike already happened" (completed, or start before now) | "not scheduled" | "hike record incomplete"
(title/meeting point not one line, start unreadable) | "free text has a hashtag or account name" | "caption too long".
--maker prints {"draft": true, "caption"}: "Meet the maker: <name>", "Based in <place>.", the stored story verbatim, the count of the
maker's active products, then fixed #AvocadoShack #MeetTheMaker (no photo, url or derived text). Refusal (exit 1): "cannot read content" |
"no such maker" (exact, case-sensitive key) | "not on the site" (hidden maker) | "no active products" | "maker record incomplete"
(name/place not one line, story not text) | "free text has a hashtag or account name" | "caption too long".
--recap prints {"draft": true, "caption"}: title, Pacific weekday date with year (no time), the owner's saved recap of a completed hike
verbatim, then fixed #AvocadoShack #NorthCoastHikingClub. No people count, route or meeting point is added. A recap too long for the
caption is cut after its last ".", "!" or "?" (followed by white space or the end) that fits; never mid-sentence, never an ellipsis.
Refusal (exit 1): "cannot read content" | "no such hike" | "say how it went first" (not completed, or no recap) | "hike record
incomplete" (title not one line, recap not text, start unreadable) | "free text has a hashtag or account name" (title or any part of
the recap, also the part cut off) | "caption too long".
Read-only: nothing is posted, scheduled, written or sent, and the module imports no network code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.content_model import CATEGORIES, CONTENT_DIR, INVISIBLE_RE, SITE_DIR, ContentError, load_content  # noqa: E402
from hass.ops import hikes  # noqa: E402

MAX_CAPTION = 2200
HIKE_TAGS = "#AvocadoShack #NorthCoastHikingClub"  # fixed; never from free text
MAKER_TAGS = "#AvocadoShack #MeetTheMaker"  # fixed; never from free text
CATEGORY_TAGS = {c: "#" + c.capitalize() for c in CATEGORIES}  # fixed per category; never from free text
# a hashtag or @account in free text is refused, never rewritten; marks: # @, full-width U+FF03 U+FF20, small-form U+FE5F U+FE6B
_TAG_RE = re.compile(r"[#@\uFF03\uFF20\uFE5F\uFE6B]\w")


def _block(v) -> bool:  # non-blank text; a plain \n is its only allowed line break or control character
    return isinstance(v, str) and bool(v.strip()) and not INVISIBLE_RE.search(v.replace("\n", "")) and not {"\u2028", "\u2029"} & set(v)


def _line(v) -> bool:  # one line of text: as _block, and no \n either (INVISIBLE_RE covers \n and \r)
    return _block(v) and "\n" not in v


def _photo_ok(image, site_dir: Path) -> bool:
    if not isinstance(image, str) or not image: return False  # absent, null or non-text image: checked before any path
    try:
        path = (site_dir / image).resolve()
        return path.is_relative_to(site_dir.resolve()) and path.is_file()
    except (OSError, ValueError):
        return False


def build(content, product_id: str, site_dir: Path = SITE_DIR) -> dict:
    """Return the draft dict, or {"draft": False, "reason": ...}. The id is only matched against loaded products."""
    def refuse(reason): return {"draft": False, "reason": reason}
    if not isinstance(content.products, list) or not all(isinstance(p, dict) for p in content.products):
        return refuse("cannot read content")
    product = next((p for p in content.products if p.get("id") == product_id), None)
    if product is None: return refuse("no such product")
    if product.get("status") != "active": return refuse("not on the site")
    if not _photo_ok(product.get("image"), Path(site_dir)): return refuse("no photo on the site")
    name, description = product.get("name"), product.get("description")
    if not (_line(name) and _block(description)): return refuse("product record incomplete")
    makers = content.makers if isinstance(content.makers, dict) else {}
    maker = makers.get(product.get("producerKey")) if isinstance(product.get("producerKey"), str) else None
    if not (isinstance(maker, dict) and _line(maker.get("name")) and _line(maker.get("place"))): maker = None
    free = [name, description, *((maker["name"], maker["place"]) if maker else ())]
    if any(_TAG_RE.search(text) for text in free): return refuse("free text has a hashtag or account name")
    lines = [name, description]
    if maker: lines.append(f"From {maker['name']} in {maker['place']}.")
    category = product.get("category")  # only a text member of CATEGORY_TAGS adds a tag; a list or object is as unknown as null
    tags = ["#AvocadoShack", *([CATEGORY_TAGS[category]] if isinstance(category, str) and category in CATEGORY_TAGS else [])]
    caption = "\n".join(lines) + "\n\n" + " ".join(tags)
    if len(caption) > MAX_CAPTION: return refuse("caption too long")
    alt = product.get("imageAlt")
    alt = alt if _line(alt) and not _TAG_RE.search(alt) else name
    return {"draft": True, "image": product["image"], "alt": alt, "caption": caption}


def _when(starts_at):  # (aware start, "Saturday, October 17 at 9:00 am (Pacific)"), or None when unreadable
    try: start, (day, clock) = datetime.fromisoformat(starts_at.replace("Z", "+00:00")), hikes._local_parts(starts_at)
    except (AttributeError, TypeError, ValueError, OverflowError): return None
    d, h = date.fromisoformat(day), int(clock[:2])
    return (start, f"{d:%A, %B} {d.day} at {h % 12 or 12}{clock[2:]} {'am' if h < 12 else 'pm'} (Pacific)") if start.tzinfo else None


def build_hike(content, event_id: str, now: datetime) -> dict:
    """Return {"draft": True, "caption"} for one scheduled future hike, or {"draft": False, "reason": ...}."""
    def refuse(reason): return {"draft": False, "reason": reason}
    community = content.community if isinstance(content.community, dict) else {}
    events, ideas = community.get("events"), community.get("routeIdeas")
    if not isinstance(events, list) or not all(isinstance(e, dict) for e in events): return refuse("cannot read content")
    hike = next((e for e in events if e.get("id") == event_id), None)
    if hike is None: return refuse("no such hike")
    when, status = _when(hike.get("startsAt")), hike.get("status")
    if status == "cancelled": return refuse("hike is cancelled")
    if status == "completed" or (when and when[0] < now): return refuse("hike already happened")
    if status != "scheduled": return refuse("not scheduled")
    if not (when and _line(title := hike.get("title")) and _line(meet := hike.get("meetingPoint"))): return refuse("hike record incomplete")
    trail = hike.get("trailId") if isinstance(ideas, list) else None
    idea = next((i for i in ideas if isinstance(i, dict) and i.get("id") == trail), None) if isinstance(trail, str) else None
    route = idea.get("title") if idea and _line(idea.get("title")) else None
    if any(_TAG_RE.search(t) for t in (title, meet, route or "")): return refuse("free text has a hashtag or account name")
    caption = "\n".join([title, when[1], f"Meet at {meet}.", *([f"Route: {route}."] if route else [])]) + "\n\n" + HIKE_TAGS
    return refuse("caption too long") if len(caption) > MAX_CAPTION else {"draft": True, "caption": caption}


def _day(starts_at):  # "Saturday, October 17, 2026 (Pacific)" for the Pacific calendar day of an aware start, else None
    try: aware, (day, _clock) = datetime.fromisoformat(starts_at.replace("Z", "+00:00")).tzinfo, hikes._local_parts(starts_at)
    except (AttributeError, TypeError, ValueError, OverflowError): return None
    d = date.fromisoformat(day)
    return f"{d:%A, %B} {d.day}, {d.year} (Pacific)" if aware else None


def build_recap(content, event_id: str) -> dict:
    """Return {"draft": True, "caption"} for one completed hike with a saved recap, or {"draft": False, "reason": ...}.
    The recap is the owner's own saved text: only cut (after a sentence end) when the caption would pass MAX_CAPTION."""
    def refuse(reason): return {"draft": False, "reason": reason}
    community = content.community if isinstance(getattr(content, "community", None), dict) else {}
    events = community.get("events")
    if not isinstance(events, list) or not all(isinstance(e, dict) for e in events): return refuse("cannot read content")
    hike = next((e for e in events if e.get("id") == event_id), None)
    if hike is None: return refuse("no such hike")
    recap = hike.get("recap")
    if hike.get("status") != "completed" or recap is None or (isinstance(recap, str) and not recap.strip()): return refuse("say how it went first")
    title, day = hike.get("title"), _day(hike.get("startsAt"))
    if not (_block(recap) and _line(title) and day): return refuse("hike record incomplete")
    if any(_TAG_RE.search(t) for t in (title, recap)): return refuse("free text has a hashtag or account name")
    head, tail = f"{title}\n{day}\n", "\n\n" + HIKE_TAGS
    room = MAX_CAPTION - len(head) - len(tail)
    if len(recap) > room:  # the longest prefix that ends a sentence (. ! ? then white space or the end) and fits
        ends = [i + 1 for i, c in enumerate(recap) if c in ".!?" and i + 1 <= room and (i + 1 == len(recap) or recap[i + 1].isspace())]
        if not ends: return refuse("caption too long")
        recap = recap[:max(ends)]
    return {"draft": True, "caption": head + recap + tail}


def build_maker(content, maker_key: str) -> dict:
    """Return {"draft": True, "caption"} for one visible maker with active products, or {"draft": False, "reason": ...}."""
    def refuse(reason): return {"draft": False, "reason": reason}
    makers, products = content.makers, content.products
    if not isinstance(makers, dict) or not isinstance(products, list) or not all(isinstance(p, dict) for p in products):
        return refuse("cannot read content")
    if maker_key not in makers: return refuse("no such maker")
    maker = makers[maker_key]
    if not isinstance(maker, dict): return refuse("maker record incomplete")
    if maker.get("hidden") is True: return refuse("not on the site")
    count = sum(1 for p in products if p.get("producerKey") == maker_key and p.get("status") == "active")
    if count == 0: return refuse("no active products")
    name, place, story = maker.get("name"), maker.get("place"), maker.get("story")
    if not (_line(name) and _line(place) and _block(story)): return refuse("maker record incomplete")
    if any(_TAG_RE.search(t) for t in (name, place, story)): return refuse("free text has a hashtag or account name")
    total = f"{count} active product on our site." if count == 1 else f"{count} active products on our site."
    caption = f"Meet the maker: {name}\nBased in {place}.\n{story}\n{total}\n\n{MAKER_TAGS}"
    return refuse("caption too long") if len(caption) > MAX_CAPTION else {"draft": True, "caption": caption}


def main(argv=None, content_dir: Path = CONTENT_DIR, site_dir: Path = SITE_DIR) -> int:
    parser = argparse.ArgumentParser(description="Print a local DRAFT Instagram post for one active product or hike, or a maker introduction (posts nothing).")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("product_id", nargs="?")
    which.add_argument("--hike", metavar="ID")
    which.add_argument("--maker", metavar="KEY")
    which.add_argument("--recap", metavar="ID")
    parser.add_argument("--now", type=lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)  # --now: tests only
    try: content = load_content(content_dir)
    except (ContentError, OSError): content = None  # missing or invalid content: one JSON refusal, never a traceback
    if content is None: result = {"draft": False, "reason": "cannot read content"}
    elif args.maker is not None: result = build_maker(content, args.maker)
    elif args.recap is not None: result = build_recap(content, args.recap)
    elif args.hike is not None: result = build_hike(content, args.hike, args.now or datetime.now(timezone.utc))
    else: result = build(content, args.product_id, site_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["draft"] else 1


if __name__ == "__main__":
    sys.exit(main())
