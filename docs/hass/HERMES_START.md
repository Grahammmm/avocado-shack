# Hermes: next assignment for Avocado Shack

Continue the Hass messaging interface described in this repository. The private text-editing tools are built on fixtures; the live demo and everything after it are still open. **Do not start by rebuilding the website or reactivating the old commerce prototype.** The owner wants to manage the existing catalog, hiking page and store information through one conversation using text, photos and voice notes.

## Read in this order

1. Root [AGENTS.md](../../AGENTS.md), [README.md](../../README.md), [README.txt](../../README.txt) and [HERMES_HANDOFF.txt](../../HERMES_HANDOFF.txt).
2. [Hass project plan](README.md), [feature backlog](FEATURES.md) and [technical plan](IMPLEMENTATION.md).
3. [Storefront guide](../../storefront-mockup/README.md), [owner/brand brief](../../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt) and recent [build ledger](../../BUILD_LEDGER.md) entries. Older proposals do not override current scope.
4. Start with [issue #1: working text demo](https://github.com/Grahammmm/avocado-shack/issues/1). [Issue #2](https://github.com/Grahammmm/avocado-shack/issues/2) covers the photo/voice trial, [#3](https://github.com/Grahammmm/avocado-shack/issues/3) reliable operation, and [#4](https://github.com/Grahammmm/avocado-shack/issues/4) future integrations. Record progress against feature IDs H01–H25.

## Start with an accurate baseline

- Work from `/home/user/repos/avocado-shack` on Agent Orange. Fetch GitHub, inspect status and preserve any uncommitted work. Inspect current `main` and the existing tools under `hass/` before writing new code. Use a new `codex/` branch/worktree; no force resets or force pushes.
- GitHub is `Grahammmm/avocado-shack`, private. Existing deploy-key access is repository-scoped. Do not copy account-wide credentials into it.
- Verify the current service and content before editing. Work from the latest `main`; do not reset to an old baseline commit.
- The live private community DB is outside the repository. Use a separate temporary database/config for tests. Preserve the original Mac project and dated backup.

## First implementation slice

**Steps 1 and 2 are done on fixtures** (H01–H06 are marked Done in [FEATURES.md](FEATURES.md)). Steps 3–5 are still open, and 3 and 4 need G; see the end of this section.

1. Done: H01–H02: one validated source for catalog/maker/event content and narrow private editing tools. Keep all 170 existing listings, 26 maker profiles, photos, source links and held exclusions intact.
2. Done: H03–H06 using a fixture conversation adapter: add/edit/hide/restore, a real-hike draft, version-bound approval, screenshot, history and selective undo. A fixture is not a completed iMessage integration.
3. Run H07 on the chosen spare Mac when the owner has supplied its identity/access and signed into the dedicated account. Prove basic BlueBubbles text/attachment support with SIP enabled. Do not read another user's personal Messages to shortcut setup.
4. Connect H08 and complete H09. Demonstrate an approved owner text modifying only the private preview, with rejection, duplicate, stale-approval and undo checks.
5. Continue to photo/voice and the owner trial only after the demo checks pass. Keep the future commerce/social/accounting backlog separate.

The user confirms a spare Mac is available. Its model, operating system, account and permissions are not yet recorded. `hello@example.com` is a proposed contact, not a provisioned mailbox or Apple account. Account login, permission dialogs, credentials and spending decisions still need the owner; continue independent fixture/content work while waiting.

**Open G steps.** H07 and H08 (the Mac, the Apple account and the live channel) are G's, listed in [CONNECT](CONNECT.md) section 2; no agent signs in or connects them. H09 real-channel evidence and the H18 owner trial stay open until they run over that channel. The release steps and the decisions still open (H07, H19, H21, H22, H23) are in [HANDOVER](HANDOVER.md). Nothing here is deployed, published or signed off.

## Definition of the first successful demo

Michael sends an ordinary message to Hass from his phone. Hass identifies the right item, asks for any missing fact, and returns a concise draft. Michael approves in the same chat. The private site changes once, a screenshot confirms it, and “undo” restores the prior content without disturbing other work. Unknown senders and replayed approvals cannot modify the site.

Do not announce “live,” “sent” or “saved” before verification. A failed outgoing confirmation after a successful edit must not cause the edit to run again.

## Preserve these boundaries

- Private, loopback preview; no DNS, public hosting or GitHub Pages changes.
- Catalog only; no prices, basket, weekly boxes, merch or checkout.
- No real hike without confirmed owner details; examples stay labeled and separate.
- No invented origins, organic claims or route facts; no restoring held products without review.
- Separate newsletter/hiking consent; email remains disconnected until explicitly implemented and authorized.
- No automatic social posts, supplier outreach, purchases or mailings from a content-edit approval.
- All first changes require owner approval; later automation must be explicitly scoped by Michael.
- Source and approved public content in Git; credentials, raw messages, private images, databases and participant data outside it.

## How to report progress

Use the GitHub milestone work items for status. Each implementation report should say what Michael can now do, which feature IDs passed, the commit, the actual tests and remaining limitations. Update BUILD_LEDGER.md at meaningful milestones. Do not repeat old QA as a new run or imply Hermes was configured globally by this handoff.

If blocked on an account, name the exact owner action and successful result; continue work that does not need it. Stop retrying unchanged failures. Leave the private website serving its last checked version.
