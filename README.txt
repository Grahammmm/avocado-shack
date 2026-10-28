AVOCADO SHACK — START HERE

Current project: storefront-mockup/ — local food catalog and community website.
Run from this folder:
  python3 storefront-mockup/community-server.py --port 3101
Open http://127.0.0.1:3101/ on the server machine, or use the private SSH tunnel
in HERMES_HANDOFF.txt from another computer.

Read HERMES_HANDOFF.txt for ownership, paths, operation, checks and remaining work.
Read storefront-mockup/README.md for current implementation details.
BUILD_LEDGER.md is chronological; its opening objective describes older work.

CURRENT SCOPE
170 food listings, 26 maker profiles, filters, product stories, hiking club,
RSVP support and newsletter signup stored locally. No email delivery connected.
No prices, baskets, weekly boxes, merch, checkout or pickup/delivery booking.
Three undated hike ideas; no confirmed upcoming or past club outings.
Owner-requested hiking mockup: a labeled Point Buchon sample invitation with a
browser-only RSVP and Cass Hill / Fiscalini Ranch example archive. See the
storefront README for changing or disabling these samples.

commerce/ is the earlier Medusa prototype, retained for reference. Shopify is a
future direction, not an existing integration. Hass is the assistant name;
older files say Astra. Michael Wolfe is the store owner.

SECURITY / DATA
This repository is private. Credentials, databases, old evidence, original
photo caches and full-size product PNGs are stored separately in the private
handoff archive. Optimized product WebP images are included in the repository.
Do not publish, configure public routing, send email, or activate commerce as
part of sandbox maintenance. Preserve source/provenance and local backups.
