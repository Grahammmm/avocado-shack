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
def _page_claims(values, ctx):
    if stop := _claim_stop(values, texts_of(ctx)):
        raise stop


def _literal_spans(text, literals):
    """Spans of complete, balanced "..." or curly double-quoted runs whose inside is exactly one supplied page text."""
    spans = []
    if text.count('"') % 2 == 0:
        spans += [m.span() for m in re.finditer(r'"([^"]*)"', text) if m.group(1) in literals]
    opened, curly = None, []
    for i, ch in enumerate(text):
        if ch == "\u201c" and opened is None:
            opened = i
        elif ch == "\u201d" and opened is not None:
            curly.append((opened, i + 1))
            opened = None
        elif ch in "\u201c\u201d":  # nested or stray: ambiguous, protect no curly span in this text
            return spans
    if opened is None:
        spans += [(a, b) for a, b in curly if text[a + 1:b - 1] in literals]
    return spans


def _outside_literals(texts, args):
    """The request texts to scan for style/layout words: quoted copy equal to the supplied title, intro or paragraph is blanked."""
    paragraphs = args.get("paragraphs")
    values = [args.get("title"), args.get("intro"), *(paragraphs if isinstance(paragraphs, (list, tuple)) else ())]
    literals = {v for v in values if isinstance(v, str) and v}
    out = []
    for t in texts:
        chars = list(t)
        for a, b in _literal_spans(t, literals) if literals else ():
            chars[a:b] = " " * (b - a)
        out.append("".join(chars))
    return out


def plan_page(slots, ctx):
    from hass.ops.front import page_value
    page = slots.get("template")
    args = {"page": page, **{k: slots[k] for k in ("title", "intro", "paragraphs") if k in slots}}
    if slots.get("hide") and len(args) > 1:
        raise SkillStop("Hide the page, or change its words? I can only do one.", "question")
    if any(STYLE.search(t) or re.search(r"\b(?:layout|html)\b", t, re.I) for t in _outside_literals(texts_of(ctx), args)):
        raise _style_stop()
    _, why = page_value(store_of(ctx) or {}, args, bool(slots.get("hide")))
    if why:
        raise SkillStop(why)
    _page_claims([v for k, v in args.items() if k in ("title", "intro")] + args.get("paragraphs", []), ctx)
    return [{"op": "store.hide_page" if slots.get("hide") else "store.set_page", "args": args}]


def plan_faq(slots, ctx):
    from hass.ops.front import faq_value
    if not slots.get("question"):
        raise SkillStop("What is the question?", "question")
    remove = bool(slots.get("remove"))
    if remove and slots.get("answer"):
        raise SkillStop("Remove the question, or change its answer? I can only do one.", "question")
    if not remove and not slots.get("answer"):
        raise SkillStop("What should the answer say?", "question")
    args = {"question": slots["question"], **({"answer": slots["answer"]} if not remove else {})}
    _, why = faq_value(store_of(ctx) or {}, args, remove)
    if why:
        raise SkillStop(why)
    if not remove:
        _page_claims(list(args.values()), ctx)
    return [{"op": "store.remove_faq" if remove else "store.set_faq", "args": args}]


_PAGE_COMMON = {**_COMMON, "logs": ("subjects", "fields")}
_PAGE_EDITS = tuple(("hass/content/store.json", key) for key in ("pageAbout", "pageGettingHere", "pagePolicies", "pageFaq")) + tuple(
    ("storefront-mockup/" + path + "/index.html", "page and footer links") for path in ("about", "getting-here", "policies", "faq")) + (
    ("storefront-mockup/index.html", "footer links"), ("storefront-mockup/hike/index.html", "footer links"))
FRONT_PAGE = Skill(
    name="front.page", label="fill or hide a fixed template page",
    summary="Fill or hide About, Getting here, Our policies or Questions using the owner's words and a fixed template.",
    triggers=(Trigger("create the Getting here page"), Trigger("fill the About template"), Trigger("take Our policies page off the site"),
              Trigger("change a template page", "vague"), Trigger("fill the geting here page", "typo"),
              Trigger("About template with a title and intro", "multi")),
    slots=(Slot("template", "enum", True, ask="Which page: About, Getting here, Our policies or Questions?",
                hint="about, getting-here, policies, faq"), Slot("title", "text", owner_words=True),
           Slot("intro", "text", owner_words=True), Slot("paragraphs", "text_list", owner_words=True), Slot("hide", "bool")),
    rules=("four-pages", "templates-only", "no-price", "no-outside-links", "claim-in-his-words", "not-already-true"),
    plan=plan_page, edits=_PAGE_EDITS, refuse=(("another page", "I can make an About, Getting here, Our policies or Questions page. Which one?"),
                                              ("outside link", "Page words cannot contain a web address, email or handle.")),
    cases="hass/tests/fixtures/skills/front/front.page.jsonl", **_PAGE_COMMON)
FRONT_FAQ = Skill(
    name="front.faq", label="add, edit or remove a question and answer",
    summary="Add or edit a question and answer on Questions, or remove a question; the first entry shows the page.",
    triggers=(Trigger("add an FAQ entry"), Trigger("add a frequently asked question"), Trigger("Questions: Is parking nearby? Ask us at the shop."),
              Trigger("remove the question about opening hours"), Trigger("change an answer on Questions", "vague"),
              Trigger("add a frequntly asked queston", "typo"), Trigger("add a question and its answer", "multi")),
    slots=(Slot("question", "text", True, ask="What is the question?", owner_words=True),
           Slot("answer", "text", "unless:remove", ask="What should the answer say?", owner_words=True), Slot("remove", "bool")),
    rules=("twenty-questions", "question-mark", "no-price", "no-outside-links", "claim-in-his-words", "not-already-true"),
    plan=plan_faq, edits=_PAGE_EDITS, refuse=(("outside link", "Page words cannot contain a web address, email or handle."),
                                           ("full page", "Questions: at most 20 entries are allowed.")),
    cases="hass/tests/fixtures/skills/front/front.faq.jsonl", **_PAGE_COMMON)
SKILLS = (FRONT_SECTIONS, FRONT_BANNER, FRONT_PAGE, FRONT_FAQ)
