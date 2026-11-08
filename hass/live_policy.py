"""HASS-LIVEPOL-1: pure live-content boundary; no interpreter or I/O.

HASS-LIVE-PLAN-1 (G, 2026-11-08): the boundary is now an allow-list. Only the operations in LIVE may go straight from the
owner's `yes <code>` to the website, each with the argument names it may carry; everything else is refused with a plain
message and kept as a private proposal for Graham (conversation writes the backlog row). The content gates below
(protected fields, protected sentences, 10 records, sign-up off) still apply on top of the table. Undo always passes.
"""
import json
import re
from collections import Counter

from hass import claims

MAX_RECORDS = 10
COMMERCE_WORDS = re.compile(r"\$\s?\d|\bbasket\b|\bcheck ?out\b|\bcart\b|add to (?:bag|basket|cart)|weekly box|"
                            r"\bmerch|\bsubtotal\b|\bpickup\b|online shop|\bprices?\b|\bpricing\b|\bstripe\b|"
                            r"\bpaypal\b|\bshipping\b|\bsku\b|stock & orders|\borders?\b|\bbuy now\b", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")
ENDORSE = ("endorsed", "recommended by", "as seen", "featured in", "award", "voted", "#1", "testimonial", "partner")
PROTECTED = tuple((kind, claims._pattern(term)) for kind, terms in (
    ("origin/organic", claims.TERMS + claims.FARM_TERMS),
    ("health/awards/endorsements", claims.HEALTH_AWARD_TERMS + ENDORSE),
    ("trail facts", claims.ACCESS_TERMS),
    ("prices", ("price", "per lb", "per pound", "cents", "dollars"))) for term in terms) + (
        ("prices", re.compile(r"\$\s?\d|\d+\s?¢")), ("contact", EMAIL), ("contact", PHONE))
FIELDS = {"products": {"brand", "displayBrand", "producerKey"}, "makers": {"place", "url"},
          "events": {"distance", "difficulty", "duration", "accessNote", "meetingAddress", "trailId"}}
OPS = {"hike.samples", "store.set_phone", "store.clear_phone", "store.set_address"}
UNREADABLE = ["the change could not be read"]

# One row per operation that may go live from chat. Value: the argument names it may carry (None = any argument; the field and
# sentence gates still judge what the change does). Adding a row here is the one-line way to let a new kind of change go live.
LIVE = {
    "product.hide": {"id"}, "product.restore": {"id"},
    "product.edit": {"id", "description", "category"},                       # never name, brand, producer, picture
    "product.set_availability": {"id", "available"}, "product.clear_availability": {"id"},
    "store.confirm_selection": None,                                         # the shelf-check day that goes with a stock word
    "specials.add": None, "specials.edit": None, "specials.remove": None, "specials.clear_expired": None,
    "hike.create": None, "hike.update": None, "hike.cancel": None,           # sign-up off only (see _signup)
    "maker.edit": {"key", "story"},                                          # the maker's about text only
    "history.revert": None,
}
# Why an operation stays private. Plain words, finishing "it ..."; an operation in neither table gets the general line.
PRIVATE = {
    "product.add": "adds an item with its brand and maker",
    "product.set_photo": "changes a picture",
    "maker.add": "adds a maker with a place and links", "maker.hide": "changes which makers are shown",
    "maker.restore": "changes which makers are shown",
    "hike.repeat": "copies a hike", "hike.complete": "records how a hike went", "hike.recap": "records how a hike went",
    "hike.samples": "changes the sample hikes",
    "store.set_phone": "is contact details", "store.clear_phone": "is contact details", "store.set_address": "is contact details",
    "store.set_hours": "changes the shop hours", "store.set_notice": "changes the shop notice", "store.clear_notice": "changes the shop notice",
    "store.set_headline": "changes the home page words", "store.set_intro": "changes the home page words",
    "store.set_story": "changes the home page words",
    "store.set_home_image": "changes the home page photo", "store.clear_home_image": "changes the home page photo",
    "route.add": "is trail details", "route.edit": "is trail details", "route.hide": "is trail details", "route.restore": "is trail details",
}


def sentences(value):
    """Folded sentences, retaining contact tokens whose internal dots are not sentence stops."""
    if isinstance(value, list):
        return [claims.fold(v if isinstance(v, str) else json.dumps(v, sort_keys=True, allow_nan=False)) for v in value]
    if not isinstance(value, str): return [claims.fold(json.dumps(value, sort_keys=True, allow_nan=False))]
    # Split before fold collapses newlines; dots inside an email/phone must remain to detect substitutions.
    spans = [m.span() for rx in (EMAIL, PHONE) for m in rx.finditer(value)]
    cuts = [m.start() for m in re.finditer(r"[.!?;\n]", value)
            if not any(start <= m.start() < end for start, end in spans)]
    starts, ends = [0] + [i + 1 for i in cuts], cuts + [len(value)]
    return [s for start, end in zip(starts, ends) if (s := claims.fold(value[start:end]))]


def _protected(value):
    found, kinds = Counter(), set()
    for sentence in sentences(value):
        hits = {kind for kind, rx in PROTECTED if rx.search(sentence)}
        if hits:
            found[sentence] += 1
            kinds.update(hits)
    return found, kinds


def _changes(before, after):
    """Include new/removed fields and nested text (notice and home-image records)."""
    if isinstance(before, dict) or isinstance(after, dict):
        b, a = before or {}, after or {}
        if not isinstance(b, dict) or not isinstance(a, dict): raise ValueError("record shape")
        for field in sorted(b.keys() | a.keys()):
            if b.get(field) != a.get(field): yield field, b.get(field), a.get(field)
    elif before != after:
        yield "record", before, after


def _text_changes(before, after):
    if isinstance(before, dict) or isinstance(after, dict):
        for _field, b, a in _changes(before, after): yield from _text_changes(b, a)
    else:
        yield before, after


def check(draft) -> list[str]:
    """Empty permits release; unreadable drafts fail closed. Undo restores prior live content."""
    try:
        ops, records = draft["ops"], draft["records"]
        if not isinstance(ops, list) or not ops or not isinstance(records, list): return UNREADABLE.copy()
        names = [call["op"] for call in ops]
        if any(not isinstance(name, str) for name in names): return UNREADABLE.copy()
        if all(name == "history.revert" for name in names): return []
        reasons = set()
        if len(records) > MAX_RECORDS: reasons.add(f"more than {MAX_RECORDS} records")
        for name in names:
            if name.startswith("route.") or name in OPS: reasons.add(f"protected operation: {name}")
            elif name not in LIVE: reasons.add(f"not live: {name}")
        for call in ops:
            allowed = LIVE.get(call["op"])
            args = call.get("args")
            if allowed is not None and isinstance(args, dict):
                reasons.update(f"not live: {call['op']}.{arg}" for arg in sorted(set(args) - allowed))
            elif allowed is not None and args is not None: return UNREADABLE.copy()
        for record in records:
            collection, before, after = record["collection"], record["before"], record["after"]
            if not isinstance(collection, str): return UNREADABLE.copy()
            if collection == "events" and any(isinstance(v, dict) and v.get("rsvpEnabled") is True for v in (before, after)):
                reasons.add("sign-up is on")
            for field, b, a in _changes(before, after):
                if collection == "club" or field in FIELDS.get(collection, set()):
                    reasons.add(f"protected field: {collection}.{field}")
                for old, new in _text_changes(b, a):
                    bp, bk = _protected(old)
                    ap, ak = _protected(new)
                    if bp != ap: reasons.update(f"protected sentences: {kind}" for kind in bk | ak)
        return sorted(reasons)
    except Exception:  # arbitrary unreadable input must never enable release or escape this pure boundary
        return UNREADABLE.copy()


PLAIN_KINDS = {"origin/organic": "where the food comes from or whether it is organic", "health/awards/endorsements": "a health claim or an award",
               "trail facts": "trail details", "prices": "a price", "contact": "contact details"}


def _plain_reason(reason: str) -> str:
    if reason == "sign-up is on": return "people have a way to sign up for that hike, so Graham should look first"
    if reason.startswith("not live: "):
        name = reason[len("not live: "):]
        if name.rpartition(".")[0] in LIVE: return "it changes more than the part I can change from chat"  # op.argument
        return "it " + PRIVATE.get(name, "is a kind of change I can't put on the website from chat yet")
    if reason.startswith("protected sentences: "): return "it touches " + PLAIN_KINDS.get(reason.split(": ", 1)[1], "a claim I can't check")
    if reason.startswith("protected operation"): return "it is a kind of change only Graham can make"
    if reason.startswith("protected field"): return "it changes something only Graham can change"
    if reason.startswith("more than"): return "it changes too many things at once"
    return "I couldn't read the change"


SAVED_FOR_GRAHAM = "I've saved it for Graham to look at, and he can do it by hand."


def refusal(reasons):
    why = "; ".join(dict.fromkeys(_plain_reason(r) for r in reasons)) or "I couldn't check it"
    return f"I can't put this on the website from chat: {why}. Nothing will be published. {SAVED_FOR_GRAHAM}"
