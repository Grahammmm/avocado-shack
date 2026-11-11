"""Hass home-page copy ops (H13): ``store.set_headline`` fills the home-page ``<h1>`` slot (``store.headline``) and
``store.set_story`` the first "COME ON IN" paragraph (``store.story``: one paragraph, 20 letters to 400 characters),
through the normal typed-op path (draft, approval, single writer). Only the store record changes.

Usage (request op):
    {"op": "store.set_headline", "args": {"first": "A little market.", "second": "A lot to discover."}}

The page shows ``first<br><em>second</em>`` (the second line emphasised). Limits: each line at most 40 characters and
at least 2 letters (the refusal names the line number); text kinds already reject markup, ``$``, ``{{ }}`` and control
characters. The two lines must differ (case, spacing and dash style ignored). The same words as now (the default when
unset; spacing ignored) are refused. Undo restores the default.

``store.set_home_image`` ({"photo": "<sha256>", "imageAlt": "..."}) puts a stored photo's metadata-free web copy in the
one hero ``<img>`` (``store.homeImage``), through ``photos.install`` exactly as ``product.set_photo``. Undo removes it.
``store.clear_home_image`` ({}) puts the shop's own photo back ("put the old photo back"): it removes ``store.homeImage``
whatever store changes came after it was set, is refused when no home photo is set, and keeps the committed photo file;
undo of the clear restores the owner's photo.

``store.set_notice`` ({"text": "Closed Thanksgiving Day", "until": "2026-11-26"}) puts one dated notice at the top of the
home page (``store.notice``; at most 160 characters, 3 letters; last day today to 60 days ahead, Pacific); a second notice
replaces it and ``store.clear_notice`` removes it. The generated page drops it once ``until`` is past; between
regenerations a page script hides it after that day, so without JavaScript it stays until the next change regenerates.

Selective undo (as hass/ops/store.py): ``history.revert`` of an older store change sets back only the store fields that
change wrote (a notice with its dates is one field) and keeps later changes to other fields; a later change to the same
field is refused as a conflict.
"""

from __future__ import annotations

import copy
from datetime import date

from hass.content_model import DEFAULT_HEADLINE, DEFAULT_STORY, MAX_HEADLINE_LINE, MAX_NOTICE, MAX_NOTICE_DAYS, MAX_STORY, shop_today
from hass.ops import Arg, Op, Refused, photos
from hass.ops.store import _line_key, _spaced, _touch


def _set_headline(content, args, ctx):
    lines = [args["first"], args["second"]]
    for i, line in enumerate(lines, 1):
        if len(line) > MAX_HEADLINE_LINE:
            return Refused(f"headline line {i} is longer than {MAX_HEADLINE_LINE} characters")
    for i, line in enumerate(lines, 1):
        if sum(c.isalpha() for c in line) < 2:
            return Refused(f"headline line {i} needs at least 2 letters")
    if _line_key(lines[0]) == _line_key(lines[1]):
        return Refused("headline lines 1 and 2 say the same thing")
    current = content.store.get("headline") or DEFAULT_HEADLINE
    if [_spaced(line) for line in lines] == [_spaced(line) for line in current]:
        return Refused("the headline already says that")
    before = copy.deepcopy(content.store)
    content.store["headline"] = lines
    return _touch(before, content.store)


def _set_story(content, args, ctx):
    text = args["text"]
    if text.splitlines() != [text]:  # any line or paragraph separator, U+2028/9 too
        return Refused("the story is one paragraph")
    if len(text) > MAX_STORY:
        return Refused(f"the story is longer than {MAX_STORY} characters")
    if sum(c.isalpha() for c in text) < 20:
        return Refused("the story needs at least 20 letters")
    if _spaced(text) == _spaced(content.store.get("story") or DEFAULT_STORY):
        return Refused("the story already says that")
    before = copy.deepcopy(content.store)
    content.store["story"] = text
    return _touch(before, content.store)


def _set_home_image(content, args, ctx):
    """The one hero image: a stored photo's metadata-free web copy, installed as product.set_photo does."""
    target = photos.install(ctx, args["photo"], args["imageAlt"], style=False)  # SKILLS-PIC-1: the wide hero keeps the owner's pixels (D6)
    if isinstance(target, Refused):
        return target
    home = {"image": target, "imageAlt": args["imageAlt"]}
    if content.store.get("homeImage") == home:
        return Refused("the home page already shows that photo with that imageAlt")
    before = copy.deepcopy(content.store)
    content.store["homeImage"] = home
    return _touch(before, content.store)


def _clear_home_image(content, args, ctx):
    """Put the shop's own hero photo back; the committed photo file stays (undo and history keep working)."""
    if "homeImage" not in content.store:
        return Refused("the home page already shows the shop’s own photo")
    before = copy.deepcopy(content.store)
    del content.store["homeImage"]
    return _touch(before, content.store)


def _set_notice(content, args, ctx):
    """The one dated owner notice (store.notice); a second notice replaces the first."""
    text, until, today = args["text"], date.fromisoformat(args["until"]), shop_today(ctx.now)
    if until < today:
        return Refused(f"the last day {args['until']} is already past")
    if (until - today).days > MAX_NOTICE_DAYS:
        return Refused(f"the last day is more than {MAX_NOTICE_DAYS} days ahead")
    if len(text) > MAX_NOTICE:
        return Refused(f"the notice is longer than {MAX_NOTICE} characters")
    if sum(c.isalpha() for c in text) < 3:
        return Refused("the notice needs at least 3 letters")
    current = content.store.get("notice") or {}
    if _spaced(text) == _spaced(current.get("text", "")) and args["until"] == current.get("until"):
        return Refused("the home page already shows that notice")
    before = copy.deepcopy(content.store)
    content.store["notice"] = {"text": text, "until": args["until"]}
    return _touch(before, content.store)


def _clear_notice(content, args, ctx):
    if "notice" not in content.store:
        return Refused("there is no notice")
    before = copy.deepcopy(content.store)
    del content.store["notice"]
    return _touch(before, content.store)


OPS = (Op("store.set_headline", {"first": Arg("text"), "second": Arg("text")}, _set_headline),
       Op("store.set_story", {"text": Arg("text")}, _set_story),
       Op("store.set_home_image", {"photo": Arg("id"), "imageAlt": Arg("text")}, _set_home_image),
       Op("store.clear_home_image", {}, _clear_home_image),
       Op("store.set_notice", {"text": Arg("text"), "until": Arg("date")}, _set_notice),
       Op("store.clear_notice", {}, _clear_notice))
