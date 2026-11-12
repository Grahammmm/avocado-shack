"""HASS-CHAT-1: a new hike worked out from the owner's words, so a live request ends in something that CAN go on the website.

G (2026-11-09): "I want to text and it should be able to figure everything out within the chat, and ask clarifying questions
if needed." The interpreter turns his words into a ``hike.create``; this pure step shapes that call before the editor sees it,
on the live site only (the private writer keeps every field, as before):

* sign-up: the website cannot take sign-ups yet (docs/hass/FEATURES.md: RSVP storage is not connected), and the live
  boundary allows a hike only with sign-up off. A guest limit he gave ("maximum of six people") becomes the sentence
  ``Limited to 6 people. Ask at the Shack to save a place.`` in the hike's description, with sign-up off, and the proposal
  says so in one line. Sign-up he asked for gets the same, with the plain reason.
* trail details the live boundary keeps for a person (the link to a saved route, how hard, how far, how long, access, the
  street address): left out of the draft, each named in one plain line, so the rest can go live. Nothing is moved into
  another field: the protection stays exactly as strong (hass/live_policy.py is not changed).
* the title: a title without a hike word is built from his place words ("Fiscalini Ranch bluff trail hike").
* the meeting place: a bare trail or route name is not a place to meet; he is asked once, with a suggestion when a saved
  route names the spot ("Meet at the Fiscalini Ranch trailhead in Cambria? Reply yes, or tell me where.").

Pure: no I/O, no clock. ``shape(ops, routes)`` returns a ``Shaped``; the conversation drafts ``ops`` and shows ``notes``, or,
with ``ask``, keeps the shaped call waiting for his answer (a bare yes takes ``ask["suggest"]``).
"""
from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, field

from hass import voice

HIKE_WORD = re.compile(r"\b(?:hikes?|walks?|strolls?|rambles?|treks?|outings?|climbs?|wanders?)\b", re.I)
# Words that name a spot people can stand at: a meeting point that has one is kept as he said it.
MEET_WORD = re.compile(r"\b(?:trail ?heads?|lots?|parking|gates?|entrances?|shop|shack|store|corner|streets?|st|ave|avenue|roads?|"
                       r"rd|blvd|boulevard|drive|dr|highway|hwy|pier|beach|bench|signs?|kiosk|caf[eé]|bridge|lodge|center|centre|"
                       r"church|school|library|stairs|steps|cove|turnout|pull ?out|bus stop|visitor|marker|end of|start of|"
                       r"across|near|outside|in front|by the|at the|next to|behind)\b|\d", re.I)
TRAIL_WORD = re.compile(r"\b(?:trails?|loops?|paths?|routes?|bluffs?|ridges?|ranch|preserve|reserve|hills?|mountains?|peaks?|"
                        r"canyons?|creek|falls|point)\b", re.I)
LIMIT_SENTENCE = re.compile(r"\s*Limited to \d+ (?:people|person)\. Ask at the Shack to save a place\.\s*")
# Fields of a hike the live boundary keeps for a person (live_policy.FIELDS["events"]); said in plain words, never dropped silently
TRAIL_FIELDS = {"difficulty": "how hard it is", "distance": "how far it is", "duration": "how long it takes",
                "accessNote": "the access note", "meetingAddress": "the street address"}
SIGNUP_TRUTH = "The website can't take sign-ups yet"
NO_SIGNUP = SIGNUP_TRUTH + ", so there's no sign-up button"
DESCRIPTION_LIMIT = 800  # content_model.TEXT_LIMITS["event"]["description"]
TITLE_LIMIT = 80
MEETING_LIMIT = 160  # content_model.TEXT_LIMITS["event"]["meetingPoint"]


@dataclass
class Shaped:
    ops: list
    notes: list = field(default_factory=list)   # plain lines for the proposal, in the order they apply
    ask: dict | None = None                       # {"question", "suggest" (meeting place text or None), "index" (the call asked about)}


def _fold(text) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(text)).split()).casefold()


def limit_sentence(n: int) -> str:
    return f"Limited to {n} {'person' if n == 1 else 'people'}. Ask at the Shack to save a place."


def _route_for(args, routes) -> dict | None:
    """The saved route the call names (trailId), else the one whose title is the meeting point or its longest space-bounded
    prefix (exact first, then longest folded title; first wins a tie); None when none."""
    routes = routes or {}
    if isinstance(args.get("trailId"), str) and isinstance(routes.get(args["trailId"]), dict):
        return routes[args["trailId"]]
    meet = _fold(args.get("meetingPoint") or "")
    best, best_len = None, 0
    for route in routes.values():
        title = _fold(route.get("title") or "") if isinstance(route, dict) else ""
        if title and (meet == title or meet.startswith(title + " ")) and len(title) > best_len:
            best, best_len = route, len(title)
    return best


def build_title(title, meeting_point):
    """A hike title: kept when it already names a hike or walk; else his place words plus "hike", using the meeting point when
    it is the longer form of the same place ("Fiscalini Ranch" + "Fiscalini Ranch bluff trail" -> "Fiscalini Ranch bluff trail
    hike"). None when there is nothing to build from or the result is too long."""
    title = " ".join(title.split()) if isinstance(title, str) else ""
    meet = " ".join(meeting_point.split()) if isinstance(meeting_point, str) else ""
    if title and HIKE_WORD.search(title):
        return title
    base = meet if meet and (not title or _fold(meet).startswith(_fold(title))) and not MEET_WORD.search(meet) else title
    base = re.sub(r"^(?:the|at)\s+", "", base, flags=re.I).strip()
    if not base:
        return None
    built = f"{base} hike"
    return built if len(built) <= TITLE_LIMIT else (title or None)


def only_a_trail(meeting_point, route) -> bool:
    """True when the meeting point names a trail or a saved route and no spot to stand at ("Fiscalini Ranch bluff trail",
    "Fiscalini Ranch"); a trailhead, a lot, a pier, a street or a number is a real meeting place."""
    if not isinstance(meeting_point, str) or not meeting_point.strip():
        return False
    if MEET_WORD.search(meeting_point):
        return False
    return route is not None or bool(TRAIL_WORD.search(meeting_point))


def suggest_meeting(route) -> str | None:
    """The suggested meeting place for a saved route: "<route title> trailhead, <town>"; None without a saved route, or when
    that place is too long for a hike's meeting place (a yes would only dead-end in a length refusal: he is asked where)."""
    if not isinstance(route, dict) or not isinstance(route.get("title"), str) or not route["title"].strip():
        return None
    place = route.get("place") if isinstance(route.get("place"), str) and route["place"].strip() else None
    suggestion = f"{route['title'].strip()} trailhead" + (f", {place.strip()}" if place else "")
    return suggestion if len(suggestion) <= MEETING_LIMIT else None


def meeting_question(title, suggestion) -> str:
    hike = voice.quote(title) if title else "the hike"
    if suggestion:
        spot, _, town = suggestion.partition(", ")
        where = f"the {spot}" + (f" in {town}" if town else "")
        return f"Where should people meet for {hike}? Meet at {where}? Reply yes, or tell me where."
    return f"Where should people meet for {hike}? Tell me the spot, like a trailhead or a parking lot."


def _signup(args, notes):
    """Sign-up off; a guest limit he gave goes into the description as a plain sentence (replacing an older one)."""
    asked = args.get("rsvpEnabled") is True
    cap = args.get("capacity")
    cap = cap if isinstance(cap, int) and not isinstance(cap, bool) and cap > 0 else None
    for key in ("capacity", "noCapacityLimit"):
        args.pop(key, None)
    args["rsvpEnabled"] = False
    if cap is not None:
        text = LIMIT_SENTENCE.sub(" ", args.get("description") or "").strip()
        sentence = limit_sentence(cap)
        if len(text) + len(sentence) + 1 <= DESCRIPTION_LIMIT:
            args["description"] = f"{text} {sentence}".strip()
            notes.append(f"{NO_SIGNUP}. I'll post it limited to {cap} {'person' if cap == 1 else 'people'}, and the page "
                         f"says {voice.quote(sentence)} so people ask you at the shop.")
            return
        notes.append(f"{NO_SIGNUP}, and the description is too full to add the guest limit, so it isn't on the page.")
        return
    if asked:
        notes.append(f"{NO_SIGNUP}. I'll post it without one, and people can ask you at the shop.")


def _trail_fields(args, routes, notes):
    trail = args.pop("trailId", None)
    if isinstance(trail, str):
        route = (routes or {}).get(trail)
        name = route.get("title") if isinstance(route, dict) and isinstance(route.get("title"), str) else None
        what = f"the link to the saved route {voice.quote(name)}" if name else "the link to a saved route"
        notes.append(f"I left out {what}: that can't go on the website from chat yet.")
    left = [(TRAIL_FIELDS[k], args.pop(k)) for k in list(TRAIL_FIELDS) if k in args]
    if left:
        said = ", ".join(f"{what} ({voice.quote(str(v))})" for what, v in left)
        notes.append(f"I left out {said}: trail details like that can't go on the website from chat yet.")


def shape(ops, routes=None, *, live=True, events=None) -> Shaped:
    """Shape every ``hike.create`` in ``ops`` (a deep copy; other calls are untouched). ``routes``: route ideas by id. Off the live
    site nothing changes. The first meeting place that is only a trail name stops at ``ask`` (the call keeps everything else).
    A ``hike.update`` that turns sign-up on or sets a guest limit becomes an offer (``ask`` kind "offer"): the nearest change that
    can go live, waiting for his yes; ``events``: the hikes by id, for its name and description."""
    ops = copy.deepcopy(ops) if isinstance(ops, list) else ops
    out = Shaped(ops)
    if not live or not isinstance(ops, list):
        return out
    if any(_capacity_conflict(call) for call in ops):  # one contradictory call: nothing in the batch is shaped or offered
        out.ask = {"kind": "offer", "question": CAPACITY_CONFLICT, "suggest": None, "ops": None}
        return out
    offer = _signup_offer(ops, events)
    if offer is not None:
        return offer
    for index, call in enumerate(ops):
        if not (isinstance(call, dict) and call.get("op") == "hike.create" and isinstance(call.get("args"), dict)):
            continue
        args = call["args"]
        route = _route_for(args, routes)  # before _trail_fields strips trailId: the route is only findable now
        title = build_title(args.get("title"), args.get("meetingPoint"))
        if title:
            args["title"] = title
        _signup(args, out.notes)
        _trail_fields(args, routes, out.notes)
        if out.ask is None and only_a_trail(args.get("meetingPoint"), route):
            suggestion = suggest_meeting(route)
            # "index": which call the question is about. trailId is gone from the call once shaped, so a later yes could not
            # rediscover the route from an abbreviated place ("Fiscalini"); the question keeps the call's place in the list.
            out.ask = {"kind": "meet", "question": meeting_question(args.get("title"), suggestion), "suggest": suggestion, "index": index}
    return out


CAPACITY_CONFLICT = "Please give either a guest limit or no limit, not both."


def _capacity_conflict(call) -> bool:
    """A hike.create/update that gives a positive guest limit and also says no limit."""
    if not (isinstance(call, dict) and call.get("op") in ("hike.create", "hike.update") and isinstance(call.get("args"), dict)):
        return False
    cap = call["args"].get("capacity")
    return isinstance(cap, int) and not isinstance(cap, bool) and cap > 0 and call["args"].get("noCapacityLimit") is True


def _signup_offer(ops, events):
    """A single hike.update that turns sign-up on (or sets a guest limit): the website can't take sign-ups, so the offer is the
    same update with sign-up left as it is and the limit written into the description. None for anything else."""
    if len(ops) != 1 or not (isinstance(ops[0], dict) and ops[0].get("op") == "hike.update" and isinstance(ops[0].get("args"), dict)):
        return None
    args = ops[0]["args"]
    if not (args.get("rsvpEnabled") is True or "capacity" in args or args.get("noCapacityLimit") is True):
        return None
    event = (events or {}).get(args.get("id")) if isinstance(args.get("id"), str) else None
    name = voice.quote(event["title"]) if isinstance(event, dict) and isinstance(event.get("title"), str) else "that hike"
    cap = args.get("capacity")
    cap = cap if isinstance(cap, int) and not isinstance(cap, bool) and cap > 0 else None
    rest = {k: v for k, v in args.items() if k not in ("rsvpEnabled", "capacity", "noCapacityLimit")}
    if cap is None or not isinstance(event, dict):
        if len(rest) > 1:  # other changes too: those go ahead, sign-up stays off
            return Shaped([{"op": "hike.update", "args": rest}], [f"{SIGNUP_TRUTH}, so I left sign-up as it is."])
        return Shaped(ops, ask={"kind": "offer", "question": f"{SIGNUP_TRUTH}, so I can't turn sign-up on for {name}. People can ask you "
                                                            "at the shop. Nothing changed.", "suggest": None, "ops": None})
    old = LIMIT_SENTENCE.sub(" ", rest.get("description", event.get("description") or "")).strip()
    sentence = limit_sentence(cap)
    rest["description"] = f"{old} {sentence}".strip()
    if len(rest["description"]) > DESCRIPTION_LIMIT:  # the yes would only dead-end in a length refusal: explain now, offer nothing
        return Shaped(ops, ask={"kind": "offer", "suggest": None, "ops": None, "question": (
            f"{SIGNUP_TRUTH}, and the description is too full to add the guest limit. Nothing changed. "
            "Send a shorter description with the guest limit, and I can try again.")})
    question = (f"{SIGNUP_TRUTH}, so I can't turn sign-up on for {name}. I can add {voice.quote(sentence)} to its description "
                "instead, so people ask you at the shop. Want that? Reply yes or no.")
    return Shaped(ops, ask={"kind": "offer", "question": question, "suggest": None, "ops": [{"op": "hike.update", "args": rest}]})


def with_meeting(ops, place, routes=None, index=None) -> list:
    """The waiting calls with the meeting place he confirmed. ``index`` is the call the question was asked about (``ask["index"]``):
    the place goes to that hike.create and no other. Without a usable index (an older stored question) it falls back to the first
    hike.create whose meeting place is only a trail."""
    ops = copy.deepcopy(ops)
    if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(ops):
        call = ops[index]
        if isinstance(call, dict) and call.get("op") == "hike.create" and isinstance(call.get("args"), dict):
            if not MEET_WORD.search(str(call["args"].get("meetingPoint") or "")):  # a real place he gave is never overwritten
                call["args"]["meetingPoint"] = place
                return ops
    for call in ops:
        if isinstance(call, dict) and call.get("op") == "hike.create" and isinstance(call.get("args"), dict) \
                and only_a_trail(call["args"].get("meetingPoint"), _route_for(call["args"], routes)):
            call["args"]["meetingPoint"] = place
            break
    return ops
