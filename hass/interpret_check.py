"""Interpreter output checked against the ops registry (NB-AV-01) before anything reaches the editor.

check() is pure: an op, argument name or value type the registry does not allow, or a ``revises`` code that is not
waiting, becomes one owner question naming the field. An enum value that is not one of the op's choices is asked about
in site words (shelf, availability) before the editor (AV0222-02). Other value checks (real dates, makers, files) stay in the editor.
Names shown to the owner contain only visible characters (no controls, zero-width, direction or line-separator marks).
The same change listed twice (same op, equal args in any key order, spacing ignored) becomes one question naming the first repeated
pair; it is checked after the shape check and before op/field checks, so a repeated unknown op is reported as a repeat.
"""

import json
import unicodedata

from hass import voice
from hass.content_model import AVAILABILITY, CATEGORIES, FORBIDDEN_TEXT, SHELF_LABELS
from hass.editor import MAX_OPS

HIDDEN = {"Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"}
STRING_KINDS = ("id", "maker_key", "text", "url", "enum", "date", "time", "image")
NAME_CUT = 40
AGAIN = "Could you say it another way?"
UNDO_GUIDANCE = "To undo the last change, say " + voice.quote("undo") + ". To see what we changed lately, say " + voice.quote("history") + "."
PRICE_REPLY = "The website doesn't show prices, so I haven't made any change. Could you send it without the price?"  # AV0222-03
PLAIN_TEXT_REPLY = ("The website only takes plain words, so I haven't made any change. "
                    "Could you send it again without special marks?")
CANT_DO_YET = "I can't do that kind of change yet. You can ask Graham."
WANTS = {"bool": "yes or no", "int": "a whole number", "text_list": "a list of words"}


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


def _enum_question(op_name: str, arg_name: str, value, choices) -> str:
    """One question for an enum value outside the op's choices; site words only for the canonical shelf/availability args."""
    choices = tuple(choices or ())
    if op_name in ("product.add", "product.edit") and arg_name == "category" and choices == CATEGORIES:
        shelves = [SHELF_LABELS[c] for c in CATEGORIES]
        return f"There is no {_clean(value)} shelf. Which shelf: {', '.join(shelves[:-1])} or {shelves[-1]}?"
    if op_name == "product.set_availability" and arg_name == "available" and choices == AVAILABILITY:
        return "Should it say Available today, Limited or Sold out?"
    if not choices: return f"I can't pick {voice.field_phrase(arg_name)} from a list. {AGAIN}"
    return f"For {voice.field_phrase(arg_name)}, I can use: {', '.join(_clean(voice.value_words(c, arg_name)) for c in choices)}. {AGAIN}"


def _problem(result: dict, registry, pending_codes):
    calls = result["ops"]
    if not calls: return "I couldn't find a change in that message. What would you like to change?"
    if len(calls) > MAX_OPS:  # RF2030-7: counted before shapes, repeats and the revises code
        return "That's a lot of changes at once. Could you send them a few at a time?"
    for n, call in enumerate(calls, 1):
        if not (isinstance(call, dict) and set(call) == {"op", "args"} and isinstance(call["op"], str)
                and isinstance(call["args"], dict)):
            return f"I couldn't read part of that message. {AGAIN}"
    if any(call["op"] == "history.revert" for call in calls): return UNDO_GUIDANCE  # AV0007-02: whole result refused
    seen = {}
    for i, call in enumerate(calls, 1):
        try: key = (call["op"], json.dumps({k: _spaced(v) for k, v in call["args"].items()}, sort_keys=True, ensure_ascii=False))
        except (TypeError, ValueError, RecursionError): continue  # args that cannot be compared are never called the same
        if key in seen:
            return "Two of those changes are the same. Did you mean to change something else?"
        seen[key] = i
    for call in calls:
        op = registry.get(call["op"])
        if op is None:
            return CANT_DO_YET
        for name, value in call["args"].items():
            label = f"{_clean(call['op'])}.{_clean(name)}"
            arg = op.args.get(name)
            if arg is None:
                return CANT_DO_YET
            if not _kind_ok(arg.kind, value):
                return f"I need {voice.field_phrase(name)} as {WANTS.get(arg.kind, 'words')}. {AGAIN}"
            reply = _forbidden_reply(arg.kind, value)
            if reply: return reply
            if arg.kind == "enum" and value not in (arg.choices or ()):
                return _enum_question(call["op"], name, value, arg.choices)
    code = result["revises"]
    if code is not None and code not in pending_codes:
        return "I can't find that change any more. Could you tell me the change again?"
    return None


def check(result: dict, registry, pending_codes) -> dict:
    """``result`` unchanged when it is fine (or is already a question/unsupported reply), else {"question": text}."""
    if "ops" not in result: return result
    problem = _problem(result, registry, set(pending_codes))
    return result if problem is None else {"question": problem}
