"""Hass route-idea op (H04): ``route.edit`` corrects the wording of one undated route idea.

Usage: ``{"op": "route.edit", "args": {"id": "idea-cass-hill", "difficulty": "Easy to moderate"}}``.
Editable text fields: ``ROUTE_EDITABLE``; only the given fields change, and values equal to the current ones are dropped.
Locked: ``id``, ``status`` (always ``idea``), ``rsvpEnabled`` (always false), ``sourceUrl`` and ``sourceName``. They are
not arguments, so the registry refuses them as unknown arguments: a route idea never becomes a dated hike, never takes
RSVPs and never loses the source link the migration check records. A real event id is refused; use ``hike.update``.
The change is drafted, approved and applied like every other edit; ``history.revert`` restores the old text.
"""

from __future__ import annotations

import copy

from hass.ops import Arg, NeedsDetails, Op, Refused, Touched

ROUTE_EDITABLE = ("title", "place", "character", "distance", "difficulty", "elevation", "elevationLabel", "duration",
                  "routeType", "terrain", "description")


def _route_edit(content, args, ctx):
    route_id = args["id"]
    if any(e["id"] == route_id for e in content.community["events"]):
        return Refused(f"{route_id} is a hike, not a route idea; use hike.update")
    idea = next((i for i in content.community["routeIdeas"] if i["id"] == route_id), None)
    if idea is None:
        return Refused(f"unknown route idea {route_id}")
    changes = {f: args[f] for f in ROUTE_EDITABLE if f in args}
    if not changes:
        return NeedsDetails(list(ROUTE_EDITABLE), "What should change on this route idea?")
    changes = {f: v for f, v in changes.items() if idea.get(f) != v}
    if not changes:
        return Refused(f"route idea {route_id} already says that")
    before = copy.deepcopy(idea)
    idea.update(changes)
    return [Touched("routeIdeas", route_id, before, copy.deepcopy(idea))]


OPS = (Op("route.edit", {"id": Arg("id"), **{f: Arg("text", required=False) for f in ROUTE_EDITABLE}}, _route_edit),)
