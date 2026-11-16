"""HASS-INTAKE-2: the full intake interview of ``item.add`` (a new product: what Mike knows when it comes in).

G, 2026-11-16: a picture sent to Hass starts a routine intake, so everything useful for the listing is collected now, even
though the website shows no prices: how many were bought, how it is sold and at what price, who made it, what it is, when it
expires. This module is the pure part: the questions (one at a time, plain words, docs/hass/VOICE.md), the reading of each
answer (``skip`` and ``don't know`` work for every question and are never replaced by a guess), the private summary Mike sees
beside the draft, and the private record that is saved after his ``yes <code>``.

Nothing here touches the website. The PUBLIC listing stays what ``item.add`` already drafts (photo, name, maker line,
description, stock word). Quantity, unit, price, cost, dates, threshold and every descriptor stay PRIVATE: they travel in the
open request's slots, are kept beside the draft in the conversation's own state, and are written to ``item-intake.jsonl`` in the
state folder (0600, like ``maker-sources.jsonl``) only when the draft is applied. They are never in an op, a preview, a
generated file or a message to the interpreter. A claim Mike states (organic, ...) is kept as his unverified word.

Switched on by the setting ``itemIntake: true`` (default off, like ``houseRender``). The dispatcher (hass/skills/dispatch.py)
asks each question and keeps the answers out of the owner's joined texts, so a price he types is never read as a public word.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta

from hass import voice
from hass.content_model import FORBIDDEN_TEXT, INVISIBLE_RE

PREFIX = "intake:"  # the asked-slot name of an intake question on the open request ("intake:qty")
STORE = "item-intake.jsonl"  # the private record, in the state folder
PENDING = ("CREATE TABLE IF NOT EXISTS intake_pending (code TEXT PRIMARY KEY, record_json TEXT NOT NULL, created_at TEXT NOT NULL)")
KEEP_DAYS = 30  # a waiting record nobody said yes to is forgotten after this long
MAX_TEXT = 400
PRIVATE_HEAD = "Kept private, not on the website:"
INTRO = "A few quick questions for your books. Say skip if you don't know one."
START = "Got the photo. A few quick questions: name, maker, how many, price and dates. What is it called?"

ORDER = ("maker_site", "qty", "qty_unit", "sold_by", "price", "cost", "ingredients", "variety", "origin", "claims",
         "allergens", "storage", "best_by", "received", "low_stock", "customer_note", "new_badge")
TEXT_FIELDS = ("ingredients", "variety", "origin", "claims", "allergens", "storage")
LABELS = {"ingredients": "Ingredients", "variety": "Flavor, size or variety", "origin": "Origin",
          "claims": "On the label (unverified, your word)", "maker_site": "Maker's website", "allergens": "Allergens", "storage": "Storage and use"}

SKIP = re.compile(r"^\s*(?:skip(?:\s+(?:it|this|that|one))?|pass|next|(?:i\s+)?(?:don'?t|do\s+not|dont)\s+know|dunno|not\s+sure|no\s+idea"
                  r"|unknown|n/?a|i\s+forgot|can'?t\s+(?:say|tell|remember))\s*[.!]*\s*$", re.IGNORECASE)
NONE_WORDS = re.compile(r"^\s*(?:none|no|nope|nothing|nil|no\s+claims?|no\s+allergens?)\s*[.!]*\s*$", re.IGNORECASE)
ABORT = re.compile(r"^\s*(?:cancel|stop|never\s*mind|forget\s+it|drop\s+it|start\s+over|quit)\s*[.!]*\s*$", re.IGNORECASE)
YES = re.compile(r"^\s*(?:yes|yep|yeah|y|sure|ok(?:ay)?|please|do\s+it)\b", re.IGNORECASE)
NO = re.compile(r"^\s*(?:no|nope|nah|n|not\s+(?:this\s+time|needed))\b", re.IGNORECASE)
CODED_KEYWORD = re.compile(r"^\s*(?:yes|no|ok|okay|approve|reject|undo|cancel|show)[\s,:-]+[0-9a-f]{4,6}\s*[.!]*\s*$", re.IGNORECASE)

UNIT_WORDS = {"each": "each", "ea": "each", "item": "each", "items": "each", "piece": "each", "pieces": "each",
              "case": "case", "cases": "case", "bag": "bag", "bags": "bag", "lb": "lb", "lbs": "lb", "pound": "lb",
              "pounds": "lb", "oz": "oz", "ounce": "oz", "ounces": "oz", "bundle": "bundle", "bundles": "bundle",
              "bunch": "bundle", "bunches": "bundle", "dozen": "dozen", "dozens": "dozen", "box": "box", "boxes": "box",
              "jar": "jar", "jars": "jar", "bottle": "bottle", "bottles": "bottle", "tin": "tin", "tins": "tin",
              "carton": "carton", "cartons": "carton", "tub": "tub", "tubs": "tub", "pack": "pack", "packs": "pack",
              "pouch": "pouch", "pouches": "pouch", "loaf": "loaf", "loaves": "loaf", "kg": "kg", "g": "g"}
SOLD_BY = (("pound", re.compile(r"\b(?:pound|pounds|lb|lbs|weight)\b", re.IGNORECASE)),
           ("bag", re.compile(r"\b(?:bag|bags)\b", re.IGNORECASE)),
           ("bundle", re.compile(r"\b(?:bundle|bundles|bunch|bunches)\b", re.IGNORECASE)),
           ("item", re.compile(r"\b(?:item|items|each|piece|one|unit|jar|bottle|box|loaf|tin|carton|tub|pack)\b", re.IGNORECASE)))
SOLD_WORDS = {"item": "per item", "pound": "per pound", "bag": "per bag", "bundle": "per bundle"}
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12}
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


# -- small helpers ----------------------------------------------------------------------------------------------------
def _clean(text) -> str:
    return " ".join(text.split()) if isinstance(text, str) else ""


def _q(text) -> str:
    return voice.quote(text)


def _said(text) -> str:
    """His own words for the summary, without a closing full stop (the sentence adds its own)."""
    return voice.quote(str(text).strip().rstrip(" ."))


def _units(qty, unit) -> str:
    """\"1 jar\", \"137 jars\", \"5 lb\", \"3 cases\": the unit as he said it, plural when there is more than one."""
    if not unit or qty == 1 or unit in ("lb", "oz", "kg", "g", "each"):
        return unit
    if unit == "loaf":
        return "loaves"
    return unit + ("es" if unit.endswith(("s", "x", "ch", "sh")) else "s")


def _num_text(n) -> str:
    return str(int(n)) if float(n) == int(n) else ("%g" % n)


def _day_text(iso) -> str:
    try:
        d = date.fromisoformat(iso)
        return f"{d:%b} {d.day}, {d.year}"
    except (TypeError, ValueError):
        return "a day I can't read"


def money_text(value) -> str:
    return "$" + value if isinstance(value, str) and value else ""


def enabled(ctx) -> bool:
    return getattr(ctx, "intake", False) is True


# -- what is asked next -----------------------------------------------------------------------------------------------
def next_key(intake, new_maker=False):
    """The next question's key, in the order Mike is asked, or None when everything is answered or skipped. A key that is in
    ``intake`` (even as None, which is a skip) is done."""
    got = intake if isinstance(intake, dict) else {}
    for key in ORDER:
        if key in got:
            continue
        if key == "maker_site" and not new_maker:
            continue
        if key == "qty_unit" and got.get("qty") is None:
            continue
        return key
    return None


def _per(intake) -> str:
    return {"item": "for each one", "pound": "per pound", "bag": "for each bag", "bundle": "for each bundle"}.get(
        (intake or {}).get("sold_by"), "for each one")


def question(key, name, intake) -> str:
    """The one plain question for ``key``. Never two questions in one."""
    what = _q(name) if name else "it"
    if key == "maker_site":
        return "Do they have a website? Send the address, like www.example.com, or say skip."
    if key == "qty":
        return f"How many did you buy of {what}? A number and what they come in is perfect, like 12 jars, 3 cases or 5 lb."
    if key == "qty_unit":
        return f"And what are the {_num_text(intake['qty'])} counted in: each, cases, bags, pounds or ounces?"
    if key == "sold_by":
        return "Is it sold per item, per pound, per bag or per bundle?"
    if key == "price":
        return f"What do you charge {_per(intake)}? I keep prices private. The website does not show them."
    if key == "cost":
        return f"What did you pay {_per(intake)}? You can skip this one."
    if key == "ingredients":
        return "What are the ingredients?"
    if key == "variety":
        return "Is there a flavor, size or variety I should note?"
    if key == "origin":
        return "Where does it come from?"
    if key == "claims":
        return "Does the label say anything special, like organic? I note it as your word, unchecked, and keep it off the website."
    if key == "allergens":
        return "Are there any allergens on the label?"
    if key == "storage":
        return "How should it be stored or used?"
    if key == "best_by":
        return "What is the best-by or expiration date?"
    if key == "received":
        return "What day did you buy or receive it?"
    if key == "low_stock":
        return "At what count should I call it low on stock?"
    if key == "customer_note":
        return "Is there one sentence you would like customers to read about it?"
    if key == "new_badge":
        return "Should it show the New label? Yes or no."
    raise KeyError(key)


# -- reading an answer ------------------------------------------------------------------------------------------------
def _parse_money(text):
    m = re.match(r"\s*\$?\s*(\d{1,6}(?:\.\d{1,2})?)(?![\d.])", text)
    if not m:
        return None
    return "%.2f" % float(m.group(1))


def _parse_qty(text):
    """(number, unit or None) from "12 jars", "3 cases", "a dozen", "5 lb", "12"; None when there is no number."""
    t = text.strip().lower().replace(",", "")
    m = re.match(r"(\d{1,6}(?:\.\d+)?)\s*(?:x\s*)?([a-z]+)?\b", t)
    if m:
        number, word = float(m.group(1)), m.group(2)
    else:
        m = re.match(r"(a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+([a-z]+)?", t)
        if not m:
            return None
        number, word = float(NUMBER_WORDS[m.group(1)]), m.group(2)
    if word in (None, "of"):
        return number, None
    unit = UNIT_WORDS.get(word)
    if unit == "dozen":
        return number * 12, "each"
    if unit is None:  # a container or counting word of his own: kept as he said it, short and plain
        unit = word[:-1] if word.endswith("s") and len(word) > 3 else word
    return number, unit


def _parse_sold_by(text):
    for key, rx in SOLD_BY:
        if rx.search(text):
            return key
    return None


def parse_day(text, today, *, past=False):
    """A date from his words (today, tomorrow, in 3 weeks, Dec 20, 12/20/2027, 2027-12-20), else None. With no year the
    next such day is taken for a best-by date, the last such day for a day he bought it (``past``)."""
    t = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", re.sub(r"[,.]", " ", _clean(text).lower())).strip()
    t = re.sub(r"^(?:on|by|about|around|best by|exp(?:ires?)?)\s+", "", t)
    if t in ("today", "now"):
        return today
    if t == "yesterday":
        return today - timedelta(days=1)
    if t == "tomorrow":
        return today + timedelta(days=1)
    m = re.fullmatch(r"in (\d{1,3}) (day|week|month)s?", t)
    if m:
        n = int(m.group(1))
        return today + timedelta(days=n * {"day": 1, "week": 7, "month": 30}[m.group(2)])
    year = month = day = None
    if (m := re.fullmatch(r"(\d{4})[-/ ](\d{1,2})[-/ ](\d{1,2})", t)):
        year, month, day = int(m[1]), int(m[2]), int(m[3])
    elif (m := re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", t)):
        month, day = int(m[1]), int(m[2])
        year = int(m[3]) if m[3] else None
    elif (m := re.fullmatch(r"([a-z]{3})[a-z]* (\d{1,2})(?: (\d{2,4}))?", t)) and m[1] in MONTHS:
        month, day = MONTHS[m[1]], int(m[2])
        year = int(m[3]) if m[3] else None
    elif (m := re.fullmatch(r"(\d{1,2}) ([a-z]{3})[a-z]*(?: (\d{2,4}))?", t)) and m[2] in MONTHS:
        day, month = int(m[1]), MONTHS[m[2]]
        year = int(m[3]) if m[3] else None
    else:
        return None
    if year is not None and year < 100:
        year += 2000
    try:
        if year is not None:
            found = date(year, month, day)
            return found if 2000 <= found.year <= 2100 else None
        found = date(today.year, month, day)
        if past and found > today:
            found = date(today.year - 1, month, day)
        elif not past and found < today:
            found = date(today.year + 1, month, day)
        return found
    except ValueError:
        return None


def _text_value(key, text):
    """(value, None) for free words, or (None, the plain re-ask)."""
    words = _clean(text)
    if any(bad in words for bad in FORBIDDEN_TEXT) or INVISIBLE_RE.search(words):
        return None, "I can't use one of the characters in that. Could you say it again in plain words?"
    if len(words) > MAX_TEXT:
        return None, "That is a bit long for my notes. Could you shorten it?"
    if NONE_WORDS.match(words) and key in ("allergens", "claims"):
        return "none", None  # for these two, "none" is an answer; for the others it is nothing to note
    if NONE_WORDS.match(words):
        return "", None
    return words, None


def read(key, text, intake, *, today, asks=1):
    """Read his answer to question ``key``. Returns one of

        ("abort", None)                       he wants to stop the whole thing
        ("again", reply)                      the answer cannot be used: the one question again, in plain words
        ("ok", {key: value, ...}, extra)      the intake answers it sets (a skipped question is ``{key: None}``) and the slots
                                              of the skill it also sets (``maker_url``)

    ``asks`` is how many times this question has been asked; the third unreadable answer counts as a skip, so he is never stuck."""
    words = _clean(text)
    if ABORT.match(words):
        return ("abort", None)
    if not words or SKIP.match(words):
        return ("ok", {key: None}, {})
    got, fail = None, None
    if key == "maker_site":
        from hass import maker_site  # lazy: the website reader is only needed for this question
        found = maker_site.addresses_in([words])
        if found:
            return ("ok", {key: found[0]}, {"maker_url": found[0]})
        fail = "I couldn't use that address."
    elif key == "qty":
        parsed = _parse_qty(words)
        if parsed is None:
            fail = "I didn't catch a number there."
        else:
            out = {"qty": parsed[0] if parsed[0] != int(parsed[0]) else int(parsed[0])}
            if parsed[1]:
                out["qty_unit"] = parsed[1]
            return ("ok", out, {})
    elif key == "qty_unit":
        word = re.sub(r"[^a-z ]", "", words.lower()).strip()
        unit = UNIT_WORDS.get(word.split()[0]) if word else None
        if unit and unit != "dozen":
            return ("ok", {key: unit}, {})
        fail = "I didn't catch that unit."
    elif key == "sold_by":
        got = _parse_sold_by(words)
        if got:
            return ("ok", {key: got}, {})
        fail = "I didn't catch that."
    elif key in ("price", "cost"):
        got = _parse_money(words)
        if got:
            return ("ok", {key: got}, {})
        fail = "I didn't catch an amount there."
    elif key in TEXT_FIELDS or key == "customer_note":
        value, fail = _text_value(key, words)
        if fail is None:
            return ("ok", {key: value or None}, {})
    elif key in ("best_by", "received"):
        found = parse_day(words, today, past=key == "received")
        if found:
            return ("ok", {key: found.isoformat()}, {})
        fail = "I couldn't read that date. Something like Dec 20, 2027 works."
    elif key == "low_stock":
        parsed = _parse_qty(words)
        if parsed:
            return ("ok", {key: parsed[0] if parsed[0] != int(parsed[0]) else int(parsed[0])}, {})
        fail = "I didn't catch a number there."
    elif key == "new_badge":
        if YES.match(words):
            return ("ok", {key: True}, {})
        if NO.match(words):
            return ("ok", {key: False}, {})
        fail = "I didn't catch that."
    else:
        raise KeyError(key)
    if asks >= 3:  # asked three times and still not readable: that one is skipped, never guessed
        return ("ok", {key: None}, {})
    return ("again", fail)


# -- what Hass says back, and what is kept ----------------------------------------------------------------------------
def private_lines(intake) -> list:
    """The "kept private" summary shown beside the draft (every line is private; none of it goes on the website)."""
    got = intake if isinstance(intake, dict) else {}
    if not got:
        return []
    out = [PRIVATE_HEAD]
    qty, unit = got.get("qty"), got.get("qty_unit")
    if qty is not None:
        out.append(f"Bought: {_num_text(qty)}" + (f" {_q(_units(qty, unit))}" if unit else "") + ".")
    if got.get("sold_by"):
        out.append(f"Sold {SOLD_WORDS[got['sold_by']]}.")
    if got.get("price"):
        out.append(f"Price: {money_text(got['price'])} {_per(got)}.")
    if got.get("cost"):
        out.append(f"You paid: {money_text(got['cost'])} {_per(got)}.")
    for key in TEXT_FIELDS:
        if got.get(key):
            out.append(f"{LABELS[key]}: {_said(got[key])}.")
    if got.get("best_by"):
        out.append(f"Best by: {_day_text(got['best_by'])}.")
    if got.get("received"):
        out.append(f"Bought or received: {_day_text(got['received'])}.")
    if got.get("low_stock") is not None:
        out.append(f"Low on stock at: {_num_text(got['low_stock'])}.")
    if got.get("maker_site"):
        out.append(f"Maker's website: {_said(got['maker_site'])}.")
    if got.get("customer_note"):
        out.append(f"Your sentence for customers: {_said(got['customer_note'])}.")
    if got.get("new_badge") is False:
        out.append("You would rather not show the New label. The website adds it by itself for a few days, so I wrote that down for Graham.")
    skipped = [LABELS.get(k, k.replace("_", " ")).split(" (")[0].lower() for k in ORDER if k in got and got[k] is None
               and k != "qty_unit"]
    if skipped:
        out.append("Skipped, so I left them blank: " + ", ".join(skipped) + ".")
    return out


def skipped_names(intake) -> list:
    return [k for k in ORDER if isinstance(intake, dict) and k in intake and intake[k] is None]


def record(draft_code, name, maker, shelf, product_id, photo, intake, now) -> dict:
    """The private intake record, as it is kept. Owner texts are never in it; only his answers to these questions."""
    answers = {k: v for k, v in (intake or {}).items() if k in ORDER}
    return {"schema": 1, "kind": "item.intake", "status": "saved", "draft": draft_code, "product": product_id, "name": name,
            "maker": maker, "shelf": shelf, "photo": photo, "answers": answers, "skipped": skipped_names(intake),
            "claims_unverified": bool(answers.get("claims") and answers["claims"] != "none"),
            "drafted_at": now.isoformat() if hasattr(now, "isoformat") else str(now)}


def keep_pending(db, code, rec, now) -> None:
    """Keep the record beside the draft ``code`` until it is applied (the conversation's own private state)."""
    db.execute(PENDING)
    stamp = now.isoformat() if hasattr(now, "isoformat") else str(now)
    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat() if hasattr(now, "isoformat") else ""
    db.execute("DELETE FROM intake_pending WHERE created_at < ?", (cutoff,))
    db.execute("INSERT OR REPLACE INTO intake_pending(code, record_json, created_at) VALUES (?, ?, ?)",
               (code, json.dumps(rec, sort_keys=True, ensure_ascii=False), stamp))


def _append(sdir, row) -> None:
    path = os.path.join(str(sdir), STORE)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as out:
        out.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def save_applied(db, sdir, code, now):
    """The draft ``code`` was applied: the waiting record becomes one line of ``item-intake.jsonl``. Returns the row or None."""
    try:
        db.execute(PENDING)
        found = db.execute("SELECT record_json FROM intake_pending WHERE code = ?", (code,)).fetchone()
        if found is None:
            return None
        row = json.loads(found["record_json"] if hasattr(found, "keys") else found[0])
        row["applied_at"] = now.isoformat() if hasattr(now, "isoformat") else str(now)
        _append(sdir, row)
        db.execute("DELETE FROM intake_pending WHERE code = ?", (code,))
        return row
    except (OSError, sqlite3.Error, ValueError):
        return None  # best effort: a record that cannot be written never undoes a change that was applied


def mark_undone(sdir, code, now):
    """The change ``code`` was undone: if it had a saved record, one more line says so; the earlier line is never edited."""
    path = os.path.join(str(sdir), STORE)
    try:
        with open(path, encoding="utf-8") as src:
            saved = any(json.loads(line).get("draft") == code and json.loads(line).get("status") == "saved" for line in src if line.strip())
        if not saved:
            return None
        _append(sdir, {"schema": 1, "kind": "item.intake", "status": "undone", "draft": code,
                       "undone_at": now.isoformat() if hasattr(now, "isoformat") else str(now)})
    except (OSError, ValueError):
        return None
    return True
