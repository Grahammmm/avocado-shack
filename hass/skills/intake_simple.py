"""Single editable catalog draft. Only the typed selling price is public; photo text is data, never ops.

This adapter uses product.add and the ordinary editor/approval/live-policy gates,
not a second publication path.
"""
import re

from hass import newitem, voice, product_claims
from hass.content_model import CATEGORIES, FORBIDDEN_TEXT, INVISIBLE_RE, TEXT_LIMITS
from hass.skills import item_intake as ii

NEXT = re.compile(r"^(?:what['’]?s next|what next|next|\?)[?!. ]*$", re.I)


def public_sources(slots):
    details = photo_details(slots.get("intake") or {})
    return [v for value in details.values() for v in (value if isinstance(value, list) else [value]) if isinstance(v, str)]


def photo_details(got):
    # An earlier explicit rejection remains an edit, even though fresh reads no longer ask for consent.
    if got.get("photo_confirmed") is False: return {}
    details = dict(got.get("photo_details") or {})
    if "printed_claims" in details:
        details["printed_claims"] = [c for i, c in enumerate(details["printed_claims"])
                                    if got.get("photo_claim_answers", {}).get(str(i)) is not False]
    return details


def fill(slots, texts):
    """Fill only absent facts. Never invent a maker location or create a maker profile."""
    out = dict(slots)
    got = dict(out.get("intake") or {})
    got["simple"] = True
    out["intake"] = got
    details = photo_details(got)
    for source, target in (("name", "name"), ("brand", "maker"), ("category", "shelf")):
        value = (got.get("category_choice") or details.get(source)) if source == "category" else details.get(source)
        if value and (not out.get(target) or got.get(target + "_default")):
            out[target] = value
            got.pop(target + "_default", None)
    if not out.get("name"): return out
    if not out.get("maker"):
        out["maker"], got["maker_default"] = "Producer not identified", True
    if not out.get("shelf"):
        out["shelf"] = newitem.stated_shelf(" ".join(texts)) or "general"
        got["shelf_default"] = not bool(newitem.stated_shelf(" ".join(texts)))
    if not out.get("description") or details and not got.get("photo_applied"):
        prior = "" if got.get("description_default") else out.get("description", "")
        parts = [prior, details.get("description") or (out.get("name", "") if not prior else "")]
        got["description_default"] = not bool(prior or details.get("description"))
        if details.get("size"):
            parts = [re.sub(re.escape(details["size"]) + r"\.?", "", p, flags=re.I).strip() for p in parts]
        parts += [details[k] for k in ("size", "count", "colour", "finish", "materials") if details.get(k)]
        label_features = details.get("features", []) + details.get("printed_claims", []) + details.get("warnings", [])
        if label_features: parts.append(", ".join(p.rstrip(".") for p in dict.fromkeys(label_features)))
        # A caption's explicit origin/organic words are owner statements, not label
        # inference. Add them only on the first photo fill so later removals stay removed.
        if details and not got.get("photo_applied"):
            for text in texts:
                for shown, sentence in product_claims.live_policy._pieces(text):
                    phrase = re.sub(r"^\s*add\s*:?\s*", "", shown, flags=re.I).strip()
                    if (product_claims.live_policy._protected(phrase)[1] == {"origin/organic"}
                            and product_claims.live_policy._owner_said(sentence, product_claims.live_policy.claims.fold("\n".join(texts)))
                            and phrase.casefold() not in " ".join(parts).casefold()):
                        parts.append(phrase)
        kept, overflow = [], []
        for part in dict.fromkeys(p.rstrip(".") + "." for p in parts if p):
            if len(" ".join([*kept, part])) <= TEXT_LIMITS["product"]["description"]:
                kept.append(part)
            else:
                overflow.append(part)
        out["description"] = " ".join(kept)
        if details: got["photo_applied"] = True
        if overflow: got["left_off_label"] = overflow
    if (not out.get("availability") or got.get("availability_derived")) and got.get("qty") is not None:
        out["availability"] = "yes" if got["qty"] > 0 else "no"
        got["availability_derived"] = True
    return out


def edit(slots, text, asked=None):
    """Return changed slots and public source text. Unstructured replies become copy, not a yes/no loop."""
    out = dict(slots)
    got = dict(out.get("intake") or {})
    public, finance = ii.caption_answers(text)
    got.update(finance)
    out["intake"] = got
    if asked == "price" and not finance and (value := ii._parse_money(text)) is not None:
        got["price"] = value
        return out, ""
    if not public or NEXT.fullmatch(public.strip()) or ii.SKIP.fullmatch(public.strip()):
        return out, ""
    if match := re.fullmatch(r"(?:remove|leave out|delete)\s+(.+)", public, re.I):
        target = match[1].strip().rstrip(".")
        description = out.get("description", "")
        out["description"] = re.sub(re.escape(target) + r"[.!]?", "", description, flags=re.I).strip()
        out["description"] = " ".join(out["description"].split())
        return out, ""
    if match := re.fullmatch(r"(?:name|call it|rename(?: it)?(?: to)?)\s*:?\s+(.+)", public, re.I):
        out["name"] = match[1]
        out["image_alt"] = match[1]
        return out, match[1]
    if match := re.fullmatch(r"(?:brand|maker)\s*:?\s+(.+)", public, re.I):
        out["maker"] = match[1]
        got.pop("maker_default", None)
        return out, match[1]
    if match := re.fullmatch(r"(?:category|shelf)\s*:?\s+(.+)", public, re.I):
        out["shelf"] = match[1].lower()
        got.pop("shelf_default", None)
        return out, match[1]
    stock = {"in stock": "yes", "sold out": "no", "low on stock": "limited"}.get(public.strip().lower())
    if stock:
        out["availability"] = stock
        got["availability_derived"] = False
        return out, public
    copy = re.sub(r"^(?:add|description)\s*:\s*", "", public, flags=re.I)
    if asked == "name":
        out["name"] = copy
    elif copy:
        out["description"] = " ".join([out.get("description", ""), copy]).strip()
        got["description_default"] = False
    return out, copy


def plan(slots, content):
    """Existing catalog schema only; the editor independently enforces holds, twins and photo safety."""
    name = slots.get("name") or ""
    brand = slots.get("maker") or "Producer not identified"
    description = slots.get("description") or name
    args = {"name": name, "brand": brand, "category": slots.get("shelf"), "description": description}
    for key, value in args.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError("The listing needs " + key + ".")
        if len(value) > TEXT_LIMITS["product"][key] or any(bad in value for bad in FORBIDDEN_TEXT) or INVISIBLE_RE.search(value):
            raise ValueError("I can't use that wording. The listing is unchanged; send the change in plain words.")
        if re.search(r"[$€£]|\b(?:prices?|costs?|dollars?|bucks?|usd|euros?|eur|gbp|cents?)\b", value, re.I):
            raise ValueError("Give the selling price separately, not in the website wording. The listing is unchanged.")
    if args["category"] not in CATEGORIES:
        raise ValueError("That shelf isn't on the website. The listing is unchanged.")
    labels = product_claims.sanitize(slots, photo_details(slots.get("intake") or {}))
    args.update(name=slots.get("name") or name, brand=slots.get("maker") or brand,
                description=slots.get("description") or name)
    if slots.get("photo"):
        args.update(photo=slots["photo"], imageAlt=slots.get("image_alt") or name)
        if labels:
            args["labelText"] = labels
        if owner := [t for t in slots.get("_owner_texts", []) if product_claims.live_policy._protected(t)[1] & {"origin/organic"}]:
            args["ownerText"] = owner
    # Reuse an identified catalog maker only; a new printed brand needs no invented town/story.
    matches = [key for key, maker in content.makers.items() if maker.get("name", "").casefold() == brand.casefold()]
    if len(matches) == 1:
        args["producerKey"] = matches[0]
    intake = slots.get("intake") or {}
    if intake.get("price") is not None:
        unit = {"pound": " per lb", "item": " each"}.get(intake.get("sold_by", ""), "")
        args["sellingPrice"] = intake["price"] + unit
    ops = [{"op": "product.add", "args": args}]
    if slots.get("availability"):
        ops.append({"op": "store.confirm_selection", "args": {slots["availability"]: [newitem.next_product_id(content)]}})
    return ops


def preview(slots, code=None):
    got = slots.get("intake") or {}
    details = photo_details(got)
    description = slots.get("description") or "Not read yet"
    size = details.get("size")
    if size: description = re.sub(re.escape(size) + r"\.?", "", description, flags=re.I)
    features = []
    for part in sorted((p for p in [*(details.get(k) for k in ("count", "colour", "finish", "materials")),
                                    *details.get("features", []), *details.get("printed_claims", []), *details.get("warnings", [])] if p),
                       key=len, reverse=True):
        if part and part.casefold() in description.casefold():
            quoted = 'Label says: “' + part + '”'
            shown = quoted if quoted.casefold() in description.casefold() else part
            features.append(shown.rstrip("."))
            description = re.sub(re.escape(shown) + r"[.!]?(?:,\s*)?", "", description, flags=re.I)
    description = " ".join(description.split()).strip(" ,;.")
    if description: description += "."
    lines = ["Here's the listing:", "Name: " + voice.quote(slots.get("name") or "Not read yet"),
             "Brand: " + voice.quote(slots.get("maker") or "Producer not identified")]
    if size: lines.append("Size: " + voice.quote(size))
    lines.append("Description: " + voice.quote(description or slots.get("name") or "Not read yet"))
    if features: lines.append("Features: " + voice.quote(", ".join(dict.fromkeys(features))))
    unit = {"pound": " per lb", "item": " each"}.get(got.get("sold_by"), "")
    if got.get("price") is not None: lines.append("Price: " + ii.money_text(got["price"]) + unit)
    category = slots.get("shelf") or "general"
    lines.append("Category: " + voice.quote(category.title()) + (" (say 'category X' to change)" if category == "general" else ""))
    if slots.get("availability"):
        lines.append("Availability: " + {"yes": "in stock", "no": "sold out", "limited": "low on stock"}[slots["availability"]])
    private = []
    if got.get("cost") is not None: private.append("cost " + ii.money_text(got["cost"]))
    if got.get("qty") is not None:
        private.append("quantity " + str(got["qty"]) + (" lb" if got.get("qty_unit") == "lb" else ""))
    if private: lines.append("Private (not shown on the website): " + ", ".join(private))
    if got.get("price") is not None and got.get("cost") is not None and got["price"] != got["cost"]:
        from decimal import Decimal
        if Decimal(got["price"]) < Decimal(got["cost"]): lines.append("Note: the selling price is below your cost.")
    if got.get("left_off_label"):
        lines.append("More label text (not in the listing; it has no room): " + voice.quote(" ".join(got["left_off_label"])))
    if details.get("barcode"): lines.append("Label barcode (kept private): " + voice.quote(details["barcode"]))
    if code:
        lines.append("Reply yes " + code + " to publish, or tell me what to change.")
    return "\n".join(lines)
