"""Generate the private site's content files from hass/content (H01).

    python3 hass/sitegen.py --check          # exit 1 if any generated file differs
    python3 hass/sitegen.py --write          # rewrite changed site files atomically
    python3 hass/sitegen.py --out DIR        # render into DIR (same relative paths)

Generated files (do not edit them by hand; edit hass/content or hass/templates):
    storefront-mockup/catalog-products.js   active products only
    storefront-mockup/producers.js          maker profiles (browser)
    storefront-mockup/producers.json        maker profiles (same data, JSON)
    storefront-mockup/community.json        club info, real events, route ideas
    storefront-mockup/index.html            hass/templates/index.html + store info
    storefront-mockup/hike/index.html       hass/templates/hike/index.html + store info

Not generated: held-products.json (historical hold evidence; held status lives in
products.json) and hiking-preview.json (labelled samples, kept separate).
"""

from __future__ import annotations

import argparse
import errno
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote_plus

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.content_model import (  # noqa: E402
    PRODUCT_OPTIONAL_PUBLIC, PRODUCT_PUBLIC_FIELDS, REPO_ROOT, Content, ContentError, checked_on, load_and_validate,
    shop_today,
)

TEMPLATE_DIR = REPO_ROOT / "hass" / "templates"
SITE_PREFIX = "storefront-mockup/"
TEMPLATES = ("index.html", "hike/index.html")
SLOT_RE = re.compile(r"\{\{([a-zA-Z.]+)\}\}")
# SHOP-1: freshness words come only from Michael's recorded check (store.selection_checked_on), never from the clock.
# The generation date is used only to decide whether that stored date is more than STALE_AFTER_DAYS old.
STALE_AFTER_DAYS = 7
AVAILABILITY_WORDS = {"yes": "Available today", "limited": "Limited", "no": "Sold out"}
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")


def _day_text(day) -> str:
    """'Friday, October 23' (fixed English names; no locale)."""
    return f"{_DAYS[day.weekday()]}, {_MONTHS[day.month - 1]} {day.day}"


def _check_state(store: dict, today):
    """(check date or None, stale?) where stale means older than STALE_AFTER_DAYS at generation date ``today``."""
    day = checked_on(store)
    return day, day is not None and (today - day).days > STALE_AFTER_DAYS


def checked_line(store: dict, today) -> str:
    day, stale = _check_state(store, today)
    if day is None:
        return "The selection has not been checked yet."
    tail = " (more than a week ago - call or visit to confirm)" if stale else ""
    return f"Selection last checked by Michael on {_day_text(day)}{tail}."


def availability_label(product: dict, store: dict, today) -> str | None:
    """Card words for an active product, or None (no check yet, or availability not confirmed)."""
    day, stale = _check_state(store, today)
    if day is None or product.get("available") not in AVAILABILITY_WORDS:
        return None
    return f"Last confirmed {_day_text(day)}" if stale else AVAILABILITY_WORDS[product["available"]]


def _catalog_js(content: Content, today) -> bytes:
    records = []
    for p in content.active_products():
        record = {k: v for k, v in p.items() if k in PRODUCT_PUBLIC_FIELDS + PRODUCT_OPTIONAL_PUBLIC}
        if (label := availability_label(p, content.store, today)) is not None:
            record["availability"] = label
        records.append(record)
    return ("const catalog=" + json.dumps(records, ensure_ascii=False) + ";\n").encode("utf-8")


def _visible_makers(content: Content) -> dict:
    return {k: m for k, m in content.makers.items() if "hidden" not in m}


def _producers_js(content: Content) -> bytes:
    return ("const producers=" + json.dumps(_visible_makers(content)) + ";").encode("utf-8")


def _producers_json(content: Content) -> bytes:
    return json.dumps(_visible_makers(content), indent=2).encode("utf-8")


def _community_json(content: Content) -> bytes:
    data = dict(content.community["club"])
    data["events"] = content.community["events"]
    data["routeIdeas"] = content.community["routeIdeas"]
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def store_slots(store: dict) -> dict[str, str]:
    """HTML-escaped values for the store-info slots in the page templates."""
    street, town, name = store["streetAddress"], store["town"], store["name"]
    maps = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name} {street} {town}")
    return {
        "store.addressLine": html.escape(f"{street}, {town}", quote=False),
        "store.addressShort": html.escape(f"{street} · {town}", quote=False),
        "store.hoursHtml": "<br>".join(html.escape(line, quote=False) for line in store["hours"]),
        "store.mapsUrl": html.escape(maps, quote=True),
    }


def render_template(text: str, slots: dict[str, str]) -> str:
    unknown = sorted({m for m in SLOT_RE.findall(text) if m not in slots})
    if unknown:
        raise ContentError([f"template: unknown slot(s) {unknown}"])
    out = SLOT_RE.sub(lambda m: slots[m.group(1)], text)
    if "{{" in out or "}}" in out:
        raise ContentError(["template: unrendered '{{' or '}}' left in output"])
    return out


def render(content: Content, template_dir: Path = TEMPLATE_DIR, today=None) -> dict[str, bytes]:
    """Return {repo-relative path: bytes} for every generated site file. ``today`` (default: the shop's current date)
    only decides whether the stored selection check is stale; no clock value is ever written into the output."""
    today = today or shop_today()
    files = {
        SITE_PREFIX + "catalog-products.js": _catalog_js(content, today),
        SITE_PREFIX + "producers.js": _producers_js(content),
        SITE_PREFIX + "producers.json": _producers_json(content),
        SITE_PREFIX + "community.json": _community_json(content),
    }
    line = html.escape(checked_line(content.store, today), quote=False)
    slots = {**store_slots(content.store), "selection.checkedLine": line}
    for rel in TEMPLATES:
        text = (Path(template_dir) / rel).read_bytes().decode("utf-8")
        files[SITE_PREFIX + rel] = render_template(text, slots).encode("utf-8")
    return files


def diff_paths(files: dict[str, bytes], root: Path) -> list[str]:
    """Generated paths whose bytes differ from (or are missing under) root."""
    changed = []
    for rel, data in files.items():
        target = Path(root) / rel
        if not target.is_file() or target.read_bytes() != data:
            changed.append(rel)
    return changed


def _check_folders(root: Path, rel: str) -> None:
    """Refuse an absolute/escaping key or a symlinked folder below root (root itself may be a link)."""
    key = Path(rel)
    parts = key.parts
    if key.is_absolute() or key.drive or not parts or ".." in parts:
        raise ValueError("generated path escapes root")
    for i in range(1, len(parts)):
        if os.path.islink(Path(root, *parts[:i])):
            raise OSError(errno.ELOOP, "generated folder is a symlink")


def write_files(files: dict[str, bytes], root: Path, only: list[str] | None = None) -> list[str]:
    """Atomically replace each (changed) file under root; return written paths."""
    written = []
    selected = [(rel, data) for rel, data in files.items() if only is None or rel in only]
    for rel, _ in selected:
        _check_folders(Path(root), rel)
    for rel, data in selected:
        target = Path(root) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        if os.path.islink(target):
            raise OSError(errno.ELOOP, "generated target is a symlink")
        fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, target)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        written.append(rel)
    return written


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (OSError, ValueError) as exc:  # ContentError is handled inside _main first
        print(f"sitegen: io error: {type(exc).__name__}", file=sys.stderr)
        return 2


def _main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail if generated files differ from the repo")
    mode.add_argument("--write", action="store_true", help="rewrite generated files that differ")
    mode.add_argument("--out", type=Path, help="render all generated files into this directory")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="repository root (default: this checkout)")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    try:
        content = load_and_validate(repo / "hass" / "content", repo / "storefront-mockup")
        files = render(content, repo / "hass" / "templates")
    except ContentError as exc:
        print("content invalid:", file=sys.stderr)
        for problem in exc.problems:
            print("  " + problem, file=sys.stderr)
        return 2

    if args.out is not None:
        written = write_files(files, args.out)
        print(f"rendered {len(written)} files into {args.out}")
        return 0
    changed = diff_paths(files, repo)
    if args.check:
        if changed:
            print("generated files out of date (run python3 hass/sitegen.py --write):")
            for rel in changed:
                print("  " + rel)
            return 1
        print(f"ok: {len(files)} generated files match hass/content "
              f"({len(content.active_products())} active products, {len(content.makers)} makers)")
        return 0
    written = write_files(files, repo, only=changed)
    print(f"wrote {len(written)} changed files" + "".join("\n  " + rel for rel in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
