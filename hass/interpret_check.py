"""Interpreter output checked against the ops registry (NB-AV-01) before anything reaches the editor.

check() is pure: an op, argument name or value type the registry does not allow, or a ``revises`` code that is not
waiting, becomes one owner question naming the field. Value checks (real dates, makers, files) stay in the editor.
Names shown to the owner contain only visible characters (no controls, zero-width, direction or line-separator marks).
The same change listed twice (same op, equal args in any key order, spacing ignored) becomes one question naming the first repeated
pair; it is checked after the shape check and before op/field checks, so a repeated unknown op is reported as a repeat.
"""

import json
import unicodedata

from hass.content_model import FORBIDDEN_TEXT
from hass.editor import MAX_OPS

HIDDEN = {"Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"}
STRING_KINDS = ("id", "maker_key", "text", "url", "enum", "date", "time", "image")
NAME_CUT = 40
AGAIN = "Could you say it another way?"
UNDO_GUIDANCE = ("To undo a change, send undo for the latest change, undo <code> for a specific change, "
                 "or history to see recent changes.")
PRICE_REPLY = "The website does not show prices, so nothing was drafted. Send the change without the price."  # AV0222-03
PLAIN_TEXT_REPLY = ("The website only accepts plain text, so nothing was drafted. "
                    "Send the change without HTML or template marks.")
WANTS = {"bool": "a yes/no", "int": "a whole number", "text_list": "a list of text"}


def _clean(value) -> str:
    """A name safe to show the owner: invisible characters removed, cut to NAME_CUT characters, "(unnamed)" if empty."""
    text = "".join(c for c in str(value) if unicodedata.category(c) not in HIDDEN) or "(unnamed)"
    return text if len(text) <= NAME_CUT else text[:NAME_CUT - 3] + "..."


def _spaced(v):  # RF1050-7: spacing folded for the repeat key only (case kept); never written back to the result
    return " ".join(v.split()) if isinstance(v, str) else [_spaced(x) for x in v] if isinstance(v, list) else v


def _kind_ok(kind: str, value) -> bool:
    if kind in STRING_KINDS: return isinstance(value, str)
    if kind == "text_list": return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if kind == "bool": return isinstance(value, bool)
    if kind == "int": return isinstance(value, int) and not isinstance(value, bool)
    return False  # a kind this check does not know is never passed through


def _forbidden_reply(kind: str, value):
    """AV0222-03: PRICE_REPLY for '$', PLAIN_TEXT_REPLY for the other FORBIDDEN_TEXT marks, in a text or text_list value."""
    for text in ([value] if kind == "text" else value if kind == "text_list" else []):
        if "$" in text: return PRICE_REPLY
        if any(bad in text for bad in FORBIDDEN_TEXT): return PLAIN_TEXT_REPLY
    return None


def _problem(result: dict, registry, pending_codes):
    calls = result["ops"]
    if not calls: return "I did not find a change in that message. What would you like to change?"
    if len(calls) > MAX_OPS:  # RF2030-7: counted before shapes, repeats and the revises code
        return (f"That is {len(calls)} changes in one message; I can take at most {MAX_OPS} at a time. "
                "Please send them in smaller groups.")
    for n, call in enumerate(calls, 1):
        if not (isinstance(call, dict) and set(call) == {"op", "args"} and isinstance(call["op"], str)
                and isinstance(call["args"], dict)):
            return f"I could not read change {n} of that message. {AGAIN}"
    if any(call["op"] == "history.revert" for call in calls): return UNDO_GUIDANCE  # AV0007-02: whole result refused
    seen = {}
    for i, call in enumerate(calls, 1):
        try: key = (call["op"], json.dumps({k: _spaced(v) for k, v in call["args"].items()}, sort_keys=True, ensure_ascii=False))
        except (TypeError, ValueError, RecursionError): continue  # args that cannot be compared are never called the same
        if key in seen:
            return f"Changes {seen[key]} and {i} in that message are the same. Did you mean to change something else? {AGAIN}"
        seen[key] = i
    for call in calls:
        op = registry.get(call["op"])
        if op is None:
            return f'I could not turn that into a change I know (unknown change type "{_clean(call["op"])}"). {AGAIN}'
        for name, value in call["args"].items():
            label = f"{_clean(call['op'])}.{_clean(name)}"
            arg = op.args.get(name)
            if arg is None:
                return f'I could not turn that into a change I know (unknown field "{label}"). {AGAIN}'
            if not _kind_ok(arg.kind, value):
                return f"{label} should be {WANTS.get(arg.kind, 'text')}. {AGAIN}"
            reply = _forbidden_reply(arg.kind, value)
            if reply: return reply
    code = result["revises"]
    if code is not None and code not in pending_codes:
        return f"I could not find draft {_clean(code)} waiting; reply with the change again."
    return None


def check(result: dict, registry, pending_codes) -> dict:
    """``result`` unchanged when it is fine (or is already a question/unsupported reply), else {"question": text}."""
    if "ops" not in result: return result
    problem = _problem(result, registry, set(pending_codes))
    return result if problem is None else {"question": problem}
