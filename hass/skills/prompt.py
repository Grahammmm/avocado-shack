"""The Skills block of the interpreter prompt (SKILLS-FW-2).

``skills_section(skills, candidates)`` returns the generated block that ``interpreter_prompt.build`` appends after
the Store section. Pure and deterministic: the same skills and candidates give the same bytes, with no clock, env
or I/O. With no skills it returns "" so the prompt is byte-identical to the one before skills existed.

The block holds the reply contract for skills, full detail (summary, slots, three trigger examples) for the router's
top candidates, and one ``name - label`` line for every other skill. It is capped at ``MAX_PROMPT_BYTES`` (6 KiB):
candidate detail is shortened first, then catalog lines are left off.
"""
from __future__ import annotations

from hass.content_model import AVAILABILITY
from hass.skills.model import MAX_OPS, MAX_PROMPT_BYTES, Registry

EXAMPLES_FULL, EXAMPLES_SHORT = 3, 1

CONTRACT = (
    'Skills. Prefer a skill when one fits. Reply with one of these JSON objects (a skill reply may also carry '
    '\"revises\", a pending draft code or null):\n'
    '{\"skill\": \"<name>\", \"slots\": {...}}\n'
    f'{{\"calls\": [{{\"skill\": \"<name>\", \"slots\": {{...}}}}, ...]}} for several asks in one message (at most {MAX_OPS})\n'
    '{\"skill\": \"none\", \"summary\": \"<one line of what was asked>\"} when no skill fits\n'
    "Use only the skill names and slot names listed below. Fill a slot with the owner's own words; leave out a slot "
    "you cannot fill and never invent a value. Code checks every slot and asks the owner for what is missing.")


def _items(skills) -> list:
    if isinstance(skills, Registry):
        return list(skills.active())
    return [s for s in sorted(skills or (), key=lambda s: s.name) if getattr(s, "status", "active") == "active"]


# RF0814-12: the one structured kind is spelled out, with a JSON example and the canonical words, so the model can fill it.
STOCK_ITEMS_SHAPE = (' (a JSON list of {"product": "<product id>", "availability": ' + "|".join(f'"{w}"' for w in AVAILABILITY)
                     + '}, e.g. [{"product": "photo-product-001", "availability": "no"}])')


def _slot_text(slot) -> str:
    req = "required" if slot.required is True else "optional" if slot.required is False else f"required {slot.required.replace(':', ' ')}"
    default = f", default {slot.default}" if slot.default is not None else ""
    shape = STOCK_ITEMS_SHAPE if slot.kind == "stock_items" else ""
    return f"{slot.name}: {slot.kind}, {req}{default}{shape}"


def _detail(skill, examples, summary=True) -> str:
    lines = [f"- {skill.name} - {skill.label}"]
    if summary:
        lines.append(f"  {skill.summary}")
    lines.append("  slots: " + ("; ".join(_slot_text(s) for s in skill.slots) if skill.slots else "(none)"))
    if examples:
        lines.append("  e.g. " + " | ".join(f'"{t.text}"' for t in skill.triggers[:examples]))
    return "\n".join(lines)


def _names(candidates) -> list:
    return [c[0] if isinstance(c, (tuple, list)) else c for c in candidates or ()]


def _assemble(detailed, others, examples, summary, keep_others) -> str:
    parts = [CONTRACT]
    if detailed:
        parts.append("Likely skills for this message:\n" + "\n".join(_detail(s, examples, summary) for s in detailed))
    if others:
        shown = others[:keep_others]
        rows = [f"- {s.name} - {s.label}" for s in shown]
        if len(shown) < len(others):
            rows.append(f"... and {len(others) - len(shown)} more skills")
        parts.append("Other skills:\n" + "\n".join(rows))
    return "\n\n".join(parts)


def skills_section(skills, candidates=()) -> str:
    """The Skills block for the active ``skills`` (a Registry or an iterable of Skill); ``candidates`` are the router's
    top picks, names or (name, score) pairs. Returns "" when there is no active skill."""
    items = _items(skills)
    if not items:
        return ""
    wanted = _names(candidates)
    by_name = {s.name: s for s in items}
    detailed = [by_name[n] for n in dict.fromkeys(wanted) if n in by_name]
    others = [s for s in items if s not in detailed]
    for examples, summary in ((EXAMPLES_FULL, True), (EXAMPLES_SHORT, True), (0, True), (0, False)):
        text = _assemble(detailed, others, examples, summary, len(others))
        if len(text.encode("utf-8")) <= MAX_PROMPT_BYTES:
            return text + "\n"
    keep = len(others)
    while keep > 0:  # candidate detail is already at its smallest: now leave catalog lines off, last first
        keep -= 1
        text = _assemble(detailed, others, 0, False, keep)
        if len(text.encode("utf-8")) <= MAX_PROMPT_BYTES:
            return text + "\n"
    return _assemble(detailed[:1], [], 0, False, 0)[:MAX_PROMPT_BYTES].rsplit("\n", 1)[0] + "\n"
