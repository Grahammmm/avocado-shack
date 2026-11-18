"""ITEMSTD-2: the item-standard completeness check (docs/hass/ITEM-STANDARD.md section 3).

`check_product(record, makers)` and `check_maker(record)` say what a saved product or maker is missing against the
standard, and the one plain question to ask Mike first. Pure: no I/O, no clock, no network, no model, and the inputs
are never changed. The fields, the asking order and the question wording live in hass/style/item-standard.json, read
once when the module loads. Picture numbers are not here (they stay in hass/style/house-style.json).

Each check returns {complete, missing, display_problems, needs_a_look, ask_order, question}; a held product returns
None. `own_photo` (an upgrade) and `website` (optional) may be listed in `missing` but never make an item incomplete
and are never asked. The question keeps Mike's own words marked with voice.quote; plain() it before printing.

Read-only report: python3 hass/itemstd.py report [--content DIR] [--json] [--write]
Only --write replaces reports/hass/catalog-gaps.json (in this repository), after the whole report is built.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import voice  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = Path(__file__).resolve().parent / "style" / "item-standard.json"
DEFAULT_CONTENT = REPO_ROOT / "hass" / "content"
REPORT_PATH = REPO_ROOT / "reports" / "hass" / "catalog-gaps.json"

SETTINGS = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
CODES = tuple(SETTINGS["codes"])
PRODUCT_REQUIRED = frozenset(SETTINGS["product_fields"]["required"])
MAKER_REQUIRED = frozenset(SETTINGS["maker_fields"]["required"])
ASK_ORDER = tuple(SETTINGS["ask_order"])
MAKER_ASK_ORDER = tuple(SETTINGS["maker_ask_order"])
SHELVES = tuple(SETTINGS["shelves"])
FRESH_SHELVES = frozenset(SETTINGS["fresh_shelves"])
PACKAGED_IDS = frozenset(SETTINGS["packaged_ids"])
QUESTIONS = dict(SETTINGS["questions"])
_LIMITS = SETTINGS["display_limits"]
_OWN_PHOTO_RE = re.compile(SETTINGS["own_photo_pattern"])
_REGION = SETTINGS["region"]


def _fold(text: str) -> str:
    return " ".join(str(text).replace("\u2019", "'").casefold().split())


_UNKNOWN_PRODUCER = frozenset(_fold(x) for x in SETTINGS["unknown_producer_labels"])
_OWN_BRAND = frozenset(_fold(x) for x in SETTINGS["own_brand_labels"])
_REGION_NAMES = frozenset(_fold(x) for x in _REGION["names"])
_REGION_PREFIXES = tuple(_fold(x) + " " for x in _REGION["prefixes"])
_REGION_SUFFIXES = tuple(" " + _fold(x) for x in _REGION["suffixes"])


def _text(value) -> str:
    """The value as stripped text, or '' when it is absent, blank or not text."""
    return value.strip() if isinstance(value, str) else ""


def _is_region(part: str) -> bool:
    """Whole regional forms only: a listed region name ("California's Central Coast" counts as Central Coast), or
    near/around X, or X County/Region/Area. A town that merely contains a word such as Valley is not a region."""
    p = _fold(part)
    if not p: return False
    if p in _REGION_NAMES or p.startswith(_REGION_PREFIXES) or p.endswith(_REGION_SUFFIXES): return True
    return "'s " in p and p.rsplit("'s ", 1)[1] in _REGION_NAMES


def _is_place_part(part: str) -> bool:
    return any(ch.isalpha() for ch in part) and all(
        ch.isalpha() or ch in " '\u2019-." or unicodedata.category(ch) == "Mn" for ch in part)


def classify_place(place) -> str:
    """'town' ("Town, State"), 'region', 'blank' or 'other'. A format and region check, not a map lookup: spelling
    is never corrected and nothing is looked up."""
    text = _text(place)
    if not text: return "blank"
    parts = [p.strip() for p in text.split(",")]
    if _is_region(parts[0]) or _is_region(text): return "region"
    if len(parts) == 2 and all(_is_place_part(p) for p in parts): return "town"
    return "other"


def _result(missing, display, look, ask_codes, required, question_for) -> dict:
    order = [c for c in CODES if c in set(missing)]
    ask = [c for c in ask_codes if c in order]
    return {"complete": not any(c in required for c in order), "missing": order,
            "display_problems": list(dict.fromkeys(display)), "needs_a_look": list(dict.fromkeys(look)),
            "ask_order": ask, "question": question_for(ask[0]) if ask else None}


def _town_question(label: str) -> str:
    return QUESTIONS["producer_town"].format(maker=voice.quote(label)) if label else QUESTIONS["producer_town_no_label"]


def check_product(record, makers):
    """What a saved product lacks against the item standard; None for a held product (never asked about)."""
    status = record.get("status")
    if status == "held": return None
    missing, display, look = [], [], []
    name = _text(record.get("name"))
    if not name: missing.append("name")
    else:
        if len(name) > _LIMITS["name_max"]: display.append("name_long")
        if any(ch.isdigit() for ch in name): display.append("name_has_digit")
    shelf = record.get("category")
    if not isinstance(shelf, str) or shelf not in SHELVES: missing.append("shelf")
    brand = _text(record.get("brand"))
    key = record.get("producerKey")
    maker = makers.get(key) if isinstance(key, str) and key and hasattr(makers, "get") else None
    label = ""
    if maker is not None and isinstance(maker, dict):
        label = _text(maker.get("name")) or key
        kind = classify_place(maker.get("place"))
        if kind != "town":
            missing.append("producer_town")
            if kind == "region": look.append("place_is_a_region")
            elif kind == "other": look.append("place_not_town_state")
    else:
        if key: look.append("broken_maker_link")
        named = bool(brand) and _fold(brand) not in _UNKNOWN_PRODUCER and _fold(brand) not in _OWN_BRAND
        if named:
            label = brand
            if not key: look.append("brand_without_maker_record")
        else:
            missing.append("producer")
        missing.append("producer_town")
    if not _text(record.get("description")): missing.append("description")
    else:
        desc = _text(record.get("description"))
        if len(desc) > _LIMITS["description_max"]: display.append("description_long")
        if "!" in desc or "?" in desc: display.append("description_punctuation")
        if any(ch.isdigit() for ch in desc): display.append("description_has_digit")
        if not desc.endswith("."): display.append("description_no_full_stop")
    image = _text(record.get("image"))
    if not image: display.append("picture_missing")
    own = bool(_OWN_PHOTO_RE.fullmatch(image))
    if not own: missing.append("own_photo")
    elif not _text(record.get("imageAlt")): display.append("alt_is_default")
    # a non-string shelf (list, object) is already a missing shelf above and is never hashed here
    fresh = isinstance(shelf, str) and shelf in FRESH_SHELVES and record.get("id") not in PACKAGED_IDS

    def question(code):
        if code == "producer":
            return QUESTIONS["producer_fresh" if fresh else "producer_packaged"].format(item=voice.quote(name))
        if code == "producer_town": return _town_question(label)
        return QUESTIONS[code]
    return _result(missing, display, look, () if status == "hidden" else ASK_ORDER, PRODUCT_REQUIRED, question)


def check_maker(record):
    """What a saved maker lacks: name, a 'Town, State' place (a region counts as producer_town), the about text, and
    the optional website. A hidden maker is never asked about."""
    missing, look = [], []
    name = _text(record.get("name"))
    if not name: missing.append("name")
    kind = classify_place(record.get("place"))
    if kind != "town":
        missing.append("producer_town")
        if kind == "region": look.append("place_is_a_region")
        elif kind == "other": look.append("place_not_town_state")
    if not _text(record.get("story")): missing.append("story")
    if not _text(record.get("url")): missing.append("website")
    ask = () if record.get("hidden") else MAKER_ASK_ORDER
    return _result(missing, [], look, ask, MAKER_REQUIRED, lambda code: _town_question(name))


# -- report (the only part that reads or writes files) ---------------------------------------------------------------

class ReportError(Exception):
    pass


def _has_surrogate(data) -> bool:
    """True if any decoded string (dict key or value, list item) holds U+D800-U+DFFF. Iterative: no recursion."""
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if any("\ud800" <= ch <= "\udfff" for ch in item): return True
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return False


def _load(path: Path, key: str, kind: type):
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except RecursionError:
        raise ReportError(f"cannot read {path}: JSON nesting is too deep") from None
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ReportError(f"cannot read {path}: {exc}") from None
    if (not isinstance(data, dict) or type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 1
            or not isinstance(data.get(key), kind)):
        raise ReportError(f"{path}: expected {{\"schemaVersion\": 1, \"{key}\": {kind.__name__}}}")
    if _has_surrogate(data):
        raise ReportError(f"cannot read {path}: JSON contains surrogate text")
    return data[key], hashlib.sha256(raw).hexdigest()


def _shelf_rank(shelf):
    return SHELVES.index(shelf) if shelf in SHELVES else len(SHELVES)


def build_report(products, makers, source) -> dict:
    """The report from the exact checker results. products: list of records; makers: key -> record."""
    for p in products:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str):
            raise ReportError("every product must be an object with a text id")
    for k, m in makers.items():
        if not isinstance(m, dict): raise ReportError(f"maker {k!r} must be an object")
    counts = {c: 0 for c in CODES}
    product_rows, gaps, incomplete, upgrades, held, hidden, active = [], 0, 0, 0, 0, 0, 0
    ordered = sorted(products, key=lambda p: (_shelf_rank(p.get("category")), _text(p.get("name")).casefold(), p["id"]))
    for p in ordered:
        row = {"id": p["id"], "name": _text(p.get("name")), "status": p.get("status")}
        res = check_product(p, makers)
        if res is None: held += 1
        elif p.get("status") == "hidden": hidden += 1
        elif p.get("status") == "active":
            active += 1
            for c in res["missing"]: counts[c] += 1
            gaps += bool(set(res["missing"]) & set(ASK_ORDER))
            incomplete += not res["complete"]
            upgrades += "own_photo" in res["missing"]
            row.update(res, question=voice.plain(res["question"]) if res["question"] else None)
        product_rows.append(row)
    maker_counts = {c: 0 for c in CODES}
    maker_rows, maker_gaps, regions, makers_hidden = [], 0, 0, 0
    for key in sorted(makers, key=lambda k: (str(k).casefold(), str(k))):
        res = check_maker(makers[key])
        row = {"key": key, "place": makers[key].get("place"), "hidden": bool(makers[key].get("hidden"))}
        if row["hidden"]: makers_hidden += 1
        else:
            for c in res["missing"]: maker_counts[c] += 1
            maker_gaps += not res["complete"]
            regions += "place_is_a_region" in res["needs_a_look"]
        row.update(res, question=voice.plain(res["question"]) if res["question"] else None)
        maker_rows.append(row)
    product_required = [c for c in CODES if c in PRODUCT_REQUIRED]
    maker_required = [c for c in CODES if c in MAKER_REQUIRED]
    summary = {
        "products_active": active, "products_held": held, "products_hidden": hidden,
        "products_with_an_information_gap": gaps, "products_incomplete": incomplete,
        "missing_by_field_products": {c: counts[c] for c in product_required},
        "own_photo_upgrades": upgrades,
        "makers": len(makers), "makers_hidden": makers_hidden, "makers_with_a_gap": maker_gaps,
        "makers_with_a_region": regions,
        "missing_by_field_makers": {c: maker_counts[c] for c in maker_required},
        "makers_without_website": maker_counts["website"],
    }
    return {"schema": 2, "about": ("Item-standard check (hass/itemstd.py, docs/hass/ITEM-STANDARD.md section 3) of the "
                                    "saved catalog. own_photo is an upgrade and website is optional: neither is a gap."),
            "source": source, "summary": summary, "products": product_rows, "makers": maker_rows}


def report_for(content: Path) -> dict:
    products, products_sha = _load(content / "products.json", "products", list)
    makers, makers_sha = _load(content / "makers.json", "makers", dict)
    try: label = content.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError: label = "a folder outside this repository"
    source = {"content": label, "products_sha256": products_sha, "makers_sha256": makers_sha}
    return build_report(products, makers, source)


def report_text(report: dict) -> str:
    s = report["summary"]
    lines = [f"Item standard check of {report['source']['content']}",
             f"Active products: {s['products_active']} (held {s['products_held']}, hidden {s['products_hidden']})",
             f"Active products with an information gap: {s['products_with_an_information_gap']} of {s['products_active']}"]
    lines += [f"  {c}: {n}" for c, n in s["missing_by_field_products"].items() if n]
    lines += [f"Incomplete active products: {s['products_incomplete']}",
              f"Stock pictures (own photo is an upgrade, not a gap): {s['own_photo_upgrades']}",
              f"Makers: {s['makers']} (hidden {s['makers_hidden']}); with a gap: {s['makers_with_a_gap']}; "
              f"place is a region: {s['makers_with_a_region']}"]
    lines += [f"  {c}: {n}" for c, n in s["missing_by_field_makers"].items() if n]
    lines.append(f"Makers without a website (optional): {s['makers_without_website']}")
    return "\n".join(lines)


def write_report(report: dict, target: Path = REPORT_PATH) -> None:
    """Replace target only after the whole text is ready (a sibling temp file, then an atomic rename)."""
    text = json.dumps(report, ensure_ascii=False, indent=1) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".catalog-gaps.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh: fh.write(text)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemstd.py", description="Item-standard check of the saved catalog.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("report", help="print the counts (read-only unless --write)")
    rp.add_argument("--content", type=Path, default=DEFAULT_CONTENT, help="folder with products.json and makers.json")
    rp.add_argument("--json", action="store_true", help="print the whole report as JSON")
    rp.add_argument("--write", action="store_true", help="also replace reports/hass/catalog-gaps.json")
    args = ap.parse_args(argv)
    try:
        report = report_for(args.content)
        if args.write:
            if not REPORT_PATH.parent.is_dir(): raise ReportError(f"{REPORT_PATH.parent} does not exist")
            try: write_report(report)
            except OSError: raise ReportError("cannot write report") from None
    except ReportError as exc:
        print(f"itemstd: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=1) if args.json else report_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
