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
  * ``hass.skills.router.candidates(text, hints, open_request, attachment, skills)`` returns up to 3 candidates, best first, each a
    ``(name, score)`` pair, a dict with ``skill``/``name`` and ``score``, or an object with ``.skill``/``.name`` and ``.score``.
    If the module is missing, or raises, agreement cannot be established (spec 2.5): nothing is drafted and the owner is asked
    which task he means; the answer he then gives stands.
  * The interpreter receives the continue-mode snapshot through its existing ``recent`` argument (keys ``question``,
    ``earlier``, plus ``skill``, ``slots``, ``asked_slot``, ``draft``); the Skills section of its prompt is FW-2's.
  * ``hass.interpret_check.check_skill`` is NOT needed: this module validates the reply shape and every slot itself.

Optional hooks a skill's module may define (found in the module that defines the skill's ``plan``; each is fail-safe):
  * ``question(slot name, slots, ctx) -> str|None``: the skill's own wording of the one question for a missing slot (it can name the
    product or offer a saved maker); ``None`` or an error keeps the slot's static ``ask``.
  * a plan error with ``.reply`` (and ``.kind`` "question" | "refuse", ``.backlog`` a backlog reason or None) is said to the owner as it
    is: a question keeps the open request, so his short answer continues it; a refusal closes it. No ``.reply``: PLAN_FAILED.
  * ``notes(skill name, slots, ctx) -> {"say": [...], "set": [...], "warn": [...]}``: lines shown beside the draft, before the owner's yes.
  * ``ctx.media_root`` (the ``mediaRoot`` setting) and ``ctx.house_render`` (the ``houseRender`` setting) for a photo check.
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
BACKLOG_REASONS = ("unknown-skill", "policy", "unsupported-page", "stuck", "price", "other")  # the reasons a refusal may name (see _read_only)
NEAR_TIE = 0.10  # the router's top two within 10%: the owner is asked (same figure as hass/skills/router.py)

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
#   SET_PHRASES[skill name](slots as the owner gave them, ctx) -> the plain phrases for "I set: ..." (D8); a skill without one gets "name: value"
RULES: dict = {}
DERIVERS: dict = {}
SET_PHRASES: dict = {}
READ_ONLY: dict = {}
READ_ONLY_LONG: set = set()  # read-only skills whose answer may run long (a full caption to copy); every other check still applies
MIXED = "I write captions and make changes in separate messages. Send the change on its own. Nothing changed."


def _no_price(slots, texts, ctx):
    return (PRICE, "price") if MONEY.search("\n".join(texts)) else None


RULES.setdefault("no-price", _no_price)


class Ctx:
    """What a skill's ``plan`` and rules may read: the saved content (read-only), today (Pacific), aliases, the owner's texts."""

    def __init__(self, content, today, aliases, texts, now, media_root=None, house_render=False, site_dir=None, *, guest_counts_db=None):
        self.content, self.today, self.aliases, self.texts, self.now = content, today, aliases, texts, now
        self.media_root, self.house_render = media_root, house_render  # the stored originals (for a photo check) and the houseRender setting
        self.guest_counts_db = guest_counts_db
        self.multi_call = False  # True while the owner's texts are shared by several calls of one message (a skill cannot tie a loose word to one call)
        self.site_dir = site_dir  # the writer's storefront-mockup folder (the same checkout the content was read from), or None


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


NEGATORS = frozenset("not no never none nothing nobody neither nor without cannot cant wont dont doesnt didnt isnt arent wasnt werent "
                     "hasnt havent hadnt wouldnt shouldnt couldnt aint".split())
CLAUSE_SPLIT = re.compile(r"[.,;:!?()\n]+|\b(?:but|and|though|although|however|instead|actually)\b")
NEGATION_WINDOW = 3  # a negator up to three words before a word denies it ("is not easy", "not too easy", "never really hard")
_FILLER_STEMS = frozenset(nl_prep.stem(w) for w in nl_prep.NAME_STOP)  # "meet at the gate, not the lot" still says "the"


def _stem_clauses(text) -> list:
    """A text as (stemmed word, denied) pairs in order: ``denied`` is true when a negator stands up to NEGATION_WINDOW words
    before the word inside its clause. Words are cut exactly as ``_fold_words`` cuts them."""
    out = []
    for clause in CLAUSE_SPLIT.split(re.sub(r"n['\u2019]t\b", " not", nl_prep.fold(text or ""))):
        words = re.findall(r"[a-z0-9]+", clause)
        for i, w in enumerate(words):
            out.append((nl_prep.stem(w), any(p in NEGATORS for p in words[max(0, i - NEGATION_WINDOW):i])))
    return out


def traceable(value, texts) -> bool:
    """Owner words: every word of ``value`` is a word the owner said (stemmed, accents and case ignored) and the owner's LAST
    mention of it did not deny it ("the hike is not easy" never makes ``easy`` a fact; a later "it is easy after all" does)."""
    last = {}
    for text in texts:  # oldest first: the newest mention of a word decides
        for stem, denied in _stem_clauses(text):
            last[stem] = denied
    return all(w in last if w in _FILLER_STEMS else last.get(w) is False for w in _fold_words(value))


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
    elif k == "stock_items":  # RF0814-12: shape only; repeats, the six-product cap and every stock rule stay in the plan
        if not (isinstance(value, list) and value and all(
                isinstance(v, dict) and set(v) == {"product", "availability"}
                and isinstance(v["product"], str) and content_model.ID_RE.fullmatch(v["product"])
                and isinstance(v["availability"], str) and v["availability"] in content_model.AVAILABILITY for v in value)):
            return "each one needs a product and in stock, low or sold out"
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
        self.refused_status: str | None = None  # the resolver's "held" or "hidden" behind ``refused``


def drop_denied(skill, slots: dict, keep, texts) -> list:
    """Owner-word slots already held (not among ``keep``, the names just given) are read again against the owner's texts as
    they stand now: one he has since denied ("it is not easy") is removed, so it is asked again or left off. Returns the names."""
    gone = []
    for sl in skill.slots:
        v = slots.get(sl.name)
        if sl.owner_words and sl.name not in keep and v not in (None, "", []) and not traceable(
                v if isinstance(v, str) else " ".join(v) if isinstance(v, list) else str(v), texts):
            slots.pop(sl.name)
            gone.append(sl.name)
    return gone


def validate(skill, current: dict, new: dict, texts, ctx, attachments=()) -> Filled:
    """Merge ``new`` (the model's values or a cheap answer) into ``current``. Valid values are kept and replace older ones;
    the first value that cannot be used is the one asked again (its plain-words reason and slot are returned) while every
    other valid value is still kept. Values for slots the skill does not have are ignored; an attachment is only ever
    one the owner sent in this request."""
    out = Filled()
    out.slots = dict(current)
    replaced: set = set()  # names given a new value that passed every check: only these skip the re-read of held facts
    slots = {s.name: s for s in skill.slots}
    for name, value in (new or {}).items():
        slot = slots.get(name)
        if slot is None or value is None:
            continue
        if slot.kind == "attachment":
            if isinstance(value, str) and value in attachments:
                out.slots[name] = value
                replaced.add(name)
            continue
        if slot.kind in kinds.RESOLVERS:
            res = _resolve(slot, value, ctx, include_hidden=skill.name == "item.restore")
            if res.status == "one":
                out.slots[name] = res.value
                replaced.add(name)
                continue
            if out.problem is None:  # the first slot that needs an answer is the one asked; the others are still kept
                out.problem, out.problem_slot = res.reply, name
                out.ask = {"slot": name, "ids": list(res.ids), "names": list(res.candidates)} if res.ids else None
                if res.status in ("held", "hidden"):
                    out.refused, out.refused_status = res.reply, res.status
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
        replaced.add(name)
    out.left_off += [n for n in drop_denied(skill, out.slots, replaced, texts) if n not in out.left_off]
    return out


def _resolve(slot, value, ctx, *, include_hidden=False):
    fn = kinds.RESOLVERS[slot.kind]
    if slot.kind == "attachment":
        return fn(value)
    if not isinstance(value, str) or not value.strip():
        return kinds.Resolved("invalid", reply=f"I can't use that for the {slot.name.replace('_', ' ')}.")
    if slot.kind == "product_ref" and include_hidden:
        return fn(ctx.content, value, ctx.aliases, include_hidden=True)
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
    out, shown, given = dict(slots), [], dict(slots)
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
    words = SET_PHRASES.get(skill.name) or getattr(sys.modules.get(getattr(skill.plan, "__module__", "")), "SET_PHRASES", {}).get(skill.name)
    if shown and callable(words):  # the skill words its own defaults (D8: "sign-up off", not "signup: False")
        shown = [p for p in (words(given, ctx) or []) if p]  # the skill decides what is worth saying, as the kit does
    return out, shown


def next_missing(skill, slots: dict):
    """The first required slot (in the skill's order) that has no value, else None."""
    return next((s for s in skill.slots if _required(s, slots) and s.kind != "attachment" and slots.get(s.name) in (None, "", [])), None) \
        or next((s for s in skill.slots if _required(s, slots) and s.kind == "attachment" and not slots.get(s.name)), None)


def skill_hook(skill, name):
    """A function the skill's own module offers by name (``question``, ``notes``), else None. The module is the one that defines
    the skill's ``plan``, the same lookup ``apply_defaults`` uses for ``derive:`` functions."""
    fn = getattr(sys.modules.get(getattr(getattr(skill, "plan", None), "__module__", "")), name, None)
    return fn if callable(fn) else None


def question_for(slot, problem=None, ask=None, *, skill=None, slots=None, ctx=None) -> str:
    """The one short question: the resolver's own reply when it has one (it names the choices), else the skill's own wording
    (``question(slot name, slots, ctx)``: it may name the product or offer a saved maker), else the slot's ``ask``."""
    if problem:
        return problem
    hook = skill_hook(skill, "question") if skill is not None else None
    if hook is not None:
        try:
            said = hook(slot.name, dict(slots or {}), ctx)
        except Exception:  # noqa: BLE001 - the skill's wording is a convenience: the static ask still stands
            said = None
        if isinstance(said, str) and said.strip():
            return said.strip()
    text = (slot.ask or "").replace("{candidates}", ", ".join((ask or {}).get("names", []))).strip()
    if text:
        return text
    return "Send me the photo." if (slot.from_attachment or slot.kind == "attachment") else "I need one more detail to go on. What is the " + slot.name.replace("_", " ") + "?"


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
        writer = editor_mod._load(str(self.conv.sdir))[2]
        content = load_content(writer / "hass" / "content")
        settings = getattr(self.conv, "settings", None) or {}
        return Ctx(content, shop_today(now), self.conv.aliases(), list(texts), now, media_root=settings.get("mediaRoot"),
                   house_render=settings.get("houseRender") is True, site_dir=writer / "storefront-mockup", guest_counts_db=settings.get("guestCountsDb"))

    def _owner(self):
        return self.conv._chat()  # the answering chat, so each owner has their own open request (HASS-LIVE-PLAN-1)

    def photo_skills(self):
        return [s for s in self.registry.active() if any(sl.kind == "attachment" and sl.from_attachment for sl in s.slots)]

    # routing agreement (spec 2.5 step 3) -------------------------------------------------------------------
    def _hints(self, texts, now):
        """The nl_prep hints the router scores with; never raises (a hint is a convenience)."""
        try:
            text = " ".join(texts)
            ctx = self._ctx(now, texts)
            return nl_prep.make_hinter(ctx.content)(text, ctx.today, self.conv.aliases())
        except Exception:  # noqa: BLE001
            return {}

    def _router_names(self, texts, req, attachments, now):
        """The router's top three skill names, best first, as ``[(name, score)]``; None when the router is missing or fails."""
        try:
            router = importlib.import_module("hass.skills.router")
            return candidates_of(router.candidates(" ".join(texts), self._hints(texts, now), req, bool(attachments), self.registry))
        except Exception:  # noqa: BLE001 - agreement cannot be established; the caller asks instead of guessing
            return None

    def _agreement(self, texts, req, picks, attachments, now, has_slots=True):
        """None to accept the model's skill(s) ``picks``, else ``(question, offered names)``: the one question that asks which task
        the owner means. Nothing is drafted on a pick the code cannot back: the router missing or failing, a pick outside its
        top three, a split between the leading two, or no second opinion and nothing filled in. When the owner already chose
        among the names we offered, the pick he then makes stands."""
        if req is not None and not req["skill"] and set(picks) <= set((req["ask"] or {}).get("agree") or ()):
            return None
        found = self._router_names(texts, req, attachments, now)
        names = [n for n, _ in found or []]
        if found is None or (not found and not has_slots):
            offered = list(dict.fromkeys(picks))
        elif not found:
            return None
        else:
            best, near = found[0], len(found) > 1 and found[0][1] - found[1][1] <= NEAR_TIE * found[0][1]
            if any(p not in names for p in picks):
                offered = list(dict.fromkeys([*picks, best[0]]))[:3]
            elif near and not {found[0][0], found[1][0]} <= set(picks):
                leaders = [found[0][0], found[1][0]]
                offered = list(dict.fromkeys([picks[0], *leaders])) if len(picks) == 1 and picks[0] in leaders else leaders
            elif len(picks) == 1 and picks[0] != best[0] and best[1] - dict(found)[picks[0]] <= NEAR_TIE * best[1]:
                offered = [picks[0], best[0]]
            else:
                return None
        labels = list(dict.fromkeys(self.registry.get(n).label for n in offered if self.registry.get(n) is not None))
        if not labels:
            return NOT_SURE, []
        return "Do you want to " + ", or ".join(labels) + "?", offered

    # entry points --------------------------------------------------------------------------------------------
    def _explicit_page(self, msg) -> bool:
        from hass.skills.backlog import explicit_page_request
        return self.registry.get("page.faq") is not None and explicit_page_request(msg.text)

    def cheap(self, msg, now):
        """A short answer to the asked slot read by code alone (no model call). The disposition, or None to let the model read it."""
        req = self.conv.requests.get(self._owner(), now)
        if req is None and self._explicit_page(msg):  # RF2345-12: an unmistakable fresh FAQ-page ask is refused by code, no model
            from hass.skills.backlog import NO_FAQ
            return self._backlog(msg, now, None, "", "unsupported-page", reply=NO_FAQ, texts=[msg.text],
                                 skill=self.registry.get("page.faq") or "page.faq")
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
            if req is not None:  # AVB-10: the owner dropped his open request before any draft
                self._logged(msg, "refused", "said-no", self.registry.get(req["skill"]) if req["skill"] else None)
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
            asked = self._agreement(_joined(req, msg), req, [name], attachments, now,
                                    has_slots=any(v not in (None, "", []) for v in result["slots"].values()))
            if asked:
                return self._ask_which(msg, now, req, asked, attachments)
        revises = result.get("revises") or (req["draft_code"] if same and req["state"] == "drafted" else None)
        return self._advance(msg, now, req if same else None, skill, result["slots"], revises, prior=None if same else req)

    def _ask_which(self, msg, now, req, asked, attachments):
        """Nothing is drafted: the owner is asked which task he means. The names offered are kept on the request, so the pick he
        then makes (the model's next reply) is the owner's own choice and stands."""
        question, offered = asked
        self.conv.requests.put(self._owner(), msg.provider_id, now, texts=_joined(req, msg), skill=None, question=question,
                               ask={"agree": offered} if offered else None, attachments=attachments)
        self.conv._reply(question)
        return "question"

    # the common step: slots in -> question, refusal, backlog or draft ----------------------------------------
    def _advance(self, msg, now, req, skill, new_slots, revises, ctx=None, prior=None, resolved=False):
        conv, owner = self.conv, self._owner()
        base = prior or req  # the request whose texts and photo this one continues
        texts = _joined(base, msg)
        attachments = (base["attachments"] if base else [])
        ctx = ctx or self._ctx(now, texts)
        ctx.texts = texts
        ctx.multi_call = ctx.multi_call or bool(req and req["calls"])  # a queued call of a several-ask message shares its texts
        said = self._read_only_hook(skill, "preflight", ctx)  # a caption skill: an ask to post, send or schedule is answered first
        if said:
            conv.requests.mark(req["request_id"], "closed", now) if req else None
            conv._reply(said)
            self._logged(msg, "refused", "policy", skill)  # AVB-10: an ask to post, send or schedule
            return "refused"
        slots = dict(req["slots"]) if req else {}
        if resolved:  # a cheap answer: already a checked value (an id the owner picked from our own list), not words to resolve
            filled = Filled()
            filled.slots = {**slots, **new_slots}
            filled.left_off = drop_denied(skill, filled.slots, set(new_slots), texts)
        else:
            filled = validate(skill, slots, new_slots, texts, ctx, attachments)
        slots = filled.slots
        for sl in skill.slots:  # the photo of this request fills its attachment slot: code decides, the model cannot
            if sl.kind == "attachment" and sl.from_attachment and attachments and not slots.get(sl.name):
                slots[sl.name] = attachments[-1]
        if filled.refused:
            said = self._read_only_hook(skill, "refusal", ctx, filled.problem_slot, filled.refused_status)
            if said:  # a read-only answer about a held or hidden record: said in its own words, nothing left open
                conv.requests.mark(req["request_id"], "closed", now) if req else None
                conv._reply(said)
                self._logged(msg, "refused", "refused", skill)  # AVB-10
                if req and req["calls"]:  # this ask is refused; the owner's other caption asks of the same message are not
                    return self._next_queued(msg, now, None, req["calls"], texts, attachments, "refused")
                return "refused"
            conv.requests.put(owner, msg.provider_id, now, texts=texts, skill=skill.name, slots=slots, attachments=attachments,
                              request_id=req["request_id"] if req else None, question=filled.refused, asked_slot=None)
            conv._reply(filled.refused)
            self._logged(msg, "refused", "refused", skill)  # AVB-10: a held or hidden record; the request stays open
            return "refused"
        if filled.problem:
            return self._ask(msg, now, req, skill, slots, texts, attachments, skill_slot=filled.problem_slot,
                             problem=filled.problem, ask=filled.ask, revises=revises)
        given = slots  # what the owner gave: a default the skill picks is not kept across a question, so it is still said as "I set" when he answers
        slots, defaults = apply_defaults(skill, slots, ctx)
        slot = next_missing(skill, slots)
        if slot is not None:
            return self._ask(msg, now, req, skill, given, texts, attachments, skill_slot=slot.name, problem=None, ask=None, revises=revises,
                             shown=slots, ctx=ctx)
        for rule in skill.rules:
            hit = RULES.get(rule, lambda *a: None)(slots, texts, ctx)
            if hit:
                return self._backlog(msg, now, req, "", hit[1], reply=hit[0], texts=texts, skill=skill)
        if skill.approval == "none":
            return self._read_only(msg, now, req, skill, slots, ctx, texts)
        try:
            ops = skill.plan(dict(slots), ctx)
        except Exception as exc:  # noqa: BLE001 - a plan must not raise; a Refusal (a sentence of the skill's own) is said, any other error is not
            return self._plan_stopped(msg, now, req, skill, given, texts, attachments, exc, revises)
        if not isinstance(ops, list) or not ops or not all(isinstance(o, dict) and set(o) == {"op", "args"} for o in ops):
            conv.requests.mark(req["request_id"], "closed", now) if req else None
            conv._reply(PLAN_FAILED)
            self._logged(msg, "refused", "failed", skill)  # AVB-10
            return "not-drafted"
        if len(ops) > MAX_OPS:
            conv._reply(TOO_MANY.format(limit=MAX_OPS, count=len(ops)))
            self._logged(msg, "refused", "cap", skill)  # AVB-10
            return "question"
        return self._draft(msg, now, req, skill, slots, texts, attachments, ops, revises, defaults, filled.left_off,
                           queued=req["calls"] if req else ())

    def _plan_stopped(self, msg, now, req, skill, given, texts, attachments, exc, revises):
        """A plan raised. A skill's own refusal (``exc.reply`` is a sentence for the owner, ``exc.kind`` is ``question`` when one
        answer fixes it, ``exc.backlog`` a backlog reason) is said as it is: a question keeps the request open with what he has given
        so far, so his short answer continues it; anything else closes it. An error with no such sentence is the generic failure."""
        conv, owner = self.conv, self._owner()
        reply = getattr(exc, "reply", None)
        if not (isinstance(reply, str) and reply.strip()):
            conv.requests.mark(req["request_id"], "closed", now) if req else None
            conv._reply(PLAN_FAILED)
            self._logged(msg, "refused", "failed", skill)  # AVB-10
            return "not-drafted"
        reply = reply.strip()
        if getattr(exc, "backlog", None) in BACKLOG_REASONS:
            return self._backlog(msg, now, req, "", exc.backlog, reply=reply, texts=texts, skill=skill)
        if getattr(exc, "kind", None) == "question":
            asks = (req["asks"] + 1) if req and req["asked_slot"] is None and req["question"] == reply else 1
            if asks > openreq.MAX_UNRESOLVED:  # the same question three times: give up, as for a slot
                example = next((t.text for t in skill.triggers if getattr(t, "tag", "") == "clean"), skill.triggers[0].text)
                conv.requests.mark(req["request_id"], "closed", now)
                return self._backlog(msg, now, None, "", "stuck", reply=STUCK.format(example=example), texts=texts, skill=skill)
            conv.requests.put(owner, msg.provider_id, now, texts=texts, request_id=req["request_id"] if req else None, skill=skill.name,
                              slots=given, asked_slot=None, question=reply, attachments=attachments, asks=asks,
                              calls=req["calls"] if req else [], draft_code=(req["draft_code"] if req else None))
            conv._reply(reply)
            return "question"
        conv.requests.mark(req["request_id"], "closed", now) if req else None
        conv._reply(reply)
        self._logged(msg, "refused", "refused", skill)  # AVB-10: the skill's own refusal
        return "refused"

    def _ask(self, msg, now, req, skill, slots, texts, attachments, *, skill_slot, problem, ask, revises, shown=None, ctx=None):
        """Ask the one question for ``skill_slot`` and keep the request. A slot asked three times and still open closes it."""
        conv, owner = self.conv, self._owner()
        slot = next(s for s in skill.slots if s.name == skill_slot)
        asks = (req["asks"] + 1) if req and req["asked_slot"] == skill_slot else 1
        if asks > openreq.MAX_UNRESOLVED:
            example = next((t.text for t in skill.triggers if getattr(t, "tag", "") == "clean"), skill.triggers[0].text)
            if req:
                conv.requests.mark(req["request_id"], "closed", now)
            stuck = self._backlog(msg, now, None, "", "stuck", reply=STUCK.format(example=example), texts=texts, skill=skill)
            queued = [c for c in (req["calls"] if req else []) if self.registry.get(c.get("skill")) is not None]
            if queued:  # this ask is given up; the owner's other asks are not
                self._queue_only(msg, now, None, queued[0], queued[1:], texts, attachments, None)
            return stuck
        question = question_for(slot, problem, ask, skill=skill, slots=shown if shown is not None else slots,
                                ctx=ctx if ctx is not None else (self._ctx(now, texts) if skill_hook(skill, "question") else None))
        conv.requests.put(owner, msg.provider_id, now, texts=texts, request_id=req["request_id"] if req else None,
                          skill=skill.name, slots=slots, asked_slot=skill_slot, question=question, ask=ask,
                          attachments=attachments, asks=asks, calls=req["calls"] if req else [],
                          draft_code=(req["draft_code"] if req else None))
        conv._reply(question)
        return "question"

    def _skill_notes(self, skill, slots, now, texts) -> dict:
        """``notes(skill name, slots, ctx)`` of the skill's module -> ``{say, set, warn}`` lines shown beside the draft (before the
        owner's yes). Missing, failing or malformed: no lines (the draft is then shown as before). Each line once, plain strings only."""
        out = {"say": [], "set": [], "warn": []}
        hook = skill_hook(skill, "notes")
        if hook is None:
            return out
        try:
            got = hook(skill.name, dict(slots), self._ctx(now, texts))
        except Exception:  # noqa: BLE001 - a note is advice, never a reason to lose the draft
            return out
        for key in out:
            lines = got.get(key) if isinstance(got, dict) else None
            out[key] = list(dict.fromkeys(line.strip() for line in (lines if isinstance(lines, (list, tuple)) else ())
                                          if isinstance(line, str) and line.strip()))
        return out

    @staticmethod
    def _note_lines(parts, left_off=()) -> list:
        """The lines shown beside a proposal. ``parts`` is one ``(skill notes, defaults it picked)`` per call drafted: what the skills
        said, then one ``I set:`` line (the defaults, or else the skill's own set lines), what was left off, then the warnings."""
        say = [line for hooked, _ in parts for line in hooked["say"]]
        defaults = [d for _, shown in parts for d in shown]
        sets = [line for hooked, shown in parts if not shown for line in hooked["set"]]
        warn = [line for hooked, _ in parts for line in hooked["warn"]]
        note = list(dict.fromkeys(say))
        if defaults:
            note.append("I set: " + "; ".join(defaults) + ".")
        note += list(dict.fromkeys(sets))
        if left_off:
            note.append("Left off (you didn't say it): " + ", ".join(n.replace("_", " ") for n in left_off) + ".")
        note += list(dict.fromkeys(warn))
        return note

    def _draft(self, msg, now, req, skill, slots, texts, attachments, ops, revises, defaults, left_off, queued=()):
        """Hand the plan to the conversation's ordinary draft path (editor.prepare, claims over the JOINED texts, proposal)."""
        conv, owner = self.conv, self._owner()
        earlier = _earlier(texts, msg)
        hooked = self._skill_notes(skill, slots, now, texts)  # the skill's own lines: what it said and did, and what to know before yes
        note = self._note_lines([(hooked, defaults)], left_off)
        conv._skill_ref = f"{skill.name}@{skill.version}"  # AVB-10: the audit line names the skill that planned this draft
        try: disposition = conv._draft(msg, now, {"ops": ops, "revises": revises}, earlier, prefix="\n".join(note) + "\n" if note else "", legacy=False)
        finally: conv._skill_ref = None
        rid = req["request_id"] if req else None
        code = conv._last_draft_code
        live = conv.requests.get(owner, now)
        if live is not None and live["pending"]:
            if queued:  # the shelf-check question now holds the open request: the queued asks wait on it, not lost
                conv.requests.put(owner, msg.provider_id, now, texts=live["texts"], request_id=live["request_id"], pending=live["pending"],
                                  question=live["question"], calls=list(queued), legacy=True)
            return disposition  # the shelf-check question took the open request over (Conversation._ask_shelf)
        if disposition == "proposed":
            if queued:  # the proposal waits for his yes while the next of his asks is asked, one at a time
                return self._next_queued(msg, now, rid, queued, texts, attachments, disposition)
            rid = conv.requests.put(owner, msg.provider_id, now, texts=texts, request_id=rid, state="drafted", skill=skill.name,
                                    slots=slots, attachments=attachments, draft_code=code)
        elif disposition in ("needs-details", "claim-question", "question"):
            rid = conv.requests.put(owner, msg.provider_id, now, texts=texts, request_id=rid, skill=skill.name, slots=slots,
                                    question=conv._said, attachments=attachments, draft_code=code if disposition == "needs-details" else None,
                                    calls=list(queued))
        else:
            if req is not None:
                conv.requests.mark(req["request_id"], "closed", now)
            if queued:
                return self._next_queued(msg, now, None, queued, texts, attachments, disposition)
        return disposition

    def _next_queued(self, msg, now, rid, queued, texts, attachments, disposition):
        """The current call is done: the next queued call becomes the open request and its one question is asked. Calls whose
        skill is gone are skipped. Returns ``disposition`` (what happened to the call just handled)."""
        live = [c for c in queued if self.registry.get(c.get("skill")) is not None]
        if live:
            self._queue_only(msg, now, {"request_id": rid} if rid is not None else None, live[0], live[1:], texts, attachments, None)
        return disposition

    # several asks in one message ------------------------------------------------------------------------------
    def _calls(self, msg, now, result, req):
        conv, owner = self.conv, self._owner()
        texts = _joined(req, msg)
        attachments = req["attachments"] if req else []
        asked = None if any(self.registry.get(c.get("skill")) is None for c in result["calls"]) else self._agreement(
            texts, req, [c.get("skill") for c in result["calls"]], attachments, now,
            has_slots=any(v not in (None, "", []) for c in result["calls"] for v in c["slots"].values()))
        if asked:
            return self._ask_which(msg, now, req, asked, attachments)
        long_ones = [c["skill"] in READ_ONLY_LONG for c in result["calls"]]
        if any(long_ones) and all(self.registry.get(c["skill"]) is not None for c in result["calls"]):
            if not all(long_ones):  # a caption and a change in one message: neither is answered or drafted
                conv.requests.mark(req["request_id"], "closed", now) if req is not None else conv.requests.close_live(owner, now, "closed")
                conv._reply(MIXED)
                self._logged(msg, "refused", "refused", *[self.registry.get(c["skill"]) for c in result["calls"]])  # AVB-10
                return "refused"
            return self._read_only_calls(msg, now, result["calls"], req, texts, attachments)
        ctx = self._ctx(now, texts)
        ctx.multi_call = len(result["calls"]) > 1
        ops, left, waiting, parts, stopped, used = [], [], [], [], [], []
        for call in result["calls"]:
            skill = self.registry.get(call["skill"])
            if skill is None or skill.approval == "none" or skill.name == "backlog.log":
                return self._backlog(msg, now, req, "", "unknown-skill")
            filled = validate(skill, {}, call["slots"], texts, ctx, attachments)
            slots = filled.slots
            for sl in skill.slots:
                if sl.kind == "attachment" and sl.from_attachment and attachments and not slots.get(sl.name):
                    slots[sl.name] = attachments[-1]
            given = slots  # keep owner-given values across questions, as in _advance
            slots, shown = apply_defaults(skill, slots, ctx)
            missing = None if filled.problem else next_missing(skill, slots)
            if filled.problem or filled.refused or missing is not None or any(
                    RULES.get(r, lambda *a: None)(slots, texts, ctx) for r in skill.rules):
                waiting.append({"skill": skill.name, "slots": given, "problem": filled.problem, "ask": filled.ask,
                                "slot": filled.problem_slot or (missing.name if missing is not None else None)})
                continue
            try:
                planned = skill.plan(dict(slots), ctx)
            except Exception as exc:  # noqa: BLE001 - as for one skill (_plan_stopped): a question is the one asked for this call, a refusal is said
                said = getattr(exc, "reply", None)
                said = said.strip() if isinstance(said, str) and said.strip() else None
                if said and getattr(exc, "kind", None) == "question":
                    waiting.append({"skill": skill.name, "slots": given, "ask": None, "slot": None, "problem": said})
                else:  # this ask is refused (or failed); the owner's other asks are not
                    reason = getattr(exc, "backlog", None)
                    stopped.append((said, reason if reason in BACKLOG_REASONS else None, skill))
                continue
            ops += planned if isinstance(planned, list) else []
            used.append(skill)  # AVB-10: only the skills that planned part of this draft
            parts.append((self._skill_notes(skill, slots, now, texts), shown))  # what each complete call said, set and warns of
            left += filled.left_off
        if len(ops) > MAX_OPS:
            conv._reply(TOO_MANY.format(limit=MAX_OPS, count=len(ops)))
            self._logged(msg, "refused", "cap", *used)  # AVB-10
            return "question"
        refused = self._say_refusals(stopped, texts, msg)
        if not ops:
            if waiting:  # the refused asks are said above; the owner's other asks go on, one question at a time
                return self._queue_only(msg, now, req, waiting[0], waiting[1:], texts, attachments, ctx)
            if req is not None:
                conv.requests.mark(req["request_id"], "closed", now)
            else:
                conv.requests.close_live(owner, now, "closed")
            if refused is None:
                conv._reply(PLAN_FAILED)
                self._logged(msg, "refused", "failed", *used)  # AVB-10
                return "not-drafted"
            return refused
        note = self._note_lines(parts, left)
        conv._skill_ref = "+".join(dict.fromkeys(f"{s.name}@{s.version}" for s in used)) or None  # AVB-10
        try: disposition = conv._draft(msg, now, {"ops": ops, "revises": result.get("revises")}, _earlier(texts, msg),
                                       prefix="\n".join(note) + "\n" if note else "", legacy=False)
        finally: conv._skill_ref = None
        live = conv.requests.get(owner, now)
        if live is not None and live["pending"]:
            if waiting:  # the shelf-check question holds the open request: the incomplete calls wait on it, not lost
                conv.requests.put(owner, msg.provider_id, now, texts=live["texts"], request_id=live["request_id"], pending=live["pending"],
                                  question=live["question"], calls=list(waiting), legacy=True)
            return disposition  # the shelf-check question took the open request over
        if disposition != "proposed" or not waiting:
            if req is not None:
                conv.requests.mark(req["request_id"], "closed", now)
            return disposition
        first, rest = waiting[0], waiting[1:]
        # the complete calls are drafted; the first incomplete one is asked next, one question at a time
        self._queue_only(msg, now, req, first, rest, texts, attachments, ctx)
        return disposition

    def _read_only_calls(self, msg, now, calls, req, texts, attachments):
        """Several caption asks in one message (every call a READ_ONLY_LONG skill): each complete one is answered in order, once;
        a held or hidden one is refused in its own words; the first that needs an answer is asked, the rest wait their turn."""
        conv, owner = self.conv, self._owner()
        ctx = self._ctx(now, texts)
        said = next((s for s in (self._read_only_hook(self.registry.get(c["skill"]), "preflight", ctx) for c in calls) if s), None)
        if said:
            conv.requests.mark(req["request_id"], "closed", now) if req is not None else conv.requests.close_live(owner, now, "closed")
            conv._reply(said)
            self._logged(msg, "refused", "policy", *[self.registry.get(c["skill"]) for c in calls])  # AVB-10
            return "refused"
        waiting, done = [], []
        for n, call in enumerate(calls):
            skill = self.registry.get(call["skill"])
            filled = validate(skill, {}, call["slots"], texts, ctx, attachments)
            if filled.refused:
                conv._reply(self._read_only_hook(skill, "refusal", ctx, filled.problem_slot, filled.refused_status) or filled.refused)
                self._logged(msg, "refused", "refused", skill, n=n)  # AVB-10
                continue
            missing = None if filled.problem else next_missing(skill, filled.slots)
            if filled.problem or missing is not None:
                waiting.append({"skill": skill.name, "slots": filled.slots, "problem": filled.problem, "ask": filled.ask,
                                "slot": filled.problem_slot or missing.name})
                continue
            if (skill.name, filled.slots) in done:  # the same caption asked twice: said once
                continue
            done.append((skill.name, filled.slots))
            fn = READ_ONLY.get(skill.name)
            conv._reply(fn(dict(filled.slots), ctx) if fn else NOT_SURE, long_ok=fn is not None)
            self._logged(msg, "answered" if fn else "refused", "ok" if fn else "unknown", skill, n=n)  # AVB-10
        if waiting:
            return self._queue_only(msg, now, req, waiting[0], waiting[1:], texts, attachments, ctx)
        conv.requests.mark(req["request_id"], "closed", now) if req is not None else conv.requests.close_live(owner, now, "closed")
        return "answer" if done else "refused"

    def _read_only_hook(self, skill, name, ctx, *args):
        """A read-only skill's own ``preflight`` / ``refusal`` sentence (hass/skills/social.py), else None. Never raises."""
        hook = skill_hook(skill, name) if getattr(skill, "approval", None) == "none" else None
        try:
            said = hook(skill.name, *args, ctx) if name == "refusal" and hook else hook(skill.name, {}, ctx) if hook else None
        except Exception:  # noqa: BLE001 - the hook is wording: without it the ordinary path goes on
            said = None
        return said.strip() if isinstance(said, str) and said.strip() else None

    def _say_refusals(self, stopped, texts, msg):
        """The asks of one message whose plan refused: each sentence is said as for one skill (a backlog reason also writes the ask
        down); an error with no sentence of the skill's own is the generic failure. Returns ``backlog`` or ``refused``, or None
        when nothing stopped."""
        if not stopped:
            return None
        from hass.skills.backlog import Backlog
        outcome = "not-drafted"
        for n, (said, reason, skill) in enumerate(stopped):
            if said is None:
                self.conv._reply(PLAN_FAILED)
                self._logged(msg, "refused", "failed", skill, n=n)  # AVB-10
                continue
            if reason:
                n_ = Backlog(self.conv.db, self.conv._now).record(reason, "", "\n".join(texts) if texts else msg.text)
                said, outcome = said + " " + NO_SKILL_SAID.format(n=n_), "backlog"
            elif outcome != "backlog":
                outcome = "refused"
            self.conv._reply(said)
            self._logged(msg, "refused", "backlog" if reason else "refused", skill, n=n)  # AVB-10
        return outcome

    def _queue_only(self, msg, now, req, first, rest, texts, attachments, ctx):
        """Make ``first`` (an incomplete call, its slots already checked) the open request, keep ``rest`` queued, ask its question."""
        conv = self.conv
        skill = self.registry.get(first["skill"])
        slot = (next((s for s in skill.slots if s.name == first["slot"]), None)
                if "slot" in first else next_missing(skill, first["slots"]))
        question = (question_for(slot, first.get("problem"), first.get("ask"), skill=skill, slots=first["slots"],
                                 ctx=ctx if ctx is not None else (self._ctx(now, texts) if skill_hook(skill, "question") else None))
                    if slot else first.get("problem"))
        conv.requests.put(self._owner(), msg.provider_id, now, texts=texts, request_id=req["request_id"] if req else None,
                          skill=skill.name, slots=first["slots"], calls=rest, attachments=attachments,
                          asked_slot=slot.name if slot else None, question=question, ask=first.get("ask"), asks=1)
        conv._reply(question or NOT_SURE)
        return "question"

    # nothing to draft ------------------------------------------------------------------------------------------
    def _logged(self, msg, step, result, *skills, n=0):
        """AVB-10: the audit line of a skill request that made no draft (an answer or a refusal); ids and fixed words only."""
        log = getattr(self.conv, "_audit_ask", None)
        if log is not None: log(msg, step, result, skills, n)

    def _read_only(self, msg, now, req, skill, slots, ctx, texts):
        if skill.name == "page.faq":
            from hass.skills.backlog import NO_FAQ
            return self._backlog(msg, now, req, "", "unsupported-page", reply=NO_FAQ, texts=texts, skill=skill)
        if skill.name == "backlog.log":
            return self._backlog(msg, now, req, slots.get("summary", ""), slots.get("reason") if slots.get("reason") in (
                "unknown-skill", "policy", "unsupported-page", "stuck", "price", "other") else "other", texts=texts, skill=skill)
        fn = READ_ONLY.get(skill.name)
        if fn is None:
            return self._backlog(msg, now, req, "", "other", texts=texts, skill=skill)
        queued = req["calls"] if req else []
        if req:
            self.conv.requests.mark(req["request_id"], "closed", now)
        self.conv._reply(fn(slots, ctx), long_ok=skill.name in READ_ONLY_LONG or (skill.name == "answer.site" and slots.get("kind") == "maker_story"))
        self._logged(msg, "answered", "ok", skill)
        if queued:  # the owner's other caption asks of the same message go on, one question at a time
            return self._next_queued(msg, now, None, queued, texts, req["attachments"], "answer")
        return "answer"

    def _backlog(self, msg, now, req, summary, reason, reply=None, texts=None, skill=None):
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
        self._logged(msg, "refused", "backlog", skill)
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
