"""Interpreter output checked against the ops registry (NB-AV-01) before anything reaches the editor.

check() is pure: an op, argument name or value type the registry does not allow, or a ``revises`` code that is not
waiting, becomes one owner question naming the field. Value checks (real dates, makers, files) stay in the editor.
"""

STRING_KINDS = ("id", "maker_key", "text", "url", "enum", "date", "time", "image")
NAME_CUT = 40
AGAIN = "Could you say it another way?"
WANTS = {"bool": "a yes/no", "int": "a whole number", "text_list": "a list of text"}


def _clean(value) -> str:
    """A name safe to show the owner: control characters removed, cut to NAME_CUT characters."""
    text = "".join(c for c in str(value) if not (ord(c) < 32 or 127 <= ord(c) < 160))
    return text if len(text) <= NAME_CUT else text[:NAME_CUT - 3] + "..."


def _kind_ok(kind: str, value) -> bool:
    if kind in STRING_KINDS: return isinstance(value, str)
    if kind == "text_list": return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if kind == "bool": return isinstance(value, bool)
    if kind == "int": return isinstance(value, int) and not isinstance(value, bool)
    return False  # a kind this check does not know is never passed through


def _problem(result: dict, registry, pending_codes):
    calls = result["ops"]
    if not calls: return "I did not find a change in that message. What would you like to change?"
    for n, call in enumerate(calls, 1):
        if not (isinstance(call, dict) and set(call) == {"op", "args"} and isinstance(call["op"], str)
                and isinstance(call["args"], dict)):
            return f"I could not read change {n} of that message. {AGAIN}"
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
    code = result["revises"]
    if code is not None and code not in pending_codes:
        return f"I could not find draft {_clean(code)} waiting; reply with the change again."
    return None


def check(result: dict, registry, pending_codes) -> dict:
    """``result`` unchanged when it is fine (or is already a question/unsupported reply), else {"question": text}."""
    if "ops" not in result: return result
    problem = _problem(result, registry, set(pending_codes))
    return result if problem is None else {"question": problem}
