"""AVB-09: deterministic capability views from the skill registry, never host or runtime state.

Regenerate: python3 hass/capabilities.py
Check only: python3 hass/capabilities.py --check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.skills import load_skills, skill_lint
from hass.ops import load_registry
from hass.skills.model import PACKS

PACK_WORDS = {"site": "Website", "front": "Front end", "till": "Till", "reports": "Reports", "core": "General help"}
APPROVAL_WORDS = {"A0": "no yes needed", "A1": "your yes first"}
SANDBOX_WORDS = {"full": "private test supported", "preview": "private preview only", "none-needed": "no target changes"}
LIVE_WORDS = {"chat-live": "eligible for live approval", "private-only": "private only", "read-only": "read only"}
ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = Path("docs/hass/capabilities.json")
PAGE_PATH = Path("docs/hass/CAPABILITIES.md")


def manifest(registry=None) -> dict:
    registry = load_skills() if registry is None else registry
    problems = skill_lint(registry, load_registry())
    if problems:
        raise ValueError("\n".join(problems))
    rows = []
    for name, skill in sorted(registry.skills.items()):
        rows.append({key: getattr(skill, key) for key in (
            "name", "label", "summary", "pack", "targets", "approval_class", "sandbox", "status",
            "live_class", "logs", "who", "patterns", "version", "side_effects")})
    # JSON-compatible lists also make direct callers and the checked-in file identical.
    return json.loads(json.dumps({"schema_version": 1, "skills": rows}))


def _words(row) -> str:
    behavior = "writes the request down, not the change" if "backlog-row" in row["side_effects"] else LIVE_WORDS[row["live_class"]]
    return "; ".join((APPROVAL_WORDS[row["approval_class"]], SANDBOX_WORDS[row["sandbox"]],
                      behavior, "registered" if row["status"] == "active" else "retired",
                      "G only" if row["who"] == "g-only" else "owners"))


def help_section(registry=None) -> str:
    data = manifest(registry)
    lines = ["Skills in this version (what is on your phone may differ):"]
    for pack in PACKS:
        lines.append(PACK_WORDS[pack] + ":")
        rows = [row for row in data["skills"] if row["pack"] == pack]
        lines.extend(f"{row['label']} - {_words(row)}" for row in rows)
        if not rows:
            lines.append("Nothing registered yet.")
    return "\n".join(lines)


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def owner_page(data) -> str:
    lines = ["# What Hass can do", "", "Generated from the skill registry. Do not edit this page or capabilities.json by hand.",
             "", "This describes the code in this version, not what is installed on the phone or enabled by host settings.",
             "Every change still needs its existing approval and policy checks. A private test is not live permission.",
             "Front end, site, till and reports are the four packs; General help has no changing target.",
             "A0 means no owner yes; A1 means owner yes. A2 (second yes) and A3 (named exception) are not enabled.",
             "Sandbox support describes the existing private writer/preview, not AVB-11's future per-target switch.",
             "The per-target switch, audit writer and pack executors are separate work; log fields below declare names only.",
             "", "Rebuild: `python3 hass/capabilities.py`. Check: `python3 hass/capabilities.py --check`.", ""]
    for pack in PACKS:
        lines += ["## " + PACK_WORDS[pack], ""]
        rows = [row for row in data["skills"] if row["pack"] == pack]
        if not rows:
            lines += ["Nothing registered yet.", ""]
            continue
        lines += ["| Skill | What it does | Gate, private test and status | Changing targets | Declared log fields |",
                  "|---|---|---|---|---|"]
        for row in rows:
            cells = [f"{row['label']} ({row['name']})", row["summary"],
                     row["approval_class"] + ": " + _words(row), ", ".join(row["targets"]) or "none",
                     ", ".join(row["logs"]) or "none"]
            lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
        lines.append("")
    return "\n".join(lines)


def generated_files(registry=None) -> dict:
    data = manifest(registry)
    # One complete row per line keeps generated diffs readable.
    rows = ",\n".join("    " + json.dumps(row, ensure_ascii=False, sort_keys=True) for row in data["skills"])
    return {JSON_PATH: '{\n  "schema_version": 1,\n  "skills": [\n' + rows + '\n  ]\n}\n',
            PAGE_PATH: owner_page(data)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on missing/stale generated files; write nothing")
    args = parser.parse_args(argv)
    try:
        files = generated_files()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    stale = []
    for relative, text in files.items():
        path = ROOT / relative
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(str(relative))
        else:
            path.write_text(text, encoding="utf-8")
            print(f"Generated {relative}")
    if stale:
        print("Stale capability files: " + ", ".join(stale), file=sys.stderr)
        return 1
    if args.check:
        print("Capability manifest and owner page match the registry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
