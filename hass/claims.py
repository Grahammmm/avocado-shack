"""NB-AV-05 (H03/H05): organic, origin, grade, process, diet and maker claims a draft adds that the owner did not say.

Pure and stdlib-only. After the editor prepares a draft, every text field it changes is scanned for claim terms that
are new (more of them than before) and absent from the owner's message; a new producerKey must name a maker the owner
named (by key or by name). Matching is on folded text and whole words: "organically" is not "organic", "locale" is
not "local". A revert draft (only history.revert ops) restores earlier text and is never checked.
RF2030-4: an owner word with a negator among the 3 words before it in its clause ("not organic", "isn't local") is not
said; fail-closed, so "not only organic but local" leaves "organic" unsaid and the owner gets the claim question.
RF2030-5: a list-of-text field (store hours lines) is checked as its newline-joined lines; other lists are skipped.
RF0250-3: a maker key or name the owner only negates is not named.
RF2330-12: fair-trade, animal-welfare and farming-method claims also need the owner's words.
RF1230-17: negators also count typed without the apostrophe ("isnt", "dont"); "wont"/"cant" may over-ask (fail-closed).
AV2022-04: a changed product brand/displayBrand or maker place must share a word with the owner's text; a maker url's host.
AV0022-11: events and routeIdeas text is also scanned for ACCESS_TERMS (dogs, wheelchair, permit, parking); longest term wins.
AV0022-12: an events number with a unit (mi, km, ft, hours, min; ranges give both ends) a draft adds must be in the owner's
text or in the text of the route idea the hike's trailId names; "3.20 miles" is "3.2 mi", "3,2" is 3.2; "5k", "10h" are not.
RF0220-11: a store record's notice.text and homeImage.imageAlt strings are checked like any text field (labels "notice.text",
"homeImage.imageAlt"); no other dictionary is scanned, and a leaf that is not a string is skipped.
"""
import re
import unicodedata
from collections import Counter
from decimal import Decimal

TERMS = ("organic", "certified", "pesticide-free", "spray-free", "non-gmo", "local", "locally", "grown in", "made in",
         "raised in", "harvested in", "sourced from", "produced in", "family farm", "estate",
         "extra virgin", "cold pressed", "first press", "unfiltered", "unpasteurized", "raw honey", "gluten-free",
         "dairy-free", "nut-free", "sugar-free", "vegan", "kosher", "halal", "all natural", "no preservatives", "grass-fed",
         "pasture-raised", "wild-caught")
_PUNCT = str.maketrans({**{c: "'" for c in "\u2018\u2019\u201b\u02bc\u0060\u00b4\u2032"},
                        **{c: '"' for c in "\u201c\u201d\u201e\u2033"}, **{chr(c): "-" for c in range(0x2010, 0x2016)}})


def fold(text) -> str:
    """NFKD, combining marks dropped, typographic apostrophes/quotes/dashes made ASCII, casefolded, spaces collapsed."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    return " ".join(plain.translate(_PUNCT).casefold().split())


def _pattern(phrase: str):
    """Whole words; a space or hyphen between words matches either ("pesticide free" is "pesticide-free")."""
    words = re.split(r"[-\s]+", fold(phrase))
    return re.compile(r"(?<!\w)" + r"[-\s]".join(re.escape(w) for w in words) + r"(?!\w)")


FARM_TERMS = ("fair trade", "fairtrade", "free-range", "cage-free", "hormone-free", "antibiotic-free", "biodynamic",
              "regenerative", "chemical-free", "unsprayed")
_TERM_RES = tuple((term, _pattern(term)) for term in TERMS + FARM_TERMS)
ACCESS_TERMS = ("dogs allowed", "dogs welcome", "dog friendly", "dog-friendly", "pet friendly", "leashed dogs",
                "wheelchair accessible", "wheelchair friendly", "ada accessible", "stroller friendly", "no permit",
                "no permit needed", "permit not required", "free parking", "parking available", "open to the public",
                "public access", "kid friendly", "family friendly", "safe for kids", "restrooms", "drinking water")
_ACCESS_RES = tuple((t, _pattern(t)) for i, t in enumerate(ACCESS_TERMS)  # one entry per spelling (hyphen = space)
                    if _pattern(t) not in [_pattern(u) for u in ACCESS_TERMS[:i]])


def _access_counts(text: str) -> dict:
    """{term: matches} in folded text, a match inside a longer term's match (\"no permit\" in \"no permit needed\") left out."""
    found = [(m.span(), term) for term, rx in _ACCESS_RES for m in rx.finditer(text)]
    kept = [(sp, t) for sp, t in found if not any(o != sp and o[0] <= sp[0] and sp[1] <= o[1] for o, _t in found)]
    return {term: sum(t == term for _s, t in kept) for term, _rx in _ACCESS_RES}


UNITS = {"mi": "mi", "mile": "mi", "miles": "mi", "km": "km", "kilometer": "km", "kilometers": "km", "kilometre": "km",
         "kilometres": "km", "ft": "ft", "foot": "ft", "feet": "ft", "hr": "hour", "hrs": "hour", "hour": "hour",
         "hours": "hour", "min": "min", "mins": "min", "minute": "min", "minutes": "min"}  # "h" alone is not a unit
_NUM = r"\d+(?:[.,]\d+)?"
QTY_RE = re.compile(rf"(?<![\w.,:])({_NUM})(?:\s*(?:[-–]|to)\s*({_NUM}))?\s*({'|'.join(sorted(UNITS, key=len, reverse=True))})(?!\w)")


def _quantities(text: str) -> list:
    """[(matched text, ((number, unit), ...))] in folded text; a range gives both ends, numbers as Decimal (3.0 is 3)."""
    return [(m.group(0), tuple((Decimal(n.replace(",", ".")), UNITS[m.group(3)]) for n in m.group(1, 2) if n))
            for m in QTY_RE.finditer(text)]


def _pairs(*texts) -> set:
    return {p for t in texts for _m, ps in _quantities(fold(t)) for p in ps}


NEGATORS = ("not", "no", "never", "nor", "without", "isn't", "aren't", "wasn't", "weren't", "don't", "doesn't", "didn't",
            "won't", "cannot", "can't", "isnt", "arent", "wasnt", "werent", "dont", "doesnt", "didnt", "wont", "cant",
            "hasn't", "haven't", "hadn't", "hasnt", "havent", "hadnt")
_CLAUSE = re.compile(r"[.!?;:\n]")


def _affirmed(rx, owner: str) -> bool:
    """True when some match of rx in the folded owner text (newlines kept) has no negator among the (up to) 3 words
    just before it in its clause. Clauses end at . ! ? ; : or a newline; words split on whitespace, , " ( ) stripped."""
    for clause in _CLAUSE.split(owner):
        for m in rx.finditer(clause):
            words = [w for w in (w.strip(',"()') for w in clause[:m.start()].split()) if w]
            if not set(words[-3:]) & set(NEGATORS):
                return True
    return False


SOURCE_FIELDS = {"products": ("brand", "displayBrand"), "makers": ("place", "url")}
STOP = {"the", "and", "of", "a", "an", "co", "inc", "llc", "company"}
PLACEHOLDER = "Producer not identified"


def _words(value) -> set:
    """Folded words of value, stop words and single characters dropped."""
    return {w for w in re.findall(r"\w+", fold(value)) if w not in STOP and len(w) > 1}


def _host(url) -> str:
    """Folded host of url (scheme and user part skipped, port dropped), leading "www." removed; "" when there is none."""
    m = re.match(r"(?:[a-z][a-z0-9+.-]*://)?(?:[^@/?#\s]*@)?([^/:?#\s]*)", fold(url))
    host = m.group(1).strip(".") if m else ""
    return host[4:] if host.startswith("www.") else host


def _source_hit(field: str, new: str, owner: str) -> bool:
    """True when a source field's new value is not backed by the owner's (folded) text."""
    if new == PLACEHOLDER: return False
    if field == "url":
        host = _host(new)
        return not host or not re.search(r"(?<![\w.-])(?:www\.)?" + re.escape(host) + r"(?![\w-]|\.\w)", owner)
    words = _words(new)
    return bool(words) and not words & set(re.findall(r"\w+", owner))


def _lines(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _said(phrase, lines: str) -> bool:
    return bool(isinstance(phrase, str) and phrase.strip() and _affirmed(_pattern(phrase), lines))


NESTED_TEXT = {"homeImage": ("imageAlt",), "notice": ("text",)}  # RF0220-11: the only dict-valued store slots with free text


def _fields(r: dict, before: dict, after: dict):
    """(label, new, old) per changed-field candidate of a record, top-level fields sorted. A store record's notice and
    homeImage dicts give only their NESTED_TEXT leaves, labelled "notice.text"; an old container or leaf that is not a
    dict or string counts as empty, a new one that is not a dict is handled as any top-level value. Other dicts: skipped."""
    for field in sorted(after):
        new, old = after[field], before.get(field)
        if r.get("collection") == "store" and field in NESTED_TEXT and isinstance(new, dict):
            old = old if isinstance(old, dict) else {}
            for leaf in NESTED_TEXT[field]:
                if isinstance(new.get(leaf), str):
                    yield f"{field}.{leaf}", new[leaf], old.get(leaf)
        else:
            yield field, new, old


def unstated(draft: dict, owner_text, makers, routes=None) -> list:
    """[(where, term)] for claims the draft adds that the owner's text does not contain; where = collection key field.
    makers: {key: maker} from the content (None when unreadable: every producerKey change is then unstated).
    routes: {id: routeIdea} (None when unreadable: only the owner's text backs an events number)."""
    if all(isinstance(c, dict) and c.get("op") == "history.revert" for c in draft.get("ops") or [None]):
        return []
    records = draft.get("records") or []
    lines = "\n".join(fold(line) for line in str(owner_text or "").splitlines())  # fold() collapses newlines
    known = dict(makers or {})
    known.update({r.get("key"): r["after"] for r in records if r.get("collection") == "makers"
                  and isinstance(r.get("after"), dict)})  # a maker this same draft adds or renames
    hits = []
    for r in records:
        before = r.get("before") if isinstance(r.get("before"), dict) else {}
        after = r.get("after") if isinstance(r.get("after"), dict) else {}
        for field, new, old in _fields(r, before, after):
            if _lines(new):  # RF2030-5: a list of text (store hours) is checked as its newline-joined lines
                new, old = "\n".join(new), "\n".join(old) if _lines(old) else ""
            if not isinstance(new, str) or new == old: continue
            where = f"{r.get('collection')} {r.get('key')} {field}"
            if field == "producerKey" and r.get("collection") == "products":
                maker = known.get(new)
                name = maker.get("name") if isinstance(maker, dict) else None
                if makers is None or not (_said(new, lines) or _said(name, lines)): hits.append((where, "maker"))
                continue
            if field in SOURCE_FIELDS.get(r.get("collection"), ()) and new.strip() and _source_hit(field, new, lines):
                hits.append((where, "link" if field == "url" else field))  # AV2022-04; the term scan still runs
            text, was = fold(new), fold(old if isinstance(old, str) else "")
            hits += [(where, term) for term, rx in _TERM_RES
                     if len(rx.findall(text)) > len(rx.findall(was)) and not _affirmed(rx, lines)]
            if r.get("collection") in ("events", "routeIdeas"):  # AV0022-11
                now_n, was_n = _access_counts(text), _access_counts(was)
                hits += [(where, term) for term, rx in _ACCESS_RES
                         if now_n[term] > was_n[term] and not _affirmed(rx, lines)]
            if r.get("collection") == "events":  # AV0022-12
                trail = after.get("trailId")
                idea = routes.get(trail) if isinstance(routes, dict) and isinstance(trail, str) else None
                backed = _pairs(owner_text) | _pairs(*(v for v in idea.values() if isinstance(v, str)) if idea else ())
                now_q, was_q = _quantities(text), Counter(p for _m, ps in _quantities(was) for p in ps)
                added = {p for p, n in Counter(p for _m, ps in now_q for p in ps).items() if n > was_q[p] and p not in backed}
                hits += [(where, t) for t in dict.fromkeys(m for m, ps in now_q if added & set(ps))]
    return hits


def question(hits) -> str:
    """One owner question naming the first two hits (field and term), then how many more."""
    named = " and ".join(f'"{term}" in {where}' for where, term in hits[:2])
    more = f" and {len(hits) - 2} more" if len(hits) > 2 else ""
    if len(hits) == 1:
        return (f"I did not draft that: {named} is not in your message. Is it true? "
                "Send the change again with it in your words, or without it.")
    return (f"I did not draft that: {named}{more} are not in your message. Are they true? "
            "Send the change again with them in your words, or without them.")
