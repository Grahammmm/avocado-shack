"""SKILLS-ITEMS-1: hide, restore and edit an item (reports/hass/SKILLS-SPEC.md 3.2, 3.3 and 3.4).

Three skills: ``item.hide``, ``item.restore`` and ``item.edit``. Each is data (SKILLS-FW-1 shape) plus one pure ``plan``
function. Nothing here writes a file, calls the network or the editor: ``plan`` turns validated slots into typed ops
(``product.hide``, ``product.restore``, ``product.edit``) and the editor, claims gate, preview, approval and undo stay
exactly as they are. "Remove" and "delete" mean hide: nothing is ever deleted. There is no price slot (D9).

Interface assumed from the dispatcher (SKILLS-FW-3b; the router, FW-2, and dispatch are not merged yet):

* Slot values arrive already resolved by ``hass.skills.kinds``: a ``product_ref`` is a product id (``items`` is a list
  of ids), a ``maker_ref`` is a maker key, a ``shelf`` is one of ``CATEGORIES``. Asking which product, or which of
  several, is the dispatcher's job and uses ``Slot.ask`` and the resolver replies.
* ``plan(slots, ctx)``: ``ctx.today`` always; ``ctx.content`` (the loaded, read-only ``Content``) in a conversation,
  and ``ctx.site_dir`` when the picture files can be checked. The rules that need the current content run only when
  ``ctx.content`` is there (the plan-golden rows of the test kit carry none); the editor re-checks every one of them.
* A refusal or a question the plan cannot avoid is raised as ``Refusal``: a ``ValueError`` whose ``.reply`` is the
  owner's sentence (the convention the test kit already plays) and whose ``.backlog`` is a backlog reason when the
  caller should also write the request down, else None.
* ``notes(name, slots, ctx)`` gives the extra proposal lines (``say`` / ``set`` / ``warn``) the dispatcher shows
  beside the draft: the hidden-not-deleted line and the owner's reason (hide), the maker-line default (edit) and the
  description advice (edit). The test kit plays this contract (it appends those lines to the proposal it captures), so
  the fixture rows assert them; it is not wired into the live conversation by this card.

Owner wording follows docs/hass/VOICE.md. Authoring guide: docs/hass/SKILLS.md. Skill docs: docs/hass/skills/items.md.
"""
from __future__ import annotations

import re

from hass import voice
from hass.content_model import CATEGORIES, FORBIDDEN_TEXT, INVISIBLE_RE, SHELF_LABELS, TEXT_LIMITS
from hass.interpret_check import PLAIN_TEXT_REPLY, PRICE_REPLY
from hass.skills.model import Skill, Slot, Trigger, Undo

MAX_ITEMS = 6  # spec 3.2 / 3.3: more than six products at once asks with the count
PRICE_SLOTS = frozenset({"price", "prices", "cost", "amount", "pricing"})
CLEAR_CHOICES = ("clearProducer", "clearImageAlt")
UNKNOWN_BRAND, UNKNOWN_SHOWN = "Producer not identified", "From the market"  # the house words for an unknown producer
_NUM = (r"(?:\d+(?:[.,]\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|"
        r"forty|fifty|sixty|seventy|eighty|ninety|hundred)")
PRICE_TEXT = re.compile(
    r"\$|\bper +(?:lb|pound|ounce|oz|dozen|each)\b|\bcents?\b|\bdollars?\b|\d\s?¢"
    + rf"|\b{_NUM}\s+for\s+{_NUM}(?=\s*(?:[.,;:!?)]|$|\s(?:each|a piece|apiece|ea|bucks?|and|or)\b))"  # 'two for five.', '2 for 5.'
    + rf"|\b(?:a|an|{_NUM})\s+bucks?\b"  # 'five bucks each', 'a buck'
    + rf"|\b{_NUM}\s+(?:a|the)\s+(?:pound|lb|dozen|ounce|oz)\b",  # '5 a pound'
    re.IGNORECASE)
FOREVER = re.compile(r"\b(?:for ever|forever|for good|permanent(?:ly)?|erase|wipe)\b", re.IGNORECASE)
DELETE_WORD = re.compile(r"\b(?:delet(?:e|ing)|erase|wipe)\b")
PERMANENT_WORD = re.compile(r"\b(?:for ever|forever|for good|permanent(?:ly)?)\b")
NEGATED_DELETE = re.compile(r"\b(?:do not|does not|never|not|no|without)\b[^.]*\b(?:delet(?:e|ing)|erase|wipe)\b")
HIDE_INSTEAD = re.compile(r"\bjust hide\b|\bhide\b[^.]*\binstead\b|\binstead\b[^.]*\bhide\b")
REJECTS_HIDE = re.compile(r"\b(?:not|rather than|instead of)\s+(?:to\s+)?(?:just\s+)?hid(?:e|ing)\b")
REFERS_BACK = re.compile(r"\b(?:it|them|that|this|those|these|everything|anything|all|one|ones)\b")  # points at what was just asked for
_DELETING = r"(?:delet(?:e|ing)|erase|wipe)"
CLAUSE_SPLIT = re.compile(  # marks, commas, dashes, colons, ' / ', 'but', and an 'and' that starts a new instruction
    r"[.;!?\n,:\u2014\u2013]|\s/\s|\s-+\s|--+|\bbut\b|\band then\b|"
    rf"\band\b(?=\s+(?:(?:do not|does not|never|not|no|without)\b[^.]*\b{_DELETING}\b|just hide\b|{_DELETING}\b))")
INSTRUCTION = re.compile(  # where one delete/hide instruction starts, lead-in words included
    rf"\b(?:(?:and|or|do not|does not|never|not|no|without|just|instead of|instead|rather than)\s+)*\b(?:{_DELETING}|hid(?:e|ing)?)\b")
NOT_A_THING = frozenset(  # clause words that name no product: verbs, negations, fillers and the 'forever' words
    "a an and the my our your please pls actually just instead of to for on in at me us i you do does did not no never without "
    "dont don't yes yeah ok okay now then also still really delete deleting deletes erase erasing wipe wiping hide hiding hid "
    "ever forever good permanent permanently or rather than want need like would should can could will".split())


def _things(clause) -> frozenset:
    """The product words of one clause, plural folded, so a prohibition can be matched to the request it withdraws."""
    words = (w for w in re.findall(r"[a-z0-9']+", clause) if w not in NOT_A_THING and not REFERS_BACK.fullmatch(w))
    return frozenset(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words)


FIELD_WORDS = {"name": "name", "description": "description", "displayBrand": "maker line", "imageAlt": "picture caption"}
SLOT_OF = {"displayBrand": "display_brand", "imageAlt": "image_alt"}  # slot names are lower case; the op arguments keep their camel case

NO_ITEMS_HIDE = "Which product should I hide?"
NO_ITEMS_RESTORE = "Which hidden product should come back?"
NO_ITEM_EDIT = "Which product should I change?"
UNKNOWN_PRODUCT = "I don't know that product. Which one do you mean?"
UNKNOWN_MAKER = "I don't know that maker. Who makes it?"
CANT_DO = "I can't do that yet. Nothing changed."
NOT_DELETED = ("I don't delete anything for good. I can hide it instead: it comes off the website, nothing is lost, "
               "and you can bring it back any time. Tell me to hide it if you'd like that.")
HIDDEN_NOT_DELETED = "It is hidden, not deleted. You can bring it back any time."
REST_OF = " Tell me again without it and I'll do the rest."


class Refusal(ValueError):
    """A plan that cannot go on. ``reply`` is the owner's sentence; ``backlog`` names a backlog reason, or None."""

    def __init__(self, reply, backlog=None):
        super().__init__(reply)
        self.reply, self.backlog = reply, backlog


# -- reading the slots -----------------------------------------------------------------------------------------------
def _content(ctx):
    return getattr(ctx, "content", None)


def _product(content, pid):
    return next((p for p in content.products if p.get("id") == pid), None)


def _quoted(product) -> str:
    return voice.quote(product["name"])


def _only(slots, allowed):
    """A slot the skill does not have is refused: price words get the price reply, anything else 'can't do that yet'."""
    if not isinstance(slots, dict):
        raise Refusal(CANT_DO)
    if PRICE_SLOTS & set(slots):
        raise Refusal(PRICE_REPLY)
    if set(slots) - set(allowed):
        raise Refusal(CANT_DO)


def _items(slots, empty) -> list:
    items = slots.get("items")
    if isinstance(items, str):
        items = [items]
    if not isinstance(items, list) or not items or not all(isinstance(i, str) and i.strip() for i in items):
        raise Refusal(empty)
    return list(dict.fromkeys(i.strip() for i in items))  # a product named twice is one change


def _too_many(ids, what):
    if len(ids) > MAX_ITEMS:
        raise Refusal(f"That is {len(ids)} products at once. Which ones should {what}?")


def _text(slots, key):
    value = slots.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise Refusal(CANT_DO)
    return value.strip()


def _concern(product) -> str:
    """The recorded reason a product is on hold, as one plain sentence (no address, file or id); '' when none is kept."""
    hold = product.get("hold")
    reason = " ".join(str(hold.get("reason") or "").split()) if isinstance(hold, dict) else ""
    reason = INVISIBLE_RE.sub("", reason).strip().rstrip(".;")
    if not reason or any(bad in reason for bad in FORBIDDEN_TEXT) or re.search(r"https?:|www\.|\.(?:com|org|json|jpe?g|webp)\b", reason, re.IGNORECASE):
        return ""
    return reason[:1].upper() + reason[1:200]


def _held(product, many):
    if product.get("status") == "held":
        concern = _concern(product)
        why = f" What was written down: {voice.quote(concern)}." if concern else ""
        raise Refusal(f"I can't change {_quoted(product)} right now. It is on hold until someone has looked at it.{why}"
                      + (REST_OF if many else ""))


# -- item.hide -------------------------------------------------------------------------------------------------------
def rule_whole_shelf(ids):
    """whole-shelf: a shelf of at most six is one change each; more asks with the count."""
    _too_many(ids, "I hide")


def owner_asks_permanent_delete(texts, content=None) -> bool:
    """True when this request's owner texts, oldest first, end on an explicit permanent-deletion instruction: a deletion word
    and a 'forever' word in one clause. A negated one, or a later 'just hide it instead', withdraws it, but only the
    instruction it is about: 'delete the cashews forever, never delete the plums' still asks for the cashews."""
    names = [n.casefold() for p in getattr(content, "products", None) or [] if isinstance(n := p.get("name"), str)
             and PERMANENT_WORD.search(n.casefold())]
    asked = []  # the product words of each standing deletion instruction (empty: it only said 'it' or 'them')
    for text in texts or ():
        if not isinstance(text, str):
            continue
        text = text.casefold().replace("\u2019", "'").replace("n't", " not")
        for name in names:
            text = text.replace(name, " ")
        for clause in CLAUSE_SPLIT.split(" ".join(text.split())):
            for part in _instructions(clause):
                kind = _kind(part)
                if kind == "ask":  # "..., not just hide it" rejects hiding; it never withdraws a deletion request
                    asked.append(_things(part))
                elif kind == "withdraw":
                    things = _things(part)
                    if not things:
                        asked = []  # 'don't', 'just hide it instead', 'never delete them': names no product, so it is about the request just made
                    else:  # it names products: it withdraws only the instructions about those products
                        kept = [a if not a else a - things for a in asked]  # 'it' requests stay; the rest lose only the products named
                        asked = [a for a, was in zip(kept, asked) if a or not was]
    return bool(asked)


def _kind(part):
    """'ask' (a permanent-deletion instruction, even one that also rejects hiding), 'withdraw' (a negated delete or a hide
    instead) or None for a fragment that is neither."""
    wants = bool(DELETE_WORD.search(part) and PERMANENT_WORD.search(part))
    if REJECTS_HIDE.search(part):
        return "ask" if wants else None
    if NEGATED_DELETE.search(part) or HIDE_INSTEAD.search(part):
        return "withdraw"
    return "ask" if wants else None


def _instructions(clause) -> list:
    """One clause as its separate instructions, cut where a delete/hide verb (with its 'never', 'without', 'just', 'instead',
    'and', 'or' lead-in) starts, so a request and an unrelated prohibition in one run-on sentence are judged apart. A fragment
    that is neither a request nor a withdrawal stays with the instruction before it ('delete the cashews and hide the plums forever')."""
    cuts = sorted({0, *(m.start() for m in INSTRUCTION.finditer(clause))})
    parts = []
    for a, b in zip(cuts, cuts[1:] + [len(clause)]):
        if parts and _kind(clause[a:b]) is None:
            parts[-1] += " " + clause[a:b]
        else:
            parts.append(clause[a:b])
    return parts



def rule_no_permanent_delete(slots, ctx=None):
    """no-permanent-delete: 'delete it for good' is answered with the hide explanation and a backlog row."""
    reason = slots.get("reason")
    if isinstance(reason, str) and FOREVER.search(reason):
        raise Refusal(NOT_DELETED, backlog="policy")
    if owner_asks_permanent_delete(getattr(ctx, "texts", None), _content(ctx)):
        raise Refusal(NOT_DELETED, backlog="policy")


def rule_held_refused(content, ids):
    """held-refused: a held product is never changed; it needs a look at the recorded concern first."""
    for pid in ids:
        if (product := _product(content, pid)) is not None:
            _held(product, len(ids) > 1)


def rule_already_hidden(content, ids):
    """already-hidden: say so and draft nothing for it."""
    for pid in ids:
        product = _product(content, pid)
        if product is None:
            raise Refusal(UNKNOWN_PRODUCT)
        if product.get("status") != "active":
            raise Refusal(f"I already have {_quoted(product)} hidden. Nothing changed." if len(ids) == 1
                          else f"I already have {_quoted(product)} hidden." + REST_OF)


def plan_hide(slots, ctx) -> list:
    _only(slots, ("items", "reason"))
    rule_no_permanent_delete(slots, ctx)
    ids = _items(slots, NO_ITEMS_HIDE)
    rule_whole_shelf(ids)
    if (content := _content(ctx)) is not None:
        rule_held_refused(content, ids)
        rule_already_hidden(content, ids)
    return [{"op": "product.hide", "args": {"id": pid}} for pid in ids]


# -- item.restore ----------------------------------------------------------------------------------------------------
def rule_not_hidden(content, ids):
    """not-hidden: a product that is already on the site needs no change."""
    for pid in ids:
        product = _product(content, pid)
        if product is None:
            raise Refusal(UNKNOWN_PRODUCT)
        if product.get("status") == "active":
            raise Refusal(f"I already have {_quoted(product)} on the website. Nothing changed." if len(ids) == 1
                          else f"I already have {_quoted(product)} on the website." + REST_OF)


def rule_maker_hidden(content, ids):
    """maker-hidden: a product cannot come back while its maker is hidden."""
    for pid in ids:
        product = _product(content, pid)
        if product is None:
            raise Refusal(UNKNOWN_PRODUCT)
        maker = content.makers.get(product.get("producerKey") or "", {})
        if maker.get("hidden") is True:
            who = voice.quote(maker.get("name") or "its maker")
            tail = (f"Bring {who} back first, then I can bring this one back." if len(ids) == 1
                    else f"Bring {who} back first." + REST_OF)
            raise Refusal(f"I can't bring {_quoted(product)} back while its maker, {who}, is hidden. " + tail)


def rule_image_missing(ctx, content, ids):
    """image-missing: the picture file must still be there (the editor's own check; runs when ctx.site_dir is given)."""
    site_dir = getattr(ctx, "site_dir", None)
    if site_dir is None:
        return
    from hass.ops import _image_file_problem
    for pid in ids:
        product = _product(content, pid)
        if product is None:
            raise Refusal(UNKNOWN_PRODUCT)
        image = product.get("image")
        if not isinstance(image, str) or _image_file_problem(site_dir, image):
            raise Refusal(f"I can't bring {_quoted(product)} back because its picture is missing. "
                          "Nothing changed. Its picture has to be put back by hand first.")


def plan_restore(slots, ctx) -> list:
    _only(slots, ("items",))
    ids = _items(slots, NO_ITEMS_RESTORE)
    _too_many(ids, "come back")
    if (content := _content(ctx)) is not None:
        rule_held_refused(content, ids)
        rule_not_hidden(content, ids)
        rule_maker_hidden(content, ids)
        rule_image_missing(ctx, content, ids)
    return [{"op": "product.restore", "args": {"id": pid}} for pid in ids]


# -- item.edit -------------------------------------------------------------------------------------------------------
def _spaced(value):
    return " ".join(value.split()) if isinstance(value, str) else value


def _fold(value) -> str:
    return _spaced(value).casefold()


def rule_no_price(texts):
    """no-price: a price, per-pound or amount in any text refuses; the website shows no prices."""
    for text in texts:
        if PRICE_TEXT.search(text):
            raise Refusal(PRICE_REPLY)


def _check_text(field, text):
    if any(bad in text for bad in FORBIDDEN_TEXT if bad != "$") or INVISIBLE_RE.search(text):
        raise Refusal(PLAIN_TEXT_REPLY)
    limit = TEXT_LIMITS["product"][field]
    if len(text) > limit:
        raise Refusal(f"That {FIELD_WORDS[field]} is too long. The most I can fit is {limit} characters. Could you shorten it?")


def rule_twin(content, product, changes):
    """twin: a rename (or new maker) may not give two products the same name and maker."""
    if "name" not in changes and "brand" not in changes:
        return
    name, brand = changes.get("name", product["name"]), changes.get("brand", product["brand"])
    twin = next((p for p in content.products if p["id"] != product["id"] and _fold(p["name"]) == _fold(name)
                 and _fold(p["brand"]) == _fold(brand)), None)
    if twin is not None:
        raise Refusal(f"There is already a product called {voice.quote(twin['name'])} from {voice.quote(twin['brand'])}. "
                      "Do you want to change that one instead?")


def rule_not_already_true(content, product, args):
    """not-already-true: a field that already has the asked value is dropped; nothing left to change says so."""
    keep = {}
    for key, value in args.items():
        if key == "id":
            continue
        if key == "clearImageAlt":
            if "imageAlt" in product:
                keep[key] = value
        elif key == "clearProducer":
            if product.get("producerKey") is not None:
                keep[key] = value
        elif _spaced(product.get(key)) != _spaced(value):
            keep[key] = value
    if not keep:
        raise Refusal(f"It already says that on {_quoted(product)}. Nothing changed.")
    return {"id": args["id"], **keep}


def _edit_args(slots, content):
    item = slots.get("item")
    if not isinstance(item, str) or not item.strip():
        raise Refusal(NO_ITEM_EDIT)
    texts = {k: _text(slots, SLOT_OF.get(k, k)) for k in FIELD_WORDS}
    rule_no_price([t for t in texts.values() if t])
    for field, text in texts.items():
        if text:
            _check_text(field, text)
    clear = slots.get("clear") or []
    if not isinstance(clear, list) or any(c not in CLEAR_CHOICES for c in clear):
        raise Refusal(CANT_DO)
    category, maker = slots.get("category"), slots.get("maker")
    if category is not None and category not in CATEGORIES:
        shelves = [SHELF_LABELS[c] for c in CATEGORIES]
        raise Refusal(f"Which shelf should it go on: {', '.join(shelves[:-1])} or {shelves[-1]}?")
    if maker is not None and not (isinstance(maker, str) and maker.strip()):
        raise Refusal(UNKNOWN_MAKER)
    if maker and "clearProducer" in clear:
        raise Refusal("You asked me to change the maker and to take it off. Which one do you want?")
    if texts["imageAlt"] and "clearImageAlt" in clear:
        raise Refusal("You asked me to change the picture caption and to take it off. Which one do you want?")
    args: dict = {"id": item.strip()}
    for field in ("name", "description"):
        if texts[field]:
            args[field] = texts[field]
    if category:
        args["category"] = category
    if maker:
        makers = content.makers if content is not None else {}
        if content is not None:
            record = makers.get(maker)
            if record is None:
                raise Refusal(UNKNOWN_MAKER)
            if record.get("hidden") is True:
                raise Refusal(f"{voice.quote(record['name'])} is hidden. Bring them back first, then I can use them.")
        name = makers.get(maker, {}).get("name", maker)  # every maker's key is its name; used when no content is given
        args.update(brand=name, producerKey=maker, displayBrand=texts["displayBrand"] or name)
    elif "clearProducer" in clear:
        args.update(clearProducer=True, brand=UNKNOWN_BRAND, displayBrand=texts["displayBrand"] or UNKNOWN_SHOWN)
    elif texts["displayBrand"]:
        args["displayBrand"] = texts["displayBrand"]
    if texts["imageAlt"]:
        args["imageAlt"] = texts["imageAlt"]
    elif "clearImageAlt" in clear:
        args["clearImageAlt"] = True
    return args


def plan_edit(slots, ctx) -> list:
    _only(slots, ("item", "name", "description", "category", "maker", "display_brand", "image_alt", "clear"))
    content = _content(ctx)
    args = _edit_args(slots, content)
    if len(args) == 1:  # only the id: nothing to change
        product = _product(content, args["id"]) if content is not None else None
        raise Refusal(f"What should change on {_quoted(product)}?" if product else "What should change on that product?")
    if content is not None:
        product = _product(content, args["id"])
        if product is None:
            raise Refusal(UNKNOWN_PRODUCT)
        _held(product, False)
        if product.get("status") != "active":
            raise Refusal(f"I have {_quoted(product)} hidden. Bring it back first, then I can change it.")
        args = rule_not_already_true(content, product, args)
        rule_twin(content, product, args)
    return [{"op": "product.edit", "args": args}]


# -- the extra proposal lines ------------------------------------------------------------------------------------------
HOUSE_MIN, HOUSE_MAX = 59, 167  # measured on the 170 live descriptions (reports/hass/SKILLS-SPEC.md 1.5)


def advisory(text) -> list:
    """Plain-words warnings about a new description against the site's own voice. Advice only; never a block."""
    out = []
    if len(text) > HOUSE_MAX:
        out.append("This is longer than the other descriptions on the website. You can keep it, or make it shorter.")
    elif len(text) < HOUSE_MIN:
        out.append("This is shorter than the other descriptions on the website. You can keep it, or add a line.")
    if not text.rstrip().endswith("."):
        out.append("The other descriptions end with a full stop.")
    if "!" in text or "?" in text:
        out.append("The other descriptions don't use exclamation or question marks.")
    return out


def notes(name, slots, ctx) -> dict:
    """The lines shown beside the draft: ``say`` (a fact to state), ``set`` (an 'I set:' line) and ``warn`` (advice)."""
    out = {"say": [], "set": [], "warn": []}
    if name == "item.hide":
        out["say"].append(HIDDEN_NOT_DELETED)
        if (reason := _text(slots, "reason")):  # listed in the reply only; it is never written to the product
            out["say"].append(f"You told me why: {voice.quote(' '.join(reason.split())[:120])}. I haven't saved that on the product.")
    elif name == "item.edit":
        try:  # notes follow the plan the owner will be asked about: what the plan dropped as unchanged is not mentioned
            [op] = plan_edit(slots, ctx)
        except Refusal:
            return out  # no draft is proposed, so there is nothing to say beside it
        args = op["args"]
        if "displayBrand" in args and not _text(slots, "display_brand"):  # a default, not the owner's own label
            # the default's source is the owner's original request: rule_not_already_true drops clearProducer from a product
            # that has no maker link, yet the fallback line can still replace a custom label
            if "clearProducer" in (slots.get("clear") or []):
                out["set"].append(f"I set: the maker line on the card to {args['displayBrand']}.")
            elif slots.get("maker"):
                out["set"].append(f"I set: the maker line on the card to {voice.quote(args['displayBrand'])}.")
        if "description" in args:
            out["warn"] += advisory(args["description"])
    return out


# -- the three skills ------------------------------------------------------------------------------------------------
_CASES = "hass/tests/fixtures/skills/items/{}.jsonl"
_STATUS = ("hass/content/products.json", "products[id].status")
_GENERATED = (("storefront-mockup/catalog-products.js", "generated"),)

ITEM_HIDE = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='full', logs=('subjects', 'fields'), who='owner',
    name="item.hide", label="hide a product",
    summary="Take one or more products off the website. Nothing is deleted; they can come back.",
    triggers=(
        Trigger("hide the plums"),
        Trigger("take the cashews off the site"),
        Trigger("remvoe the strawbery jam", "typo"),
        Trigger("hide the figs, the cashews and the guacamole", "multi"),
        Trigger("get rid of the old stuff", "vague"),
        Trigger("we dont carry Etto anymore"),
        Trigger("delete the guacamole"),
        Trigger("pull all the bread", "multi"),
        Trigger("stop selling the lemons"),
        Trigger("delete everything"),
    ),
    slots=(Slot("items", "product_ref", True, ask=NO_ITEMS_HIDE),
           Slot("reason", "text", False)),
    rules=("held-refused", "already-hidden", "whole-shelf", "no-permanent-delete"),
    plan=plan_hide, edits=(_STATUS, *_GENERATED), side_effects=("none",), preview="product:the first product",
    approval="owner-yes", live_class="chat-live", undo=Undo("revert", "none"),
    refuse=(("the product is on hold", "I can't change it right now. It is on hold until someone has looked at it."),
            ("the product is already hidden", "I already have it hidden. Nothing changed."),
            ("more than six products", "That is too many at once. Which ones should I hide?"),
            ("the owner asks to delete it for good", NOT_DELETED)),
    cases=_CASES.format("item.hide"), version=1)

ITEM_RESTORE = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='full', logs=('subjects', 'fields'), who='owner',
    name="item.restore", label="bring a hidden product back",
    summary="Put one or more hidden products back on the website.",
    triggers=(
        Trigger("bring back the lemons"),
        Trigger("put the cashews back"),
        Trigger("resotre the figs", "typo"),
        Trigger("lemons and guacamole are back on", "multi"),
        Trigger("undo what I hid yesterday", "vague"),
        Trigger("make the cashews visible again"),
        Trigger("un-hide the garlic pesto"),
        Trigger("bring back the raw milk cheese"),
        Trigger("put it back", "vague"),
        Trigger("restore everything I hid", "multi"),
    ),
    slots=(Slot("items", "product_ref", True, ask=NO_ITEMS_RESTORE),),
    rules=("not-hidden", "held-refused", "maker-hidden", "image-missing"),
    plan=plan_restore, edits=(_STATUS, *_GENERATED), side_effects=("none",), preview="product:the first product",
    approval="owner-yes", live_class="chat-live", undo=Undo("revert", "none"),
    refuse=(("the product is already on the website", "I already have it on the website. Nothing changed."),
            ("the product is on hold", "I can't change it right now. It is on hold until someone has looked at it."),
            ("the maker is hidden", "Its maker is hidden. Bring the maker back first."),
            ("the picture file is missing", "I can't bring it back because its picture is missing. Nothing changed. Its picture has to be put back by hand first.")),
    cases=_CASES.format("item.restore"), version=1)

ITEM_EDIT = Skill(
    pack='site', targets=('site',), approval_class='A1', sandbox='preview', logs=('subjects', 'fields'), who='owner',
    name="item.edit", label="change a product",
    summary="Change a product's name, description, maker or shelf. Prices are not kept on the website.",
    triggers=(
        Trigger("rename the Hass avocado to Hass avocados"),
        Trigger("chnage the pesto desription to say its great on toast", "typo"),
        Trigger("move the garlic pesto to the dairy shelf"),
        Trigger("rename the oranges to Navel oranges and add a line to the lemons description: try a squeeze over roasted vegetables", "multi"),
        Trigger("the guacamole text is boring", "vague"),
        Trigger("the figs are by Fair Hills Farm now, not Producer not identified"),
        Trigger("make the eggs $6.50"),
        Trigger("the lemons description: 3 for $5, best deal"),
        Trigger("add a line to the guacamole description: pairs well with chips"),
        Trigger("fix the picture caption on the lemons", "vague"),
    ),
    slots=(Slot("item", "product_ref", True, ask=NO_ITEM_EDIT),
           Slot("name", "text", False, limit=("product", "name")),
           Slot("description", "text", False, owner_words=True, limit=("product", "description")),
           Slot("category", "shelf", False),
           Slot("maker", "maker_ref", False),
           Slot("display_brand", "text", False, owner_words=True, limit=("product", "displayBrand")),
           Slot("image_alt", "text", False, owner_words=True, limit=("product", "imageAlt")),
           Slot("clear", "text_list", False)),
    rules=("not-already-true", "twin", "no-price", "held-refused"),
    plan=plan_edit,
    edits=(("hass/content/products.json", "products[id].name"), ("hass/content/products.json", "products[id].description"),
           ("hass/content/products.json", "products[id].category"), ("hass/content/products.json", "products[id].brand"),
           ("hass/content/products.json", "products[id].producerKey"),
           ("hass/content/products.json", "products[id].displayBrand"),
           ("hass/content/products.json", "products[id].imageAlt"), *_GENERATED),
    side_effects=("none",), preview="product:the product", approval="owner-yes",
    live_class="private-only",  # a maker, brand or maker line change is a protected field; description and shelf alone are chat-live; a name is private
    undo=Undo("revert", "none"),
    refuse=(("a price is in the message", PRICE_REPLY),
            ("nothing is asked to change", "What should change on that product?"),
            ("the product already says it", "It already says that. Nothing changed."),
            ("another product has the new name and maker", "There is already a product with that name and maker. Nothing changed."),
            ("the product is hidden or on hold", "I can't change it right now.")),
    cases=_CASES.format("item.edit"), version=1)

SKILLS = (ITEM_HIDE, ITEM_RESTORE, ITEM_EDIT)

# Rule id -> the function (or functions) that enforce it; tests/test_skills_items.py pins every id to a row.
RULE_FUNCTIONS = {
    "held-refused": rule_held_refused, "already-hidden": rule_already_hidden, "whole-shelf": rule_whole_shelf,
    "no-permanent-delete": rule_no_permanent_delete, "not-hidden": rule_not_hidden, "maker-hidden": rule_maker_hidden,
    "image-missing": rule_image_missing, "not-already-true": rule_not_already_true, "twin": rule_twin,
    "no-price": rule_no_price,
}
