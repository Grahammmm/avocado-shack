"""AV1537-15 (H10): read a product label from a stored photo with the local vision model, as a question to confirm.

LabelReader(base_url, model).read(image_bytes, categories) sends one Ollama `POST /api/chat` (loopback http only,
the NB-AV-02 adapter's checks, transport and reply limits) with the photo's metadata-free web copy, and returns at most
{"name", "brand", "category"} as printed on the label. Everything else the model says (maker, origin, organic ...) is
dropped, and so is any value with an organic/origin claim term: a photo never supplies a claim. Any failure is {} with
a short code in `last_error` only; nothing is logged. Not wired into a service: the operator names the existing model.
"""
import base64
import json
import unicodedata

from hass import claims
from hass.content_model import TEXT_LIMITS
from hass.interpreter_local import LocalInterpreter, _Failed

FIELDS = ("name", "brand", "category")
PROMPT = ("Read the product label in this photo. Answer only with a JSON object "
          '{"name": string or null, "brand": string or null, "category": string or null}: the product name and the '
          "brand exactly as printed on the label, and the kind of product. Use null for anything not printed. "
          "Add nothing else.")
_TERMS = tuple(claims.fold(term).replace("-", " ") for term in claims.TERMS)
PLACEHOLDERS = frozenset({"null", "none", "nil", "n/a", "na", "unknown", "not printed", "not visible", "not shown",
                          "-", "--", "?", "no brand", "no name", "unbranded"})  # a "not printed" answer, not a value


def _norm(value) -> str:
    return " ".join(claims.fold(value).split()).rstrip(".")


def _clean(field, value, categories):
    """The value to offer for one field, or None when it must not be offered."""
    if not isinstance(value, str) or not value.strip(): return None
    value = value.strip()
    if any(unicodedata.category(c).startswith("C") for c in value): return None  # control/format characters
    if len(value) > TEXT_LIMITS["product"][field]: return None
    folded = claims.fold(value).replace("-", " ")
    if any(term in folded for term in _TERMS): return None  # no organic/origin claim ever comes from a photo
    if _norm(value) in PLACEHOLDERS: return None  # a whole-value placeholder only
    if field == "category":
        return next((c for c in categories if isinstance(c, str) and c.casefold() == value.casefold()), None)
    return value


def keep(result, categories) -> dict:
    """Only name/brand/category, each checked on its own; any other key is dropped silently."""
    found = {field: _clean(field, result.get(field), categories) for field in FIELDS}
    if found["brand"] and found["name"] and _norm(found["brand"]) == _norm(found["name"]):
        found["brand"] = None  # a brand that only echoes the name is offered once, as the name
    return {field: value for field, value in found.items() if value is not None}


def question(found) -> str:
    """The confirm line, naming only the parts that were read."""
    words = " ".join(found[f] for f in ("brand", "name") if f in found)
    if "category" in found: words = f"{words} ({found['category']})" if words else found["category"]
    return f"The label looks like: {words}. Is that right? Say which product it is either way."


class LabelReader(LocalInterpreter):
    """read(image_bytes, categories) -> dict. Transport is (url, body_bytes, headers, timeout) -> (status, body_bytes),
    as for LocalInterpreter; base_url, model and timeout are validated the same way (no default model)."""

    def __init__(self, base_url, model, timeout=30, transport=None):
        super().__init__(base_url, model, PROMPT, timeout=timeout, transport=transport)

    def _label_request(self, image_bytes) -> bytes:
        image = base64.b64encode(bytes(image_bytes)).decode("ascii")
        return json.dumps({"model": self.model, "messages": [{"role": "user", "content": PROMPT, "images": [image]}],
                           "stream": False, "format": "json", "options": {"temperature": 0}}).encode("utf-8")

    def read(self, image_bytes, categories) -> dict:
        """The checked label fields (possibly {}); on any failure {} and the reason code in last_error."""
        self.last_error = None
        try:
            if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes: raise _Failed("shape")
            return keep(self._call(self._label_request(image_bytes)), list(categories or ()))
        except _Failed as failure:
            self.last_error = failure.args[0]
            return {}
