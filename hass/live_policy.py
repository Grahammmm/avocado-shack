"""HASS-LIVEPOL-1: pure live-content boundary; no interpreter or I/O."""
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
        for record in records:
            collection, before, after = record["collection"], record["before"], record["after"]
            if not isinstance(collection, str): return UNREADABLE.copy()
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
    if reason.startswith("protected sentences: "): return "it touches " + PLAIN_KINDS.get(reason.split(": ", 1)[1], "a claim I can't check")
    if reason.startswith("protected operation"): return "it is a kind of change only Graham can make"
    if reason.startswith("protected field"): return "it changes something only Graham can change"
    if reason.startswith("more than"): return "it changes too many things at once"
    return "I couldn't read the change"


def refusal(reasons):
    why = "; ".join(dict.fromkeys(_plain_reason(r) for r in reasons)) or "I couldn't check it"
    return f"I can't put this on the website from chat: {why}. Nothing will be published. Graham can do it by hand."
