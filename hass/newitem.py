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
is returned instead of a draft.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict

from hass import claims, house_style as hs
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
    """The shelf he named ("on the pantry shelf"), else None."""
    return next((c for c in CATEGORIES if re.search(rf"\b{re.escape(SHELF_LABELS[c].split()[0].lower())}\b\s+shelf", text, re.I)), None)


def extract_facts(message: str, content) -> dict:
    """The plain-regex reader: what the message says, nothing more. Every key of FACT_KEYS is present (None when unsaid)."""
    text = " ".join(message.split())
    facts = dict.fromkeys(FACT_KEYS)
    key = find_maker(text, content.makers)
    index = kind_index(content)
    words = re.findall(r"[\w’'-]+", text)
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
    for word, rx in AVAILABILITY_WORDS.items():
        if re.search(rx, text, re.I):
            facts["availability"] = word
            break
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
        at = max(i for i, w in enumerate(words) if _fold(w) == facts["kind"])
        variety = []
        for w in reversed(words[max(0, at - 2):at]):  # lowercase describing words right before the thing, up to two
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
    except (TypeError, ValueError):
        return dict.fromkeys(FACT_KEYS)
    doc = doc if isinstance(doc, dict) else {}
    return {k: (doc[k].strip() or None) if isinstance(doc.get(k), str) else None for k in FACT_KEYS}


def _stem(word: str) -> str:
    word = word.casefold()
    for tail, repl in (("ies", "y"), ("es", ""), ("s", "")):
        if word.endswith(tail) and len(word) > len(tail) + 2: return word[:-len(tail)] + repl
    return word


def ground(facts: dict, message: str, content) -> tuple:
    """(facts kept, [what was dropped]): a value must be traceable to the message (or be a maker/kind the catalog knows)."""
    kept, dropped = dict(facts), []
    low = _fold(message)
    for key in ("name", "maker", "place", "story", "container", "size", "price", "use", "url"):
        value = kept.get(key)
        if not value: continue
        if key == "name":  # his product words, with the maker first: every word of it is his
            ok = all(_fold(w) in low for w in re.findall(r"[\w’'-]+", value))
        elif key == "story":  # his sentences; a verb may only change its ending (keep -> keeps) when "they" became the maker
            known = {_stem(w) for w in re.findall(r"[\w’'-]+", low)} | {_stem(w) for w in re.findall(r"[\w’'-]+", _fold(kept.get("maker") or ""))}
            ok = all(_stem(w) in known or w.lower() in ("is", "has", "does", "goes") for w in re.findall(r"[\w’'-]+", _fold(value)))
        else:
            ok = _fold(value) in low
        if not ok:
            kept[key] = None
            dropped.append(key)
    if kept.get("availability") and not (kept["availability"] in AVAILABILITY_WORDS and re.search(AVAILABILITY_WORDS[kept["availability"]], message, re.I)):
        kept["availability"] = None  # not an allowed value, or his words do not say it
        dropped.append("availability")
    if kept.get("shelf") and kept["shelf"] != stated_shelf(message):
        kept["shelf"] = None  # only a shelf he named; otherwise it comes from the kind (or one question)
        dropped.append("shelf")
    if kept.get("kind") and _fold(kept["kind"]) not in low:
        kept["kind"], _ = None, dropped.append("kind")
    if kept.get("url") and not str(kept["url"]).startswith("https://"):
        kept["url"], _ = None, dropped.append("url")
    return kept, dropped


# ---------------------------------------------------------------- writing in the shop's voice
def _town(place: str):
    head = (place or "").split(",")[0].strip()
    return head if "," in (place or "") and head and not head.lower().startswith(("near ", "north", "south")) else None


def _serving_ok(sentence: str, owner_text: str) -> bool:
    inner = re.findall(r"(?<=[a-z,;:] )[A-Z][\w’'-]*", sentence)  # a capitalised word mid-sentence names something
    terms = [t for t in claims.TERMS + claims.FARM_TERMS + claims.HEALTH_AWARD_TERMS if hs._has_term(sentence, t) and not hs._has_term(owner_text, t)]
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


def compose(facts: dict, content, spec: dict, message: str, writer=None) -> dict:
    """{"text", "source": template|writer, "serving_from": id|None, "writer_rejected": str|None}."""
    maker = content.makers.get(find_maker(facts.get("maker") or "", content.makers) or "", {})
    place = maker.get("place") or facts.get("place") or ""
    allowed = " ".join([message, maker.get("name", ""), maker.get("place", ""), facts.get("name") or "", facts.get("maker") or ""])
    index = kind_index(content)
    rejected = None
    if writer is not None:
        examples = [s for _id, s in index.get(facts.get("kind") or "", {}).get("serving", [])[:4]] or [e["description"] for e in spec["descriptions"]["examples"][:4]]
        text = (writer(writer_prompt(facts, spec, examples)) or "").strip()
        bad = grounded_text(text, allowed) + [w for w in ungrounded_claims(text, allowed, serving_vocabulary(content), serving_openers(content)) if w not in grounded_text(text, allowed)]
        check = hs.check_description(text, spec, name=facts.get("name"), owner_text=message)
        if not bad and check["pass"]:
            return {"text": text, "source": "writer", "serving_from": None, "writer_rejected": None}
        rejected = ("not in Michael's words: " + ", ".join(bad)) if bad else "failed: " + ", ".join(c["name"] for c in check["checks"] if not c["ok"])[:120]
    kind_phrase = _cap(re.sub(rf"^{re.escape(facts.get('maker') or '~')}\s+", "", facts.get("name") or "", flags=re.I) or facts.get("kind") or "")
    first = None
    if facts.get("maker") and kind_phrase and kind_phrase.lower() != _fold(facts["maker"]):
        town = _town(place)
        first = f"{kind_phrase} from {facts['maker']}" + (f" in {town}" if town else "") + "."
    serving, source_id = [], None
    if facts.get("use"):
        serving = [f"Try it {facts['use']}."]
    else:
        pool = [(i, s) for i, s in index.get(facts.get("kind") or "", {}).get("serving", []) if _serving_ok(s, message)]
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


def question(facts: dict, content, label=None):
    """ONE short question for the most important thing the page shows and the message lacks, else None."""
    if not facts.get("name") and not facts.get("kind"):
        if label and (label.get("name") or label.get("brand")):  # the existing label-reader path, as a question to confirm
            said = " ".join(v for v in (label.get("brand"), label.get("name")) if v)
            return f"The label looks like: {said}. Is that right? Say which product it is either way."
        return "What is this item called?"
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
    ask = question(facts, content, label)
    base = {"facts": facts, "dropped": dropped, "left_off": [], "private": {}, "style": {}}
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
        from hass import newitem_render  # noqa: PLC0415 - Pillow is optional
        renderer = newitem_render.render
    try:
        out = renderer(photo)
        image.update(bytes=out["jpeg"], report=out["report"], check=out["check"])
    except (hs.PillowMissing, ImportError) as exc:
        image.update(bytes=None, report={"review": [str(exc)]}, check=None)
    ops = ([{"op": "maker.add", "args": {k: v for k, v in new_maker.items()}}] if new_maker else []) + [
        {"op": "product.add", "args": {"name": name, "brand": brand, "category": shelf, "description": desc["text"], "photo": sha, "imageAlt": alt,
                                       **({"producerKey": key or new_maker["key"]} if (key or new_maker) else {})}}]
    pid = next_product_id(content)
    if facts.get("availability") and selection_checked:
        ops.append({"op": "product.set_availability", "args": {"id": pid, "available": facts["availability"]}})
    left_off = [{"what": "price", "value": facts["price"], "why": "the site shows no prices"}] if facts.get("price") else []
    left_off += [{"what": "size", "value": facts["size"], "why": "the site shows no sizes"}] if facts.get("size") else []
    said = [t for t in claims.TERMS + claims.FARM_TERMS + claims.HEALTH_AWARD_TERMS if hs._has_term(message, t)]
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
