# Avocado Shack

**The private home for Avocado Shack's website and Hass, Michael Wolfe's planned store assistant.**

The working website is a food catalog for in-person visits, with the North Coast Hiking Club and newsletter signup. Hass will let Michael manage it by sending texts, photos and voice notes. That messaging connection is planned, not running yet.

## Start here

| What you need | Read this |
| --- | --- |
| Hass plan, milestones and owner setup | [Hass project plan](docs/hass/README.md) |
| Complete prioritized feature list | [Feature backlog](docs/hass/FEATURES.md) |
| Hermes's next assignment | [Hermes start instructions](docs/hass/HERMES_START.md) |
| Implementation and verification requirements | [Technical plan](docs/hass/IMPLEMENTATION.md) |
| Existing site's operation and private data locations | [Project handoff](HERMES_HANDOFF.txt) |
| Website files, event format and checks | [Storefront guide](storefront-mockup/README.md) |
| Decisions and actual completed work | [Build ledger](BUILD_LEDGER.md) |

Use [GitHub Issues](https://github.com/Grahammmm/avocado-shack/issues) for the work queue. Use this repository for reviewed source, content, optimized web images and project documentation. Start new work from the latest `main`, use a `codex/` branch, and keep changes small enough to review. GitHub stores the project; it is not the website host.

## Current website

- 170 food listings and 26 maker profiles, with category/producer filters and town search.
- Product descriptions, documented locations and organic labels; maker stories expand within cards.
- Separate `/hike` page with maps, sample invitations and a dummy RSVP.
- Real RSVP and newsletter forms can save locally. No email delivery is connected; no real hikes are scheduled.
- Catalog only: no prices, basket, online orders, weekly boxes or merchandise.

The active code is in [`storefront-mockup/`](storefront-mockup/). The `commerce/` prototype and earlier proposals are historical. Shopify and Clover are possible later integrations, not the current backend.

## Where things live

| Location | Purpose |
| --- | --- |
| This private GitHub repository | Shared source, plans, issues and source history |
| Agent Orange: `/home/user/repos/avocado-shack` | Working checkout and private website service |
| Agent Orange: `/home/user/.local/share/avocado-shack` | Private runtime, community database and archived data; outside Git |
| Mac: `/Users/owner/Documents/ChatGPT/Avo_Shack` | Preserved original project and `handoff-backups/2026-10-20` |
| Dedicated Mac for Hass | User confirms one is available; identity, account and bridge setup remain pending |

Credentials, participant details, message history, original photo archives and private backups stay out of GitHub. Optimized images needed to render the website are already included. This repository is not a complete export of personal chats or external accounts.

The preview remains bound to `127.0.0.1:3101` on Agent Orange. Use the private SSH instructions in [the handoff](HERMES_HANDOFF.txt). Do not enable GitHub Pages or public hosting as part of ordinary development.
