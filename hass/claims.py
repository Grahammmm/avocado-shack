"""NB-AV-05 (H03/H05): organic, origin, grade, process, diet and maker claims a draft adds that the owner did not say.

Pure and stdlib-only. After the editor prepares a draft, every text field it changes is scanned for claim terms that
are new (more of them than before) and absent from the owner's message; a new producerKey must name a maker the owner
named (by key or by name). Matching is on folded text and whole words: "organically" is not "organic", "locale" is
not "local". A revert draft (only history.revert ops) restores earlier text and is never checked.
RF2030-4: an owner word with a negator among the 3 words before it in its clause ("not organic", "isn't local") is not
said; fail-closed, so "not only organic but local" leaves "organic" unsaid and the owner gets the claim question.
RF2030-5: a list-of-text field (store hours lines) is checked as its newline-joined lines; other lists are skipped.
"""
import re
import unicodedata

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


_TERM_RES = tuple((term, _pattern(term)) for term in TERMS)


NEGATORS = ("not", "no", "never", "nor", "without", "isn't", "aren't", "wasn't", "weren't", "don't", "doesn't", "didn't",
            "won't", "cannot", "can't")
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


def _lines(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _said(phrase, owner: str) -> bool:
    return bool(isinstance(phrase, str) and phrase.strip() and _pattern(phrase).search(owner))


def unstated(draft: dict, owner_text, makers) -> list:
    """[(where, term)] for claims the draft adds that the owner's text does not contain; where = collection key field.
    makers: {key: maker} from the content (None when unreadable: every producerKey change is then unstated)."""
    if all(isinstance(c, dict) and c.get("op") == "history.revert" for c in draft.get("ops") or [None]):
        return []
    owner, records = fold(owner_text or ""), draft.get("records") or []
    lines = "\n".join(fold(line) for line in str(owner_text or "").splitlines())  # fold() collapses newlines
    known = dict(makers or {})
    known.update({r.get("key"): r["after"] for r in records if r.get("collection") == "makers"
                  and isinstance(r.get("after"), dict)})  # a maker this same draft adds or renames
    hits = []
    for r in records:
        before = r.get("before") if isinstance(r.get("before"), dict) else {}
        after = r.get("after") if isinstance(r.get("after"), dict) else {}
        for field in sorted(after):
            new, old = after[field], before.get(field)
            if _lines(new):  # RF2030-5: a list of text (store hours) is checked as its newline-joined lines
                new, old = "\n".join(new), "\n".join(old) if _lines(old) else ""
            if not isinstance(new, str) or new == old: continue
            where = f"{r.get('collection')} {r.get('key')} {field}"
            if field == "producerKey" and r.get("collection") == "products":
                maker = known.get(new)
                name = maker.get("name") if isinstance(maker, dict) else None
                if makers is None or not (_said(new, owner) or _said(name, owner)): hits.append((where, "maker"))
                continue
            text, was = fold(new), fold(old if isinstance(old, str) else "")
            hits += [(where, term) for term, rx in _TERM_RES
                     if len(rx.findall(text)) > len(rx.findall(was)) and not _affirmed(rx, lines)]
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
