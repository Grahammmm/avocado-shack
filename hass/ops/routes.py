"""Hass route-idea op (H04): ``route.edit`` corrects the wording of one undated route idea.

Usage: ``{"op": "route.edit", "args": {"id": "idea-cass-hill", "difficulty": "Easy to moderate"}}``.
Editable text fields: ``ROUTE_EDITABLE``; only the given fields change.
Values equal to the current ones, spacing ignored, are dropped.
Locked: ``id``, ``status`` (always ``idea``), ``rsvpEnabled`` (always false), ``sourceUrl`` and ``sourceName``. They are
not arguments, so the registry refuses them as unknown arguments: a route idea never becomes a dated hike, never takes
RSVPs and never loses the source link the migration check records. A real event id is refused; use ``hike.update``.
The change is drafted, approved and applied like every other edit; ``history.revert`` restores the old text.
A new ``title`` already used by another route idea or a hike (case and spacing ignored) is refused, naming that id.
Look-alike Unicode forms count as the same title (NFKC); an edit that only re-encodes the text (NFC) already says that.
``route.add`` (AV1322-02) drafts a new idea ``idea-<title slug>`` (all fields; public https source); undo removes it.
"""

from __future__ import annotations

import copy
import re
import unicodedata

from hass.content_model import _https
from hass.ops import Arg, NeedsDetails, Op, Refused, Touched
from hass.ops.hikes import MAX_ID_BASE

ROUTE_EDITABLE = ("title", "place", "character", "distance", "difficulty", "elevation", "elevationLabel", "duration",
                  "routeType", "terrain", "description")


def _fold(text):
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def _spaced(value):
    """Spacing and composed/decomposed forms only; case and characters kept."""
    return " ".join(unicodedata.normalize("NFC", value).split()) if isinstance(value, str) else value


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
    changes = {f: v for f, v in changes.items() if _spaced(idea.get(f)) != _spaced(v)}
    if not changes:
        return Refused(f"route idea {route_id} already says that")
    if "title" in changes and (taken := _title_taken(content, changes["title"], route_id)):
        return taken
    before = copy.deepcopy(idea)
    idea.update(changes)
    return [Touched("routeIdeas", route_id, before, copy.deepcopy(idea))]


def _title_taken(content, title, skip_id=None):
    """Refused naming the other route idea or hike already using ``title`` (case, spacing, NFKC folded), else None."""
    others = [i for i in content.community["routeIdeas"] if i.get("id") != skip_id] + content.community["events"]
    for other in others:
        if isinstance(other.get("title"), str) and _fold(other["title"]) == _fold(title):
            return Refused(f"{other.get('id')} is already called {other['title']}")


def _route_add(content, args, ctx):
    if not (args.get("sourceUrl") and args.get("sourceName")):
        return NeedsDetails(["sourceUrl", "sourceName"], "Where does this route come from (link and name)?")
    if missing := [f for f in ROUTE_EDITABLE if f not in args]:  # the validator needs every route text non-empty
        return NeedsDetails(missing, "Please provide: " + ", ".join(missing))
    problems = []
    _https(problems, "sourceUrl", args["sourceUrl"])
    if problems:
        return Refused("sourceUrl must be a public https:// link")  # the link itself is never echoed
    plain = "".join(c for c in unicodedata.normalize("NFKD", args["title"]) if not unicodedata.combining(c))
    if not (slug := re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")):  # same slug rule as hikes._slug_id
        return Refused("title needs a letter or digit")
    if taken := _title_taken(content, args["title"]):
        return taken
    base = f"idea-{slug}"[:MAX_ID_BASE].rstrip("-")
    used = {e["id"] for e in content.community["events"]} | {i["id"] for i in content.community["routeIdeas"]}
    new_id, n = base, 1
    while new_id in used:
        n += 1
        new_id = f"{base}-{n}"
    record = {"id": new_id, **{f: args[f] for f in ROUTE_EDITABLE}, "sourceUrl": args["sourceUrl"],
              "sourceName": args["sourceName"], "status": "idea", "rsvpEnabled": False}
    content.community["routeIdeas"].append(record)
    return [Touched("routeIdeas", new_id, None, copy.deepcopy(record))]


OPS = (Op("route.edit", {"id": Arg("id"), **{f: Arg("text", required=False) for f in ROUTE_EDITABLE}}, _route_edit),
       Op("route.add", {"title": Arg("text"), "place": Arg("text"), "description": Arg("text"),
                        "sourceUrl": Arg("text", required=False), "sourceName": Arg("text", required=False),
                        **{f: Arg("text", required=False) for f in ROUTE_EDITABLE
                           if f not in ("title", "place", "description")}}, _route_add))
