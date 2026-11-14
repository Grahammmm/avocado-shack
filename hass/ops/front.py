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


OPS = (
    Op("store.set_sections", {"order": Arg("text_list"), "hidden": Arg("text_list", False)}, _set_sections),
    Op("store.reset_sections", {}, lambda content, args, ctx: _clear(content, "homeSections")),
    Op("store.set_banner", {"text": Arg("text"), "start": Arg("date"), "end": Arg("date"),
                            "link": Arg("enum", False, choices=tuple(BANNER_LINKS))}, _set_banner),
    Op("store.clear_banner", {}, lambda content, args, ctx: _clear(content, "banner")),
)
