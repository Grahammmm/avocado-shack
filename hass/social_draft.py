"""Local Instagram post draft from one product photo (AVB-22, F07 "prepare" half only).

    python3 hass/social_draft.py PRODUCT_ID

Prints one JSON object. Success: {"draft": true, "image", "alt", "caption"} built only from the product's
stored name, description, image, imageAlt and its maker's name and place (caption <= 2200 characters, at most
5 hashtags: #AvocadoShack plus one fixed tag per category, never derived from free text). Refusal (exit 1):
{"draft": false, "reason"}: "cannot read content" | "no such product" | "not on the site" | "no photo on the site" |
"product record incomplete" (name/description not non-empty text, or blank, or a line break/control character
where one line is expected; the description may hold a plain \\n) | "free text has a hashtag or account name" (a # or @
followed by a letter, digit or _ in name, description or maker name/place; nothing is stripped) | "caption too long".
A malformed maker (incl. blank or control-character name/place) is no maker. A non-text, empty, multi-line,
control-character or tagged imageAlt is not used (alt = name); a products
list that is not a list of records is 'cannot read content'.
Read-only: nothing is posted, scheduled, written or sent, and the module imports no network code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.content_model import CATEGORIES, CONTENT_DIR, INVISIBLE_RE, SITE_DIR, ContentError, load_content  # noqa: E402

MAX_CAPTION = 2200
CATEGORY_TAGS = {c: "#" + c.capitalize() for c in CATEGORIES}  # fixed per category; never from free text
_TAG_RE = re.compile(r"[#@][\w]", re.UNICODE)  # a hashtag or @account in free text is refused, never rewritten


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
    tags = ["#AvocadoShack", *([CATEGORY_TAGS[product["category"]]] if product.get("category") in CATEGORY_TAGS else [])]
    caption = "\n".join(lines) + "\n\n" + " ".join(tags)
    if len(caption) > MAX_CAPTION: return refuse("caption too long")
    alt = product.get("imageAlt")
    alt = alt if _line(alt) and not _TAG_RE.search(alt) else name
    return {"draft": True, "image": product["image"], "alt": alt, "caption": caption}


def main(argv=None, content_dir: Path = CONTENT_DIR, site_dir: Path = SITE_DIR) -> int:
    parser = argparse.ArgumentParser(description="Print a local DRAFT Instagram post for one active product (posts nothing).")
    parser.add_argument("product_id")
    product_id = parser.parse_args(argv).product_id
    try: content = load_content(content_dir)
    except (ContentError, OSError): content = None  # missing or invalid content: one JSON refusal, never a traceback
    result = {"draft": False, "reason": "cannot read content"} if content is None else build(content, product_id, site_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["draft"] else 1


if __name__ == "__main__":
    sys.exit(main())
