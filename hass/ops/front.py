"""Private front-end pack: four typed store operations; selective history undo is unchanged."""
import copy
from datetime import date

from hass.content_model import (HOME_SECTIONS, BANNER_LINKS, BANNER_PAGES, MAX_BANNER_AHEAD, default_sections,
                                shop_today, validate_banner, validate_sections)
from hass.ops import Arg, Op, Refused
from hass.ops.store import _touch


def sections_value(order, hidden):
    rows = [{"id": part, "shown": part not in hidden} for part in order]
    problems = []
    validate_sections(problems, rows)
    if any(part not in HOME_SECTIONS for part in hidden) or len(set(hidden)) != len(hidden):
        problems.append("Hidden parts must be unique home part names.")
    return rows, problems


def banner_problem(banner, store, today):
    problems = []
    validate_banner(problems, banner)
    if problems:
        return problems[0]
    from hass.skills.shop import price_problem
    if why := price_problem(banner["text"]):
        return why
    if (date.fromisoformat(banner["start"]) - today).days > MAX_BANNER_AHEAD:
        return "The banner cannot start more than 60 days ahead."
    if date.fromisoformat(banner["end"]) < today:
        return "That banner would already be over. Which days should it show?"
    page = BANNER_PAGES.get(banner.get("link"))
    if page and not store.get(page, {}).get("shown"):
        return "That page is not shown. Choose a shown page for the banner link."
    return None


def _set_sections(content, args, ctx):
    rows, problems = sections_value(args["order"], args.get("hidden", []))
    if problems:
        return Refused(problems[0])
    if rows == content.store.get("homeSections", default_sections()):
        return Refused("The home parts are already that way.")
    before = copy.deepcopy(content.store)
    content.store["homeSections"] = rows
    return _touch(before, content.store)


def _clear(content, key):
    if key not in content.store:
        return Refused("There is nothing to put back.")
    before = copy.deepcopy(content.store)
    del content.store[key]
    return _touch(before, content.store)


def _set_banner(content, args, ctx):
    if why := banner_problem(args, content.store, shop_today(ctx.now)):
        return Refused(why)
    if args == content.store.get("banner"):
        return Refused("The banner is already that way.")
    before = copy.deepcopy(content.store)
    content.store["banner"] = copy.deepcopy(args)
    return _touch(before, content.store)


def page_value(store, args, hide=False):
    from hass.content_model import INFO_PAGES, validate_page
    page = args.get("page")
    if page not in INFO_PAGES:
        return None, "I can make an About, Getting here, Our policies or Questions page. Which one?"
    key, title = INFO_PAGES[page]
    old = store.get(key)
    if hide:
        if not old or not old["shown"]:
            return None, "That page is already hidden."
        value = {**copy.deepcopy(old), "shown": False}
    else:
        value = {**copy.deepcopy(old or {"title": title, "intro": "", **({"entries": []} if page == "faq" else {})}),
                 **{k: copy.deepcopy(v) for k, v in args.items() if k != "page"}, "shown": True}
        if page == "faq" and "paragraphs" in args:
            return None, "Use front.faq to add a question and its answer."
    problems = []
    validate_page(problems, key, value)
    if problems:
        return None, problems[0]
    if value == old:
        return None, "The page is already that way."
    return value, None


def faq_value(store, args, remove=False):
    from hass.content_model import validate_page
    value = copy.deepcopy(store.get("pageFaq", {"shown": False, "title": "Questions", "entries": []}))
    folded = lambda q: " ".join(q.casefold().split())
    index = next((i for i, entry in enumerate(value["entries"]) if folded(entry["q"]) == folded(args["question"])), None)
    if remove:
        if index is None:
            return None, "That question is not on the Questions page."
        value["entries"].pop(index)
        if not value["entries"]:
            value["shown"] = False
    else:
        entry = {"q": args["question"], "a": args["answer"]}
        if index is None:
            value["entries"].append(entry)
        else:
            value["entries"][index] = entry
        value["shown"] = True
    problems = []
    validate_page(problems, "pageFaq", value)
    if problems:
        return None, problems[0]
    if value == store.get("pageFaq"):
        return None, "That question and answer are already there."
    return value, None


def _page_op(content, args, ctx, hide=False, faq=False, remove=False):
    from hass.content_model import INFO_PAGES
    value, why = faq_value(content.store, args, remove) if faq else page_value(content.store, args, hide)
    if why:
        return Refused(why)
    before = copy.deepcopy(content.store)
    content.store["pageFaq" if faq else INFO_PAGES[args["page"]][0]] = value
    return _touch(before, content.store)


OPS = (
    Op("store.set_sections", {"order": Arg("text_list"), "hidden": Arg("text_list", False)}, _set_sections),
    Op("store.reset_sections", {}, lambda content, args, ctx: _clear(content, "homeSections")),
    Op("store.set_banner", {"text": Arg("text"), "start": Arg("date"), "end": Arg("date"),
                            "link": Arg("enum", False, choices=tuple(BANNER_LINKS))}, _set_banner),
    Op("store.clear_banner", {}, lambda content, args, ctx: _clear(content, "banner")),
    Op("store.set_page", {"page": Arg("enum", choices=tuple(BANNER_PAGES)), "title": Arg("text", False),
                           "intro": Arg("text", False), "paragraphs": Arg("text_list", False)}, _page_op),
    Op("store.hide_page", {"page": Arg("enum", choices=tuple(BANNER_PAGES))},
       lambda content, args, ctx: _page_op(content, args, ctx, hide=True)),
    Op("store.set_faq", {"question": Arg("text"), "answer": Arg("text")},
       lambda content, args, ctx: _page_op(content, args, ctx, faq=True)),
    Op("store.remove_faq", {"question": Arg("text")},
       lambda content, args, ctx: _page_op(content, args, ctx, faq=True, remove=True)),
)
