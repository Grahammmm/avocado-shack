"""Maker skills (SKILLS-MAKERS-1): add, edit, hide and restore a maker and their about text.

Spec: reports/hass/SKILLS-SPEC.md, group D, rows 3.16 to 3.19. Guide: docs/hass/skills/makers.md.

A maker's "about" text is the story under "Meet the maker" on each of their product cards. There is no maker page of
its own. These four skills only plan typed ops (``maker.add / edit / hide / restore``); the editor, the claims gate,
the live boundary, the preview and ``yes <code>`` approval are unchanged and still run after the plan.

Every plan is a pure function ``plan(slots, ctx) -> [{"op", "args"}]``. ``ctx`` is read, never written, and every
attribute of it is optional (without it the plan leaves to the editor's own checks what it cannot see):

    ctx.content       the loaded ``Content`` (read-only): resolve a maker by name, refuse a twin, say "it already says
                      that", name the products a hide would take with it.
    ctx.owner_text    the owner's joined texts of the open request: a story sentence that carries a claim he did not
                      say is left off (``claims.unstated``, negation aware).
    ctx.texts         the owner's messages of the open request, latest last: only the latest can say "I don't know the
                      town" (rule town-state; ``ctx.owner_text`` stands in only when there are no texts).
    ctx.source_urls   website links recorded when the site was migrated; those cannot be removed or replaced (default:
                      the frozen baseline in hass/content/migration-baseline.json, read once at import).

A plan that must stop raises ``Refusal`` (a ``ValueError`` whose ``.reply`` is the fixed plain-words owner reply and
whose ``.kind`` is "question" when one answer fixes it, else "refuse"). ``describe_*`` return the same ops plus the lines
a proposal adds: ``set_lines`` ("I set: ..."), ``left_off`` and ``notes``.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from typing import NamedTuple

from hass import claims, interpret_check, itemstd
from hass.content_model import CONTENT_DIR, FORBIDDEN_TEXT, TEXT_LIMITS, _https
from hass.nl_prep import WORD_NUMBERS
from hass.ops import catalog
from hass.skills.model import Skill, Slot, Trigger, Undo

LIMITS = TEXT_LIMITS["maker"]
MAX_NAMES = 5  # product names listed in one reply before "and N more"
PRICE_REPLY = interpret_check.PRICE_REPLY
PLAIN_TEXT_REPLY = interpret_check.PLAIN_TEXT_REPLY
PRICE_RE = re.compile(r"\$|\bper\s+(?:lb|lbs|pound|pounds|oz|ounce|ounces|kg|dozen|jar|bottle|bag)\b|"
                      r"\b\d+(?:\.\d+)?\s*(?:dollars|bucks|usd)\b|"
                      r"\b(?:\d+(?:[.,]\d+)?\s*|(?:a|an|" + "|".join(re.escape(w) for w in sorted(WORD_NUMBERS, key=len, reverse=True)) + r")\s+)"
                      r"(?:dollars?|bucks?|cents?)\b|\d\s?\u00a2|"
                      r"\b\d+(?:\.\d+)?\s+(?:a|the)\s+(?:pound|lb|dozen|ounce|oz|jar|bottle|bag)\b", re.IGNORECASE)
FIELD_WORDS = {"name": "name", "place": "town", "story": "about text", "url": "website link"}


class Refusal(ValueError):
    """A plan that stops. ``reply`` is the fixed plain-words owner reply; ``kind`` is "question" or "refuse"."""

    def __init__(self, reply: str, kind: str = "refuse"):
        super().__init__(reply)
        self.reply, self.kind = reply, kind


class Outcome(NamedTuple):
    ops: list
    set_lines: tuple = ()  # "I set: ..." (a default the owner did not give)
    left_off: tuple = ()  # "Left off: ..." (something not written, with the reason)
    notes: tuple = ()  # a plain extra sentence the proposal can add


# -- plain helpers ------------------------------------------------------------------------------------------------
def _norm(text) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    return " ".join(plain.casefold().replace("'", "").replace("\u2019", "").split())


def _clean(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _join(names, last: str) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" {last} " + names[-1]


def _product_names(products) -> str:
    names = sorted(p["name"] for p in products)
    shown, more = names[:MAX_NAMES], len(names) - MAX_NAMES
    return _join(shown, "and") + (f" and {more} more" if more > 0 else "")


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


# -- slot rules ---------------------------------------------------------------------------------------------------
def rule_no_price(text: str) -> None:
    """no-price: a price in any maker text is never written."""
    if PRICE_RE.search(text):
        raise Refusal(PRICE_REPLY)


def _text(value, field: str, ask: str | None = None) -> str:
    """One checked text slot: no price, no marks the site refuses, within its limit. A missing value asks, or is ''."""
    text = _clean(value)
    if not text:
        if ask:
            raise Refusal(ask, "question")
        return ""
    rule_no_price(text)
    if any(bad in text for bad in FORBIDDEN_TEXT):
        raise Refusal(PLAIN_TEXT_REPLY)
    if len(text) > LIMITS[field]:
        raise Refusal(f"That {FIELD_WORDS[field]} is longer than the website has room for. Could you make it shorter?")
    return text


def rule_public_url(value) -> str:
    """public-url: one public https address. A bare site name ("beehappyfarm.com") gets https://; anything else asks."""
    raw = _clean(value)
    if not raw:
        return ""
    bare = not re.match(r"[a-z][a-z0-9+.-]*://", raw, re.IGNORECASE) and re.fullmatch(
        r"(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?", raw, re.IGNORECASE)
    candidate = "https://" + raw if bare else raw
    problems: list = []
    _https(problems, "url", candidate)
    if problems:
        raise Refusal("That doesn't look like a full website address. Could you send it like https://example.com?", "question")
    return candidate


TOWN_QUESTION = "Which town are they in?"
TOWN_MISSING = "Still missing: the town"
# his own words, as the last sentence of his latest message: "I don't know the town" (straight or curly apostrophe)
# (alone, after any earlier punctuation, or straight after an unpunctuated request; a final ".", "!" or "?" is allowed)
_UNKNOWN_TOWN = re.compile(r"(?<![\w'\u2019])i\s+don['\u2019]t\s+know\s+the\s+town\s*[.!?]*$", re.IGNORECASE)


def said_unknown_town(ctx) -> bool:
    """True only when the owner's latest message (``ctx.texts[-1]``) ends with "I don't know the town". ``ctx.owner_text``
    is read only when there are no texts at all (direct plan calls). No context, a slot or an older message: False."""
    texts = getattr(ctx, "texts", None)
    if texts is not None:
        latest = texts[-1] if isinstance(texts, (list, tuple)) and texts else ""
    else:
        latest = getattr(ctx, "owner_text", None)
    return isinstance(latest, str) and bool(_UNKNOWN_TOWN.search(latest.strip()))


def rule_town_state(place: str, ctx=None) -> bool:
    """town-state (ITEM-STANDARD section 5): a place the item-standard checker does not read as "Town, State" is not
    drafted; the one question is "Which town are they in?". When the place is a region and his latest message says he
    doesn't know the town, the region is kept as he gave it and True is returned (the draft says "Still missing: the
    town"). The town he gives is used as given: nothing is looked up, corrected or completed."""
    found = itemstd.check_maker({"name": "-", "place": place, "story": "-"})
    if "producer_town" not in found["missing"]:
        return False
    if "place_is_a_region" in found["needs_a_look"] and said_unknown_town(ctx):
        return True
    raise Refusal(TOWN_QUESTION, "question")


# -- the story: his sentences, a leading pronoun replaced by the maker's name -------------------------------------
_ADVERBS = {"also", "still", "now", "mostly", "only", "always", "just", "really", "often", "even"}
_AGREE = {"are": "is", "were": "was", "have": "has", "do": "does", "go": "goes", "don't": "doesn't", "aren't": "isn't",
          "haven't": "hasn't", "weren't": "wasn't"}
_SAME = {"can", "will", "would", "could", "should", "may", "might", "must", "shall", "can't", "won't", "doesn't", "isn't",
         "wasn't", "hasn't", "has", "is", "was", "had", "did", "began", "sold", "made", "grew", "kept", "built", "ran", "took",
         "came", "went", "got", "found", "won", "brought", "left", "set", "put", "became", "told", "gave", "bought", "taught",
         "chose", "wrote", "stood", "held", "met", "led", "drew", "knew", "saw", "ground", "dug", "fed", "sent", "spent",
         "thought", "caught", "sang", "rose", "wove"}
_PRESENT = {"make", "keep", "grow", "roast", "bake", "sell", "brew", "press", "pick", "harvest", "raise", "run", "own", "use",
            "source", "supply", "ship", "serve", "offer", "work", "start", "love", "craft", "produce", "cure", "smoke", "cook",
            "mill", "blend", "pour", "stock", "farm", "tend", "care", "believe", "take", "bring", "send", "build", "find",
            "need", "want", "live", "choose", "turn", "feed", "freeze", "preserve", "dry", "ferment", "pack", "gather",
            "forage", "tap", "bottle", "carry", "treat", "show", "look", "begin", "think", "know", "like", "stir", "mix"}
_AUX = {"can", "could", "will", "would", "should", "may", "might", "must", "shall", "can't", "won't", "do", "does", "did",
        "don't", "doesn't", "didn't"}
_PRONOUN = re.compile(r"(They(?:['\u2019](?:re|ve|ll))?|She|He|His|Her|Their)(?=[\s,]|$)")
_STRICT = "make|keep|grow|roast|bake|sell|brew|harvest|raise|own|serve|offer|produce|ship|supply|gather|preserve|ferment|forage|bring|build|choose|carry"
# the second verb of "They bake and sell": a verb that is rarely a noun, or any listed verb after an adverb ("and now dry")
_CONJ = re.compile(rf"\b(and|but|or) (?:(?P<adv>(?:now|also|still|then|often|always|only|just|even) )?)(?P<verb>(?(adv)(?:{'|'.join(sorted(_PRESENT))})|(?:{_STRICT})))\b")

# where the maker stops being the subject of the verbs: an infinitive, a modal / auxiliary, a relative or subordinate clause,
# or a comma / semicolon that does not just continue with "and|but|or <verb>"
_CLAUSE = re.compile(r"\s(?:to|that|which|who|whom|whose|because|so|when|while|if|although|though|since|before|after|until|unless|where"
                     r"|can|could|will|would|should|may|might|must|shall|do|does|did|is|are|was|were|has|have|had)\b|;|,(?!\s+(?:and|but|or)\s)"
                     # a coordinated clause with its own subject: "and customers bake" (anything but a verb or adverb after and|but|or)
                     rf"|\s(?:and|but|or)\s+(?!(?:(?:now|also|still|then|often|always|only|just|even)\s+)?(?:{'|'.join(sorted(_PRESENT))})\b)")


def _third(verb: str):
    """The verb for one maker, or None when we cannot bend it safely."""
    low = verb.lower()
    if low in _SAME or low.endswith("ed"):
        return verb
    if low in _AGREE:
        return _AGREE[low]
    if low not in _PRESENT:
        return None
    if low.endswith(("s", "x", "z", "ch", "sh", "o")):
        return verb + "es"
    if low.endswith("y") and low[-2] not in "aeiou":
        return verb[:-1] + "ies"
    return verb + "s"


def _sentence(text: str, name: str) -> str:
    """One sentence with its opening pronoun replaced by the maker's name; unchanged when that cannot be done safely."""
    m = _PRONOUN.match(text)
    if not m:
        return text
    pro, rest = m.group(1), text[m.end():]
    if pro in ("His", "Her", "Their"):
        return f"{name}\u2019s{rest}"
    if pro in ("She", "He"):
        return name + rest
    if len(pro) > 4:  # They're / They've / They'll
        word = {"re": "is", "ve": "has", "ll": "will"}[pro[-2:]]
        return f"{name} {word}{rest}"
    words = rest.split()
    skipped = []
    while words and words[0].lower() in _ADVERBS:
        skipped.append(words.pop(0))
    if not words:
        return text
    head = re.match(r"[A-Za-z']+", words[0])
    verb = _third(head.group(0)) if head else None
    if head is None or verb is None:
        return text
    tail = " ".join([verb + words[0][head.end():], *words[1:]])
    if head.group(0).lower() not in _AUX:  # after a modal or "don't" the next verb stays as he wrote it ("can bake and sell")
        cut = _CLAUSE.search(tail)
        cut = cut.start() if cut else len(tail)
        same, rest = tail[:cut], tail[cut:]  # only the verbs that share the maker as subject, before any "to", "that", comma clause...
        tail = _CONJ.sub(lambda m: f"{m.group(1)} {m.group(2) or ''}{_third(m.group(3))}", same) + rest  # "... and now dry pasta"
    return " ".join([name, *skipped, tail])


def story_words(text: str, name: str) -> str:
    """His sentences as he said them, a leading They / She / He / Their / His / Her replaced by the maker's name."""
    text = _clean(text)
    if not text:
        return ""
    out = " ".join(_sentence(s, name) for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"\u201c])", text))
    return out if out[-1] in ".!?\"\u201d" else out + "."


def fallback_story(name: str, place: str) -> str:
    """D5: a maker with no story gets this one line."""
    return f"{name} is based in {place.rstrip('.')}."


def _unsaid(content, owner_text, key, before, after) -> list:
    """Claim terms in the new story that the owner's joined texts do not carry (``claims.unstated``)."""
    if owner_text is None:
        return []
    draft = {"ops": [{"op": "maker.edit" if before else "maker.add", "args": {}}],
             "records": [{"collection": "makers", "key": key, "before": before, "after": after}]}
    makers = dict(content.makers) if content is not None else {}
    return list(dict.fromkeys(term for where, term in claims.unstated(draft, owner_text, makers) if where.endswith(" story")))


# -- finding the maker --------------------------------------------------------------------------------------------
def find_maker(content, query, want: str) -> str:
    """One maker key for what the owner said. ``want`` is "visible" (edit, hide) or "hidden" (restore); a maker in
    the other state, an unknown name or several fits stop with the plain reply. With no content the value is the key."""
    query = _clean(query)
    if not query:
        raise Refusal("Which maker do you mean?", "question")
    if content is None:
        return query
    makers = content.makers
    key = query if query in makers else None
    if key is None:
        found = catalog.lookup(content, "maker", query)
        if "match" in found:
            key = found["match"]
        else:
            cands = found["candidates"]
            if not cands:
                by_norm = {_norm(m["name"]): m["name"] for m in makers.values()}
                close = [by_norm[c] for c in difflib.get_close_matches(_norm(query), list(by_norm), n=3, cutoff=0.6)]
                if close:
                    raise Refusal(f"I don't know a maker called {query}. Do you mean {_join(close, 'or')}?", "question")
                raise Refusal(f"I don't know a maker called {query}. Who is it?", "question")
            fits = [c for c in cands if (c["status"] == "hidden") == (want == "hidden")]
            if len(fits) > 1:
                raise Refusal(f"Which maker do you mean: {_join([c['name'] for c in fits], 'or')}?", "question")
            key = (fits or cands)[0]["id"]
            if not fits and len(cands) > 1:
                raise Refusal("Those makers are " + ("already on the site." if want == "hidden" else "hidden. Do you want me to bring one back first?"))
    name, hidden = makers[key]["name"], makers[key].get("hidden") is True
    if want == "visible" and hidden:
        raise Refusal(f"{name} is hidden. Do you want me to bring them back first?", "question")
    if want == "hidden" and not hidden:
        raise Refusal(f"{name} is already on the site.")
    return key


def _active_products(content, key) -> list:
    return [p for p in content.products if p.get("status") == "active" and p.get("producerKey") == key] if content else []


def _twin(content, name: str, exclude=None):
    """The first maker, other than ``exclude`` (the maker being edited), whose key or name matches ``name``."""
    if content is None:
        return None
    want = _norm(name)
    return next((k for k, m in content.makers.items()
                 if k != exclude and (_norm(k) == want or _norm(m.get("name", "")) == want)), None)


def rule_maker_twin(content, name: str, own_key=None) -> None:
    """maker-twin: the same name (case, spacing and apostrophes ignored) is never a second maker."""
    twin = _twin(content, name, own_key)
    if twin is not None:
        existing = content.makers[twin]
        if existing.get("hidden") is True:
            raise Refusal(f"{existing['name']} is on the site but hidden. Do you want me to bring them back instead?", "question")
        raise Refusal(f"{existing['name']} is already on the site. Do you want to change it instead?", "question")


# -- 3.16 maker.add -----------------------------------------------------------------------------------------------
def describe_add(slots: dict, ctx=None) -> Outcome:
    content, owner_text = getattr(ctx, "content", None), getattr(ctx, "owner_text", None)
    name = _text(slots.get("name"), "name", ask="What is the maker called?")
    place = _text(slots.get("place"), "place", ask="Where are they based (town and state)?")
    rule_maker_twin(content, name)
    url = rule_public_url(slots.get("url"))
    given = _clean(slots.get("story"))
    story, set_lines, left = "", (), ()
    if given:
        story = _text(story_words(given, name), "story")
        if terms := _unsaid(content, owner_text, name, None, {"name": name, "place": place, "story": story}):
            story, left = "", (f"the part of the story that says {_join(terms, 'and')}, because you didn't say it",)
    unknown_town = rule_town_state(place, ctx)  # after every text check: a price or a long text is said first
    if not story:  # rule story-note (D5)
        story = fallback_story(name, place)
        set_lines = (f"the about text to \u201c{story}\u201d, because you didn't give one",)
    args = {"key": name, "name": name, "place": place, "story": story}
    if url:
        args["url"] = url
    return Outcome([{"op": "maker.add", "args": args}], set_lines, left,
                   ("They show on the site as soon as a product is put on their shelf.",) + ((TOWN_MISSING,) if unknown_town else ()))


def plan_add(slots: dict, ctx=None) -> list:
    return describe_add(slots, ctx).ops


# -- 3.17 maker.edit ----------------------------------------------------------------------------------------------
def _baseline_source_urls() -> frozenset:
    """The website links recorded when the site was migrated (the frozen baseline the editor's own check protects)."""
    try:
        data = json.loads((CONTENT_DIR / "migration-baseline.json").read_text("utf-8"))
        return frozenset(v for v in data["sources"]["makerUrls"].values() if isinstance(v, str))
    except (OSError, ValueError, KeyError, AttributeError):
        return frozenset()


SOURCE_URLS = _baseline_source_urls()  # read once at import; a plan stays a pure function of its inputs


def rule_source_link(maker: dict, ctx) -> None:
    """source-link-kept: a website link the site had from the start is not removed or replaced (the editor would fail
    the migration check at the yes, so the owner is told now). ``ctx.source_urls`` overrides the frozen baseline."""
    urls = getattr(ctx, "source_urls", None)
    if maker.get("url") and maker["url"] in (SOURCE_URLS if urls is None else urls):
        raise Refusal(f"The website link for {maker['name']} was on the site from the start, so I can't remove or change it from chat. Nothing changed.")


def describe_edit(slots: dict, ctx=None) -> Outcome:
    content, owner_text = getattr(ctx, "content", None), getattr(ctx, "owner_text", None)
    key = find_maker(content, slots.get("maker"), "visible")
    maker = content.makers[key] if content is not None else {}
    shown = maker.get("name") or _clean(slots.get("maker"))
    changes: dict = {}
    for field in ("name", "place"):
        if _clean(slots.get(field)):
            changes[field] = _text(slots[field], field)
    url, clear = rule_public_url(slots.get("url")), slots.get("clear_url") is True
    if url and clear:
        raise Refusal(f"Do you want the website link for {shown} changed, or taken off?", "question")
    if url:
        changes["url"] = url
    given = _clean(slots.get("story"))
    if not (changes or given or clear):
        raise Refusal(f"What should change about {shown}?", "question")
    new_name = changes.get("name", shown)
    if "name" in changes:
        rule_maker_twin(content, changes["name"], own_key=key)
    left: list = []
    if given:
        story = _text(story_words(given, new_name), "story")
        after = {**maker, **changes, "story": story}
        if terms := _unsaid(content, owner_text, key, maker or None, after):
            left.append(f"your new about text, because it says {_join(terms, 'and')} and you didn't")
        else:
            changes["story"] = story
    unknown_town = "place" in changes and rule_town_state(changes["place"], ctx)  # only a place he gives now is checked
    notes: list = []
    if maker:  # not-already-true: say so for what is already there, and draft nothing for it
        for field in [f for f in changes if _clean(maker.get(f)) == changes[f]]:
            notes.append(f"The {FIELD_WORDS[field]} already says that.")
            del changes[field]
        if clear and "url" not in maker:
            notes.append(f"{shown} has no website link, so there is nothing to take off.")
            clear = False
        if not changes and not clear:
            if left:
                raise Refusal(f"I can't change the about text for {shown}: {left[0]}. Could you say it in your own words?")
            raise Refusal(notes[-1] if notes and "nothing to take off" in notes[-1] else f"{shown} already says that. I haven't changed anything.")
        if clear or "url" in changes:
            rule_source_link(maker, ctx)
    if unknown_town and "place" in changes:
        notes.append(TOWN_MISSING)
    args = {"key": key, **changes, **({"clearUrl": True} if clear else {})}
    return Outcome([{"op": "maker.edit", "args": args}], (), tuple(left), tuple(notes))


def plan_edit(slots: dict, ctx=None) -> list:
    return describe_edit(slots, ctx).ops


def notes(skill_name: str, slots: dict, ctx=None) -> dict:
    """The proposal-notes hook the dispatcher (and the shared kit) shows beside a draft. A maker drafted with a region because he
    doesn't know the town gets "Still missing: the town", and a maker.add he gave no story for gets the plan's own set line
    ("I set: the about text to ..., because you didn't give one."). maker.hide and maker.restore show their plan's own product-effect
    note ("This hides ... too." / "Their products stay hidden until you bring them back: ..."). Nothing else from a plan is shown."""
    out = {"say": [], "set": [], "warn": []}
    describe = {"maker.add": describe_add, "maker.edit": describe_edit, "maker.hide": describe_hide, "maker.restore": describe_restore}.get(skill_name)
    try:
        if describe is not None:
            plan = describe(dict(slots or {}), ctx)
            if skill_name in ("maker.hide", "maker.restore"):  # the plan's own product-effect note, word for word
                out["say"] += plan.notes
            elif TOWN_MISSING in plan.notes:
                out["say"].append(TOWN_MISSING)
            if skill_name == "maker.add" and not _clean((slots or {}).get("story")):  # rule story-note (D5): said before yes
                out["set"] += [f"I set: {line}." for line in plan.set_lines]
    except ValueError:  # a plan that stops has no draft to note
        pass
    return out


# -- 3.18 maker.hide ----------------------------------------------------------------------------------------------
def describe_hide(slots: dict, ctx=None) -> Outcome:
    content = getattr(ctx, "content", None)
    key = find_maker(content, slots.get("maker"), "visible")
    with_products, active = slots.get("with_products"), _active_products(content, key)
    args: dict = {"key": key}
    notes: tuple = ()
    if active:  # rule with-products
        n = len(active)
        if with_products is None:
            raise Refusal(f"Do you want me to hide {_plural(n, 'their one product', f'their {n} products')} too?", "question")
        if with_products is not True:
            raise Refusal(f"I can't hide {content.makers[key]['name']} and leave their products on the site: {_product_names(active)}. "
                          "Do you want me to hide them too?", "question")
        args["withProducts"] = True
        notes = (f"This hides {_product_names(active)} too.",)
    elif with_products is True:
        args["withProducts"] = True
    return Outcome([{"op": "maker.hide", "args": args}], (), (), notes)


def plan_hide(slots: dict, ctx=None) -> list:
    return describe_hide(slots, ctx).ops


# -- 3.19 maker.restore -------------------------------------------------------------------------------------------
def describe_restore(slots: dict, ctx=None) -> Outcome:
    content = getattr(ctx, "content", None)
    key = find_maker(content, slots.get("maker"), "hidden")
    hidden = [p for p in content.products if p.get("status") == "hidden" and p.get("producerKey") == key] if content else []
    notes = (f"Their products stay hidden until you bring them back: {_product_names(hidden)}.",) if hidden else ()
    return Outcome([{"op": "maker.restore", "args": {"key": key}}], (), (), notes)


def plan_restore(slots: dict, ctx=None) -> list:
    return describe_restore(slots, ctx).ops


# -- the skills ---------------------------------------------------------------------------------------------------
RULES = {  # every rule id a skill names maps to the function that enforces it (tested one by one)
    "maker-twin": rule_maker_twin, "no-price": rule_no_price, "public-url": rule_public_url, "story-note": fallback_story,
    "claims": _unsaid, "not-already-true": describe_edit, "source-link-kept": rule_source_link,
    "maker-visible": find_maker, "maker-hidden": find_maker, "with-products": describe_hide,
    "town-state": rule_town_state,
}
# Enforced by the editor after the plan, not by the skill: the owner sees its own plain "Heads up" line.
EDITOR_RULES = {"place-warning": "hass/ops/catalog.py maker.edit warns how many active product cards a new town relabels"}

_MAKERS, _PRODUCTS, _CASES = "hass/content/makers.json", "hass/content/products.json", "hass/tests/fixtures/skills/makers/{}.jsonl"
_GEN = (("storefront-mockup/producers.js", "producers"), ("storefront-mockup/producers.json", "producers"),
        ("storefront-mockup/index.html", "makers"))
_CARDS = (("storefront-mockup/catalog-products.js", "products"),)

SKILLS = (
    Skill(
        pack='site', targets=('site',), approval_class='A1', sandbox='preview', logs=('subjects', 'fields'), who='owner',
        name="maker.add", label="add a maker", version=1,
        summary="Add a maker with their town and a short about text; with no story, one line says where they are based.",
        triggers=(
            Trigger("add a maker: Bee Happy Farm in Atascadero, they keep bees on the hill, beehappyfarm.com"),
            Trigger("new maker rost bros morro bay, small batch roasters", "typo"),
            Trigger("I want to add a new maker", "vague"),
            Trigger("add Lonesome Dove Bakery, Paso Robles, no website"),
            Trigger("add two makers: Bee Happy in Atascadero and Roast Bros in Morro Bay", "multi"),
            Trigger("their story: Maria started it in her kitchen and now sells to the whole coast"),
        ),
        slots=(
            Slot("name", "text", required=True, ask="What is the maker called?", owner_words=True, limit=("maker", "name")),
            Slot("place", "text", required=True, ask="Where are they based (town and state)?", owner_words=True, limit=("maker", "place")),
            Slot("story", "text", required=False, default="derive:based_in_note", owner_words=True, limit=("maker", "story")),
            Slot("url", "url", required=False, owner_words=True),
        ),
        rules=("maker-twin", "claims", "no-price", "public-url", "story-note", "town-state"),
        plan=plan_add,
        edits=((_MAKERS, "makers[key]"),) + _GEN,
        side_effects=("maker-create",),
        preview="home", approval="owner-yes", live_class="private-only",
        undo=Undo("revert", "The maker is hidden, not deleted; nothing on the site shows them."),
        refuse=(
            ("a price in the maker's text", PRICE_REPLY),
            ("the maker is already on the site", "<Maker> is already on the site. Do you want to change it instead?"),
            ("the website address is not a full public https address",
             "That doesn't look like a full website address. Could you send it like https://example.com?"),
        ),
        cases=_CASES.format("maker.add"),
    ),
    Skill(
        pack='site', targets=('site',), approval_class='A1', sandbox='preview', logs=('subjects', 'fields'), who='owner',
        name="maker.edit", label="change a maker or their about text", version=1,
        summary="Change a maker's name, town, about text or website link; a new story replaces the whole text.",
        triggers=(
            Trigger("update Etto's story: they started in a small kitchen and now dry pasta slowly"),
            Trigger("stepladder is in camria not cambira", "typo"),
            Trigger("remove Etto's website"),
            Trigger("fix the maker text", "vague"),
            Trigger("Fair Hills is in San Miguel and Stepladder's site is the new link", "multi"),
            Trigger("add a line to the Etto story: all their durum is American grown"),
            Trigger("rename Linn's to Linn's Preserves"),
        ),
        slots=(
            Slot("maker", "maker_ref", required=True, ask="Which maker?"),
            Slot("name", "text", required=False, owner_words=True, limit=("maker", "name")),
            Slot("place", "text", required=False, owner_words=True, limit=("maker", "place")),
            Slot("story", "text", required=False, owner_words=True, limit=("maker", "story")),
            Slot("url", "url", required=False, owner_words=True),
            Slot("clear_url", "bool", required=False),
        ),
        rules=("maker-visible", "not-already-true", "place-warning", "source-link-kept", "claims", "no-price", "public-url",
               "maker-twin", "town-state"),
        plan=plan_edit,
        edits=((_MAKERS, "makers[key]"),) + _GEN + _CARDS,
        side_effects=("none",),
        preview="product:a product of that maker", approval="owner-yes", live_class="private-only",
        undo=Undo("revert", "none"),
        refuse=(
            ("a price in the maker's text", PRICE_REPLY),
            ("nothing would change", "<Maker> already says that. I haven't changed anything."),
            ("the maker is hidden", "<Maker> is hidden. Do you want me to bring them back first?"),
            ("the website link was on the site from the start",
             "The website link for <Maker> was on the site from the start, so I can't remove or change it from chat. Nothing changed."),
        ),
        cases=_CASES.format("maker.edit"),
    ),
    Skill(
        pack='site', targets=('site',), approval_class='A1', sandbox='preview', logs=('subjects', 'fields'), who='owner',
        name="maker.hide", label="stop carrying a maker", version=1,
        summary="Hide a maker, and with your yes their products too; nothing is deleted.",
        triggers=(
            Trigger("we stopped carrying Etto"),
            Trigger("dropp Stepladder and all their cheese", "typo"),
            Trigger("get rid of that cheese guy", "vague"),
            Trigger("drop Etto and Linn's", "multi"),
            Trigger("Etto is gone for good"),
            Trigger("pause Etto for the winter"),
            Trigger("hide Fair Hills but keep the products"),
        ),
        slots=(
            Slot("maker", "maker_ref", required=True, ask="Which maker?"),
            Slot("with_products", "bool", required=False),
        ),
        rules=("maker-visible", "with-products"),
        plan=plan_hide,
        edits=((_MAKERS, "makers[key].hidden"), (_PRODUCTS, "products[id].status")) + _GEN + _CARDS,
        side_effects=("none",),
        preview="home", approval="owner-yes", live_class="private-only",
        undo=Undo("revert", "none"),
        refuse=(
            ("the maker is already hidden", "<Maker> is hidden already."),
            ("their products would stay on the site",
             "I can't hide <Maker> and leave their products on the site. Do you want me to hide them too?"),
        ),
        cases=_CASES.format("maker.hide"),
    ),
    Skill(
        pack='site', targets=('site',), approval_class='A1', sandbox='preview', logs=('subjects', 'fields'), who='owner',
        name="maker.restore", label="bring a maker back", version=1,
        summary="Bring a hidden maker back; their products come back one by one when you ask.",
        triggers=(
            Trigger("Etto is back"),
            Trigger("bring back Stepladder"),
            Trigger("restor etto", "typo"),
            Trigger("bring back the pasta people", "vague"),
            Trigger("Etto and Linn's are back", "multi"),
            Trigger("restore Fair Hills and its products"),
            Trigger("we carry Etto again"),
        ),
        slots=(Slot("maker", "text", required=True, ask="Which maker?"),),
        rules=("maker-hidden",),
        plan=plan_restore,
        edits=((_MAKERS, "makers[key].hidden"),) + _GEN,
        side_effects=("none",),
        preview="home", approval="owner-yes", live_class="private-only",
        undo=Undo("revert", "none"),
        refuse=(
            ("the maker is already on the site", "<Maker> is already on the site."),
            ("no maker by that name", "I don't know a maker called that. Who is it?"),
        ),
        cases=_CASES.format("maker.restore"),
    ),
)
