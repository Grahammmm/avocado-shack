#!/usr/bin/env python3
"""HASS-NPP-A: derive the gallery field limits from the measured TSV, and keep the asset pins current.

    python3 scripts/hass/npp_limits.py                 write hass/npp/assets/hass-gallery-style/limits.json
    python3 scripts/hass/npp_limits.py --check         exit 1 when the committed limits.json differs from the TSV
    python3 scripts/hass/npp_limits.py --table         print the measured-lengths table (same shape as GALLERY-STYLE.md)
    python3 scripts/hass/npp_limits.py pins            rewrite the "assets" hashes in hass/npp/pins.json
    python3 scripts/hass/npp_limits.py pins --check    exit 1 when any asset hash differs from pins.json

Method (GALLERY-STYLE.md): lengths count Unicode code points including spaces and punctuation; words are
whitespace-separated; percentiles use nearest rank ceil(p*n) with no interpolation; only non-empty values are counted.
The soft/hard limits that are not measured (description 156/200, story 280/340) come from design section 2.2 and are
constants here, so a reviewer sees them in one place. No network, no model, no private value: the TSV is the public
live catalog.
"""
import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "hass" / "npp" / "assets"
TSV = ASSETS / "hass-gallery-style" / "gallery-fields.tsv"
LIMITS = ASSETS / "hass-gallery-style" / "limits.json"
PINS = ROOT / "hass" / "npp" / "pins.json"

# (limits.json key, label in the GALLERY-STYLE table, TSV column)
FIELDS = (
    ("brand", "Display brand", "brand"),
    ("name", "Product name", "name"),
    ("origin", "Origin line, including prefix/fallback", "origin"),
    ("description", "Description (including serving suggestion)", "description"),
    ("maker_name", "Expanded maker name", "maker_name"),
    ("maker_place", "Expanded maker place", "maker_place"),
    ("maker_story", "Expanded maker story", "maker_story"),
    ("maker_url", "Maker URL", "maker_url"),
    ("image", "Image path", "image"),
    ("image_alt", "Image alt text", "imageAlt"),
    ("link_to_this", "Deep-link URL", "link_to_this"),
)
# Design section 2.2: description soft max 156 / hard 200 chars, story soft 280 / hard 340; 2-3 sentences.
SOFT_HARD = {"description": {"soft_max_chars": 156, "hard_max_chars": 200, "sentences_min": 2, "sentences_max": 3,
                             "soft_target_words": 25, "soft_target_chars": 140},
             "maker_story": {"soft_max_chars": 280, "hard_max_chars": 340}}
FIXED_LABELS = {"meet_the_maker": "Meet the maker", "link_to_this": "Link to this"}
SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")
SCHEMA = 1


def rank(values, p):
    """Nearest rank, ceil(p*n), no interpolation."""
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p * len(ordered))) - 1]


def load_rows(path=TSV):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def stat(values):
    words = [len(v.split()) for v in values]
    chars = [len(v) for v in values]
    return {"present": len(values), "words": {"p50": rank(words, 0.5), "p90": rank(words, 0.9)},
            "chars": {"p50": rank(chars, 0.5), "p90": rank(chars, 0.9)}}


def build(rows):
    fields = {}
    for key, _label, column in FIELDS:
        values = [r[column] for r in rows if r.get(column, "").strip()]
        fields[key] = stat(values)
    description_ends = {}
    for r in rows:
        n = len(SENTENCE_END.findall(r["description"]))
        description_ends[str(n)] = description_ends.get(str(n), 0) + 1
    count = lambda column, truthy: sum(1 for r in rows if (r[column].strip() == "True" if truthy else bool(r[column].strip())))
    badges = {"organic": count("organic", True), "new": count("isNew", True)}
    maker_rows = fields["maker_name"]["present"]
    return {
        "schema": SCHEMA,
        "source": "hass-gallery-style/gallery-fields.tsv",
        "method": "code points; whitespace words; nearest rank ceil(p*n); non-empty values only",
        "records": len(rows),
        "fields": fields,
        "description_sentence_endings": dict(sorted(description_ends.items())),
        "badges": badges,
        "availability_present": count("availability", False),
        "selling_price_present": count("sellingPrice", False),
        "fixed_labels": {"meet_the_maker": {"text": FIXED_LABELS["meet_the_maker"], "present": maker_rows,
                                            "words": 3, "chars": len(FIXED_LABELS["meet_the_maker"])},
                         "link_to_this": {"text": FIXED_LABELS["link_to_this"], "present": len(rows),
                                          "words": 3, "chars": len(FIXED_LABELS["link_to_this"])}},
        "limits": SOFT_HARD,
    }


def table(limits):
    out = ["| Field | Present / %d | Words p50 / p90 | Characters p50 / p90 |" % limits["records"], "|---|---:|---:|---:|"]
    for key, label, _column in FIELDS:
        f = limits["fields"][key]
        out.append(f"| {label} | {f['present']} | {f['words']['p50']} / {f['words']['p90']} | "
                   f"{f['chars']['p50']} / {f['chars']['p90']} |")
    return "\n".join(out)


def render(limits):
    return json.dumps(limits, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


# ---------------------------------------------------------------------------------------------------- pins
def asset_hashes(assets=ASSETS):
    """sha256 of every file under hass/npp/assets, keyed by its posix path relative to that folder."""
    return {p.relative_to(assets).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(assets.rglob("*")) if p.is_file()}


def pins_check(pins_path=PINS, assets=ASSETS):
    """List of problems: pinned hash differs, asset missing from the pins, pin with no file. Empty = clean."""
    pins = json.loads(Path(pins_path).read_text(encoding="utf-8"))
    pinned, actual = pins.get("assets", {}), asset_hashes(assets)
    problems = [f"hash differs: {k}" for k in sorted(set(pinned) & set(actual)) if pinned[k] != actual[k]]
    problems += [f"asset not pinned: {k}" for k in sorted(set(actual) - set(pinned))]
    problems += [f"pinned file missing: {k}" for k in sorted(set(pinned) - set(actual))]
    return problems


def pins_write(pins_path=PINS, assets=ASSETS):
    pins = json.loads(Path(pins_path).read_text(encoding="utf-8"))
    pins["assets"] = asset_hashes(assets)
    Path(pins_path).write_text(json.dumps(pins, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("command", nargs="?", choices=("limits", "pins"), default="limits")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--table", action="store_true")
    args = ap.parse_args(argv)
    if args.command == "pins":
        problems = pins_check()
        if args.check:
            print("\n".join(problems) or "pins ok")
            return 1 if problems else 0
        pins_write()
        print(f"pinned {len(asset_hashes())} assets in {PINS.relative_to(ROOT)}")
        return 0
    limits = build(load_rows())
    if args.table:
        print(table(limits))
        return 0
    text = render(limits)
    if args.check:
        same = LIMITS.exists() and LIMITS.read_text(encoding="utf-8") == text
        print("limits ok" if same else "limits.json differs from the TSV; run scripts/hass/npp_limits.py")
        return 0 if same else 1
    LIMITS.write_text(text, encoding="utf-8")
    print(f"wrote {LIMITS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
