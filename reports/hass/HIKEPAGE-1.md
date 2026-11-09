# HASS-HIKEPAGE-1: the full hike page, spots left and the RSVP flow (design and audit)

Card t_e5d28414 · repo Grahammmm/avocado-shack · branch `rb/hass-hikepage-1` from `origin/main` dead9f7 · 2026-11-08 PST.
The design itself is `docs/hass/HIKE-PAGE.md` (decisions for G on its first lines). This report is the evidence, the audit and the card plan.
**State reached: documents written and in a docs-only PR. Not reviewed, not merged, nothing verified live.**

## 1. In plain words

* **What exists today.** The live hike page is a static page. It shows a sample Point Buchon invitation, a real interactive Aerial/Topo map with an elevation profile (Point Buchon only), the stats, meeting details and a sample RSVP form that sends nothing. A real hike gets a plainer card, with no map for Cass Hill or Fiscalini, no spots line and, on the live site, only "To join, ask at the Shack."
* **The RSVP form G described does not exist on the live site.** `/api/community` and `/api/community/rsvps` are a local test server on AgentOrange, not part of the Cloudflare site. The live page cannot take or count an RSVP.
* **Spots logic is half there.** A hike can already carry a `capacity`, the local API counts seats and refuses overbooking, and the page code already says "N places available" and "This hike is full" **when that API answers**. There is no default of 6, no cancel, no way to add a walk-in without an email, and nothing on the live static page.
* **Recommended topo map:** the method Point Buchon already uses, built once per route from USGS topo and OpenStreetMap data and served from our own site (free, fast, no visitor tracking), shown for every hike whose route has files, with an official-map link where it does not.
* **Recommended spot-count approach:** Hass keeps a private roster on the box and publishes **numbers only** as its own capped release class (option b), page API-first so a real backend (option a) can replace it later. Option c (a rebuild per RSVP) is rejected because it spends the shared 10-a-day limit.
* **Monday minimum:** one small page card so a hike with a limit **shows its limit** ("Limited to 6 people · availability unconfirmed; ask at the Shack", a capacity-only line, never a count). Everything else (live count, waitlist, who is coming, the full per-hike page) comes after.

## 2. What was done (and not done)

Read only on the box. Files read: the live site checkout (`~/.local/share/hass/theavocadoman-site`: `hike/index.html`, `community.js`, `community.json`, `hiking.css`, `hiking-preview.json`, `trail-explorer.js`), the repo's `hass/sitegen.py`, `hass/content_model.py`, `hass/ops/hikes.py`, `hass/ops/routes.py`, `hass/live_policy.py`, `hass/corrlog.py`, `hass/morning_report.py`, `hass/conversation.py` (guest-count parts), `storefront-mockup/community-server.py`, `storefront-mockup/README.md`, `reports/hass/SKILLS-SPEC.md`, the HIKES-1 PR #530 (`docs/hass/skills/hikes.md`, head 57d0689), `reports/hass/{STORE-TEST-1,E2E-HIKE-1,HIKE-FLOW-1}.md`, `docs/hass/{COMMANDS,PUBLISHING,VOICE,OPERATIONS,SUPPORT,IMPLEMENTATION,MAC_RUNBOOK}.md`, `reports/hiking-club/{TRAIL_MAP_SOURCES.txt,route-map-sources-2026-11.md}`, and two public policy pages (OSM tile policy, USGS credits).

Also opened, as status only: `community-data/migration-api-verification.json` and `hosting-sunset-status.json` (no personal data); `community-data/sandbox.env` was printed with its value masked. **Not read:** `community.sqlite3` or any RSVP row, the Hass host config or state, any real owner message, any secret. **Not called:** any live address, Cloudflare, GitHub write APIs apart from this PR.

Scratch runs (loopback only, nothing under `community-data/`, synthetic names `Synthetic Guest n` at `example.invalid`): the live site's own files served on 127.0.0.1:18771; the repo's local community server on 127.0.0.1:18772 with a scratch config (one made-up hike, capacity 6, `trailId` Point Buchon) and a scratch SQLite file. Scripts: `reports/hass/hikepage-1/serve_scratch_api.py`, `scratch_race.py`. Both servers were stopped afterwards.

## 3. Findings (each with its evidence)

| # | Finding | Evidence | State |
|---|---|---|---|
| F1 | Live site is static (Cloudflare Pages from `theavocadoman-site`); no function, worker, binding or `wrangler` file | listing of the site checkout; `docs/hass/MAC_RUNBOOK.md` steps 18/23 (Pages rollback, HTML rewriting); `static-site-qa.cjs` header ("no /api, POST answered with an HTML 405") | VERIFIED for the repos; the live project settings were not looked at |
| F2 | The community API exists only as `storefront-mockup/community-server.py`, binds 127.0.0.1, rejects non-loopback POST | the file | READ |
| F3 | On the static site the page cannot RSVP: both signup forms say "Online signup isn't open yet" and `send()` refuses to POST without the service | `community.js` (`liveService`, `send`, `SIGNUP_CLOSED`); screenshot 01 shows the disabled hike-updates form | VERIFIED |
| F4 | `maps` in `hike/index.html` is the meta description; the real map is `trail-explorer.js` for Point Buchon only (`EXPLORER_TRAILS`, hard-coded `/assets/trails/point-buchon.json`; `sitegen.PUBLISH_ASSETS` lists the five Point Buchon files by name) | grep; code | VERIFIED |
| F5 | Real events render with a plain card; the rich invitation layout is only the sample | `community.js` `render()` vs `sampleInvitation()` | READ; screenshots 01 vs 02 |
| F6 | The page contacts only its own host (no map tile, font, analytics or CDN host) | the browser's resource list after scrolling to the map | VERIFIED |
| F7 | Map weights: aerial 1.8 MB (default view), topo 0.4 MB (on press), photo 0.3 MB, route JSON 25 KB | resource list; `ls -l` | VERIFIED |
| F8 | `events[].capacity` is optional, whole number 1–1000, no default; `rsvpEnabled: true` needs exactly one of `capacity` or `noCapacityLimit` | `content_model.py` `MAX_EVENT_CAPACITY`; `ops/hikes.py` `hike.create` | READ |
| F9 | Capacity is enforced atomically in the local API | `community-server.py` (`BEGIN IMMEDIATE`). Scratch run: 2 of 6 seats left, 8 simultaneous 1-seat RSVPs → 2 × 200, 6 × 409; final `confirmedGuests 6, remaining 0`; a group of 2 at 0 left → 409 | VERIFIED (scratch) |
| F10 | No cancel/remove and no walk-in path; the table requires an email | schema in `community-server.py`; no DELETE route | READ |
| F11 | Public API returns only `confirmedGuests` and `remaining`, never names or emails | `do_GET`; scratch run's event keys (list printed by `scratch_race.py`) | VERIFIED (scratch) |
| F12 | Hass reads seat totals read-only through the private setting `guestCountsDb` (aggregate only, fail closed); whether it is set on the live host was not checked | `ops/hikes.py guest_counts_checked`, `health._guest_check`, `docs/hass/SUPPORT.md` | READ |
| F13 | `live_policy` makes a hike that carries `distance, difficulty, duration, accessNote, meetingAddress, trailId` (and every `route.*`) `private-only`, and limits a live release to 10 records; the daily cap (default 10) and 2-minute spacing are `publish_live` settings | `live_policy.py FIELDS/OPS/MAX_RECORDS`; `PUBLISHING.md` | READ |
| F14 | The correspondence log keeps up to 80 characters of Mike's text with numbers/addresses/links blanked, **not names** | `docs/hass/VOICE.md`, `corrlog.py EXCERPT_MAX` | READ → needs a private-text flag |
| F15 | Interpreter is loopback-only; its audit row holds codes and seconds, never text | `interpreter_local.py LOOPBACK`; `conversation.py AUDIT` comment | READ |
| F16 | Cass Hill and Fiscalini cannot get a map yet: trail line, turnaround and frame unresolved, no confirmed photo | `reports/hiking-club/route-map-sources-2026-11.md` verdicts "Blocked" | READ |
| F17 | HIKES-1 skills (PR 530) are open, not in main and not in the live runtime; the live runtime is on the older plain-words path | `STORE-TEST-1.md` (runtime 0a8114c, item 3 of section 8) | READ |
| F18 | On Monday the sample invitation will read "Date to be confirmed" (its date, Nov 8, will have passed) | `community.js sampleInvitation` `past` rule | READ (not rendered) |

Screenshots (`reports/hass/hikepage-1/`): `01-live-static-hike-page.jpg` (full page, the live site's files), `02-scratch-hike-with-api.jpg` (a scratch hike showing "2 places available" and the RSVP button, from the local API), `03-topo-layer.jpg` (Topo view of the explorer).

## 4. Where the design asks for a decision or crosses a protected boundary

The seven decisions are on the first lines of `HIKE-PAGE.md`. The ones that touch protected code or live release: **4** (a new `counts` release class touches `publish_live.py` and `live_policy.py`) and **6** (relaxing the D4 trail-facts boundary). Neither is needed for Monday. Decision 1 (online RSVP) means a Cloudflare change, a credential and **off-box storage of guest names and any form email at Cloudflare (a data-exposure decision, only G)**. The credential holder is a separate no-login account `hass-rsvp` running `hass-rsvp-bridge.service`; the token is a root-owned mode-0400 file that systemd hands only to that unit (`LoadCredential`), and the Hass account gets only a closed-command socket (design 3.6.1; the privacy and logging boundary is 3.6.3). The default path (decision 1 = A) keeps all names on the box. No card here edits approval, ownership or reply logic. Two touch protected code and need the independent reviewer: ROSTER-1 (a small hook in `editor.py`, the writer path) and COUNTS-1 (`publish_live.py`, `live_policy.py`), which is also held for decision 4 and an attended review.

## 5. The cards, in build order

Model column follows `WORKER-GUIDE.md` (routine well-specified: Sol Medium; substantial: Sol High; a protected-code card should also get the independent reviewer named by actual authorship). The operator may choose differently. "Chain" = a file that only one card at a time may own.

| # | Card | Owns (files) | Needs | Model | Monday? |
|---|---|---|---|---|---|
| 1 | **HIKEPAGE-SPOTS-1**: the card shows the limit as "Limited to 6 people · availability unconfirmed; ask at the Shack" when no trusted count exists (count unknown or capacity mismatch: never "N spots left"); "N spots left" only from a matching count; "Full" + waitlist line only when a count says 0; nothing new when no capacity; one concrete test per row of HIKE-PAGE.md 3.3.1; wording moves from "places available" to "spots" | `storefront-mockup/community.js` (chain), `storefront-mockup/community-ui-qa.cjs`, `storefront-mockup/static-site-qa.cjs`, `hass/screenshot.cjs`, `hass/tests/test_preview_hike_results.py` (these pin the old strings), `storefront-mockup/hiking.css` only if needed | none | Sol Medium | **YES (minimum)**; needs the operator to move the runtime to a main with it before the 21:00 gate |
| 2 | **HIKES-1 follow-up**: default capacity 6 by code when sign-up is turned on ("I set: 6 spots"), a 6-person maximum until decision 2-A, bring default; the sign-up default **stays OFF (D8)** until G approves decision 3 (then a one-line change with its test), `capacity` moved out of `hike.edit` | `hass/skills/hikes.py` (chain), `hass/tests/fixtures/skills/hikes/*.jsonl`, `docs/hass/skills/hikes.md` | PR 530 merged. Decisions 2 and 3 are **not** needed to build it (it keeps D8 OFF and the 6 maximum); they only flip a default later | Sol Medium | no |
| 3 | **ROSTER-1**: private roster (`rsvp.sqlite3` in the state folder, 0600), seats, waitlist, pending rows, purge at +30 days, counts, `BEGIN IMMEDIATE`, scan test that no name reaches any log or journal; the `rsvp.*` ops and the editor's hook for a private store with undo | `hass/rsvp_roster.py` (new), `hass/ops/rsvp.py` (new), `hass/editor.py` (sole owner, minimal hook), `hass/tests/test_rsvp_roster.py`, `docs/hass/RSVP.md` | decision 7 for the purge | Sol High (touches the writer path) | no |
| 4 | **RSVP-SKILLS-1**: `rsvp.add`, `rsvp.remove`, `who.coming`, `waitlist`, `spots.set`, `hike.full`; private-text flag in the correspondence log; new side effects `rsvp-roster`, `spots-sync` and live class `counts` in the skill model | `hass/skills/rsvp.py` (new), `hass/tests/fixtures/skills/rsvp/`, `docs/hass/skills/rsvp.md`, `hass/corrlog.py`, `hass/skills/model.py` (small, after the framework card) | 3, FW-3 merged, 2 | Sol High | no |
| 5 | **COUNTS-1**: the public `hike-spots.json` from `hass/content/spots.json`, release class `counts` (numbers only, own cap/spacing, STOP), schema check, stale-capacity rule | `hass/spots_sync.py` (new), `hass/sitegen.py` (chain), `hass/publish_live.py`, `hass/live_policy.py`, `docs/hass/PUBLISHING.md`, tests | 3, **decision 4**, attended review | Sol High + the independent reviewer | no |
| 6 | **HIKEPAGE-CARD-1**: one renderer, the rich layout for every real hike, the field table of section 2.1 (placeholders, defaults), spots line reads API → counts file → capacity-only line (3.3.1) | `storefront-mockup/community.js` (chain), `storefront-mockup/hiking.css`, `hass/templates/hike/index.html` if needed, the page QA scripts | 1 (and 5 for the count source) | Sol High | no |
| 7 | **HIKE-ADD-2**: `hike.add` v2 builds the whole page: copy from a route idea, one question for what is missing, `route.add` chaining | `hass/skills/hikes.py` (chain), `hass/skills/routes.py` (new), fixtures, docs | 2, 6, decision 6 for live release | Sol High | no |
| 8 | **TOPO-1**: a data-driven explorer (route id instead of hard-coded Point Buchon), topo as the default view, a generic route builder, `sitegen` takes route assets by pattern | `storefront-mockup/trail-explorer.js`, `trail-explorer.css`, `reports/hiking-club/build-trail-data.py`, `hass/sitegen.py` (chain, after 5), `storefront-mockup/map-qa` scripts | none | Sol High | no |
| 8a | **TOPO-2 / TOPO-3**: Cass Hill and Fiscalini route data and photo | `storefront-mockup/assets/trails/<id>*`, `reports/hiking-club/` sources | 8; **blocked** on the route line, turnaround, frame and a confirmed photo (custodian: whoever can check the trails against the official guides) | Sol Medium + a human check | no |
| 9 | **RECAP-2**: recap offers "N were signed up", purge schedule hook | `hass/skills/hikes.py` (chain), `hass/retention.py` | 3, 7 | Sol Medium | no |
| 10 | **ONLINE-RSVP-1** (only if decision 1 = B): the Pages function + D1 + the host bridge (token owned by root, delivered only to the `hass-rsvp` unit, closed socket interface; design 3.6.1) + the privacy/logging rules of 3.6.3 + G's written acceptance of off-box guest data | new files outside `hass/` plus G's attended install steps | G; Cloudflare change | Sol High / attended | no |

Shared-file chains (one card at a time): `community.js` = 1 → 6; `hikes.py` = 530 → 2 → 7 → 9; `sitegen.py` = 5 → 8; `editor.py` = 3 only; `model.py` = 4 only (small); `live_policy.py` and `publish_live.py` = 5 only.

## 6. Monday (2026-11-09), exactly

* **Minimum = card 1.** Without it the hike is saved with `capacity: 6` (Mike says "sign-up on, 6 spots" on the older path, explicitly, because sign-up is OFF by default until G approves decision 3) but the page never shows the number. With it the page says "Limited to 6 people · availability unconfirmed; ask at the Shack": a limit, not a count.
* **Mike's script:** do **not** link a route idea on Monday (`trailId` makes the draft private-only, F13); a plain hike with meeting place, day and time is chat-live.
* **If card 1 is not in the runtime by the 21:00 gate:** no-code fallback, Mike's own words in the description ("limited to six people"). That has not been tried.
* **Not on Monday:** live counts, waitlist, who is coming, the per-hike rich page, new maps, an online form.

## 7. Not verified / limits

* No live address was called, so F1 (no `/api` live) is inferred from the repos and the runbook.
* Whether `guestCountsDb` is set on the live Hass host was not checked (private config).
* Cloudflare Pages Function and D1 limits, the narrowest token scope, the dashboard labels, D1's region and backup retention, whether the box's systemd supports `LoadCredential` (247+) and whether any agent account has sudo are UNVERIFIED (design 3.6.1, 3.6.3).
* The skill names, slot lists, reply wording and the roster schema are a design, not measured behaviour. Nothing was built or run except the two scratch servers.
* The OSM tile policy and USGS credit page were read on 2026-11-08; the licences of the Cass Hill / Fiscalini candidate photos are as recorded in the earlier route-map report, not rechecked.
* Decision 3 would change the D8 default ("sign-up off") that PR 530 documents. Round 2 of review: the design **keeps D8 OFF until G explicitly approves decision 3**; unanswered recommendations (decisions 2 and 3 included) are proposals, not authorization, and 6 is the maximum until decision 2-A.
* Round 2 of review also fixed the unknown-count wording: the Spots-left position never says "6 spots" without a count; it says the capacity-only line (HIKE-PAGE.md 3.3.1, cases: capacity 6 / taken unknown, capacity mismatch, known remaining 0 = Full + waitlist).
