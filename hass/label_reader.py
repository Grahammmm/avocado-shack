"""AV1537-15 (H10): read a product label from a stored photo with the local vision model, as a question to confirm.

LabelReader(base_url, model).read(image_bytes, categories) sends one Ollama `POST /api/chat` (loopback http only,
the NB-AV-02 adapter's checks, transport and reply limits) with the photo's metadata-free web copy, and returns at most
{"name", "brand", "category"} as printed on the label. Everything else the model says (maker, origin, organic ...) is
dropped, and so is any value with an organic/origin claim term or text the catalog refuses (<, >, $, {{, }}): a photo
never supplies a claim. Any failure is {} with
a short code in `last_error` only; nothing is logged. Not wired into a service: the operator names the existing model.
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
PROMPT = ("Read the product label in this photo. Answer only with a JSON object "
          '{"name": string or null, "brand": string or null, "category": string or null}: the product name and the '
          "brand exactly as printed on the label, and the kind of product. Use null for anything not printed. "
          "Add nothing else.")


def _claim_key(value) -> str:
    return " ".join(claims.fold(value).replace("-", " ").split())  # dashes and space runs of any width compare alike


_TERMS = tuple(_claim_key(term) for term in claims.TERMS + claims.FARM_TERMS + claims.HEALTH_AWARD_TERMS)
PLACEHOLDERS = frozenset({"null", "none", "nil", "n/a", "na", "unknown", "not printed", "not visible", "not shown",
                          "-", "--", "?", "no brand", "no name", "unbranded"})  # a "not printed" answer, not a value
AMOUNT_RE = re.compile(r"[$€£]?\s*\d+(?:[.,]\d+)?\s*(?:fl\.?\s*oz|oz|lbs?|g|kg|mg|ml|l|ct|count|pack|pk)?\.?",
                       re.IGNORECASE)  # a price or a size (amount + unit), not a name


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
    if len(value) > TEXT_LIMITS["product"][field]: return None
    folded = _claim_key(value)
    if any(term in folded for term in _TERMS): return None  # no organic/origin claim ever comes from a photo
    if _norm(value) in PLACEHOLDERS: return None  # a whole-value placeholder only
    if field in ("name", "brand") and (not _has_letter(value) or AMOUNT_RE.fullmatch(" ".join(value.split()))):
        return None  # a barcode, price or bare size
    if field == "category":
        return next((c for c in categories if isinstance(c, str) and c.casefold() == value.casefold()), None)
    return value


def keep(result, categories) -> dict:
    """Only name/brand/category, each checked on its own; any other key is dropped silently."""
    found = {field: _clean(field, result.get(field), categories) for field in FIELDS}
    if found["brand"] and found["name"] and _norm(found["brand"]) == _norm(found["name"]):
        found["brand"] = None  # a brand that only echoes the name is offered once, as the name
    return {field: value for field, value in found.items() if value is not None}


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
    return f" {voice.quote(twin['name'])} is already on the website. Reply with that name if you want to update it instead." if twin else ""


def question(found, makers=None, products=None) -> str:
    """The confirm line, naming only the parts that were read, plus the catalog records they match (never ops)."""
    fn, fb = _norm(found.get("name", "")).split(), _norm(found.get("brand", "")).split()
    skip_brand = bool(fb) and fn[:len(fb)] == fb and len(fn) > len(fb)  # the name already begins with the brand
    words = " ".join(found[f] for f in ("brand", "name") if f in found and not (f == "brand" and skip_brand))
    if "category" in found: words = f"{words} ({found['category']})" if words else found["category"]
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

    def _label_request(self, image_bytes) -> bytes:
        image = bytes(image_bytes)
        if self.api == "openai":  # HASS-INTERP-OPENAI-1: the photo as a data URI, same prompt, non-thinking JSON reply
            uri = f"data:{interpreter_local.image_type(image)};base64,{base64.b64encode(image).decode('ascii')}"
            return self._openai_body([{"role": "user", "content": [{"type": "text", "text": PROMPT},
                                                                   {"type": "image_url", "image_url": {"url": uri}}]}])
        return json.dumps({"model": self.model, "messages": [{"role": "user", "content": PROMPT,
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
            return keep(self._call(self._label_request(image_bytes)), list(categories or ()))
        except _Failed as failure:
            self.last_error = failure.args[0]
            return {}
        finally:
            self.last_seconds = round(time.monotonic() - started, 3)
