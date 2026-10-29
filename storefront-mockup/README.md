# Avocado Shack — local food catalog

Open http://127.0.0.1:3101/ while the local server is running.

This version is for browsing the food and planning an in-person visit. It has 170 food listings, category/producer/town search, local-maker and organic-selection filters, progressive scrolling, and 26 sourced producer profiles. Cards show food descriptions, producer introductions, and verified producer locations where known. Full food descriptions, maker stories, verified producer locations and producer links are shown inline. There is no separate product-detail dialog. Desktop uses four columns at 1180px and wider, three at 801–1179px, two at 520–800px, and compact photo/text rows on smaller phones.

There are no prices, baskets, checkout, pickup/delivery selection, weekly boxes, merchandise, or owner assistant interface in the current page. The newsletter stays on the home page. The hiking club, maps, RSVP and hiking-only signup live at `/hike` (also `/hike/`). Old home-page `#hikes` links redirect there. Email delivery is not connected. The previous commerce interface is preserved under archive/commerce-preview. No changes from this revision were deployed to the public domain. Its previously authorized shutdown remains in place.

## Files
- index.html, style.css, script.js, shop.js: current catalog interface.
- hike/index.html: dedicated hiking page. All its shared scripts and map assets use root-relative paths.
- catalog-products.js: display-only food data; no prices or commerce collections.
- producers.js / producers.json: maker profiles and research source links.
- shop-data.json, catalog.json, catalog-extraction.csv: historical extraction and commerce assumptions; retained as project evidence and not loaded by this page.
- assets/products: optimized product images. Earlier merch/box assets remain saved for possible later use but are not referenced by this catalog.

## Sourcing boundaries
A producer’s base is labeled “Based in”; this is not an assertion that every ingredient was grown in that town. Unidentified growers are not assigned invented locations. The Central Coast filter uses the researched producer places. Organic badges use explicit product names or documented organic product lines (Ocean Ranch granola, Straus dairy, Green Gold microgreens, Massa Organics). Manufacturer/farm business summaries are factual, rather than automatically labeling every producer a small local business.

The catalog is derived from photographed products. It is not live inventory. Availability changes; no real-time stock quantities are shown. Original photos, generated-image logs, sources, and held-product evidence remain in the project. Exact packaging/variety and availability still need owner confirmation before future launch. Two photographed raw-milk cheese candidates remain held outside the catalog pending manufacturer recall review.

## Local server
python3 storefront-mockup/community-server.py --port 3101

## Checks
catalog-only-qa.cjs checks all 170 food listings, no commerce UI/copy, town search, sourcing filters, empty search, inline maker stories, duplicate-free scrolling, and overflow/color consistency at 320, 375, 390, 768, and 1440 pixels. Results: catalog-only-QA.json. Phone and desktop screenshots are catalog-only-*.png. Earlier commerce tests apply to the archived experience, not this revision.

Running checks on Agent Orange (Linux): the active scripts (`catalog-only-qa.cjs`, `community-qa.py`, `community-ui-qa.cjs`) take optional environment overrides. `PLAYWRIGHT_MODULE` points at a Playwright package (default `require('playwright')`), `CHROMIUM_PATH` at a matching Chromium binary, `NODE` at the Node executable (default `node` on PATH), and `QA_OUT_DIR` at the folder for JSON/screenshots (default `storefront-mockup`, which overwrites committed evidence). Run from the repository root with the service up on 3101; the catalog check only reads the live page, and the community check uses its own temporary database on port 3102. Example:

    PLAYWRIGHT_MODULE=/path/to/node_modules/playwright CHROMIUM_PATH=/path/to/chrome-headless-shell \
      QA_OUT_DIR=/tmp/avoshack-qa node storefront-mockup/catalog-only-qa.cjs
    PLAYWRIGHT_MODULE=... CHROMIUM_PATH=... QA_OUT_DIR=/tmp/avoshack-qa python3 storefront-mockup/community-qa.py

Older commerce-era QA scripts still hardcode the Mac runtime and are left as historical.


## Hiking club and newsletter
`community.json` holds club information, sourced trail ideas, and real upcoming/completed hikes. Its events list remains empty until Michael supplies confirmed details. The owner-requested mockup is separate: `hiking-preview.json` enables a sample Point Buchon invitation and Cass Hill / Fiscalini Ranch archive entries. Labels distinguish them from confirmed events. The sample RSVP validates in the browser, clears its fields, and sends or stores nothing. Its confirmed guest count is 0 and does not increase on a sample submission. For real events, `/api/community` computes `confirmedGuests` from the sum of RSVP party sizes. Counts include each person, not just each form, and never expose names or email addresses. Successful real RSVPs refresh the count; duplicate registrations do not add guests. Set `enabled` to false to remove these samples. A real scheduled event takes precedence over the sample invitation; completed events take precedence over the sample archive. `community.js` renders these states; `hiking.css` scopes the new field-guide design. The featured Point Buchon invitation now uses a real licensed coastal photo, cached USGS aerial/topographic imagery, OpenStreetMap geometry, and a USGS-derived estimated elevation profile. `trail-explorer.js` / `trail-explorer.css` provide layer switching, zoom/pan, an enlarged view and a profile scrubber linked to the route marker. No external map requests or account are needed. See `reports/hiking-club/TRAIL_MAP_SOURCES.txt` for credits, data and method. The old coastal SVG is retained but no longer displayed.

The local Python server saves subscriptions and RSVPs in `../community-data/community.sqlite3`, outside the served website and ignored by Git. It binds only to 127.0.0.1. Separate opt-ins are stored for the community newsletter and hiking updates. Repeat signups merge choices without duplicating the email. RSVP capacity is checked in a database transaction; duplicate RSVPs do not claim more places. There is no email delivery, active sender mailbox, or public subscriber list.

`owner@example.com` is the proposed sender in config, not an active mail link or configured mailbox. Before launch: confirm the address and mailbox/domain access, connect email delivery and unsubscribe handling, and replace local-setup privacy text with the actual deployed data/delivery details. All work in this revision remains local.

To add a hike, put a real record in `community.json` events. Required: stable `id`, `title`, `startsAt` including UTC offset, `timezone` (normally America/Los_Angeles), and `status` (`scheduled`, `completed`, or `cancelled`). For RSVPs add `meetingPoint`, `rsvpEnabled:true`, and an optional positive integer `capacity`. Add `distance`, `difficulty`, `duration`, and `description` for useful participant details. Mark past outings `completed` and add `recap` to display history. A past date alone does not assert that a hike occurred. No example record is published.

Checks: `community-qa.py` uses a temporary database, separate fixture config and port3102. It tests persisted signups, consent choices, input validation, duplicate registration, concurrent capacity limits, past-hike rejection, no personal-data leakage, and mobile UI at320/375/390/768/1440. Test entries never enter the normal calendar or database. Evidence: community-api-QA.json, community-ui-QA.json, community-*-mobile.png.


### Placeholder routes
Owner requested three specific sample routes: Point Buchon (Los Osos), Cass Hill (Cayucos), and Fiscalini Ranch Bluff Trail (Cambria). These are undated route records in `community.json.routeIdeas`, with source links. `hiking-preview.json` separately supplies the illustrative invitation/archive dates. These samples cannot accept real RSVPs. Current access, chosen route and any group-use requirements must be checked when a real outing is planned.

## Hiking mockup — October 27, 2026
The sample November 8 invitation and archive months are illustrative only. No real club outing has been confirmed. The trail statistics are sourced in `reports/hiking-club/trail-research.txt`; walking durations, group pace, meeting time and difficulty labels are planning estimates. Confirm route access and all event details with Michael before creating a real event. The existing real RSVP and separate newsletter/hiking signup infrastructure remains available; email delivery remains disconnected.

## Map checks — October 27, 2026
`reports/hiking-club/map-qa.cjs` tests map layers, zoom/pan, keyboard use, profile positions, enlarged-view focus, phone touch scrolling, dummy RSVP isolation and eight widths from 320–1920. Use `PREVIEW_URL` for a separate local preview, `PLAYWRIGHT_MODULE` for the installed test browser package, and `QA_OUT_DIR` for evidence outside the source tree. The catalog and section-navigation scripts now also accept `PREVIEW_URL`. Results are in `reports/hiking-club/map-upgrade-qa-20261027.json`; actual phone hardware and Safari were not tested.

## Catalog and hiking subpage — October 28, 2026
The product-discovery buttons and product dialog have been removed. Product photos are no longer buttons. Complete product descriptions remain on each card; longer maker stories and source links are tucked into a collapsed “Meet the maker” disclosure. The privacy dialog remains. The full hiking experience now lives at `/hike`, with navigation back to the food, newsletter and visit section. The local server serves both `/hike` and `/hike/`; a plain static host can serve the same directory as `/hike/`.

Fresh checks are recorded in `reports/hiking-club/catalog-hike-qa-20261028.json`. They cover all 170 inline descriptions and maker/source links, filters, four-across desktop layout and phone rows, clean hiking routes and old anchors, guest totals including group size and duplicates, independent consent choices and isolated form data. No actual hike or participant was added.

## Simplified catalog cards — October 28, 2026
The requested community-focused introduction is in place. The origin/local/organic filter row is removed; category, producer and town search remain. Documented location and organic labels stay visible. Full maker stories and their source links expand in place with a native keyboard-accessible disclosure, closed initially. All 170 products and the four-column desktop / compact phone layout are preserved. Fresh checks: `reports/catalog-card-update-20261028.json`. No form/backend/data changes.
