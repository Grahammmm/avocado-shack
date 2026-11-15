"""AV1104-03: generated home pages for the browser checks of the Visit hours status (read-only; writes nothing).

    python3 -B -m hass.tests.visit_hours_fixtures

Prints one JSON object {case name: the home page sitegen.render produces}. Each case is the real canonical content,
copied in memory, with only the hours and home notice varied; the rendering date is the explicit day given below.
"""

import copy
import dataclasses
import json
from datetime import date

from hass import sitegen
from hass.content_model import load_content

MAIN = ["Monday–Friday 9am–6pm", "Saturday 9am–5pm · Closed Sunday"]
THANKSGIVING = {"text": "We are closed Thursday for Thanksgiving.", "from": "2026-11-26", "until": "2026-11-26"}
# name: (hours lines, notice or None, the day the page is generated)
CASES = {
    "main": (MAIN, None, date(2026, 11, 16)),
    "minutes": (["Monday-Friday 9:30am - 12pm · Closed Saturday-Sunday"], None, date(2026, 11, 16)),
    "no_sunday": (["Monday–Saturday 9am–5pm"], None, date(2026, 11, 16)),
    "no_saturday": (["Monday–Friday 9am–6pm"], None, date(2026, 11, 16)),
    "all_closed": (["Closed Monday–Sunday"], None, date(2026, 11, 16)),
    "unreadable": ([MAIN[0], "Saturday by appointment · Closed Sunday"], None, date(2026, 11, 16)),
    "unreadable_first": (["Mon-Fri 9am-6pm", MAIN[1]], None, date(2026, 11, 16)),
    "holiday_notice": (MAIN, THANKSGIVING, date(2026, 11, 25)),
    "legacy_notice": (MAIN, {"text": "Open late this week.", "until": "2026-11-28"}, date(2026, 11, 25)),
    "bad_notice_dates": (MAIN, THANKSGIVING, date(2026, 11, 25)),
}


def build() -> dict[str, str]:
    base = load_content()
    pages = {}
    for name, (hours, notice, today) in CASES.items():
        store = copy.deepcopy(base.store)
        store["hours"] = list(hours)
        if notice:
            store["notice"] = dict(notice)
        files = sitegen.render(dataclasses.replace(base, store=store), today=today)
        page = files[sitegen.SITE_PREFIX + "index.html"].decode("utf-8")
        if name == "bad_notice_dates":  # the generator never writes this; a hand-edited page must still fail closed
            page = page.replace('data-until="2026-11-26"', 'data-until="soon"')
        pages[name] = page
    return pages


if __name__ == "__main__":
    print(json.dumps(build()))
