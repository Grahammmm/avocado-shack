"""HASS-LIVEPOL-1: pure live-content boundary; no interpreter or I/O.

HASS-LIVE-PLAN-1 (G, 2026-11-08): the boundary is now an allow-list. Only the operations in LIVE may go straight from the
owner's `yes <code>` to the website, each with the argument names it may carry; everything else is refused with a plain
message and kept as a private proposal for Graham (conversation writes the backlog row). The content gates below
(protected fields, protected sentences, 10 records, sign-up off) still apply on top of the table. Undo always passes.

HASS-LIVE-ADD-1 (G, 2026-11-09): a NEW product (product.add) and, only to name on it, a NEW maker (maker.add) may go live. The brand,
display brand and producer key (and the maker's place) pass the field gate only on a record that very draft creates with that live
operation (NEW_RECORD_FIELDS); the maker's link never does; and the conversation asks instead of drafting when a brand, maker or
town is not in the owner's own words of the request (unsaid). Everything else about products and makers stays private.
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
    "product.edit": {"id", "description", "category"},                        # never name, brand, producer, picture
    "product.set_availability": {"id", "available"}, "product.clear_availability": {"id"},
    "store.confirm_selection": None,                                         # the shelf-check day that goes with a stock word
    "specials.add": None, "specials.edit": None, "specials.remove": None, "specials.clear_expired": None,
    "hike.create": None, "hike.update": None, "hike.cancel": None,           # sign-up off only (see _signup)
    "maker.edit": {"key", "story"},                                          # the maker's about text only
    # HASS-LIVE-ADD-1 (G, 2026-11-09): a NEW product may go live, with the brand, display brand and producer key the owner said in
    # this request (see unsaid) and with the picture that comes with it (the op needs one; the shop has no placeholder). Never the
    # `image` argument (an existing picture file). The brand fields pass the field gate only inside this op (see NEW_RECORD_FIELDS).
    "product.add": {"name", "brand", "category", "description", "photo", "imageAlt", "producerKey", "displayBrand"},
    # ... and a NEW maker only so that this new product can name it: the name and the place (the maker's about text is the
    # skill's "<Maker> is based in <place>."); never the link (url). A maker on its own is refused (see _lone_makers).
    "maker.add": {"key", "name", "place", "story"},
    "history.revert": None,
}
# Fields that are protected everywhere (FIELDS) except on a record the draft CREATES with the named live operation.
# Changing the same field on an existing product or maker stays refused, and the maker's url is never in this table.
NEW_RECORD_FIELDS = {"products": ("product.add", {"brand", "displayBrand", "producerKey"}), "makers": ("maker.add", {"place"})}
LONE_MAKER = "maker.add without a new product"
# Why an operation stays private. Plain words, finishing "it ..."; an operation in neither table gets the general line.
PRIVATE = {
    "product.set_photo": "changes a picture",
    "maker.hide": "takes a maker off the website", "maker.restore": "brings a maker back onto the website",
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


def _created_here(collection, field, before, names) -> bool:
    """True when a protected field is set on a record this draft CREATES (before is None) with the live operation that owns it."""
    op, fields = NEW_RECORD_FIELDS.get(collection, (None, ()))
    return before is None and op in LIVE and op in names and field in fields


def _lone_makers(ops) -> list[str]:
    """A maker.add whose key no product.add in the same draft names as its producerKey is a maker on its own: refused."""
    named = {c["args"].get("producerKey") for c in ops if c["op"] == "product.add" and isinstance(c.get("args"), dict)}
    return [f"not live: {LONE_MAKER}" for c in ops
            if c["op"] == "maker.add" and not (isinstance(c.get("args"), dict) and c["args"].get("key") in named)][:1]


def _town(place):
    return place.split(",")[0].strip() if isinstance(place, str) else None


DENIAL_WORDS = frozenset(claims.NEGATORS) | {
    "none", "neither", "wrong", "mistake", "mistaken", "incorrect", "ignore", "forget", "scrap", "except", "unlike", "instead",
    "rather", "than"}
_BREAK = re.compile(r"[.!?;:\n,]|\bbut\b")


def _denied(words) -> bool:
    return any(w in DENIAL_WORDS or w.endswith("n't") for w in words)


AUXILIARIES = frozenset({"is", "are", "was", "were", "am", "be", "been", "do", "does", "did", "has", "have", "had", "will", "would",
                         "can", "could", "should"})


def _denied_after(words) -> bool:
    """The words right after a mention deny it when its verb is negated or called wrong: "X is not the maker", "X isn't it",
    "X didn't make it", "X is wrong", "X never made it"."""
    if not words: return False
    if words[0] in ("never", "wrongly") or words[0].endswith("n't"): return True
    return len(words) > 1 and words[0] in AUXILIARIES and _denied(words[1:2])


def _owner_said(phrase, lines: str) -> bool:
    """True when the owner's own words (folded, one line per text of the request) name the phrase and the LAST mention is not
    denied. A mention is denied by a negator or a correction word ("not", "never", "wrong", "instead", n't ...) anywhere before it
    in its clause (clauses end at . ! ? ; : , a newline or "but"), however many words away: "not made by the people at X" denies
    X; and by a negated or wrong verb straight after it: "X is not the maker", "X didn't make it". A later denial or correction
    beats an earlier affirmative mention; a later plain mention beats an earlier denial. Pure."""
    if not (isinstance(phrase, str) and phrase.strip()): return False
    rx, last = claims._pattern(phrase), None
    for clause in _BREAK.split(lines):
        for m in rx.finditer(clause):
            last = not (_denied(clause[:m.start()].split()) or _denied_after(clause[m.end():].split()))
    return bool(last)


def unsaid(draft, owner_text) -> list[str]:
    """HASS-LIVE-ADD-1: the brand, the maker line, the maker's name and the town that a NEW product or maker in the draft carries
    but the owner's own texts of this request do not hold (whole phrase, case and accents ignored, a denied mention does not
    count). [] when every one is in his words. Only the conversation can call this (it alone holds his texts), when it drafts;
    the house words for an unknown maker (\"Producer not identified\", \"From the market\") need no owner words. Pure."""
    try:
        names = {call["op"] for call in draft["ops"]}
        lines = "\n".join(claims.fold(line) for line in str(owner_text or "").splitlines())
        found = []
        for record in draft["records"]:
            after = record.get("after")
            if record.get("before") is not None or not isinstance(after, dict): continue
            if record.get("collection") == "products" and "product.add" in names:
                house = after.get("brand") == claims.PLACEHOLDER
                shown = after.get("displayBrand")
                values = [None if house else after.get("brand"),
                          None if shown in (None, after.get("brand")) or (house and shown == "From the market") else shown]
            elif record.get("collection") == "makers" and "maker.add" in names:
                values = [after.get("name"), _town(after.get("place"))]
            else: continue
            found += [v for v in values if isinstance(v, str) and v.strip() and not _owner_said(v, lines)]
        return list(dict.fromkeys(found))
    except Exception:  # an unreadable draft is refused by check(); this helper only ever asks
        return []


def unsaid_question(values) -> str:
    """The one plain owner question for the values unsaid() found."""
    from hass.voice import quote
    named = " and ".join(quote(f'"{v}"') for v in values[:2]) + (" (and a few more)" if len(values) > 2 else "")
    return (f"You didn't say {named} in your message, and a brand, a maker or a town only goes on the website in your own words. "
            "Send the change again with it in your own words, or without it.")


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
        reasons.update(_lone_makers(ops))
        for record in records:
            collection, before, after = record["collection"], record["before"], record["after"]
            if not isinstance(collection, str): return UNREADABLE.copy()
            if collection == "events" and any(isinstance(v, dict) and v.get("rsvpEnabled") is True for v in (before, after)):
                reasons.add("sign-up is on")
            for field, b, a in _changes(before, after):
                if collection == "club" or (field in FIELDS.get(collection, set()) and not _created_here(collection, field, before, names)):
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
        if name == LONE_MAKER: return "it adds a maker on its own, without a new product"
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
