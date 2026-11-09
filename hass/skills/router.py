"""The skill router (SKILLS-FW-2): narrows the prompt before the model call and checks the model's pick after it.

Two steps, both pure code (no model, no clock, no file; the backlog write is the only effect and it goes through a
store the caller hands in):

* ``candidates(text, hints, open_request, attachment, skills)`` scores every active skill from a folded, stemmed
  lexicon of its trigger examples, the ``nl_prep`` hints, the message's attachment and the open request, and returns at
  most three ``(name, score)`` pairs. It never decides alone: it picks what the prompt shows in full and gives a second
  opinion on the model's pick.
* ``route(reply, ranked, skills, ...)`` turns the model's reply into one ``Route``: run these skill calls, ask one
  question, pass an old-style ``ops`` reply through, or write the request to the backlog ("none of these"). A wrong pick
  can only produce a wrong draft the owner must approve, so when the two opinions disagree the owner is asked, in plain
  words, and nothing is drafted.

Spec: reports/hass/SKILLS-SPEC.md section 2.5. Not wired into ``conversation.py`` yet (a later card).
"""
from __future__ import annotations

import difflib
import math
from dataclasses import dataclass

from hass import interpret_check, nl_prep
from hass.skills import backlog as backlog_mod
from hass.skills.kinds import WORDS_FOR_AVAILABILITY

TOP = 3
NEAR_TIE = 0.10  # the model's pick scored within 10% of the leader: the two opinions are split
HINT_BOOST, OPEN_BOOST = 1.5, 3.0
FUZZY_MIN, FUZZY_CUTOFF = 5, 0.8
STOP = frozenset("a an and at be but by do for from i in is it me my of on or our the to up we you your can could would please "
                 "just that this with are was what whats get got".split())
AVAILABILITY_TOKENS = frozenset(nl_prep.stem(w) for words in WORDS_FOR_AVAILABILITY.values() for w in " ".join(words).split()) - STOP

ACTIONS = ("run", "ask", "question", "unsupported", "ops", "backlog", "retry")


@dataclass(frozen=True)
class Route:
    """What to do with one interpreter reply. ``calls`` is ((skill name, slots), ...) for action ``run``."""
    action: str
    calls: tuple = ()
    revises: str | None = None
    reply: str = ""  # the owner-facing text for ask / question / unsupported / backlog
    reason: str = ""  # backlog reason (set by code)
    summary: str = ""
    backlog_id: int | None = None
    raw: dict | None = None  # the untouched reply for action ``ops``


def _tokens(text) -> list:
    return nl_prep.tokens(text, stop=STOP)


def _active(skills) -> list:
    return list(skills.active()) if hasattr(skills, "active") else [s for s in skills if getattr(s, "status", "active") == "active"]


class _Lexicon:
    def __init__(self, items):
        self.items = items
        self.vocab = {s.name: {t for trig in s.triggers for t in _tokens(trig.text)} for s in items}
        df: dict = {}
        for tokens in self.vocab.values():
            for t in tokens:
                df[t] = df.get(t, 0) + 1
        n = max(1, len(items))
        self.weight = {t: 1.0 + math.log(n / c) for t, c in df.items()}
        self.all = sorted(self.weight)

    def canon(self, token):
        if token in self.weight:
            return token
        if len(token) >= FUZZY_MIN:
            close = difflib.get_close_matches(token, self.all, n=1, cutoff=FUZZY_CUTOFF)
            if close:
                return close[0]
        return None


def _has_attachment_slot(skill) -> bool:
    return any(s.kind == "attachment" for s in skill.slots)


def candidates(text, hints=None, open_request=None, attachment=None, skills=()) -> list:
    """Up to three ``(skill name, score)``, best first (ties by name), score > 0 only. With an attachment only skills
    that own an attachment slot compete. ``open_request`` is a dict with the open request's ``skill`` (or None)."""
    items = _active(skills)
    if attachment:
        items = [s for s in items if _has_attachment_slot(s)]
    if not items:
        return []
    lex = _Lexicon(items)
    said = {c for c in (lex.canon(t) for t in set(_tokens(text))) if c}
    hints = hints if isinstance(hints, dict) else {}
    folded = nl_prep.fold(text)
    hike = bool(hints.get("hikes")) or bool(nl_prep.HIKE_WORD_RE.search(folded))
    stock = bool(hints.get("products")) or bool(AVAILABILITY_TOKENS & {nl_prep.stem(t) for t in nl_prep.TOKEN_RE.findall(folded)})
    open_skill = open_request.get("skill") if isinstance(open_request, dict) else None
    scored = []
    for skill in items:
        score = sum(lex.weight[t] for t in said & lex.vocab[skill.name])
        score += HINT_BOOST if (hike and skill.group == "hike") or (stock and skill.group == "stock") else 0.0
        score += OPEN_BOOST if open_skill == skill.name else 0.0
        if score > 0:
            scored.append((skill.name, round(score, 4)))
    scored.sort(key=lambda p: (-p[1], p[0]))
    return scored[:TOP]


def price_only(text, hints, ranked=()) -> bool:
    """A money hint and nothing else to change: no date, time or hike in the hints and no availability word."""
    hints = hints if isinstance(hints, dict) else {}
    if not hints.get("price") or any(hints.get(k) for k in ("dates", "times", "hikes")):
        return False
    return not (AVAILABILITY_TOKENS & {nl_prep.stem(t) for t in nl_prep.TOKEN_RE.findall(nl_prep.fold(text))})


def _labels_question(labels) -> str:
    labels = list(dict.fromkeys(labels))
    if len(labels) == 1:
        return f"Do you want me to {labels[0]}?"
    return "Do you want me to " + ", ".join(labels[:-1]) + " or " + labels[-1] + "?"


def _log(store, reason, summary, text, reply=backlog_mod.CANT_DO) -> Route:
    number = store.record(reason, summary, text) if store is not None else None
    return Route("backlog", reply=reply, reason=reason, summary=summary, backlog_id=number)


def route(reply, ranked, skills, *, text="", hints=None, store=None, pending_codes=(), retried=False) -> Route:
    """Decide what to do with the interpreter ``reply``.

    ``ranked`` is ``candidates(...)`` for the same message; ``text`` is the owner's joined texts (kept privately in the
    backlog row, never sent anywhere); ``store`` is a ``Backlog`` (None = do not write). Never raises on a bad reply.
    "None of these" (a ``none`` reply, an unknown skill, an unreadable reply after one re-ask, or no candidate and no
    usable slots) writes one backlog row and answers ``CANT_DO``; nothing is drafted."""
    if not isinstance(reply, dict):
        return _log(store, "other", "", text) if retried else Route("retry")
    if "ops" in reply and not interpret_check.is_skill_reply(reply):
        return Route("ops", raw=reply)
    for key, action in (("question", "question"), ("unsupported", "unsupported")):
        if isinstance(reply.get(key), str) and reply[key].strip() and not interpret_check.is_skill_reply(reply):
            return Route(action, reply=reply[key])
    if not interpret_check.is_skill_reply(reply):
        return _log(store, "other", "", text) if retried else Route("retry")

    checked = interpret_check.check_skill(reply, skills, pending_codes)
    if "question" in checked:
        return Route("question", reply=checked["question"])
    if checked.get("skill") == "none":
        summary = checked.get("summary", "")
        if not checked.get("unknown") and price_only(text, hints, ranked):
            return _log(store, "price", summary, text, interpret_check.PRICE_REPLY)
        return _log(store, "unknown-skill", summary, text)

    calls = tuple((c["skill"], dict(c.get("slots") or {})) for c in (checked["calls"] if "calls" in checked else [checked]))
    names = [n for n, _s in ranked]
    if not names:
        if not any(slots for _n, slots in calls):  # no second opinion and nothing filled in: never guess
            return _log(store, "unknown-skill", "", text)
    else:
        outside = [n for n, _s in calls if n not in names]
        if outside:
            wanted = list(dict.fromkeys([skills.get(names[0]).label] + [skills.get(n).label for n, _s in calls]))
            return Route("ask", reply=_labels_question(wanted[:TOP]))
        lead, score = ranked[0]
        called = {n for n, _s in calls}
        # leading pair ambiguous: ask unless the reply has a call for both of them (whatever else it holds)
        if len(ranked) > 1 and (score - ranked[1][1]) <= NEAR_TIE * score and not {lead, ranked[1][0]} <= called:
            return Route("ask", reply=_labels_question([skills.get(lead).label, skills.get(ranked[1][0]).label]))
        if len(calls) == 1:
            pick = dict(ranked)[calls[0][0]]
            if calls[0][0] != lead and (score - pick) <= NEAR_TIE * score:
                return Route("ask", reply=_labels_question([skills.get(lead).label, skills.get(calls[0][0]).label]))

    first = skills.get(calls[0][0])
    if len(calls) == 1 and "backlog-row" in first.side_effects:  # backlog.log, page.faq: the skill's own fixed reply
        fixed = first.refuse[0][1] if first.name == "page.faq" and first.refuse else backlog_mod.CANT_DO
        reason = "unsupported-page" if first.name == "page.faq" else "other"
        summary = calls[0][1].get("summary", "") if isinstance(calls[0][1].get("summary", ""), str) else ""
        return _log(store, reason, summary, text, fixed)
    return Route("run", calls=calls, revises=checked.get("revises"))
