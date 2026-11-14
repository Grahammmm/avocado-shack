"""Front-end templates only: move home parts or schedule the top strip. No live ops."""
import re

from hass.content_model import HOME_SECTIONS, BANNER_LINKS, default_sections
from hass.ops.front import banner_problem, sections_value
from hass.skills.model import Skill, Slot, Trigger, Undo
from hass.skills.pages import _claim_stop
from hass.skills.shop import SkillStop, store_of, texts_of, today_of

PARTS = {"market": "market", "food": "market", "the food": "market", "food list": "market",
         "our-way": "our-way", "why we do it": "our-way", "our way": "our-way",
         "visit": "visit", "visit us": "visit", "visit block": "visit",
         "newsletter": "newsletter", "the newsletter": "newsletter"}
PART_REPLY = "I can move these parts: the food, why we do it, visit us, newsletter."
STYLE_REPLY = "I can't change colours, fonts or sizes yet. I wrote it down."  # the model's refusal sentence (refuse=)
STYLE_STOP = "Colours, fonts, sizes and new kinds of parts can't be changed by message."  # dispatch adds the backlog line
STYLE = re.compile(r"\b(?:colou?rs?|fonts?|sizes?|bigger|smaller|red|blue|new (?:part|section))\b", re.I)


class _StyleStop(SkillStop):
    backlog = "other"  # dispatch writes the request down and says so (dispatch.BACKLOG_REASONS)


def _style_stop():
    return _StyleStop(STYLE_STOP)


def _parts(values):
    out = []
    for value in values:
        key = " ".join(value.casefold().split())
        if STYLE.search(key):
            raise _style_stop()
        if key not in PARTS:
            raise SkillStop(PART_REPLY)
        out.append(PARTS[key])
    return out


def plan_sections(slots, ctx):
    store = store_of(ctx) or {}
    if any(STYLE.search(t) for t in texts_of(ctx)):
        raise _style_stop()
    if slots.get("reset"):
        if any(slots.get(k) for k in ("order", "hide", "show")):
            raise SkillStop("Change the home parts, or put them back? I can only do one.", "question")
        if "homeSections" not in store:
            raise SkillStop("The home parts are already that way.")
        return [{"op": "store.reset_sections", "args": {}}]
    if not any(slots.get(k) for k in ("order", "hide", "show")):
        raise SkillStop("Which home part should I move, hide or show?", "question")
    current = store.get("homeSections", default_sections())
    named = _parts(slots.get("order") or [])
    if len(set(named)) != len(named):
        raise SkillStop("Name each home part exactly once, in the new order.", "question")
    order = named + [r["id"] for r in current if r["id"] not in named]  # the parts he named first, the rest as they are
    hide, show = _parts(slots.get("hide", [])), _parts(slots.get("show", []))
    if set(hide) & set(show):
        raise SkillStop("Hide or show that part?", "question")
    hidden = ({r["id"] for r in current if not r["shown"]} | set(hide)) - set(show)
    rows, problems = sections_value(order, hidden)
    if problems:
        raise SkillStop(problems[0])
    if rows == current:
        raise SkillStop("The home parts are already that way.")
    return [{"op": "store.set_sections", "args": {"order": order, **({"hidden": [p for p in HOME_SECTIONS if p in hidden]} if hidden else {})}}]


def plan_banner(slots, ctx):
    store = store_of(ctx) or {}
    if slots.get("clear"):
        if any(slots.get(k) for k in ("text", "start", "end", "link")):
            raise SkillStop("Change the banner, or take it down? I can only do one.", "question")
        if "banner" not in store:
            raise SkillStop("There is nothing to put back.")
        return [{"op": "store.clear_banner", "args": {}}]
    if not slots.get("text"):
        raise SkillStop("What should the banner say?", "question")
    if not slots.get("end"):
        raise SkillStop("Until which day?", "question")
    args = {"text": slots["text"], "start": slots.get("start") or today_of(ctx).isoformat(), "end": slots["end"]}
    if slots.get("link"):
        args["link"] = slots["link"]
    if why := banner_problem(args, store, today_of(ctx)):
        raise SkillStop(why)
    if stop := _claim_stop([args["text"]], texts_of(ctx)):
        raise stop
    if args == store.get("banner"):
        raise SkillStop("The banner is already that way.")
    return [{"op": "store.set_banner", "args": args}]


_COMMON = dict(pack="front", targets=("site",), approval_class="A1", sandbox="preview", logs=("fields",), who="owner",
               side_effects=("none",), preview="home", approval="owner-yes", live_class="private-only",
               undo=Undo("revert", "none"), version=1)
FRONT_SECTIONS = Skill(
    name="front.sections", label="move or hide a home page part",
    summary="Reorder the four home parts, hide why we do it or newsletter, or put the original order back.",
    triggers=(Trigger("hide the newsletter part"), Trigger("move visit us above the food"),
              Trigger("put the home parts back"), Trigger("move the home parts around", "vague"),
              Trigger("hide the newslter part", "typo"), Trigger("hide why we do it and show the newsletter", "multi")),
    slots=(Slot("order", "text_list", hint="the parts from the top in the new order (the food, why we do it, visit us, "
                                           "newsletter); parts not named follow in their order"),
           Slot("hide", "text_list"), Slot("show", "text_list"), Slot("reset", "bool")),
    rules=("four-parts", "food-and-visit-stay", "templates-only", "not-already-true"), plan=plan_sections,
    edits=(("hass/content/store.json", "homeSections"), ("storefront-mockup/index.html", "home parts and links"),
           ("storefront-mockup/hike/index.html", "home links")),
    refuse=(("hide food or visit", "The food list and the visit block always stay on the home page."),
            ("another part", PART_REPLY), ("a style change", STYLE_REPLY)),
    cases="hass/tests/fixtures/skills/front/front.sections.jsonl", **_COMMON)
FRONT_BANNER = Skill(
    name="front.banner", label="put a dated banner across the top",
    summary="Schedule one short line across the top of home and hike, with an optional own-site link.",
    triggers=(Trigger("banner: Come say hello from tomorrow through Sunday"),
              Trigger("put a dated line across the top on every page"), Trigger("take down the dated banner"),
              Trigger("change the top banner", "vague"), Trigger("a baner across the top", "typo"),
              Trigger("banner: Come say hello and link to visit us", "multi")),
    slots=(Slot("text", "text", "unless:clear", ask="What should the banner say?", owner_words=True),
           Slot("start", "day", default="derive:today"),
           Slot("end", "day", "unless:clear", ask="Until which day?"),
           Slot("link", "enum", hint=", ".join(BANNER_LINKS)), Slot("clear", "bool")),
    rules=("short-line", "dated-window", "own-site-link", "no-price", "claim-in-his-words", "not-already-true"),
    plan=plan_banner, edits=(("hass/content/store.json", "banner"), ("storefront-mockup/index.html", "top strip"),
                             ("storefront-mockup/hike/index.html", "top strip")),
    refuse=(("outside link", "The banner cannot contain a web address, email or handle."),
            ("long window", "The banner end must be on or after its start, at most 31 days apart.")),
    cases="hass/tests/fixtures/skills/front/front.banner.jsonl", **_COMMON)
SKILLS = (FRONT_SECTIONS, FRONT_BANNER)
