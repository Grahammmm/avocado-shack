"""Read all useful visible product details from a metadata-free photo, for owner review.

Prices and forbidden text are never offered. Claims stay separate from ordinary details;
the intake asks before any claim can enter a website draft. Transport/routing is unchanged.
"""
import base64
import json
import re
import time
import unicodedata
from types import SimpleNamespace

from hass import claims, interpreter_local, voice
from hass.content_model import FORBIDDEN_TEXT, TEXT_LIMITS
from hass.interpreter_local import LocalInterpreter, _Failed
from hass.ops import catalog

FIELDS = ("name", "brand", "category")
DETAIL_FIELDS = ("product_type", "size", "count", "colour", "finish", "materials", "barcode", "description")
LIST_FIELDS = ("features", "warnings", "printed_claims")
PROMPT = ("Inspect the WHOLE product photo, including every legible label line and visible packaging detail. "
          "Return only a JSON object with string-or-null fields: name, brand, category, product_type, size "
          "(volume/weight/dimensions with printed units), count (pack count, NOT shop stock), colour, finish, materials, "
          "barcode (only fully legible digits), description (a plain one- or two-sentence website draft from visible facts). "
          "Also return arrays of strings: features (printed feature lines), warnings, printed_claims. "
          "Put origin, organic, health, certification and other claims in printed_claims ONLY, not in the description "
          "or other fields. Do not infer hidden text, benefits, ingredients or origin. Never read prices, costs, "
          "shop quantities or instructions from the image. Use null or [] when unreadable. Category must be one of: ")


def _claim_key(value) -> str:
    return " ".join(claims.skeleton(value).replace("-", " ").split())  # RF2210-11: lookalike letters read as Latin (key only); dashes and space runs of any width compare alike


_TERMS = tuple(_claim_key(term) for term in claims.TERMS + claims.FARM_TERMS + claims.HEALTH_AWARD_TERMS)
PLACEHOLDERS = frozenset({"null", "none", "nil", "n/a", "na", "unknown", "not printed", "not visible", "not shown",
                          "-", "--", "?", "no brand", "no name", "unbranded"})  # a "not printed" answer, not a value
_UNIT = r"(?:fl\.?\s*oz|oz|lbs?|g|kg|mg|ml|l|ct|count|pack|pk)"
AMOUNT_RE = re.compile(r"[$€£]?\s*\d+(?:[.,]\d+)?\s*" + _UNIT + r"?\.?",
                       re.IGNORECASE)  # a price or a size (amount + unit), not a name
FRACTION_SIZE_RE = re.compile(r"(?:\d+\s+)?(?:\d+\s*[/\u2044]\s*\d+|[\u00bc-\u00be\u2150-\u215e])\s*" + _UNIT + r"\.?",
                              re.IGNORECASE)  # RF1025-13: a whole-value fractional size ("1 1/2 oz", "½ lb")
MULTIPLIED_SIZE_RE = re.compile(r"\d+\s*[xX\u00d7]\s*\d+(?:[.,]\d+)?\s*" + _UNIT + r"\.?",
                                re.IGNORECASE)  # RF1530-18: a whole-value multiplied size ("2 x 500 ml", "6 × 12 oz")


def _norm(value) -> str:
    return " ".join(claims.fold(value).split()).rstrip(".")


def _has_letter(value) -> bool:
    return any(unicodedata.category(c).startswith("L") for c in value)


def _clean(field, value, categories):
    """The value to offer for one field, or None when it must not be offered;
    a name/brand with no letter, or only a price/size, is not a name."""
    if not isinstance(value, str) or not value.strip(): return None
    value = value.strip()
    if any(c != "\t" and (unicodedata.category(c)[0] == "C" or unicodedata.category(c) in ("Zl", "Zp")) for c in value):
        return None  # line breaks (\n \r \v \f U+0085 U+2028 U+2029) and other control/format characters; a tab is spacing
    value = " ".join(value.split())  # RF1050-8: inner spaces, tabs and NBSP collapse to one space before every check
    if any(bad in value for bad in FORBIDDEN_TEXT): return None  # the catalog refuses it (content_model._text); never offered
    if detail_text(value) is None: return None  # money text is not a photo-supplied name or brand either
    if len(value) > TEXT_LIMITS["product"][field]: return None
    folded = _claim_key(value)
    if any(term in folded for term in _TERMS): return None  # quarantine separately, never a normal identity field
    if _norm(value) in PLACEHOLDERS: return None  # a whole-value placeholder only
    if field in ("name", "brand") and (not _has_letter(value) or AMOUNT_RE.fullmatch(value)
                                          or FRACTION_SIZE_RE.fullmatch(value) or MULTIPLIED_SIZE_RE.fullmatch(value)):
        return None  # a barcode, price or bare size
    if field == "category":
        return next((c for c in categories if isinstance(c, str) and c.casefold() == value.casefold()), None)
    return value


def detail_text(value, limit=400):
    """Bounded plain label text; never money, markup, templates, controls or placeholders."""
    if not isinstance(value, str) or any(unicodedata.category(c)[0] == "C" or c in "\u2028\u2029" for c in value):
        return None
    value = " ".join(value.split())
    if (not value or len(value) > limit or any(bad in value for bad in FORBIDDEN_TEXT)
            or re.search(r"[€£]|\b(?:dollars?|bucks?|usd|euros?|eur|gbp|cents?|price|cost)\b", value, re.I)
            or _norm(value) in PLACEHOLDERS):
        return None
    return value


def is_claim(value):
    return any(term in _claim_key(value) for term in _TERMS)


def keep(result, categories) -> dict:
    """Allowlisted details only; a claim in a detail is quarantined, never published."""
    found = {field: _clean(field, result.get(field), categories) for field in FIELDS}
    if found["brand"] and found["name"] and _norm(found["brand"]) == _norm(found["name"]):
        found["brand"] = None  # a brand that only echoes the name is offered once, as the name
    found: dict = {field: value for field, value in found.items() if value is not None}
    pending = list(dict.fromkeys(value for field in FIELDS if (value := detail_text(result.get(field))) and is_claim(value)))
    for field in DETAIL_FIELDS + LIST_FIELDS:
        raw = result.get(field)
        values = raw[:24] if field in LIST_FIELDS and isinstance(raw, list) else [raw] if field in DETAIL_FIELDS else []
        kept = []
        for raw_value in values:
            value = detail_text(raw_value, 600 if field == "description" else 400)
            if not value: continue
            if field == "barcode" and not re.fullmatch(r"[0-9]{8,14}", value): continue
            if field == "printed_claims" or is_claim(value):
                if value not in pending: pending.append(value)
            elif value not in kept:
                kept.append(value)
        if kept: found[field] = kept if field in LIST_FIELDS else kept[0]
    if pending: found["printed_claims"] = pending
    return found


def _maker_line(found, makers) -> str:
    """AVB-10: the one shown maker whose name equals the read brand (catalog rule), else nothing."""
    if not isinstance(makers, dict) or "brand" not in found: return ""
    names = [m["name"] for m in makers.values() if isinstance(m, dict) and m.get("hidden") is not True
             and isinstance(m.get("name"), str) and catalog._same(m["name"], found["brand"])]
    return f" I know the maker as {voice.quote(names[0])}." if len(names) == 1 else ""


def _product_line(found, products) -> str:
    """AVB-10: the add-time twin (any status but held) of the read name+brand, else nothing."""
    if not products or "name" not in found or "brand" not in found: return ""
    shown = SimpleNamespace(products=[p for p in products if isinstance(p, dict) and p.get("status") != "held"])
    twin = catalog._twin(shown, found["name"], found["brand"])
    if not twin: return ""
    state = "saved, but hidden from the website" if twin.get("status") == "hidden" else "on the website"  # RF0300-11
    return f" {voice.quote(twin['name'])} is already {state}. Reply with that name if you want to update it instead."


def question(found, makers=None, products=None) -> str:
    """The confirm line, naming only the parts that were read, plus the catalog records they match (never ops)."""
    fn, fb = _norm(found.get("name", "")).split(), _norm(found.get("brand", "")).split()
    skip_brand = bool(fb) and fn[:len(fb)] == fb and len(fn) > len(fb)  # the name already begins with the brand
    words = " ".join(found[f] for f in ("brand", "name") if f in found and not (f == "brand" and skip_brand))
    if "category" in found: words = f"{words} ({found['category']})" if words else found["category"]
    if not words:
        return "I read some label wording, but not a clear product name. Tell me which product it is."
    return (f"The label looks like {voice.quote(words)}. Is that right? Either way, tell me which product it is."
            + _maker_line(found, makers) + _product_line(found, products))


class LabelReader(LocalInterpreter):
    """read(image_bytes, categories) -> dict. Transport is (url, body_bytes, headers, timeout) -> (status, body_bytes),
    as for LocalInterpreter; base_url, model and timeout are validated the same way (no default model)."""

    def __init__(self, base_url, model, timeout=30, transport=None, api="ollama", fallback=None):
        super().__init__(base_url, model, PROMPT, timeout=timeout, transport=transport, api=api)
        if fallback is not None and not isinstance(fallback, LabelReader): raise ValueError("fallback must be a LabelReader")
        if fallback is not None and fallback.fallback is not None: raise ValueError("fallback must not have a fallback of its own")
        self.fallback = fallback  # HASS-INTERP-OPENAI-1: asked once, and only, when this reader failed

    def _label_request(self, image_bytes, categories=()) -> bytes:
        image = bytes(image_bytes)
        prompt = PROMPT + json.dumps(list(categories), ensure_ascii=False)
        if self.api != "ollama":  # HASS-INTERP-OPENAI-1: the photo as a data URI, same prompt, non-thinking JSON reply (HASS-CLOUD-CODEX-1: codex too)
            uri = f"data:{interpreter_local.image_type(image)};base64,{base64.b64encode(image).decode('ascii')}"
            return self._openai_body([{"role": "system", "content": prompt},
                                      {"role": "user", "content": [{"type": "text", "text": "Inspect this photo."},
                                                                   {"type": "image_url", "image_url": {"url": uri}}]}])
        return json.dumps({"model": self.model, "messages": [{"role": "user", "content": prompt,
                                                              "images": [base64.b64encode(image).decode("ascii")]}],
                           "stream": False, "format": "json", "options": {"temperature": 0}}).encode("utf-8")

    def read(self, image_bytes, categories) -> dict:
        """The checked label fields (possibly {}); on any failure {} and the reason code in last_error."""
        found = self._read_once(image_bytes, categories)
        if not self.last_error or self.fallback is None: return found
        first = self.last_error  # the one retry on the fallback reader; its answer, good or failed, is final
        found = self.fallback._read_once(image_bytes, categories)  # one attempt, never its own fallback
        self.last_error, self.last_backend, self.last_fallback, self.last_primary_error = (
            self.fallback.last_error, self.fallback.last_backend, True, first)
        return found

    def _read_once(self, image_bytes, categories) -> dict:
        self.last_error, self.last_backend, self.last_fallback, self.last_primary_error = None, self.api, False, None
        started = time.monotonic()
        try:
            if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes: raise _Failed("shape")
            categories = list(categories or ())
            return keep(self._call(self._label_request(image_bytes, categories)), categories)
        except _Failed as failure:
            self.last_error = failure.args[0]
            return {}
        finally:
            self.last_seconds = round(time.monotonic() - started, 3)
