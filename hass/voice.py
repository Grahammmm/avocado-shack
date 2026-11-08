"""HASS-VOICE-1: the voice rules for everything Hass says to Mike, as a deterministic check.

The rules are written in plain words in docs/hass/VOICE.md. This module is the part that fails the build and stops a
bad message at the door: `check(text)` returns the list of broken rules (empty = fine). Pure: no I/O, no clock, no
model. `guard(text)` is what the outbox calls on every owner message: a message that breaks a rule is replaced by
SAFE_LINE and the caller logs it (hass/corrlog.py). `quote(text)` wraps words that are Mike's own (a product name he
typed, a caption he asked for): they are shown as he wrote them and the check leaves them alone.
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
SAFE_LINE = "I'm not sure how to put that. Could you say it another way?"
OPEN, CLOSE = "\ue000", "\ue001"  # private-use marks around words that are Mike's own; removed before sending
LONG_AFTER = 600  # characters; a longer message needs long_ok (he asked for a list, or it is a draft he must read)

# Whole words that Mike should never see. Matched case-insensitively on word boundaries.
BANNED_WORDS = (
    "interpreter", "model", "models", "cache", "cached", "commit", "commits", "queue", "queued", "relay", "api",
    "config", "configuration", "json", "sqlite", "database", "server", "backend", "endpoint", "token", "payload",
    "parse", "parser", "regex", "schema", "stack", "debug", "hash", "sha", "uuid", "boolean", "integer", "bytes",
    "exception", "traceback", "stderr", "stdout", "timeout", "http", "worktree", "repo", "repository", "branch",
    "deploy", "pipeline", "sandbox", "fixture", "operator", "admin", "selection", "metadata", "exif", "script",
    "daemon", "service", "reader", "error", "errors", "invalid", "unsupported", "glitch", "bug",
    "applied", "verified", "reverted", "rejected", "proposed", "ids", "id", "alias", "aliases", "drafted", "catalog",
    "variable", "syntax", "parameter", "argument", "null", "undefined", "retry", "retries",
)
BANNED_PHRASES = (  # these may have ordinary words inside, so they are matched as phrases
    "needs-details", "needs details", "approval-held", "not drafted", "fail closed", "fails closed", "failed closed",
    "state unknown", "not verified", "no change record", "generated file", "preview server", "label reader",
    "daily limit for reading", "the reader was not working",
)
_WORD_RE = re.compile(r"\b(" + "|".join(BANNED_WORDS) + r")\b", re.I)
_PHRASE_RE = re.compile("|".join(re.escape(p) for p in BANNED_PHRASES), re.I)

PATTERNS = (  # (rule name, regex). A hit anywhere outside quoted words breaks the rule.
    ("an id like photo-product-001", re.compile(r"\b(?=[a-z0-9-]*\d)[a-z]+(?:-[a-z0-9]+)+\b", re.I)),
    ("an internal name like product.set_photo", re.compile(r"\b(?:product|hike|route|store|maker|home|history|alias|cost)\.[a-z_]+\b", re.I)),
    ("a long code", re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,64}\b", re.I)),
    ("a count like 1 of 1000", re.compile(r"\b\d+\s+of\s+\d+\b", re.I)),
    ("a time with seconds", re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b")),
    ("a date written like a computer", re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2})?\b")),
    ("a time zone code", re.compile(r"\b(?:PST|PDT|UTC|GMT)\b|\+00:00|-0[78]:00")),
    ("a file name", re.compile(r"\b[\w-]+\.(?:json|py|png|jpe?g|html?|cjs|mjs|js|sqlite3?|db|md|txt|log|csv|ics|ya?ml|sh)\b", re.I)),
    ("a folder path", re.compile(r"(?<![\w:/])(?:~|\.{1,2})?/[\w.-]+/[\w./-]*|\b[\w.-]+/[\w.-]+/[\w./-]+")),
    ("a placeholder like <code>", re.compile(r"<[a-z][a-z0-9 _-]*>", re.I)),
    ("a leftover {}", re.compile(r"[{}]")),
    ("a number code like error 500", re.compile(r"\b(?:error|code|status|exit|http)\s*[:#]?\s*\d{3}\b", re.I)),
    ("a computer word like None or null", re.compile(r"\b(?:None|null|NaN|undefined|True|False)\b")),
    ("an arrow", re.compile(r"->|=>|→|←")),
    ("square brackets", re.compile(r"[\[\]]")),
    ("a computer name like unit_cost", re.compile(r"\b[a-z]+_[a-z_]+\b")),
    ("a name written like startsAt", re.compile(r"\b[a-z]{3,}[A-Z][A-Za-z]+\b")),
    ("an approval code on its own", None),  # handled in check(): a 4 to 6 character code is fine only after yes or no
)
_CODE_RE = re.compile(r"(?<![\w-])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{4,6}(?![\w-])", re.I)
_AFTER_YES_RE = re.compile(r"\b(?:yes|no|undo|show|cancel)[ ,]+$", re.I)
_APPROVAL_RE = re.compile(r"\b(yes|no|undo|show|cancel)([ ,]+)(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{4,12}\b", re.I)
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u2705\u274C\uFE0F\u200D]")
_PHONE_OR_NUMBER = re.compile(r"\d")


def quote(text) -> str:
    """Mark words that are Mike's own (shown as he wrote them, never judged)."""
    text = str(text)
    return OPEN + text + CLOSE if text else text


def plain(text: str) -> str:
    """The text with the marks removed (what is actually sent)."""
    return text.replace(OPEN, "").replace(CLOSE, "")


def _ours(text: str) -> str:
    """Only Hass's own words: every marked stretch is replaced by a harmless word."""
    out, depth, buf = [], 0, []
    for ch in text:
        if ch == OPEN:
            depth += 1
            if depth == 1: buf.append(" thing ")
        elif ch == CLOSE:
            depth = max(0, depth - 1)
        elif depth == 0:
            buf.append(ch)
    out.append("".join(buf))
    return "".join(out)


def has_emoji(text) -> bool:
    return bool(_EMOJI_RE.search(str(text or "")))


def check(text, *, emoji_ok=False, long_ok=False, ids_ok=False) -> list:
    """The rules a message breaks, as short plain phrases; [] when it is fine.

    emoji_ok: Mike used an emoji first. long_ok: he asked for a list, or it is a draft he must read in full.
    ids_ok: the message teaches a command whose answer is an id he has to type (find, listing, post, alias)."""
    if not isinstance(text, str) or not text.strip(): return ["empty"]
    ours = _ours(text)
    ours = _APPROVAL_RE.sub(r"\1\2code", ours)  # an approval code right after yes / no / undo / show (up to 12 characters) is allowed
    broken = []
    for hit in _WORD_RE.finditer(ours):
        if ids_ok and hit.group(1).lower() in ("id", "ids"): continue
        broken.append(f"the word '{hit.group(1).lower()}'")
    broken += [f"the phrase '{h.group(0).lower()}'" for h in _PHRASE_RE.finditer(ours)]
    for name, rx in PATTERNS:
        if rx is None: continue
        if ids_ok and name in ("an id like photo-product-001", "an internal name like product.set_photo", "a placeholder like <code>"): continue
        if rx.search(ours): broken.append(name)
    for hit in _CODE_RE.finditer(ours):
        if not _AFTER_YES_RE.search(ours[:hit.start()]) and not ids_ok:
            broken.append("an approval code on its own")
            break
    if ours.count("!") > 1: broken.append("too many exclamation marks")
    if not emoji_ok and _EMOJI_RE.search(ours): broken.append("an emoji Mike did not use first")
    if not long_ok and len(plain(text)) > LONG_AFTER: broken.append("too long for one message")
    return list(dict.fromkeys(broken))


def guard(text, **flags):
    """(text to send, broken rules). A message that breaks a rule is replaced by SAFE_LINE."""
    broken = check(text, **flags)
    return (SAFE_LINE if broken else plain(text)), broken


# -- honesty ------------------------------------------------------------------------------------------------------

_NEGATED = re.compile(
    r"\b(?:not|n't|never|nothing|no|isn't|wasn't|haven't|hasn't|didn't|couldn't|can't|cannot|without|unless|until|if|once|"
    r"yet|waiting|still|before|when|or)\b[^.!?\n]{0,60}?\b(?:done|saved|live|sent|checked|published|changed|updated|"
    r"put|added|removed|cancelled|canceled|finished|worked|ready|on the website|on the site|showing)\b", re.I)
_SUCCESS = re.compile(
    r"\b(?:done|all set|saved|published|updated|finished|it worked|worked|is live|now live|goes? live|"
    r"on the (?:website|site) now|now (?:showing|on the (?:website|site))|has been (?:sent|saved|changed|added|removed)|"
    r"i(?:'ve| have) (?:saved|changed|updated|added|removed|sent|put|checked))\b", re.I)


def claims_success(text) -> bool:
    """True when the message says something is done, live, saved, sent or checked. A negated or conditional phrase
    ('nothing was changed', 'not saved yet', 'reply yes to put it on the website') does not count."""
    stripped = _NEGATED.sub(" ", plain(str(text)))
    stripped = re.sub(r"\b(?:reply|say|send|tell me)\b[^.!?\n]*", " ", stripped, flags=re.I)  # an instruction is not a claim
    return bool(_SUCCESS.search(stripped))


_LIVE = re.compile(r"\b(?:done|is live|now live|on the website now|now on the website|it's on the website|is on the website|showing now)\b", re.I)


def claims_live(text) -> bool:
    """True when the message says the change is on the website now. 'Saved, but not on the website yet' and 'I'm not sure it's on
    the website' do not count."""
    stripped = _NEGATED.sub(" ", plain(str(text)))
    stripped = re.sub(r"\b(?:reply|say|send|tell me|ask)\b[^.!?\n]*", " ", stripped, flags=re.I)
    return bool(_LIVE.search(stripped))


# What Hass says when it does not know or cannot do something. One place, so the honesty tests can name them.
DONT_KNOW = "I don't know {what}. {ask}"
CANT_DO_YET = "I can't do that yet. {instead}"
NOT_SURE_IT_WORKED = "I'm not sure that worked. I'll check, and I'll tell you what I find."


# -- times in everyday words ----------------------------------------------------------------------------------------


class VoiceError(AssertionError):
    """Strict mode (tests, CI): a message that breaks a rule is an error, so the build fails instead of the fallback hiding it."""


def clock_words(at: datetime) -> str:
    """`2:05 pm`, `9 am`: no seconds, no zone."""
    hour = at.hour % 12 or 12
    return f"{hour} {'am' if at.hour < 12 else 'pm'}" if at.minute == 0 else f"{hour}:{at:%M} {'am' if at.hour < 12 else 'pm'}"


def natural(at, now=None) -> str:
    """A time as a person says it: `today at 2:05 pm`, `tomorrow at 9 am`, `Monday at 9 am`, `Saturday, Nov 14 at 9 am`.
    A time without a zone, or one that cannot be read, is `at a time I can't read`."""
    if not isinstance(at, datetime) or at.tzinfo is None: return "at a time I can't read"
    at = at.astimezone(LOCAL_TZ)
    base = now.astimezone(LOCAL_TZ) if isinstance(now, datetime) and now.tzinfo else None
    if base is not None:
        days = (at.date() - base.date()).days
        if days == 0: return f"today at {clock_words(at)}"
        if days == 1: return f"tomorrow at {clock_words(at)}"
        if days == -1: return f"yesterday at {clock_words(at)}"
        if 1 < days < 7: return f"{at:%A} at {clock_words(at)}"
    return f"{at:%A}, {at:%b} {at.day} at {clock_words(at)}"


def natural_iso(iso, now=None) -> str:
    """natural() for an ISO text; anything unreadable is `at a time I can't read`."""
    try: return natural(datetime.fromisoformat(iso), now)
    except (TypeError, ValueError): return "at a time I can't read"


# -- technical reasons in everyday words -----------------------------------------------------------------------------
# The shop's rules (ops/*.py, the editor) refuse changes with technical sentences. Mike never sees those: explain()
# gives the plain sentence for the ones we know, and the generic line for the rest. The second item is a short
# neutral code for the correspondence log.

GENERIC_REFUSAL = "I couldn't make that change, so nothing changed. Could you say it another way?"
REASONS = (  # (regex on the lower-cased technical text, log code, plain sentence)
    (r"selection was not checked today", "shelf-check-needed",
     "I need today's shelf check first. Tell me what's on the shelves today, and then I can change that."),
    (r"out of date; check the selection", "shelf-check-old",
     "That date is too old. I need a fresh shelf check first. Tell me what's on the shelves today."),
    (r"is longer than|too long", "too-long", "That's too long for the website. Could you make it a bit shorter?"),
    (r"already (?:has|says|shows|called|hidden|marked|scheduled)|is already|already the same|nothing to change|no change",
     "already-so", "That's already how it is, so nothing changed."),
    (r"guest count unavailable", "guest-count-missing",
     "I can't see how many guests have signed up, so I can't change this safely. Please ask Graham."),
    (r"start is in the past|is already past|already past", "time-passed", "That time has already passed. What day and time should it be?"),
    (r"below \d+ confirmed|confirmed guests", "guests-over-limit",
     "More guests than that have already signed up. What limit should it be?"),
    (r"^held:|held product|on hold", "on-hold", "That product is on hold, so I can't change it. Please ask Graham."),
    (r"is hidden; restore|restore it|restore the maker|restore .* first", "hidden-first",
     "That one is hidden right now. Do you want me to bring it back first?"),
    (r"unknown (?:route idea|change)|no such|not found|not-found|is not on the site", "not-found",
     "I don't know that one. Could you give me its name?"),
    (r"nothing to clear|has no .* set", "nothing-to-clear", "There's nothing there to remove."),
    (r"conflict:", "changed-since", "That has changed since, so I can't undo it cleanly. Please ask Graham."),
    (r"still has active products", "maker-has-products",
     "That maker still has products showing. Should I hide those too?"),
    (r"image file .* missing|photo file cannot be read", "photo-missing",
     "I can't find that photo. Could you send it again?"),
    (r"send the photo with the product name", "photo-needs-name", "Send the photo with the product name as its caption."),
    (r"is a hike, not a route|is a route idea, not a real hike", "wrong-kind",
     "That's a different kind of thing than I expected. Could you say which one you mean?"),
    (r"not scheduled|has not started yet|is cancelled|is completed", "hike-state",
     "That hike can't be changed that way right now. Could you tell me what you want to happen?"),
    (r"limit|at most|more than \d+ days", "over-limit", "That's more than I can take at once. Could you make it smaller?"),
    (r"needs at least|needs a day or time|say the same thing|must be", "unclear-text",
     "That doesn't look quite right. Could you say it another way?"),
)
WARNINGS = (  # (regex on the technical warning, builder of the plain sentence)
    (r"guest count unavailable", lambda m: "I can't see how many guests have signed up. Please check before you say yes."),
    (r"has (\d+) confirmed guests?; nobody is notified", lambda m: (
        f"{m[1]} {'guest has' if m[1] == '1' else 'guests have'} signed up, and nobody is told automatically.")),
    (r"moves to .*; (\d+) confirmed guests? (?:is|are) not told", lambda m: (
        f"{m[1]} {'guest has' if m[1] == '1' else 'guests have'} signed up for the old time, and nobody is told automatically.")),
    (r"adds organic badge", lambda m: "This adds the Organic badge."),
    (r"removes organic badge", lambda m: "This takes off the Organic badge."),
    (r"changes the .based in. line on (\d+)", lambda m: f"This changes the 'Based in' line on {m[1]} product card{'s' if m[1] != '1' else ''}."),
    (r"has no active products", lambda m: "No product cards will change."),
    (r"rsvps are off", lambda m: "Sign-ups are off, so the guest limit does nothing until they are turned on."),
    (r"rsvps turned on", lambda m: "Sign-ups are being turned on with the guest limit that was saved."),
)


def explain(technical) -> tuple:
    """(plain sentence, short log code) for a technical refusal. Unknown reasons give GENERIC_REFUSAL and 'unmapped'."""
    text = str(technical or "").lower()
    for rx, code, sentence in REASONS:
        if re.search(rx, text): return sentence, code
    return GENERIC_REFUSAL, "unmapped"


def explain_warning(technical) -> str:
    text = str(technical or "").lower()
    for rx, build in WARNINGS:
        m = re.search(rx, text)
        if m: return build(m)
    return "There is one thing to double-check before you say yes."


# -- values and field names in everyday words ---------------------------------------------------------------------------
FIELDS = {  # the shop's own words for what can change; an unknown field is "a detail", never its internal name
    "name": "the name", "brand": "the brand", "category": "the shelf", "description": "the description",
    "displayBrand": "the brand shown on the card", "producerKey": "the maker", "image": "the photo", "photo": "the photo",
    "imageAlt": "the photo description", "status": "whether it shows", "available": "the shelf word",
    "available_on": "when it was last checked", "place": "the place", "story": "the story", "url": "the website link",
    "hidden": "whether it is hidden", "title": "the title", "startsAt": "the start time", "capacity": "the guest limit",
    "rsvpEnabled": "whether guests can sign up", "meetingPoint": "the meeting place", "distance": "the distance",
    "duration": "how long it takes", "difficulty": "how hard it is", "accessNote": "the access note",
    "recap": "the recap", "cancelNote": "the cancellation note", "hours": "the opening hours", "intro": "the intro",
    "headline": "the headline", "notice": "the notice", "phone": "the phone number", "streetAddress": "the street address",
    "town": "the town", "homeImage": "the home page photo", "selection_checked_on": "the shelf check", "routeType": "the route type",
    "elevationLabel": "the elevation", "sourceName": "the source name", "sourceUrl": "the source link", "trailId": "the route idea",
    "record": "this", "bring": "what to bring", "meetingAddress": "the meeting address", "meetTime": "the meeting time",
    "walkTime": "the walk time", "returnTime": "the return time", "invitation": "the invitation",
}
SKIP_FIELDS = ("id", "addedOn", "key", "createdAt", "updatedAt")  # internal; never listed for a new record
STATUS_WORDS = {"active": "showing", "hidden": "hidden", "held": "on hold", "scheduled": "scheduled", "cancelled": "cancelled",
                "completed": "done"}


def field_phrase(field) -> str:
    return FIELDS.get(field, "a detail")


def value_words(value, field=None) -> str:
    """A stored value as Mike would say it: yes/no, nothing, a plain number, status words, lists joined with ';'."""
    if value is None or value == "" or value == []: return "nothing"
    if value is True: return "yes"
    if value is False: return "no"
    if field == "status" and isinstance(value, str): return STATUS_WORDS.get(value, value)
    if isinstance(value, list) and all(isinstance(v, str) for v in value): return "; ".join(value)
    if isinstance(value, (int, float)): return str(value)
    if isinstance(value, str): return value
    return "more than I can show here"
