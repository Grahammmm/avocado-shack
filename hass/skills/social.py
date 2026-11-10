"""SKILLS-SOCIAL-1 part 1 (SKILLS-SPEC 3.27, 3.28): write a caption the owner can copy, for a product, a hike or a maker.

Three read-only skills: ``social.item``, ``social.hike`` and ``social.maker``. Each reply is the caption that
hass/social_draft.py already builds (``build``, ``build_hike``, ``build_maker``: the same text as the ``post <id>`` and
``post hike <id>`` commands), shown as copyable text. Nothing here posts, sends, schedules, saves a draft, attaches a
photo, approves or edits anything: the plans are empty, approval is ``none`` and the reply is text only. A product's
photo is the one on its product card; the reply says so in one plain line and carries no attachment.

The replies are registered into ``hass.skills.dispatch.READ_ONLY`` (like ``specials.show``) and their names into
``dispatch.READ_ONLY_LONG``, so a full caption may be longer than an everyday message. ``preflight`` and ``refusal`` are
hooks the dispatcher finds in this module (the module that defines the plans). Guide: docs/hass/skills/social.md.
"""
from __future__ import annotations

import re
from pathlib import Path

from hass import social_draft, voice
from hass.skills.model import Skill, Slot, Trigger, Undo

q = voice.quote  # the caption is built from the shop's own saved words: shown exactly, never judged or reworded

COPY_HEAD = "Here's a post you can copy. I haven't posted anything."
PRODUCT_PHOTO = "The photo is the one on the product card; it isn't attached here."
NO_PHOTO = "No photo is attached here."
NO_POSTING = "I can write a caption for you to copy, but I don't post, send or schedule anything."
CANT_READ = "I can't look that up right now, so I didn't write a post. Nothing has changed."
CANT_SEE_PHOTO = "I can't check the product's photo right now, so I didn't write a post. Nothing has changed."
NO_STORY = "That maker has no story yet, so I can't write a post about them. Add the maker's story first."
ITEM_REFUSALS = {
    "no such product": "I don't know that product, so I can't write a post for it.",
    "not on the site": "That product isn't on the website right now, so I can't write a post for it.",
    "no photo on the site": "That product has no photo on the website yet, so I can't write a post for it.",
    "product record incomplete": "That product is missing its name or description, so I can't write a post for it.",
}
HIKE_REFUSALS = {
    "no such hike": "I don't know that hike, so I can't write a post for it.",
    "hike is cancelled": "That hike is cancelled, so there is nothing to announce.",
    "hike already happened": "That hike has already happened, so there is nothing to announce.",
    "not scheduled": "That hike isn't scheduled yet, so there is nothing to announce.",
    "hike record incomplete": "That hike is missing its time or meeting place, so I can't write a post for it.",
}
MAKER_REFUSALS = {
    "no such maker": "I don't know that maker, so I can't write a post about them.",
    "not on the site": "That maker isn't on the website right now, so I can't write a post about them.",
    "no active products": "That maker has nothing on the website right now, so I can't write a post about them.",
    "maker record incomplete": "That maker is missing a name or place, so I can't write a post about them.",
}
SHARED_REFUSALS = {
    "free text has a hashtag or account name": "Its words have a # or @ in them, so I can't write a post for it.",
    "caption too long": "That post would be too long for Instagram, so I didn't write it.",
}
RESOLVER_REFUSALS = {  # a product or maker the resolver will not hand over: said as a caption answer, not as a change
    ("item", "held"): "That product is on hold, so I can't write a post for it yet.",
    ("item", "hidden"): "That product is hidden, so I can't write a post for it.",
    ("maker", "hidden"): "That maker is hidden, so I can't write a post about them.",
}

# Explicit asks to publish, send or schedule (never ordinary caption wording like "post about the honey"). Each check
# looks at one of the owner's texts, lower-cased.
_OBJ = r"(?:it|this|that|them|these|those|the (?:post|caption|announcement))"
SELF = re.compile(r"\b(?:i|we)(?:'ll|'d| will| can| could| want to| am going to|'m going to| are going to)? (?:post|share|schedule|send)\b")
INTENT = (
    re.compile(r"\bschedul(?:e|ing)\s+" + _OBJ + r"\b"),
    re.compile(r"\bschedul(?:e|ing)\b.*\b(?:post|caption|announcement)s?\b|\b(?:post|caption|announcement)s?\b.*\bschedule (?:it|them|for|on)\b"),
    re.compile(r"\bpublish(?:es|ed|ing)?\b"),
    re.compile(r"\b(?:post|share|put up)\s+" + _OBJ + r"(?:\s+(?:up|out|online))?\s*(?:$|[.!?,]|\s+(?:now|today|tonight|tomorrow|right away|for me|later|"
               r"on|to|at)\b)"),
    re.compile(r"\b(?:post|share)\b.*\b(?:right now|right away|tonight)\b"),
    re.compile(r"^\s*(?:please\s+)?(?:post|share)\b(?!\s+about\b).*\bnow\s*[.!]?\s*$"),
    re.compile(r"\b(?:send|email|text|message)\b.*\b(?:club|members|hikers|mailing list|everyone|followers)\b"),
    re.compile(r"\b(?:send|email|text)\s+" + _OBJ + r"\s+(?:out|to)\b"),
)


def wants_posting(texts) -> bool:
    """True when one of the owner's texts asks Hass to publish, send or schedule (Hass only writes a caption to copy)."""
    said = [SELF.sub(" ", t.lower()) for t in texts or () if isinstance(t, str)]  # the owner posting it himself is fine
    return any(rx.search(t) for t in said for rx in INTENT)


def preflight(skill_name, slots, ctx):
    """The dispatcher's check before any question for a social skill: an ask to post, send or schedule is answered honestly
    (and nothing else happens). None lets the caption request go on."""
    return NO_POSTING if skill_name in NAMES and wants_posting(getattr(ctx, "texts", None)) else None


def refusal(skill_name, slot_name, status, ctx=None):
    """The dispatcher's wording when the resolver refuses a held or hidden product or a hidden maker for a caption."""
    return RESOLVER_REFUSALS.get((slot_name, status)) if skill_name in NAMES else None


def _plan(slots, ctx):
    return []  # read-only: a caption is text in the reply, never an op


def _copy(caption, *tail) -> str:
    return "\n".join([COPY_HEAD, q(caption), *tail])


def _said(reason, table) -> str:
    return table.get(reason) or SHARED_REFUSALS.get(reason) or CANT_READ  # "cannot read content" and anything unknown


def item_reply(slots, ctx) -> str:
    """The product caption from the writer's own content and site folder, then the one plain photo line."""
    content, site = getattr(ctx, "content", None), getattr(ctx, "site_dir", None)
    if content is None:
        return CANT_READ
    if site is None:
        return CANT_SEE_PHOTO  # never this installation's own site folder: the photo must be the writer's
    try:
        out = social_draft.build(content, (slots or {}).get("item"), Path(site))
    except (AttributeError, TypeError, ValueError, OSError):
        return CANT_READ
    return _copy(out["caption"], PRODUCT_PHOTO) if out.get("draft") else _said(out.get("reason"), ITEM_REFUSALS)


def hike_reply(slots, ctx) -> str:
    """The hike announcement caption (only a scheduled hike that has not started yet, by the request's clock)."""
    content, now = getattr(ctx, "content", None), getattr(ctx, "now", None)
    if content is None or now is None:
        return CANT_READ
    try:
        out = social_draft.build_hike(content, (slots or {}).get("hike"), now)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return CANT_READ
    return _copy(out["caption"], NO_PHOTO) if out.get("draft") else _said(out.get("reason"), HIKE_REFUSALS)


def maker_reply(slots, ctx) -> str:
    """The meet-the-maker caption; a maker without a story is asked for one first."""
    content = getattr(ctx, "content", None)
    if content is None:
        return CANT_READ
    key = (slots or {}).get("maker")
    try:
        out = social_draft.build_maker(content, key)
    except (AttributeError, TypeError, ValueError):
        return CANT_READ
    if out.get("draft"):
        return _copy(out["caption"], NO_PHOTO)
    if out.get("reason") == "maker record incomplete":
        maker = content.makers.get(key) if isinstance(getattr(content, "makers", None), dict) else None
        if isinstance(maker, dict) and not social_draft._block(maker.get("story")):
            return NO_STORY
    return _said(out.get("reason"), MAKER_REFUSALS)


# -- declarations ----------------------------------------------------------------------------------------------------
_CASES = "hass/tests/fixtures/skills/social/{}.jsonl"


def _read_only(name, label, summary, triggers, slot, refuse):
    return Skill(name=name, label=label, summary=summary, triggers=triggers, slots=(slot,), rules=(), plan=_plan, edits=(),
                 side_effects=("none",), preview="none", approval="none", live_class="read-only", undo=Undo("none", "none"),
                 refuse=refuse, cases=_CASES.format(name), version=1)


SOCIAL_ITEM = _read_only(
    "social.item", "write a post caption for a product",
    "Write an Instagram caption for one product on the website, to copy. Nothing is posted.",
    (Trigger("write a post for the honey"),
     Trigger("give me an instagram caption for the plum jam"),
     Trigger("caption for the sourdough so I can post it myself"),
     Trigger("wrte a captoin for the eggs", "typo"),
     Trigger("something for instagram about that new thing", "vague"),
     Trigger("captions for the honey and the plum jam", "multi"),
     Trigger("post about the avocado honey")),
    Slot("item", "product_ref", True, ask="Which product should the post be about?"),
    (("the product is hidden or on hold", RESOLVER_REFUSALS[("item", "hidden")]),
     ("the product has no photo on the website", ITEM_REFUSALS["no photo on the site"]),
     ("asked to post or schedule it", NO_POSTING)))

SOCIAL_HIKE = _read_only(
    "social.hike", "write a post caption for a hike",
    "Write an announcement caption for one upcoming hike, to copy. Nothing is posted or sent.",
    (Trigger("write a post for the Mill Creek hike"),
     Trigger("caption to announce Saturday's hike"),
     Trigger("give me something to post about the beach walk"),
     Trigger("anounce the ridge hike captoin", "typo"),
     Trigger("can you do a hike post", "vague"),
     Trigger("captions for the Mill Creek hike and the ridge hike", "multi"),
     Trigger("post about the hike this weekend")),
    Slot("hike", "hike_ref", True, ask="Which hike should the post be about?"),
    (("the hike is cancelled, past or not scheduled", HIKE_REFUSALS["hike is cancelled"]),
     ("asked to post, send or schedule it", NO_POSTING)))

SOCIAL_MAKER = _read_only(
    "social.maker", "write a post caption for a maker",
    "Write a meet-the-maker caption for one maker with a story, to copy. Nothing is posted.",
    (Trigger("write a meet the maker post for Bee Happy Farm"),
     Trigger("caption introducing the bakery that makes our bread"),
     Trigger("give me a post about the honey people"),
     Trigger("meat the makr post for the jam lady", "typo"),
     Trigger("something about one of our makers", "vague"),
     Trigger("maker posts for the bakery and the honey farm", "multi"),
     Trigger("post about who makes the plum jam")),
    Slot("maker", "maker_ref", True, ask="Which maker should the post be about?"),
    (("the maker has no story", NO_STORY),
     ("the maker is hidden or has nothing on the website", MAKER_REFUSALS["no active products"]),
     ("asked to post or schedule it", NO_POSTING)))

SKILLS = (SOCIAL_ITEM, SOCIAL_HIKE, SOCIAL_MAKER)
NAMES = tuple(s.name for s in SKILLS)
REPLIES = {"social.item": item_reply, "social.hike": hike_reply, "social.maker": maker_reply}


def _register() -> None:
    """Hand the three replies to the dispatcher (idempotent, like specials.show) and mark them as long-caption answers."""
    from hass.skills import dispatch
    for name, fn in REPLIES.items():
        dispatch.READ_ONLY.setdefault(name, fn)
        dispatch.READ_ONLY_LONG.add(name)


_register()
