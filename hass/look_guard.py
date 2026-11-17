"""HASS-SITE-LOOK-1 look guard (PLAN-v2 D): check(diff, owner_text) -> None or the refusal reason of a model's look diff.

Only the three templates and three stylesheets may change (generated pages are regenerated, never edited); no new, deleted,
renamed, binary or mode change; no added script/form/input/iframe/embed/object tag, on*= attribute, javascript: reference or
absolute/off-site URL in src, href, @import or url(...); no added or removed <meta>, <link>, <head> or CSP line; added visible
text passes claims.py and the live policy's COMMERCE_WORDS. Lines are judged after entity and CSS-escape decoding. Pure."""
from __future__ import annotations

import html
import re

from hass import claims
from hass.live_policy import COMMERCE_WORDS

MODEL_FILES = ("hass/templates/index.html", "hass/templates/hike/index.html", "hass/templates/info/index.html",
               "storefront-mockup/style.css", "storefront-mockup/hiking.css", "storefront-mockup/trail-explorer.css")
TAG = re.compile(r"<\s*/?\s*(?:script|form|input|iframe|embed|object|base|frame|frameset|applet|portal)(?![\w-])", re.I)
HANDLER = re.compile(r"(?<![\w-])on[a-z]+\s*=", re.I)
SCRIPTY = re.compile(r"javascript:|vbscript:|expression\(|-moz-binding|behavior:", re.I)  # judged with whitespace removed
PROTECTED = re.compile(r"<\s*/?\s*(?:meta|link|head)(?![\w-])|content-security-policy", re.I)
URL_VALUES = re.compile(r"""\b(?:src|href|srcset|action|poster|xlink:href)\s*=\s*["']?\s*([^"'\s>]*)"""
                        r"""|@import\s+(?:url\(\s*)?["']?\s*([^"')\s;]*)|url\(\s*["']?\s*([^"')\s]*)""", re.I)
OFF_SITE = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:|[/\\]{2})|\{\{", re.I)  # a scheme, //host, or a slot (value unknown)
CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})\s?|\\(.)")
VISIBLE_ATTR = re.compile(r"""\b(?:alt|title|aria-label|placeholder)\s*=\s*["']([^"']*)""", re.I)
CSS_CONTENT = re.compile(r"""content\s*:\s*(["'])(.*?)\1""", re.I)
HUNK = re.compile(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def _decode(line: str) -> str:
    """HTML entities then CSS escapes, twice, so a nested spelling cannot hide a construct."""
    for _ in range(2):
        line = CSS_ESCAPE.sub(lambda m: chr(min(int(m[1], 16), 0x10FFFF) or 0xFFFD) if m[1] else m[2], html.unescape(line))
    return line


def parse(diff: str):
    """[(path, added, removed)] of a plain unified diff, or a refusal reason. Hunk lines are counted from each @@ header,
    so a content line spelled like a header ("--- x") stays content."""
    files, old, left = [], None, [0, 0]
    for line in diff.splitlines():
        if left != [0, 0]:
            kind = line[:1] or " "
            if kind not in " +-\\" or (kind in " -" and not left[0]) or (kind in " +" and not left[1]): return "mode"
            left = [left[0] - (kind in " -"), left[1] - (kind in " +")]
            if kind in "+-": files[-1][1 if kind == "+" else 2].append(line[1:])
        elif old is not None:  # the line after "--- a/X" must be "+++ b/X": /dev/null or a rename is refused
            if not (line.startswith("+++ b/") and old.startswith("a/") and old[2:] == line[6:].strip()): return "mode"
            if old[2:] not in MODEL_FILES: return "path"
            files.append((old[2:], [], []))
            old = None
        elif line.startswith("--- "): old = line[4:].strip()
        elif (hunk := HUNK.match(line)) and files: left = [int(hunk[1] or 1), int(hunk[2] or 1)]
        elif not line.startswith(("diff --git ", "index ", "\\")): return "mode"  # mode, rename, binary or stray text
    return "mode" if left != [0, 0] or old is not None else files


def visible_text(path: str, lines) -> str:
    text = "\n".join(map(_decode, lines))
    if path.endswith(".css"): return "\n".join(m[2] for m in CSS_CONTENT.finditer(text))
    return "\n".join([re.sub(r"<[^>]*>|\{\{[^}]*\}\}", " ", text), *VISIBLE_ATTR.findall(text)])


def check(diff: str, owner_text: str) -> str | None:
    files = parse(diff)
    if isinstance(files, str): return files
    added, removed = [x for f in files for x in f[1]], [x for f in files for x in f[2]]
    if not added and not removed: return "empty"
    for line in map(_decode, added):
        if TAG.search(line): return "tag"
        if HANDLER.search(line): return "handler"
        if SCRIPTY.search(re.sub(r"[\s\x00-\x1f]+", "", line)): return "javascript"
        if any(OFF_SITE.search(v) for m in URL_VALUES.finditer(line) for v in m.groups() if v): return "url"
    if any(PROTECTED.search(_decode(x)) for x in added + removed): return "protected"
    now, was = ("\n".join(visible_text(f[0], f[i]) for f in files) for i in (1, 2))
    if claims.unstated({"records": [{"collection": "look", "key": "page", "before": {"text": was}, "after": {"text": now}}]},
                       owner_text, {}): return "claims"
    if len(COMMERCE_WORDS.findall(now)) > len(COMMERCE_WORDS.findall(was)): return "commerce"
    return None
