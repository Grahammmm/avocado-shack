"""Dated home-page notice rendering, preview text and historical artifact checks.

Without JavaScript an expired notice remains until the next regeneration.
Consistency checks accept the exact pre-expiry artifact, never unrelated drift.
"""

import html
from datetime import date
from pathlib import Path

from hass.content_model import iso_day, shop_today

BANNER_JS = ("<script>(()=>{const swap=()=>{const day=new Date().toLocaleDateString('en-CA',{timeZone:'America/Los_Angeles'});"
             "document.querySelectorAll('[data-banner]').forEach(b=>{const live=day>=b.dataset.start&&day<=b.dataset.end;"
             "b.hidden=!live;b.style.display=live?'':'none';const d=b.previousElementSibling;"
             "d.hidden=live;d.style.display=live?'none':''})};swap();setInterval(swap,1000);"
             "document.addEventListener('visibilitychange',swap);window.addEventListener('pageshow',swap)})()</script>\n")


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


NOTICE_JS = ("<script>(()=>{const expire=()=>document.querySelectorAll('.home-notice').forEach(n=>{"
             "if(new Date().toLocaleDateString('en-CA',{timeZone:'America/Los_Angeles'})>n.dataset.until)n.hidden=true});"
             "expire();setInterval(expire,1000);document.addEventListener('visibilitychange',expire);"
             "window.addEventListener('pageshow',expire)})()</script>\n")


def live_text(notice, today=None) -> str | None:
    """The preview expects no notice once its last day is before Pacific today."""
    notice = notice or {}
    live = isinstance(notice.get("until"), str) and notice["until"] >= (today or shop_today()).isoformat()
    return notice.get("text") if live else None


def slots(notice, today: str) -> dict[str, str]:
    """No notice, or an expired notice: both template slots stay empty."""
    paragraph = (f'<p class="home-notice" data-until="{html.escape(notice["until"])}" role="status">'
                 if notice and notice["until"] >= today else "")
    return {"store.noticeHtml": paragraph and paragraph + html.escape(notice["text"], quote=False) + "</p>",
            "store.noticeScript": paragraph and NOTICE_JS}


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
    if last is not None and last < today:
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
