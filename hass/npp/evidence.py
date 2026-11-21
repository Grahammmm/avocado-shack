"""Pure builder and validator for the version-1 NPP receipt evidence.

Pass only structured evidence, never source text. Model fields are identifiers,
not provider responses. Approval times may be nonnegative millisecond numbers
or ISO 8601 instants (use Z for UTC, since positive offsets fail the phone guard).
"""

import re
from copy import deepcopy
from datetime import datetime
from math import isfinite
from typing import Any


_PRIVATE = re.compile(r"@|\+\d|\$|/home/")
_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,47}")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*")
_CHANGE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_HEX = re.compile(r"[a-fA-F0-9]{7,64}")
_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|-\d{2}:\d{2})")


def _matches(pattern):
    return lambda value: type(value) is str and pattern.fullmatch(value) is not None


def _one_of(*choices):
    return lambda value: type(value) is str and value in choices


def _optional(rule):
    return lambda value: value is None or rule(value)


def _millis(value):
    return (type(value) is int and value >= 0
            or type(value) is float and isfinite(value) and value >= 0)


def _approved_at(value):
    if _millis(value):
        return True
    if type(value) is not str or not _INSTANT.fullmatch(value):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


_NAME_OK = _matches(_NAME)
_STAGE = dict(stage=_one_of(*(f"S{n}" for n in range(1, 14))),
              started_ms=_millis, ended_ms=_millis,
              outcome=_one_of("ok", "fallback", "failed", "skipped"),
              code=_optional(_NAME_OK))
_MODEL_FIELDS = dict(step=_NAME_OK, pinned=_matches(_MODEL),
                     returned=_optional(_matches(_MODEL)), drift=lambda value: type(value) is bool)
_CHECK = dict(name=_NAME_OK, verdict=_one_of("pass", "fail"),
              private=_optional(_one_of("match", "no-match")))
_APPROVAL = dict(version=lambda value: type(value) is int and value > 0,
                 role=_one_of("G", "Mike", "owner"), approved_at=_approved_at,
                 change_id=_matches(_CHANGE), draft_hash=_matches(_HEX))
_PUBLISH = dict(change_id=_matches(_CHANGE), commit=_optional(_matches(_HEX)),
                live_verify=_optional(_one_of("seen", "pending", "failed")))
_RECORDS = dict(stages=_STAGE, models=_MODEL_FIELDS, checks=_CHECK,
                approval=_APPROVAL, publish=_PUBLISH)
_DOC_KEYS = _RECORDS.keys() | {"fallbacks", "evidence_version"}


def _accepts(rule, value):
    # All allowed fields are scalars; non-scalar values are refused by their rules.
    return not (type(value) is str and _PRIVATE.search(value)) and rule(value)


def _drift(pinned, returned):
    return returned is not None and returned != pinned


def _record_problems(section, row):
    schema = _RECORDS[section]
    if type(row) is not dict or row.keys() != schema.keys():
        return [f"{section}: unexpected object shape"]
    problems = [f"{section}.{key}: invalid value" for key, rule in schema.items()
                if not _accepts(rule, row[key])]
    if problems:
        return problems
    if section == "stages" and row["ended_ms"] < row["started_ms"]:
        return ["stages: reversed times"]
    if section == "models" and row["drift"] != _drift(row["pinned"], row["returned"]):
        return ["models.drift: inconsistent value"]
    return []


def role_for(chat, owner_names):
    """Project a configured chat's name to a fixed receipt role."""
    name = owner_names.get(chat) if owner_names is not None else None
    return {"g": "G", "mike": "Mike"}.get(name.lower(), "owner") if type(name) is str else "owner"


def validate(doc):
    """Return schema problems without quoting any input value or unknown key."""
    if type(doc) is not dict or doc.keys() != _DOC_KEYS:
        return ["evidence: unexpected object shape"]
    problems = []
    if type(doc["evidence_version"]) is not int or doc["evidence_version"] != 1:
        problems.append("evidence_version: invalid value")
    for section in ("stages", "models", "checks", "fallbacks"):
        rows = doc[section]
        if type(rows) is not list:
            problems.append(f"{section}: expected list")
        elif section == "fallbacks":
            if any(not _accepts(_NAME_OK, code) for code in rows):
                problems.append("fallbacks: invalid code")
        else:
            for row in rows:
                problems.extend(_record_problems(section, row))
    for section in ("approval", "publish"):
        if doc[section] is not None:
            problems.extend(_record_problems(section, doc[section]))
    return problems


class Evidence:
    """Collect validated values; approval and publish each keep the latest record."""

    def __init__(self):
        self._rows: dict[str, list[dict]] = dict(stages=[], models=[], checks=[])
        self._latest: dict[str, dict | None] = dict(approval=None, publish=None)
        self._fallbacks = set()

    def _record(self, section, **row):
        problems = _record_problems(section, row)
        if problems:
            raise ValueError(problems[0])
        if section in self._latest:
            self._latest[section] = row
        else:
            self._rows[section].append(row)

    def stage(self, stage, started_ms, ended_ms, outcome, code=None):
        self._record("stages", stage=stage, started_ms=started_ms, ended_ms=ended_ms,
                     outcome=outcome, code=code)

    def model(self, step, pinned, returned):
        # Reject non-identifiers before comparing values or recording drift.
        if type(pinned) is not str or (returned is not None and type(returned) is not str):
            raise ValueError("models: expected identifiers")
        self._record("models", step=step, pinned=pinned, returned=returned,
                     drift=_drift(pinned, returned))

    def fallback(self, code):
        if not _accepts(_NAME_OK, code):
            raise ValueError("fallbacks: invalid code")
        self._fallbacks.add(code)

    def check(self, name, verdict, private=None):
        self._record("checks", name=name, verdict=verdict, private=private)

    def approval(self, version, role, approved_at, change_id, draft_hash):
        self._record("approval", version=version, role=role, approved_at=approved_at,
                     change_id=change_id, draft_hash=draft_hash)

    def publish(self, change_id, commit=None, live_verify=None):
        self._record("publish", change_id=change_id, commit=commit, live_verify=live_verify)

    def doc(self) -> dict[str, Any]:
        """Return a detached JSON-ready snapshot, not mutable builder state."""
        return deepcopy(dict(evidence_version=1, **self._rows, **self._latest,
                             fallbacks=sorted(self._fallbacks)))
