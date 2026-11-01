"""NB-AV-05 (H03/H05): organic, origin, grade, process, diet and maker claims a draft adds that the owner did not say.

Pure and stdlib-only. After the editor prepares a draft, every text field it changes is scanned for claim terms that
are new (more of them than before) and absent from the owner's message; a new producerKey must name a maker the owner
named (by key or by name). Matching is on folded text and whole words: "organically" is not "organic", "locale" is
not "local". A revert draft (only history.revert ops) restores earlier text and is never checked.
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


def _said(phrase, owner: str) -> bool:
    return bool(isinstance(phrase, str) and phrase.strip() and _pattern(phrase).search(owner))


def unstated(draft: dict, owner_text, makers) -> list:
    """[(where, term)] for claims the draft adds that the owner's text does not contain; where = collection key field.
    makers: {key: maker} from the content (None when unreadable: every producerKey change is then unstated)."""
    if all(isinstance(c, dict) and c.get("op") == "history.revert" for c in draft.get("ops") or [None]):
        return []
    owner, records = fold(owner_text or ""), draft.get("records") or []
    known = dict(makers or {})
    known.update({r.get("key"): r["after"] for r in records if r.get("collection") == "makers"
                  and isinstance(r.get("after"), dict)})  # a maker this same draft adds or renames
    hits = []
    for r in records:
        before = r.get("before") if isinstance(r.get("before"), dict) else {}
        after = r.get("after") if isinstance(r.get("after"), dict) else {}
        for field in sorted(after):
            new, old = after[field], before.get(field)
            if not isinstance(new, str) or new == old: continue
            where = f"{r.get('collection')} {r.get('key')} {field}"
            if field == "producerKey" and r.get("collection") == "products":
                maker = known.get(new)
                name = maker.get("name") if isinstance(maker, dict) else None
                if makers is None or not (_said(new, owner) or _said(name, owner)): hits.append((where, "maker"))
                continue
            text, was = fold(new), fold(old if isinstance(old, str) else "")
            hits += [(where, term) for term, rx in _TERM_RES
                     if len(rx.findall(text)) > len(rx.findall(was)) and not rx.search(owner)]
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
