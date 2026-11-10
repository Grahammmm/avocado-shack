"""SKILLS-ITEMPIC-1: replace one product's picture (reports/hass/SKILLS-SPEC.md 3.5, card 15 of 20).

One skill, ``item.picture``. Mike sends a photo and names the product; Hass drafts ONE ``product.set_photo`` that points the
product's picture at that photo with a caption that says what it shows. He sees the preview and the picture advice and says
yes. The editor, claims gate, live boundary, preview and ``yes <code>`` approval are unchanged.

* Slots: ``item`` (a product, asked "Which product is this photo for?"), ``photo`` (the message's photo, asked "Send the new
  photo."), ``image_alt`` (the caption; when he does not say it, the product's saved name). The op argument keeps its camel
  case: ``image_alt`` goes out as ``imageAlt``.
* Rules, all in the plan (no dispatcher rule is registered): ``hidden-or-held-refused``, ``already-this-photo``,
  ``one-photo-one-product`` (two products, or the home page and a product, on one photo asks first), ``alt-says-what-it-shows``
  and ``house-picture`` (the advice ``notes`` shows beside the draft, the same advice item.add gives).
* The photo goes through ``photos.install`` exactly as item.add's does: with ``houseRender`` on, a photo the house render will
  not stand behind is refused by the installer with its plain retake sentence and nothing is drafted (the same as item.add
  today); with it off, a photo that does not match is a warning and he may say yes knowingly (D6). A check that cannot run is
  said, never passed silently.
* A catalog illustration replaced by his photo loses the " (illustration)" caption suffix (D1): the new file is a
  ``photo-<sha16>`` file, which the page labels as a photo, and the caption is drafted from the name, never the old caption.
* Undo puts the old picture and caption back. The old picture file is never removed; the new photo file stays, unused.

Owner wording follows docs/hass/VOICE.md. Skill page: docs/hass/skills/item_picture.md.
"""
from __future__ import annotations

import importlib.util
import re

from hass import media, voice
from hass.content_model import FORBIDDEN_TEXT, INVISIBLE_RE
from hass.interpret_check import PLAIN_TEXT_REPLY
from hass.ops.photos import MAX_ALT, _alt_problem
from hass.skills.item_add import _original, picture_review  # noqa: F401 - picture_review is the AV1109-10 handover
from hass.skills.model import Skill, Slot, Trigger, Undo

ASK_ITEM = "Which product is this photo for?"
ASK_PHOTO = "Send the new photo."
ONE_AT_A_TIME = "Send the photos one at a time. Which product is this photo for?"
ONE_PLACE = "One photo can go in one place. Is this photo for the home page, or for a product?"
UNKNOWN = "I don't know a product called that. Which product is this photo for?"
NO_PHOTO = "I can't find that photo. Send the new photo."
NO_CATALOG = "I couldn't check that product just now, so nothing is changed. Try again in a moment."
ALT_ASK = ("The picture caption should say what the photo shows, like \u201cMeyer lemons in a wooden crate\u201d. "
           "What should it say?")
ALT_LONG = f"That caption is longer than the website has room for ({MAX_ALT} characters). Could you make it shorter?"
NOT_CHECKED = ("I couldn't check how this photo will look, so it may not match the other pictures. "
               "If this one is fine, just reply yes.")
OLD_STAYS = "The old picture stays in the site folder, so undo can put it back."
ILLUSTRATION = " (illustration)"

_PRODUCTS = "hass/content/products.json"
_PICTURE = ("storefront-mockup/assets/products/photo-<sha16>.<ext>", "file")
_GEN = (("storefront-mockup/catalog-products.js", "products"),)  # the home page does not list product pictures

# one photo, one product: "photos for the lemons and the plums" and "photos for lemons and plums" name two products;
# "the salt and vinegar chips" is one name. A list is told from a name by the product the model picked: a name has words of
# the picked product on BOTH sides of its "and"; two products have the picked one on at most one side.
_DET = r"(?:the|a|an|some|my|our|these|those|their)"
_WORD = r"[\w'\u2019-]+"
_AND = r"\s*,?\s*(?:\band\b|&|\+|\bplus\b)\s+(?:also\s+)?"
CONJUNCTION = re.compile(_AND, re.IGNORECASE)
COMMA = re.compile(r"\s*,\s*")  # a list can be commas alone: "photos for lemons, plums"
# after a comma these start a caption or an aside, not a second product: "the Etto rigatoni, in the box", "the lemons, please"
_CAPTION_LEAD = frozenset({"in", "on", "at", "with", "without", "from", "by", "for", "of", "to", "as", "under", "over", "near", "next",
                           "inside", "outside", "behind", "beside", "around", "against", "between", "into", "onto", "about", "like",
                           "just", "only", "also", "too", "instead", "though", "definitely", "obviously", "actually", "sorry", "not",
                           "but", "so", "or", "if", "when", "which", "that's", "thats", "please", "pls", "plz"})
# a reply that opens with one of these is an acknowledgement before the answer: "yes, the lemons"
_REPLY_LEAD = frozenset({"sorry", "hi", "hello", "hey", "sure", "oh", "well", "so", "actually", "just", "right", "great", "good",
                         "cool", "yeah", "yep", "nope", "um", "uh", "hmm", "sorry,", "wait", "oops"})
PLACE = re.compile(r"\b(?:for|of|on|to)\s+", re.IGNORECASE)
SHORT_REPLY = re.compile(rf"(?:[\s,&+]*{_WORD}){{1,8}}[\s.!]*")  # a reply that is only a short phrase: "lemons and plums please"
# a word after "and" that carries on the sentence instead of naming a second product
_NOT_A_PRODUCT = frozenset({"it", "its", "it's", "i", "i'm", "i'll", "we", "they", "this", "that", "there", "then", "now", "please",
                            "thanks", "thank", "thx", "ok", "okay", "yes", "no"})
BOTH = re.compile(r"\b(?:both|each\s+of\s+them|two\s+(?:of\s+them|products|items|things))\b", re.IGNORECASE)
HOME_PAGE = re.compile(r"\bhome\s*-?\s*page\b|\bfront\s+page\b|\bmain\s+(?:picture|photo)\b", re.IGNORECASE)
_SMALL_WORDS = frozenset({"the", "and", "for", "with", "from", "this", "that", "one", "photo", "picture", "pic", "new"})


class Refusal(ValueError):
    """A plan that cannot go on. ``reply`` is the owner's sentence; ``kind`` is "question" when one answer fixes it, else
    "refuse"; ``backlog`` names a backlog reason, or None."""

    def __init__(self, reply, kind="refuse", backlog=None):
        super().__init__(reply)
        self.reply, self.kind, self.backlog = reply, kind, backlog


# -- plain helpers ------------------------------------------------------------------------------------------------------
def _clean(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _content(ctx):
    return getattr(ctx, "content", None)


def _texts(ctx) -> list:
    texts = getattr(ctx, "texts", None)
    if isinstance(texts, (list, tuple)):
        return [t for t in texts if isinstance(t, str)]
    one = getattr(ctx, "owner_text", None)
    return [one] if isinstance(one, str) and one else []


def _product(content, pid):
    return next((p for p in content.products if p.get("id") == pid), None) if content is not None and pid else None


def _q(text) -> str:
    return voice.quote(text)


def _words(text) -> set:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9']+", (text or "").casefold()) if len(w) >= 3 and w not in _SMALL_WORDS}


def _drop_illustration(alt: str) -> str:
    """D1: his photo is a photo, so a caption never carries the catalog's ' (illustration)' label."""
    while alt.casefold().endswith(ILLUSTRATION):
        alt = alt[:-len(ILLUSTRATION)].rstrip()
    return alt


def installed_names(sha) -> tuple:
    """The site paths ``photos.install`` gives this stored photo: a JPEG (always with the house render) or a PNG."""
    return tuple(f"assets/products/photo-{sha[:16]}.{ext}" for ext in ("jpg", "png"))


# -- one photo, one place ---------------------------------------------------------------------------------------------
def _is_list(left, right, name) -> bool:
    """True when the two sides of an 'and' are two products; False when they are one product's name (salt and vinegar chips)."""
    right = re.sub(rf"^{_DET}\s+", "", right.strip().casefold().replace("\u2019", "'"))
    if not right or right.split()[0] in _NOT_A_PRODUCT:
        return False
    want = _words(name)
    left_hit = _words(left) & want
    right_hit = (_words(right) & want) - left_hit
    return not (left_hit and right_hit)


def _first(words) -> str:
    """The first word of a phrase, lower case, without a leading 'the/a/my...'."""
    words = re.sub(rf"^{_DET}\s+", "", words.strip().casefold().replace("\u2019", "'")).split()
    return words[0] if words else ""


def _is_comma_list(left, right, name) -> bool:
    """A bare comma between two names ('lemons, plums') is a list; a comma before a caption or a reply word ('the Etto
    rigatoni, in the box', 'the lemons, please', 'yes, the lemons') is not."""
    lead, nxt = _first(left), _first(right)
    if not lead or lead in _NOT_A_PRODUCT or lead in _REPLY_LEAD or not nxt or nxt in _CAPTION_LEAD or nxt[0].isdigit():
        return False
    return _is_list(left, right, name)


def _lists_two(turn, name) -> bool:
    """True when the text puts two products on the one photo: an 'and' (or &, +, plus) or a bare comma between two names
    after 'for/of/on/to', or a reply that is only such a list. Every 'and' and comma is read on its own, so 'cookies and cream
    chocolate and lemons' lists two while 'the Etto rigatoni, in the box' is one product with a caption."""
    text = turn.strip()
    short = SHORT_REPLY.fullmatch(text) is not None
    for found in sorted([(m, False) for m in CONJUNCTION.finditer(text)] + [(m, True) for m in COMMA.finditer(text)],
                        key=lambda pair: pair[0].start()):
        found, comma = found
        before, after = text[:found.start()], text[found.end():]
        if comma and CONJUNCTION.match(after):  # ', and plums' is the 'and' read above
            continue
        place = None
        for place in PLACE.finditer(before):  # the last 'for/of/on/to' before this 'and' or comma
            pass
        if place is not None:
            left = before[place.end():]
        elif short:
            left = before
        else:
            continue
        left = re.split(r"\s*,\s*|\s*,?\s*(?:\band\b|&|\+|\bplus\b)\s+", left)[-1]  # only the words next to this 'and' or comma
        left = " ".join(re.sub(rf"^{_DET}\s+", "", left.strip(), flags=re.IGNORECASE).split()[-4:])
        right = " ".join(re.split(r"[,.;:!?]|\s" + _AND, after)[0].split()[:3])
        if left and (_is_comma_list if comma else _is_list)(left, right, name):
            return True
    return False


def _crowded(turn, name="") -> str | None:
    """The question one text of his raises about where the photo goes, or None."""
    if HOME_PAGE.search(turn):
        return ONE_PLACE
    if _lists_two(turn, name) or BOTH.search(turn):
        return ONE_AT_A_TIME
    return None


def one_place(texts, name="") -> str | None:
    """The question to ask when his texts put the one photo on two products or on the home page and a product; None when it
    is one place. A later text of his that names the one product (and asks nothing new, so not another list) answers it; the
    earlier text is kept, so a request whose product he never picked still asks."""
    turns = [t for t in texts if isinstance(t, str)]
    asked = [(i, q) for i, t in enumerate(turns) if (q := _crowded(t, name))]
    if not asked:
        return None
    last, question = asked[-1]
    want = _words(name)
    for turn in turns[last + 1:]:
        if want and want & _words(turn):
            return None
    return question


# -- the drafted caption (the dispatcher calls it by name; the plan calls it for a caption still empty) -------------------
def picture_alt(slots, ctx):
    """The caption when he does not say one: the product's saved name. Never the old caption or a file name."""
    product = _product(_content(ctx), _clean(slots.get("item")))
    return _drop_illustration(_clean(product.get("name"))) or None if product else None


def _alt(slots, ctx, sha) -> tuple:
    """(caption, drafted?) or Refusal."""
    alt, drafted = _clean(slots.get("image_alt")), False
    if not alt:
        alt, drafted = _clean(picture_alt(slots, ctx)), True
    alt = _drop_illustration(alt)
    if not alt:
        raise Refusal(ALT_ASK, "question")
    if any(bad in alt for bad in FORBIDDEN_TEXT) or INVISIBLE_RE.search(alt):
        raise Refusal(PLAIN_TEXT_REPLY, "question")
    if len(alt) > MAX_ALT:
        raise Refusal(ALT_LONG, "question")
    if _alt_problem(alt, sha):
        raise Refusal(ALT_ASK, "question")
    return alt, drafted


# -- the plan -----------------------------------------------------------------------------------------------------------
def describe(slots, ctx=None) -> tuple:
    """(ops, [I set phrases]) or Refusal. Reads only: nothing is written."""
    if not isinstance(slots, dict):
        raise Refusal(ASK_ITEM, "question")
    content, pid = _content(ctx), _clean(slots.get("item"))
    product = _product(content, pid)
    name = product.get("name", "") if product else pid
    if (question := one_place(_texts(ctx), name)):  # whatever the model picked, one photo is one product
        raise Refusal(question, "question")
    if not pid:
        raise Refusal(ASK_ITEM, "question")
    if content is None:  # no product list to check the product against: fail closed, never plan without the direct recheck
        raise Refusal(NO_CATALOG)
    if product is None:  # rule hidden-or-held-refused, checked again here whatever the resolver said
        raise Refusal(UNKNOWN, "question")
    if product.get("status") == "held":
        raise Refusal(f"I can't change {_q(product['name'])} right now. It is on hold until someone has looked at it.")
    if product.get("status") != "active":
        raise Refusal(f"{_q(product['name'])} is hidden. Bring it back first, then I can change its picture.")
    sha = slots.get("photo")
    if not (isinstance(sha, str) and media.SHA_RE.fullmatch(sha)):
        raise Refusal(ASK_PHOTO, "question")
    if _can_read(ctx) and _original(ctx, sha) is None:  # not a photo he sent: never trust an id the model made up
        raise Refusal(NO_PHOTO, "question")
    if product is not None and product.get("image") in installed_names(sha):  # rule already-this-photo
        raise Refusal(f"{_q(product['name'])} already has this photo. Nothing changed.")
    alt, drafted = _alt(slots, ctx, sha)
    phrases = [f"the picture caption to \u201c{_q(alt)}\u201d, and you can send a different one if you like"] if drafted else []
    return [{"op": "product.set_photo", "args": {"id": pid, "photo": sha, "imageAlt": alt}}], phrases


def plan_picture(slots, ctx=None) -> list:
    return describe(slots, ctx)[0]


def _can_read(ctx) -> bool:
    return callable(getattr(ctx, "photo_bytes", None)) or bool(getattr(ctx, "media_root", None))


# -- the picture advice (rule house-picture: read-only, never a silent pass) ------------------------------------------------
def review(ctx, sha) -> tuple:
    """(say, warn) about the photo: item.add's own advice for the flag as it is set; a check that cannot run says so."""
    data = _original(ctx, sha)
    if data is None or importlib.util.find_spec("PIL") is None:
        return (), (NOT_CHECKED,)
    return picture_review(data, bool(getattr(ctx, "house_render", False)))


def set_phrases(slots, ctx) -> list:
    """The dispatcher's "I set: ..." line (D8): the caption Hass drafted because he did not say one. Never raises."""
    try:
        return list(describe(dict(slots), ctx)[1])
    except Refusal:
        return []


SET_PHRASES = {"item.picture": set_phrases}


def notes(name, slots, ctx) -> dict:
    """The lines shown beside the draft: the picture advice, the caption Hass set, and that the old picture stays."""
    try:
        ops, phrases = describe(dict(slots), ctx)
    except Refusal:
        return {}
    say, warn = review(ctx, ops[0]["args"]["photo"])
    return {"say": list(say) + [OLD_STAYS], "set": [f"I set: {p}." for p in phrases], "warn": list(warn)}


# -- the skill ----------------------------------------------------------------------------------------------------------
ITEM_PICTURE = Skill(
    name="item.picture", label="change a product's picture", version=1,
    summary="Put the photo he sent on one product, with a caption that says what it shows.",
    triggers=(
        Trigger("new picture for the lemons"),
        Trigger("here's a better one of the Stardust guacamole"),
        Trigger("fixed the pic for the oragnes", "typo"),
        Trigger("this one is better", "vague"),
        Trigger("photos for the lemons and the plums", "multi"),
        Trigger("photo for the Etto rigatoni, in the box"),
        Trigger("new photo for the raw milk cheese"),
        Trigger("retake of the bread, plain counter"),
        Trigger("use this photo for the lemons and the home page", "multi"),
    ),
    slots=(
        Slot("item", "product_ref", required=True, ask=ASK_ITEM),
        Slot("photo", "attachment", required=True, ask=ASK_PHOTO, from_attachment=True),
        Slot("image_alt", "text", required=True, default="derive:picture_alt", ask="What does the photo show?",
             owner_words=True, limit=("product", "imageAlt")),
    ),
    rules=("hidden-or-held-refused", "already-this-photo", "one-photo-one-product", "alt-says-what-it-shows", "house-picture"),
    plan=plan_picture,
    edits=((_PRODUCTS, "products[id].image"), (_PRODUCTS, "products[id].imageAlt"), _PICTURE) + _GEN,
    side_effects=("picture-render",),
    preview="product:the product", approval="owner-yes",
    live_class="private-only",  # product.set_photo is not in the live boundary (hass/live_policy.py); its owner widens that
    undo=Undo("revert", "The old picture and caption come back; the new photo file stays in the site folder, unused. "
                        "The old picture file is never removed."),
    refuse=(
        ("the product is on hold", "I can't change it right now. It is on hold until someone has looked at it."),
        ("the product is hidden", "It is hidden. Bring it back first, then I can change its picture."),
        ("the product already has this photo", "<Product> already has this photo. Nothing changed."),
        ("photos for two products in one message", ONE_AT_A_TIME),
        ("the home page and a product on one photo", ONE_PLACE),
        ("the caption is a file name or placeholder", ALT_ASK),
    ),
    cases="hass/tests/fixtures/skills/item_picture/item.picture.jsonl",
)

SKILLS = (ITEM_PICTURE,)
