"""HASS-INTAKE-2: read ONE intake answer that fixed code could not take ("nine fifty-seven a jar", "next Friday week").

AnswerReader(base_url, model).read(key, words, today) sends one JSON request to the same local model service the interpreter uses
(loopback http only, the interpreter's checks, transport and reply limits) with the question's key, the exact form wanted and
his answer, and returns {"value": ...} or {}. It sees nothing else of the interview: no other answer, no name, no price from
another question. Its value is never trusted: hass.skills.item_intake.from_reader checks it again by the rules a typed answer
gets, and a vague, partial or out-of-range value is dropped. Any failure is {} with a short code in ``last_error`` only.
Fixed code asks it once per question, on the first try only (see item_intake.read).
"""
import json
import time

from hass.interpreter_local import LocalInterpreter, _Failed

FORMS = {
    "qty": '{"number": a positive number, "unit": one of each|case|bag|lb|oz|bundle|box|jar|bottle|tin|carton|tub|pack|pouch|loaf|kg|g|can|jug|bar|gallon or null}',
    "qty_unit": "one of each|case|bag|lb|oz|bundle|box|jar|bottle|tin|carton|tub|pack|pouch|loaf|kg|g|can|jug|bar|gallon",
    "sold_by": "one of item|pound|bag|bundle",
    "price": "dollars as digits with at most two decimals, like 9.57",
    "cost": "dollars as digits with at most two decimals, like 4.31",
    "best_by": "one day as YYYY-MM-DD",
    "received": "one day as YYYY-MM-DD",
    "low_stock": "a whole or decimal number, 0 or more",
    "new_badge": "true or false",
}
PROMPT = ("You read one short answer from a shop owner to one question about a product he bought. Answer only with a JSON object "
          '{"value": ...} where value has the form asked. Use null for anything unclear: a range, two different values, a maybe, '
          "a changed mind with no clear final answer, or anything you would have to guess. Never guess and never add words.")


class AnswerReader(LocalInterpreter):
    """read(key, words, today) -> {"value": ...} or {}. Transport, url and model are the interpreter's own."""

    def __init__(self, base_url, model, timeout=30, transport=None, api="ollama", think=None, fallback=None):
        super().__init__(base_url, model, PROMPT, timeout=timeout, transport=transport, api=api, think=think)
        if fallback is not None and (not isinstance(fallback, AnswerReader) or fallback.fallback is not None): raise ValueError("bad fallback")
        self.calls, self.fallback = 0, fallback  # how many times the model was asked; HASS-CLOUD-CODEX-1: asked once when this one failed

    def _answer_request(self, key, words, today) -> bytes:
        user = json.dumps({"question": key, "form": FORMS[key], "today": today.isoformat(), "answer": words}, ensure_ascii=False)
        messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}]
        if self.api != "ollama":
            return self._openai_body(messages)
        body = {"model": self.model, "messages": messages, "stream": False, "format": "json", "options": {"temperature": 0}}
        if self.think is False:
            body["think"] = False
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    def read(self, key, words, today) -> dict:
        found = self._read_once(key, words, today)
        if self.last_error and self.fallback is not None:  # the one retry on the local reader; its answer is final
            first, before, found = self.last_error, self.fallback.calls, self.fallback._read_once(key, words, today)
            self.calls += self.fallback.calls - before
            self.last_error, self.last_backend, self.last_fallback, self.last_primary_error = (
                self.fallback.last_error, self.fallback.last_backend, True, first)
        return found

    def _read_once(self, key, words, today) -> dict:
        self.last_error, self.last_seconds, self.last_backend, self.last_fallback, self.last_primary_error = None, None, self.api, False, None
        started = time.monotonic()
        try:
            if key not in FORMS or not isinstance(words, str) or not words.strip() or len(words) > 400:
                raise _Failed("shape")
            self.calls += 1
            result = self._call(self._answer_request(key, words, today))
            return {"value": result["value"]} if "value" in result else {}
        except _Failed as failure:
            self.last_error = failure.args[0]
            return {}
        finally:
            self.last_seconds = round(time.monotonic() - started, 3)
