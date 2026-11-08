"""Dated home-page notice rendering, preview text and historical artifact checks.

Without JavaScript an expired notice remains until the next regeneration.
Consistency checks accept the exact pre-expiry artifact, never unrelated drift.
"""

import html
from datetime import date
from pathlib import Path

from hass.content_model import shop_today

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
    it differs from the current render and from every earlier-day render the content allows (the day a notice's
    last day was, and each day the set of active specials changed).
    """
    from hass.sitegen import diff_paths, render, shop_today
    from hass.specials import change_days

    today = shop_today()
    templates = Path(root) / "hass" / "templates"
    stale = diff_paths(render(content, templates, today=today), root)
    notice = content.store.get("notice")
    notice_days = [date.fromisoformat(notice["until"])] if notice and notice["until"] < today.isoformat() else []
    for notice_day in [None, *notice_days]:
        for special_day in [None, *change_days(content.store, today)]:
            if not stale:
                return stale
            if notice_day is None and special_day is None:
                continue
            before = diff_paths(render(content, templates, today=today, notice_today=notice_day,
                                       specials_today=special_day), root)
            stale = [rel for rel in stale if rel in before]
    return stale
