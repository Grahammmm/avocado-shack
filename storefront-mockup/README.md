# Avocado Shack — local food catalog

Open http://127.0.0.1:3101/ while the local server is running.

This version is for browsing the food and planning an in-person visit. It has 170 food listings, category/producer/town search, local-maker and organic-selection filters, progressive scrolling, and 26 sourced producer profiles. Cards show food descriptions, producer introductions, and verified producer locations where known. Product details expand the food and maker stories.

There are no prices, baskets, checkout, pickup/delivery selection, weekly boxes, merchandise, or owner assistant interface in the current page. Local newsletter and hiking-club forms are now included; email delivery is not connected. The previous commerce interface is preserved under archive/commerce-preview. No changes from this revision were deployed to the public domain. Its previously authorized shutdown remains in place.

## Files
- index.html, style.css, script.js, shop.js: current catalog interface.
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
catalog-only-qa.cjs checks all 170 food listings, no commerce UI/copy, town search, sourcing filters, empty search, maker dialogs, duplicate-free scrolling, and overflow/color consistency at 320, 375, 390, 768, and 1440 pixels. Results: catalog-only-QA.json. Phone and desktop screenshots are catalog-only-*.png. Earlier commerce tests apply to the archived experience, not this revision.


## Hiking club and newsletter
`community.json` holds club information and real upcoming/completed hikes. Its events list is empty until Michael supplies confirmed details. No invented hike is shown in the normal sandbox. `community.js` renders the calendar, history, RSVP form, and signup states.

The local Python server saves subscriptions and RSVPs in `../community-data/community.sqlite3`, outside the served website and ignored by Git. It binds only to 127.0.0.1. Separate opt-ins are stored for the community newsletter and hiking updates. Repeat signups merge choices without duplicating the email. RSVP capacity is checked in a database transaction; duplicate RSVPs do not claim more places. There is no email delivery, active sender mailbox, or public subscriber list.

`owner@example.com` is the proposed sender in config, not an active mail link or configured mailbox. Before launch: confirm the address and mailbox/domain access, connect email delivery and unsubscribe handling, and replace local-setup privacy text with the actual deployed data/delivery details. All work in this revision remains local.

To add a hike, put a real record in `community.json` events. Required: stable `id`, `title`, `startsAt` including UTC offset, `timezone` (normally America/Los_Angeles), and `status` (`scheduled`, `completed`, or `cancelled`). For RSVPs add `meetingPoint`, `rsvpEnabled:true`, and an optional positive integer `capacity`. Add `distance`, `difficulty`, `duration`, and `description` for useful participant details. Mark past outings `completed` and add `recap` to display history. A past date alone does not assert that a hike occurred. No example record is published.

Checks: `community-qa.py` uses a temporary database, separate fixture config and port3102. It tests persisted signups, consent choices, input validation, duplicate registration, concurrent capacity limits, past-hike rejection, no personal-data leakage, and mobile UI at320/375/390/768/1440. Test entries never enter the normal calendar or database. Evidence: community-api-QA.json, community-ui-QA.json, community-*-mobile.png.


### Placeholder routes
Owner requested sample SLO County routes before dates are available. `community.json.routeIdeas` now holds three explicitly undated ideas: Fiscalini Ranch Bluff Trail (Cambria), Montaña de Oro Bluff Trail (Los Osos), and Bob Jones Pathway (Avila Beach). These are not events, do not appear in past-hike history, and cannot accept RSVPs. Official source links live with each entry. Distances describe named trail segments where verified; actual outing lengths and meeting points are still undecided. Current access and any group-use requirements must be checked when a real outing is planned.
