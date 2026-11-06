"""Hass sample-hikes switch (AV1422-10, H04): ``hike.samples {show}`` hides or shows the labelled sample hikes on /hike.

``show=false`` sets the one club flag ``showSamples: false``; ``show=true`` removes it (absent = shown, as before).
Asking for the state it is already in is refused and nothing is written. ``history.revert`` restores the previous state.
The sample file ``storefront-mockup/hiking-preview.json`` is never edited.
"""

from __future__ import annotations

import copy

from hass.ops import Arg, Op, Refused, Touched


def _samples(content, args, ctx):
    club = content.community["club"]
    hidden = club.get("showSamples") is False
    if args["show"] is hidden:  # asking for the state it is not in changes it; the same state is refused
        before = copy.deepcopy(club)
        if hidden:
            del club["showSamples"]
        else:
            club["showSamples"] = False
        return [Touched("club", "club", before, copy.deepcopy(club))]
    return Refused("the sample hikes are already hidden" if hidden else "the sample hikes are already shown")


OPS = (Op("hike.samples", {"show": Arg("bool")}, _samples),)
