"""Hass skills (SKILLS-FW-1): the registry and the lint.

``load_skills()`` imports every module in this package and merges its ``SKILLS`` tuple, the way
``hass.ops.load_registry`` does for ops: add a module, edit no list. A duplicate skill name raises.
``skill_lint(skills, ops_registry)`` returns the list of problems (empty = clean). See docs/hass/SKILLS.md.
"""
from __future__ import annotations

import importlib
import pkgutil

from hass import editor
from hass.skills.model import (MAX_OPS, SLOT_KINDS, Registry, Skill, Slot, Trigger, Undo,  # noqa: F401
                               _fold, lint_cases, lint_plan_output, lint_skill)

__all__ = ["MAX_OPS", "SLOT_KINDS", "Registry", "Skill", "Slot", "Trigger", "Undo", "load_skills", "skill_lint"]


def load_skills() -> Registry:
    """Import every module in hass.skills and merge their SKILLS; duplicate names raise ValueError."""
    registry = Registry()
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        for skill in getattr(module, "SKILLS", ()):
            if skill.name in registry.skills:
                raise ValueError(f"duplicate skill name {skill.name!r}")
            registry.skills[skill.name] = skill
    return registry


def skill_lint(skills, ops_registry, *, repo_root=None, golden=None) -> list:
    """Level-1 lint (spec 2.9). ``skills`` is a Registry or an iterable of Skill.

    Always: every mandatory field, unique names, no trigger text in two skills. ``golden`` maps a skill name to a list of
    slot dicts whose plans are run and checked (registered ops only, at most 20, none from a read-only skill).
    With ``repo_root`` the case files are checked too (rows, refusals, undo, version); a later card turns that on for
    every skill once the catalog fixtures exist."""
    items = list(skills.skills.values()) if isinstance(skills, Registry) else list(skills)
    problems, seen_names, seen_triggers = [], set(), {}
    for skill in items:
        name = getattr(skill, "name", "?")
        if name in seen_names:
            problems.append(f"{name}: name used twice")
        seen_names.add(name)
        problems += lint_skill(skill, ops_registry, editor.COLLECTION_FILE)
        if not isinstance(skill, Skill):
            continue

        for t in skill.triggers:
            key = _fold(getattr(t, "text", ""))
            if key in seen_triggers and seen_triggers[key] != name:
                problems.append(f"{name}: triggers: {t.text!r} is also a trigger of {seen_triggers[key]}")
            seen_triggers.setdefault(key, name)
        for slots in (golden or {}).get(skill.name, ()):
            try:
                out = skill.plan(dict(slots), None)
            except Exception as exc:  # a plan must not raise on a golden input
                problems.append(f"{name}: plan: raised {type(exc).__name__}")
                continue
            problems += lint_plan_output(skill, out, ops_registry)
        if repo_root is not None:
            problems += lint_cases(skill, repo_root)
    return problems
