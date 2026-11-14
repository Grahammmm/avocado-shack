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

# Front-end skills, part 2 (AVB-19-B2)

Two more skills and four more private-only store ops, same files. Design sections 2, 3 (`pageAbout`, `pageGettingHere`,
`pagePolicies`, `pageFaq`), 4.3 and 4.4.

| Skill | What Mike says (examples) | Plans |
|---|---|---|
| `front.page` | "create the Getting here page: Parking is right behind the shop." · "fill the About template" · "hide Our policies page" | `store.set_page` / `store.hide_page` |
| `front.faq` | "Questions: Is parking nearby? Yes, right behind the shop." · "remove the question about opening hours" | `store.set_faq` / `store.remove_faq` |

## Pages

Exactly four fixed pages share one template, `hass/templates/info/index.html`: `about/` (About), `getting-here/`
(Getting here), `policies/` (Our policies) and `faq/` (Questions). No other page can be made by message; the header nav
does not change.

- `pageAbout`, `pageGettingHere`, `pagePolicies`: `{"shown", "title", "intro", "paragraphs"}`. Title 3 to 60
  characters, intro up to 300, 1 to 6 paragraphs of 20 to 600 characters; every text is one line with no web address,
  email, handle or price, HTML-escaped; a claim word he did not say stops the plan (as for the banner).
- `pageFaq`: `{"shown", "title", "entries"}` (`intro` optional). At most 20 entries `{"q", "a"}`; a question is 5 to 120
  characters and ends in `?`, an answer 2 to 600; the same question (case and spaces folded) replaces its answer. Each
  entry renders as `<details><summary>question</summary><p>answer</p></details>`. The first entry shows the page in the
  same draft; removing the last entry hides it.
- A page that is not shown is a `noindex` "Nothing here yet" placeholder, is never published (`sitegen.publish_files`)
  and has no banner or footer links. A shown page adds one footer link on every generated page (home, hike and the shown
  pages). The 404 page (a fixed file, not rendered from store content) is left unchanged: it gets no footer links, so no
  new release path opens.
- `hide_page` keeps the words with `shown: false`; `undo` of a creation removes the key (the placeholder comes back).

## Routing and the old FAQ refusal

`page.faq` is retired (`status="retired"`, its name never reused). The dispatcher's code path that sent exact FAQ asks to
that refusal asks `registry.get("page.faq")`, which returns nothing for a retired skill, so "add an FAQ" now goes to the
model and `front.faq` (tested in `hass/tests/test_front_pages.py`, no dispatcher edit). A bare "add an FAQ" names no
question, so the reply is "What is the question?": the model's guessed words are not his and are dropped.
`page.about` still changes the home page story; its "new About page" refusal now points at `front.page` (version 2).

## Preview and release

A store record that changes a page key previews that page (`kind: store`, `page`, `pageTitle`); `screenshot.cjs`
accepts only the four page paths and adds `pageTitle`. The release engine (`publish_live.py`) allows exactly the four
page files for a store change; `editor.GENERATED_PATHS`, `REVISION_PATHS`, `design_check` and the static-site check list
the template and the four paths. All four new ops are in `live_policy.PRIVATE`; none is in `LIVE`.
