"""Dated home-page notice rendering, preview text and historical artifact checks.

Without JavaScript a notice appears on its first day, and an expired one goes, at the next regeneration.
Consistency checks accept the exact earlier notice-phase artifact (before its first day, on its last), never unrelated drift.
"""

import html
from datetime import date
from pathlib import Path

from hass.content_model import iso_day, notice_days, shop_today

BANNER_JS = '<script src="/banner.js"></script>\n'  # AV1052-03: the runtime is storefront-mockup/banner.js, never inline (CSP)


def banner_link(banner, store):
    from hass.content_model import BANNER_LINKS, BANNER_PAGES
    link = banner.get("link")
    page = BANNER_PAGES.get(link)
    return BANNER_LINKS.get(link) if not page or store.get(page, {}).get("shown") else None


def banner_target(banner, store, today):
    if not banner or not banner["start"] <= today.isoformat() <= banner["end"]:
        return None
    link = banner_link(banner, store)
    return {"text": banner["text"], **({"link": link} if link else {})}


NOTICE_JS = '<script src="/notice.js"></script>\n'  # AV1052-03: the runtime is storefront-mockup/notice.js, never inline (CSP)


def live_text(notice, today=None) -> str | None:
    """The preview expects the notice only from its first day (none saved: already started) through its last Pacific day."""
    notice = notice or {}
    day = (today or shop_today()).isoformat()
    first = notice.get("from")
    live = isinstance(notice.get("until"), str) and notice["until"] >= day and not (isinstance(first, str) and first > day)
    return notice.get("text") if live else None


def window_target(notice, today=None) -> dict | None:
    """AV2152-08: {text, from, until, state} for a notice with an explicit first day (state scheduled, active or ended on
    ``today``), None for a legacy or absent one; an invalid schedule raises ValueError (the preview target is unreadable)."""
    if not isinstance(notice, dict) or "from" not in notice:
        return None
    days = notice_days(notice)
    if days is None:
        raise ValueError("bad notice schedule")
    first, last = days
    day = today or shop_today()
    return {"text": notice["text"], "from": first.isoformat(), "until": last.isoformat(),
            "state": "scheduled" if day < first else "active" if day <= last else "ended"}


def slots(notice, today: str) -> dict[str, str]:
    """No notice, or an expired notice: both template slots stay empty. Before its explicit first day the paragraph is
    carried hidden with ``data-from``; the page script reveals it that day (no JavaScript: at the next regeneration)."""
    if not notice or notice["until"] < today:
        return {"store.noticeHtml": "", "store.noticeScript": ""}
    first = notice.get("from")
    attrs = (f' data-from="{html.escape(first)}"' if first else "") + f' data-until="{html.escape(notice["until"])}"'
    hidden = " hidden" if first and today < first else ""
    return {"store.noticeHtml": f'<p class="home-notice"{hidden}{attrs} role="status">' + html.escape(notice["text"], quote=False) + "</p>",
            "store.noticeScript": NOTICE_JS}


def stale_paths(content, root: Path) -> list[str]:
    """Allow an earlier exact render of a notice or special that has since expired; never ignore corruption,
    missing files or symlinks.

    Writes and publishing continue using the current render, removing expired notices and specials.
    The notice and specials clock overrides do not change the selection freshness clock. A path is stale only when
    it differs from the current render and from every earlier-day render the content allows. Both dated sections
    always use the SAME earlier day (a notice's last day and the day after, each day the set of active specials
    changed), so a mix no real day could produce, such as an expired notice with a later special, stays stale.

    A special also adds the day before its start: a page generated then correctly omits it, and once its first
    day arrives that unchanged page is still an earlier exact render (``specials.change_days`` has no such day).
    """
    from hass.sitegen import diff_paths, render, shop_today
    from hass.specials import change_days

    today = shop_today()
    templates = Path(root) / "hass" / "templates"
    stale = diff_paths(render(content, templates, today=today), root)
    days = set(change_days(content.store, today))
    for sp in content.store.get("specials") or []:
        start = iso_day(sp.get("start")) if isinstance(sp, dict) else None
        if start is not None and date.min < start <= today:
            days.add(date.fromordinal(start.toordinal() - 1))
    notice = content.store.get("notice")
    last = iso_day(notice.get("until")) if isinstance(notice, dict) else None
    first = iso_day(notice.get("from")) if isinstance(notice, dict) else None
    if first is not None and date.min < first <= today:  # AV2152-08: the render before its first day (hidden)
        days.add(date.fromordinal(first.toordinal() - 1))
    if last is not None and last < today:  # ... and the active render on its last day
        days.add(last)
        if last < date.max:
            days.add(date.fromordinal(last.toordinal() + 1))
    banner = content.store.get("banner")  # AVB-19: the day before it shows, its first day and the day after its last
    start, end = (iso_day(banner.get("start")), iso_day(banner.get("end"))) if isinstance(banner, dict) else (None, None)
    for day, offset in ((start, -1), (start, 0), (end, 1)):
        if day is not None and date.min.toordinal() <= day.toordinal() + offset <= date.max.toordinal():
            days.add(date.fromordinal(day.toordinal() + offset))
    for day in sorted(d for d in days if d < today):
        if not stale:
            return stale
        before = diff_paths(render(content, templates, today=today, notice_today=day, specials_today=day, banner_today=day), root)
        stale = [rel for rel in stale if rel in before]
    return stale
