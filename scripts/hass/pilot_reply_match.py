#!/usr/bin/env python3
"""Classify one captured NPP reply offline; a text match is not live verification."""

import argparse
import json
from pathlib import Path
import re
import sys


DEFAULT_TEMPLATES = (Path(__file__).resolve().parents[2]
                     / "hass/npp/assets/hass-npp-reply/reply-templates.json")
PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z_0-9]*)\}")
METADATA = {"about", "caps", "rule", "existing", "never_say"}
TOKENS = {"code": r"\S+?", "n": r"[0-9]+", "url": r"\S+"}
# Free-text fields can contain spaces, but must not absorb another sentence.
FIELD = r"(?:(?![.!?]\s)[^\r\n?!])+?"


class MatchError(ValueError):
    """A fixed diagnostic safe to print without disclosing input."""


def template_strings(document, prefix=""):
    for name, value in document.items():
        key = prefix + name
        if name in METADATA or name.endswith("_note") or key == "brackets.compose":
            continue
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9]*", name):
            raise MatchError("invalid-templates")
        if isinstance(value, dict):
            yield from template_strings(value, key + ".")
        elif isinstance(value, str) and value:
            yield key, value


def compile_template(text):
    pieces = PLACEHOLDER.split(text)
    seen = set()
    pattern = re.escape(pieces[0])
    for name, literal in zip(pieces[1::2], pieces[2::2]):
        pattern += (f"(?P={name})" if name in seen
                    else f"(?P<{name}>{TOKENS.get(name, FIELD)})")
        pattern += re.escape(literal)
        seen.add(name)
    return re.compile(pattern)


def classify(reply, document):
    if not isinstance(document, dict) or not isinstance(document.get("caps"), dict):
        raise MatchError("invalid-templates")
    char_cap = document["caps"].get("question_max_chars")
    count_cap = document["caps"].get("max_questions_per_reply")
    if any(type(cap) is not int or cap < 0 for cap in (char_cap, count_cap)):
        raise MatchError("invalid-templates")

    patterns = [(key, compile_template(text)) for key, text in template_strings(document)]
    matches = [(key, match) for key, pattern in patterns if (match := pattern.fullmatch(reply))]
    if len(matches) > 1:
        raise MatchError("ambiguous-template")

    is_question = bool(matches and matches[0][0].startswith("questions."))
    question_count = int(is_question)
    if not matches:
        # Runtime joins questions with a space. Diagnose cap breaches on that
        # shape, but never accept a concatenation as a single template match.
        parts = re.split(r"(?<=\?) ", reply)
        questions = [p for key, p in patterns if key.startswith("questions.")]
        if len(parts) > 1 and all(any(p.fullmatch(part) for p in questions) for part in parts):
            question_count = len(parts)
    if question_count > count_cap:
        raise MatchError("max_questions_per_reply")
    if question_count and len(reply) > char_cap:
        raise MatchError("question_max_chars")
    if not matches:
        raise MatchError("no-template")

    key, match = matches[0]
    if key == "prompts.ready":
        fields = match.groupdict()
        if "code" not in fields or "n" not in fields:
            raise MatchError("invalid-templates")
        return f"{key}\nversion: {fields['n']}\ncode length: {len(fields['code'])}"
    if key == "confirm.posted":
        if "url" not in match.groupdict():
            raise MatchError("invalid-templates")
        return f"{key}\nurl: present"
    return key


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reply", type=Path, required=True, help="UTF-8 reply file")
    parser.add_argument("--templates", type=Path, default=DEFAULT_TEMPLATES,
                        help="override the repository's reply-templates.json")
    args = parser.parse_args(argv)
    try:
        try:
            document = json.loads(args.templates.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            raise MatchError("invalid-templates") from None
        try:
            reply = args.reply.read_text(encoding="utf-8").removesuffix("\n")
        except (OSError, UnicodeError):
            raise MatchError("unreadable-reply") from None
        print(classify(reply, document))
    except MatchError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
