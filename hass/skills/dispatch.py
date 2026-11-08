"""Skill dispatch (SKILLS-FW-3): a skill reply from the interpreter -> validated slots -> a plan -> ``editor.prepare``.

The model reads the sentence; code decides the change. This module only ever turns an interpreter reply into the same
typed ops the conversation already knows how to draft, and keeps the owner's open request (hass/skills/openreq.py) in step:

    {"skill": name, "slots": {...}, "revises": code|null}     one skill
    {"calls": [{"skill", "slots"}, ...], "revises": null}     several asks in one message (at most MAX_OPS ops in all)
    {"skill": "none", "summary": "..."}                       nothing fits: backlog row, nothing changes
    {"cancel": true}                                          drop the open request (continue mode)

Nothing here approves, applies, releases or sends anything. Every draft goes through ``Conversation._draft`` (editor, claims,
proposal, owner ``yes <code>``), exactly as a raw-ops draft does. The owner's texts are private: never logged or printed.

Interface assumptions about SKILLS-FW-2 (router / prompt / reply check), all optional, all fail-safe:
  * ``hass.skills.router.candidates(text, hints, open_request, attachment)`` returns up to 3 candidates, best first, each a
    ``(name, score)`` pair, a dict with ``skill``/``name`` and ``score``, or an object with ``.skill``/``.name`` and ``.score``.
    If the module is missing, or raises, the agreement rule (spec 2.5) is skipped and the model's skill is used: a wrong
    choice can only produce a wrong DRAFT, which the owner still has to approve by code.
  * The interpreter receives the continue-mode snapshot through its existing ``recent`` argument (keys ``question``,
    ``earlier``, plus ``skill``, ``slots``, ``asked_slot``, ``draft``); the Skills section of its prompt is FW-2's.
  * ``hass.interpret_check.check_skill`` is NOT needed: this module validates the reply shape and every slot itself.
"""
from __future__ import annotations

import importlib
import re
import sys
from datetime import datetime

from hass import content_model, nl_prep
from hass.ops import DATE_RE, TIME_RE
from hass.skills import kinds, openreq
from hass.skills.model import MAX_OPS

MODES = ("ops-only", "both", "skills-first")
DEFAULT_MODE = "ops-only"
MAX_CALLS = MAX_OPS

# which op families a skill group owns: in skills-first a raw-ops reply is refused for these (spec 2.4)
GROUP_OPS = {"item": ("product",), "stock": ("product", "store"), "hike": ("hike",), "maker": ("maker",),
             "shop": ("store",), "page": ("store",)}

DROPPED = "Okay, I dropped that. Nothing changed."
NOT_SURE = "Sorry, I could not understand that request."
STUCK = "I'm not getting this. Send it in one message, like: {example}"
TOO_MANY = "That is more than {limit} changes at once ({count}). Send it in smaller parts."
PLAN_FAILED = "Sorry, I could not set that up, so nothing was changed. Please send the change again."
PRICE = "The website does not show prices, so nothing was drafted. Send the change without the price."
PHOTO_FOR = "What is this photo for: {labels}?"
PHOTO_MISMATCH = "A photo goes with {labels}. Which one is it?"
NO_SKILL_SAID = "I can't do that yet. I wrote it down as request #{n}. Nothing on the site changed."
HIDDEN = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b\u200e\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")
MONEY = re.compile(r"\$\s*\d|\b\d+(?:\.\d\d)?\s*(?:dollars?|bucks|usd)\b|\bper\s+(?:lb|pound|oz|ounce|kg|dozen)\b", re.I)

# Rules and derived defaults are named functions the skill modules register (spec 2.2: "each id maps to a named function").
#   RULES[id](slots, texts, ctx) -> None | (owner reply, backlog reason)        first hit stops
#   DERIVERS[name](slots, ctx)   -> a value for a slot whose default is "derive:<name>"
#   READ_ONLY[skill name](slots, ctx) -> the reply of a read-only skill other than the backlog ones
RULES: dict = {}
DERIVERS: dict = {}
READ_ONLY: dict = {}


def _no_price(slots, texts, ctx):
    return (PRICE, "price") if MONEY.search("\n".join(texts)) else None


RULES.setdefault("no-price", _no_price)


class Ctx:
    """What a skill's ``plan`` and rules may read: the saved content (read-only), today (Pacific), aliases, the owner's texts."""

    def __init__(self, content, today, aliases, texts, now):
        self.content, self.today, self.aliases, self.texts, self.now = content, today, aliases, texts, now


# -- reply shapes ---------------------------------------------------------------------------------------------
def checked(result):
    """The reply normalised when it is exactly one of the skill shapes (skill + slots, calls, none, cancel), else None (the
    caller then reads it as an old ops / question / unsupported reply). Nothing is repaired."""
    if not isinstance(result, dict):
        return None
    keys = set(result)
    if keys == {"cancel"} and result["cancel"] is True:
        return result
    if keys in ({"skill", "slots"}, {"skill", "slots", "revises"}) and isinstance(result["skill"], str) \
            and isinstance(result["slots"], dict) and (result.get("revises") is None or isinstance(result.get("revises"), str)):
        return {"skill": result["skill"], "slots": result["slots"], "revises": result.get("revises")}
    if keys == {"skill", "summary"} and result["skill"] == "none" and isinstance(result["summary"], str):
        return result
    if keys in ({"calls"}, {"calls", "revises"}) and isinstance(result["calls"], list) and 1 <= len(result["calls"]) <= MAX_CALLS \
            and all(isinstance(c, dict) and set(c) == {"skill", "slots"} and isinstance(c["skill"], str)
                    and isinstance(c["slots"], dict) for c in result["calls"]) \
            and (result.get("revises") is None or isinstance(result.get("revises"), str)):
        return {"calls": result["calls"], "revises": result.get("revises")}
    return None


def is_skill_reply(result) -> bool:
    return isinstance(result, dict) and bool({"skill", "calls", "cancel"} & set(result))


def owned_op_families(registry) -> set:
    """Op families (``product``, ``hike`` ...) at least one active skill owns."""
    out = set()
    for skill in registry.active():
        out.update(GROUP_OPS.get(skill.group, ()))
    return out


def op_is_owned(op_name: str, registry) -> bool:
    return op_name.split(".", 1)[0] in owned_op_families(registry)


def _joined(req, msg) -> list:
    """The owner's texts of this request, oldest first, with this message last (an empty caption adds nothing)."""
    return [*(req["texts"] if req else []), *([msg.text] if msg.text and msg.text.strip() else [])]


def _earlier(texts, msg) -> list:
    """``texts`` without this message (the draft path adds it itself)."""
    return texts[:-1] if texts and msg.text and texts[-1] == msg.text else list(texts)


# -- slot validation ------------------------------------------------------------------------------------------
def _fold_words(text) -> set:
    return {nl_prep.stem(w) for w in re.findall(r"[a-z0-9]+", nl_prep.fold(text or ""))}


def traceable(value, texts) -> bool:
    """Owner words: every word of ``value`` is a word the owner said (stemmed, accents and case ignored)."""
    said = _fold_words(" ".join(texts))
    return all(w in said for w in _fold_words(value))


def _slot_limit(slot):
    if slot.limit:
        return content_model.TEXT_LIMITS.get(slot.limit[0], {}).get(slot.limit[1])
    return None


def _value_problem(slot, value):
    """None when ``value`` is the right JSON type and shape for a plain (not resolved) slot kind, else the owner-words reason."""
    k = slot.kind
    text_ok = lambda v: isinstance(v, str) and bool(v.strip()) and not HIDDEN.search(v) \
        and not any(bad in v for bad in content_model.FORBIDDEN_TEXT)  # noqa: E731
    if k in ("text", "url"):
        if not text_ok(value):
            return "that text has a character I can't use"
        cap = _slot_limit(slot)
        if cap is not None and len(value.strip()) > cap:
            return f"that is over {cap} characters"
    elif k == "text_list":
        if not (isinstance(value, list) and value and all(text_ok(v) for v in value)) or len(set(value)) != len(value):
            return "that list has an empty or repeated line"
    elif k == "id":
        if not (isinstance(value, str) and content_model.ID_RE.fullmatch(value)):
            return "that is not a name I can use"
    elif k == "date":
        if not (isinstance(value, str) and DATE_RE.fullmatch(value)):
            return "that date doesn't look right"
    elif k == "time":
        if not (isinstance(value, str) and TIME_RE.fullmatch(value)):
            return "that time doesn't look right"
    elif k == "bool":
        if not isinstance(value, bool):
            return "that should be yes or no"
    elif k == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return "that should be a number"
    elif k in ("enum", "maker_key", "image"):
        if not (isinstance(value, str) and value.strip()):
            return "that is empty"
    return None


class Filled:
    """The result of validating new slot values: what is kept, what needs an answer, what was left off."""

    def __init__(self):
        self.slots: dict = {}
        self.problem: str | None = None
        self.problem_slot: str | None = None
        self.ask: dict | None = None
        self.left_off: list = []
        self.refused: str | None = None


def validate(skill, current: dict, new: dict, texts, ctx, attachments=()) -> Filled:
    """Merge ``new`` (the model's values or a cheap answer) into ``current``. Valid values are kept and replace older ones;
    the first value that cannot be used is the one asked again (its plain-words reason and slot are returned) while every
    other valid value is still kept. Values for slots the skill does not have are ignored; an attachment is only ever
    one the owner sent in this request."""
    out = Filled()
    out.slots = dict(current)
    slots = {s.name: s for s in skill.slots}
    for name, value in (new or {}).items():
        slot = slots.get(name)
        if slot is None or value is None:
            continue
        if slot.kind == "attachment":
            if isinstance(value, str) and value in attachments:
                out.slots[name] = value
            continue
        if slot.kind in kinds.RESOLVERS:
            res = _resolve(slot, value, ctx)
            if res.status == "one":
                out.slots[name] = res.value
                continue
            if out.problem is None:  # the first slot that needs an answer is the one asked; the others are still kept
                out.problem, out.problem_slot = res.reply, name
                out.ask = {"slot": name, "ids": list(res.ids), "names": list(res.candidates)} if res.ids else None
                if res.status in ("held", "hidden"):
                    out.refused = res.reply
            continue
        problem = _value_problem(slot, value)
        if problem:
            if out.problem is None:
                out.problem, out.problem_slot = f"I can't use that for the {name.replace('_', ' ')}: {problem}.", name
            continue
        if slot.owner_words and not traceable(value if isinstance(value, str) else " ".join(value), texts):
            out.left_off.append(name)  # a fact the owner did not say: never written, never confirmed back to him
            out.slots.pop(name, None)
            continue
        out.slots[name] = value.strip() if isinstance(value, str) else value
    return out


def _resolve(slot, value, ctx):
    fn = kinds.RESOLVERS[slot.kind]
    if slot.kind == "attachment":
        return fn(value)
    if not isinstance(value, str) or not value.strip():
        return kinds.Resolved("invalid", reply=f"I can't use that for the {slot.name.replace('_', ' ')}.")
    if slot.kind in ("product_ref", "maker_ref"):
        return fn(ctx.content, value, ctx.aliases)
    if slot.kind in ("hike_ref", "route_ref"):
        return fn(ctx.content, value)
    if slot.kind == "day":
        return fn(value, ctx.today)
    return fn(value)


def _required(slot, slots) -> bool:
    req = slot.required
    if req is True:
        return True
    if isinstance(req, str) and req.startswith("if:"):
        return bool(slots.get(req[3:]))
    if isinstance(req, str) and req.startswith("unless:"):
        return not slots.get(req[7:])
    return False


def apply_defaults(skill, slots: dict, ctx) -> tuple:
    """(slots with defaults, ["name: value", ...] shown to the owner as "I set ..."). A default fills only an empty slot."""
    out, shown = dict(slots), []
    for slot in skill.slots:
        if slot.name in out or slot.default is None:
            continue
        if isinstance(slot.default, str) and slot.default.startswith("derive:"):
            fn = DERIVERS.get(slot.default[7:]) or getattr(sys.modules.get(getattr(skill.plan, "__module__", "")), slot.default[7:], None)
            if not callable(fn):
                continue
            value = fn(out, ctx)
        else:
            value = slot.default
        if value is not None:
            out[slot.name] = value
            shown.append(f"{slot.name.replace('_', ' ')}: {value}")
    return out, shown


def next_missing(skill, slots: dict):
    """The first required slot (in the skill's order) that has no value, else None."""
    return next((s for s in skill.slots if _required(s, slots) and s.kind != "attachment" and slots.get(s.name) in (None, "", [])), None) \
        or next((s for s in skill.slots if _required(s, slots) and s.kind == "attachment" and not slots.get(s.name)), None)


def question_for(slot, problem=None, ask=None) -> str:
    """The one short question: the resolver's own reply when it has one (it names the choices), else the slot's ``ask``."""
    if problem:
        return problem
    return slot.ask.replace("{candidates}", ", ".join((ask or {}).get("names", [])))


def candidates_of(router_result) -> list:
    """(name, score) pairs, best first, from whatever shape the router returns (see the module docstring)."""
    out = []
    for c in list(router_result or [])[:3]:
        if isinstance(c, (tuple, list)) and len(c) >= 2:
            out.append((c[0], c[1]))
        elif isinstance(c, dict):
            out.append((c.get("skill") or c.get("name"), c.get("score", 0)))
        else:
            out.append((getattr(c, "skill", None) or getattr(c, "name", None), getattr(c, "score", 0)))
    return [(n, s) for n, s in out if isinstance(n, str) and isinstance(s, (int, float))]


# -- the orchestrator -----------------------------------------------------------------------------------------
class Dispatcher:
    """One per Conversation. ``conv`` supplies the db, the editor and the draft path; nothing here is reachable by anyone but
    the owner, because ``Conversation._handle`` drops every other sender and chat before a request exists."""

    def __init__(self, conv, registry):
        self.conv, self.registry = conv, registry

    # context ------------------------------------------------------------------------------------------------
    def _ctx(self, now, texts):
        from hass import editor as editor_mod
        from hass.content_model import load_content, shop_today
        content = load_content(editor_mod._load(str(self.conv.sdir))[2] / "hass" / "content")
        return Ctx(content, shop_today(now), self.conv.aliases(), list(texts), now)

    def _owner(self):
        return self.conv.settings["ownerChat"]

    def photo_skills(self):
        return [s for s in self.registry.active() if any(sl.kind == "attachment" and sl.from_attachment for sl in s.slots)]

    # routing agreement (spec 2.5 step 3) -------------------------------------------------------------------
    def _agreement(self, text, req, skill_name, attachments):
        """None to accept the model's skill, or the one question that asks which task the owner means."""
        try:
            router = importlib.import_module("hass.skills.router")
            found = candidates_of(router.candidates(text, {}, req, bool(attachments)))
        except Exception:  # noqa: BLE001 - no router, or it failed: the model's skill stands (the owner approves any draft)
            return None
        if not found:
            return None
        names = [n for n, _ in found]
        best = found[0]
        pick = dict(found).get(skill_name)
        if skill_name not in names or (skill_name != best[0] and pick is not None and best[1] <= pick * 1.10):
            first = self.registry.get(skill_name)
            other = self.registry.get(best[0] if best[0] != skill_name else (names[1] if len(names) > 1 else ""))
            if first is None or other is None:
                return None
            return f"Do you want to {first.label}, or {other.label}?"
        return None

    # entry points --------------------------------------------------------------------------------------------
    def cheap(self, msg, now):
        """A short answer to the asked slot read by code alone (no model call). The disposition, or None to let the model read it."""
        req = self.conv.requests.get(self._owner(), now)
        if req is None or not req["skill"] or not req["asked_slot"]:
            return None
        skill = self.registry.get(req["skill"])
        slot = next((s for s in getattr(skill, "slots", ()) if s.name == req["asked_slot"]), None)
        try:
            ctx = self._ctx(now, [*req["texts"], msg.text])
            ok, value = openreq.cheap_answer(slot, msg.text, ask=req["ask"], content=ctx.content, aliases=ctx.aliases, today=ctx.today)
        except Exception:  # noqa: BLE001 - unreadable content: the model path (and its own errors) decides
            return None
        if not ok:
            return None
        return self._advance(msg, now, req, skill, {slot.name: value}, None, ctx=ctx, resolved=True)

    def reply(self, msg, now, result, req):
        """Handle a skill-shaped model reply. ``req`` is the owner's live request (or None). Returns the disposition."""
        owner = self._owner()
        if "cancel" in result:
            if req is not None:
                self.conv.requests.mark(req["request_id"], "cancelled", now)
            self.conv._reply(DROPPED)
            return "cancelled"
        if "calls" in result:
            return self._calls(msg, now, result, req)
        name = result["skill"]
        if name == "none":
            return self._backlog(msg, now, req, result.get("summary") or "", "other")
        skill = self.registry.get(name)
        if skill is None:
            return self._backlog(msg, now, req, "", "unknown-skill")
        same = req is not None and req["skill"] == name
        attachments = req["attachments"] if req else []
        if attachments and not any(sl.kind == "attachment" for sl in skill.slots):
            labels = ", ".join(s.label for s in self.photo_skills()) or "a product"
            self.conv._reply(PHOTO_MISMATCH.format(labels=labels))
            return "question"
        if not same:
            asked = self._agreement(msg.text, req, name, attachments)
            if asked:
                texts = _joined(req, msg)
                self.conv.requests.put(owner, msg.provider_id, now, texts=texts, skill=None, question=asked, attachments=attachments)
                self.conv._reply(asked)
                return "question"
        revises = result.get("revises") or (req["draft_code"] if same and req["state"] == "drafted" else None)
        return self._advance(msg, now, req if same else None, skill, result["slots"], revises, prior=None if same else req)

    # the common step: slots in -> question, refusal, backlog or draft ----------------------------------------
    def _advance(self, msg, now, req, skill, new_slots, revises, ctx=None, prior=None, resolved=False):
        conv, owner = self.conv, self._owner()
        base = prior or req  # the request whose texts and photo this one continues
        texts = _joined(base, msg)
        attachments = (base["attachments"] if base else [])
        ctx = ctx or self._ctx(now, texts)
        ctx.texts = texts
        slots = dict(req["slots"]) if req else {}
        if resolved:  # a cheap answer: already a checked value (an id the owner picked from our own list), not words to resolve
            filled = Filled()
            filled.slots = {**slots, **new_slots}
        else:
            filled = validate(skill, slots, new_slots, texts, ctx, attachments)
        slots = filled.slots
        for sl in skill.slots:  # the photo of this request fills its attachment slot: code decides, the model cannot
            if sl.kind == "attachment" and sl.from_attachment and attachments and not slots.get(sl.name):
                slots[sl.name] = attachments[-1]
        if filled.refused:
            conv.requests.put(owner, msg.provider_id, now, texts=texts, skill=skill.name, slots=slots, attachments=attachments,
                              request_id=req["request_id"] if req else None, question=filled.refused, asked_slot=None)
            conv._reply(filled.refused)
            return "refused"
        if filled.problem:
            return self._ask(msg, now, req, skill, slots, texts, attachments, skill_slot=filled.problem_slot,
                             problem=filled.problem, ask=filled.ask, revises=revises)
        slots, defaults = apply_defaults(skill, slots, ctx)
        slot = next_missing(skill, slots)
        if slot is not None:
            return self._ask(msg, now, req, skill, slots, texts, attachments, skill_slot=slot.name, problem=None, ask=None, revises=revises)
        for rule in skill.rules:
            hit = RULES.get(rule, lambda *a: None)(slots, texts, ctx)
            if hit:
                return self._backlog(msg, now, req, "", hit[1], reply=hit[0], texts=texts)
        if skill.approval == "none":
            return self._read_only(msg, now, req, skill, slots, ctx, texts)
        try:
            ops = skill.plan(dict(slots), ctx)
        except Exception:  # noqa: BLE001 - a plan must not raise; if one does, nothing is drafted
            conv.requests.mark(req["request_id"], "closed", now) if req else None
            conv._reply(PLAN_FAILED)
            return "not-drafted"
        if not isinstance(ops, list) or not ops or not all(isinstance(o, dict) and set(o) == {"op", "args"} for o in ops):
            conv.requests.mark(req["request_id"], "closed", now) if req else None
            conv._reply(PLAN_FAILED)
            return "not-drafted"
        if len(ops) > MAX_OPS:
            conv._reply(TOO_MANY.format(limit=MAX_OPS, count=len(ops)))
            return "question"
        return self._draft(msg, now, req, skill, slots, texts, attachments, ops, revises, defaults, filled.left_off)

    def _ask(self, msg, now, req, skill, slots, texts, attachments, *, skill_slot, problem, ask, revises):
        """Ask the one question for ``skill_slot`` and keep the request. A slot asked three times and still open closes it."""
        conv, owner = self.conv, self._owner()
        slot = next(s for s in skill.slots if s.name == skill_slot)
        asks = (req["asks"] + 1) if req and req["asked_slot"] == skill_slot else 1
        if asks > openreq.MAX_UNRESOLVED:
            example = next((t.text for t in skill.triggers if getattr(t, "tag", "") == "clean"), skill.triggers[0].text)
            if req:
                conv.requests.mark(req["request_id"], "closed", now)
            return self._backlog(msg, now, None, "", "stuck", reply=STUCK.format(example=example), texts=texts)
        question = question_for(slot, problem, ask)
        conv.requests.put(owner, msg.provider_id, now, texts=texts, request_id=req["request_id"] if req else None,
                          skill=skill.name, slots=slots, asked_slot=skill_slot, question=question, ask=ask,
                          attachments=attachments, asks=asks, calls=req["calls"] if req else [],
                          draft_code=(req["draft_code"] if req else None))
        conv._reply(question)
        return "question"

    def _draft(self, msg, now, req, skill, slots, texts, attachments, ops, revises, defaults, left_off, queued=()):
        """Hand the plan to the conversation's ordinary draft path (editor.prepare, claims over the JOINED texts, proposal)."""
        conv, owner = self.conv, self._owner()
        earlier = _earlier(texts, msg)
        note = []
        if defaults:
            note.append("I set: " + "; ".join(defaults) + ".")
        if left_off:
            note.append("Left off (you didn't say it): " + ", ".join(n.replace("_", " ") for n in left_off) + ".")
        disposition = conv._draft(msg, now, {"ops": ops, "revises": revises}, earlier, prefix="\n".join(note) + "\n" if note else "", legacy=False)
        rid = req["request_id"] if req else None
        code = conv._last_draft_code
        live = conv.requests.get(owner, now)
        if live is not None and live["pending"]:
            return disposition  # the shelf-check question took the open request over (Conversation._ask_shelf)
        if disposition == "proposed":
            rid = conv.requests.put(owner, msg.provider_id, now, texts=texts, request_id=rid, state="drafted", skill=skill.name,
                                    slots=slots, attachments=attachments, draft_code=code, calls=list(queued))
        elif disposition in ("needs-details", "claim-question", "question"):
            rid = conv.requests.put(owner, msg.provider_id, now, texts=texts, request_id=rid, skill=skill.name, slots=slots,
                                    question=conv._said, attachments=attachments, draft_code=code if disposition == "needs-details" else None,
                                    calls=list(queued))
        elif req is not None:
            conv.requests.mark(req["request_id"], "closed", now)
        return disposition

    # several asks in one message ------------------------------------------------------------------------------
    def _calls(self, msg, now, result, req):
        conv, owner = self.conv, self._owner()
        texts = _joined(req, msg)
        attachments = req["attachments"] if req else []
        ctx = self._ctx(now, texts)
        ops, defaults, left, waiting = [], [], [], []
        for call in result["calls"]:
            skill = self.registry.get(call["skill"])
            if skill is None or skill.approval == "none" or skill.name == "backlog.log":
                return self._backlog(msg, now, req, "", "unknown-skill")
            filled = validate(skill, {}, call["slots"], texts, ctx, attachments)
            slots = filled.slots
            for sl in skill.slots:
                if sl.kind == "attachment" and sl.from_attachment and attachments and not slots.get(sl.name):
                    slots[sl.name] = attachments[-1]
            slots, shown = apply_defaults(skill, slots, ctx)
            missing = None if filled.problem else next_missing(skill, slots)
            if filled.problem or filled.refused or missing is not None or any(
                    RULES.get(r, lambda *a: None)(slots, texts, ctx) for r in skill.rules):
                waiting.append({"skill": skill.name, "slots": slots, "problem": filled.problem, "ask": filled.ask,
                                "slot": filled.problem_slot})
                continue
            try:
                planned = skill.plan(dict(slots), ctx)
            except Exception:  # noqa: BLE001
                waiting.append({"skill": skill.name, "slots": slots, "problem": None, "ask": None, "slot": None})
                continue
            ops += planned if isinstance(planned, list) else []
            defaults += shown
            left += filled.left_off
        if len(ops) > MAX_OPS:
            conv._reply(TOO_MANY.format(limit=MAX_OPS, count=len(ops)))
            return "question"
        if not ops:
            if not waiting:
                conv._reply(PLAN_FAILED)
                return "not-drafted"
            return self._queue_only(msg, now, req, waiting[0], waiting[1:], texts, attachments, ctx)
        disposition = conv._draft(msg, now, {"ops": ops, "revises": result.get("revises")}, _earlier(texts, msg),
                                  prefix=("I set: " + "; ".join(defaults) + ".\n") if defaults else "", legacy=False)
        live = conv.requests.get(owner, now)
        if live is not None and live["pending"]:
            return disposition  # the shelf-check question took the open request over
        if disposition != "proposed" or not waiting:
            if req is not None:
                conv.requests.mark(req["request_id"], "closed", now)
            return disposition
        first, rest = waiting[0], waiting[1:]
        # the complete calls are drafted; the first incomplete one is asked next, one question at a time
        self._queue_only(msg, now, req, first, rest, texts, attachments, ctx)
        return disposition

    def _queue_only(self, msg, now, req, first, rest, texts, attachments, ctx):
        """Make ``first`` (an incomplete call, its slots already checked) the open request, keep ``rest`` queued, ask its question."""
        conv = self.conv
        skill = self.registry.get(first["skill"])
        slot = next((s for s in skill.slots if s.name == first.get("slot")), None) or next_missing(skill, first["slots"])
        question = question_for(slot, first.get("problem"), first.get("ask")) if slot else None
        conv.requests.put(self._owner(), msg.provider_id, now, texts=texts, request_id=req["request_id"] if req else None,
                          skill=skill.name, slots=first["slots"], calls=rest, attachments=attachments,
                          asked_slot=slot.name if slot else None, question=question, ask=first.get("ask"), asks=1)
        conv._reply(question or NOT_SURE)
        return "question"

    # nothing to draft ------------------------------------------------------------------------------------------
    def _read_only(self, msg, now, req, skill, slots, ctx, texts):
        if skill.name == "page.faq":
            from hass.skills.backlog import NO_FAQ
            return self._backlog(msg, now, req, "", "unsupported-page", reply=NO_FAQ, texts=texts)
        if skill.name == "backlog.log":
            return self._backlog(msg, now, req, slots.get("summary", ""), slots.get("reason") if slots.get("reason") in (
                "unknown-skill", "policy", "unsupported-page", "stuck", "price", "other") else "other", texts=texts)
        fn = READ_ONLY.get(skill.name)
        if fn is None:
            return self._backlog(msg, now, req, "", "other", texts=texts)
        if req:
            self.conv.requests.mark(req["request_id"], "closed", now)
        self.conv._reply(fn(slots, ctx))
        return "answer"

    def _backlog(self, msg, now, req, summary, reason, reply=None, texts=None):
        """Write the request down (the catch-all), say so in plain words, change nothing, close the open request."""
        from hass.skills.backlog import Backlog
        conv = self.conv
        n = Backlog(conv.db, conv._now).record(reason, summary, "\n".join(texts) if texts else msg.text)
        if req is not None:
            conv.requests.mark(req["request_id"], "closed", now)
        else:
            conv.requests.close_live(self._owner(), now, "closed")
        base = NO_SKILL_SAID.format(n=n)
        conv._reply((reply + " " + base) if reply else base)
        return "backlog"

    # a photo (spec 2.7) --------------------------------------------------------------------------------------
    def photo(self, msg, now, sha, caption):
        """The stored original joins the owner's request. Returns a disposition, or None when the caption should now be read
        as an ordinary text of that request (``Conversation._request``)."""
        conv = self.conv
        how, req = conv.requests.bind_attachment(self._owner(), msg.provider_id, sha, now, self.registry)
        if how == "filled":
            if caption:
                return None  # the caption may say more (a name, a description): the model reads it with this request
            skill = self.registry.get(req["skill"])
            return self._advance(msg, now, req, skill, {}, None)
        if caption:
            return None
        labels = ", ".join(s.label for s in self.photo_skills())
        conv.requests.put(self._owner(), msg.provider_id, now, texts=req["texts"] if req else [], request_id=req["request_id"],
                          skill=req["skill"], slots=req["slots"], attachments=req["attachments"],
                          question=PHOTO_FOR.format(labels=labels), asked_slot=req["asked_slot"], ask=req["ask"], asks=req["asks"])
        conv._reply(PHOTO_FOR.format(labels=labels))
        return "photo-question"
