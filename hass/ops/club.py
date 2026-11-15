"""Hass club ops (AV2152-09, H13): ``club.set_intro`` sets the opening paragraph of the /hike page (the club manifesto
line) in the club record (``community.club.intro``), through the normal typed-op path (draft, approval, single writer).

Usage (request op):
    {"op": "club.set_intro", "args": {"text": "A good morning doesn't need much. ..."}}

One paragraph of 20 letters to 400 characters; the text kind already refuses markup, ``$``, ``{{ }}``, control and
invisible characters and outer spaces. The text replaces the whole paragraph and is stored as sent. The same words as
now (the default when unset; spacing ignored) are refused. ``history.revert`` puts the whole club record back, absent
intro included, and is refused when the club record changed again after that change. Nothing else on /hike changes.
"""

from __future__ import annotations

import copy

from hass.content_model import DEFAULT_CLUB_INTRO, MAX_CLUB_INTRO
from hass.ops import Arg, Op, Refused, Touched
from hass.ops.store import _spaced


def _set_intro(content, args, ctx):
    text, club = args["text"], content.community["club"]
    if text.splitlines() != [text]:  # any line or paragraph separator, U+2028/9 too
        return Refused("the club intro is one paragraph")
    if len(text) > MAX_CLUB_INTRO:
        return Refused(f"the club intro is longer than {MAX_CLUB_INTRO} characters")
    if sum(c.isalpha() for c in text) < 20:
        return Refused("the club intro needs at least 20 letters")
    if _spaced(text) == _spaced(club.get("intro", DEFAULT_CLUB_INTRO)):
        return Refused("the club intro already says that")
    before = copy.deepcopy(club)
    club["intro"] = text
    return [Touched("club", "club", before, copy.deepcopy(club))]


OPS = (Op("club.set_intro", {"text": Arg("text")}, _set_intro),)
