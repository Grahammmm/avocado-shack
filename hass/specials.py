"""AVO-SPECIALS-1: the "This week's specials" section of the home page (which is also the shop page: the catalog
lives on it).

How a special can never show after its last day (two checks that use the same rule, last day inclusive, Pacific):
  1. BUILD: ``slots`` renders only the specials with start <= today <= end at generation time, and nothing at all
     (no heading, no box, no script) when none are active. Every generation (each approved change, each publish)
     uses the Pacific date of that moment.
  2. BROWSER: each card carries data-start / data-end and a tiny script (SPECIALS_JS) hides a card whose last day
     is before the visitor's Pacific day (or whose first day is after it) and hides the whole section when no card
     is left, so a page built on Monday cannot show Tuesday's expired special on Wednesday. It re-checks every
     second, on tab focus and on back/forward cache restore. Without JavaScript the build-time check alone
     applies; the next generation removes the expired card from the file.
Prices: the site shows no prices anywhere else; the only text that may hold one is the owner-written deal line,
shown exactly as typed (HTML-escaped).
"""

from __future__ import annotations

import html
from datetime import date

from hass.content_model import active_specials, iso_day

SPECIALS_JS = '<script src="/specials.js"></script>\n'  # AV1052-03: the runtime is storefront-mockup/specials.js, never inline (CSP)


def _card(sp: dict, products: dict) -> str:
    product = products.get(sp.get("product"))
    shown = product if isinstance(product, dict) and product.get("status") == "active" else None  # a hidden or held product shows no picture
    picture = ""
    if shown and sp.get("picture"):
        alt = shown.get("imageAlt") or shown.get("name") or ""
        picture = (f'<img class="special-image" src="{html.escape(shown["image"], quote=True)}" '
                   f'alt="{html.escape(alt, quote=True)}" loading="lazy" width="120" height="120">')
    link = (f'<a class="text-link special-link" href="?item={html.escape(sp["product"], quote=True)}#market">See it below</a>'
            if shown else "")
    return (f'<li data-start="{sp["start"]}" data-end="{sp["end"]}">{picture}<div><h3>{html.escape(sp["title"], quote=False)}</h3>'
            f'<p class="special-deal">{html.escape(sp["deal"], quote=False)}</p>{link}</div></li>')


def slots(store: dict, products: list, today: date) -> dict[str, str]:
    """{"specials.html", "specials.script"}: both empty when no special is active on ``today`` (nothing else changes)."""
    live = active_specials(store, today)
    if not live:
        return {"specials.html": "", "specials.script": ""}
    by_id = {p["id"]: p for p in products if isinstance(p, dict) and "id" in p}
    cards = "".join(_card(sp, by_id) for sp in live)
    section = ('<section class="weekly-specials" aria-labelledby="specials-heading"><p class="label">FROM MICHAEL</p>'
               f'<h2 id="specials-heading">This week’s specials</h2><ul>{cards}</ul></section>\n')
    return {"specials.html": section, "specials.script": SPECIALS_JS}


def change_days(store: dict, today: date) -> list[date]:
    """Days up to ``today`` on which the set of active specials changed (a first day, or the day after a last day):
    a page generated on any of them is a consistent earlier artifact of the same content."""
    days = set()
    for sp in store.get("specials") or []:
        for day in (iso_day(sp.get("start")), iso_day(sp.get("end"))):
            if day is not None and day < today:
                days.update(d for d in (day, date.fromordinal(day.toordinal() + 1)) if d < today)
    return sorted(days)
