# Hass feature backlog

**States are as of the 2026-11-02 feature audits.** Numbers define development order, not completion. Use these IDs in issues, commits and acceptance evidence. The [project plan](README.md) explains the benefits and milestones; the [technical plan](IMPLEMENTATION.md) defines the controls.

## Existing foundation to preserve

| Existing feature | Current limit |
| --- | --- |
| 170 catalog listings, 26 makers, product images, category/producer/town search | Static content, no authenticated owner editing tools; not live inventory |
| Product stories, documented location/organic labels, expandable maker bios | Sources must remain attached; unknown origins remain unknown |
| `/hike`, route maps, elevation display, labeled sample invitations | No real events confirmed; mock RSVP sends/saves nothing |
| Local newsletter and real-event RSVP persistence | Email disconnected; newsletter/hiking consent separate; private data excluded from Git |
| Private GitHub, Agent Orange service and preserved Mac backup | No iMessage bridge or Hass runtime connected |

## Milestone 1 — working text demo

| ID / order | Owner benefit and feature | Dependencies | Done when | State |
| --- | --- | --- | --- | --- |
| H01 | One reliable product/maker/event data source | None | Current records, assets, sources, hidden/held status and stable IDs migrate without losing content; generated web files match it. | Done |
| H02 | Private editing service | H01 | Typed operations validate fields and permissions; only an authenticated internal caller can request writes; public form routes cannot edit content. | Done |
| H03 | Add, edit, hide and restore a product or maker | H02 | Exact record is identified; ambiguous names ask a question; hiding is reversible; held products stay blocked. No pricing or basket UI appears. | Done |
| H04 | Draft and update real hikes | H02 | Exact date/time zone, meeting place and event details are confirmed; route ideas/sample events cannot silently become real events. Cancel and complete are explicit states. | Done |
| H05 | Approve, revise or cancel in the same conversation | H03–H04 | Approval names one version of one change; rejection causes no write; old or ambiguous “yes” cannot authorize a different draft. | Done |
| H06 | Preview, result and undo | H05 | Before/after summary and screenshot are available; a checked change has source history; undo reverses only that change without losing later edits. | Done |
| H07 | Dedicated Mac bridge compatibility check | Chosen Mac/account access | Owner sends/receives a test iMessage and an attachment with SIP enabled; actual versions/permissions and restart behavior are recorded. Failure blocks bridge rollout, not H01–H06. | Needs G: chosen Mac and Apple account; live iMessage check not run |
| H08 | Owner-only text channel | H05–H07 | Allowlisted sender and intended private chat work; group/unknown messages, echoed replies and duplicate deliveries cannot trigger edits; no unrelated inbox is ingested. | Needs G: connect the live channel (CONNECT.md section 2) after H07 |
| H09 | Demo and regression evidence | H01–H08 | Owner text → draft → approval → private update → screenshot → undo passes. Denial, invalid input, duplicate delivery and old approval tests pass; existing catalog/forms still work. | Partly: demo uses fixture texts, not the real channel; no real-screenshot chain test |

## Milestone 2 — small owner trial

| ID / order | Owner benefit and feature | Dependencies | Done when | State |
| --- | --- | --- | --- | --- |
| H10 | Photos become useful product drafts | H09 | Photo/label extraction proposes name, maker and category; uncertain facts prompt a question. Original is preserved privately; approved web derivative has alt text and no location metadata. | Partly: label reader never run on a real vision model or photo |
| H11 | Voice notes become editable requests | H09 | Real iPhone voice-note formats are tested; Hass repeats interpreted intent and asks about unclear names, quantities or dates. No action runs merely because transcription completed. | Partly: voice notes recognised but not transcribed or read back |
| H12 | One conversation for text plus attachments | H10–H11 | Photo, caption and later clarification join the correct draft; unsupported/oversized files produce a useful reply; repeated attachments do not duplicate products. | Done |
| H13 | Hours, home-page copy and image changes | H09 | Approved edits use structured fields and approved layout slots; malicious markup is rejected; phone/desktop checks pass. Unusual layout requests use H24. | Partly: no home-page image slot; story block copy fixed in template |
| H14 | Hike management and guest totals | H09 | Michael can reschedule/cancel and ask for confirmed people, counted from actual RSVPs. Capacity changes respect existing guests; no guessed totals or silent notification sends. | Done |
| H15 | Owner memory and useful clarification | H09 | Approved business facts/preferences retain source and date; Michael can correct/forget them. Chat history is not treated as verified fact; model quality does not improve automatically without evaluation. | Done |
| H16 | Durable queue, restart and offline recovery | H08 | Interrupted work resumes once, in order; new messages are distinguished from history; missing attachments wait; stale drafts expire; write success with reply failure is reconciled. | Done |
| H17 | Clear status and control | H16 | “Status,” “cancel,” “undo” and “pause changes” work; replies distinguish draft/applied/failed. Persistent outages have a documented support path. | Done |
| H18 | Owner trial on real devices | H10–H17 | Michael completes at least one of each agreed task using his phone; review 7 days of normal use or an agreed representative trial. Fix observed failures before broader use. | Needs G: live channel, agreed task list and Michael's phone trial |

## Milestone 3 — reliable everyday operation

| ID / order | Owner benefit and feature | Dependencies | Done when | State |
| --- | --- | --- | --- | --- |
| H19 | Managed operation and maintenance | H18 | Mac login/startup/sleep and Agent Orange service behavior are documented; health checks report meaningful failures without repetitive messages; no extra telemetry vendor is assumed. | Needs G: decide what runs health checks and where alerts go; Mac unmeasured |
| H20 | Backups and recovery | H18 | Restore of content, approved media and private state is demonstrated from isolated backups; the original Mac archive stays intact. Owner can pause edits during recovery. | Partly: drill run only on fixtures; content comes back from Git, not backup |
| H21 | Privacy, retention and access | H18 | Owner-approved sender list, message/media retention and deletion rules are enforced; credentials and participant/message data stay out of Git, screenshots and routine logs. | Needs G: owner retention periods; no deletion step enforces them yet |
| H22 | Usage and support limits | H18 | Model/service usage has agreed spending limits; failures stop safely; support responsibility, recovery contact and account ownership are documented. No unsupported unlimited-usage promise. | Needs G: agreed usage limit; confirm private support/recovery/account record exists |
| H23 | Optional narrow automatic changes | H18–H22 | Michael explicitly opts in by action type; limits, history, pause and undo remain. New permissions, bulk destructive actions and external outreach still need separate approval. | Needs G: owner opt-in per action type; policy module not wired in |
| H24 | Design changes requested through Hass | H18–H22 | Requests beyond content fields become isolated code changes with visual checks and same-thread review. No unrestricted shell execution or self-deployment from incoming text. | Partly: no path from an owner request to a checked code change |
| H25 | Release and owner handover | H19–H24 | Acceptance suite and restore drill pass; Michael receives a short phone guide and known limitations. Private operation can launch; a public site requires separate authorization and configured form/privacy behavior. | Needs G: real-deployment acceptance and restore drill, handover, G launch decision |

## Later store-manager work

These features preserve the whole vision but are **not part of H01–H25**. Sequence them after the messaging foundation and a new scope decision. A future integration does not become active simply because it is listed here.

| ID | Benefit / capability | Prerequisite and acceptance boundary |
| --- | --- | --- |
| F01 | Shopify catalog, online pickup orders, payments and later local delivery/US shipping | Approved commerce phase, business-owned accounts, fulfillment/tax/payment configuration and end-to-end order tests. Current catalog-only scope stays in place until then. |
| F02 | Clover/POS sales reduce shared inventory | Audit actual Clover plan, itemized sales, units/SKUs and connector support. Test weighed produce/fractional quantities and refunds; do not assume a reader photo proves integration support. |
| F03 | Record purchase costs; suggest sale prices and margins | Verified supplier costs, pack conversions, shrink/tax rules and owner margin targets. Show arithmetic and assumptions; price changes initially require approval. |
| F04 | Low-stock warnings and a concise morning report | Reliable POS/online sales plus recorded receipts, waste and adjustments. Distinguish counted stock from estimates; include pending offers and decisions. |
| F05 | Supplier messages, offers and purchase orders | Explicit access to designated supplier channels; classify quotes, compare terms and draft replies. Sending, bargaining or committing money needs owner authorization and limits. |
| F06 | Slow-seller insights, replenishment and spoilage discounts | Reliable sales/cost/freshness history. Propose measurable changes; enforce price floors, expiry and cancellation; never discount held/recalled products. |
| F07 | Instagram and other social content from a photo | Business account access and verified publishing support. Prepare branded post, caption and schedule; owner approves destination/content before first publication. |
| F08 | Community newsletter and hiking notifications | Confirm business sender/domain, delivery service and unsubscribe handling. Preserve separate consents; publishing a hike does not automatically send a mailing. |
| F09 | Supplier invoices and bookkeeping, such as QuickBooks | Authorized accounting account, document matching and duplicate checks. Draft/reconcile entries for review; no promise to replace an accountant or autonomously file taxes. |
| F10 | Import historical sales, costs, suppliers and approved store knowledge | Inventory available records, permission and data quality first. Preserve provenance; exclude unrelated personal/campaign records; support correction and deletion. |
| F11 | Improve recommendations using results | Compare recommendations with measured outcomes and owner corrections; version rules, evaluate changes and roll back regressions. No uncontrolled rewriting of its own permissions. |
| F12 | Weekly boxes or merchandise, only if revived | Owner explicitly reopens these removed features. Box stock/cost/allergen and merch fulfillment need their own acceptance checks; do not restore old mockups automatically. |

## Release evidence

For each completed ID, record the commit, date, test command or steps, result and remaining limits in the issue and a concise project report. A plan, mocked connector or historical test is not evidence of a working integration. Use isolated fixtures for tests; never create fake participants in the real community database.
