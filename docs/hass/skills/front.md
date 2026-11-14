# Front-end skills, part 1 (AVB-19-B1)

Two skills on top of four private-only store ops. Code: `hass/skills/front.py`, ops `hass/ops/front.py`. Design: the
reviewed AVB-19 front-end pack design (sha256 ae6e151a…), sections 2, 3 (`homeSections`, `banner`), 4.1 and 4.2.
Templates only: the owner's words go into text slots, HTML-escaped; nothing else
about the page can be changed by message. Approval, preview, claims and undo are the existing ones (`yes <code>`, `undo`).

| Skill | What Mike says (examples) | Plans |
|---|---|---|
| `front.sections` | "hide the newsletter part" · "move visit us above the food" · "put the home parts back" | `store.set_sections` / `store.reset_sections` |
| `front.banner` | "banner: Come say hello from tomorrow through Sunday" · "take down the dated banner" | `store.set_banner` / `store.clear_banner` |

## Content (optional keys of `hass/content/store.json`; absent = today's page, byte for byte)

- `homeSections`: four rows `{"id", "shown"}`, ids `market`, `our-way`, `visit`, `newsletter`, each once. `market` and
  `visit` are always shown. The hero stays first; specials and the notice stay above it. A hidden part's header-nav and
  footer links are left out on home and hike. Section text lives in `hass/templates/home/<id>.html`.
- `banner`: `{"text", "start", "end", "link"?}`. One line, 3 to 80 characters with 3 letters, no web address, email,
  handle or price; real days, `end` on or after `start`, at most 31 days apart; `start` at most 60 days ahead (plan and
  op). `link` is one of the shop's own places (`visit`, `market`, `hike`; the four page names wait for B2 and render
  without a link until their page is shown). `banner.text` is scanned by the claims gate like `notice.text`.

## Top strip and dates

The banner is the existing top strip (`div.preview`) on home and hike; 404 keeps the default line. Both lines are in the
page; the server shows the one for its render day, and `notice.BANNER_JS` swaps them by the browser's Pacific day (every
second, on `visibilitychange` and `pageshow`), so a page made before the start day still turns it on and after the end
day off. `notice.stale_paths` accepts an earlier exact render from the day before the start, the start day and the day
after the end, on the same day as notice and specials (a mix no real day could make stays stale).

## Preview

A store record that changes `homeSections` adds `sections` (the shown ids in order) to the preview target; one that
changes `banner` adds `banner` (`{text, link?}`, or `null` when cleared or already over) and, only when the banner starts
after today, `effectiveDay`. With `effectiveDay` the preview browser's clock is fixed to that Pacific day before the page
loads (`page.clock.setFixedTime`); the served files keep the real clock and never contain it. `screenshot.cjs` refuses a
bad `effectiveDay` before loading the browser, and adds `sectionsShown`, `bannerShown` / `bannerGone`, `pageLoaded` and
`noHorizontalOverflow` for these targets.

## Live

All four ops are in `live_policy.PRIVATE`; none is in `LIVE`. G chooses later which may go public.
