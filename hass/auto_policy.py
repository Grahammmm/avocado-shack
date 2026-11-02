"""H23 policy: which single draft change could skip approval if the owner opted in (UNWIRED).

Nothing imports this module: the approval flow is unchanged and no setting reads it. The opt-in itself needs
H18-H22 and the owner first. The eligible set is closed on purpose: an op added to the registry later needs
approval until someone edits ``ELIGIBLE`` here. Undo (``history.revert``) is never eligible.
"""

from __future__ import annotations

ELIGIBLE = ("product.set_availability", "store.confirm_selection")  # the daily shelf-check actions
MAX_PRODUCTS = 20
_LISTS = ("yes", "limited", "no")


def qualifies(ops, opted_in, paused) -> tuple[bool, str]:
    """``ops`` is a draft's list of ``{"op": name, "args": {...}}``; returns ``(allowed, reason)``. Never raises: a
    pause flag other than ``False`` is "changes are paused", a non-list or misshaped selection draft is "draft
    unreadable", an opt-in that is not a list/tuple/set of str is "opt-in list unreadable"."""
    if paused is not False:
        return False, "changes are paused"
    if not isinstance(ops, (list, tuple)):
        return False, "draft unreadable"
    if not isinstance(opted_in, (list, tuple, set, frozenset)) or not all(isinstance(n, str) for n in opted_in):
        return False, "opt-in list unreadable"
    if len(ops) != 1:
        return False, "more than one change" if ops else "no change"
    call = ops[0]
    name = call.get("op") if isinstance(call, dict) else None
    if name not in ELIGIBLE:
        return False, "needs approval"
    if name not in opted_in:
        return False, "not opted in"
    if name == "store.confirm_selection":
        args = call.get("args")
        lists = [args[k] for k in _LISTS if k in args] if isinstance(args, dict) else None
        if lists is None or not all(isinstance(v, (list, tuple)) and all(isinstance(i, str) for i in v) for v in lists):
            return False, "draft unreadable"
        total = sum(len(v) for v in lists)
        if total > MAX_PRODUCTS:
            return False, "too many products at once"
    return True, "opted in"


def check_opt_in(names) -> list[str]:
    """Problems with a list of opted-in op names; empty when fine (for a future settings validator)."""
    if not isinstance(names, (list, tuple)):
        return ["opt-in list is not a list"]
    problems, seen = [], set()
    for name in names:
        if not isinstance(name, str):
            problems.append(f"{name!r} is not a name")
        else:
            if name not in ELIGIBLE:
                problems.append(f"{name} cannot be automatic")
            if name in seen:
                problems.append(f"{name} is listed twice")
            seen.add(name)
    return problems
