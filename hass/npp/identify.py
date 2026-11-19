"""S2: pinned photo-only identification; evidence, not public copy or finance.

The composer supplies metadata-free web copies in attachment order. The first is
still the listing photo; additional images are only supplied to the label read.
"""
import base64
from copy import copy
from dataclasses import dataclass
import json
import re
import time
from typing import Any

from hass import cloud_codex, interpreter_local, label_reader
from hass.interpreter_local import _Failed

ASSET = "hass-product-identify/"


def _valid(value, rule):
    """The closed subset used by the pinned identify schema (bool is not a number)."""
    types = {dict: "object", list: "array", str: "string", type(None): "null",
             bool: "boolean", int: "number", float: "number"}
    kind = types.get(type(value))
    expected = rule["type"]
    if kind not in ([expected] if isinstance(expected, str) else expected):
        return False
    if "enum" in rule and value not in rule["enum"]:
        return False
    if kind == "object":
        props = rule["properties"]
        return (set(rule["required"]) <= value.keys() <= props.keys()
                and all(_valid(v, props[k]) for k, v in value.items()))
    if kind == "array":
        return len(value) <= rule["maxItems"] and all(_valid(v, rule["items"]) for v in value)
    if kind == "string":
        return rule.get("minLength", 0) <= len(value) <= rule.get("maxLength", len(value))
    if kind == "number":
        return rule["minimum"] <= value <= rule["maximum"]
    return True


def _normalize(raw, schema):
    if not _valid(raw, schema):
        raise _Failed("identify-schema")
    result: dict[str, Any] = dict(raw, confidence=dict(raw["confidence"]))
    clean = label_reader.identity_text
    # Do not change the label's brand spelling or use it as a public slot.
    result["item"] = clean("name", raw["item"], title=True)
    result["brand_on_label"] = clean("brand", raw["brand_on_label"])
    size = label_reader.detail_text(raw["size_text"], 30)
    result["size_text"] = size if size and re.fullmatch(
        r"[0-9]+(?:[.,][0-9]+| [0-9]+/[0-9]+|/[0-9]+)?\s*(?:fl\.?\s*oz|oz|lbs?|g|kg|mg|ml|l)\.?", size, re.I) else None
    claims = []
    for field in ("item", "brand_on_label", "label_words", "visible_claims"):
        values = raw[field] if isinstance(raw[field], list) else [raw[field]]
        words = []
        for value in values:
            if not (word := label_reader.detail_text(value, 40)):
                continue
            if field == "visible_claims" or label_reader.is_claim(word):
                claims.append(word)
            elif field == "label_words":
                words.append(word)
        if field == "label_words":
            result[field] = list(dict.fromkeys(words))
    result["visible_claims"] = list(dict.fromkeys(claims))[:8]
    if not all(result[k] for k in ("is_product", "item")):
        result["item"] = None
        result["confidence"]["item"] = 0
    for field, score in (("brand_on_label", "brand"), ("size_text", "size")):
        if not result[field]:
            result["confidence"][score] = 0
    return result


@dataclass(frozen=True)
class Reading:
    evidence: dict | None
    receipt: dict  # only model ID, latency and codes; never image/text


def _read_batch(reader, photos, prompt, schema):
    images = [base64.b64encode(image).decode("ascii") for image in photos]
    text = "Inspect the attached photos."
    prompt += "\nThe first photo is the main view; any others show label details of the same product."
    if reader.api == "ollama":
        body = json.dumps({"model": reader.model, "messages": [{"role": "system", "content": prompt},
                          {"role": "user", "content": text, "images": images}],
                          "stream": False, "format": "json", "options": {"temperature": 0}}).encode()
    else:
        parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for image, encoded in zip(photos, images):
            uri = f"data:{interpreter_local.image_type(image)};base64,{encoded}"
            parts.append({"type": "image_url", "image_url": {"url": uri}})
        body = reader._openai_body([{"role": "system", "content": prompt}, {"role": "user", "content": parts}])
    return _normalize(reader._call(body), schema)


class Identifier:
    def __init__(self, pinned, local=None, *, runner=None, clock=time.monotonic):
        """local is the configured local LabelReader; NPP uses the primary model from pins, not live label settings."""
        pins, files, _ = pinned
        self.step = pins["steps"]["identify"]
        self.schema = json.loads(files[ASSET + "identify.schema.json"])
        examples = json.loads(files[ASSET + "examples.json"])["examples"]
        self.prompt = (files[ASSET + "SKILL.md"].decode() + "\nFixed JSON schema:\n" + json.dumps(self.schema)
                       + "\nExample outputs (illustrations only, not evidence about these photos):\n"
                       + json.dumps([row["output"] for row in examples]))
        self.local, self.runner, self.clock = local, runner or cloud_codex.Runner(), clock

    def read(self, photos):
        photos = tuple(photos)
        started = self.clock()
        actual_model, evidence, error, fallback = None, None, None, False

        def run(request):
            nonlocal actual_model
            response = self.runner(request)
            if isinstance(response, dict) and isinstance(response.get("model"), str):
                actual_model = response["model"]
            return response

        transport = cloud_codex.CodexTransport(self.step["effort"], run)
        # Charge the fallback for the whole primary attempt, including setup.
        primary = label_reader.LabelReader(None, self.step["model"], timeout=self.step["timeout_s"], api="codex", transport=transport)
        if not photos or not all(isinstance(photo, bytes) and photo for photo in photos):
            error = "unreadable-photo"
        else:
            try:
                evidence = _read_batch(primary, photos, self.prompt, self.schema)
            except _Failed as failed:
                error = failed.args[0]
                local = self.local
                if local is not None and local.api in ("ollama", "openai"):
                    fallback, actual_model = True, None
                    transport.started = started

                    def observe(url, body, headers, timeout):
                        nonlocal actual_model
                        status, raw = local.transport(url, body, headers, timeout)
                        if status == 200 and isinstance(raw, bytes) and len(raw) <= interpreter_local.MAX_BODY:
                            try:
                                model = json.loads(raw).get("model")
                                actual_model = model if isinstance(model, str) else None
                            except (ValueError, AttributeError, RecursionError):
                                pass  # the normal LabelReader transport parser rejects malformed replies
                        return status, raw

                    degraded = copy(local)
                    degraded.transport = cloud_codex.Remaining(transport, observe, clock=self.clock)
                    try:
                        evidence = _read_batch(degraded, photos, self.prompt, self.schema)
                    except _Failed as failed:
                        error = failed.args[0]
        return Reading(evidence, {"model": actual_model, "ms": round((self.clock() - started) * 1000),
                                  "fallback": fallback, "schema_valid": evidence is not None,
                                  "error": error if evidence is None else None})
