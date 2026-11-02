"""Local Instagram post draft from one product photo (AVB-22, F07 "prepare" half only).

    python3 hass/social_draft.py PRODUCT_ID

Prints one JSON object. Success: {"draft": true, "image", "alt", "caption"} built only from the product's
stored name, description, image, imageAlt and its maker's name and place (caption <= 2200 characters, at most
5 hashtags: #AvocadoShack plus one fixed tag per category, never derived from free text). Refusal (exit 1):
{"draft": false, "reason"}: "no such product" | "not on the site" | "no photo on the site" | "caption too long".
Read-only: nothing is posted, scheduled, written or sent, and the module imports no network code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.content_model import CATEGORIES, CONTENT_DIR, SITE_DIR, load_content  # noqa: E402

MAX_CAPTION = 2200
CATEGORY_TAGS = {c: "#" + c.capitalize() for c in CATEGORIES}  # fixed per category; never from free text


def _photo_ok(image, site_dir: Path) -> bool:
    try:
        path = (site_dir / image).resolve()
        return isinstance(image, str) and path.is_relative_to(site_dir.resolve()) and path.is_file()
    except (OSError, ValueError):
        return False


def build(content, product_id: str, site_dir: Path = SITE_DIR) -> dict:
    """Return the draft dict, or {"draft": False, "reason": ...}. The id is only matched against loaded products."""
    def refuse(reason): return {"draft": False, "reason": reason}
    product = next((p for p in content.products if p.get("id") == product_id), None)
    if product is None: return refuse("no such product")
    if product.get("status") != "active": return refuse("not on the site")
    if not _photo_ok(product.get("image"), Path(site_dir)): return refuse("no photo on the site")
    maker = content.makers.get(product.get("producerKey")) if isinstance(product.get("producerKey"), str) else None
    lines = [product["name"], product["description"]]
    if maker: lines.append(f"From {maker['name']} in {maker['place']}.")
    tags = ["#AvocadoShack", *([CATEGORY_TAGS[product["category"]]] if product.get("category") in CATEGORY_TAGS else [])]
    caption = "\n".join(lines) + "\n\n" + " ".join(tags)
    if len(caption) > MAX_CAPTION: return refuse("caption too long")
    return {"draft": True, "image": product["image"], "alt": product.get("imageAlt") or product["name"], "caption": caption}


def main(argv=None, content_dir: Path = CONTENT_DIR, site_dir: Path = SITE_DIR) -> int:
    parser = argparse.ArgumentParser(description="Print a local DRAFT Instagram post for one active product (posts nothing).")
    parser.add_argument("product_id")
    result = build(load_content(content_dir), parser.parse_args(argv).product_id, site_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["draft"] else 1


if __name__ == "__main__":
    sys.exit(main())
