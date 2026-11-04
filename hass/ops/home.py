"""Hass home-page copy ops (H13): ``store.set_headline`` fills the home-page ``<h1>`` slot (``store.headline``) and
``store.set_story`` the first "COME ON IN" paragraph (``store.story``: one paragraph, 20 letters to 400 characters),
through the normal typed-op path (draft, approval, single writer). Only the store record changes.

Usage (request op):
    {"op": "store.set_headline", "args": {"first": "A little market.", "second": "A lot to discover."}}

The page shows ``first<br><em>second</em>`` (the second line emphasised). Limits: each line at most 40 characters and
at least 2 letters (the refusal names the line number); text kinds already reject markup, ``$``, ``{{ }}`` and control
characters. The same words as now (the default when unset; spacing ignored) are refused. Undo restores the default.

``store.set_home_image`` ({"photo": "<sha256>", "imageAlt": "..."}) puts a stored photo's metadata-free web copy in the
one hero ``<img>`` (``store.homeImage``), through ``photos.install`` exactly as ``product.set_photo``. Undo removes it.

Selective-undo limit (as hass/ops/store.py): the store is ONE record, so ``history.revert`` of an older store change
after a later store change is refused as a conflict. Undo the newest store change first.
"""

from __future__ import annotations

import copy

from hass.content_model import DEFAULT_HEADLINE, DEFAULT_STORY, MAX_HEADLINE_LINE, MAX_STORY
from hass.ops import Arg, Op, Refused, photos
from hass.ops.store import _spaced, _touch


def _set_headline(content, args, ctx):
    lines = [args["first"], args["second"]]
    for i, line in enumerate(lines, 1):
        if len(line) > MAX_HEADLINE_LINE:
            return Refused(f"headline line {i} is longer than {MAX_HEADLINE_LINE} characters")
    for i, line in enumerate(lines, 1):
        if sum(c.isalpha() for c in line) < 2:
            return Refused(f"headline line {i} needs at least 2 letters")
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
    target = photos.install(ctx, args["photo"], args["imageAlt"])
    if isinstance(target, Refused):
        return target
    home = {"image": target, "imageAlt": args["imageAlt"]}
    if content.store.get("homeImage") == home:
        return Refused("the home page already shows that photo with that imageAlt")
    before = copy.deepcopy(content.store)
    content.store["homeImage"] = home
    return _touch(before, content.store)


OPS = (Op("store.set_headline", {"first": Arg("text"), "second": Arg("text")}, _set_headline),
       Op("store.set_story", {"text": Arg("text")}, _set_story),
       Op("store.set_home_image", {"photo": Arg("id"), "imageAlt": Arg("text")}, _set_home_image))
