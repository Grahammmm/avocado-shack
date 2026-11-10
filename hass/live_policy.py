"""HASS-LIVEPOL-1: pure live-content boundary; no interpreter or I/O.

HASS-LIVE-PLAN-1 (G, 2026-11-08): the boundary is now an allow-list. Only the operations in LIVE may go straight from the
owner's `yes <code>` to the website, each with the argument names it may carry; everything else is refused with a plain
message and kept as a private proposal for Graham (conversation writes the backlog row). The content gates below
(protected fields, protected sentences, 10 records, sign-up off) still apply on top of the table. HASS-SEC-2 (M1): an undo meets
the same content gates (no longer "undo always passes"); the release engine also refuses the undo of a change that never went
live. HASS-SEC-2 (H1): text is unhidden and lookalike letters made Latin before matching (claims.skeleton), contact details,
prices and the claim classes have paraphrase shapes, and a superlative or a word of mixed alphabets is refused as a claim the
gate cannot check.

HASS-LIVE-ADD-1 (G, 2026-11-09): a NEW product (product.add) and, only to name on it, a NEW maker (maker.add) may go live. The brand,
display brand and producer key (and the maker's place) pass the field gate only on a record that very draft creates with that live
operation (NEW_RECORD_FIELDS); the maker's link never does; and the conversation asks instead of drafting when a brand, maker or
town is not in the owner's own words of the request (unsaid). Everything else about products and makers stays private.
"""
import json
import re
import unicodedata
from collections import Counter

from hass import claims

MAX_RECORDS = 10
COMMERCE_WORDS = re.compile(r"\$\s?\d|\bbasket\b|\bcheck ?out\b|\bcart\b|add to (?:bag|basket|cart)|weekly box|"
                            r"\bmerch|\bsubtotal\b|\bpickup\b|online shop|\bprices?\b|\bpricing\b|\bstripe\b|"
                            r"\bpaypal\b|\bshipping\b|\bsku\b|stock & orders|\borders?\b|\bbuy now\b", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# PHONE_STRICT is the original shape (separators required); the publish screen keeps it for image and other binary bytes.
PHONE_STRICT = re.compile(r"(?<!\d)\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")
# HASS-SEC-2 (H1, M3): every common way to write a phone number: the strict shape; 10 bare digits, a +1 or 1 in front, a
# bracketed area code, any of space, dash, slash between the groups (a dot only in the strict shape, so a decimal such as a map
# coordinate 120.8740879 is not a phone); and an international + number of 8 to 15 digits. Never inside a word or a longer number.
PHONE = re.compile(
    PHONE_STRICT.pattern
    + r"|(?<![\w+.,\-])(?:\+\s?1[ \t.\-]?|1[ \t.\-]?)?(?:\(\d{3}\)[ \t.\-]?|\d{3}[ \t\-/]?)\d{3}[ \t\-]?\d{4}(?![\w]|[.,]\d)"
    + r"|(?<![\w+])\+\s?\d(?:[ \t.\-()]?\d){7,14}(?![\w]|[.,]\d)")
_TLDS = r"(?:com|net|org|edu|gov|io|co|us|info|biz|me|app|dev|shop|store|farm|ca|uk|ai|online|site|xyz|live|page|link|website)"
URL = re.compile(r"(?:https?://|www\.)\S+|(?<![\w@.\-])[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9\-]+)*\." + _TLDS + r"(?![\w\-])",
                 re.I)
_AT, _DOT = r"\s*[\[(]?\s*(?:@|\bat\b)\s*[\])]?\s*", r"\s*[\[(]?\s*(?:\.|\bdot\b)\s*[\])]?\s*"
SPELLED_ADDRESS = re.compile(r"\b[\w.+\-]+" + _AT + r"[\w\-]+(?:" + _DOT + r"[\w\-]+)*?" + _DOT + _TLDS + r"\b", re.I)
SPELLED_HOST = re.compile(r"\b[\w\-]+\s*[\[(]?\s*\bdot\b\s*[\])]?\s*" + _TLDS + r"\b", re.I)
HANDLE = re.compile(r"(?<![\w@.])@[a-z0-9_](?:[a-z0-9_.]*[a-z0-9_])?", re.I)
CONTACT = (EMAIL, PHONE, URL, SPELLED_ADDRESS, SPELLED_HOST, HANDLE)
ENDORSE = ("endorsed", "recommended by", "as seen", "featured in", "award", "voted", "#1", "testimonial", "partner")


def _words(*patterns):
    return tuple(re.compile(p) for p in patterns)


# HASS-SEC-2 (H1): the plain claim words above cannot hold every way to say a claim, so each class also has paraphrase shapes,
# matched on the skeleton (claims.skeleton) of a sentence. They are deliberately wide: a sentence they catch is refused for the
# website and kept for Graham, never lost.
PARAPHRASES = {
    "origin/organic": _words(
        r"\b(?:grown|raised|picked|harvested|sourced|caught|foraged|farmed|cultivated|gathered|hand[- ]?picked)\s+(?:\w+\s+){0,2}?"
        r"(?:in|on|at|by|from|near|nearby|around|outside|across)\b",
        r"\b(?:homegrown|home[- ]grown|farm[- ]fresh|farm[- ]to[- ]table|family[- ](?:owned|run|grown|farmed)|single[- ]origin|"
        r"estate[- ]grown|backyard|hometown|down the road|around the corner)\b",
        r"\b(?:farms?|ranch(?:es)?|orchards?|groves?|vineyards?|homesteads?|apiar(?:y|ies)|pastures?|plantations?)\b",
        r"\b(?:straight|direct(?:ly)?|fresh|comes?|came|coming)\s+from\b(?!\s+(?:the\s+|a\s+|your\s+)?(?:pan|oven|jar|fridge|freezer|"
        r"grill|skillet|bag|tin|can|box|pot|bottle|toaster|stove|packet|carton|tub)\b)", r"\bfrom\s+(?:our|their|his|her|my)\s+own\b",
        r"\b(?:pesticides?|herbicides?|fungicides?|insecticides?|sprays?|sprayed|spraying|chemicals?|synthetic|gmos?|additives?|"
        r"preservatives?|hormones?|antibiotics?|natural|naturally|organically|usda|untreated|non[- ]?toxic|heirloom|grass[- ]?fed|"
        r"wild[- ]?(?:caught|harvested|grown))\b"),
    "health/awards/endorsements": _words(
        r"\bgood for (?:you\b|(?:your|the) (?:\w+ )?(?:heart|gut|health|skin|body|bones?|brain|immune\w*|digestion|blood|liver|"
        r"kidneys?|eyes|hair|joints|mood|sleep|teeth)\b)",
        r"\b(?:healthy|healthier|healthiest|healthful|nutritious|nutrients?|vitamins?|antioxidants?|probiotics?|prebiotics?|"
        r"electrolytes?|omega[- ]?3s?|cholesterol|blood (?:pressure|sugar)|diabet\w*|cancers?|inflammat\w*|diseases?|illness\w*|"
        r"ailments?|remed(?:y|ies)|medicin\w*|medical|therapeutic|wellness|detox\w*|cleanse|immun\w*|digestion|digestive|"
        r"metabolism|keto|paleo|low[- ](?:fat|sugar|carb|sodium|calorie)|fat[- ]free|heart[- ]healthy|gut health|superfoods?|"
        r"healing|heals?)\b",
        r"\b(?:boost|lower|reduce|prevent|fight|support|improve|strengthen|protect|help)(?:s|es|ing|ed)?\s+(?:\w+\s+){0,3}?"
        r"(?:heart|gut|immun\w*|blood|cholesterol|pressure|sugar|digestion|skin|bones?|brain|health|inflammation|energy|mood|"
        r"sleep|weight|stress|aging|ageing)\b",
        r"\b(?:won(?!')|wins|winner|winners|winning|prizes?|medals?|ribbons?|troph(?:y|ies)|champion\w*|first place|1st place|"
        r"second place|2nd place|best in show|accolades?|honou?red|recogni[sz]ed by|certificat\w+|five[- ]star|\d(?:\.\d)?[- ]stars?|"
        r"top[- ]rated|highly rated|rated|ranked|awards?|awarded)\b",
        r"\b(?:loved|trusted|approved|chosen|preferred|praised|adored|beloved|endorsed|used|recommended|favou?red|backed)\s+by\b",
        r"\b(?:favou?rites? (?:of|at|among|with)|go-to (?:for|of)|as (?:seen|featured|heard) (?:on|in)|featured (?:on|in|at|by)|"
        r"seen on|official|celebrit\w+|famous|renowned|acclaimed|reviews?|rave|raving|testimonials?|recommend\w*|endors\w*|"
        r"sponsor\w*|partner\w*)\b"),
    "prices": _words(
        r"[$€£¥₹]\s?\d|\d\s?[$€£¥₹¢]",
        r"\d+(?:[.,]\d+)?\s*(?:usd|eur|euros?|gbp|dollars?|bucks?|cents?|quid|pesos?)\b",
        r"\b(?:a|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|hundred|half|"
        r"couple)(?:\s+\w+)?\s+(?:dollars?|bucks?|cents?|quid|euros?)\b",
        r"\b(?:bucks?|quid|dollars?|cents?|pennies)\b",
        r"\bper (?:lb|pound|oz|ounce|kg|kilo|kilogram|gram|dozen|jar|bag|box|bunch|pint|quart|gallon|each)\b",
        r"\b(?:costs?|priced|pricey|cheap|cheaper|cheapest|affordable|bargain|half[- ]price|prices?)\b"),
}
# Trail facts in other words, for hikes, route ideas and the club only (a dog treat or a parking note in a shop item is not a
# trail fact; the plain ACCESS_TERMS still apply everywhere).
TRAIL_COLLECTIONS = frozenset({"events", "routeIdeas", "club"})
TRAIL_PARAPHRASES = _words(
    r"\b(?:dogs?|dog[- ]friendly|pups?|puppies|pets?|pet[- ]friendly|leash\w*|off[- ]leash|horses?|equestrian|bikes?|bicycles?|"
    r"cyclists?)\b",
    r"\b(?:parking|park (?:at|in|on|for|along|by|near|free|here|there)|car park|parking lot)\b",
    r"\b(?:wheelchairs?|strollers?|accessib\w*|ada|handicap\w*|mobility)\b",
    r"\b(?:permits?|passes|fees?|free entry|admission|reservations? (?:needed|required))\b",
    r"\b(?:restrooms?|bathrooms?|toilets?|port[- ]?a[- ]?pott(?:y|ies)|outhouses?|drinking water|water fountains?|"
    r"water (?:available|station|stations|tap|taps)|no water)\b",
    r"\b(?:kid[- ]friendly|family[- ]friendly|beginner[- ]friendly|safe for (?:kids|children|everyone|all)|all ages|all abilities|"
    r"all levels)\b",
    r"\b(?:easy|easier|moderate|strenuous|difficult|challenging|steep|steeper|flat|paved|unpaved|gravel|rocky|shaded?|shady|"
    r"elevation|climbs?|climbing|switchbacks?)\b",
    r"\b\d+(?:[.,]\d+)?\s?(?:miles?|mi|km|kilomet(?:er|re)s?|feet|ft|hours?|hrs?|minutes?|mins?)\b")
# HASS-SEC-2 (H1): what the gate cannot put in a class but must not let through: a superlative (best, finest, the creamiest,
# number one, world's ...). A word that mixes alphabets is added in _protected (it can only be a disguise).
_NOT_SUPERLATIVE = frozenset({
    "west", "forest", "interest", "harvest", "honest", "rest", "guest", "test", "quest", "nest", "chest", "crest", "request",
    "contest", "protest", "suggest", "digest", "latest", "modest", "invest", "pest", "vest", "zest", "jest", "fest", "priest",
    "attest", "conquest", "behest", "inquest", "tempest", "midwest", "northwest", "southwest", "earnest", "everest", "manifest",
    "arrest", "bequest", "wrest", "unrest", "breast", "feast", "least", "beast", "east", "northeast", "southeast", "yeast",
    "almost", "utmost", "host", "post", "most", "lest"})
SUPERLATIVES = _words(
    r"\b(?:best|finest|greatest|tastiest|freshest|healthiest|purest|cheapest|creamiest|sweetest|juiciest|richest|smoothest|"
    r"biggest|largest|oldest|highest|strongest|top[- ](?:rated|quality|notch|selling)|best[- ]?selling|number one|world'?s|"
    r"world[- ](?:class|famous)|unbeatable|unbeaten|unrivall?ed|unmatched|unparall?eled|unsurpassed|second to none|like no other|"
    r"one and only|guarantee[sd]?|100 ?%|100 percent)\b",
    r"(?<!\w)#1(?!\d)")
_SUPERLATIVE_WORD = re.compile(r"\b(?:the (?:very )?)(\w{3,}est)\b|\b(\w{2,}iest)\b")
# Serving advice, not a claim: "at its best", "best served warm", "best kept cold".
_SERVING_BEST = re.compile(r"\bat (?:its|their|his|her|your) best\b|\bbest (?:given|served|kept|eaten|enjoyed|used|stored|warmed|"
                           r"chilled|toasted|with|when|within)\b")


def _superlative(sentence) -> bool:
    sentence = _SERVING_BEST.sub(" ", sentence)
    if any(rx.search(sentence) for rx in SUPERLATIVES): return True
    return any((m.group(1) or m.group(2)) not in _NOT_SUPERLATIVE for m in _SUPERLATIVE_WORD.finditer(sentence))


_DIGIT_WORDS = frozenset({"zero", "oh", "o", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"})


def _spelled_number(sentence) -> bool:
    """A phone number spelled out: seven or more digits in a row, at least three of them written as words."""
    run = words = 0
    for token in re.findall(r"[a-z]+|\d+", sentence):
        if token.isdigit(): run += len(token)
        elif token in _DIGIT_WORDS: run, words = run + 1, words + 1
        else: run = words = 0
        if run >= 7 and words >= 3: return True
    return False


def _script(c) -> str:
    name = unicodedata.name(c, "")
    script = name.split(" ")[0] if name else "?"
    return "CJK" if script in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL") else script


def _mixed_script(text) -> bool:
    """True when one word holds letters from two alphabets ("оrganic" with a Cyrillic о): only a disguise does that."""
    return any(len({_script(c) for c in word}) > 1 for word in re.findall(r"[^\W\d_]+", text))


PROTECTED = tuple((kind, claims._pattern(term)) for kind, terms in (
    ("origin/organic", claims.TERMS + claims.FARM_TERMS),
    ("health/awards/endorsements", claims.HEALTH_AWARD_TERMS + ENDORSE),
    ("trail facts", claims.ACCESS_TERMS),
    ("prices", ("price", "per lb", "per pound", "cents", "dollars"))) for term in terms) + (
        ("prices", re.compile(r"\$\s?\d|\d+\s?¢")), *(("contact", rx) for rx in CONTACT))
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


def _pieces(value):
    """[(shown text, skeleton)] per sentence. HASS-SEC-2 (H1): the text is first unhidden (NFKC, invisible characters and
    accents dropped), then cut at . ! ? ; and line breaks, never inside a contact token (an email, phone, web address or an
    'at ... dot' spelling, found with lookalike letters already made Latin) and never between two digits (2.5, $4.50)."""
    if isinstance(value, list):
        items = [v if isinstance(v, str) else json.dumps(v, sort_keys=True, allow_nan=False) for v in value]
        return [(claims.unhidden(v), claims.skeleton(v)) for v in items]
    if not isinstance(value, str):
        text = json.dumps(value, sort_keys=True, allow_nan=False)
        return [(claims.unhidden(text), claims.skeleton(text))]
    shown = claims.unhidden(value)
    look = shown.translate(claims._LOOKALIKE)  # one letter for one letter: the same positions as shown
    spans = [m.span() for rx in CONTACT for m in rx.finditer(look)]
    cuts = [m.start() for m in re.finditer(r"[.!?;\n]", look)
            if not any(start <= m.start() < end for start, end in spans)
            and not (look[m.start() - 1:m.start()].isdigit() and look[m.start() + 1:m.start() + 2].isdigit())]
    starts, ends = [0] + [i + 1 for i in cuts], cuts + [len(shown)]
    return [(shown[start:end], s) for start, end in zip(starts, ends) if (s := claims.skeleton(shown[start:end]))]


def sentences(value):
    """Skeleton sentences (claims.skeleton), retaining contact tokens whose internal dots are not sentence stops."""
    return [s for _shown, s in _pieces(value)]


def _protected(value, collection=None, names=()):
    """Counter of the claim sentences in value, and the claim kinds found. A sentence that mixes alphabets inside a word keeps
    a mark in its key, so swapping one letter of an existing claim for a lookalike is a change too. `names`: the draft's own
    product, brand and maker names (patterns); the paraphrase and superlative shapes do not read them ("Test Orchard" is a
    maker's name, not an origin claim), the plain claim words, prices and contact details still do."""
    found, kinds = Counter(), set()
    for shown, sentence in _pieces(value):
        hits = {kind for kind, rx in PROTECTED if rx.search(sentence)}
        wide = sentence
        for rx in names: wide = rx.sub(" ", wide)
        hits |= {kind for kind, rxs in PARAPHRASES.items() if any(rx.search(wide) for rx in rxs)}
        if collection in TRAIL_COLLECTIONS and any(rx.search(wide) for rx in TRAIL_PARAPHRASES): hits.add("trail facts")
        if _spelled_number(sentence): hits.add("contact")
        mixed = _mixed_script(shown)
        if mixed or _superlative(wide): hits.add(UNCHECKED)
        if hits:
            found[sentence + ("\0mixed" if mixed else "")] += 1
            kinds.update(hits)
    return found, kinds


NAME_FIELDS = ("name", "brand", "displayBrand", "producerKey")


def _names(records) -> tuple:
    """Patterns for the product, brand and maker names the draft's records carry (before or after), longest first."""
    names = {v for r in records if isinstance(r, dict) for side in (r.get("before"), r.get("after")) if isinstance(side, dict)
             for v in (side.get(f) for f in NAME_FIELDS) if isinstance(v, str) and claims.skeleton(v)}
    return tuple(claims._pattern(claims.skeleton(n)) for n in sorted(names, key=len, reverse=True))


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


PREDICATE_FILLER = AUXILIARIES | frozenset({
    "definitely", "really", "certainly", "absolutely", "actually", "clearly", "obviously", "simply", "just", "also", "still",
    "truly", "ever", "the", "a", "an", "my", "our", "very", "quite", "so"})


def _denied_after(words) -> bool:
    """The words right after a mention deny it when its predicate is negated or called wrong, however an auxiliary, an adverb
    or an article sits in between (up to four words, stopping at the first other word): "X is not the maker", "X isnt it",
    "X is definitely not the maker", "X didn't make it", "X has really never made it", "X is the wrong maker", "X is wrong"."""
    for w in words[:4]:
        w = w.strip("\"()")
        if w in ("never", "wrongly") or _denied([w]): return True
        if w not in PREDICATE_FILLER: return False
    return False


_HEDGES = (r"(?:maybe|perhaps|probably|possibly|no idea|not sure|unsure|i think|i guess|i believe|dunno|or so|or something|"
           r"i'm not sure|im not sure)\b")
# Right after the mention ("Fillmore maybe", "Fillmore (I think)", "fillmore-ish"), or after a comma when the hedge closes the
# clause ("Fillmore, not sure."); "Harbor Lane, perhaps Fillmore" hedges Fillmore, not Harbor Lane.
_HEDGE_AFTER = re.compile(r"\s*-\s*ish\b|\s*\(?\s*" + _HEDGES + r"|[\s,]*" + _HEDGES + r"[\s)]*(?:[.!?;:\n,]|$)")
_HEDGE_BEFORE = re.compile(r"\b(?:maybe|perhaps|probably|possibly|might be|could be|i think|i guess|not sure if|unsure if)\b")
_REQUEST = re.compile(r"\s*(?:(?:hey|hi|ok|okay|so)\s+)?(?:(?:can|could|would|will) (?:you|we|u)|please)\b")


def _hedged(lines, end, clause, m, stop) -> bool:
    """HASS-SEC-2 (L4): a mention the owner is not sure of: in a clause that ends with a question mark (unless the clause is a
    request: "can you add ... ?", "could you ... ?", "please ... ?"), followed by -ish, maybe, no idea, not sure (and the like),
    or after maybe, perhaps, probably in its clause. `end` is where the mention ends in lines, `stop` the clause's end mark."""
    question = stop is not None and stop.group() == "?" and not _REQUEST.match(clause)
    return bool(question or _HEDGE_AFTER.match(lines, end) or _HEDGE_BEFORE.search(clause[:m.start()]))


def _owner_said(phrase, lines: str) -> bool:
    """True when the owner's own words (folded, one line per text of the request) name the phrase and the LAST mention is not
    denied. A mention is denied by a negator or a correction word ("not", "never", "wrong", "instead", n't ...) anywhere before it
    in its clause (clauses end at . ! ? ; : , a newline or "but"), however many words away: "not made by the people at X" denies
    X; and by a negated or wrong verb straight after it: "X is not the maker", "X didn't make it". A later denial or correction
    beats an earlier affirmative mention; a later plain mention beats an earlier denial. HASS-SEC-2 (L4): a hedged mention
    (a question, "X-ish", "X maybe", "X? no idea", "not sure") counts as not said, like a denied one. Pure."""
    if not (isinstance(phrase, str) and phrase.strip()): return False
    rx, last, start = claims._pattern(phrase), None, 0
    for cut in [*_BREAK.finditer(lines), None]:
        end = cut.start() if cut else len(lines)
        clause = lines[start:end]
        for m in rx.finditer(clause):
            last = not (_denied(clause[:m.start()].split()) or _denied_after(clause[m.end():].split())
                        or _hedged(lines, start + m.end(), clause, m, cut))
        start = cut.end() if cut else end
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
    """Empty permits release; unreadable drafts fail closed. HASS-SEC-2 (M1): an undo (only history.revert ops) skips the
    operation table (history.revert is live) but its records meet every content gate a change meets: protected fields and
    sentences, sign-up off and the 10-record limit. The undo of a change that went live passes them (it is that change's exact
    inverse); whether the change it takes back went live at all is the release engine's question (publish_live.went_live)."""
    try:
        ops, records = draft["ops"], draft["records"]
        if not isinstance(ops, list) or not ops or not isinstance(records, list): return UNREADABLE.copy()
        names = [call["op"] for call in ops]
        if any(not isinstance(name, str) for name in names): return UNREADABLE.copy()
        undo = all(name == "history.revert" for name in names)
        reasons = set()
        if len(records) > MAX_RECORDS: reasons.add(f"more than {MAX_RECORDS} records")
        for name in () if undo else names:
            if name.startswith("route.") or name in OPS: reasons.add(f"protected operation: {name}")
            elif name not in LIVE: reasons.add(f"not live: {name}")
        for call in () if undo else ops:
            allowed = LIVE.get(call["op"])
            args = call.get("args")
            if allowed is not None and isinstance(args, dict):
                reasons.update(f"not live: {call['op']}.{arg}" for arg in sorted(set(args) - allowed))
            elif allowed is not None and args is not None: return UNREADABLE.copy()
        if not undo: reasons.update(_lone_makers(ops))
        names_seen = _names(records)
        for record in records:
            collection, before, after = record["collection"], record["before"], record["after"]
            if not isinstance(collection, str): return UNREADABLE.copy()
            if collection == "events" and any(isinstance(v, dict) and v.get("rsvpEnabled") is True for v in (before, after)):
                reasons.add("sign-up is on")
            for field, b, a in _changes(before, after):
                if collection == "club" or (field in FIELDS.get(collection, set()) and not _created_here(collection, field, before, names)):
                    reasons.add(f"protected field: {collection}.{field}")
                for old, new in _text_changes(b, a):
                    bp, bk = _protected(old, collection, names_seen)
                    ap, ak = _protected(new, collection, names_seen)
                    if bp != ap: reasons.update(f"protected sentences: {kind}" for kind in bk | ak)
        return sorted(reasons)
    except Exception:  # arbitrary unreadable input must never enable release or escape this pure boundary
        return UNREADABLE.copy()


def is_undo(draft) -> bool:
    """True for a readable draft whose ops are all history.revert."""
    ops = draft.get("ops") if isinstance(draft, dict) else None
    return isinstance(ops, list) and bool(ops) and all(isinstance(c, dict) and c.get("op") == "history.revert" for c in ops)


def undone(draft) -> list:
    """The change ids an undo draft takes back (an op without a readable changeId gives None: never a live change)."""
    return [c.get("args", {}).get("changeId") if isinstance(c.get("args"), dict) else None for c in draft["ops"]] if is_undo(draft) else []


UNCHECKED = "unchecked claims"  # HASS-SEC-2 (H1): a superlative or a word of mixed alphabets: the gate has no class for it
UNDO_NOT_LIVE = "undo of a change that never went live"  # HASS-SEC-2 (M1): the change was saved before the website went live
PLAIN_KINDS = {"origin/organic": "where the food comes from or whether it is organic", "health/awards/endorsements": "a health claim or an award",
               "trail facts": "trail details", "prices": "a price", "contact": "contact details", UNCHECKED: "a claim I can't check"}


def _plain_reason(reason: str) -> str:
    if reason == "sign-up is on": return "people have a way to sign up for that hike, so Graham should look first"
    if reason == UNDO_NOT_LIVE: return "it takes back a change that never went on the website from chat"
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
