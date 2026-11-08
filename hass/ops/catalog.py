"""Hass product and maker ops (H03): add, edit, hide, restore, plus a read-only name lookup.

"Remove" means hide: no record is ever deleted. Held products are refused by every op (no op changes ``held`` or
``hold``). Ops take only exact ids/keys; resolving a name is always ``lookup`` first. Facts come from arguments only.
Add and rename refuse a name+brand (product) or name (maker) another record has, case and spacing ignored, naming it.
Edits drop fields that already have the asked value (exact equality, inner spacing ignored); an edit left with nothing
is refused, naming them.
A maker ``place`` edit warns with the number of active product cards whose "Based in" line (and town search) it relabels.
"""

from __future__ import annotations

import copy
import re
import unicodedata

from hass import voice
from hass.content_model import AVAILABILITY, CATEGORIES, TEXT_LIMITS, checked_on, shop_today
from hass.field_words import field_list
from hass.ops import Arg, NeedsDetails, NotFound, Op, Refused, Touched, _image_file_problem

PRODUCT_ID_RE = re.compile(r"photo-product-(\d+)")
# storefront-mockup/shop.js organic(): name matches /\borganic\b/i or the maker is one of these.
ORGANIC_NAME_RE = re.compile(r"\borganic\b", re.IGNORECASE | re.ASCII)
ORGANIC_MAKERS = ("Ocean Ranch", "Straus", "Green Gold", "Massa Organics")
PRODUCT_EDITABLE = ("name", "brand", "category", "image", "description", "displayBrand", "imageAlt")
MAKER_EDITABLE = ("name", "place", "story", "url")
MAX_KEY, MAX_CANDIDATES = 64, 10
PRODUCT_LIMITED = ("name", "brand", "displayBrand", "description")  # imageAlt: RF1510-13 (photos.install)
MAKER_LIMITED = ("name", "place", "story")


def _too_long(args, kind, fields):
    """Refused naming the first of fields whose string is over its TEXT_LIMITS limit (the value is never echoed)."""
    limits = TEXT_LIMITS[kind]
    return next((Refused(f"{f} is longer than {limits[f]} characters") for f in fields
                 if isinstance(args.get(f), str) and len(args[f]) > limits[f]), None)


def _organic(product) -> bool:
    return bool(ORGANIC_NAME_RE.search(product["name"])) or product.get("producerKey") in ORGANIC_MAKERS


def _product(content, pid):
    """The product dict, or NotFound / Refused (held products are blocked for every op)."""
    product = next((p for p in content.products if p["id"] == pid), None)
    if product is None:
        return NotFound(pid)
    if product.get("status") == "held":
        hold = product.get("hold") or {}
        return Refused(f"held: {hold.get('reason')} (source {hold.get('source')}); "
                       "needs review of the recorded concern")
    return product


def _maker_problem(content, key):
    """Refused when a product may not point at this maker (hidden makers cannot be referenced)."""
    if key is not None and content.makers.get(key, {}).get("hidden") is True:
        return Refused(f"maker {key} is hidden; restore the maker first")
    return None


def _maker(content, key):
    return content.makers[key] if key in content.makers else NotFound(key)


def _same(a, b) -> bool:  # NFKC look-alikes count as the same, as routes._fold does
    fold = lambda x: " ".join(unicodedata.normalize("NFKC", str(x)).split()).casefold()
    return fold(a) == fold(b)


def _spaced(value):
    return " ".join(value.split()) if isinstance(value, str) else value


def _twin(content, name, brand, pid=None):
    """The first product other than ``pid`` with this name and brand (any status), else None."""
    return next((p for p in content.products if p["id"] != pid and _same(p["name"], name) and _same(p["brand"], brand)),
                None)


def _maker_twin(content, name, key=None):
    return next((k for k, m in content.makers.items() if k != key and _same(m.get("name", ""), name)), None)


def _key_fold(key) -> str:
    """Maker key compared ignoring case, spacing and look-alike Unicode forms (NFKC)."""
    return " ".join(unicodedata.normalize("NFKC", key).split()).casefold()


def _shown(value) -> str:
    text = "none" if value is None else str(value)
    return text if len(text) <= 40 else text[:40] + "…"


def _drop_unchanged(changes, record, label, more=False):
    """Keys whose value differs from the record's (exact equality, inner spacing ignored); Refused when all were
    unchanged and not ``more``."""
    left = {k: v for k, v in changes.items() if _spaced(record.get(k)) != _spaced(v)}
    if changes and not left and not more:
        return Refused(f"{label} already has " + ", ".join(f"{k}={_shown(v)}" for k, v in changes.items())
                       + "; nothing to change")
    return left


def _touch(collection, key, before, after):
    return [Touched(collection, key, before, copy.deepcopy(after))]


def _product_add(content, args, ctx):
    if problem := _too_long(args, "product", PRODUCT_LIMITED):
        return problem
    if twin := _twin(content, args["name"], args["brand"]):
        tail = {"active": "already has this name and brand; edit it instead",
                "hidden": "has this name and brand and is hidden; restore it instead"}.get(
            twin.get("status"), "has this name and brand and is held; it needs review of the recorded concern")
        return Refused(f"{twin['id']} {tail}")
    key = args.get("producerKey")
    if refused := _maker_problem(content, key):
        return refused
    if "image" in args and "photo" in args:
        return Refused("give image or photo, not both")
    if "image" not in args and "photo" not in args:
        return Refused("Send the photo with the product name as its caption.")
    if "photo" in args and "imageAlt" not in args:
        return Refused("imageAlt is required with photo")
    image = args.get("image")
    if "photo" in args:
        from hass.ops import photos  # lazy: photos imports this module
        if isinstance(image := photos.install(ctx, args["photo"], args["imageAlt"]), Refused):
            return image
    numbers = [int(m.group(1)) for p in content.products if (m := PRODUCT_ID_RE.fullmatch(p["id"]))]
    record = {"id": "photo-product-%03d" % (max(numbers, default=0) + 1)}
    for field in ("name", "brand", "category", "image", "description"):
        record[field] = image if field == "image" else args[field]
    shown = args["displayBrand"] if "displayBrand" in args else (
        "From the market" if args["brand"] == "Producer not identified" else args["brand"])  # absence alone defaults
    record.update(producerKey=key, displayBrand=shown, status="active")
    record.update({"imageAlt": args["imageAlt"]} if "imageAlt" in args else {})  # optional; kept after status
    record["addedOn"] = shop_today(ctx.now).isoformat()  # AV1622-06: Pacific day of this add; no other op sets it
    content.products.append(record)
    if _organic(record):
        ctx.warnings.append(f"adds Organic badge to {record['id']}")
    return _touch("products", record["id"], None, record)


def _product_edit(content, args, ctx):
    product = _product(content, args["id"])
    if not isinstance(product, dict):
        return product
    if problem := _too_long(args, "product", PRODUCT_LIMITED):
        return problem
    changes = {field: args[field] for field in PRODUCT_EDITABLE if field in args}
    if "producerKey" in args and args.get("clearProducer"):
        return Refused("producerKey and clearProducer cannot be combined")
    if "imageAlt" in args and args.get("clearImageAlt"):
        return Refused("imageAlt and clearImageAlt cannot be combined")
    if "producerKey" in args:
        changes["producerKey"] = args["producerKey"]
    elif args.get("clearProducer"):
        changes["producerKey"] = None
    clear_alt = bool(args.get("clearImageAlt")) and "imageAlt" in product  # clearing an absent alt is no change
    if not changes and not clear_alt:
        fields = list(PRODUCT_EDITABLE) + ["producerKey", "clearProducer", "clearImageAlt"]
        return NeedsDetails(fields, f"What would you like to change about {voice.quote(product['name'])}?")
    changes = _drop_unchanged(changes, product, args["id"], more=clear_alt)
    if isinstance(changes, Refused):
        return changes
    if refused := _maker_problem(content, changes.get("producerKey")):
        return refused
    if ("name" in changes or "brand" in changes) and (twin := _twin(
            content, changes.get("name", product["name"]), changes.get("brand", product["brand"]), product["id"])):
        return Refused(f"{twin['id']} already has this name and brand")
    before = copy.deepcopy(product)
    product.update(changes)
    if clear_alt:
        del product["imageAlt"]
    if _organic(product) and not _organic(before):
        ctx.warnings.append(f"adds Organic badge to {product['id']}")
    elif _organic(before) and not _organic(product):
        ctx.warnings.append(f"removes Organic badge from {product['id']}")
    return _touch("products", product["id"], before, product)


def _restore_image_problem(ctx, pid, image):
    """Making a product active again checks its image like setting one (shared _image_file_problem rule)."""
    problem = _image_file_problem(ctx.site_dir, image) if isinstance(image, str) else "image file does not exist"
    if problem == "image file does not exist":
        return Refused(f"{pid} cannot be restored: image file {image} is missing")
    return Refused(f"{pid} cannot be restored: {problem}") if problem else None


def _set_status(content, args, ctx, *, expect, new, state_error):
    product = _product(content, args["id"])
    if not isinstance(product, dict):
        return product
    if product["status"] != expect:
        return Refused(f"{product['id']} {state_error(product['status'])}")
    if new == "active":
        if refused := _maker_problem(content, product.get("producerKey")):
            return refused
        if refused := _restore_image_problem(ctx, product["id"], product.get("image")):
            return refused
    before = copy.deepcopy(product)
    product["status"] = new
    return _touch("products", product["id"], before, product)


def _product_hide(content, args, ctx):
    return _set_status(content, args, ctx, expect="active", new="hidden", state_error=lambda s: f"is already {s}")


def _product_restore(content, args, ctx):
    return _set_status(content, args, ctx, expect="hidden", new="active", state_error=lambda s: f"is {s}, not hidden")


NOT_CHECKED_TODAY = "the selection was not checked today; check the selection first"  # HASS-SHELFCHECK-FLOW-1: Conversation asks the owner instead


def _product_set_availability(content, args, ctx):
    """SHOP-1: mark one active product yes|limited|no. Shown on its card only while the selection check is recent."""
    product = _product(content, args["id"])
    if not isinstance(product, dict):
        return product
    if product["status"] != "active":
        return Refused(f"{product['id']} is {product['status']}; restore it before marking it available")
    day = checked_on(content.store)
    if (product.get("available") == args["available"]
            and product.get("available_on") == shop_today(ctx.now).isoformat()):  # HASS-SHELFCHECK-FLOW-1: a stale same word is a re-check
        return Refused(f"{product['id']} is already marked available={args['available']}; nothing to change")
    if day != shop_today(ctx.now):  # AV1102-01: only onto today's shelf check
        return Refused(NOT_CHECKED_TODAY)
    before = copy.deepcopy(product)
    product["available"] = args["available"]
    product["available_on"] = day.isoformat()
    return _touch("products", product["id"], before, product)


def _product_clear_availability(content, args, ctx):
    """AV1622-05: take one product's availability word and its own check day off its card (never sets 'no')."""
    product = _product(content, args["id"])
    if not isinstance(product, dict):
        return product
    if product["status"] != "active":
        return Refused(f"{product['id']} is {product['status']}; restore it before clearing its availability")
    if "available" not in product:
        return Refused(f"{product['id']} has no availability word set; nothing to clear")
    before = copy.deepcopy(product)
    product.pop("available")
    product.pop("available_on", None)
    return _touch("products", product["id"], before, product)


def _maker_add(content, args, ctx):
    key = args["key"]
    if len(key) > MAX_KEY:
        return Refused(f"maker key is longer than {MAX_KEY} characters")
    if problem := _too_long(args, "maker", MAKER_LIMITED):
        return problem
    if (same := next((k for k in content.makers if _key_fold(k) == _key_fold(key)), None)) is not None:
        hidden = content.makers[same].get("hidden") is True
        return Refused(f"maker {same} already exists" + ("; restore it instead" if hidden else ""))
    if twin := _maker_twin(content, args["name"]):
        verb = "restore" if content.makers[twin].get("hidden") is True else "edit"
        return Refused(f"maker {twin} already has this name; {verb} it instead")
    content.makers[key] = {field: args[field] for field in MAKER_EDITABLE if field in args}  # url may be absent
    return _touch("makers", key, None, content.makers[key])


def _maker_edit(content, args, ctx):
    maker = _maker(content, args["key"])
    if not isinstance(maker, dict):
        return maker
    if problem := _too_long(args, "maker", MAKER_LIMITED):
        return problem
    if "url" in args and args.get("clearUrl"):
        return Refused("url and clearUrl cannot be combined")
    changes = {field: args[field] for field in MAKER_EDITABLE if field in args}
    clear_url = bool(args.get("clearUrl"))
    if not changes and not clear_url:
        fields = list(MAKER_EDITABLE) + ["clearUrl"]
        return NeedsDetails(fields, f"What should change on maker {args['key']}? Give at least one of: "
                            + field_list(fields))
    clear_url = clear_url and "url" in maker  # clearing an absent url is no change
    changes = _drop_unchanged(changes, maker, f"maker {args['key']}", more=clear_url) if changes else changes
    if not changes and not clear_url:
        return Refused(f"maker {args['key']} has no url set; nothing to clear")
    if isinstance(changes, Refused):
        return changes
    if "name" in changes and (twin := _maker_twin(content, changes["name"], args["key"])):
        return Refused(f"maker {twin} already has this name")
    if "place" in changes:  # only active products are on the shop; hidden and held ones are not counted
        n = sum(1 for p in content.active_products() if p.get("producerKey") == args["key"])
        ctx.warnings.append(f"changes the \"Based in\" line on {n} active product card{'s' if n != 1 else ''} of maker "
                            f"{args['key']} (town search follows it)" if n else
                            f"maker {args['key']} has no active products; no product card changes")
    before = copy.deepcopy(maker)
    maker.update(changes)
    if clear_url:
        maker.pop("url")
    return _touch("makers", args["key"], before, maker)


def _maker_hide(content, args, ctx):
    """Hide a maker; ``withProducts`` also hides its active products in the same change (maker first, then by id)."""
    maker = _maker(content, args["key"])
    if not isinstance(maker, dict):
        return maker
    if maker.get("hidden") is True:
        return Refused(f"maker {args['key']} is already hidden")
    active = sorted((p for p in content.active_products() if p.get("producerKey") == args["key"]),
                    key=lambda p: p["id"])
    if active and args.get("withProducts") is not True:
        return Refused(f"maker {args['key']} still has active products: " + ", ".join(p["id"] for p in active))
    before = copy.deepcopy(maker)
    maker["hidden"] = True
    touched = _touch("makers", args["key"], before, maker)
    for product in active:
        was = copy.deepcopy(product)
        product["status"] = "hidden"
        touched += _touch("products", product["id"], was, product)
    return touched


def _maker_restore(content, args, ctx):
    maker = _maker(content, args["key"])
    if not isinstance(maker, dict):
        return maker
    if maker.get("hidden") is not True:
        return Refused(f"maker {args['key']} is visible, not hidden")
    before = copy.deepcopy(maker)
    del maker["hidden"]
    return _touch("makers", args["key"], before, maker)


_FOLD_PUNCT = str.maketrans({**{c: "'" for c in "\u2018\u2019\u02bc\u0060\u00b4"}, "\u201c": '"', "\u201d": '"',
                             **{chr(c): "-" for c in range(0x2010, 0x2016)}})


def _fold(text) -> str:
    """Lookup form: accents removed, typographic punctuation made ASCII, apostrophes dropped, spaces collapsed, casefolded."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    return " ".join(plain.translate(_FOLD_PUNCT).replace("'", "").split()).casefold()


def lookup(content, kind, query, aliases=None):
    """Read-only name lookup: {"match": id} for one hit, {"candidates": [...]} (<=10, by id) otherwise.
    H15 aliases {name: (kind, id)}: a folded query equal to an alias of this kind whose record still exists gives
    {"match": id, "via": "alias <name>"} (space and - compare equal); a dangling alias is ignored."""
    if kind not in ("product", "maker"):
        raise ValueError("kind must be 'product' or 'maker'")
    needle = _fold(query) if isinstance(query, str) else ""
    for name, (alias_kind, ident) in (aliases or {}).items():
        if needle and alias_kind == kind and _fold(name).replace(" ", "-") == needle.replace(" ", "-") and (
                ident in content.makers if kind == "maker" else any(p["id"] == ident for p in content.products)):
            return {"match": ident, "via": f"alias {name}"}
    hits = []
    if needle and kind == "product":
        hits = [(p["id"], {"id": p["id"], "name": p["name"], "brand": p["brand"], "status": p["status"]})
                for p in content.products
                if any(needle in _fold(p.get(f, "")) for f in ("name", "brand", "displayBrand"))]
    elif needle:
        hits = [(k, {"id": k, "name": m["name"], "status": "hidden" if m.get("hidden") else "visible"})
                for k, m in content.makers.items() if needle in _fold(k) or needle in _fold(m["name"])]
    hits.sort(key=lambda hit: hit[0])
    if len(hits) == 1:
        return {"match": hits[0][0]}
    return {"candidates": [item for _id, item in hits[:MAX_CANDIDATES]]}


_PRODUCT_FIELDS = {"name": Arg("text"), "brand": Arg("text"), "category": Arg("enum", choices=CATEGORIES),
                   "image": Arg("image"), "description": Arg("text"), "displayBrand": Arg("text")}
_OPTIONAL = {"producerKey": Arg("maker_key", required=False), "imageAlt": Arg("text", required=False)}
# The maker target is plain text, not "maker_key": membership is checked by _maker() so an unknown key is NotFound.
# (product producerKey references stay "maker_key", so an unknown maker there is still invalid.)
_ID, _KEY = {"id": Arg("id")}, {"key": Arg("text")}

OPS = (
    Op("product.add", {**_PRODUCT_FIELDS, "displayBrand": Arg("text", required=False), "image": Arg("image", required=False), "photo": Arg("id", required=False),
                       **_OPTIONAL}, _product_add),
    Op("product.edit", {**_ID, **{k: Arg(a.kind, required=False, choices=a.choices) for k, a in _PRODUCT_FIELDS.items()},
                        **_OPTIONAL, "clearProducer": Arg("bool", required=False),
                        "clearImageAlt": Arg("bool", required=False)}, _product_edit),
    Op("product.hide", _ID, _product_hide),
    Op("product.restore", _ID, _product_restore),
    Op("product.set_availability", {**_ID, "available": Arg("enum", choices=AVAILABILITY)}, _product_set_availability),
    Op("product.clear_availability", _ID, _product_clear_availability),
    Op("maker.add", {"key": Arg("text"), **{k: Arg("url", required=False) if k == "url" else Arg("text")
                                           for k in MAKER_EDITABLE}},
       _maker_add),
    Op("maker.edit", {**_KEY, **{k: Arg("url" if k == "url" else "text", required=False) for k in MAKER_EDITABLE},
                      "clearUrl": Arg("bool", required=False)},
       _maker_edit),
    Op("maker.hide", {**_KEY, "withProducts": Arg("bool", required=False)}, _maker_hide),
    Op("maker.restore", _KEY, _maker_restore),
)
