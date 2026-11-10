"""Hass skill model (SKILLS-FW-1): the frozen shape every skill fills, and the lint that pins it.

A skill is data plus one pure ``plan`` function. The interpreter picks a skill and fills slots; code validates the
slots and plans typed ops. Nothing here writes a file, calls a network or changes the editor, claims or approval path.
Spec: reports/hass/SKILLS-SPEC.md sections 2.2 and 2.9 (level 1). Authoring guide: docs/hass/SKILLS.md.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, NamedTuple

from hass.ops import KINDS as OP_KINDS

# Skill-level kinds are resolved by code (hass/skills/kinds.py) before the plan runs.
SKILL_KINDS = ("product_ref", "maker_ref", "hike_ref", "route_ref", "shelf", "availability", "day", "clock",
               "attachment")
# Plain kinds the dispatcher checks for shape only (never resolved, never an op kind). stock_items: stock.set's list of
# {"product": <id>, "availability": "yes"|"limited"|"no"} objects (RF0814-12).
PLAIN_KINDS = ("stock_items",)
SLOT_KINDS = OP_KINDS + SKILL_KINDS + PLAIN_KINDS

SIDE_EFFECTS = ("picture-render", "inventory-word", "shelf-check-day", "maker-create", "restock-date",
                "private-note", "backlog-row", "none")
PREVIEWS = ("hike", "home", "picture", "none")  # plus "product:<query>"
APPROVALS = ("owner-yes", "none")
LIVE_CLASSES = ("chat-live", "private-only", "read-only")
UNDO_MODES = ("revert", "forget", "none")
TRIGGER_TAGS = ("clean", "vague", "typo", "multi")
STATUSES = ("active", "retired")

NAME_RE = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*")
SLOT_NAME_RE = re.compile(r"[a-z][a-z0-9_]*")
RULE_RE = re.compile(r"[a-z][a-z0-9-]*")
CASES_RE = re.compile(r"hass/tests/fixtures/skills/[a-z0-9_-]+/[a-z0-9_.-]+\.jsonl")

MAX_SUMMARY, MIN_TRIGGERS, MAX_ASK_WORDS, MAX_OPS = 120, 6, 14, 20
MIN_CASE_ROWS, MIN_REFUSAL_ROWS, MIN_UNDO_ROWS = 10, 2, 1
MAX_PROMPT_BYTES = 6 * 1024  # spec 2.4: the generated Skills block (hass/skills/prompt.py, a later card)

Plan = Callable[[dict, Any], list]


class Trigger(NamedTuple):
    """One example sentence in the owner's voice. ``tag`` marks the kind of example the lint counts."""
    text: str
    tag: str = "clean"


@dataclass(frozen=True)
class Slot:
    name: str
    kind: str
    required: Any = False  # True, False, "if:<slot>" or "unless:<slot>"
    default: Any = None  # a literal or "derive:<function>" (run by code, shown as "I set X to Y")
    ask: str = ""  # the one short question when the slot is required and missing
    owner_words: bool = False  # the value must be traceable to the owner's own texts
    limit: tuple | None = None  # (content kind, field): read from content_model.TEXT_LIMITS, never copied
    from_attachment: bool = False


@dataclass(frozen=True)
class Undo:
    mode: str  # "revert" (draft history.revert), "forget" (drop a private row) or "none" (read-only)
    residue: str  # what undo cannot remove; "none" when nothing stays


@dataclass(frozen=True)
class Skill:
    name: str
    label: str
    summary: str
    triggers: tuple
    slots: tuple
    rules: tuple
    plan: Plan
    edits: tuple
    side_effects: tuple
    preview: str
    approval: str
    live_class: str
    undo: Undo
    refuse: tuple
    cases: str
    version: int
    status: str = "active"

    @property
    def group(self) -> str:
        return self.name.split(".", 1)[0]


def _fold(text) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", plain.casefold().replace("'", "")).split())


def lint_skill(skill, ops_registry, coll_files=None) -> list:
    """Problems with one skill's declaration (strings naming the skill and the field); [] when it is well formed."""
    name = getattr(skill, "name", "?")
    out: list = []

    def bad(field_name, why):
        out.append(f"{name}: {field_name}: {why}")

    if not isinstance(skill, Skill):
        return [f"{name}: not a Skill"]
    if not isinstance(skill.name, str) or not NAME_RE.fullmatch(skill.name):
        bad("name", "must be group.verb, lower case")
    if skill.status not in STATUSES:
        bad("status", f"must be one of {STATUSES}")
    if not (isinstance(skill.label, str) and skill.label.strip()):
        bad("label", "required")
    elif NAME_RE.fullmatch(skill.label) or re.search(r"\b[a-z]+\.[a-z_]+\b", skill.label):
        bad("label", "must be owner words, not the id")
    if not (isinstance(skill.summary, str) and skill.summary.strip()):
        bad("summary", "required")
    elif len(skill.summary) > MAX_SUMMARY:
        bad("summary", f"over {MAX_SUMMARY} characters")

    triggers = skill.triggers if isinstance(skill.triggers, tuple) else ()
    if len(triggers) < MIN_TRIGGERS:
        bad("triggers", f"at least {MIN_TRIGGERS} examples")
    tags = set()
    for t in triggers:
        if not (isinstance(t, Trigger) and isinstance(t.text, str) and t.text.strip() and t.tag in TRIGGER_TAGS):
            bad("triggers", f"each is Trigger(text, tag in {TRIGGER_TAGS})")
            break
        tags.add(t.tag)
    for needed in ("vague", "typo", "multi"):
        if triggers and needed not in tags:
            bad("triggers", f"needs at least one {needed} example")
    folded = [_fold(t.text) for t in triggers if isinstance(t, Trigger)]
    if len(set(folded)) != len(folded):
        bad("triggers", "the same trigger text twice")

    slots = skill.slots if isinstance(skill.slots, tuple) else ()
    names = [s.name for s in slots if isinstance(s, Slot)]
    if not isinstance(skill.slots, tuple) or len(names) != len(slots):
        bad("slots", "must be a tuple of Slot")
    if len(set(names)) != len(names):
        bad("slots", "slot names must be unique")
    for s in slots:
        if not isinstance(s, Slot):
            continue
        if not SLOT_NAME_RE.fullmatch(s.name):
            bad("slots", f"slot name {s.name!r} must be lower case")
        if s.kind not in SLOT_KINDS:
            bad("slots", f"{s.name}: kind {s.kind!r} is not in SLOT_KINDS")
        req = s.required
        if req is not True and req is not False:
            ref = req.split(":", 1)[1] if isinstance(req, str) and req.startswith(("if:", "unless:")) else None
            if ref is None or ref not in names or ref == s.name:
                bad("slots", f"{s.name}: required must be True, False or if:/unless: another slot")
        if req is True or isinstance(req, str):
            words = len(s.ask.split())
            if not s.ask or words > MAX_ASK_WORDS:
                bad("slots", f"{s.name}: a required slot needs an ask of 1 to {MAX_ASK_WORDS} words")
        elif s.ask:
            bad("slots", f"{s.name}: an optional slot never asks")
        if isinstance(s.default, str) and s.default.startswith("derive:") and not s.default[7:].isidentifier():
            bad("slots", f"{s.name}: derive: needs a function name")
        if s.from_attachment and s.kind != "attachment":
            bad("slots", f"{s.name}: from_attachment only on an attachment slot")
        if s.kind == "attachment" and not s.from_attachment:
            bad("slots", f"{s.name}: an attachment slot is filled from the message's photo")
        if s.limit is not None and not (isinstance(s.limit, tuple) and len(s.limit) == 2):
            bad("slots", f"{s.name}: limit is (content kind, field)")

    if not isinstance(skill.rules, tuple) or not all(isinstance(r, str) and RULE_RE.fullmatch(r) for r in skill.rules):
        bad("rules", "must be a tuple of rule ids (lower case, hyphens)")
    if len(set(skill.rules)) != len(skill.rules):
        bad("rules", "duplicate rule id")
    if not callable(skill.plan):
        bad("plan", "must be a function plan(slots, ctx) -> list of {op, args}")
    if not isinstance(skill.edits, tuple) or not all(
            isinstance(e, tuple) and len(e) == 2 and all(isinstance(x, str) and x for x in e) for e in skill.edits):
        bad("edits", "must be a tuple of (file, key path)")
    else:
        for file, _path in skill.edits:
            content_file = file.startswith("hass/content/") and file.endswith(".json")
            if content_file and coll_files is not None and file[13:-5] not in coll_files.values():
                bad("edits", f"{file} is not a content file the editor writes")
            elif not content_file and not file.startswith("storefront-mockup/"):
                bad("edits", f"{file} must be under hass/content/ or a generated storefront-mockup/ file")
    se = skill.side_effects
    if not isinstance(se, tuple) or not se or any(x not in SIDE_EFFECTS for x in se):
        bad("side_effects", f"must be a non-empty tuple from {SIDE_EFFECTS}")
    elif "none" in se and len(se) > 1:
        bad("side_effects", "'none' cannot be combined")
    if not (skill.preview in PREVIEWS or (isinstance(skill.preview, str) and re.fullmatch(r"product:\S.*", skill.preview))):
        bad("preview", f"must be product:<query> or one of {PREVIEWS}")
    if skill.approval not in APPROVALS:
        bad("approval", f"must be one of {APPROVALS}")
    if skill.live_class not in LIVE_CLASSES:
        bad("live_class", f"must be one of {LIVE_CLASSES}")
    if isinstance(skill.undo, Undo):
        if skill.undo.mode not in UNDO_MODES or not (isinstance(skill.undo.residue, str) and skill.undo.residue.strip()):
            bad("undo", f"mode in {UNDO_MODES} and a residue sentence ('none' if nothing stays)")
    else:
        bad("undo", "must be an Undo")
    if not isinstance(skill.refuse, tuple) or not all(
            isinstance(r, tuple) and len(r) == 2 and all(isinstance(x, str) and x.strip() for x in r)
            for r in skill.refuse):
        bad("refuse", "must be a tuple of (condition, fixed owner reply)")
    if not (isinstance(skill.cases, str) and CASES_RE.fullmatch(skill.cases)):
        bad("cases", "must be hass/tests/fixtures/skills/<group>/<name>.jsonl")
    elif Path(skill.cases).stem != skill.name or Path(skill.cases).parent.name == "":
        bad("cases", "file name must be <skill name>.jsonl")
    if not (isinstance(skill.version, int) and not isinstance(skill.version, bool) and skill.version >= 1):
        bad("version", "must be an integer of at least 1")

    # Read-only skills may not plan an op and need no approval; a skill that plans needs the owner's yes.
    if skill.approval == "none":
        if skill.live_class != "read-only":
            bad("live_class", "a skill without approval is read-only")
        if isinstance(skill.undo, Undo) and skill.undo.mode == "revert":
            bad("undo", "a skill without approval changes no content, so there is nothing to revert")
        if skill.edits:
            bad("edits", "a skill without approval declares no content edits")
    elif skill.live_class == "read-only":
        bad("live_class", "read-only needs approval 'none'")
    publishes = any(isinstance(e, tuple) and e and str(e[0]).startswith("storefront-mockup/") for e in skill.edits or ())
    if skill.approval == "owner-yes" and skill.preview == "none" and (skill.live_class != "private-only" or publishes):
        bad("preview", "'none' only for read-only skills, or a private-only skill that edits no site file")  # AV1109-04: stock.restock
    if skill.approval == "owner-yes" and not skill.edits:
        bad("edits", "a skill that asks for approval declares what it edits")
    return out


def lint_plan_output(skill, ops, ops_registry) -> list:
    """Problems with one golden plan result: only registry ops, at most MAX_OPS, none from a read-only skill."""
    out = []
    if not isinstance(ops, list) or not all(isinstance(o, dict) and set(o) == {"op", "args"} for o in ops):
        return [f"{skill.name}: plan: must return a list of {{op, args}}"]
    if len(ops) > MAX_OPS:
        out.append(f"{skill.name}: plan: more than {MAX_OPS} ops")
    if skill.approval == "none" and ops:
        out.append(f"{skill.name}: plan: a read-only skill plans no op")
    for o in ops:
        if o["op"] not in ops_registry:
            out.append(f"{skill.name}: plan: {o['op']} is not a registered op")
    return out


def lint_cases(skill, repo_root) -> list:
    """Case file checks (spec 2.9 level 1): at least 10 rows, 2 refusals, 1 undo, version matches. A missing file is one problem."""
    import json
    path = Path(repo_root) / skill.cases
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return [f"{skill.name}: cases: {skill.cases} is missing"]
    out, rows = [], []
    for i, ln in enumerate(lines, 1):
        try:
            row = json.loads(ln)
        except ValueError:
            out.append(f"{skill.name}: cases: line {i} is not JSON")
            continue
        if not isinstance(row, dict):
            out.append(f"{skill.name}: cases: line {i} is not an object")
            continue
        rows.append(row)
    if len(rows) < MIN_CASE_ROWS:
        out.append(f"{skill.name}: cases: at least {MIN_CASE_ROWS} rows")
    if sum(1 for r in rows if r.get("kind") == "refuse") < MIN_REFUSAL_ROWS:
        out.append(f"{skill.name}: cases: at least {MIN_REFUSAL_ROWS} refusal rows")
    if sum(1 for r in rows if r.get("undo") is True or r.get("kind") == "undo") < MIN_UNDO_ROWS:
        out.append(f"{skill.name}: cases: at least {MIN_UNDO_ROWS} undo row")
    if any(r.get("version") != skill.version for r in rows):
        out.append(f"{skill.name}: cases: rows were written for another version")
    return out


@dataclass
class Registry:
    """Loaded skills by name. Only active skills answer ``get``; retired ones stay listed so a name is never reused."""
    skills: dict = field(default_factory=dict)

    def get(self, name):
        s = self.skills.get(name)
        return s if s is not None and s.status == "active" else None

    def active(self) -> tuple:
        return tuple(s for _n, s in sorted(self.skills.items()) if s.status == "active")
