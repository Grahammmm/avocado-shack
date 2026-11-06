#!/usr/bin/env python3
"""AV2152-12: publish two fixture copies of the site to scratch folders, measure rendered text contrast with
site-contrast-qa.cjs, and write or byte-compare reports/site-contrast-2026-11.md.

  PLAYWRIGHT_MODULE=/path/to/playwright python3 storefront-mockup/site-contrast-qa.py [--check | --write]

--check (default) renders to scratch and compares; --write replaces only the report. A genuine contrast failure is
recorded in the report and is NOT an error; stale/missing report, unassessed text, missing coverage, a blocked
request or a tool error exit nonzero. Nothing here runs the service, sitegen --write, or touches canonical content."""
import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
REPORT = REPO / "reports" / "site-contrast-2026-11.md"
FIXED_DAY = date(2026, 11, 5)
NOTICE_TEXT = "Fixture notice: the Shack opens at noon on Saturday."
sys.path.insert(0, str(REPO))


def luminance(hexcolor):
    """Independent (Python) WCAG relative luminance, used to recheck every recommendation in the report."""
    out = 0.0
    for w, i in ((0.2126, 1), (0.7152, 3), (0.0722, 5)):
        c = int(hexcolor[i:i + 2], 16) / 255
        out += w * (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def ratio(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def fixture_sites(root: Path):
    """Write site A (content exactly as committed) and site B (a deep copy with a live notice and availability)."""
    from hass.content_model import load_and_validate
    from hass.sitegen import publish_files, write_files
    content = load_and_validate(REPO / "hass" / "content", REPO / "storefront-mockup")
    b = copy.deepcopy(content)
    b.store["notice"] = {"text": NOTICE_TEXT, "until": "2026-11-20"}
    b.store["selection_checked_on"] = FIXED_DAY.isoformat()
    words = ["yes", "limited", "no"]
    for i, p in enumerate(b.active_products()[:6]):
        p["available"], p["available_on"] = words[i % 3] if i < 3 else "yes", FIXED_DAY.isoformat() if i < 3 else "2026-11-01"
    tree = {}
    for key, c in (("a", content), ("b", b)):
        files = publish_files(c, REPO, today=FIXED_DAY)
        write_files(files, root / key)
        h = hashlib.sha256()
        for rel in sorted(files):
            h.update(rel.encode() + b"\0" + hashlib.sha256(files[rel]).digest())
        tree[key] = (h.hexdigest()[:16], len(files))
    return tree


def run_collector(root: Path, env_extra):
    out = root / "out"
    out.mkdir()
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), "QA_OUT_DIR": str(out),
           "TMPDIR": str(root), **env_extra}
    cmd = ["node", str(HERE / "site-contrast-qa.cjs"), "--site-a", str(root / "a"), "--site-b", str(root / "b")]
    r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=1500)
    if r.returncode != 0 or "RESULT " not in r.stdout:
        raise SystemExit(f"collector failed (exit {r.returncode}): {r.stderr.strip()[-600:]}")
    return json.loads((out / "contrast.json").read_text())


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def input_identity(tree):
    rows = [("fixture site A (content as committed), published tree", f"{tree['a'][0]} ({tree['a'][1]} files)"),
            ("fixture site B (live notice + availability), published tree", f"{tree['b'][0]} ({tree['b'][1]} files)"),
            ("storefront-mockup/site-contrast-qa.cjs", sha(HERE / "site-contrast-qa.cjs")),
            ("storefront-mockup/site-contrast-qa.py", sha(Path(__file__)))]
    return rows


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def fmt(r):
    return f"{r:.3f}"


def render(doc, tree):
    c = doc["counts"]
    lines = ["# Site text contrast audit, November 2026", "",
             "Measured text/background colour pairs the home page (with its catalog) and `/hike` render, against WCAG 2.2 AA "
             "(1.4.3: 4.5:1 normal text, 3:1 large text). **This is a measurement, not a conformance claim**: failing rows are "
             "findings for a later change; no CSS was changed. Non-text contrast, Safari and physical devices are out of scope.", "",
             "## How this was measured", "",
             "- Command: `PLAYWRIGHT_MODULE=<playwright> python3 storefront-mockup/site-contrast-qa.py --write` (and `--check`, the default, which byte-compares).",
             "- `sitegen.publish_files(..., today=2026-11-05)` writes two fixture copies to a scratch folder outside the repository; a "
             "loopback static server and headless Chromium measure them. Real templates, runtime renderers and CSS are used; fixtures only supply data.",
             "- Fixture differences from normal content: **site A** is the committed content (no notice, no availability). **Site B** is a deep copy with "
             f"`store.notice` = \"{NOTICE_TEXT}\" (until 2026-11-20), `selection_checked_on` 2026-11-05 and six products given an availability word "
             "(Available today, Limited, Sold out, and three \"Last confirmed\" days). `/hike` club events, RSVP counts and service replies are fixtures "
             "(`hike-real-events`), answered from the page's own `/api/community` and POST routes; nothing leaves loopback and every other host is blocked.",
             f"- Browser: {doc['browser']}; viewports {', '.join(doc['viewports'])}; fixed clock {doc['clock']} (12:00 Pacific, 2026-11-05); Pacific time zone; `document.fonts.ready` awaited; reduced motion.",
             "- Text runs: every nonempty rendered text node, input values and placeholders, `::before`/`::after` generated text and SVG text (computed fill). "
             "Foreground is the computed colour with alpha and ancestor opacity applied; background is every ancestor layer composited in painting order over the white canvas "
             "(opacity scales each layer; exact for opaque layers). Text over an image or another box is measured from the backing pixels under the text bounds "
             "with the text suppressed (worst case reported with the lightest and darkest backing). Large text is 24 px, or 18.666667 px at weight 700 or more.",
             "- Ratios are unrounded WCAG ratios compared to the threshold (shown to 3 decimals; a 4.499 never passes as 4.5).",
             "- \"Nearest passing foreground\" is an opaque 24-bit colour with the background held fixed, minimising squared Euclidean distance in encoded RGB bytes from the "
             "measured foreground (ties: lowest RGB), searched exactly over all 16,777,216 colours. For a selector measured on several backings it must pass on every one.",
             "- Interaction: every kind of link, button, summary and control is measured at default, pointer hover and keyboard focus (one instance per kind, deduplicated by selector and context).",
             "- Limits: hidden/closed content is excluded until revealed (disclosures and dialogs are measured open); the collector is not an axe run; "
             "text in disabled controls is listed as exempt; the logo and photographs are images, not text.", "",
             "## Input identity", "", "| Input | Hash |", "|---|---|"]
    lines += [f"| {cell(k)} | `{v}` |" for k, v in input_identity(tree)]
    lines += ["", "## Result", "", f"Occurrences measured (route × viewport × state × interaction × text run): **{sum(c.values())}**.", "",
              "| Pass | Fail | Exempt | Unassessed |", "|---:|---:|---:|---:|", f"| {c['pass']} | {c['fail']} | {c['exempt']} | {c['unassessed']} |", "",
              f"Complete: **{'yes' if c['unassessed'] == 0 and not doc['coverageErrors'] else 'NO'}** (complete means zero unassessed and every required state seen). "
              f"Blocked non-loopback requests: {len(doc['blocked'])}.", ""]
    if doc["coverageErrors"]:
        lines += ["### Coverage errors", ""] + [f"- {cell(e)}" for e in doc["coverageErrors"]] + [""]

    lines += ["## State matrix", "", "Each state ran at both widths. A required selector must have visible nonempty text in the state, or the audit fails.", "",
              "| State | Route | 390 px | 1440 px |", "|---|---|---|---|"]
    by = {}
    for s in doc["states"]:
        by.setdefault(s["id"], {"route": s["route"]})[s["vp"]] = s
    occ_n = {}
    for o in doc["occurrences"]:
        occ_n[(o["state"].split("/")[0] if False else o["state"], o["vp"])] = occ_n.get((o["state"], o["vp"]), 0) + 1
    for sid in sorted(by):
        cols = []
        for vp in ("390", "1440"):
            s = by[sid].get(vp)
            cols.append("missing" if not s else f"{occ_n.get((sid, vp), 0)} runs, {len(s['required'])} required seen" + (f", {s['interactive']} hover/focus" if s["interactive"] else ""))
        lines.append(f"| `{sid}` | `{by[sid]['route']}` | {cols[0]} | {cols[1]} |")
    lines.append("")

    fails = sorted(doc["failures"], key=lambda f: (f["ratio"], f["gsel"]))
    lines += ["## Failing pairs", "",
              f"{len(fails)} failing selector/colour groups ({c['fail']} occurrences). Ratio is the lowest measured; the suggestion keeps the background fixed and "
              "passes against every backing measured for that selector.", ""]
    if fails:
        lines += ["| # | Selector | Interaction | Foreground / background | Size / weight | Threshold | Ratio | Nearest passing foreground | Occurrences, viewports, states |", "|---:|---|---|---|---|---:|---:|---|---|"]
        for i, f in enumerate(fails, 1):
            bg = f["bg"] if not f["bgRange"] else f"{f['bg']} (backing {f['bgRange'][0]} to {f['bgRange'][1]})"
            if f["rec"]["ok"]:
                rec = f"`{f['rec']['color']}` ({fmt(f['rec']['worst'])})"
                backings = sorted(set(f["bgs"]))
                for b in backings:  # independent recheck
                    assert ratio(f["rec"]["color"], b) >= f["threshold"], "recommendation fails the independent recheck"
            else:
                rec = f"no foreground-only solution: backings run from `{f['rec']['darkest']}` to `{f['rec']['lightest']}`"
            lines.append(f"| {i} | `{cell(f['gsel'])}` ({cell(f['kind'])}) | {f['interaction']} | `{f['fg']}` on `{bg}` | {f['size']:g} px / {f['weight']} | {f['threshold']:g} | {fmt(f['ratio'])} | {rec} | {f['count']}; {', '.join(f['vps'])} px; {cell(', '.join(f['states']))} |")
        lines.append("")
        lines += ["### Example nodes", ""] + [f"{i}. `{cell(f['first'])}` — \"{cell(f['text'])}\"" for i, f in enumerate(fails, 1)] + [""]
    else:
        lines += ["No failing pair was measured.", ""]

    lines += ["## Exemptions and unassessed", ""]
    ex = {}
    for o in doc["occurrences"]:
        if o["status"] in ("exempt", "unassessed"):
            ex.setdefault((o["status"], o["reason"], o["gsel"]), set()).add(o["vp"])
    if ex:
        lines += ["| Status | Selector | Reason | Viewports |", "|---|---|---|---|"]
        for (st, reason, g), vps in sorted(ex.items()):
            lines.append(f"| {st} | `{cell(g)}` | {cell(reason)} | {', '.join(sorted(vps))} |")
    else:
        lines.append("None.")
    lines.append("")

    pairs = {}
    for o in doc["occurrences"]:
        if o["status"] in ("pass", "fail"):
            k = (o["fg"], o["bg"], o["threshold"], o["status"])
            p = pairs.setdefault(k, {"n": 0, "ratio": o["ratio"], "ex": {}})
            p["n"] += 1
            p["ratio"] = min(p["ratio"], o["ratio"])
            p["ex"].setdefault(o["gsel"], 0)
            p["ex"][o["gsel"]] += 1
    lines += ["## Pair inventory", "", f"{len(pairs)} distinct effective foreground/background/threshold/status pairs, lowest ratio first.", "",
              "| Foreground | Background | Threshold | Status | Lowest ratio | Occurrences | Selectors (up to 4) |", "|---|---|---:|---|---:|---:|---|"]
    for (fg, bg, thr, st), p in sorted(pairs.items(), key=lambda kv: (kv[1]["ratio"], kv[0])):
        sels = ", ".join(f"`{cell(s)}`" for s in sorted(p["ex"], key=lambda s: (-p["ex"][s], s))[:4])
        lines.append(f"| `{fg}` | `{bg}` | {thr:g} | {st} | {fmt(p['ratio'])} | {p['n']} | {sels} |")
    lines.append("")

    idx = {}
    for o in doc["occurrences"]:
        if o["status"] in ("pass", "fail"):
            e = idx.setdefault((o["gsel"], o["kind"], o["fg"], o["bg"], o["size"], o["weight"], o["status"]), {"n": 0, "s": set(), "v": set(), "i": set()})
            e["n"] += 1
            e["s"].add(o["state"])
            e["v"].add(o["vp"])
            e["i"].add(o["interaction"])
    lines += ["## Occurrence index", "", "Every selector group with its colours, how many nodes were measured (cards counted individually) and in which states and viewports.", "",
              "| Selector | Kind | Foreground / background | Size / weight | Status | Count | Viewports | Interactions | States |", "|---|---|---|---|---|---:|---|---|---|"]
    for k, e in sorted(idx.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][3], kv[0][4])):
        g, kind, fg, bg, size, weight, st = k
        lines.append(f"| `{cell(g)}` | {kind} | `{fg}` on `{bg}` | {size:g} px / {weight} | {st} | {e['n']} | {', '.join(sorted(e['v']))} | {', '.join(sorted(e['i']))} | {cell(', '.join(sorted(e['s'])))} |")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m = ap.add_mutually_exclusive_group()
    m.add_argument("--check", action="store_true", help="render to scratch and byte-compare the report (default)")
    m.add_argument("--write", action="store_true", help="replace reports/site-contrast-2026-11.md")
    ap.add_argument("--report", type=Path, default=REPORT, help=argparse.SUPPRESS)
    ap.add_argument("--json-out", type=Path, help="debug: also save the raw measurement JSON here (outside the repository)")
    args = ap.parse_args(argv)
    if not os.environ.get("PLAYWRIGHT_MODULE"):
        print("site-contrast-qa: set PLAYWRIGHT_MODULE to the playwright module folder", file=sys.stderr)
        return 2
    root = Path(tempfile.mkdtemp(prefix="avoshack-contrast-"))
    try:
        tree = fixture_sites(root)
        doc = run_collector(root, {"PLAYWRIGHT_MODULE": os.environ["PLAYWRIGHT_MODULE"]})
        if args.json_out:
            args.json_out.write_text(json.dumps(doc))
        text = render(doc, tree)
        problems = []
        if doc["counts"]["unassessed"]:
            problems.append(f"{doc['counts']['unassessed']} unassessed text run(s)")
        problems += doc["coverageErrors"]
        if doc["blocked"]:
            problems.append("non-loopback requests were attempted: " + ", ".join(doc["blocked"]))
        if problems and not args.write:
            print("site-contrast-qa: incomplete audit:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        if problems:
            print("site-contrast-qa: refusing to write an incomplete audit:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        data = text.encode("utf-8")
        if args.write:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            if not args.report.exists() or args.report.read_bytes() != data:
                args.report.write_bytes(data)
            print(f"wrote {args.report.name}: {doc['counts']}")
            return 0
        if not args.report.exists() or args.report.read_bytes() != data:
            print("site-contrast-qa: report is missing or stale (run with --write)", file=sys.stderr)
            return 1
        print(f"ok: report matches ({doc['counts']})")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
