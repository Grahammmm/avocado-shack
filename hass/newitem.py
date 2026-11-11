"""HASS-NEWITEM-1 (H10/H13 gap): a complete new-shelf-item draft, in house style, from one photo and one plain message.

``draft(message, photo, content=...)`` returns what Hass would put in front of Michael: the web picture (house_style spec,
see newitem_render), its alt text, the description in the shop's voice, the maker entry when the maker is new, the shelf,
availability, what was left off the page, a plain-language reply and the typed ops that the EXISTING editor/approval path
takes (``maker.add``, ``product.add`` with ``photo`` + ``imageAlt``, ``product.set_availability``). It writes nothing, sends
nothing, approves nothing; ops go through editor.prepare, claims.unstated, the preview and "yes <code>" exactly as before.

Facts come from Michael's words only. The LLM reads the message (``EXTRACT_PROMPT`` -> ``parse_facts``); a plain regex
reader (``extract_facts``) covers the common phrasings for offline tests and as a floor. Either way each fact must be
traceable to the message (``ground``): a value Michael did not write is dropped and, if the page needs it, asked about.
The description never states a claim, origin, ingredient or story that is not in the message or on a maker record; a
description written by a model (``writer=``) is accepted only if it passes ``house_style.check_description`` and the
same grounding test, else the template below is used. If the message lacks something the page shows, ONE short question
is returned instead of a draft. A maker or place is kept only when his words tie it to the item ("from <maker> in <place>",
or a catalog maker he named); otherwise ONE question confirms it. Claim terms (organic, local ...) never reach a public field
(name, alt, description, maker note); they are listed in left_off. The photo passes media.check_photo and the renderer's pixel
budget first; any photo that cannot be checked, decoded or drawn gives status "refused", one fixed reply and no ops.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict

from hass import claims, house_style as hs, media, newitem_render  # newitem_render imports Pillow only when a picture is drawn
from hass.content_model import CATEGORIES, SHELF_LABELS
from hass.ops.photos import _alt_problem

FACT_KEYS = ("name", "maker", "place", "story", "kind", "shelf", "container", "size", "price", "availability", "use", "url")
CONTAINERS = ("jar", "bottle", "bag", "box", "tub", "carton", "can", "tin", "jug", "pouch", "loaf", "block", "wheel", "bunch", "basket", "tray", "dozen")
STOP = frozenset("a an the some of new from by in at for with and or my our this that got get have has just came come in-stock".split())
GENERIC_SERVING = ("Taste a little first, then decide how to use the rest.", "Keep it close to the stove and see where dinner goes.")
AVAILABILITY_WORDS = {"no": r"\b(sold out|out of stock|none left|all gone)\b", "limited": r"\b(limited|only (?:a )?few|last (?:few|couple)|just a few)\b",
                      "yes": r"\b(got in|just got|got some|we have|have|in stock|arrived|new in|available|came in)\b"}
PRICE_RE = re.compile(r"\$\s?\d+(?:\.\d{1,2})?|\b\d+(?:\.\d{1,2})?\s?(?:dollars|bucks)\b", re.I)
SIZE_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:fl\.?\s?oz|oz|ounces?|lbs?|pounds?|kg|g|ml|l|pints?|quarts?|gallons?|ct|count|pack)\b", re.I)
USE_RE = re.compile(r"\b(?:good|great|nice|lovely|perfect|tasty|delicious|yummy)\s+(on|with|in|for)\s+([a-z][a-z ]{2,28}?)\s*(?=[.,;!]|\band\b|$)", re.I)
NEW_MAKER_RE = re.compile(r"\b(?:from|by|made by|out of)\s+(?P<name>[A-Z][\w’'&.-]*(?:\s+(?:&\s+|and\s+)?[A-Z][\w’'&.-]*){0,3})"
                          r"(?:\s*(?:,|—|-|\bin\b|\bout of\b|\bup in\b|\bnear\b|\bbased in\b)\s*(?P<place>[A-Z][A-Za-z’']*(?: [A-Z][A-Za-z’']*){0,2}(?:,\s*[A-Z][A-Za-z’']*(?: [A-Z][A-Za-z’']*)?)?))?")
VAGUE = frozenset("something stuff things thing new item items product products".split())  # "got something new" names nothing
THING_RE = re.compile(r"(?:got in|just got|got|have|new in|came in)\s+(?:some\s+|a\s+|the\s+|new\s+)?(?P<thing>[A-Za-z][\w’' -]{2,40}?)(?=\s+(?:from|by|made)\b|[,.;!]|\s+\d|$)", re.I)
STORY_RE = re.compile(r"^(they|he|she|it(?:'s|’s| is| was)|the (?:family|farm|crew|team|folks|owners?|bees?|couple))\b", re.I)
EXTRACT_PROMPT = (
    "Read the owner's message about one new item for the Avocado Shack shelf. Reply with exactly one JSON object with these keys, "
    "each a string copied from the message or null: " + ", ".join(FACT_KEYS) + ". "
    "name = the product as he calls it (maker first, like 'Cal Poly honey'); maker = who makes or grows it; place = where the maker is "
    "based, only if he said it; story = his own sentences about the maker, only if he said any; kind = the thing itself ('honey'); "
    "shelf = only if he named a shelf; container = jar, bag and so on; size and price exactly as written; availability = yes, limited "
    "or no from his words; use = how he said to eat it. Never add a fact, claim, origin, ingredient or story that is not in the message. "
    "Use null for anything he did not say. Add nothing else.")


# ---------------------------------------------------------------- reading the message
def _fold(text) -> str:
    return claims.fold(text)


def _has(haystack: str, needle: str) -> bool:
    return bool(needle) and re.search(r"(?<!\w)" + re.escape(_fold(needle)) + r"(?!\w)", _fold(haystack)) is not None


def kind_index(content) -> dict:
    """{kind word: {"shelf": majority shelf, "serving": [(id, sentence)], "count": n}} from the live catalog (last word of a name)."""
    shelves, serving, count = defaultdict(Counter), defaultdict(list), Counter()
    for p in sorted(content.products, key=lambda r: r["id"]):
        if p.get("status") != "active": continue
        kind = _fold(p["name"]).split()[-1]
        shelves[kind][p["category"]] += 1
        count[kind] += 1
        serving[kind] += [(p["id"], s) for s in hs.sentences(p["description"])[1:]]
    return {k: {"shelf": shelves[k].most_common(1)[0][0], "serving": serving[k], "count": count[k]} for k in count}


def find_maker(message: str, makers: dict):
    """The one visible maker whose key or name is in the message (longest wins), else None."""
    hits = [(len(m["name"]), k) for k, m in makers.items() if not m.get("hidden") and (_has(message, k) or _has(message, m["name"]))]
    return max(hits)[1] if hits else None


def stated_shelf(text: str):
    """The shelf he named ("on the pantry shelf"), else None (a negated mention does not count)."""
    return _shelf_evidence(_fold(text))


def extract_facts(message: str, content) -> dict:
    """The plain-regex reader: what the message says, nothing more. Every key of FACT_KEYS is present (None when unsaid)."""
    text = " ".join(message.split())
    facts = dict.fromkeys(FACT_KEYS)
    key = find_maker(text, content.makers)
    index = kind_index(content)
    words = re.findall(r"[\w’'-]+", text)
    lead = re.findall(r"[\w’'-]+", re.split(r"(?<=[.!?])\s+", text)[0])  # the item sentence: later sentences are about the maker or its use
    thing = None  # the product phrase: what he "got in" (maker/story/serving words after it are not the product)
    if (m := THING_RE.search(text)): thing = re.sub(r"(?i)^in\s+", "", m.group("thing").strip(" ,"))
    if thing and thing.split()[-1].lower() in VAGUE: thing = None
    if thing:
        kinds = [w for w in re.findall(r"[\w’'-]+", thing) if _fold(w) in index]
    else:  # no "got in X": the first sentence up to the maker ("from/by/made") only, never his story
        head = re.split(r"(?i)\b(?:from|by|made)\b|[.!?;]", text, maxsplit=1)[0]
        kinds = [w for w in re.findall(r"[\w’'-]+", head) if _fold(w) in index]
    facts["kind"] = _fold(kinds[-1]) if kinds else None
    if (m := PRICE_RE.search(text)): facts["price"] = m.group(0)
    if (m := SIZE_RE.search(text)): facts["size"] = m.group(0)
    facts["container"] = next((c for c in CONTAINERS if _has(text, c)), None)
    facts["availability"] = _availability_evidence(_fold(text))
    if (m := USE_RE.search(text)): facts["use"] = f"{m.group(1).lower()} {m.group(2).strip().lower()}"
    facts["shelf"] = stated_shelf(text)
    if key:
        facts["maker"] = content.makers[key]["name"]
    elif (m := NEW_MAKER_RE.search(text)):
        facts["maker"] = m.group("name").strip(" .,")
        facts["place"] = (m.group("place") or "").strip(" .,") or None
    if thing:
        if not facts["kind"]: facts["kind"] = _fold(thing.split()[-1])
        phrase = thing
    elif facts["kind"]:
        src = lead if any(_fold(w) == facts["kind"] for w in lead) else words
        at = max(i for i, w in enumerate(src) if _fold(w) == facts["kind"])
        variety = []
        for w in reversed(src[max(0, at - 2):at]):  # lowercase describing words right before the thing, up to two
            if w[:1].islower() and w.lower() not in STOP and w.lower() not in CONTAINERS and not w[0].isdigit(): variety.insert(0, w)
            else: break
        phrase = " ".join([*variety, facts["kind"]])
    else:
        phrase = None
    if phrase:
        phrase = " ".join(w for w in phrase.split() if not (facts["maker"] and _has(facts["maker"], w) and w[:1].isupper()))
        facts["name"] = " ".join(x for x in (facts["maker"], phrase) if x) if facts["maker"] else _cap(phrase)
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    story = [s for s in sents[1:] if STORY_RE.match(s) and not PRICE_RE.search(s)]
    if story and facts["maker"]: facts["story"] = " ".join(_third_person(s, facts["maker"]) for s in story)
    return facts


def _third_person(sentence: str, maker: str) -> str:
    """'They keep bees on the hill.' -> 'Maker keeps bees on the hill.' (regular verbs; anything else is left for the LLM path)."""
    m = re.match(r"(?i)they(?:'re| are)\s+(.*)", sentence)
    if m: return f"{maker} is {m.group(1)}"
    m = re.match(r"(?i)they\s+(have|do|go|are)\b(.*)", sentence)
    if m: return f"{maker} {dict(have='has', do='does', go='goes', are='is')[m.group(1).lower()]}{m.group(2)}"
    m = re.match(r"(?i)(?:they|he|she)\s+([a-z]+?)(es|s|e|y)?\b(.*)", sentence)
    if not m: return sentence
    verb = (m.group(1) + (m.group(2) or ""))
    verb = verb[:-1] + "ies" if verb.endswith("y") and verb[-2:-1] not in "aeiou" else verb + ("es" if verb.endswith(("s", "sh", "ch", "x")) else "s")
    return f"{maker} {verb}{m.group(3)}"


def parse_facts(raw: str) -> dict:
    """The LLM's JSON reply as facts: only FACT_KEYS, each a non-empty string or None; anything else is ignored."""
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError, RecursionError):  # RecursionError: decoder-excessive nesting is just invalid JSON
        return dict.fromkeys(FACT_KEYS)
    doc = doc if isinstance(doc, dict) else {}
    return {k: (doc[k].strip() or None) if isinstance(doc.get(k), str) else None for k in FACT_KEYS}


def _stem(word: str) -> str:
    word = word.casefold()
    for tail, repl in (("ies", "y"), ("es", ""), ("s", "")):
        if word.endswith(tail) and len(word) > len(tail) + 2: return word[:-len(tail)] + repl
    return word


def _stems(text) -> list:
    return [_stem(w) for w in re.findall(r"[\w’'-]+", _fold(text))]


AUX = frozenset("is are was were has have had does do did goes go".split())  # the verbs "they" -> "Maker" may change; never a fact on their own
NEGSET = frozenset(claims.NEGATORS)


def _unaffirmed_terms(text: str, low: str) -> list:
    """Claim terms in `text` that the (folded) owner message does not affirm: absent, or only said with a negator (\"not organic\")."""
    return [t for t in claims.TERMS + claims.FARM_TERMS + claims.HEALTH_AWARD_TERMS if hs._has_term(text, t) and not claims._affirmed(claims._pattern(t), low)]


def claim_terms(text) -> list:
    """Every claim term in `text`, affirmed or not. Under the claim-omission policy (left_off: a claim goes on a card only when he
    asks for it by name and it is documented) none of these may reach a public field of a new-item draft."""
    return [t for t in claims.TERMS + claims.FARM_TERMS + claims.HEALTH_AWARD_TERMS if text and hs._has_term(text, t)]


def without_claims(name, kind):
    """The public name with every claim term taken out ('Organic honey' -> 'Honey'); the kind word is kept or put back."""
    if not name or not claim_terms(name): return name
    # Match the detector's folded text, but cut spans from the original name.
    # Expanded characters share a source span; discarded combining marks belong
    # to the preceding span so a removed claim cannot leave its accent behind.
    folded, spans = [], []
    for i, char in enumerate(name):
        plain = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c))
        part = plain.translate(claims._PUNCT).casefold()
        if not part and spans:
            spans[-1] = (spans[-1][0], i + 1)
        for c in part:
            if c.isspace():
                if not folded: continue
                if folded[-1] == " ":
                    spans[-1] = (spans[-1][0], i + 1)
                    continue
                c = " "
            folded.append(c)
            spans.append((i, i + 1))
    text = "".join(folded).rstrip()
    removed = set()
    for term in claim_terms(name):
        for match in claims._pattern(term).finditer(text):
            removed.update(range(spans[match.start()][0], spans[match.end() - 1][1]))
    name = "".join(" " if i in removed else c for i, c in enumerate(name))
    name = " ".join(name.split()).strip(" ,-")
    if claim_terms(name): return without_claims(name, kind)
    if kind and not any(_fold(w) == _fold(kind) for w in name.split()): name = " ".join(x for x in (name, kind) if x)
    return _cap(name) if name else None


def defer_claims(facts: dict) -> dict:
    """The facts as the public fields may use them: no claim term in the name, the story or the serving use (left_off lists them)."""
    out = {**facts, "name": without_claims(facts.get("name"), facts.get("kind"))}
    for key in ("story", "use"):
        if claim_terms(out.get(key)): out[key] = None
    return out


def _asserted(value: str, low: str) -> bool:
    """The value is in the message and at least one occurrence is not negated (the claims gate's own negator rule)."""
    return claims._affirmed(claims._pattern(value), low)


PRONOUN_START = re.compile(r"(?i)^(they|he|she|it|we|i|our|my|their|his|her)\b")
JOINERS = re.compile(r"(?i)\b(but|and|or|so|that|which|who|whom|whose|because|while|though|although|if|when|whereas|then|yet|except|unless)\b|[,;:()—]")


def _story_ok(story: str, maker, message: str) -> bool:
    """A story sentence is kept only if its meaning is provably Michael's, by construction, never by word matching: it is ONE of his
    own sentences word for word (its subject a name, not a pronoun), or ONE of his simple 'They/He/She <verb> ...' sentences with only
    the pronoun replaced by the maker's name (the single conjugation _third_person does). A sentence with any joiner (but, and, that,
    which, a comma ...) cannot be rewritten, since a negator or a subject could land on the wrong clause: it is dropped and the one-line
    'is based in' note is used. Claim terms he did not affirm are refused either way."""
    low = _fold(message)
    sources = [s.strip() for s in re.split(r"(?<=[.!?])\s+", message) if s.strip()]
    if _unaffirmed_terms(story, low): return False
    sents = hs.sentences(story)
    if not sents: return False
    for sent in sents:
        want = _fold(sent)
        for src in sources:
            if _fold(src) == want and not PRONOUN_START.match(src.strip()): break  # his own sentence, as he wrote it
            if maker and re.match(r"(?i)(they|he|she)\b", src) and not JOINERS.search(src) and _fold(_third_person(src, maker)) == want: break  # only the pronoun
        else:
            return False
    return True


def _availability_evidence(low: str):
    """The availability word his own words support (no > limited > yes, a negated phrase does not count), else None."""
    return next((word for word in ("no", "limited", "yes") if claims._affirmed(re.compile(AVAILABILITY_WORDS[word], re.I), low)), None)


def _shelf_evidence(low: str):
    """The shelf he named (\"on the pantry shelf\", \"dairy section\"), else None."""
    for c in CATEGORIES:
        word = re.escape(SHELF_LABELS[c].split()[0].lower())
        if claims._affirmed(re.compile(rf"\b{word}\b\s+(?:shelf|section|aisle)|\b(?:shelf|section|aisle)\s*:?\s*{word}\b"), low): return c
    return None


def _same(a, b) -> bool:
    return bool(a) and bool(b) and _fold(str(a)).strip(" .,") == _fold(str(b)).strip(" .,")


def maker_relations(message: str) -> list:
    """[(maker, place or None)]: the maker relationships his own words state, 'from/by/made by/out of <Maker>[ in|, <Town, State>]'."""
    return [(m.group("name").strip(" .,"), (m.group("place") or "").strip(" .,") or None) for m in NEW_MAKER_RE.finditer(" ".join(message.split()))]


def _maker_supported(maker: str, message: str, content) -> bool:
    """A catalog maker he named (the one the plain reader finds), or the <Maker> of one of his 'from/by <Maker>' phrases."""
    key = find_maker(maker, content.makers)
    if key and key == find_maker(message, content.makers) and (_same(maker, key) or _same(maker, content.makers[key]["name"])): return True
    return any(_same(maker, name) for name, _place in maker_relations(message))


def _place_supported(place: str, maker, message: str, content) -> bool:
    """The place his words give for THAT maker ('from <maker> in <place>'), or that catalog maker's recorded place."""
    if not maker: return False
    key = find_maker(maker, content.makers)
    if key and _same(place, content.makers[key].get("place")): return True
    return any(_same(maker, name) and _same(place, where) for name, where in maker_relations(message))


def ground(facts: dict, message: str, content) -> tuple:
    """(facts kept, [what was dropped]): a value must be traceable to the message (or be a maker/kind the catalog knows),
    not negated there, and a claim word only counts when he affirmed it. Shelf and availability are never taken on trust
    from a reader: they must be what his words support (the shelf he named; the availability his phrases show), else None."""
    kept, dropped = dict(facts), []
    low = _fold(message)
    for key in ("name", "maker", "place", "story", "container", "size", "price", "use", "url"):
        value = kept.get(key)
        if not value: continue
        if key == "name":  # his product words, with the maker first: every word of it is his, no claim word he did not affirm
            ok = all(_fold(w) in low for w in re.findall(r"[\w’'-]+", value)) and not _unaffirmed_terms(value, low)
        elif key == "story":
            ok = _story_ok(value, kept.get("maker"), message)
        elif key == "maker":  # the maker must be WHO he says makes it, not just a capitalised word somewhere in the message
            ok = _asserted(value, low) and not _unaffirmed_terms(value, low) and _maker_supported(value, message, content)
        elif key == "place":  # the place must be where he says THAT maker is, not any place he mentioned
            ok = _asserted(value, low) and not _unaffirmed_terms(value, low) and _place_supported(value, kept.get("maker"), message, content)
        else:
            ok = _fold(value) in low
            if ok and key == "use": ok = _asserted(value, low) and not _unaffirmed_terms(value, low)
        if not ok:
            kept[key] = None
            dropped.append(key)
    if kept.get("kind") and not (_fold(kept["kind"]) in low and _asserted(kept["kind"], low)):
        kept["kind"], _ = None, dropped.append("kind")
    for key, evidence in (("availability", _availability_evidence(low)), ("shelf", _shelf_evidence(low))):
        if kept.get(key) != evidence:
            if kept.get(key): dropped.append(key)
            kept[key] = evidence
    if kept.get("url") and not str(kept["url"]).startswith("https://"):
        kept["url"], _ = None, dropped.append("url")
    return kept, dropped



# ---------------------------------------------------------------- writing in the shop's voice
def _town(place: str):
    head = (place or "").split(",")[0].strip()
    return head if "," in (place or "") and head and not head.lower().startswith(("near ", "north", "south")) else None


def _serving_ok(sentence: str, owner_text: str) -> bool:
    inner = re.findall(r"(?<=[a-z,;:] )[A-Z][\w’'-]*", sentence)  # a capitalised word mid-sentence names something
    terms = claim_terms(sentence)  # a catalog sentence carrying any claim is never borrowed (claim-omission policy)
    return len(sentence.split()) >= 4 and not inner and not terms and not any(c.isdigit() for c in sentence) and sentence.endswith(".")


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def writer_prompt(facts: dict, spec: dict, examples: list) -> str:
    """The prompt for a model that writes the description: voice rules from the measured spec, real examples, the facts, nothing else."""
    d = spec["descriptions"]
    rules = [f"Write one product description for the shop site: {d['sentences']['min']} to {d['sentences']['max']} sentences, "
             f"{d['chars']['p05']:.0f} to {d['chars']['p95']:.0f} characters, plain text, ending with a full stop.",
             "Voice: calm and warm; the first sentence says what it is and (if given) who makes it and where; the next suggests how to eat or use it, "
             "in the imperative ('Spoon a little beside cheese').", "No digits, prices, sizes, exclamation marks, questions, or hype words.",
             "Use ONLY these facts. Never add an organic, local, origin, ingredient, award, health or story claim that is not in them."]
    shown = "\n".join(f"- {e}" for e in examples)
    return "\n".join(rules) + "\nReal examples from the shop:\n" + shown + "\nFacts (JSON): " + json.dumps({k: v for k, v in facts.items() if v}, ensure_ascii=False)


CONNECTIVES = frozenset("from in by a an the of and at near".split())  # the only glue a fact sentence may add to the facts' own words
PROVENANCE = frozenset("""blended blend made make makes infused mixed brewed aged roasted baked grown grow grows raised harvested picked since
    years year generations generation family owned founded handmade homemade traditional recipe ingredient ingredients contains containing
    wild raw pure natural pasture century old heirloom batch artisan sourced from by near""".split())  # origin / make-up / history words: only ever from the facts


def _fact_vocab(facts: dict, maker: dict) -> set:
    """Word stems of the structured facts (and the maker record) only: NOT the whole message, so a claim he denied or never made is not in it."""
    return {s for text in (facts.get("name"), facts.get("maker"), facts.get("place"), facts.get("kind"), facts.get("container"), facts.get("use"),
                           maker.get("name"), maker.get("place")) if text for s in _stems(text)}


def writer_problems(text: str, facts: dict, maker: dict, message: str, content) -> list:
    """Why a model-written description may not be used ([] = it may). The first sentence (who makes it, where) is fact-only: every
    word is one of the facts' own words or plain glue. Later sentences are serving suggestions in the catalog's own words. Nothing in
    either may be an ingredient, origin or history word the facts lack, a claim he did not affirm, a negation or a number."""
    low, facts_vocab = _fold(message), _fact_vocab(facts, maker)
    catalog = {s for p in content.products if p.get("status") == "active" for s in _stems(p["description"])}
    openers = {s[0] for p in content.products if p.get("status") == "active" for s in (_stems(x) for x in hs.sentences(p["description"])[1:]) if s}
    sents, problems = hs.sentences(text), []
    if _unaffirmed_terms(text, low): problems.append("claim word he did not affirm: " + ", ".join(_unaffirmed_terms(text, low)))
    if any(w in NEGSET for w in re.findall(r"[\w’'-]+", _fold(text))): problems.append("a negation (the facts are written plainly)")
    fact_first = bool(facts.get("maker") or facts.get("place"))
    for n, sent in enumerate(sents):
        words = _stems(sent)
        if n == 0 and fact_first:
            extra = [w for w in words if w not in facts_vocab and w not in {_stem(c) for c in CONNECTIVES}]
            if extra: problems.append("sentence 1 says more than the facts: " + ", ".join(dict.fromkeys(extra)))
            continue
        bad_origin = [w for w in words if w in {_stem(p) for p in PROVENANCE} and w not in facts_vocab]
        unknown = [w for w in words if w not in catalog and w not in facts_vocab and w not in {_stem(c) for c in CONNECTIVES}]
        if bad_origin: problems.append(f"sentence {n + 1} states origin, ingredient or history: " + ", ".join(dict.fromkeys(bad_origin)))
        if unknown: problems.append(f"sentence {n + 1} uses words the shop never uses: " + ", ".join(dict.fromkeys(unknown)))
        if words and words[0] not in openers and words[0] not in facts_vocab and n: problems.append(f"sentence {n + 1} is not a serving suggestion like the others")
    return problems


def grounded_text(text: str, allowed: str) -> list:
    """Capitalised mid-sentence words and numbers in `text` that `allowed` (message + maker record) does not contain."""
    seen = []
    for sent in hs.sentences(text):
        for i, w in enumerate(re.findall(r"[\w’'-]+", sent)):
            if (i and w[:1].isupper() or any(c.isdigit() for c in w)) and not _has(allowed, w) and w not in seen:
                seen.append(w)
    return seen


FUNCTION_WORDS = frozenset(STOP | set("on onto into to it its is are was be as your you little some any each over under up out off then there their his her one two "
                            "first before after".split()))
CLAIM_MARKERS = re.compile(r"\b(?:with added|added|made with|contains?|containing|includes?|including|infused|blend of|mixed with|flavou?red|ingredients?)\b", re.I)


def serving_vocabulary(content) -> frozenset:
    """Stemmed words the shop already uses in the serving sentences (not the first sentence) of live descriptions."""
    return frozenset(_stem(w) for p in content.products if p.get("status") == "active"
                     for s in hs.sentences(p["description"])[1:] for w in re.findall(r"[\w’'-]+", s))


def serving_openers(content) -> frozenset:
    """Stemmed first words of the serving sentences of live descriptions (Spoon, Try, Keep, ...): the shop's imperative verbs."""
    return frozenset(_stem(re.findall(r"[\w’'-]+", s)[0]) for p in content.products if p.get("status") == "active"
                     for s in hs.sentences(p["description"])[1:] if re.findall(r"[\w’'-]+", s)
                     ) - {_stem(w) for w in FUNCTION_WORDS}


def _is_serving_suggestion(sent: str, openers) -> bool:
    words = re.findall(r"[\w’'-]+", _fold(sent))
    return bool(words) and _stem(words[0]) in openers


def ungrounded_claims(text: str, allowed: str, vocabulary, openers=frozenset()) -> list:
    """Words that assert something Michael did not say. The first sentence (what it is, who makes it) may use only his words;
    later serving sentences may also use the shop's own serving words, but never an ingredient/contents phrase."""
    known = {_stem(w) for w in re.findall(r"[\w’'-]+", _fold(allowed))} | {_stem(w) for w in FUNCTION_WORDS}
    bad = []
    for n, sent in enumerate(hs.sentences(text)):
        pool = known if n == 0 else known | vocabulary
        if n and not _is_serving_suggestion(sent, openers):  # a later sentence is a suggestion ("Spoon a little onto toast."), never an assertion ("It has butter.")
            bad.append("assertion: " + " ".join(sent.split()[:4]))
            continue
        bad += [w for w in re.findall(r"[\w’'-]+", _fold(sent)) if _stem(w) not in pool and w not in bad]
        if n and (m := CLAIM_MARKERS.search(sent)) and not CLAIM_MARKERS.search(allowed): bad.append(m.group(0))
    return bad


def writer_unproven(text: str, first, pool: list, use) -> list:
    """Sentences of a model-written description that are NOT provably safe ([] = every sentence is). Heuristic word checks cannot
    prove a sentence's meaning (roles, clauses, semicolons), so a model's text is accepted only as a CHOICE among pieces whose
    provenance is known: the deterministic fact sentence built from the facts (exactly), and the shop's own serving sentences
    for this kind, 'Try it <his use>.' and the two generic lines (each exactly, comma/semicolon clauses included)."""
    allowed = {_fold(s) for s in [*pool, *GENERIC_SERVING, *([f"Try it {use}."] if use else [])]}
    allowed_first = {_fold(first)} if first else allowed
    sents = hs.sentences(text)
    bad = []
    for n, sent in enumerate(sents):
        ok = _fold(sent) in (allowed_first if n == 0 else allowed)
        if not ok: bad.append(" ".join(sent.split()[:6]))
    return bad or ([] if sents else ["empty"])


def compose(facts: dict, content, spec: dict, message: str, writer=None) -> dict:
    """{"text", "source": template|writer, "serving_from": id|None, "writer_rejected": str|None}."""
    maker = content.makers.get(find_maker(facts.get("maker") or "", content.makers) or "", {})
    place = maker.get("place") or facts.get("place") or ""
    allowed = " ".join([message, maker.get("name", ""), maker.get("place", ""), facts.get("name") or "", facts.get("maker") or ""])
    index = kind_index(content)
    rejected = None
    kind_phrase = _cap(re.sub(rf"^{re.escape(facts.get('maker') or '~')}\s+", "", facts.get("name") or "", flags=re.I) or facts.get("kind") or "")
    first = None
    if facts.get("maker") and kind_phrase and kind_phrase.lower() != _fold(facts["maker"]):
        town = _town(place)
        first = f"{kind_phrase} from {facts['maker']}" + (f" in {town}" if town else "") + "."
    pool = [(i, s) for i, s in index.get(facts.get("kind") or "", {}).get("serving", []) if _serving_ok(s, message)]
    if writer is not None:
        examples = [s for _id, s in index.get(facts.get("kind") or "", {}).get("serving", [])[:4]] or [e["description"] for e in spec["descriptions"]["examples"][:4]]
        text = (writer(writer_prompt(facts, spec, examples)) or "").strip()
        bad = grounded_text(text, allowed) + [w for w in ungrounded_claims(text, allowed, serving_vocabulary(content), serving_openers(content)) if w not in grounded_text(text, allowed)]
        problems = writer_problems(text, facts, maker, message, content)
        check = hs.check_description(text, spec, name=facts.get("name"), owner_text=message)
        pieces = writer_unproven(text, first, [s for _i, s in pool], facts.get("use"))
        if claim_terms(text): problems = [*problems, "a claim word (claims go on a card only on request): " + ", ".join(claim_terms(text))]
        if not bad and not problems and not pieces and check["pass"]:
            return {"text": text, "source": "writer", "serving_from": None, "writer_rejected": None}
        rejected = (("not in Michael's words: " + ", ".join(bad)) if bad else "; ".join(problems) if problems else
                    ("not built from the facts and the shop's own serving sentences: " + "; ".join(pieces)) if pieces else
                    "failed: " + ", ".join(c["name"] for c in check["checks"] if not c["ok"]))[:240]
    serving, source_id = [], None
    if facts.get("use"):
        serving = [f"Try it {facts['use']}."]
    else:
        serving = [s for _i, s in pool[:1 if first else 2]]  # without a maker sentence the catalog uses two serving sentences
        source_id = pool[0][0] if pool else None
    if len(serving) + bool(first) < 2:  # the catalog never has one-sentence descriptions of this kind
        serving.append(GENERIC_SERVING[0 if not serving else 1])
    text = " ".join(s for s in (first, *serving) if s)
    return {"text": text, "source": "template", "serving_from": source_id, "writer_rejected": rejected}


def alt_text(facts: dict) -> str:
    name = facts.get("name") or _cap(facts.get("kind") or "Item")
    return f"{name} in a {facts['container']}" if facts.get("container") else name


# ---------------------------------------------------------------- the draft
def next_product_id(content) -> str:
    numbers = [int(m.group(1)) for p in content.products if (m := re.fullmatch(r"photo-product-(\d+)", p["id"]))]
    return "photo-product-%03d" % (max(numbers, default=0) + 1)


def question(facts: dict, content, label=None, maker_unsupported=False):
    """ONE short question for the most important thing the page shows and the message lacks, else None."""
    if not facts.get("name") and not facts.get("kind"):
        if label and (label.get("name") or label.get("brand")):  # the existing label-reader path, as a question to confirm
            said = " ".join(v for v in (label.get("brand"), label.get("name")) if v)
            return f"The label looks like: {said}. Is that right? Say which product it is either way."
        return "What is this item called?"
    if maker_unsupported:  # a maker his words do not tie to the item (a town, a word elsewhere): confirm, never guess
        return f"Who makes the {facts.get('kind') or 'item'}, and what town and state are they in?"
    new_maker = facts.get("maker") and not find_maker(facts["maker"], content.makers)
    if new_maker and not (facts.get("place") and "," in facts["place"]):
        return f"Where is {facts['maker']} based (town and state)?"
    if not (facts.get("shelf") or kind_index(content).get(facts.get("kind") or "", {}).get("shelf")):
        shelves = [SHELF_LABELS[c] for c in CATEGORIES]
        return f"Which shelf does it go on: {', '.join(shelves[:-1])} or {shelves[-1]}?"
    return None


def draft(message: str, photo: bytes, *, content, spec=None, facts=None, label=None, renderer=None, writer=None,
          selection_checked=False) -> dict:
    """One complete new-item draft (see the module docstring). `facts` is the LLM reader's result (parse_facts); None uses the regex reader.
    `selection_checked` is True when the shop's shelf check is current today (product.set_availability is refused otherwise)."""
    spec = spec or hs.load_spec()
    raw = facts if facts is not None else extract_facts(message, content)
    facts, dropped = ground({**dict.fromkeys(FACT_KEYS), **raw}, message, content)
    facts = defer_claims(facts)
    base = {"facts": facts, "dropped": dropped, "left_off": [], "private": {}, "style": {}}
    try:  # the store's own byte gate first: empty, over 20 MB, not JPEG/PNG, broken structure -> one fixed reply, no ops
        media.check_photo(photo)
    except media.Refused as exc:
        return _refused(base, exc.code, exc.reply)
    except TypeError:
        return _refused(base, "unreadable", media.REPLIES["unreadable"])
    ask = question(facts, content, label, maker_unsupported=bool(raw.get("maker")) and "maker" in dropped)
    if ask:
        return {**base, "status": "question", "question": ask, "reply": ask, "ops": []}
    key = find_maker(facts.get("maker") or "", content.makers)
    new_maker = None
    if facts.get("maker") and not key:
        story = facts.get("story")
        sentences = hs.sentences(story) if story else []
        text = " ".join(_cap(s.strip()) if s.strip().endswith(".") else _cap(s.strip()) + "." for s in sentences) if sentences else f"{facts['maker']} is based in {facts['place']}."
        new_maker = {"key": facts["maker"], "name": facts["maker"], "place": facts["place"], "story": text,
                     **({"url": facts["url"]} if facts.get("url") else {})}
    shelf = facts.get("shelf") or kind_index(content)[facts["kind"]]["shelf"]
    name = facts.get("name") or _cap(facts["kind"])
    brand = (content.makers[key]["name"] if key else facts["maker"]) if facts.get("maker") else "Producer not identified"
    desc = compose({**facts, "name": name}, content, spec, message, writer)
    alt = alt_text({**facts, "name": name})
    sha = hashlib.sha256(photo).hexdigest()
    image: dict = {"path": f"assets/products/photo-{sha[:16]}.jpg", "sha256": sha}
    if renderer is None:
        renderer = newitem_render.render
    try:
        out = renderer(photo)
        image.update(bytes=out["jpeg"], report=out["report"], check=out["check"])
    except (hs.PillowMissing, ImportError) as exc:
        image.update(bytes=None, report={"review": [str(exc)]}, check=None)
    except (media.Refused, newitem_render.Refused) as exc:
        return _refused(base, exc.code, exc.reply)
    except Exception:  # noqa: BLE001 - a photo that cannot be decoded or drawn is one fixed refusal with no ops, never a crash
        return _refused(base, "unreadable", media.REPLIES["unreadable"])
    ops = ([{"op": "maker.add", "args": {k: v for k, v in new_maker.items()}}] if new_maker else []) + [
        {"op": "product.add", "args": {"name": name, "brand": brand, "category": shelf, "description": desc["text"], "photo": sha, "imageAlt": alt,
                                       **({"producerKey": key or new_maker["key"]} if (key or new_maker) else {})}}]
    pid = next_product_id(content)
    if facts.get("availability") and selection_checked:
        ops.append({"op": "product.set_availability", "args": {"id": pid, "available": facts["availability"]}})
    left_off = [{"what": "price", "value": facts["price"], "why": "the site shows no prices"}] if facts.get("price") else []
    left_off += [{"what": "size", "value": facts["size"], "why": "the site shows no sizes"}] if facts.get("size") else []
    said = [t for t in claims.TERMS + claims.FARM_TERMS + claims.HEALTH_AWARD_TERMS if claims._affirmed(claims._pattern(t), _fold(message))]
    left_off += [{"what": "claim", "value": t, "why": "a claim like this goes on a card only when you ask for it by name and it is documented"} for t in said]
    if facts.get("availability") and not selection_checked:
        left_off.append({"what": "availability", "value": facts["availability"], "why": "the shelf check is not done today; say 'check the selection' first"})
    product = {"id": pid, "name": name, "brand": brand, "category": shelf, "image": image["path"], "description": desc["text"],
               "producerKey": key or (new_maker["key"] if new_maker else None),
               "displayBrand": "From the market" if brand == "Producer not identified" else brand, "status": "active"}
    makers_after = {**content.makers, **({new_maker["key"]: {k: v for k, v in new_maker.items() if k != "key"}} if new_maker else {})}
    style = {"description": hs.check_description(desc["text"], spec, name=name, maker_name=facts.get("maker"), owner_text=message),
             "product": hs.check_product(product, makers_after, spec), "image": image["check"],
             **({"maker": hs.check_maker({k: v for k, v in new_maker.items() if k != "key"}, spec, key=new_maker["key"])} if new_maker else {})}
    alt_problem = _alt_problem(alt, sha)
    review = list(image["report"].get("review", [])) + ([alt_problem] if alt_problem else [])
    isolated = image["report"].get("isolation") == "cutout"
    problems = [f"{k}: {', '.join(v['hard_failures']) or 'score ' + str(v['score'])}" for k, v in style.items() if v and not v["pass"]]
    status = "draft" if not problems and not review and isolated else "draft-with-warnings"
    reply = _reply(name, shelf, desc["text"], new_maker, image, left_off, review + problems, facts["availability"] if selection_checked else None)
    return {**base, "status": status, "question": None, "ops": ops, "image": image, "alt": alt, "description": desc, "maker": new_maker,
            "shelf": SHELF_LABELS[shelf], "product": product, "left_off": left_off, "style": style, "review": review + problems,
            "private": {k: facts[k] for k in ("price", "size") if facts.get(k)}, "reply": reply}


def _refused(base: dict, code: str, reply: str) -> dict:
    """The photo cannot be used: a fixed owner reply, no ops, no picture, nothing to approve."""
    return {**base, "status": "refused", "refused": code, "question": None, "reply": reply, "ops": []}


def _reply(name, shelf, description, new_maker, image, left_off, review, availability) -> str:
    lines = [f"New item draft: {name}, on the {SHELF_LABELS[shelf]} shelf.", f"Description: {description}"]
    if new_maker: lines.append(f"New maker: {new_maker['name']}, {new_maker['place']}. Their note: {new_maker['story']}")
    lines.append("Picture: made to match the shop's other pictures." if image.get("bytes") and not review else "Picture: see the notes below.")
    if availability:
        from hass.sitegen import AVAILABILITY_WORDS  # noqa: PLC0415 - the card words, defined once in sitegen
        lines.append(f"On the card: {AVAILABILITY_WORDS[availability]}")
    for item in left_off: lines.append(f"Left off the site: {item['what']} ({item['value']}): {item['why']}.")
    lines += [f"Check: {r}" for r in review]
    return "\n".join(lines)
