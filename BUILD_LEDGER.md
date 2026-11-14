## Current handoff scope — October 20, 2026
The active product is the private catalog/community website in storefront-mockup/.
Earlier commerce objectives below are historical. Start with README.txt and
HERMES_HANDOFF.txt for the current scope, Agent Orange paths and operating rules.
Private repository: https://github.com/Grahammmm/avocado-shack.
Migration passed. Completion report and evidence: reports/hermes-handoff/.

# Avocado Shack build ledger

## AVOC-MAIN-RED-SCAFFOLD: scaffold capability metadata — November 13, 2026

Repaired the AVB-20 template after AVB-09 made capability metadata mandatory. Generated skills describe their existing owner-approved site write (`site`, site target, A1, subject/field-name audit declaration, owner); sandbox support follows the op and selected arguments' live boundary (`full` for chat-live, otherwise `preview`). The lint, live policy and approval path are unchanged. Added coverage for all metadata fields and a private-only product-name edit alongside the existing product, text and store cases; the review-required warning remains.

Fresh proof: the four requested modules (`test_skills_scaffold`, `test_capabilities`, `test_skills_lint`, `test_help`) reproduced 4 failures and 10 errors on main, then passed all 49 tests with the repair. `python3 hass/capabilities.py --check` passes without regeneration: no registry skill was added. CI planner/required-check evidence is recorded in the PR and task handoff. No live edits, messages or publication.

## R4-AV-05: the skill test kit judges replies before the safe fallback — November 13, 2026

The checker, not the control row, was wrong: its isolated Conversation used the normal voice fallback, replacing a jargon-filled question with a safe line before the kit examined it. The scratch conversation now sets its own outbox to strict voice checking, so the existing VoiceError handler records `jargon`. This does not change the live conversation, voice rules, or the negative control. No new meta-tests or workflow changes.

Fresh builder proof: `python3 hass/skills/testkit.py selftest` changed from exit 1 (`bad-jargon-in-question` wrongly had no problems) to exit 0 (`testkit selftest: the kit behaves`); the unchanged deliberately jargon-filled question now fails with exactly `[jargon]`. The existing KitProvesItself checks passed under Python 3.12. A broader plan-test invocation reached its 180-second command limit after those checks; it is not claimed as a completed pass. Final affected-gate evidence is recorded in the PR and task handoff. No live service, data, send or publication touched. Rollback: revert this PR.

## Objective and scope
Execute planning/Avocado_Shack_Website_Build_Goal.docx: a complete private branded commerce website using real owner photos, Astra text/photo updates, supported Medusa workflows, pickup checkout, packing, recovery and handoff. Work resumed on October 6 after authorization for local vision installation. Browser preview access now works. Completion is unproven.

The user deferred Stripe account creation and authorized mock checkout on October 5, 2026. Simulator evidence proves demo behavior only. Real Stripe Checkout, signatures, events and refunds remain integration gates before actual orders. No public deployment, live charges, paid subscriptions, external marketing or customer messages.

## Decisions and runtime
- Medusa 2.21.2, Node 24.21.0, Next 16.3.8, persistent PostgreSQL 18.4 through a beta local wrapper. Separate React installations satisfy the engine/storefront dependency contracts. Offline lockfile check preserved every resolved package; root engine metadata now matches Node 24.
- Approved sample: Hass avocado, $2 each, 12 allocated online, real supplied photograph. One-avocado package and local-pickup handling persist; no ingredient/allergen claims supplied. Take-home avocado is exempt food, not a blanket tax exemption for the store.
- 33 unique supplied photos and three exact duplicate links are evidence, not 33 verified products. All 36 imported original source paths are currently unavailable; 33 cached photos and 33 previews are verified present. Later uploaded originals remain private; browser derivatives strip metadata.
- Published shop hours used for pickup at the user's direction. Initial cutoff/capacity are internal defaults pending operational confirmation.
- Private preview http://127.0.0.1:3100/; current optimized stack session 46128. Role access file: commerce/.runtime/access.txt, ignored and private. Never share config.json or backend/.env.
- Separate optional authenticated Astra worker, local explicit-text rules, OCR and installed Qwen3-VL identity proposals. Model suggestions require owner correction and approval. No photo transmission to a cloud model or Messages bridge installed.
- Engine owns commerce records. Custom avo tables hold evidence, approvals, audits, checkout bindings, pickup and packing surfaces. Supported engine workflows perform catalog, stock, payment and fulfillment changes.

## Acceptance audit
| Specification check | Verified evidence | Unfinished or unverified scope |
|---|---|---|
| 1. Owner input | Real multi-photo/HEIC evidence, metadata removal, explicit text details, 33 local OCR/manual/model candidate reviews, required primary-photo selection, private split drafts and missing-value holds: photo-candidates-live.log, dictated-unit-live.log, photo-orientation-heic-live.log | Reviewed identity/package matching; actual camera-origin HEIC verification |
| 2. Approval | Exact version/replay/native readback, explicit before/after comparison and real stock-change rejection: approval-stock-race-live.log, photo-readback-live.log | Full visual review and broader conversational interpretation still need verification |
| 3. Storefront | Approved catalog/detail/cart/pickup/status, native reservation-aware availability/sold-out behavior; final optimized build: catalog-availability-live.log, catalog-availability-build.log | Core responsive views checked; full keyboard/zoom and remaining error/active packing states; actual approved boxes/swaps |
| 4. Inventory | Competing baskets, transfers, reservations/buffers; stock operation receipts preserve later movement and restart: stock-race-smoke.log, stock-receipt-restart-summary.json | Actual shared-stock box purchase; journal-retention policy before launch |
| 5. Payment | Server/frozen quote, one simulator order/task, cancellation intent, late refund, raw SDK signature boundary: current-sample-journey.log, late-refund-live.log, payment-webhook-summary.json | Account-backed provider/HTTP webhook and card behavior; simulator/offline signatures are narrower evidence |
| 6. Stripe | Hosted adapter implemented; user explicitly deferred account and authorized simulator | Real test Checkout/webhook/refund integration remains deferred, not verified |
| 7. Pickup/packing | Slot/cutoff/DST, assignment, stages/actual contents/shortages, native fulfillment/refund, exact order facts/photo snapshot: current-sample-journey.log, customer-photo-history-live.log | Actual box recipe-change snapshot; operational capacity/lead confirmation; inline form visual walkthrough |
| 8. Recovery | Frozen quote, receipt recovery, lost refund/task/fulfillment acknowledgment, whole-stack paid-order restart, first-run setup and fresh 33-table/media/import/config restore: order-task-recovery-live.log, paid-order-restart-summary.json, current-handoff-restore.log | Actual provider late refund deferred; no arbitrary-process-kill claim |
| 9. Access/usability | Role/media/order isolation, optional worker outage, 68 current unit tests; declared contrast fixes/build: private-media-live.log, worker-stock-grounding-unit.log, dictated-unit-unit.log, static-contrast-summary.json | Full keyboard/200% zoom/physical-phone and active packing-form QA; responsive core views and 28 computed contrast samples now checked |

Evidence files are in commerce/evidence. A passing narrow test is not proof of the whole row. Earlier screenshots are not verification of subsequent interface changes.

## Available owner and staff work
Owner: product drafts and exact rejection/approval; real multi-photo evidence; candidate splitting; reviewed product details; receipts/transfers/recounts/spoilage/corrections with links and history; copy revisions/restoration; ordering/product pauses; pickup-window controls; immediate/dated specials; failed-draft replacement closure; simulator late refunds; recovery queue; private marketing drafts.
Staff: active-first queue by pickup time with terminal history; assignment; immutable accepted pack sheet; shortage/resolve; separately confirmed actual contents; ready and collected. Staff updates/audits commit together; a forced audit failure rolled back correctly.
Customer: approved real catalog, search/category/detail, quantities, basket persistence, unavailable-item recovery, pickup, clearly labeled simulator, cancellation/reset, session-protected order return status. No compulsory customer account beyond private preview access.

## Owner inputs and external gates
- Pending: one real box name, price, exact components/counts, component costs and optional replacement details. Three actual tier offers must not be fabricated.
- Authorized October 6: project-local Ollama/Qwen vision installation, loopback only. Installation and private draft integration verified; photos stay local.
- Trial: operational pickup capacity/lead time, handling evidence for other goods, tax classifications, customer policies/retention and contact details.
- Stripe deferred. Physical phone access needs an approved secure connection. Public hosting, delivery/shipping, POS replacement and outbound marketing remain outside this build.

## Next work in development order
1. Implement remaining independent inventory/offer/workflow requirements: full owner content-command coverage; exercise the new box-revision path when inputs arrive.
2. Review installed private photo interpretation against owner-confirmed identities; preserve the deterministic approval boundary.
3. Exercise actual approved box flow when owner inputs arrive. Complete remaining visual/accessibility walkthrough when browser access is permitted.
4. Verify clean install/migrations and broader restart failures; refresh final backup after functional changes. Maintain owner/employee handoff in commerce/README.md.
5. Perform final requirement-by-requirement completion audit. Do not mark complete with missing or indirect evidence.

Earlier inventory check: Versioned owner safety buffers are enforced against shared component stock minus current engine reservations, inside the checkout lock, before new holds. Two competing baskets with one remaining available unit produced one winner; its exact quote replay returned the same attempt. Packer/negative/stale setting writes were rejected. All test holds canceled, original buffer restored, and physical stock unchanged. TypeScript, optimized build and 41 unit tests pass. Actual approved box-buffer behavior and visual controls remain unverified.

Earlier packing check: Server-enforced preparing → picked → packed → ready → collected sequence. Packed requires explicit exact actual contents; ready revalidates the persisted packed contents. Unresolved shortages and skipped steps fail, repeated state calls are safe, and engine stock fulfillment remains at ready. Complete authenticated simulated order test passed, including narrowly injected audit rollback, shortage/resolve, invalid contents, picked/packed replay, collection, refund and confirmed-allocation restoration (commerce/evidence/packing-stages-smoke.log). TypeScript/optimized build passed. New UI stages still require visual review.

Latest offer work: Exact-version, repeat-safe private revisions clone a published box into a new draft with source provenance. Approval atomically marks the new offer published and source superseded in the custom policy store. Gateway hides private/superseded offers; old engine product/variant remains intact for prior accepted checkouts. Two competing revisions cannot replace an already superseded source. Ordinary product updates reject box recipes. Schema, TypeScript, optimized build and 41 unit tests pass; live authorization/unpublished-source guards pass without offer changes (box-revision-guards-smoke.log). Actual published replacement, competing-revision persistence and paid snapshot behavior remain unverified until owner box inputs arrive.

Latest intake check: Box evidence and private offer now save in one transaction with source-event replay protection. A scoped text-only insert fault rolled back evidence; after removal, retry retained three real photos, original references and duplicate links. One box/evidence pair survives replay, and missing price/cost blocks approval. Owner bootstrap reloads box evidence; customer/packer receive no internal offer records or component costs. Optimized build and authenticated test pass (box-intake-atomic-smoke.log). Uploaded-file failure cleanup beyond database rollback and new review-photo visual layout remain unverified.

Latest content check: Owner messages can draft welcome, owner-note heading and note copy. Successive messages preserve pending edits rather than reverting to published copy. Live test passed private accumulation, event replay without a new version, stale approval and packer-input rejection, and unchanged customer copy (content-message-smoke.log). Original published/private copy restored; test copy was never published. TypeScript, optimized build and 41 unit tests pass. Hours, featured items, specials and calendar text commands remain incomplete; do not count these three commands as full owner-command coverage.

Latest hours work: Displayed store hours are now versioned approved website copy, with owner form review and “Set the store hours to: …” text intake. Legacy copy defaults to the previously verified hours. Live test proved private edits accumulate, customer copy stays unchanged, pickup-window settings and accepted task snapshots remain unchanged, and original copy is restored (hours-message-smoke.log). No test hours were published. Optimized build and 41 unit tests pass. Specials, featured-item and calendar text commands remain incomplete; new hours layout still needs visual verification.

Latest owner experience: Added bounded newest-first persisted activity endpoint, owner-only on server. Astra view summarizes actions, names, timestamps and recorded quantity/price receipts with optional before/after detail. Read-only live access/order/bounds test passed (activity-smoke.log); optimized build passes. This is audit history, not invented chat replies. Visual/mobile readability remains unverified under the browser restriction.

Latest feature work: Text command “Feature [approved product name]” creates a private homepage feature using its real photo/current price; “Stop featuring products” clears it. Content approval is bound to the product source revision and rejects subsequent product changes until re-review. Live test passed private isolation, unknown-product/packer rejection, source-event replay, changed-product hold, approved real feature and clear; original copy/selection restored (feature-message-smoke.log). No product/discount invented. A stylesheet overwrite was caught by the build; exact earlier CSS recovered from its local source map and later styles reapplied. CSS recovery hash/prefix evidence saved, optimized build passes. New feature visual layout remains unverified. Specials and calendar text commands remain incomplete.

Latest reproducibility check: Fresh isolated commerce npm ci passed from the unchanged lockfile. All 17 direct versions match; Sharp native image encoding, esbuild transform and Medusa framework import work (clean-install-summary.json). Fresh storefront npm ci and optimized build also pass with exact direct versions checked (clean-storefront-summary.json). Active data/runtime was untouched. Installer reported unapproved package hooks; required native/module checks succeeded without broadly enabling them. This is a clean dependency directory on this Mac, not a separate-machine or empty-engine migration test.

Latest clean-engine check: Fresh migration exposed double TypeScript loading and implicit provider-path resolution errors. Fixed explicit index.ts/service.ts imports, TypeScript extension/noEmit settings, and removed redundant tsx import from the launcher/setup migration command. Isolated migration completed, backend health/internal authentication passed, and two real-photo bootstrap runs retained exactly 34 private drafts/evidence with zero products/orders (clean-engine-summary.json). Backend TypeScript and main simulator paid/packing/audit-fault/refund cleanup pass with the corrected loader (native-loader-commerce-smoke.log). Isolated database/backend stopped; original store preview restored. Initial migration required diagnosis/retries, so a fresh uninterrupted first-run with the final setup remains to be proved.

Latest first-run proof: New workspace/database had zero public tables, then the corrected migration completed on its first attempt. Fresh backend health/internal authentication and repeat-safe engine setup pass. Seeding retained 34 private real-photo/sample drafts with no catalog products or orders (first-run-summary.json). Reused the previously verified clean dependency installation; did not claim a separate machine. Isolated services stopped; original preview remained running and unchanged during this test.

Latest calendar work: “Close pickup on YYYY-MM-DD” and “Reopen pickup on YYYY-MM-DD” create persisted private proposals with exact window versions and prior states. Owner-only approval atomically changes availability and audits it; changed windows require a new request, replay is safe. Live closure test passed ambiguous-date rejection, source replay, packer denial, stale-window rejection, new-checkout blocking, unchanged existing pending checkout and accepted task snapshots. Original windows restored and pending hold canceled (pickup-command-smoke.log). TypeScript, optimized build and 41 unit tests pass. New proposal table added to restore verifier but fresh backup/restore remains due; reopen and post-closure paid fulfillment paths now pass their runtime test. Specials and broader natural-language coverage remain incomplete.

Latest calendar completion proof: A pending real-avocado simulator checkout completed payment and every packing stage after its window closed, retaining its original pickup label/items. Reopen approval/replay allowed a new checkout. Test order refunded after collection, pending hold canceled, original window flags and confirmed allocation restored (pickup-completion-smoke.log). Read-only reservation audit currently finds zero refunded orders with active reservations; existing refund tests cover fulfilled orders, so unpacked-refund reservation release is still unproven and is the next integrity check.

### Resumed after disk cleanup — 2026-10-05
- Disk check: 30 GiB available. Optimized refund-release build passed.
- Private optimized preview running at http://127.0.0.1:3100/ (launcher session 72815).
- Replayed the earlier refunded simulator task to release its stranded reservation; API returned 200.
- Unpacked refund regression passed: one reserved unit became zero, physical stock stayed unchanged, replay remained safe. Evidence: commerce/evidence/unpacked-refund-summary.json.
- Full packing/exception/refund regression passed. Evidence: commerce/evidence/refund-release-regression.log.
- Real Stripe remains intentionally deferred. Browser visual QA and the other documented goal gates remain incomplete.

### Accepted product facts and refreshed recovery proof — 2026-10-05
- Checkout now freezes reviewed description, package, ingredients, allergens, handling and source revision alongside the recipe. Recipe data is copied rather than shared with a mutable catalog object. Existing orders remain unchanged.
- Focused helper test proves later catalog edits cannot change the accepted facts or recipe. Simulator checkout read back identical facts from the durable database: commerce/evidence/order-facts-unit.log and order-facts-live.log. No invented product claims were published.
- Clean offline backup restored successfully on isolated port 55433. All 29 selected business tables, uploaded media hashes and private configuration matched: commerce/evidence/restore-summary.json. This proves this snapshot, not all crash boundaries.
- Preview restarted after backup, launcher session 19045.

### Pickup approval covers the whole date — 2026-10-05
- Re-read the build document: owner-confirmed specials remain explicit unfinished scope, alongside photo identification, boxes and full visual QA.
- Pickup-date approval now rejects added, removed, expired or version-changed windows. It cannot silently apply only the old subset.
- Unit checks cover changed membership, expiry (empty/removed list) and versions. Live test added a temporary same-date window, confirmed approval returned 409 without changing original availability, then removed the fixture. Closure/replay, role denial, accepted-order preservation and cleanup passed: commerce/evidence/pickup-set-unit.log and pickup-set-live.log.
- Private optimized preview ready, launcher session 59387. Next independent implementation: owner-confirmed specials with bounded quantities/rules and exact approval; do not fabricate offers.

### Explicit immediate specials — 2026-10-05
- Owner can send “Special: Hass avocado, each, $1.50, 4 available for online pickup” as a private draft for an already approved individual product. This is an internal syntax example, not an approved public offer.
- Requires lower positive price, positive explicit total online allocation and exact approved identity/unit; boxes, ambiguous products, percentage discounts and scheduled dates are held. No urgency or impact claims are generated.
- Existing review shows the observation that no end date or automatic restoration is set. Existing exact-version product approval performs supported price/stock changes and preserves the real photo/product details.
- Unit tests and live simulator test passed: proposal did not change catalog, source replay reused draft, approval changed server price, earlier accepted checkout stayed identical, approval replay safe. Cleanup canceled the hold and restored $2/12. Evidence: commerce/evidence/special-command-unit.log and special-command-live.log.
- Still unfinished: scheduled promotions/automatic restoration, broader natural-language discount rules and distinct storefront promotion treatment. This immediate workflow is partial progress toward the full specials requirement. Runtime session 70627.

### Special-source approval safety — 2026-10-05
- Special proposals now retain their approved product ID, revision and original price. Before first application, a changed or paused product requires a new proposal. Review notes explicitly show old/new price and total online quantity.
- Frozen approved targets remain retryable after an interrupted engine update; exact applied-version replay remains unchanged. Editing a special retains its source binding.
- Focused tests passed. Live competing-draft test: first approval changed the product, second approval returned 409, previous checkout stayed unchanged, and cleanup restored $2/12. Evidence: commerce/evidence/special-source-unit.log and special-source-live.log.
- Runtime session 68403 loads both the source guard and final review-note wording; private optimized stack reports READY. Scheduled offers and full visual verification remain incomplete.

### Durable quote price survives cart recreation — 2026-10-05
- Found a prerequisite for timed offers: native cart creation previously used current catalog price. It now uses unit prices from the attempt's durable server-authored snapshot through supported createCartWorkflow inputs, not from the browser or request body. Native cart total must still match the accepted quote.
- Backend TypeScript passed. Live fault-boundary fixture stored a creating attempt, changed approved catalog price from $2 to $1.50, reconciled it, then verified Medusa line prices and paid simulator order retained $2. Client penny price ignored. Test order refunded and sample $2/12 restored. Evidence: commerce/evidence/frozen-price-recovery.log.
- First verifier attempted to query computed cart.total as a physical database column; it failed and cleaned up. Corrected verifier reads persisted line prices; second run passed. No production core records were directly mutated.
- Backend watcher reloaded successfully in current stack session 68403. Scheduled specials remain incomplete; this fixes their required accepted-price/recovery boundary.

### Native dated price-list proof — 2026-10-05
- Verified installed Medusa supported create/update/delete price-list workflows plus pricing calculatePrices on the real approved Hass variant. Native dates selected $2 before start, $1.50 while active and $2 after expiry; removal restored $2. No physical stock change or real payment.
- Temporary simulator-only authenticated diagnostic endpoint was removed after the check. Diagnostic source is retained as evidence, not a shipped owner workflow: commerce/evidence/native-dated-pricing-probe.ts.txt and native-dated-pricing-summary.json. Backend TypeScript passed before and after.
- This is native-engine evidence for scheduled offers, not proof of a complete scheduled-special feature. Remaining implementation: dated owner proposal/review and revisions, server catalog calculated prices, quantity/allocation rule and exact approval/recovery, storefront treatment, accepted-checkout boundary integration. Runtime watcher reloads restored source in session 68403.

### Dated-special owner workflow implemented and API-verified — 2026-10-05
- Added durable scheduled_specials proposals; owner text captures approved identity, real photo, lower fixed price, explicit quantity and exact dates. Ordinary local clock times use Los Angeles; calendar errors and missing/repeated DST times are held. Review includes exact old/new price, dates, allocation rule and affected pages.
- Exact-version approval checks unchanged product revision and physical bin count, rejects overlapping offers, protects reservations, checkpoints stock application, creates/reuses supported native dated price list and verifies readback. Cancel/reject record reasons; closure state and audit commit together. Accepted orders/stock are not restored on cancellation or expiry. Engine price lists own the dated prices.
- Catalog and quote use native calculated prices. Listings/details show the active end time. Approved public offer metadata excludes private evidence/allocation details. Accepted discounted orders freeze offer ID/dates. A new displayed-total mismatch returns 409 and refreshes the basket for review; retries of the same accepted identities/quantities use the durable prior quote.
- Optimized build/backend TypeScript passed; 9 focused unit checks passed. Live scheduled flow: private until approval, stale/packer/overlap guards, price applied, older checkout unchanged, normal price after cancel, discounted accepted checkout paid/refunded, source/approval replay safe. Full interrupted checkout and packing/refund regressions passed.
- Natural expiry test passed across actual clock boundary: new catalog returned $2 automatically while an accepted $1.50 checkout replayed, paid and refunded at its saved price. All internal offers closed, holds released, sample $2/12 preserved. Evidence: commerce/evidence/scheduled-special-live.log, scheduled-natural-expiry.log, scheduled-final-unit.log, scheduled-special-build.log, scheduled-recovery-regression.log and scheduled-packing-regression.log.
- Fresh pre-expiry-test backup restored on isolated port 55433; all 32 selected tables now include proposals, native price lists/rules, plus media/config hashes: restore-summary.json. Later internal expiry-test records are newer than that snapshot.
- Private optimized runtime session 94253. Whole goal is still incomplete: photo model permission/input gates, actual boxes/swaps, real Stripe deferred, wider crash recovery and all-view visual QA. Dated-special UI is build-verified but not visually reviewed due browser policy. Percentage discount phrasing is not supported; fixed-dollar rules are supported.

### Durable stock receipts protect later inventory — 2026-10-05
- Stock quantities and applied operation receipts now persist together through the supported native inventory-level workflow. A replay returns current stock and original applied target instead of recounting an old target. Durable source binding rejects a different operation/target. Stock movements, scheduled allocation and product approvals share this helper.
- Product approvals freeze source balance and catalog revision. Code rejects replay over a later catalog revision; legacy interrupted approvals lacking a frozen source balance require a new reviewed update. This superseded-revision branch is not yet separately exercised.
- Fault tests injected scoped custom audit failures after engine stock updates. A later movement restored 13 to 12; retrying either the stock receipt or product approval preserved 12. Product photo, description, package/ingredient/allergen/handling fields were unchanged. Both triggers removed.
- Backend TypeScript passed. Scheduled offer, linked correction and complete packing/refund regressions passed. After a full process/database restart, replay of the native receipt still preserved current 12 instead of target 13. Evidence: commerce/evidence/stock-receipt-recovery.log, product-stock-receipt.log, stock-receipt-restart-summary.json, stock-receipt-special-regression.log, stock-receipt-correction-regression.log and stock-receipt-packing-regression.log.
- Refreshed offline backup restored successfully; 32 selected business tables (including inventory metadata receipts), media and private configuration matched. Evidence: stock-receipt-restore.log and restore-summary.json.
- Private optimized stack session 30578. Sample remains $2/12. Whole goal remains incomplete; these checks prove the stock acknowledgment boundary, not every process-crash boundary. Receipt history is retained in native inventory metadata for this PoC; trial/launch storage policy still needs review.

### Failed approval resolved after a verified replacement — 2026-10-05
- Added explicit owner closure for exception-state product drafts after a newer applied revision becomes current for the same product. Checks exact original version, replacement identity/current revision and reason; state/link/reason/audit commit together. Closed drafts cannot edit or approve again. No engine product/stock mutation occurs during closure.
- Live fault test: old approval stock applied but audit failed, newer reviewed $2.25/12 update became current, old retry returned 502 without overwriting it, then exact owner closure recorded the replacement once and removed the exception. Packer/stale/self-replacement/changed replay denied; closed edit/reapproval denied. Catalog and stock unchanged by closure. All internal test changes restored to $2/12, trigger removed. Evidence: commerce/evidence/superseded-product-live.log. This also exercises the previously unverified later-catalog-revision guard.
- Ordinary rejection regression passed; optimized build passed. Astra review presents the closure and retained reason. Activity names the action plainly and distinguishes recovered stock acknowledgments from new stock changes. UI remains visually unverified due the existing browser policy. Evidence: superseded-rejection-regression.log and superseded-draft-build.log.
- Private stack restarted to load final UI; runtime handle recorded below after READY verification. Goal remains active; no change to original completion gates. Latest backup predates this closure test's audit records.

- Final owner UI stack reports READY; current launcher session 93284.

### Closed-payment lifecycle and native simulator refund — 2026-10-05
- Cancellation now persists intent and retains the closed native payment session. Reconciler completes interrupted unpaid cancellations and routes paid cancellation intents to non-packing review. Creating-state recovery recognizes closed native sessions; it cannot reopen them.
- Owner-only late-refund action is simulator-only. It verifies the original paid reference/amount, authorizes/captures through the native payment module, refunds through its supported API, verifies full capture/refund sums, releases remaining provenance-bound temporary holds, and updates customer status/queue/audit. Replay uses the same financial records; changed reasons/roles rejected. No order or packing task is created and physical stock is unchanged.
- Existing legacy deleted-session simulator record recovered with its original provider reference and refunded. Real Stripe adoption/refund is not enabled or claimed tested. Source reference: https://docs.stripe.com/api/refunds/object documents pending/failed refund states; this gates provider verification before enabling the path.
- First live run used the native order-refund workflow, which failed because there was no order link. Captured funds remained in review, then the same reference was successfully retried through the payment-module refund API. Failed evidence retained: commerce/evidence/late-refund-first-failure.log.
- Scoped audit-failure test proved a completed native refund survives a lost final acknowledgment and retry does not duplicate it. Trigger removed. Cancellation-intent tests cover unpaid interruption, closed-session creating checkpoint and payment during cancellation with a remaining temporary hold.
- Backend TypeScript and optimized build passed. Live checks and full cancellation/reset, checkout recovery, packing/refund regressions passed. Evidence: commerce/evidence/late-refund-live.log, legacy-late-refund-summary.json, cancellation-intent-live.log, late-refund-build.log, late-refund-reset-regression.log, late-refund-recovery-regression.log and late-refund-packing-regression.log. Sample restored to $2/12.
- Refreshed offline backup includes new financial records; restore verification now explicitly includes captures (33 selected tables). Result and current runtime recorded after verification below. Whole goal remains active: real Stripe, photo identification, actual boxes and full visual QA remain incomplete.

- Fresh restore passed for all 33 selected tables, media and private configuration. Private optimized stack reports READY; current launcher session 49723. Evidence: commerce/evidence/late-refund-restore.log and restore-summary.json.

### Offline provider signature boundary verified — 2026-10-05
- Tested the actual payment adapter with the installed Stripe SDK and fixture-only secrets. No Stripe API methods were available; all database writes used one isolated transaction that rolled back. Explicit post-rollback query proved zero fixture events remained. Main runtime stayed in simulator mode.
- Raw Buffer and string signatures accepted; duplicate event stored once; later expired event preserved earlier paid evidence. Wrong secret, altered whitespace, parsed-object payload, missing header, stale timestamp and signed live-mode event rejected. Unsupported event ignored. Adapter returned not_supported, so it nominated reconciliation evidence rather than completing an order.
- Evidence: commerce/evidence/payment-webhook-offline.log and payment-webhook-summary.json. Official raw-body guidance: https://docs.stripe.com/webhooks/signature. This does not prove the actual HTTP middleware, Stripe account session, webhook delivery or real refund; those remain gated.
- Current complete gateway unit suite: 50 passed, zero failures (commerce/evidence/current-unit-suite.log). Updated acceptance table reflects current evidence without claiming full completion. Preview remains the existing live optimized stack, session 49723; no restart or new backup needed for rolled-back fixture-only checks.

### Owner percentage rules implemented — 2026-10-05
- Immediate and dated special messages now accept an explicit percentage (up to two decimals) in place of the fixed dollar price. Shared deterministic helper uses integer/BigInt cents, with nearest-cent unit-price rounding (half cents up); no model performs money arithmetic. Resolved price must be positive and below the reviewed regular price.
- Source retains the original discount expression/rule. Approval rejects an edited price that disagrees with that rule or a changed source price/revision. Dated review shows the percentage, rounding and exact dollar result. Native engine stores the approved fixed amount. Quantity remains explicitly owner-supplied.
- Optimized build and full 54-unit suite passed, including fractional percentage, half-cent and large-integer boundaries. Immediate/datetime live “25% off” flows passed privacy-before-approval, native price, earlier quote preservation, stale/overlap/replay guards and refund/cleanup. Sample $2/12 restored; all internal offers closed. Evidence: commerce/evidence/percentage-full-unit.log, percentage-immediate-live.log, percentage-scheduled-live.log and percentage-build.log.
- An initial suite command ran from the wrong directory and discovered zero tests; ignored as evidence. Correct commerce-directory run discovered and passed 54.
- Private optimized runtime session 14938. Existing latest backup predates these percentage test records; backup mechanism itself is unchanged. Whole goal remains incomplete. Next independent check: real HEIC camera uploads, since all supplied originals are HEIC and the owner workflow must accept phone photos.

### Phone-photo intake and imported-asset recovery — 2026-10-05
- Disk space verified: 24 GiB available after owner cleanup. Preview resumed; optimized launcher session 96972 reports READY at http://127.0.0.1:3100/.
- HEIF/HEIC intake uses local macOS sips fallback when Sharp lacks HEVC decoding, followed by bounded, rotated JPEG conversion and metadata removal. Original upload bytes remain private. Live technical HEIC fixture passed duplicate-event, private-original and unpublished-draft checks; all 56 unit tests passed. The fixture was encoded from an authentic preserved JPEG, not a phone-origin original.
- All 36 original source paths in the import manifest are currently unavailable; cached JPEG assets remain. Evidence: commerce/evidence/original-photo-availability.json, heic-upload-summary.json, heic-upload-live.log and heic-full-unit.log. Actual phone-origin HEIC upload remains unverified.
- Fixed backup omission: entire inventory-intake directory is now included alongside database, uploaded media and private config. Fresh offline backup and isolated restore passed SHA256/file-set comparison of all 74 imported asset files, uploaded media, private configuration and 33 selected database tables. Evidence: commerce/evidence/heic-restore.log and restore-summary.json.
- Whole goal remains active: actual box inputs, automatic photo identification, full browser QA and deferred Stripe integration remain open.

### Native fulfillment acknowledgment recovery — 2026-10-05
- Scoped simulator test forces custom audit failure after native ready and collected operations. Custom task rolls back to packed/ready, while native fulfillment/delivery persists. After removing each fault, retry reuses the exact single fulfillment and unchanged delivered timestamp; each stage has exactly one committed audit. State replay also succeeds.
- Evidence: commerce/evidence/fulfillment-recovery-live.log; reproducible script commerce/scripts/fulfillment-recovery-smoke.mjs. Fault trigger/function removed in finally. Test order refunded in simulator and owner-confirmed allocation restored to 12. This covers the lost acknowledgment boundary, not an arbitrary OS-process kill.
- Prior goal turn classified progress: HEIC local conversion and full imported-asset backup/restore verified. Current turn also progress: new live fulfillment recovery evidence. No completion claim; pending owner inputs/vision runtime/full browser QA remain. Current backup predates this latest simulator order; refresh before final handoff.

### Numeric owner-message clarification — 2026-10-05
- Requirements audit exposed regex truncation risk: fractional quantities could match only the trailing integer, and over-precision money could become a smaller valid amount. Parser now rejects these numeric forms and clears previous values when malformed explicit replacements are supplied. Ordinary comma-delimited $2 input remains supported.
- All 57 gateway unit tests pass (commerce/evidence/numeric-intake-unit.log). Live owner intake verified fractional quantity and over-precision price stay unknown, generate questions, and fail approval with 422. Private fixture drafts rejected; no catalog/stock mutation. Evidence: commerce/evidence/numeric-intake-live.log.
- Restart loaded corrected parser; optimized stack session 14674 reports READY. No frontend changes; prior optimized build reused. Full goal remains active; unresolved gates retain original scope.

### Product facts through owner text — 2026-10-05
- Added explicit labeled description, package size, ingredients, allergens, handling and category intake. Worker boundary keeps bounded strings; existing-product inheritance now preserves explicit owner corrections rather than overwriting them with published facts. Omitted details retain existing reviewed values; empty details propose clearing. No photo-derived facts inferred.
- All 58 gateway tests pass (commerce/evidence/text-details-unit.log). Live authenticated worker-backed intake retains details privately, preserves known tax class, deduplicates source event, and leaves published description unchanged. Private test draft rejected. Evidence: commerce/evidence/text-details-live.log. Existing exact-version approval/readback path still governs publication.
- Optimized preview restarted with corrected gateway/worker, session 79006. No frontend edits. Full scope remains active; automatic image identity, actual boxes and full browser QA remain unverified.

### Product photo/copy readback and order evidence — 2026-10-05
- Native product approval now reads and verifies description, thumbnail and category in addition to price, identity, metadata details and stock. Accepted basket snapshots record the actual product photo path, so later catalog image replacement cannot change that accepted evidence.
- All 58 gateway tests and backend TypeScript pass. Native approved product-details and later text-only updates pass the stronger readback, retaining authentic photo/$2. Simulator checkout/packing/refund and fulfillment acknowledgment regression pass; allocation restored to 12. Direct database read verifies photo in the accepted attempt linked to paid packing task. Evidence: commerce/evidence/photo-snapshot-unit.log, photo-readback-typescript.log, photo-readback-live.log, photo-snapshot-commerce.log and photo-snapshot-persisted.json.
- Unit test proves snapshot photo independent of later in-memory catalog replacement; actual live photo replacement walkthrough still unverified. No synthetic images or claims added. Current optimized runtime session 16987. Whole goal remains active.

### Live photo revision and fresh restore — 2026-10-05
- Created a simulated paid order, uploaded the previously confirmed authentic Hass photo as a new revision, verified catalog photo stays unchanged before exact approval, then native readback and authenticated JPEG serving reflect the new upload path. Product identity, price, package and description retained. No synthetic inventory or alternate product photo used.
- Direct persisted attempt and packing-task read proved the full earlier accepted snapshot, including original photo, stayed byte-equivalent after catalog approval. Packing/collection/refund passed and confirmed allocation restored to 12. Evidence: commerce/evidence/photo-replacement-live.log and photo-replacement-summary.json; reproducible scripts/photo-replacement-smoke.mjs.
- Fresh offline backup followed by isolated restore passes 33 selected tables, uploaded media, 74 imported assets and private configuration (commerce/evidence/photo-replacement-restore.log, restore-summary.json). Private optimized runtime restarted, session 2711.
- Prior turn and current turn classify as progress with persisted implementation/test evidence. Full goal remains unproven due original outstanding gates.

### Inline packing action forms — 2026-10-05
- Replaced native browser prompts for assignment, shortage reporting/resolution and full refund with labeled inline forms, bounded text, cancel controls and explicit refund explanation. Pending operations disable controls. Shared request wrapper returns success/failure so failed saves keep the entered text rather than closing the form. No commerce transitions or authorization changed.
- Optimized Next build including TypeScript passed (commerce/evidence/packing-inline-build.log). A first build failed after a wrong working-directory edit attempt left temporary syntax errors; fixed with absolute paths, then full build passed. Prior API stage/recovery evidence remains applicable to unchanged server routes, not proof of the new UI interactions.
- Current optimized preview session 76142. Actual keyboard/mobile interaction, focus behavior and visual fit remain unverified under browser restriction. Full goal stays active.

### Whole-batch photo validation — 2026-10-05
- Owner intake now validates and normalizes every attached image before writing any originals or derivatives. A corrupt later image cannot leave earlier unlinked files. Sequential preparation bounds concurrent codec work; photo count/size limits remain unchanged.
- Live mixed-batch test with one authentic retained JPEG and one corrupt image returns 422; exact before/after media file set matches and source event has no evidence row. All 58 gateway tests pass. Evidence: commerce/evidence/multi-photo-invalid-live.log and multi-photo-validation-unit.log. This proves prevalidation failure cleanup, not filesystem write failures or arbitrary process crashes.
- Requested pending vision installation decision and real box price/recipe/cost inputs together via async question. No model installed and no fabricated offers created. Current optimized runtime session 19336. Goal remains active with substantive independent progress.

### Upright bounded phone derivatives — 2026-10-05
- Verified EXIF rotation is applied before metadata removal. Changed derivative resizing from width-only to fit inside 1400×1800 without cropping or enlarging, preventing tall/narrow phone images from producing excessive output dimensions. Original bytes remain untouched and private.
- All 60 unit tests pass, including orientation 6 and portrait/narrow aspect-ratio retention (commerce/evidence/photo-orientation-unit.log). Local authentic-photo HEIC technical fixture upload passes revised two-axis bounds, metadata removal, original-byte privacy and replay checks (photo-orientation-heic-live.log). Actual camera-origin HEIC remains unverified because supplied original paths are unavailable.
- Runtime session 12004 serves the change; no frontend rebuild needed. Vision installation and real box inputs still pending. Full goal remains active.

### Owner approval comparison — 2026-10-05
- Added owner-only read-only draft preview with current product revision, regular current price, physical online-bin quantity and computed receipt/recount target. Product review displays before/after price and quantity, with explicit refresh; approval remains disabled until a comparison loads.
- Web approvals send reviewed product/version/stock/revision. Inside the stock lock, mismatches reject before applying; interrupted already-frozen approvals retain their original recovery semantics. Legacy internal approval scripts without review remain supported; this check does not replace existing validation, exact draft version and stock receipt guards.
- Live test verifies packer denial, actual $2/12 comparison, wrong stock/product/version/revision rejection, exact approval and replay; confirmed price/quantity unchanged. Final optimized build passes. Evidence: commerce/evidence/approval-comparison-live.log and approval-comparison-build.log. No visual/keyboard/mobile walkthrough claimed.
- First relative-path edit failed before modifying files; corrected with absolute paths. Final runtime handle recorded in tool output; full goal remains active.

### Actual stock-review race and handoff reconciliation — 2026-10-05
- Live receipt changed physical stock 12→13 after comparison. Earlier approval rejected with 409; fresh comparison showed 13→12 recount, exact approval/replay succeeded and confirmed quantity restored. Evidence: commerce/evidence/approval-stock-race-live.log.
- Verified all 33 cached full photos plus all 33 previews exist, with byte counts/hashes recorded; manifest retains three exact duplicate links. Imported originals remain unavailable. Evidence: commerce/evidence/imported-cache-verification.json. Corrected stale ledger runtime and original-file status.
- Current goal is active; remaining major gates are local visual-model decision, actual box recipes/prices/costs, full permitted browser QA and deferred account-backed Stripe integration. Current backup predates latest approval records; refresh before final handoff.

### Local OCR for all imported inventory evidence — 2026-10-05
- Ran installed local Apple Vision OCR over all 33 unique cached owner photos. Bounded confidence-bearing label lines are now attached to the original private unreviewed draft with per-photo cached-byte hash and actor/source audit. No product name, price, quantity, certification, tax class or eligibility inferred; previously reviewed drafts are excluded. Original evidence and duplicate links preserved.
- Replay verification reran all 33 and proved exact draft versions/fields unchanged. No duplicate import audit inserted due deterministic source-event key. Evidence: commerce/evidence/import-label-live.log, import-label-summary.json, import-label-replay.log and import-label-replay-summary.json. Reproducible scripts/import-label-evidence.mjs.
- Existing review UI already renders label lines; no new frontend build. Actual visual readability remains unverified; OCR text is untrusted evidence, not automatic identity. Current stack session 72461 stays running. New private OCR records require next backup refresh. Full goal active; vision model decision/real boxes/full browser QA still pending.

### Private OCR restore and unpublished-media access — 2026-10-05
- Live role checks prove owner receives all 33 private OCR drafts with unknown name/price/count; visitor/packer bootstrap omits labels/drafts and direct comparison returns 403. Evidence: commerce/evidence/import-label-access-live.log and import-label-access-summary.json. Fresh offline backup/isolated restore passed all 33 tables, media, 74 imported assets/config (import-label-restore.log).
- Found derivative-media route allowed any authenticated role to read unapproved photos by known URL. Restricted non-owner access to approved current catalog photos, existing explicitly used website images and authorized accepted-order photo snapshots. Packer keeps photos of orders with tasks; customers get only their own snapshot media. Private originals remain rejected by filename rules.
- Live check verifies private imported and rejected-upload derivatives 404 for visitor/packer and 200 for owner; site/catalog images still work. Historical accepted photo works for packer while unrelated visitor is denied. Evidence: commerce/evidence/private-media-live.log and private-media-summary.json. Actual same-customer historical media path is implemented but not independently tested.
- No frontend edits. Runtime 28159. Goal remains active; original major gates remain pending.

### Customer-owned historical photo access — 2026-10-05
- Created a real visitor-session simulator order, approved a new upload revision of the authentic confirmed Hass image, and verified the customer's accepted order still returns/serves its previous image. A different visitor receives 403 for the order and 404 for the historic image; current approved catalog image remains accessible.
- Unpacked simulator order refunded in finally; no packing/stock fulfillment occurred. Evidence: commerce/evidence/customer-photo-history-live.log and customer-photo-history-summary.json. Reproducible scripts/customer-photo-history-smoke.mjs. No real customer messages, real payments or synthetic inventory.
- This completes the previously untested same-customer historical media boundary. Runtime remains 28159. Full goal stays active; next remaining major work depends on vision-model decision, actual box inputs and permitted browser QA. Latest backup predates this simulated order/photo revision.

### Declared contrast and control dimensions — 2026-10-05
- Source inspection found transparent secondary/add/category/intake controls inherit dark hover background but keep green foreground, contrast 1.41:1. Added explicit white hover text for those controls. Existing transparent link/name exceptions keep their own readable styles.
- Corrected checkbox min-height/padding/margin inherited from global text-input styling; clickable label remains at least 44px. Primary text links now declare 44px height. No visual palette change.
- Deterministic sRGB contrast checks pass for declared body/muted/emphasis/button/hover/error color pairs (4.5 threshold) and focus outline/paper (3 threshold). This checks declared pairs, not all computed browser contexts. Optimized build passes. Evidence: commerce/evidence/static-contrast.log, static-contrast-summary.json and static-accessibility-build.log.
- Actual full phone/desktop keyboard/zoom/contrast walkthrough still unverified under browser policy restriction. Goal stays active with remaining gates; current runtime handle in launch output.

### Owner-grounded financial and stock proposals — 2026-10-05
- Optional worker's valid-looking price/count/action/pool no longer suffice: gateway extracts those fields only from explicit owner message and gives explicit owner identity/details precedence. Photo candidate identity/label evidence remain proposed private fields. This prepares a future vision worker without letting label/shelf guesses invent allocation or price. Manual exact-version owner edits remain available.
- All 61 unit tests pass, including valid-integer worker guesses, conflicting explicit owner values and malformed fractional replacements. Live numeric clarification and text-detail flows pass with the real worker (commerce/evidence/worker-stock-grounding-unit.log, worker-grounding-numeric-live.log, worker-grounding-details-live.log). No catalog change; private test drafts rejected.
- First live attempt started before gateway readiness and failed with ECONNREFUSED; existing launch reached READY, checks reran successfully without another restart. Runtime session 90924. No frontend rebuild required. Goal remains active; major pending gates unchanged.

### Native paid order to packing-task checkpoint — 2026-10-05
- Scoped trigger fails only the new simulator attempt's task insert after supported native cart completion. Native order persists, custom paid/task transaction rolls back and attempt records exception. Removing fault and retrying uses the exact original native order; repeat stays one order/one task. Full simulator refund passes.
- Evidence: commerce/evidence/order-task-recovery-live.log and order-task-recovery-summary.json; reproducible scripts/order-task-recovery-smoke.mjs. Trigger/function removed in finally. No core financial writes or synthetic inventory used. This verifies a failed task checkpoint, not an arbitrary process kill.
- Prior turn classified progress (grounded worker inputs), current turn progress (new consequential recovery evidence). Whole goal remains active; completion not proven. Local vision decision, actual box inputs and permitted full browser QA remain the principal dependencies. Current runtime 90924; backup predates newest simulator order.

### Whole-stack paid-order restart — 2026-10-05
- Prepared an uncollected simulator order, saved exact hashes/counts for paid attempt, task, native order, payment session, payment and capture, stopped entire preview/database, backed up and restarted. All six record-family hashes matched after restart; packing queue retained one paid task with accepted quantity. Completion replay retained exact financial records and order.
- Isolated restore of that live-paid checkpoint passed 33 business tables, media/import assets/config. Then simulator refund verified, and a second clean backup/isolated restore passed so latest backup does not revive the test as active paid work. Evidence: commerce/evidence/paid-order-restart-prepare.log, paid-order-restart-verify.log, paid-order-restart-summary.json, paid-order-backup-restore.log and paid-order-clean-restore.log. Reproducible scripts/paid-order-restart-smoke.mjs --prepare, full stop/start, then script without flag.
- Runtime session 94597. This is clean full-process restart evidence, not arbitrary kill during a write. Goal remains active with unresolved major gates.

### Manual review of imported shelf candidates — 2026-10-05
- Read all local OCR rows and visually inspected all three supplied-photo contact sheets covering 33 unique images. Saved grounded candidate notes for pantry, bread, dairy, eggs and produce; two store overviews marked context-only. Guessed prices/counts, organic/local certifications and fulfillment claims excluded. Identity suggestions are not confirmed products. Evidence source: commerce/evidence/import-label-review-source.json and import-photo-candidates.json.
- Added private owner candidate controls using existing exact-version shared-photo split workflow. Reviewers create a separate draft with explicit candidate name; unit/package, price, stock and handling/tax still need confirmation. No catalog products created. Manually curated notes are distinct from automatic future vision identification.
- Import/replay logs show 33 notes added then zero repeat changes. Live test verifies all 33 preserve unknown fields, exactly two context photos, child provenance/shared photo/replay, approval 422 and unchanged catalog; child rejected. Optimized build passes. Evidence: commerce/evidence/photo-candidates-import.log, photo-candidates-replay.log, photo-candidates-live.log and photo-candidates-build.log. Full visual UI QA still pending.
- Restarted preview to serve new controls; current handle in launch result. Whole goal active. New note records need backup refresh before final handoff.

### Owner handoff aligned with current build — 2026-10-05
- Updated commerce/README.md for manually reviewed shelf candidates/shared-photo drafts, before/after comparison and stale approval, source-photo availability, bounded HEIC/metadata conversion, original/derivative privacy, inline packing forms, backup coverage and precise open acceptance gates. Removed inaccurate claim that local manifests were committed.
- Rechecked current owner OCR access and unpublished media boundaries successfully after the candidate-note changes; evidence: commerce/evidence/handoff-owner-access.log and handoff-media-access.log. Guide distinguishes implemented behavior from unverified visual interaction and deferred real payment.
- Previous turn progress (all-photo review/private candidate controls); current turn progress (required handoff brought current and access revalidated). Runtime16340. Next principal dependencies remain owner vision decision, real box inputs and permitted browser QA; no account setup or model install inferred from silence.

### Native reservation-aware storefront availability — 2026-10-05
- Found storefront lacked availability/sold-out display despite correct checkout stock enforcement. Gateway now derives each variant's purchasable quantity from native physical stock minus reservations and safety buffer, divided by exact shared component requirements. Repeated component links aggregate; missing stock gives zero and invalid component counts fail review.
- Listing/detail controls display sold out, prevent local additions exceeding the chosen variant's available quantity, and retain basket data. Explicit refresh reloads availability and selected-product facts. Checkout remains authoritative; no new allocations or hidden inventory source introduced. Alternative box choices remain independently available.
- All 63 gateway tests and final optimized build pass. Live real confirmed product test reserves all 12, sees catalog availability 0, rejects competing checkout, then cancels unpaid attempt and reads availability12. No physical stock change/payment. Evidence: commerce/evidence/catalog-availability-unit.log, catalog-availability-build.log and catalog-availability-live.log. Actual box availability and full UI walkthrough still pending owner inputs/browser access.
- Runtime87822. Goal active. Backup predates new private candidate notes and latest canceled test; refresh before final handoff.

### Ordinary dictated price units without stock leakage — 2026-10-05
- Added natural `$2 each` / `$9 jar` unit recognition alongside per/slash forms, with unit word boundaries. Found and removed a quantity hazard: stock parsing now excludes dollar-price expressions so `$2 each` never becomes quantity2. Omitted stock stays unknown and asks for a count.
- All 64 gateway tests pass, including seven fixed units, spaced dollar signs, per/slash forms, missing stock and partial-unit words. Live worker-backed owner input verifies explicit12, missing count/question/approval422 and rejection cleanup. Evidence: commerce/evidence/dictated-unit-unit.log and dictated-unit-live.log. No catalog/stock mutation or inferred photo numbers.
- Current runtime45434; no frontend change. Full goal active; pending principal dependencies unchanged.

### Current sample journey and acceptance evidence — 2026-10-05
- Reran complete sample purchase/packing/refund after reservation-aware catalog and intake changes: server ignores tampered price, one native order/task, all assignment/shortage/state/actual-content checks pass, order snapshot retained and physical allocation restored12. Media privacy checks also pass. Evidence: commerce/evidence/current-sample-journey.log and current-media-boundary.log.
- Fresh clean offline backup and isolated restore pass all 33 selected tables plus uploaded media, all74 imported assets and private config, including new33 candidate-note reviews. Evidence: commerce/evidence/current-handoff-restore.log and restore-summary.json. Updated top acceptance matrix to current evidence and explicit remaining scope. Runtime72909 reports READY.
- No completion claim. Owner's requested vision-runtime decision and actual box ingredients/prices/costs remain unanswered; full browser QA blocked by tool policy; real Stripe remains deferred. Previous/current turns classify progress.

### Known overview photos cannot become products — 2026-10-05
- Found context-only UI notes did not prevent splitting/approval of known imported store overviews. Server now rejects product splits and approvals for those two overview evidence photos, independent of edited field flags. Private photo review metadata survives draft edits. UI hides split/approval controls for context notes.
- Live test submits otherwise valid owner-confirmed Hass sale values against each overview: context marker retained, approval422, split422 and published catalog unchanged. Private fields/questions restored with monotonically increased version. Real shelf candidate regression still passes. Final optimized build passes. Evidence: commerce/evidence/context-photo-live.log, context-shelf-regression.log and context-photo-build.log.
- This covers known imported overview evidence, not automatic classification of new camera photos; future vision remains pending. Runtime47061. Goal stays active.

### Early weight-package clarification and draft-form isolation — 2026-10-05
- Questions now hold per-lb/per-pound products before approval and ask for a confirmed fixed-price/prepacked selling package; prior validation rejected them only after clicking approve. Explicit per-bag product with owner-provided 1lb package still validates.
- Found uncontrolled unit/action/category/tax fields lacked per-draft remount while other fields had keys. Keyed the entire owner review form to draft ID/version, preventing previous selections from carrying into a new draft. Unit placeholder remains required; no default each substitution added.
- All 65 unit tests pass, including weighed hold and prepacked acceptance. Live weight-priced input gets question and approval422; private fixture rejected. Final optimized build passes. Evidence: commerce/evidence/fixed-package-unit.log, fixed-package-live.log and fixed-package-build.log. Actual interactive form-switching remains unverified under browser policy; source remount/compile evidence is narrower.
- Runtime handle in current launch result. Whole goal active; vision decision, box inputs and full browser QA remain pending.

### Dependency impasse audit 1 — 2026-10-05
- Prior turn classified progress (weight clarification/form isolation). Current turn classified no progress toward implementation: revalidated prerequisites only. Actual worker health confirms local-rules/automatic_identityfalse; no published real box offers; vision install decision and owner recipe/price/cost inputs unanswered. Browser restriction remains; no prohibited equivalent retry performed. Stripe intentionally deferred. Evidence: commerce/evidence/dependency-audit.json.
- Remaining original feature/verification work cannot be completed from existing approved facts and access. Do not invent offers, silently install an unanswered runtime, or count manual photo notes as automatic interpretation. First consecutive true impasse turn; goal remains active. Resume principal feature work when prerequisite changes. Current running optimized preview37958.

### Dependency impasse audit 2 — 2026-10-05
- Previous/current turns classified no progress: same missing principal inputs/access, no new authorization or owner facts. Live check confirms zero published boxes and local-rules worker with automatic_identityfalse. No equivalent browser workaround attempted. Second consecutive true impasse turn; goal remains active until audit threshold or prerequisite change.

### Dependency impasse audit 3 — 2026-10-05
- Third consecutive no-progress goal turn with the same genuine missing principal inputs/access. Live check again confirms zero published real box offers and local-rules/automatic_identityfalse. No user authorization/input change; browser policy still bars full walkthrough and equivalent workarounds. No safe independent implementation step identified that completes the remaining original requirements.
- Mark goal blocked, not complete. Resume when owner supplies vision installation decision, real box recipes/prices/component costs, or permitted browser QA access changes. Stripe remains deferred as instructed. Private optimized preview37958 and saved work preserved. No repeat tests or speculative offers added.

### Local vision and browser milestone — 2026-10-06
- User authorized proceeding with local vision installation and QA. Installed official Ollama 0.35.1 (SHA256 verified), project-local Qwen3-VL 2B Instruct (manifest digest verified), loopback-only, cloud disabled. Ollama created its normal local identity directory; no global app/service installed.
- All 33 real cached photos processed in 107,905 ms with zero request errors. Classification totals: 28 multiple-candidate, one single-candidate, one unknown, three context. This is coverage, not accuracy. Some labels/varieties are overly specific; owner review remains mandatory. No synthetic selling inventory was created.
- Each image in a six-photo batch is now interpreted separately; the aggregate is bounded to 48 names. The gateway continues to ground price, quantity and stock actions in explicit text. 68 tests pass, including authority rejection, mixed-photo ambiguity and immutable-evidence selection.
- Real uploaded-photo live tests retained unknown commerce values, rejected incomplete approval, kept private drafts and public catalog unchanged. Multi-photo selection is now required before approval, bound to retained evidence, persisted on reload, and outside-evidence indices rejected. Private test draft rejected. Evidence: local-vision-live.log, primary-photo-live.log.
- Responsive browser core-view walkthrough now works. Checked shop, detail, basket/pickup, simulator/cancel, empty search/reset, unavailable boxes, policies, owner intake/review and packing queue/history. Fixed false empty-shop loading, silent empty search, 14px file inputs and completed photo-list clutter. Desktop two-column composition preserved. Saved browser-qa-summary.json and screenshots. Full keyboard/200% text zoom, physical-camera HEIC and active packing-form interaction remain unverified.
- 28 rendered storefront text samples pass computed contrast checks. Final optimized build passes. Optional model failure still holds proposals for manual review; all commerce approvals remain deterministic.
- First backup comparison failed because the original database was stopped; original restarted and comparison passed. First supervised restart discovered an old orphaned Medusa child on port 9000; stopped that exact project process, restarted successfully and added a verified duplicate-port launch guard. First-attempt logs retained. Latest database/media backup matches 33 business tables and private/imported media on restore.
- Remaining owner gate: real box names, selling prices, exact component counts, costs and any swap. Stripe stays intentionally deferred. Do not claim full goal completion.

- Final optional-worker regression passed authenticated interpretation/path rejection, worker shutdown without stopping commerce, explicit-text fallback, a simulator paid order, all packing stages/shortage/assignment/replay checks, refund and restored allocation 12. Test fallback draft rejected; worker restored under supervised launcher. Evidence: local-vision-worker-regression.log.
- Final primary-photo selector verified in responsive browser at effective width 355: saved Photo 1 selected, numbered evidence captions, no horizontal overflow, keyboard Tab reaches the named product input with a visible focus ring. Screenshot: mobile-primary-photo-review.png.

### Full vision storefront mockup — 2026-10-06
- Added standalone local design at storefront-mockup, port 3101, separate from existing commerce preview and database. Uses selected actual supplied market photos and Michael portrait.
- Customer browsing, category filters, approved avocado sample basket, simulated fulfillment/checkout explanation, box concept details and non-submitting signup. Separate Hass owner presentation includes scripted delivery/margin, social and box proposals, approvals and local photo attachment.
- No Shopify/POS/AI/social integration, payments, inventory mutations or external messages. No unconfirmed prices/stock invented. Real box recipes remain pending.
- Browser QA at 1440 desktop and 390 phone: no JavaScript errors or horizontal overflow; basket/checkout, filters and owner approval interactions passed. Screenshots visually inspected. QA.json retained. Local server session 47716.

### Photo-derived mockup catalog — 2026-10-06
- Reused existing per-photo manual extraction and reviewed all three contact sheets; enlarged coffee and granola/honey photographs to resolve additional named variants.
- Populated 95 candidate catalog entries from 30 product source photographs. Preserved source photo references, unknown selling fields and owner-confirmed avocado sample separately in storefront-mockup/catalog.json and catalog-extraction.csv.
- Added product/producer search, producer and shelf filters, progressive browsing and product details. No production database or Shopify account was changed.
- Browser checks passed at 1440px and 390px: no script errors or horizontal overflow; search, four Ocean Ranch variants, product dialog and sample basket verified.
- Remaining: label-by-label confirmation of tentative candidates, package sizes, current prices and online allocations. Photos do not establish current stock or purchase costs.

### Three-section shopping mockup — in progress 2026-10-06
- User authorized invented prices for mockup, AI individual product displays, branded merchandise, sample small/medium/large boxes and pickup/delivery scheduling.
- Implemented shared multi-product basket, apparel sizes, editable quantities, time choices and delivery address. All operations remain local demonstrations, no payment/actual booking.
- 95 individual product image edits generating; 7 merchandise and 3 box concepts generated through built-in imagegen. Original shelf sources retained.
- Initial QA passed 375/390/768/1440px: no horizontal overflow or JS errors, mixed basket total $64 including $6 sample delivery, search and order review.
- Remaining: finish image generation, visual identity checks, compress web assets, final resource/interaction verification.

### Three-section shopping mockup — completed 2026-10-06
- Final storefront: 93 grocery candidate listings after duplicate removal, 7 branded merchandise concepts, 3 sample weekly boxes ($28/$46/$68).
- Individual AI product displays replaced shelf thumbnails. Packaging/product mismatches caught in visual review were regenerated (butter, chèvre, Sierra Nevada cheddar, strawberry basket, Spring Greens, pale melon, mango). Originals remain accessible in product details; generated imagery does not prove exact SKU/label facts.
- Built-in imagegen prompt/source logs saved in storefront-mockup/image-generation-log.json and image-final-corrections.json; all consumed assets persisted in workspace.
- 103 web images optimized to WebP, total 6,679,174 bytes versus 215,863,237 bytes of consumed source PNGs. No missing assets in file check.
- Final shopping QA: 375/390/768/1440px no overflow or JS errors; mixed basket, clothing sizes, search and delivery/time order-review checks passed. Mockup remains internal at port 3101, no real payment or bookings.
- Before live commerce: approve final products/variants, prices/units, merchandise production artwork, box recipes, stock, scheduling rules, tax and delivery service coverage; connect actual Shopify backend. These are intentionally outside this design mockup.

### Expanded produce, producers and continuous category browsing — 2026-10-06
- Added 9 photograph-derived candidates: passion fruit, figs, blackberries, garlic, shallots, yellow/red onions, radicchio and purple daikon. Now 102 grocery listings plus 7 merchandise and 3 weekly boxes.
- Corrected/added product label evidence for AG Berries raspberries, Stardust Grove pesto/guacamole, Mighty Cap Mushrooms and Ava’s Keitt mango carton. Christopher Ranch garlic carton and Hummingbird shallot bag attributions explicitly tentative. Coke Farm tomato cartons recorded as insufficient for conclusive grower attribution.
- Added Fruit, Vegetables, Dairy & Cheese, Eggs, Meat, Pantry, Drinks & Coffee, Bread and Flowers categories. Search and producer filtering combine with category selection.
- Replaced manual pagination with continuous scroll loading that appends cards, preserves cart and stops at the end of the matching catalog. Fixed an observer edge case discovered in testing.
- Scroll QA passed on mobile: all 102 listings reachable, no duplicate IDs or script errors; fruit/dairy filtering, empty search and cart preservation verified. All 112 product images served successfully. New AI edits and prompts saved in expanded-image-log.json.
- Local preview restarted on port 3101, session 98908. Exact unknown cultivars/growers remain unconfirmed; prices, imagery, scheduling and orders remain mockup content.

### Producer stories and comprehensive label expansion — in progress 2026-10-06
- User requested full photo inventory expansion, researched producer stories in an Anthony Bourdain-inspired food voice, no customer-facing AI/design/research labels, 8 merchandise products and catalog-backed vegetable boxes.
- Added 70 visible product varieties (now 170 displayed grocery entries after holding two raw-milk cheeses), 26 researched producer profiles with primary-source URLs, food descriptions, and eighth merchandise bottle.
- Rebuilt boxes with explicit product IDs and quantities from the catalog. Customer panels use food stories and maker origins; source/evidence stays in project data.
- Material finding: manufacturer home page currently displays Graziers raw-milk cheese recall. Photographed raw-milk cheeses held outside shop pending exact product/lot verification; recorded in held-products.json.
- Generating 74 new/replacement image assets, then visual QA and regression checks. Checkout remains unavailable; cart review never reports an order submitted.

## 2026-10-06 catalog and food-story completion
- Expanded customer catalog to 170 grocery listings; 26 sourced producer profiles; 8 merchandise designs; 3 vegetable boxes with catalog-linked recipes.
- Rewrote product stories in original, direct food-focused prose, emphasizing flavor and cooking. Kept organic/location claims grounded in producer evidence; did not assign unknown growers from reused cartons.
- Removed customer-facing research/AI/preview labels. Kept functional checkout/signup limitations truthful and preserved evidence and price assumptions in README/data files.
- Generated 74 new displays; corrected 8 visually inaccurate/unsupported displays. Optimized 181 active images to about 12 MB total.
- Passed mixed-cart, sizing, delivery calculation, search, responsive overflow at 375/390/768/1440, all-catalog scrolling (170, no duplicates), basket preservation, maker panel, vegetable recipe references, and 181 image resource checks.
- Excluded two photographed raw-milk cheese candidates pending manufacturer recall review. Source: https://sierranevadacheese.com/. Exact photographed labels/stock still need owner verification before live selling.
- Evidence: storefront-mockup/{shop-QA,scroll-QA,story-QA,asset-QA}.json; research and generation logs; held-products.json.

## Banner values update
Expanded the hero with Michael-inspired hospitality, wholesome food at fair prices, seasonal/organic sourcing, local growers, small producers, and community. Organic sourcing is expressed as a selection goal, not a claim about every product. Added a compact editorial values rule and responsive reading sizes. Shopping regression and 375/390/768/1440 overflow checks passed.

## Mobile independent review
Two user-requested agents reviewed visual layout at 375/390 and interactions at 320/390/430. Layout, filters, basket, and focus restoration passed. Fixed short touch targets (navigation/footer/basket/quantity/close), added dynamic accessible dialog titles, and made modal Close sticky during long-story scrolling. Shopping regression passed again at 375/390/768/1440; independent fix verification pending.
Independent recheck passed at 320/390/430: persistent Close, named dialogs, enlarged controls, no basket overflow, and working filters/delivery/focus restoration. Added minimum 44px nav link width for the narrow Merch label. Evidence: mobile-function-reverify.json and mobile-visual screenshots.

## Hosting request: slofishreport.com
User authorized publication of current storefront on Namecheap domain. Prepared deployment/slofishreport-upload.zip (15.6 MB) containing customer site scripts and 181 optimized product assets plus authentic logo/store/owner images. Omitted research logs, originals, test artifacts and internal product evidence fields. Added public title/description and disabled directory listing. Browser Namecheap session is signed out; user login requested. DNS/hosting changes not attempted yet. Payments/order processing remain unconnected.

## Namecheap signed-in hosting inspection
Verified slofishreport.com is owned/active in the account. No Hosting subscription exists. Current DNS: www CNAME parkingpage.namecheap.com, @ URL redirect http://www.slofishreport.com, SPF email-forwarding TXT. No DNS mutations made.
Prepared Stellar annual trial in cart. Correct cart pricing: $0 first month, then $26.88 first year, renews $55.88/year. Initial configuration showed GBP20.25/year but omitted renewal cost; corrected approval question sent. Cart also contains unrelated campaign email purchase; must exclude from any hosting transaction without deleting user's unrelated item casually. No purchase or agreement accepted. Upload ready deployment/slofishreport-upload.zip. Await user's paid-hosting approval or choice of free hosting. Evidence deployment/namecheap-hosting-cart.jpg. Browser tabs retained for checkout and DNS.

## Trial sunset authorization
User authorized a free 30-day trial and explicitly requested site offline in 14 days. Created ACTIVE thread heartbeats: reminder-before-avocado-shack-trial-removal (October19 19:10 local) and remove-avocado-shack-trial-site-october-20 (October20 19:10 local). Removal job preserves backup, verifies offline, cancels domain-specific trial if active subject to necessary account/confirmation gates, and reports blockers. Scheduler requires app availability/access; not a guaranteed server-side expiry. Hosting NOT activated. Cart still includes unrelated paid email item; must not purchase it under free-only authorization. Need user to remove unrelated cart item and complete required trial agreement/payment setup or explicitly authorize recoverable removal.

## Live deployment completed October 6
Namecheap Stellar trial activated for slofishreport.com: orderHOSTING_ORDER, $0charged, packageHOSTING_PACKAGE, auto-renewal OFF, expiresNovember5. User expressly confirmed hosting terms at checkout. Uploaded15MBzip (slow upload), extracted181 optimized assets and site files in /home/HOSTING_USER/public_html; moved zip to private home. Nameservers saved to Namecheap Web Hosting DNS. Independent public DNS resolvers return198.54.116.174. FreeSSLHOSTING_SSL_IDActive; HTTPS200 apex/www; added.htaccess HTTP301 toHTTPS and verified.
Public browser test: productsearch, addHass, basket$2, imagesrender, nooverflow. Site is a public mockup: no realpayments/order submission/signup.
Server cron saved and confirmed in cPanel: minute10everyhour, UTCepoch1792548600 (Oct20 19:10LA), checks.avoshack-preview marker, archivespublic_html to/home/HOSTING_USER/avoshack-archived-20261020 and recreates public folder with preview-endedpage. Originaldata preserved. Local simulation passed archive and idempotence. Server removal works without Codex session; appOct20task should VERIFY this then cancel onlyStellar trial if needed, preserve domain and otheremail/services, remove redundantcronaftercompletion. Cancellation task stillneedsaccountaccess if required; auto-renewOFFalreadyverified.
Evidence: deployment/live-storefront.jpg, expiry-QA.json, live-assets-QA.json. Localdistribution.htaccess should match publishedredirect nextpackage; do not reupload whole15MBunnecessarily.

## Mobile shopping hierarchy update
Removed numbered shop directory. Page order now hero → vegetableboxes → onlineshop → merch → Michaelstory → signup. Reordered headerlinks toboxes/shop/merch. Expanded boxbrandcopy with seasonal food, localfarms, smallgrowers and community without inventingall-localingredientorigins. Published only revisedindex.html via cPanel; confirmedlive sectionorder, no directory, nooverflow. Regression passed375/390/768/1440. Screenshot deployment/mobile-boxes-live.jpg. Trialexpirycron unchanged.

## Rich sharing preview
Published OpenGraph/Twitter large-image metadata with title "Avocado Shack · Good food, close to home." and value proposition: seasonal produce, small growers, community, vegetable boxes and market favorites. Created1200x630 branded share.jpg from authenticlogo/storephoto with cream/forestgreen/terracotta editorial design. HTTPSmetadata andimage200 verified; evidence deployment/share-QA.json. Uploaded/extracted shareupdatezip and movedzipprivate. Socialplatformcache may retain oldpreview temporarily.

## Ten refreshed logo directions
Created10distinctbuilt-inimagegenlogo concepts grounded in AvocadoShack’s coastal neighborhood market, growers, wholesome food, hospitality and community. Inspectedall10incomparisonboard: readablebrandnames, cohesivecolors, nofabricatedcertifications/foundingdates. SavedindividualPNGs, comparisonJPG, responsivegallery andpromptlog inbranding/logo-refresh. Website logo unchanged pendingselection. Recommended01continuity,03simpleicon,07marketapplications. These are rasterdesignconcepts; chosenmarkneedsvectorfinalizationforproduction.

## Local catalog-only revision — in progress
Objective: rebuild the local storefront as an in-person discovery catalog. Remove boxes, merch, prices, cart, checkout/pickup/delivery and assistant-demo UI. Keep food imagery, filters, progressive scrolling, product stories, producer bios and verified locations. Add compact producer context to each card. Preserve previous commerce UI under storefront-mockup/archive/commerce-preview. Do not modify deployed site, DNS, hosting, or October20 shutdown. Acceptance: all170 foodlistings remain accessible; no selling controls or prices; verified local/organic labels only; readable phone layouts and functional accessible details.

## Local catalog-only revision — completed
Rebuilt local index and scripts as food discovery catalog. Removed weeklyboxes, merch, allprices/units/cart/checkout/pickup/delivery controls, signup and ownerdemo. Replaced commercecopy/oldpublicdomain metadata with food/community messaging and in-person visit links. Newcatalog-products.js contains170food records withoutcommercefields; historicalsource/shopdata retainedunloaded. Fruit/vegetables lead. Everycardhas shortfoodstory; identifiedmakers add compactbusinessintro and verified “Based in”town/region. Addedsearchbytown, CentralCoastmaker and organicselectionfilters. Unknownoriginsleftunclaimed. Makerstoriesretainedindetails.
Verification: catalog-only-QA.json passed170records,noduplicates,nocommerceUI, townsearch, filters, accessiblemakerpanels, noerrors;320/375/390/768/1440 nohorizontaloverflow and consistentcream background. Inspectedphonecards anddetail/screenshots. Responsivefilters tightenedtohorizontalrows. Keptcurrentpublicsite/deployment/DNS/hostingandOctober20shutdownunchanged.

## Community and hiking additions — in progress
Add NorthCoastHikingClub calendar/history, RSVP and Michaelcommunitynewsletter to local sandbox only. No hike dates supplied; upcoming/past start empty, not fabricated. Proposed sender owner@example.com remains unconfigured. Implement local-only signup/RSVP persistence, explicit email-delivery status, consent choices, capacity-aware RSVP and mobile/accessibility checks. Real hike details requested asynchronously; no external accounts or services configured.

## Community and hiking additions — completed locally
Added NorthCoastHikingClub entry in mainnav/hero/footer, upcominghike details and capacity-aware RSVPform, completedhike history/recaps, hike-update signup, and Michael’s communitynewsletter with optionalhiking opt-in. No actualhikes supplied; regularcommunity.json events remainempty with honest emptystates. Proposed owner@example.com stored asunconfigured; noactiveemail link ormailboxclaims.
Replaced Pythonstaticserver with community-server.py on127.0.0.1:3101. LocalSQLite subscriptions/RSVPs storedoutsidewebroot inGitignoredcommunity-data; consentchoices recorded; transactionalcapacity andduplicateRSVPguards; publicAPI returnsno subscriberdata. No emails or externalservicecalls. Forms explain localsetup status andnocofirmationemails. Nochanges topublicdomain/hosting/shutdown.
Verification: isolatedfixtureconfig andtemporaryDB/port3102 tested persistedsubscriptions, consentmerge, invalidemail, cross-originrejection, duplicateRSVP, capacity andconcurrentcapacity, rejectionofpast-events, nopersonaldata inpublicAPI. UI tests exercised RSVP, newsletter/hikeforms, history andemptyregularcalendar; noerrors/overflow at320/375/390/768/1440. Inspectedphone/desktopsections. Foodcatalogregression remains170items, duplicatefree andcommercefree. Evidence community-api-QA.json, community-ui-QA.json, catalog-only-QA.json; docs README contains eventsetup fields andremainingemailconnectionwork.

## Owner-requested placeholder hike routes
Added3explicitlyundatedrouteIdeas separatefromevents: FiscaliniRanchBluffTrail(Cambria), MontanaDeOroBluffTrail(LosOsos), BobJonesPathway(AvilaBeach). Userconfirmednorealnext/pasthikesyet; nofictitiouspastcluboutings, datesormeetingpointsadded. Routecardslabeled “Route idea · date TBD”, noRSVPbuttons orbooking. Descriptions, terrain andverifiedsegmentdistances linkprimarysources: cambriacsd.org/trails; parks.ca.gov/?page_id=592; slocountyparks.com/trails-r1/. Clubhistoryremainsemptyuntilrealentries. Communityregressioncheckedthreecards/labels, RSVPflowonlyisolatedfixture, consent/persistence/capacity andmobileoverflow. Alllocalonly; signupdataretained; publicshutdownunchanged.


## Hermes handoff inventory — October 20, 2026
Completed read-only local/Agent Orange inventory and saved reports/hermes-handoff/Avocado_Shack_Hermes_Handoff_Report.html plus inventory-evidence.json. Authoritative working copy remains on Mac. Current catalog/community site differs from historical Medusa commerce prototype; Shopify is a future direction, not this implementation. Git main has no commits, zero tracked files and no remote; internal Codex refs exist. Agent Orange SSH succeeded; no Avocado Shack project found in bounded project locations. No transfer or GitHub setup performed. Local3101 stopped; public preview HTTP200 around9amPacific. Scheduled shutdown tonight19:10Pacific remains pending; hosting cancellation unverified. Existing QA evidence reviewed, not rerun. Community DB has zero subscriptions/RSVPs; older backup latestOct6 does not cover new community data. Proposed clean private repo and separate data migration sequence recorded for Hermes.

## Private repository and Hermes migration — in progress, October 20
User authorized private GitHub setup, Agent Orange project/data copy and Hermes preparation while preserving the Mac backup. Created Grahammmm/avocado-shack, verified PRIVATE. Prepared root ignore rules separating source/optimized images from private runtime, raw image caches and archived evidence. Candidate source scan: 556 files, about90MB, no matches to inspected private config credentials or credential-token/private-key patterns. Hermes instructions define current catalog/community scope, private loopback service, separate private data and historical Medusa limitations. Transfer, source commit and runtime verification still pending at this entry.


## Hermes migration — verified complete, October 20, 2026
Private GitHub repository Grahammmm/avocado-shack is populated on main. Agent Orange clone /home/user/repos/avocado-shack uses a repo-scoped SSH write deploy key with pinned GitHub host keys; read and dry-run push passed. No account-wide token copied. Private data is in /home/user/.local/share/avocado-shack, permissions700 directory/600 DB and key; Git-ignored community-data symlink points there.
User service avocado-shack-sandbox.service enabled/active, loopback127.0.0.1:3101; restart and SQLite backup verified. Mac viewing via private SSH localhost3101 forward; no public routing changes. Current catalog/community API check passed170imageURLs, DBintegrity, consentmerge, validation and concurrentRSVPcapacity using isolatedfixtures. Full catalog/community desktop/mobile QA reran via private tunnel:320/375/390/768/1440, nooverflow/errors,170items/no duplicates. Screenshots inspected. No tests inserted fixture people into the actual communityDB.
Local dated handoff-backups/2026-10-20 preserves original source/private data. Full gzip integrity passed. Remote deduplicated archive649778953bytes restored43828regular-filepaths (3090252080logicalbytes), everySHA256 matched manifest. Historical extracted snapshot is read-only; temporary incomplete first archive removed only after verified replacement. Reproducible dependencies/runtime/model downloads and disposable restore environments excluded and recorded. Historical Mac PostgreSQL files were not claimed to be a verified Linux commerce runtime.
HERMES_HANDOFF.txt, AGENTS.md, owner/product brief, service file, backup helper and verification scripts prepared. Current source and older prototype clearly distinguished. Final report Avocado_Shack_Hermes_Handoff_Ready.html and migration-verification.json record actual checks. Preserve Mac original and backups. No global Hermes settings changed, autonomous messaging task launched, outbound mail connected, or public site deployed. Existing Namecheap shutdown/cancellation automation remains separate and pending its scheduled window.

## Claude Code takeover — verified on Agent Orange, October 20, 2026
Claude Code took over maintenance from the Hermes handoff. Read AGENTS.md, README.txt, HERMES_HANDOFF.txt, storefront README, owner brief, migration-verification.json and recent ledger. Scope unchanged: catalog/community only; no prices, basket, checkout, boxes, merch or pickup/delivery.
Fresh checks this session (not historical): clean main at c7063c4 matching origin/main via deploy key fetch; service active, listening only on 127.0.0.1:3101; page/data files HTTP200; public API exposes no personal data and emailConnected=false; community DB integrity ok, 0 subscriptions/0 RSVPs (read-only open); private dir 700, DB/key/env 600; deduplicated archive SHA256 matches recorded 31794cdc…49ff3. Content: 170 products, 170 unique ids, no price/stock fields, all 170 WebP images present; 26 producers with producers.js identical to producers.json; both held Sierra Nevada raw-milk cheeses absent; community events empty; 3 undated routeIdeas.
Active QA scripts hardcoded the Mac runtime; added optional PLAYWRIGHT_MODULE/CHROMIUM_PATH/NODE/QA_OUT_DIR overrides (defaults unchanged). Reran catalog-only-qa.cjs and community-qa.py (+community-ui-qa.cjs) using an existing Playwright 1.62.1 package and installed Chromium headless shell 1243, output to a scratch folder so committed evidence was not overwritten. Both passed: 170 items/no duplicates, filters, maker dialogs, commerce absent, consent merge, validation, cross-origin rejection, duplicate/concurrent RSVP capacity, past-event rejection, no overflow/errors at 320/375/390/768/1440. Real community DB still 0/0 after tests. Mobile hero and route-idea screenshots inspected.
Not checked from Agent Orange: Mac original and dated Mac backup (on the Mac; preserved, untouched). Namecheap preview shutdown/cancellation remains separate and pending its 19:10 window. Nothing published, emailed or deployed.

## North Coast Hiking Club visual mockup — completed, October 27, 2026
User requested a polished club section with Point Buchon, Cass Hill and Fiscalini Ranch examples, trail statistics and a dummy RSVP. Working from Agent Orange main 0a58b23 in a separate Mac working copy; original Mac backup and active private database untouched. Feature uses a separate hiking-preview.json, so sample dates/history never enter the actual event calendar. Point Buchon is the featured invitation, with an original coastal schematic; the other trails demonstrate the archive. Dummy RSVP performs browser validation only, sends no request and clears fields. Existing confirmed-event RSVP and separate hiking/newsletter consent retained. Trail metrics checked against PG&E, Cambria CSD and Highway 1 Road Trip; times/meetup details are explicitly sample plans. Acceptance: phone/desktop layout, no demo POST/storage, real-event precedence, isolated consent/RSVP regression, catalog regression; pending visual inspection and sync to Agent Orange.

Hiking mockup checks passed locally: community integration used a temporary 3102 database; confirmed-event precedence, RSVP duplicate/capacity/race handling and separate signup consent passed. Sample form rejected missing name/invalid email; valid submission generated zero POST requests, no browser storage, cleared inputs and focused the result. No overflow or short RSVP controls at 320/375/390/430/768/1024/1440. Desktop and mobile artwork/layout screenshots inspected. Catalog regression passed 170 unique items, maker/location/organic filters and existing colors. An initial test selector expected a decorative arrow in the accessible name; corrected to the actual accessible label, then the suite passed.
Found and fixed an existing progressive-catalog navigation bug: section navigation triggered extra products and pushed the hiking target roughly 3,000 pixels below the screen. Suspend product loading while following a section link and while the visitor is beyond the catalog. Header and direct-hash navigation now land within 50 pixels of the viewport top at 390/1440, and all 170 products still progressively load when browsing the catalog. Evidence: reports/hiking-club/qa-20261027.json. Remote source was freshly clean at 0a58b23 and equal to origin/main before transfer; active service loopback and database fingerprint recorded. Private Agent Orange installation pending at this entry.

Hiking update installed on Agent Orange October 27 (Pacific): fast-forwarded clean main to 3105dae, preserving the prior 0a58b23 work. Service remains active on 127.0.0.1:3101. Seven served source/assets matched checkout bytes, real events remain empty, emailConnected=false, and the private database SHA256 is unchanged. Original Mac project and dated backup were not modified. GitHub privacy freshly verified true. Full UI/API/catalog checks ran in the separate Mac working copy with isolated fixture data, as recorded above. Public hosting and unrelated accounts were not changed.

Correction to premature verification wording: the final Agent Orange browser check timed out and has NOT passed. Local working-copy UI/API/catalog checks passed; remote served-file and unchanged-database checks passed. The forwarding-only SSH connection stalled; a session-backed one-hour connection returned the HTML with HTTP200 in about 0.18 seconds, but full browser loading still needs diagnosis. The temporary Mac test server was stopped. GitHub main contains the source update; no public access enabled.

Private preview follow-up verified after the transient connection timeouts: the Agent Orange page returned HTTP200 for its document, both stylesheets and all five scripts; browser document.readyState was complete, the dummy RSVP was present and every loaded image was complete. Direct resource checks returned HTTP200, including the 3 MB store image in about 1.14 seconds. The session-backed SSH preview is working; a one-hour connection was left open for review. The original local test server is stopped. The source update remains private, with the real event calendar and database unchanged.

## Hiking map upgrade and product showcase — in progress, October 27, 2026
User requested authentic landscape photos, better aerial/topographic mapping and a side-on elevation profile, while keeping the store a price-free product showcase. Starting from clean Agent Orange/GitHub main ac83d48; isolated branch codex/hiking-maps. Retrieved licensed Point Buchon photos, bounded OpenStreetMap geometry and public USGS imagery/elevation sources. Planned checks: geographic alignment and elevation provenance; layer/zoom/pan/profile controls, keyboard/mobile use; no demo RSVP storage and no commerce UI. Keep site private and preserve original Mac backup and community data.

Map upgrade implemented and locally checked October 27 (Pacific). Real CC BY 2.0 Point Buchon photo, 3200 × 1800 USGS aerial/topographic layers, OSM route, and USGS 3DEP-derived elevation profile replace the drawn map. Controls: layers, zoom/pan, fit, enlarged view, keyboard navigation and a linked elevation scrubber. Route is ~6.7 miles including parking approach; estimated cumulative ascent/descent ~600 ft, distinct from PG&E’s published 300-ft elevation-change figure. Source, license and reproducible calculations are documented in reports/hiking-club/TRAIL_MAP_SOURCES.txt. No runtime external map requests or new accounts.

Fresh checks passed: layer/zoom/drag/keyboard controls; linked route/profile positions and return endpoint; modal Escape/focus restoration; touch scroll at default zoom and map pan when zoomed; dummy RSVP no POST/local/session storage; 320/375/390/430/768/1024/1440/1920 widths with no overflow and 44px controls. One initial test asserted before the asynchronous dialog-close event; waiting for the event resolved the test timing failure. Catalog regression: 170 unique products, no commerce controls/copy, working source/town/organic filters. Section anchors retain position at 390/1440. No browser errors or external map requests. Desktop aerial and phone topo screenshots inspected. Safari/physical-phone checks were unavailable; do not represent emulation as device testing. Evidence: reports/hiking-club/map-upgrade-qa-20261027.json.

Removed the final price-oriented sentence from the store introduction. Current site remains a product showcase; catalog data, held products, real calendar and community database were not changed. Remote main freshly confirmed clean at ac83d48 with active loopback service and original database fingerprint. Private installation pending at this entry.

Private installation verified: Agent Orange main fast-forwarded to aece221 and pushed to the existing private GitHub repository. Eight served files/assets returned HTTP200 and matched the checked source byte-for-byte. Service remains bound only to 127.0.0.1:3101. Real events remain empty, email is disconnected, and the private community database hash is unchanged. A fresh phone-size browser visit through the SSH preview connection reached document-ready complete, loaded the map, switched to topo, and reported no overflow or browser errors. Original Mac project and dated backup remain untouched. Evidence: reports/hiking-club/map-private-installation-20261027.json. The temporary 3103 test server will be stopped; an eight-hour private SSH forward on 3101 is available for review. No public hosting or domain changes.

## Denser catalog and dedicated hiking page — in progress, October 28, 2026
User requested four-across desktop catalog, full product/maker information inline with no discovery/detail link, a confirmed-guest count, and a dedicated /hike page. Start from clean local/Agent Orange 7a874d9. Keep development private, catalog-only scope and original Mac backup. Acceptance: all 170 products and maker/source details remain available inline; responsive density without overflow; /hike and /hike/ plus legacy #hikes work; guest count sums RSVP party sizes, with no participant details exposed; sample RSVP remains inert and real tests use isolated fixtures; separate newsletter/hiking consent is preserved.

Implemented the denser catalog with four desktop columns, compact phone photo/text rows, complete food and producer stories inline, and preserved producer source links. Removed product image buttons and discovery/detail dialogs. Moved the whole hiking experience to /hike (both slash forms supported), retained the home newsletter and separate hiking signup, and redirected old #hikes bookmarks. Real-event confirmedGuests is derived from summed RSVP party_size; the sample stays at 0 and never records an RSVP.

Fresh checks passed: all 170 products with exact full descriptions, maker stories and source links; no product dialog, prices or commerce controls; all filters and duplicate-free progressive loading; 320–1920 widths with no overflow and expected 1/2/3/4-column layouts. Isolated API/UI fixtures verified group totals, no count increase for duplicate registrations, uncapped counts, database counts overriding any configured count, count refresh after RSVP, capacity races, no participant data in API responses, separate consent and dummy-form isolation. Both /hike paths, map layers, old #hikes links, and links back to the catalog/newsletter passed at phone/desktop sizes. The navigation test was corrected to wait for smooth scrolling and accept the natural bottom-of-page position when the newsletter is shorter than the viewport. Desktop/phone images inspected. Evidence: reports/hiking-club/catalog-hike-qa-20261028.json. Private installation pending.

Private installation complete: clean Agent Orange main fast-forwarded to 6d4f252 and pushed to the existing private GitHub repository. Restarted only the loopback preview service for the new /hike route and aggregate count field. Both hiking URL forms and six shared page/script assets returned HTTP200 and matched source. Fresh installed-browser check confirms four desktop columns, no product-detail links, no hiking section on the catalog page, working phone-size /hike map, 0 sample guests and no browser errors/overflow. Real events remain empty, email disconnected and database SHA256 unchanged. Original Mac project/backup untouched. Temporary test server stopped; private SSH preview on 3101 reopened. Verification: reports/hiking-club/catalog-hike-installed-20261028.json.


## Simpler catalog cards — October 28, 2026
User requested exact new catalog introduction, removal of origin/Central Coast/organic filters, visible product locations and organic labels, and less text per card. Start from clean local and Agent Orange 9f725f8. Keep category/producer/search controls and four-across desktop grid. Move full maker stories and source links into keyboard-accessible, collapsed native disclosures. Preserve documented product origins/organic rules, catalog-only scope, private service, real community data and original Mac backup. Check filtering/progressive loading, disclosure keyboard behavior, inline facts, desktop/mobile layout and installed private preview.

Implemented and checked locally: exact requested introduction; source filter controls/logic/styles removed; redundant Central Coast badges removed while documented locations and organic labels stay visible; full producer text/source links now in native closed disclosures. All 170 food records unchanged. Fresh catalog checks passed for search/category/producer behavior, progressive loading without duplicates, exact product/maker text, Enter/Space/click disclosure controls, privacy dialog and nine widths 320–1920 with no overflow or browser errors. Desktop and phone screenshots inspected. Evidence: reports/catalog-card-update-20261028.json. Emulation only, no physical handset/Safari check. Temporary test server uses its own /tmp database. Private installation pending.

Private installation complete at a660a15: Agent Orange main fast-forwarded and pushed to private GitHub. Served index.html, shop.js and style.css match checked source; loopback service active; real community DB fingerprint unchanged. Initial bundle named only HEAD; fetch corrected before any merge. Remote browser load waits were intermittent: a fresh diagnostic reached readyState=complete with 12 cards and all scripts HTTP200, while other navigation waits timed out. Expanded-card visual and accessibility checks passed in the isolated local preview; do not claim a full remote-browser visual pass. Source/backup/privacy scope unchanged. Temporary test server stopped after verification; SSH forward restored on 3101.

## Hass messaging plan and GitHub work queue — in progress, October 30, 2026

Objective: make the existing private GitHub repository the shared home for source, the Hass iMessage feature plan, and Hermes's next tasks. The user confirmed a spare Mac is available. Exact Mac/macOS and Apple account setup remain unknown. Current Agent Orange main and origin/main were freshly checked at 0d29ba0e5d108b3513e1a9b92ca37bc592371c3b, clean; the private service is active. GitHub metadata confirms private visibility and no existing issues were returned.

Acceptance: a clear current-versus-planned overview; prioritized features with dependencies and completion checks; a private iMessage/Agent Orange architecture and ownership/data boundaries; actionable GitHub work items; verified push and links for Hermes. No bridge installation, personal-message access, account creation, public deployment, commerce restoration, or participant-database changes in this planning task. Preserve the original Mac copy and dated backup. Work from isolated branch codex/hass-imessage-plan. Next: write the plan and handoff, create the work queue, check documentation and push through the existing repository-scoped Agent Orange access.

Plan prepared: new GitHub README and docs/hass/ contain the owner overview, 25 current-milestone features, 12 future integrations, dependencies, completion checks, technical contracts and Hermes start instructions. Refreshed stale catalog-filter/story descriptions in the storefront guide. BlueBubbles remains a proposed bridge pending actual Mac/account compatibility; public service and participant data unchanged. GitHub Issues was disabled (first creation returned 410); enabled only that repository setting, then created open work items #1–#4 for the text demo, photo/voice trial, reliable operation and future integrations. No assignee or notification to an external Hermes service was configured.

Fresh documentation checks: 25 relative links resolve; H01–H25 and F01–F12 are complete and unique; existing source still contains 170 unique products, 26 makers, zero real events and all product image files. Changed files are documentation only; git diff --check passed; no inspected credential patterns found in the changed documents. No browser regression or message integration test was run. Evidence: reports/hass-plan-verification-20261030.json. Next: commit and synchronize to private GitHub and Agent Orange.

## Hass plan delivered to private GitHub — October 30, 2026

Plan commit db66f5a8d0a22d54fe4a77ca7a59e9cbf41d7562 was fast-forwarded onto Agent Orange main and pushed to GitHub. Both revisions matched and the remote working tree was clean; the existing private service remained active without restart. GitHub API independently confirmed private=true, has_issues=true and has_pages=false, and listed all four docs/hass files on main. Issues #1–#4 are open with implementation checklists and acceptance criteria. Source/assets and plans are shared through GitHub; credentials, personal messages, participant data, raw archives and the preserved Mac backup remain outside it.

The planning/handoff task is complete. Hermes can begin issue #1 using docs/hass/HERMES_START.md. The assistant is not connected yet: chosen Mac identity/account setup and bridge validation remain before real iMessage use. No external Hermes runtime was notified or configured. This final evidence update records the verified plan delivery; it makes no website/runtime changes.

## H01 one validated content source — October 30, 2026

Branch codex/hass-a1 from origin/main 59d1880f (Hass plan unit A1, issue #1). Added `hass/content/` as the single editable source: products.json (170 active catalog records plus the 2 held cheese candidates as `held` with their recorded recall reason/source; no prices or units copied), makers.json (26 profiles), community.json (club details, 0 real events, 3 undated route ideas) and store.json (address and hours). `hass/sitegen.py` validates the source (closed field lists, no commerce fields, no markup or `$` in text, https links, known categories/makers, existing images, exact event times with America/Los_Angeles, undated route ideas, samples never promoted) and generates catalog-products.js, producers.js, producers.json, community.json, index.html and hike/index.html. The pages come from `hass/templates/` with escaped store-info slots. `held-products.json` and `hiking-preview.json` stay as they were and are not generated.

Fresh checks: `sitegen.py --check` reports all 6 generated files byte-identical to the committed site; `migration_check.py` against the frozen `migration-baseline.json` reports 170/170 listings preserved, 26/26 makers, 30/30 source links, both held ids excluded from the catalog and still matching held-products.json, 0 real events, 3 route ideas and output identical to the pre-migration files (6/6 SHA-256). `hass/tests` (17 tests, Python 3.12) cover byte identity, rejection of 29 invalid edits, hidden/held exclusion, store-edit regeneration with escaping and migration-check failures for deleted listings, restored held items, lost sources and hand-edited site files; every write goes to a temporary directory. CI runs these through the existing `hass/tests` step of the check workflow (PR #5). No site file changed, no service restart, no browser regression run (output is byte-identical), live community database not read.

Review round 1 fixes (sol-reviewer RETURN at c7dbe858): products.json and makers.json root envelopes are now closed (only `schemaVersion` plus the payload; a root `price` or `privateNote` is rejected), and event/route-idea ids or trail references that are JSON arrays or objects now fail as content-invalid instead of crashing. 2 new tests (10 cases) prove each rejection exits 2 from `sitegen.py --out` and `--write` with no output written. `hass/tests` now 19 tests, all passing; `sitegen.py --check` and `migration_check.py` unchanged. Exact-head CI still needs the PR #5 workflow on main.

## H02 private typed editing service — October 30, 2026

Branch rb/a2 from origin/main 345b2479 (Hass plan unit A2, issue #1). First commit closes the two H01 validator gaps left open at merge: ids and product images now use full matches (a trailing newline is rejected), `startsAt` must be a full `YYYY-MM-DDTHH:MM[:SS]` with `Z` or `±HH:MM` and parse with a time zone (so `2026-12-05-08:00` and `2026-12-05T08:00` are rejected), and malformed source JSON is reported as content-invalid. Added `hass/ops/` (closed argument kinds, op registry loaded from package modules, empty in production) and `hass/editor.py`: `prepare` turns typed ops into a draft bound to a SHA-256 content revision in a private 0700 state dir; `apply` is a single writer (non-blocking lock) that refuses the main checkout, branch `main`, detached HEAD, a dirty worktree or a missing Git identity, returns `stale` on a moved revision, writes only the four content files and six generated files, runs the generator and migration checks and makes one signed-off commit `hass content: <change_id>` without pushing. Journals make interrupted writes recoverable (`applied` if committed, otherwise files restored and `failed`); nothing is re-applied automatically. There is no network listener and `community-server.py` is unchanged.

Fresh checks: `hass/tests` 30 tests pass (Python 3.14 locally) in throwaway Git repos with a linked writer worktree and temp state dirs; `sitegen.py --check` and `migration_check.py` pass on the checkout. Test-only ops live in `hass/tests/fixture_ops.py`. Spec note: a store-hours edit regenerates only `storefront-mockup/index.html`, because `hike/index.html` shows the address but not the hours; the test asserts that. No real writer worktree or state dir was created on Agent Orange, the live service was not restarted and the community database was not read.

## H03 product and maker edit ops — October 30, 2026

Branch rb/a3 from origin/main 65fb40f (Hass plan unit A3, issue #1). Added `hass/ops/catalog.py`: `product.add|edit|hide|restore`, `maker.add|edit|hide|restore` and a read-only `lookup` that turns an ambiguous name into candidate ids. "Remove" means hide; held products are refused by every op with their recorded reason and source; nothing is ever deleted. Makers gain an optional `hidden: true` (`content_model.py`); `sitegen.py` leaves hidden makers out of `producers.js` and `producers.json`, byte-identical output with none hidden. `maker.hide` is refused while an active product names the maker. Newly organic-matching products get the draft warning `adds Organic badge to <id>`.

Fresh checks: `hass/tests` 39 tests pass in throwaway Git repos with a linked writer worktree (8 new, each through `prepare` + `apply`); `sitegen.py --check` and `migration_check.py` pass; no committed content changed (170 active products, 26 makers), no service restart, community database not read.

## H04 real-hike ops — October 30, 2026

Branch rb/a4 from origin/main 333bc02 (Hass plan unit A4, issue #1). Added `hass/ops/hikes.py`: `hike.create|update|cancel|complete` and a read-only `guest_counts(db_path)`. The start is computed from a local date and time in America/Los_Angeles with its offset; a repeated (DST end) or missing (DST start) local time asks for another time and a past start is refused. With RSVPs on, a capacity or an explicit no-limit choice is required, and a capacity below the confirmed guests counted read-only from the configured RSVP database is refused (an unset or unreadable database is refused too). Events come only from arguments: no route-idea or sample fact is copied, no event id can be supplied, nothing is sent and `emailConnected` stays false.

Fresh checks: `hass/tests` pass (8 new, each through `prepare` + `apply` on a throwaway writer worktree with an injected clock and a temp RSVP database holding placeholder rows); `sitegen.py --check` and `migration_check.py` pass; no committed content changed (events list still empty), live community database not read, no service restart.

## H05 approval state machine and fixture conversation — October 30, 2026

Branch rb/a5 from origin/main 65fb40fd (Hass plan unit A5, issue #1). Added `hass/conversation.py`: owner messages become H02 drafts through a replaceable interpreter (only the exact-text `FixtureInterpreter` exists; no model or network adapter), and a draft is applied only after `yes` from an owner sender in the owner chat, bound to change id, draft hash, base revision and expiry. Duplicates, echoes, edited messages, strangers and other chats are recorded by id and disposition only and get no reply; expired, ambiguous, replaced or stale approvals never write (stale → `rejected` and a new proposal). Results and replies are committed to a 0600 SQLite store in the private state dir before any send; `recover()` settles interrupted approvals from the H02 change record without applying again. Settings `ownerSenders`, `ownerChat`, `approvalTtlSeconds` have no defaults; real addresses stay outside Git. `hass/fixture_chat.py` runs a JSONL fixture and prints the outbox; it sends nothing anywhere. A fixture is not iMessage: no messaging integration exists.

Fresh checks after merging main 333bc02e (H03): `hass/tests` 51 tests pass (11 new) in throwaway Git repos with placeholder `example.invalid` addresses; `sitegen.py --check` and `migration_check.py` pass on the checkout. No state dir or writer worktree was created on Agent Orange, nothing was sent and no service was restarted.

Fresh checks after merging main 078badcf (H04): `hass/tests` 59 tests pass (51 + 8 H04); `sitegen.py --check` and `migration_check.py` pass on the checkout. The only conflicts were the H04/H05 sections of this ledger and `hass/README.md`; both sections are kept, no code changed in the merge.

Review fix (Sol RETURN at beb3b4a3): a cancelled or expired draft's code was free again, so repeating the same request (same A2 hash, same 4-hex code) let a late `yes <old code>` approve and commit the repeat. Draft codes are now never reissued (a repeat takes its code from a derived digest), and a repeat of a closed draft needs `yes <new code>`; a bare `yes` gets a reply naming the code. Two new tests (cancel → repeat, expiry → repeat) fail on beb3b4a3 and pass now; `hass/tests` 61 tests pass; `sitegen.py --check` and `migration_check.py` pass.

## H06 preview, history and undo — October 30, 2026

Branch rb/a6 from origin/main b82e327 (Hass plan unit A6, issue #1). Added `hass/preview.py` and `hass/screenshot.cjs`: a private phone-width screenshot of an isolated loopback copy of the site (fresh empty temp database, browser limited to GETs from the preview origin, server always stopped, PNGs 0600 in the state dir). With a previewer, proposals carry a screenshot and an applied change is reported only after it is checked (`verified`); a failed check is reported, never retried. Added `history.revert` (`hass/ops/history.py`): undo is a new, approved inverse change of only that change's records, refused on a conflict with a later edit; additions are hidden or cancelled, never deleted; the original gets `revertedBy` and its draft becomes `reverted`. `history` keyword and `editor.py history` CLI. CI's `Hass tests` step now exports `PLAYWRIGHT_MODULE` so the browser tests run.

Fresh checks: `hass/tests` 68 tests pass (7 new: 3 with real Chromium against loopback copies of throwaway repos, 4 with a fake previewer); `sitegen.py --check` and `migration_check.py` pass. No state dir or writer worktree created on Agent Orange, the live service and community database were not touched, nothing was sent.

H06 review fix: event undo now checks restored capacity against the read-only confirmed-seat count (refusing unavailable counts) and refuses restoring a scheduled start at or before the injected clock. Two regression tests cover over-capacity/missing/unreadable counts, equality at capacity, and cancel/complete/date-update undo at and after the original start. Both tests reproduced the missing guards before the fix. Fresh affected checks: `python3 -m unittest hass.tests.test_undo hass.tests.test_hike_ops hass.tests.test_conversation -v` ran 27 tests in 7.704s, all OK; `git diff --check` passed. Tests used isolated fixture repos and RSVP databases; no server or live data was used.

## H06 fixture chat preview flag — October 30, 2026

Branch rb/av-n3 from origin/main 8adcb41 (Hass unit AV-N3, PR #14: commit 6a52451, merged as 49c5d4b). `hass/fixture_chat.py --preview` builds `preview.Previewer` for the writer worktree recorded in the state dir and passes it to `Conversation`, so a fixture replay gets the same private proposal/result screenshots and check-before-reply as the owner path. Without the flag the call is unchanged. Nothing is sent; screenshots stay 0600 in the state dir. Added `hass/tests/test_fixture_chat.py` (3 tests, the CLI as a subprocess on a throwaway repo, worktree and 0700 state dir) and the fixture `conversation-preview.jsonl`; `hass/README.md` H06 gained one sentence.

Checks at PR head 6a52451 (recorded in PR #14, with `PLAYWRIGHT_MODULE`/`CHROMIUM_PATH` set as in `hass/README.md`): `python3 -m unittest discover -s hass/tests -t . -v` ran 73 tests, OK, browser test run; `python3 hass/sitegen.py --check` reported 6 generated files matching (170 active products, 26 makers); `python3 hass/migration_check.py` passed. CI `check` green with the browser test run, not skipped. No review fix.

Limits: without `PLAYWRIGHT_MODULE` the replay still exits 0, says `Preview unavailable` and leaves the draft `applied` with `not verified: …`. A fixture is not iMessage.

## H20 prep private state backup and restore drill — October 30, 2026

Branch rb/av-n4 from origin/main 49c5d4b (AV-N4, PR #15: commit 1adf1b5 and review fix ef645c2, merged as 146c95c). Added `hass/statebackup.py` with `create`, `verify` and `restore`. `create` takes the writer lock (`busy`), refuses a pending journal (`unsettled`) and any symlink or unknown entry (`refused`, each named), copies config, drafts, changes and screenshots, snapshots `conversation.sqlite3` with the SQLite online backup API, skips `writer.lock` and writes `MANIFEST.json` last into a new `<out>/hass-state-<UTC stamp>/`; `out` must be an existing 0700 dir of the user outside the state dir, the repository and the writer worktree. `verify` checks the manifest, every SHA-256, modes, unlisted files and symlinks and `PRAGMA integrity_check`, and names each damaged file (`corrupt`). `restore` verifies first, refuses an existing `--into` and the recorded writer worktree, builds the new state dir in a temp dir beside it and renames it into place; only `config.json` `worktree` is rewritten. Added `hass/tests/test_statebackup.py` (7 tests, including a drill of two changes and one undo restored onto a second drill worktree).

Checks at PR head ef645c2 (recorded in PR #15): `python3 -m unittest discover -s hass/tests -t . -v` ran 80 tests, OK (skipped=4, browser tests without a local Playwright); `python3 hass/sitegen.py --check` reported 6 files matching (170 active products, 26 makers); `python3 hass/migration_check.py` passed. CI `check` passed at ef645c2.

Review fix (RETURN at 1adf1b5): `create` now refuses a symlinked or non-regular `config.json`/`writer.lock` before the config is read or the lock opened, so a dangling `writer.lock` symlink no longer creates its target; `out` must be exactly mode 0700 (an owned 0500 dir exits 2). The new assertions failed on 1adf1b5.

Limits: H20 stays partial. This is prep only: the drill restores isolated copies into a new state dir bound to a separate drill worktree; restoring onto the recorded writer worktree is an attended operation and no live restore was run. No real Agent Orange state was backed up. Scheduling, retention, off-box copies, encryption and restore of content and approved media are not built.

## H17 status, pause and resume (part, with H14 guest totals) — October 30, 2026

Branch rb/av-n2 from origin/main 8adcb41 (AV-N2, PR #13: commit 0098e5c and review fix dc8dacb, main merged in at 2723ec8, merged as d13cb15). `hass/conversation.py` now takes whole-message `status`, `pause [changes]` and `resume [changes]` with the approval normalisation (lower case, trailing `.`/`!`); `pause the hike` still goes to the interpreter. `pause` stores one `control` row (table created by the first pause) that survives restarts. While paused, an approval that resolves one draft gets `Changes are paused; <code> was not applied. Send resume changes, then yes <code>.` and writes no approval or state move (expiry unchanged); proposals end with `PAUSED_LINE`, `no`/`cancel` still work and undo drafts are gated the same way. `resume` removes the row, lists waiting codes and never applies. `status` is read-only: pause state, waiting and needs-details drafts, the last approved change with its result and short commit (plus a failed or not-verified reason), and for each upcoming scheduled hike `<n> confirmed of <capacity|no limit>` from the read-only `guestCountsDb` seat totals (H14 part); an unset, missing or wrong-schema database gives `guest count unavailable`, never 0. Added `hass/tests/test_status_pause.py` (12 tests).

Checks at PR head dc8dacb (recorded in PR #13): `python3 -m unittest discover -s hass/tests -t .` ran 82 tests, OK (skipped=3, browser tests without a local Playwright); `python3 hass/sitegen.py --check` reported 6 files matching; `python3 hass/migration_check.py` passed. CI `check` passed at dc8dacb.

Review fix (RETURN at 0098e5c): `status` ran the persisting expiry sweep. It now only hides lapsed proposals; the next other message still expires them and a late `yes <code>` is refused as expired. The regression test failed on 0098e5c.

Limits: H17 and H14 stay partial. The documented support path for persistent outages is not written; `cancel` and `undo` are the H05/H06 commands. Guest totals are seat counts only, no names or emails.

## H13 store hours and address ops (part) — October 30, 2026

Branch rb/av-n1 from origin/main 8adcb41 (AV-N1, PR #12: commit e20d7ab, main merged in at 5ae9b65, merged as 398986b). Added `hass/ops/store.py` with `store.set_hours` (`hours`, a text list) and `store.set_address` (`streetAddress` and/or `town`), through the normal draft, approval and single-writer path. Refused: more than 7 hours lines, a line over 60 characters, repeated lines or unchanged hours; an address part over 80 characters or an unchanged address. No address argument asks for details; `name` and `schemaVersion` are not arguments (`invalid`). Added `hass/tests/test_store_ops.py` (8 tests).

Checks at PR head e20d7ab (recorded in PR #12): `python3 -m unittest discover -s hass/tests -t . -v` ran 78 tests, OK (skipped=3); `python3 hass/sitegen.py --check` reported 6 files matching (170 active products, 26 makers); `python3 hass/migration_check.py` passed. CI `check` succeeded at e20d7ab. No review fix.

Limits: H13 stays partial: home-page copy and image slots are not built. The store is one record, so undoing an older store change after a later one is refused (`conflict: store store changed after <id>`); undo the newest first. The `hours line <i>` refusal counts from 0.

## H08 prep: bridge adapter, fixtures only (BL-AV-3) — October 31, 2026

Branch rb/bl-av-3 from origin/main 398986b (BL-AV-3, Hass plan unit A8, PR #18: commit b48bb1c and review fix f29c3ec, merged as 544f4e7). Added `hass/bridge.py`: `normalize()` turns a documented BlueBubbles `new-message` or `updated-message` webhook event into an `Inbound` for `Conversation`, or a named `Drop` (`unsupported-event`, `group-or-unknown-chat`, `attachments-not-supported`, `malformed`). `seal`/`unseal` wrap it in an HMAC-SHA256 envelope that refuses a bad shape, version or MAC, a stale timestamp (over 300 s) and a replayed nonce. `BlueBubblesSender` posts Outbox replies only to a loopback base URL, reads a non-symlink owner-only password file at each send and raises `BridgeError` without the URL query or password. Added `hass/tests/test_bridge.py` and six synthetic fixtures under `hass/tests/fixtures/bridge/`; the existing `hass/README.md` section `H08 prep: bridge adapter (fixtures only)` documents it.

Checks at PR head f29c3ec (commands listed in PR #18; its body records no counts): `python3 -m unittest discover -s hass/tests -t . -v`, `python3 hass/sitegen.py --check`, `python3 hass/migration_check.py`, `git diff --stat origin/main...HEAD`. CI `check` passed at f29c3ec.

Review fix (f29c3ec): from-me echoes also need `handle.address`, so no sender is invented, and a lone surrogate in `guid`, `handle.address`, the chat guid or `text` is `malformed`; `unseal()` refuses one as `EnvelopeError("shape")` before the MAC is computed, so the nonce is not used up.

Limits: H08 stays open; this is fixture-only prep. Nothing listens, no BlueBubbles server or Mac is connected and nothing is sent; connecting one (A9) needs the owner and G. Attachments are dropped as not supported.

## Storefront QA scripts: explicit preview URL, private output (BL-AV-2) — October 31, 2026

Branch rb/bl-av-2 from origin/main 398986b (BL-AV-2, PR #17: commit e8238ea, test-budget fit 3fd517b and review fix d237c14, merged as 071c781). The four current QA scripts (`catalog-only-qa.cjs`, `section-navigation-qa.cjs`, `community-ui-qa.cjs`, `community-qa.py`) now exit 2 with one stderr line, before Playwright loads or a server starts, unless `PREVIEW_URL` is an explicit `http://` loopback address with a port and `QA_OUT_DIR` resolves outside the repository; an unset `QA_OUT_DIR` gets a fresh `avoshack-qa-*` temp folder. Added the shared guard `storefront-mockup/qa-env.cjs` and `hass/tests/test_qa_env.py` with its driver `hass/tests/fixtures/qa_env_driver.cjs` (subprocesses only, no browser or server). CI's "Catalog + community checks" step exports `PREVIEW_URL=http://127.0.0.1:3101`, and `storefront-mockup/README.md` documents both variables.

Checks at PR head d237c14: PR #17's body lists the covered refusal and acceptance cases but no commands or counts. CI `check` passed at d237c14.

Review fix (d237c14): `QA_OUT_DIR` resolves symlinks and `..` in filesystem order, and an explicit `:80` port is accepted.

Limits: the legacy QA scripts hard-coded to the Mac are unchanged and stay documented history.

## H16 durable inbound queue (BL-AV-4) — October 31, 2026

Branch rb/bl-av-4 from origin/main 398986b, stacked on BL-AV-3 (BL-AV-4, PR #19: commit 6924e83, BL-AV-3 merged in at 3569d10 with the replayed-envelope-after-reopen test, origin/main merged in at 5e2e34d, merged as b604406). Added `hass/inbox.py`: `Inbox(state_dir, start_at=None)` keeps `<state>/inbox.sqlite3` (0600). The first open must record a timezone-aware start point, which later opens cannot move. `enqueue` answers `queued`, `duplicate` or `history` (received before the start point: id and time only, never a command); an empty, zone-less or non-date `received_at` raises `ValueError` and stores nothing. `drain` hands pending messages to `Conversation.handle` in `(received_at, provider_id)` order and marks each done only afterwards, so a crash in between redelivers and is answered `duplicate`; an exception leaves that message and later ones pending. Payloads are erased when done, and `seen()` is the persistent nonce set for `bridge.unseal`. Added `hass/tests/test_inbox.py` and the `hass/README.md` section `H16 part: durable inbound queue`.

Checks at PR head 5e2e34d: PR #19's body points to a card comment for the output; its body records no commands or counts. CI `check` passed at 5e2e34d.

Limits: H16 stays partial: no worker, timer, CLI or live adapter feeds or drains the queue; fixtures only. Retention periods stay H21.

## H19 read-only health check, change-only notify (RF0708-4) — October 31, 2026

Branch rb/rf0708-4 from origin/main 071c781 (RF0708-4, PR #20: commit bc15751, merged as 56388d2). Added `hass/health.py`: one JSON line with `ok`, `problems` (`{check, detail}` only, no message text, sender or number), `info`, `fingerprint` and `notify`. Checks in order: `state` (an unsafe, symlinked or missing dir exits 2 and is never created), `settings`, `db-integrity` (`PRAGMA quick_check`), `outbox-stuck` (unsent rows older than `--outbox-minutes`, default 15), `apply-stuck` (approved drafts older than 10 min), `paused` (info only) and, with `--backups`, `backup-age` (default 26 h). The database is opened `mode=ro`, `writer.lock` is never taken and nothing is written into the state dir. `--seen FILE` (outside the repo and state dir, not a symlink) is written 0600 and `notify` is true only when the fingerprint changes; without it `notify` is `not ok`. Exit 0 ok, 1 problems, 2 unsafe or usage. Added `hass/tests/test_health.py`.

Checks at PR head bc15751: PR #20's body lists the covered edge paths; its body records no commands or counts. CI `check` passed at bc15751.

Limits: H19 stays partial: no timer or service runs the check and nothing is sent; `notify` is only a flag in the output line.

## H15 owner memory store (RF0708-5) — October 31, 2026

Branch rb/rf0708-5 from origin/main 071c781 (RF0708-5, PR #21: commit 2d8dccc, merged as cf884aa). Added `hass/memory.py`: a `memory` table in the private `conversation.sqlite3`, created on first use, so the H20 backup covers it. `Memory(state_dir, clock)` offers remember, correct, forget, get and list. A source must be `owner-approved:<id>`, `owner-stated:<id>` or `operator:<note>`; anything else is `ValueError('unverified source')`, and remembering a stored key says to use correct. `correct` supersedes in one `BEGIN IMMEDIATE` transaction; `forget` marks the active row forgotten and blanks the value of every row of that key (dates kept), with `secure_delete` on. Added `hass/tests/test_memory.py`.

Checks at PR head 2d8dccc (recorded in PR #21): `test_memory` ran 9 tests, OK; with `test_statebackup` and `test_conversation`, 29 OK; discover ran 127 tests, OK (4 skipped). CI `check` passed at 2d8dccc.

Limits: H15 stays partial: the store has no chat wiring. The owner commands are RF0835-4 (PR #26), not merged when this section was written.

## H09 fixture demo transcript (RF0708-6) — October 31, 2026

Branch rb/rf0708-6 from origin/main 071c781 (RF0708-6, PR #23: commit d47bfb8, current main merged in at 3fe6f57 and again at 83f2130, merged as c9ae3cf). Added the 8-row fixture `hass/tests/fixtures/conversation-demo.jsonl` (request, `yes`, `history`, `undo`, `yes`, a repeated `demo-1`, an `undo` from a stranger, a final `yes`), its interpreter fixture `conversation-demo-interpreter.json` (one `product.edit` description change) and `hass/tests/test_demo_transcript.py`. The test runs `fixture_chat.py` by subprocess on a throwaway `WriterRepo` and checks the reply sequence (proposal, applied, history, undo proposal, reverted, nothing waiting), that the repeated and stranger rows get no reply and no draft, that the undo restores the original description, that two fresh runs agree, and that a missing `--interpreter` file exits 2.

Checks at PR head 83f2130 (recorded in PR #23): `python3 -B -m unittest hass.tests.test_demo_transcript -v` ran 3 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 147 tests, OK (skipped=4); `python3 -m compileall -q storefront-mockup reports/hermes-handoff` passed. CI `check` passed at 83f2130.

Limits: H09 stays partial: fixture identities only, no bridge and nothing sent. `--preview` screenshots and time-based expiry or old-approval cases are not in the demo.

## H19 inbox-stuck and inbox-integrity (RF0905-6) — October 31, 2026

Branch rb/rf0905-6 from origin/main c9ae3cf (RF0905-6, PR #25: commit bb99582, merged as 0f340f0). `hass/health.py` also opens `<state>/inbox.sqlite3` (the H16 queue) with `mode=ro`. Pending rows whose `enqueued_at` is strictly older than `--inbox-minutes` (default 15, at least 1) give `inbox-stuck` with only the count as detail; unreadable or zone-less times count too. A failed `quick_check` or an unreadable file gives `inbox-integrity`, and the conversation checks still run. With no inbox file or no `inbound` table the output is unchanged; `done` and `history` rows are ignored. The check never creates the file, writes or takes the writer lock. Added `hass/tests/test_health_inbox.py`; `hass/tests/test_health.py` is unedited.

Checks at PR head bb99582 (recorded in PR #25): `python3 -m unittest hass.tests.test_health_inbox hass.tests.test_health hass.tests.test_inbox -v` ran 25 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 155 tests, OK (skipped=4). CI `check` passed at bb99582.

Limits: H19 stays partial: still no timer or service runs the check, and nothing is sent.

## H10 product imageAlt (RF0905-5) — October 31, 2026

Branch rb/rf0905-5 from origin/main c9ae3cf (RF0905-5, PR #28: commit 0753789e, merged as d24e758). `hass/content_model.py` allows the optional public product field `imageAlt` (plain text, at most 200 characters, checked on every status). `hass/sitegen.py` emits it when present; with no record using it the output is byte-identical. In `hass/ops/catalog.py`, `product.add` and `product.edit` take `imageAlt` and `product.edit` takes `clearImageAlt`; both together are refused, and clearing an absent alt with nothing else needs details. `storefront-mockup/shop.js` uses `imageAlt` for the photo alt and falls back to the product name. Added `hass/tests/test_product_alt.py` and the driver `hass/tests/fixtures/shop_photo_driver.cjs`.

Checks at PR head 0753789e (recorded in PR #28): `python3 -m unittest hass.tests.test_product_alt hass.tests.test_catalog_ops hass.tests.test_content -v` ran 37 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 156 tests, OK (skipped=4); `python3 hass/sitegen.py --check` reported 6 generated files matching (170 active products, 26 makers). CI `check` passed at 0753789e.

Limits: H10 stays partial: there is no photo pipeline or photo-to-product wiring yet; alt text is set only through product ops. `history.revert` restores a record with its keys in a different order.

## H20 statebackup restore --paused (RF0850-4) — October 31, 2026

Branch rb/rf0850-4 from origin/main c9ae3cf (RF0850-4, PR #27: commit 96dbc69, merged as 59b7210). `python3 hass/statebackup.py restore BACKUP --into DIR --worktree WT --paused` restores as before, then, inside the temp dir before the rename, records the H17 pause flag (`CONTROL` from `hass.conversation`, set by `statebackup-restore`) in the restored `conversation.sqlite3`. An already-paused backup keeps its original `set_at`; a backup without a store gets a new 0600 store holding only `control`. A failure there removes the temp dir as a copy failure does, so `--into` never appears. The result gains `"paused": true` and `"pausedSince"`; without the flag nothing changes. Added `hass/tests/test_statebackup_paused.py`.

Checks at PR head 96dbc69 (recorded in PR #27): `python3 -m unittest hass.tests.test_statebackup_paused hass.tests.test_statebackup hass.tests.test_status_pause -v` ran 24 tests, OK; `python3 -m unittest discover -s hass/tests -t . -v` ran 152 tests, OK (skipped=4); `python3 hass/sitegen.py --check` and `python3 hass/migration_check.py` passed. CI `check` passed at 96dbc69.

Limits: H20 stays partial: no live restore was run, and restoring onto the recorded writer worktree stays attended. Scheduling, retention, off-box copies and encryption are not built.

## H17 support path per health problem (RF0935-6) — October 31, 2026

Branch rb/rf0935-6 from origin/main 59b7210 (RF0935-6, PR #29: commit 44acfcd, merged as 307c90a). Added `docs/hass/SUPPORT.md`: one heading for every problem id `hass/health.py` emits (`state`, `settings`, `db-integrity`, `outbox-stuck`, `apply-stuck`, `backup-age`, `seen`, `inbox-stuck`, `inbox-integrity`) and for the info lines `conversation` and `paused`, each with Means / Check first / Next step / Stop and ask, plus a Restore section naming `restore --paused`. The `hass/README.md` H17 limits line points to it. Added `hass/tests/test_support_doc.py`: the ids found by `ast` in `health.py` must equal the documented headings (an undocumented id or a stale heading is reported by name), heading wording must be exact, every `python3 hass/...` path must exist, and the doc holds no `@`, 7+ digit run or http URL.

Checks at PR head 44acfcd (recorded in PR #29): `python3 -m unittest hass.tests.test_support_doc hass.tests.test_health -v` ran 16 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 177 tests, OK (skipped=4). CI `check` passed at 44acfcd.

Limits: H17 stays partial: the support path is a document only and no live support contact is set up. When merged, `statebackup.py create` refused a state dir holding `inbox.sqlite3` and the doc said so; RF1035-6 below adds the inbox to backups.

## H16 fixture_chat --queue (RF0935-7) — October 31, 2026

Branch rb/rf0935-7 from origin/main 59b7210 (RF0935-7, PR #30: commit bb3094c, merged as d40dc5f). `hass/fixture_chat.py` takes an optional `--queue START_AT`: it opens `Inbox(state, start_at)`, enqueues every fixture message before the first drain, drains once, closes in `finally`, then flushes as before. A `ValueError` (start point mismatch, bad `at`) exits 2 before draining. One counts-only stderr line reports `queued`, `duplicate`, `history` and `handled`. Without the flag the code path is unchanged. Added `hass/tests/test_fixture_chat_queue.py` (CLI subprocess tests on a throwaway `WriterRepo`); a symlink to a group-readable state dir exits 2 and creates no `inbox.sqlite3`.

Checks at PR head bb3094c (recorded in PR #30): `python3 -B -m unittest hass.tests.test_fixture_chat_queue hass.tests.test_inbox hass.tests.test_demo_transcript -v` ran 20 tests, OK; `python3 -B -m unittest discover -s hass/tests -t .` ran 177 tests, OK (skipped=4). CI `check` passed at bb3094c.

Limits: H16 stays partial: the queue is fed and drained only by the fixture CLI; there is no live transport, worker or timer.

## H20 state backup covers the inbound queue (RF1035-6) — October 31, 2026

Branch rb/rf1035-6 from origin/main 9320452e (RF1035-6, PR #33: commit 952d721, test-budget fit f3770cf, merged as bf8b183). `hass/statebackup.py` accepts `inbox.sqlite3` as a top-level regular file. `create` snapshots it before `conversation.sqlite3`, so a message handled between the two snapshots stays pending and is answered `duplicate` on a later drain. `verify` runs `PRAGMA integrity_check` on both stores; `restore` copies it like any file and `--paused` still touches only `conversation.sqlite3`. A leftover `inbox.sqlite3-journal` is still refused as `unknown entry`. The `hass/README.md` H20 bullet and `docs/hass/SUPPORT.md` say the inbox is included. Added `hass/tests/test_statebackup_inbox.py` (fixtures only).

Checks at PR head f3770cf (recorded in PR #33): `python3 -m unittest hass.tests.test_statebackup_inbox hass.tests.test_statebackup hass.tests.test_statebackup_paused hass.tests.test_inbox hass.tests.test_support_doc -v` ran 38 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 194 tests, OK (skipped=4). CI `check` passed at f3770cf.

Limits: H20 stays partial: no live restore was run; scheduling, retention, off-box copies and encryption are not built. The `inbox-integrity` section of `docs/hass/SUPPORT.md` still says backups do not hold the inbox (noted in PR #33 for a follow-up).

## H16 bridge nonces kept one day, then pruned (RF1035-7) — October 31, 2026

Branch rb/rf1035-7 from origin/main 9320452e (RF1035-7, PR #32: commits ec5a44b, 1d01e56, merged as 6b92a6e65e0bdbc74983ed6e985845ff6a3dea69). `hass/inbox.py` sets `NONCE_KEEP_S = 86400` (at least twice `bridge.MAX_SKEW`). `Nonces.add` deletes rows seen more than that long ago in the same transaction, before the insert. The comparison is strict, and a future-dated row (clock moved back) is never pruned early. Lookups never prune, and the schema is unchanged. A replay of a pruned nonce is still refused by `unseal` as `stale`. One `hass/README.md` H16 line. Added `hass/tests/test_inbox_nonces.py`.

Checks at PR head 1d01e56 (recorded in PR #32): `python3 -m unittest hass.tests.test_inbox_nonces hass.tests.test_inbox hass.tests.test_bridge hass.tests.test_fixture_chat_queue -v` ran 37 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 193 tests, OK (skipped=4). CI `check` passed at 1d01e56.

Limits: only nonces are pruned. Message retention periods (H21, owner decision), `inbound` table pruning and any live bridge are not built.

## H21 routine outputs carry no sender or message text (RF1058-11) — October 31, 2026

Branch rb/rf1058-11 from origin/main 6b92a6e (RF1058-11, PR #34: commit 877bb38, merged as 326b1e1eb7dc4e97ee8ee7d042ef335136acc56d). Test only, no code change. Added `hass/tests/test_output_hygiene.py`: one fixture state holds made-up sender, chat and message canaries. `fixture_chat.py` (plain and `--queue`), `health.py`, `statebackup.py create`/`verify` and `editor.py history` run on it. No canary may appear in stdout, stderr or `MANIFEST.json`, except that the chat id may appear in `fixture_chat` replies. It also covers an unknown sender, a missing `--fixture`, a stuck outbox (detail `"1"` only) and an unchanged `git status`.

Checks at PR head 877bb38 (recorded in PR #34): `python3 -m unittest hass.tests.test_output_hygiene -v` ran 4 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 206 tests, OK (skipped=4). CI `check` passed at 877bb38.

Limits: this checks the listed CLIs on fixtures only. Retention and deletion (owner decision), screenshots, logging and the Mac transport are not covered.

## H01 sitegen and migration_check name io errors, exit 2 (RF1105-29) — October 31, 2026

Branch rb/rf1105-29 from origin/main ba546cb (RF1105-29, PR #37: commit efaca77, merged as b755ac253f39758c875c98fc29ebab32c6f0185f). `hass/sitegen.py` and `hass/migration_check.py` turn an `OSError`/`ValueError` into one stderr line `sitegen: io error: <ExcName>` or `migration_check: io error: <ExcName>` and exit 2. Only the class name is printed, never a path or file bytes. `ContentError` keeps its `content invalid:` output, and `--check` still exits 1 on a real difference. `--write`/`--out` refuse a symlinked generated file before writing. Added `hass/tests/test_generated_io.py`.

Checks at PR head efaca77 (recorded in PR #37): `python3 -m unittest hass.tests.test_generated_io hass.tests.test_content hass.tests.test_editor -v` ran 41 tests, OK; `python3 hass/sitegen.py --check` and `python3 hass/migration_check.py` passed. CI `check` passed at efaca77.

Limits: content rules, templates, generated bytes, storefront QA scripts and any storefront deploy are unchanged.

## H02/H06 editor CLI io errors as one JSON line; history skips a corrupt record (RF1105-28) — October 31, 2026

Branch rb/rf1105-28 from origin/main ba546cb (RF1105-28, PR #36: commit b65aebd, merged as 4c800140881a95e2ea977217843a98db928b3fe5). `hass/editor.py` `main()` turns an `OSError`/`ValueError` into `{"result": "io-error", "problems": ["<ExcName>"]}` and exits 2 (class name only). `history` lists a change record that cannot be read as `state` `unreadable` with `ops: []` and keeps the other records unchanged. Library functions still raise for in-process callers. Added `hass/tests/test_editor_cli_io.py`.

Checks at PR head b65aebd (recorded in PR #36): `python3 -m unittest hass.tests.test_editor_cli_io hass.tests.test_editor hass.tests.test_undo hass.tests.test_conversation -v` ran 41 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 216 tests, OK (skipped=4). CI `check` passed at b65aebd.

Limits: op validation, apply/undo semantics, `recover` and `conversation.py` are unchanged; no live bridge.

## H09/H16 fixture_chat names a bad fixture line before anything runs (RF1105-30) — October 31, 2026

Branch rb/rf1105-30 from origin/main fc494c3 (RF1105-30, PR #54: commit 4b73b9d, merged as cda613b74931774674a3ed9b0008c7fbf6824919). `hass/fixture_chat.py` checks every fixture line before any message is handled or queued. A bad line exits 2 with `fixture_chat: fixture line <n>: <field> <rule>`, naming the field and never its value. Nothing is handled, queued or sent. Valid fixtures run as before. Added `hass/tests/test_fixture_chat_rows.py`. One test in `hass/tests/test_fixture_chat_queue.py` was updated under the operator scope approval of 2026-10-31 14:25.

Checks: CI `check` passed at PR head 4b73b9d (PR #54). Re-run on main f055044 for this ledger: `python3 -B -m unittest hass.tests.test_fixture_chat_rows hass.tests.test_fixture_chat hass.tests.test_fixture_chat_queue hass.tests.test_demo_transcript` ran 22 tests, OK (skipped=1).

Limits: `bridge.py` payload parsing, `Inbox`, `Conversation` rules, attachments and any live bridge are unchanged.

## H20 statebackup list, read-only (RF1120-7) — October 31, 2026

Branch rb/rf1120-7 from origin/main fc494c3 (RF1120-7, PR #53: commits e5bccc0, 2a12cd6, 84bf930, merged as f055044cf8d37e5fe082a5fc3646a966caca8c36). `python3 hass/statebackup.py list --out DIR` prints one JSON line per `hass-state-<UTC stamp>` entry, newest first (`backup`, `createdAt`, `files`, `complete`, `problem`), and exits 0. It writes nothing and hashes nothing; that stays `verify`. An `--out` that is a link, missing or not a folder is refused (exit 2). A symlinked entry is never followed. A missing or invalid manifest is named as the entry's `problem`. Other names are ignored. The `hass/README.md` H20 block and `docs/hass/SUPPORT.md` point to `list` before `verify`/`restore`. Added `hass/tests/test_statebackup_list.py`.

Checks at PR head 84bf930 (recorded in PR #53): `python3 -m unittest discover -s hass/tests -p 'test_statebackup*.py' -v` ran 35 tests, OK. CI `check` passed at 84bf930.

Limits: H20 stays partial: deleting or pruning backups, `verify`/`restore` changes, `health.py` and timers are not built.

## H04 turning RSVPs on asks for a capacity or no limit (RF1130-5) — October 31, 2026

Branch rb/rf1130-5 from origin/main 4c80014 (RF1130-5, PR #39: commit 9fef871, merged as 49e9d901ed58de803ac344fe48ca5e03a1c2fa3d). `hike.update` that leaves `rsvpEnabled` true on an event with no `capacity`, without `capacity` or `noCapacityLimit: true` in the request, returns `needs-details` (`capacity`, `noCapacityLimit`) with the same question as `hike.create`. Nothing is drafted. One `hass/README.md` H04 line. Added `hass/tests/test_hike_rsvp_on.py`.

Checks at PR head 9fef871 (recorded in PR #39): `python3 -m unittest hass.tests.test_hike_rsvp_on hass.tests.test_hike_ops hass.tests.test_status_pause -v` ran 29 tests, OK. CI `check` passed at 9fef871.

Limits: existing RSVPs, guest notification, the RSVP database, `hike.create` and content-model validation are unchanged.

## H08 picture replies send their text with a fixed note (RF1140-7) — October 31, 2026

Branch rb/rf1140-7 from origin/main 4c80014 (RF1140-7, PR #40: commit 20a38761, merged as 2b86dd5c277e4019fb43c77f8755de5d93d6d89b). `BlueBubblesSender.send` with attachments no longer raises `attachments-not-supported`; it sends the text plus one fixed `PICTURE_NOTE` line, so the outbox moves on. The picture is never opened, sent or named in the request and stays in the state dir. A text-only send is byte-identical. One `hass/README.md` bridge line; the attachments test in `hass/tests/test_bridge.py` now expects text plus note. Added `hass/tests/test_bridge_pictures.py`.

Checks at PR head 20a38761 (recorded in PR #40): `python3 -m unittest hass.tests.test_bridge_pictures hass.tests.test_bridge hass.tests.test_conversation -v` ran 30 tests, OK. CI `check` passed at 20a38761.

Limits: sending pictures (needs A9/H07 measurements), inbound attachments, `Outbox` retry or skip rules and any live bridge or Mac are not built.

## H04 cancel or RSVPs off warns about confirmed guests (RF1130-6) — October 31, 2026

Branch rb/rf1130-6 from origin/main a987a09 (RF1130-6, PR #43: commit 58e0018, merged as dd296b879369ea05f8a294aa649bce5a853656ed). `hike.cancel` on an RSVP event, and `hike.update` turning RSVPs off, still draft normally and add the warning `<id> has N confirmed guests; nobody is notified automatically`, or `<id> guest count unavailable; check RSVPs before approving`. It is never a refusal. Confirmed guests are warned about in the draft, never messaged: no outbound message exists. RSVPs are not changed. One `hass/README.md` H04 line. Added `hass/tests/test_hike_guest_warning.py`.

Checks at PR head 58e0018 (recorded in PR #43): `python3 -m unittest hass.tests.test_hike_guest_warning hass.tests.test_hike_rsvp_on hass.tests.test_hike_ops -v` ran 24 tests, OK. CI `check` passed at 58e0018.

Limits: notifying guests (outbound, needs G), changing or deleting RSVPs, refusing a cancel and status lines are not built.

## H19 health prints its JSON line when --seen cannot be written (RF1105-11) — October 31, 2026

Branch rb/rf1105-11 from origin/main 5072a83 (RF1105-11, PR #47: commit 99590a0, merged as 4bda5fac7f24eaf8da851e23e024a74fc4f1dbc9). `hass/health.py` `main()` catches an `OSError` from recording the `--seen` file (full disk, read-only or changed-permission folder). The JSON line is still printed with `notify` true and the value-free info entry `seen file not updated` (no path). `ok`, `problems`, `fingerprint` and the exit code stay those of the real checks. One `docs/hass/SUPPORT.md` bullet. Added `hass/tests/test_health_seen.py`.

Checks at PR head 99590a0 (recorded in PR #47): `python3 -m unittest hass.tests.test_health_seen hass.tests.test_health hass.tests.test_health_inbox hass.tests.test_support_doc -v` ran 33 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 307 tests, OK (skipped=4). CI `check` passed at 99590a0.

Limits: new checks, alert delivery, timers (attended operator work), `statebackup.py` and the backup-verify check are not built.

## H17 status says RSVPs off for a hike without RSVPs (RF1130-7) — October 31, 2026

Branch rb/rf1130-7 from origin/main 85223ca (RF1130-7, PR #51: commit d87cb89, merged as 2c1aaf4537c91d7c490f73ce10ae2c1184cb2c1d). In `status`, an upcoming scheduled hike with `rsvpEnabled` false reads `Hike <title> <local start>: RSVPs off` instead of `0 confirmed of no limit`. The RSVP database is opened only when a listed hike has RSVPs on. Hikes with RSVPs on are unchanged. One `hass/README.md` H17 line. Added `hass/tests/test_status_rsvp_off.py`.

Checks at PR head d87cb89 (recorded in PR #51): `python3 -m unittest hass.tests.test_status_rsvp_off hass.tests.test_status_pause -v` ran 18 tests, OK. CI `check` passed at d87cb89.

Limits: other status lines, pause/resume, memory commands and hike ops are unchanged.

## H20 statebackup create builds aside and renames in (RF1105-13) — October 31, 2026

Branch rb/rf1105-13 from origin/main f2576fee25 (RF1105-13, PR #58: commits 56011b6, 3fef4d2, d39d71f, merged as 4baeaaa8f110ff80e22dc4340a6f6925c36cdb8f). `hass/statebackup.py create` builds the backup in a dot-named `.hass-state-<stamp>.partial-<pid>` folder and renames it to `hass-state-<stamp>` after `MANIFEST.json` is written. A failed run leaves no `hass-state-*` folder, so the stamp stays free; a good backup is byte-identical to before. Added `hass/tests/test_statebackup_atomic.py`.

Checks at PR head d39d71f (recorded in PR #58): a targeted statebackup/health set ran 70 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 397 tests, OK (skipped=5). CI `check` passed at d39d71f. Re-run on main 4baeaaa for this ledger: `python3 -B -m unittest hass.tests.test_health_seen hass.tests.test_statebackup_atomic hass.tests.test_hike_rsvp_on hass.tests.test_hike_guest_warning hass.tests.test_status_rsvp_off hass.tests.test_bridge_pictures` ran 46 tests, OK.

Limits: `verify`/`restore`, the manifest schema, cleaning up partial folders left by a killed process, retention/pruning and timers are not built.

## H10 product.set_photo installs a stored photo's web copy (NB-AV-08) — October 31, 2026

Branch rb/nb-av-08 from origin/main 7ae191d (NB-AV-08, PR #72: commit f125a52, merged as c179e3270f826d6106e7aa479df9eb9088965f0c). New op `product.set_photo {id, photo, imageAlt}` in `hass/ops/photos.py`: the product must exist and `photo` must be 64 lowercase hex naming a stored original. It calls `media.web_copy` under the `mediaRoot` setting (a media root inside the repo is refused) and sets `image` to `assets/products/photo-<sha[:16]>.<jpg|png>` plus `imageAlt`. `hass/editor.py` refuses an asset path outside `IMAGE_RE` or the writer worktree and writes the asset with the content change; a failed or recovered apply restores or removes the photo file. `OpContext.assets`; one `docs/hass/IMPLEMENTATION.md` line. Added `hass/tests/test_set_photo.py`.

Checks at PR head f125a52 (recorded in PR #72): `python3 -m unittest hass.tests.test_set_photo hass.tests.test_catalog_ops hass.tests.test_editor hass.tests.test_undo hass.tests.test_media_web` ran 46 tests, OK. CI `check` passed at f125a52.

Limits: undo (`history.revert`) restores `image`/`imageAlt` but leaves the committed photo file in place, unreferenced.

## H05 interpreter output checked against the ops registry (NB-AV-01) — October 31, 2026

Branch rb/nb-av-01 from origin/main 7ae191d (NB-AV-01, PR #70: commit e77dfcb, merged as db937b35d55c8f3793e98c88899a4de65d33ebfd). New pure `hass/interpret_check.py` runs between `_checked` and `editor.prepare` in `Conversation._request`. The first problem wins: empty `ops`, a call that is not exactly `{"op", "args"}`, an unknown op, an unknown argument, a wrong Python type for the argument kind, or `revises` naming no waiting draft. Each gets a fixed reply; names are cut to 40 characters with control characters removed. The registry is cached on the conversation. Added `hass/tests/test_interpret_check.py`.

Checks at PR head e77dfcb (recorded in PR #70): `python3 -m unittest hass.tests.test_interpret_check hass.tests.test_conversation hass.tests.test_demo_transcript hass.tests.test_fixture_chat -v` ran 29 tests, OK (skipped=1); `python3 -m unittest discover -s hass/tests -t .` ran 477 tests, OK (skipped=5). CI `check` passed at e77dfcb.

Limits: value checks (maker exists, real date, image file, choices) stay in the editor with `Not drafted:`.

## H15 owner alias memory resolves lookup (NB-AV-14) — October 31, 2026

Branch rb/nb-av-14 from origin/main db937b3 (NB-AV-14, PR #78: commit 330d45d, merged as 3f3547d2c6ae5318927f6ae646bab1bbf3fb7ae1). `alias <name>: <product id or maker key>` saves memory key `alias.<slug>` (kind `fact`, value `product:<id>` or `maker:<key>`) only when the id exists in the writer-worktree catalog. A bad name, an unknown id, an id that is both product and maker, or an unavailable catalog is a named refusal that stores nothing, and `remember alias.<x>: …` is refused. `catalog.lookup(..., aliases=None)` returns `{"match", "via": "alias <name>"}` for a folded whole-name match whose record still exists; dangling or other-kind aliases fall back to names. `forget alias.<slug>` uses the existing forget path. One `docs/hass/COMMANDS.md` row. Added `hass/tests/test_memory_alias.py`.

Checks at PR head 330d45d (recorded in PR #78): `python3 -B -m unittest hass.tests.test_memory_alias hass.tests.test_memory hass.tests.test_memory_chat hass.tests.test_catalog_ops hass.tests.test_commands_doc` ran 44 tests, OK; `python3 -B -m unittest hass.tests.test_conversation hass.tests.test_status_pause` ran 25 tests, OK. CI `check` passed at 330d45d.

Limits: the interpreter still never reads memory.

## H05 local-model interpreter adapter, loopback only (NB-AV-02) — October 31, 2026

Branch rb/nb-av-02 from origin/main db937b3 (NB-AV-02, PR #77: commit d51710c, merged as 4eba2f6924dcbd41d26cae5359bda7bd9b1ddecb). New `hass/interpreter_local.py`: `LocalInterpreter(base_url, model, system_prompt, timeout=30, transport=None).interpret(text, pending)` makes one Ollama `POST /api/chat` (`stream` false, `format` json, temperature 0) to `http` on `127.0.0.1`, `localhost` or `::1` only. The default transport ignores environment proxies, follows no redirect and reads at most 256 KiB + 1. Any failure returns a fixed `unsupported` reply and keeps only a code in `last_error` (`timeout|connect|http-<n>|too-large|not-json|shape`); the URL, prompt and owner text are never kept. A short `docs/hass/IMPLEMENTATION.md` section. Added `hass/tests/test_interpreter_local.py` (fake transport only).

Checks at PR head d51710c (recorded in PR #77): `python3 -m unittest hass.tests.test_interpreter_local hass.tests.test_interpret_check hass.tests.test_conversation -v` ran 32 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 526 tests, OK (skipped=5). CI `check` passed at d51710c.

Limits: nothing is wired into a service and `Conversation` is unchanged; tests open no socket and call no model.

## H21 read-only retention report (NB-AV-15) — October 31, 2026

Branch rb/nb-av-15 from origin/main 92e4c2d (NB-AV-15, PR #74: commits 4e68653, e491cee, ac6b395, merged as 833b0fbf7ae3e7761c1031c81ee372897ff3014a). `python3 hass/retention.py report --state DIR --days N [--media ROOT] [--backups DIR] [--now ISO]` prints one JSON line of counts strictly older than now minus N days for inbox, messages, outbox, drafts, screenshots, media and backups, with `deletes: 0`. Photos with no usable date are `undated`, never guessed. SQLite is opened `mode=ro`; a missing or corrupt DB reports `"unavailable"` (exit 1). A missing or symlinked folder or DB, or a bad `--days`/`--now`, exits 2 with nothing opened or created. No ids, text or file names are printed. Commit e491cee ignores stamp-shaped backup names that are no real calendar time. `hass/README.md` gains a `## Retention report (H21)` section. Added `hass/tests/test_retention.py`.

Checks recorded in PR #74 (head not named in the PR): `python3 -B -m unittest hass.tests.test_retention -v` ran 9 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 496 tests, OK (skipped=5). CI `check` passed at PR head ac6b395.

Limits: a report only; it deletes nothing. `docs/hass/SUPPORT.md` is not touched.

## H03/H05 unstated organic, origin or maker claims become a question (NB-AV-05) — October 31, 2026

Branch rb/nb-av-05 from origin/main f311e31 (NB-AV-05, PR #76: commits de339da, 45d5912, merged as 8363e3ae0f082d7b29cea994b3c92b1bc2520f31). After `editor.prepare` returns `ok`, `_request` runs `claims.unstated(draft, msg.text, makers)`. A `claims.TERMS` term (organic, certified, origin, local, family farm and similar) that the draft adds and the owner's message does not contain, or a changed `producerKey` whose maker the owner did not name, gets one question with disposition `claim-question` and no `drafts` row; a waiting draft named by `revises` keeps its state. Matching is whole words on folded text. Unreadable `makers.json` fails closed. New `hass/claims.py`. Added `hass/tests/test_claims.py`.

Checks at commit de339da (recorded in PR #76): `python3 -m unittest hass.tests.test_claims hass.tests.test_interpret_check hass.tests.test_conversation hass.tests.test_demo_transcript -v` ran 38 tests, OK. CI `check` passed at PR head 45d5912.

Limits: the term list is fixed; only a draft made entirely of `history.revert` ops skips the check.

## H05 interpreter prompt from the ops registry and catalog (NB-AV-03) — October 31, 2026

Branch rb/nb-av-03 from origin/main a82ab14 (NB-AV-03, PR #81: commit 75a413b, merged as 212262c7627ab2a34e6ff9c00b514d92f001dd8b). New pure `hass/interpreter_prompt.py`: `build(registry, content)` returns a deterministic system prompt: role, reply contract, fixed rules, one line per op sorted by name, then products (`id | name | status`) and makers (`key | name`). Catalog values are JSON-string-escaped, U+0085/U+2028/U+2029 included. Caps are `MAX_PRODUCTS = 400` and `MAX_MAKERS = 200`, then `… and N more (ask the owner)`; above `PROMPT_MAX_BYTES` (64 KiB) it raises `ValueError`. Snapshot `hass/tests/fixtures/interpreter-prompt.txt`. Added `hass/tests/test_interpreter_prompt.py`.

Checks at PR head 75a413b (recorded in PR #81): `python3 -m unittest hass.tests.test_interpreter_prompt hass.tests.test_interpreter_local -v` ran 18 tests, OK. CI `check` passed at 75a413b.

Limits: no wiring and no model call.

## H22 daily interpreter call cap (NB-AV-07) — October 31, 2026

Branch rb/nb-av-07 from origin/main 212262c (NB-AV-07, PR #83: commits 6caf121, 8148a6e, merged as d56f15358c628e0fd71ca4cf1593357d27c48f6a). Optional setting `interpreterDailyCap`: an int from 1 to 10000, absent or `null` for no cap, anything else a `ConfigError`. With a cap, `_request` counts calls per America/Los_Angeles day in a `usage(day, calls)` table before calling the interpreter. At or over the cap the owner gets one `DAILY_LIMIT` reply (disposition `daily-limit`), with no draft and no call. Approvals, `undo`, `remember`, `history`, `no` and `status` are never counted, a duplicate provider id is never counted twice, and a failed call stays counted. `status` shows `Interpreter today: N of CAP`; the `docs/hass/COMMANDS.md` status row says so. Added `hass/tests/test_interpreter_cap.py`.

Checks at commit 6caf121 (recorded in PR #83, run under `memcap`): `python3 -m unittest hass.tests.test_interpreter_cap hass.tests.test_conversation hass.tests.test_status_pause hass.tests.test_commands_doc hass.tests.test_health -v` ran 47 tests, OK. CI `check` passed at PR head 8148a6e.

Limits: without a cap there is no `usage` table and no status line, and an interpreter exception behaves as before.

## H19 health reports the local model unreachable (NB-AV-06) — October 31, 2026

Branch rb/nb-av-06 from origin/main 212262c (NB-AV-06, PR #82: commits 61eacd1, 0a64fdc, f13497a, ecdeac7, merged as fe8971edf4efac05ea1e19a1ccd2c70538ada7a0). `python3 hass/health.py --state DIR --model <loopback url> [--model-name NAME]` adds check `model`: one GET `/api/tags` with a 3 s timeout, no proxy, no redirect and at most 256 KiB + 1 read; the URL rule is `interpreter_local.check_url`. The problem detail is fixed: `unreachable`, `http <status>`, `bad reply` or `model not installed` (a name without `:` means `<name>:latest`). A bad `--model`, an empty `--model-name` or `--model-name` alone exits 2 before any read. The URL and reply text never appear. Commit f13497a skips malformed model names in the reply instead of crashing. `docs/hass/SUPPORT.md` gains a `model` section. Added `hass/tests/test_health_model.py`.

Checks: test count not recorded in the PR (PR #82 points to the card for its output). CI `check` passed at PR head ecdeac7.

Limits: no `--model` leaves the output unchanged; notify is the existing `--seen` fingerprint. No send; the only network use is the loopback GET.

## H09 interpreter eval set and offline scorer (NB-AV-04) — October 31, 2026

Branch rb/nb-av-04 from origin/main d3f700d (NB-AV-04, PR #88: commit 88c3f59, merged as b75fd83f9610a6097faa260c6dae81c422a607ca). `hass/tests/fixtures/interpreter-eval.jsonl` holds exactly 30 synthetic cases: 8 product, 4 maker, 6 hike, 3 store hours/address, 3 corrections with `revises`, 3 must-ask, 3 unsupported. `hass/interpreter_eval.py` `score(cases, replies, registry)` passes each reply through `conversation._checked` and `interpret_check.check` and reports only ids and short reasons (`cases`, `passed`, `failed`, `missing`, `extra`). It exits 2 for an unreadable or malformed file, a bad or duplicate id, or a count other than 30. The replies fixture has 27 correct and 3 deliberately wrong replies. 4 `docs/hass/IMPLEMENTATION.md` lines. Added `hass/tests/test_interpreter_eval.py`.

Checks: test count not recorded in the PR. CI `check` passed at PR head 88c3f59.

Limits: `--live --url U --model M --out FILE` is operator-only, writes a new file outside the repo and is never run in CI or tests (fake transport).

## H12 a photo opens one needs-details draft; a later text fills it (NB-AV-09) — October 31, 2026

Branch rb/nb-av-09 from origin/main fe8971e (NB-AV-09, PR #79: commits 8e97486, 4f5c5c3, be0b176, 56d0b5c, merged as 34856246dc42a98f8ee007a4041756717f5850f1). `Conversation(..., photos=None)`: with a photo source, one owner photo is stored with `media.store_original(..., source="owner-chat")` and opens one `needs-details` draft `[product.set_photo {photo}]` asking `PHOTO_QUESTION` (disposition `photo-draft`); `load_settings(sdir, photos=True)` requires `mediaRoot`. More than one attachment gets `attachment-many` with nothing fetched. The same photo while its draft waits gets `photo-duplicate` and no new row. A caption goes to `_request` and is never a command or approval. A fill naming another photo gets `photo-mismatch`. Fix commit be0b176: `no <code>` (or a bare no) cancels a needs-details photo draft; `yes` never approves it. Added `hass/tests/test_photo_draft.py`.

Checks at commit 8e97486 (recorded in PR #79): `python3 -m unittest hass.tests.test_photo_draft hass.tests.test_attachment_reply hass.tests.test_conversation hass.tests.test_set_photo -v` ran 41 tests, OK. CI `check` passed at PR head 56d0b5c.

Limits: `photos=None` keeps the RF0835-5 `ATTACHMENT_REPLY` path unchanged.

## H17 status counts photo drafts and pending attachments (NB-AV-12) — October 31, 2026

Branch rb/nb-av-12 from origin/main 53669fe (NB-AV-12, PR #95: commit 8f8d9cb, merged as 65d074f1893ffc6bcd2222456a7ecb461fa7da50). `status` adds `Photos waiting for details: N` (unexpired needs-details drafts made only of `product.set_photo` ops) and `Photos still downloading: M` (inbox rows `pending` with `tries > 0`, read with `mode=ro` and `timeout=1`). There is no line when the count is 0, when the inbox file is missing (it is never created) or has no `tries` column; any `sqlite3.Error` gives `unavailable`. The `docs/hass/COMMANDS.md` status row names both lines. Added `hass/tests/test_status_photos.py`.

Checks at PR head 8f8d9cb (recorded in PR #95): `python3 -m unittest hass.tests.test_status_photos hass.tests.test_status_pause hass.tests.test_status_rsvp_off hass.tests.test_commands_doc -v` ran 31 tests, OK. CI `check` passed at 8f8d9cb.

Limits: read-only and counts only; the per-draft `needs details` line is unchanged.

## H12 photo limits named in the reply; nothing stored or drafted (NB-AV-10) — October 31, 2026

Branch rb/nb-av-10 from origin/main a808bd1 (NB-AV-10, PR #94: commit 5bd825b, merged as 31d573c5d8dd4980b86516ccd2666d35dda10996). New pure `media.check_photo(data)` runs the `store_original` checks and the web-copy filter in memory and raises `Refused(code)`. `_photo` runs it first, so a refused photo gets its fixed reply (disposition `photo-refused:<code>`) and leaves no original, sidecar, web copy or draft; before, a sideways or unreadable photo was still stored. `REPLIES` name the limit (JPEG or PNG, 20 MB, the right way up), and the new code `many` answers two or more attachments with nothing fetched. 3 `docs/hass/COMMANDS.md` lines; two `test_photo_draft.py` assertions now expect the new reply and disposition. Added `hass/tests/test_photo_limits.py`.

Checks at PR head 5bd825b (recorded in PR #94, run under `memcap`): `python3 -m unittest hass.tests.test_photo_limits hass.tests.test_photo_draft hass.tests.test_media hass.tests.test_media_web hass.tests.test_commands_doc -v` ran 44 tests, OK. CI `check` passed at 5bd825b.

Limits: `store_original` itself is unchanged and still keeps a sideways original, which `web_copy` then refuses.

## H16 attachment fetch failures wait, retry 3 times, then reply (NB-AV-11) — October 31, 2026

Branch rb/nb-av-11 from origin/main 33279db (NB-AV-11, PR #93: commits f370f9b, 88e30a0, 755f926, merged as ca364a672604b62a1abc15a329a738aae10e1f3c). When the photo source's `fetch` raises or returns nothing, `handle` raises `AttachmentPending` and the transaction rolls back: nothing is recorded and the caption is not read. `hass/inbox.py` adds `tries`/`next_try_at` (by `ALTER TABLE` on an older inbox), `MAX_TRIES = 3` and `BACKOFF_S = (30, 120)`; `drain` stops at a head message that is not yet due, so order is kept. The 3rd try sends one `FETCH_FAILED` reply (disposition `attachment-failed`) and stores and drafts nothing. New read-only `Inbox.waiting()`. Added `hass/tests/test_attachment_retry.py`.

Checks at commit f370f9b (recorded in PR #93): `python3 -m unittest hass.tests.test_attachment_retry hass.tests.test_inbox hass.tests.test_inbox_unreadable hass.tests.test_statebackup_inbox hass.tests.test_health_inbox hass.tests.test_photo_draft -v` ran 50 tests, OK. CI `check` passed at PR head 755f926.

Limits: other exceptions behave as before: they propagate and are not counted as a try.

## H09 demo transcript v2 with a photo, approval, screenshot and undo (NB-AV-13) — October 31, 2026

Branch rb/nb-av-13 from origin/main 4f33ef9 (NB-AV-13, PR #96: commits b3215fc, 9970d36, 43833e8, 58ce584, merged as 759dc93d1a37adca339b1dc85cfccae6e54f22af). `hass/fixture_chat.py --photos DIR`: a fixture row's `photos: [name]` becomes its attachments, and the adapter serves those files' bytes as the Conversation's photo source. Each name must be a regular file directly inside DIR (no `..`, `/`, symlink or missing file), otherwise exit 2 at parse time before anything is handled; without `--photos` the field is ignored. New 8-row `conversation-demo-photo.jsonl` and `-interpreter.json`: photo with caption, the same photo again, the fill, `yes`, `history`, `undo`, `yes` and a redelivered photo. Fix commit 43833e8 gives a statebackup drill redaction test a sentinel no tmp path can contain. One `hass/README.md` pointer. Added `hass/tests/test_demo_transcript_photo.py`.

Checks at commit b3215fc (recorded in PR #96, run under `memcap`): `python3 -B -m unittest hass.tests.test_demo_transcript_photo hass.tests.test_demo_transcript hass.tests.test_fixture_chat -v` ran 12 tests, OK (skipped=1); pre-push hass unittests passed. CI `check` passed at PR head 58ce584. Re-run on main df99c97 for this ledger: `python3 -B -m unittest hass.tests.test_set_photo hass.tests.test_interpret_check hass.tests.test_memory_alias hass.tests.test_interpreter_local hass.tests.test_retention hass.tests.test_claims hass.tests.test_interpreter_prompt hass.tests.test_interpreter_cap hass.tests.test_health_model hass.tests.test_interpreter_eval hass.tests.test_photo_draft hass.tests.test_status_photos hass.tests.test_photo_limits hass.tests.test_attachment_retry hass.tests.test_demo_transcript_photo` ran 132 tests, OK.

Limits: fixtures only: no live bridge, download, model call or send. The v1 `test_demo_transcript.py` is unedited.

## H13 store hours repeats ignore case, spacing and dash style (RF1720-1) — October 31, 2026

Branch rb/rf1720-1 from origin/main dea25e3 (RF1720-1, PR #114: commit 3854827134d, merged as e485da94f9ef26e191f06bf40cf0d9fa95f0527d). For Michael: two hours lines that differ only by case, spacing or dash style are now refused as repeats, and the refusal names both 1-based line numbers: `hours lines {j} and {i} say the same thing` (first pair only). New private `_line_key` in `hass/ops/store.py` (NFKC, U+2010–U+2015 and U+2212 to `-`, whitespace runs collapsed, `casefold()`) is used only for the comparison; Michael's exact text is saved. The no-op check stays exact (re-casing a line is a real change), and the line count and length limits are still checked first with the same messages. One `test_store_limits.py` assertion now expects the new message. Added `hass/tests/test_store_hours_repeat.py`.

Checks at PR head 3854827134d (recorded in PR #114): `python3 -m unittest hass.tests.test_store_hours_repeat hass.tests.test_store_ops hass.tests.test_store_limits hass.tests.test_undo` ran 32 tests, OK. CI `check` passed at 3854827134d.

Limits: accents are not folded. The content validator's repeat check stays exact.

## Site: today's hike stays listed as Today until midnight Pacific (RF1720-2) — October 31, 2026

Branch rb/rf1720-2 from origin/main 6304c56 (RF1720-2, PR #115: commit 8d3257d, merged as a962d6cb645550292284b2ca4b925f60ec5f3544). For Michael: a scheduled hike that started earlier today stays on the community page until midnight Pacific, and its date line reads `Today — started <h:mm AM/PM Pacific>`. `storefront-mockup/community.js` adds `pacificDay` (YYYY-MM-DD in America/Los_Angeles); `upcoming` keeps a `scheduled` hike while its start is in the future or its Pacific day is today. Cancelled and completed hikes never qualify. Sorting, the `THE NEXT HIKE` label, the RSVP button and the RSVP modal are unchanged. `storefront-mockup/community-ui-qa.cjs` adds one block (no existing assertion edited) with a fixed browser clock per case: start + 30 min, start − 1 min, 00:01 Pacific the next day, 23:59 Pacific in an `Asia/Tokyo` browser, and a cancelled copy of the fixture hike. The block reads the fixture hike from `/api/community`, because the static `community.json` has no events.

Checks at PR head 8d3257d (recorded in PR #115, run under `memcap` on port 3191 because 3101 was in use): the `check.yml` community UI steps printed `Community UI passed` and `community-qa.py exit 0`; the same run with the old `community.js` failed `Started hike not listed as Today`. `python3 -m unittest discover -s hass/tests -t .` ran 849 tests, OK (skipped=5). CI `check` passed at 8d3257d.

Limits: the day is the Pacific day, whatever the visitor's time zone. RSVP acceptance is unchanged.

## H06 store preview check also finds the address (RF1720-3) — October 31, 2026

Branch rb/rf1720-3 from origin/main 6304c56 (RF1720-3, PR #117: commit 03d551e, merged as b52437cd9a4fdbf6656d4e44de595762664696d4). For Michael: the store preview check now also reports whether the street address and town are shown, not only the hours. `hass/preview.py` `target_for` store branch carries `streetAddress` and `town` from the record's `after` value (empty string when missing). `hass/screenshot.cjs` sets `checks.addressShown` when both are non-empty: true only when the page text contains `<street>, <town>` (top line) and `<street> · <town>` (visit block). When either is empty the key is not set, so older records keep working. Product, maker and event checks are unchanged. One `test_store_ops.py` assertion now expects the two new keys. Added `hass/tests/test_preview_store_address.py`.

Checks at PR head 03d551e (recorded in PR #117, real Chromium, none skipped): `python3 -m unittest hass.tests.test_preview_store_address hass.tests.test_preview hass.tests.test_preview_viewports hass.tests.test_preview_overlay hass.tests.test_store_ops -v` ran 37 tests, OK. Pre-push tests were not run (host busy). CI `check` passed at 03d551e.

Limits: maker previews still have no check.

## H05 interpreter-check names drop invisible and direction characters (RF1730-1) — October 31, 2026

Branch rb/rf1730-1 from origin/main 6304c56 (RF1730-1, PR #116: commit 52e1bca, merged as bad06d5bb93086cf019257e0ebf0acf332d51e7d). For Michael: any op, field or draft-code name that the interpreter check shows him in a question now contains only visible characters. `hass/interpret_check.py` `_clean` drops characters in Unicode categories `Cc`, `Cf`, `Zl`, `Zp`, `Cs`, `Co` and `Cn` (controls, zero-width and direction marks, BOM, line and paragraph separators), then applies the existing 40-character cut, so the cut counts visible characters only. A name left empty shows as `(unnamed)`. Accents, CJK and emoji are kept. Values are never touched, and a valid result is still returned unchanged. Existing `test_interpret_check.py` unedited. Added `hass/tests/test_interpret_check_names.py`.

Checks at PR head 52e1bca (recorded in PR #116): `python3 -m unittest hass.tests.test_interpret_check_names hass.tests.test_interpret_check -v` ran 18 tests, OK; `hass.tests.test_interpreter_eval` ran 10 tests, OK. Pre-push tests were not run (host busy). CI `check` passed at 52e1bca.

Limits: only names shown in interpreter-check questions are cleaned; the content text rules are RF1300-10's.

## H10 product photo alt text must describe the photo (RF1730-2) — October 31, 2026

Branch rb/rf1730-2 from origin/main e485da9 (RF1730-2, PR #119: commit bc549f9, merged as 0cb6ac9e85404b4c7be5dfd47b265b4f4c6a2556). For Michael: `product.set_photo` now refuses an `imageAlt` that is a file name (ends `.jpg`, `.jpeg`, `.png`, `.heic`, `.heif`, `.gif`, `.webp`, `.tif` or `.tiff`), a camera or phone default name (`IMG_4021`, `DSC 0042`, `pxl_2026…`), a bare placeholder word (`photo`, `image`, `N/A`, `TBD`, …), contains the photo id, or has fewer than 3 letters, with one fixed reply: `imageAlt should say what the photo shows (for example "Hass avocados in a wooden crate"), not a file name or placeholder`. The new `_alt_problem` in `hass/ops/photos.py` runs right after the photo-id check and before the media store is read, so nothing is written. Real descriptions behave as before. Existing tests unedited. Added `hass/tests/test_set_photo_alt.py`.

Checks at PR head bc549f9 (recorded in PR #119, run under `memcap`): `python3 -m unittest hass.tests.test_set_photo_alt hass.tests.test_set_photo hass.tests.test_undo -v` ran 23 tests, OK. Pre-push tests passed (hass unittests). CI `check` passed at bc549f9.

Limits: the rule catches file names and placeholders, not wrong descriptions.

## H05 a repeated change in one message becomes a question (RF1730-3) — October 31, 2026

Branch rb/rf1730-3 from origin/main 0cb6ac9 (RF1730-3, PR #122: commit 3fe510a, merged as d31d732cfc529135b3136c153f5e366ca800da1b). For Michael: when one message lists the same change twice (same `op` and equal `args` in any key order, compared with `json.dumps(sort_keys=True)`), `interpret_check.check` returns one question naming the first repeated pair: `Changes 1 and 2 in that message are the same. Did you mean to change something else? Could you say it another way?` Nothing is drafted. The check runs after the per-call shape check and before the op, field, kind and revises checks. Args that cannot be serialised are never called the same and never raise. Different changes to the same item, and JSON-different values (`true`, `1`, `1.0`), pass unchanged. No existing test edited. Added `hass/tests/test_interpret_check_repeat.py`.

Checks at PR head 3fe510a (recorded in PR #122): `python3 -m unittest hass.tests.test_interpret_check_repeat hass.tests.test_interpret_check -v` ran 20 tests, OK. CI `check` passed at 3fe510a.

Limits: only exact repeats in one message are caught; repeats across messages are the editor's no-op refusal.

## H16 a waiting question expires like a proposal (AV1537-01) — October 31, 2026

Branch rb/av1537-01 from origin/main 6a5328b (AV1537-01, PR #73: commits 9bf984b, c1ec1ed, 2d17b97, merged as 26a0f0878c4765811acd178b51aeaafab91b9eeb). For Michael: a needs-details question now lapses after `approvalTtlSeconds` like a proposal; an answer refreshes it, and a late answer starts a new request. `hass/conversation.py` adds `expired` to the needs-details transitions and `_expiry(row)` (a legacy row without `expires_at` uses `created_at + ttl`, no migration write); `status` and the interpreter's `pending` hide a lapsed question. Merge fix c1ec1ed (operator decision 2026-10-31 17:28): a `revises` code whose draft expired starts fresh; an unknown code still gets NB-AV-01's question. Added `hass/tests/test_needs_details_expiry.py` and `hass/tests/test_revises_expired_vs_unknown.py`.

Checks at PR head 2d17b97 (recorded in PR #73): `python3 -B -m unittest hass.tests.test_revises_expired_vs_unknown hass.tests.test_needs_details_expiry hass.tests.test_interpret_check -v` ran 19 tests, OK; `python3 -m unittest discover -s hass/tests -t .` ran 538 tests, OK (skipped=5). CI `check` passed at 2d17b97.

Limits: no separate question TTL setting, no schema migration and no health check; cancelling a question is AV1537-02.

## H17 no or cancel closes a waiting question (AV1537-02) — October 31, 2026

Branch rb/av1537-02 from origin/main 26a0f08 (AV1537-02, PR #84: commit d61583a, merged as d3f700db7ae4f46e9da25eee79d0886412bb0553). For Michael: `no`, `cancel` or `reject` (with or without a code) now closes one open question as well as a proposal, with `Cancelled <code>; nothing changed.`; several open items give the usual "Which draft do you mean?" list. It works while paused. `yes <question code>` answers `<code> still needs details: <question>` and never approves; a bare `yes` keeps `Nothing is waiting for approval.` (unedited `test_conversation`). A later fill naming a cancelled question starts a new request. `docs/hass/COMMANDS.md` rows say "draft or question". Added `hass/tests/test_cancel_question.py`.

Checks at PR head d61583a (recorded in PR #84, run under `memcap`): `python3 -B -m unittest hass.tests.test_cancel_question hass.tests.test_conversation hass.tests.test_status_pause hass.tests.test_commands_doc -v` ran 39 tests, OK; full hass discovery ran 579 tests, OK (skipped=5). Pre-push tests were not run (host busy). CI `check` passed at d61583a.

Limits: help text, expiry and interpreter behaviour are unchanged.

## H17/H25 help lists the owner commands (AV1537-03) — October 31, 2026

Branch rb/av1537-03 from origin/main d3f700d (AV1537-03, PR #89: commit 983196510a, merged as 53669fe9fc2e996d91d5c31df3a02786a643a1f4). For Michael: a whole message `help`, `commands` or `?` replies a short plain-text list (13 lines of at most 70 characters): how to send a change in plain words, then one example per command. It is read-only like `status`, works while paused, and expires nothing. `hass/conversation.py` adds `HELP_TEXT` and the `help` verb; `docs/hass/COMMANDS.md` one row. Added `hass/tests/test_help.py`, which keeps the list in step with the parser verbs.

Checks at PR head 983196510a (recorded in PR #89): `python3 -B -m unittest hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_conversation -v` ran 28 tests, OK; full hass discovery ran 617 tests, OK (skipped=5). Pre-push tests were not run (host busy). CI `check` passed at 983196510a.

Limits: the owner phone guide is separate H25 work; `find` came with AV1537-04.

## H03 find lists matching products and makers (AV1537-04) — October 31, 2026

Branch rb/av1537-04 from origin/main 53669fe (AV1537-04, PR #99: commits 03b0cca, a1290fa4f, d6ba964, merged as 33279db21e9fd1de3b1aed2a9a95d16cb44a1a56). For Michael: `find <words>` replies up to 10 lines `product <id>: <name> (<status>)` or `maker <key>: <name> (<status>)`, then `… <n> more; add a word.` (or `or more` / `maybe more` when the lookup cap hides the true total; no made-up count). No hit gives `No product or maker matches "<query>".`; unreadable content gives `Catalog unavailable right now; nothing changed.` An alias match adds ` (your alias)`. Read-only: no interpreter, draft or expiry pass; works while paused. One `HELP_TEXT` line and one `docs/hass/COMMANDS.md` row. Added `hass/tests/test_find.py`.

Checks at PR head d6ba964 (recorded in PR #99): `python3 -B -m unittest hass.tests.test_find hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_catalog_ops -v` ran 34 tests, OK; full hass discovery ran 701 tests, OK (skipped=5). Pre-push tests passed. CI `check` passed at d6ba964.

Limits: `lookup` itself is unchanged; hikes and route ideas are not searched.

## H01 text fields have maximum lengths (AV1537-05) — October 31, 2026

Branch rb/av1537-05 from origin/main 833b0fb (AV1537-05, PR #85: commits 57e2ae2, 2a270a2, 4c38657, merged as abaf1176abfad7eeee780ff1de4510e5311a3b1e). For Michael: every owner-editable text field has a maximum length from one table, `content_model.TEXT_LIMITS` (for example product name 80, description 600, hike recap 2000 characters, counted in code points). A longer value is `<where>: longer than <n> characters`, so ops refuse it as `invalid` before any draft; current content passes. Fix commit 4c38657 shortens one `test_hike_ids.py` fixture title to 79 characters (it was over the new 80 limit). One `hass/README.md` line. Added `hass/tests/test_text_limits.py`.

Checks at PR head 4c38657 (recorded in PR #85): the spec acceptance set plus `test_hike_ids`, `python3 -B -m unittest hass.tests.test_text_limits hass.tests.test_content hass.tests.test_catalog_ops hass.tests.test_hike_ops hass.tests.test_store_ops hass.tests.test_product_alt hass.tests.test_hike_ids -v`, ran 65 tests, OK. Pre-push tests were not run (host busy). CI `check` passed at 4c38657.

Limits: no limit value is owner-configurable; `hass/ops/__init__.py` and the content are unchanged.

## H05/H06 proposals show changed text in full (AV1537-06) — October 31, 2026

Branch rb/av1537-06 from origin/main 33279db (AV1537-06, PR #102: commits ac3ceb7, d27c780, dc0fa0e, merged as 0f89574bb7837465485d9a89990d963b5099b8ae). For Michael: a proposal shows each changed field's new value in full, so he approves what he can read; store hours lines are joined with `; `, and a value with line breaks is printed indented after `→`, so `Expires …` and `Reply yes …` stay the last two lines. The old value, `status`, `history` and `Applied …` keep the 120-character cut. `hass/conversation.py` adds `_full` and `_arrow`. Added `hass/tests/test_proposal_full_text.py`.

Checks at PR head dc0fa0e (recorded in PR #102, run under `memcap`): `python3 -B -m unittest hass.tests.test_proposal_full_text hass.tests.test_conversation hass.tests.test_demo_transcript hass.tests.test_status_pause -v` ran 37 tests, OK; full hass discovery ran 738 tests, OK (skipped=5). Pre-push tests passed. CI `check` passed at dc0fa0e.

Limits: no bridge message splitting; screenshots and the summary format are unchanged.

## H17 status names past scheduled hikes (AV1537-07) — November 1, 2026

Branch rb/av1537-07 from origin/main 5370850e (AV1537-07, PR #145: commit 275d2e4, merged as b9612d0c37c64d04d3d885b5140733a38973377b). For Michael: `status` adds, after the upcoming hikes, `Hike <title> <local start> has passed but is still scheduled; send "complete <title>" or "cancel <title>" in your own words.` for each scheduled hike whose start is at or before now (oldest first, at most 5, then `… and <n> more past hikes still scheduled.`). These lines never show or read guest counts; unreadable content is still `Hikes: unavailable`. `test_status_pause.py` and `test_status_rsvp_off.py` were edited to expect the new line (G decision 2026-11-01 05:45 PST, this card only). Added `hass/tests/test_status_past_hikes.py`.

Checks at PR head 275d2e4 (recorded in PR #145): `python3 -B -m unittest hass.tests.test_status_past_hikes hass.tests.test_status_pause hass.tests.test_status_rsvp_off -v` ran 25 tests, OK; full hass discovery ran 1065 tests, OK (skipped=10). Pre-push tests passed. CI `check` passed at 275d2e4.

Limits: hikes are never completed automatically; no site JS change and no health alert.

## H04 hike.update can clear optional fields (AV1537-08) — October 31, 2026

Branch rb/av1537-08 from origin/main db937b3 (AV1537-08, PR #75: commit 03670656f, merged as f311e31281394ccaa75ec04f65384cd99d64e910). For Michael: `hike.update` takes `clear: [names]` and removes those optional fields (hike text except `meetingPoint`, or `trailId`) in the same draft as any set fields. Refused in this order: an unknown name (`clear: <name> is not a hike field`), a field that can never be removed (title, date, time, meetingPoint, RSVPs, capacity: `clear: <name> cannot be removed`), a field also set (`<name> cannot be set and cleared together`). Clearing only absent fields changes nothing. `hass/ops/hikes.py`, one `hass/README.md` line. Added `hass/tests/test_hike_clear.py`.

Checks at PR head 03670656f (recorded in PR #75): `python3 -B -m unittest hass.tests.test_hike_clear hass.tests.test_hike_ops hass.tests.test_hike_rsvp_on hass.tests.test_hike_guest_warning hass.tests.test_hike_capacity_rsvp_off hass.tests.test_hike_move_warning hass.tests.test_interpret_check -v` ran 60 tests, OK; full hass discovery ran 525 tests, OK (skipped=5). CI `check` passed at 03670656f.

Limits: recaps (AV1537-09) and route ideas are not cleared by this op.

## H04 hike.recap corrects a completed hike's recap (AV1537-09) — October 31, 2026

Branch rb/av1537-09 from origin/main 833b0fb (AV1537-09, PR #86: commit a15bc34, merged as 278dca8be5c55fd1ce76e18f9c1773c5c9f81f64). For Michael: `hike.recap {id, recap}` sets or corrects the trail-journal recap of a completed hike and changes nothing else; undo restores the old text. A scheduled hike is refused (`<id> is scheduled; use hike.complete with a recap`), a cancelled one too (`<id> is cancelled`), and the same recap again changes nothing. Every other field of a completed hike stays locked. `hass/ops/hikes.py`, `hass/README.md`. Added `hass/tests/test_hike_recap.py`.

Checks at PR head a15bc34 (recorded in PR #86): `python3 -B -m unittest hass.tests.test_hike_recap hass.tests.test_hike_ops hass.tests.test_hike_clear -v` ran 23 tests, OK; full hass discovery ran 588 tests, OK (skipped=5). Pre-push tests passed. CI `check` passed at a15bc34.

Limits: other completed-hike fields, photo recaps and site JS are unchanged.

## H03 changing a maker's place warns how many product cards change (AV1537-10) — October 31, 2026

Branch rb/av1537-10 from origin/main 212262c (AV1537-10, PR #87: commit 43f93b6, merged as b10efa4b7d84a34499fddea1b3c9dbb2e9445be6). For Michael: a `maker.edit` that changes `place` still drafts and adds one warning, `changes the "Based in" line on N active product card(s) of maker <key> (town search follows it)`, or `maker <key> has no active products; no product card changes`. Hidden and held products are not counted; an unchanged place, or a name, story or link change alone, never warns. `hass/ops/catalog.py`, one `hass/README.md` line. Added `hass/tests/test_catalog_place.py`.

Checks at PR head 43f93b6 (recorded in PR #87, run under `memcap`): `python3 -m unittest hass.tests.test_catalog_place hass.tests.test_catalog_ops hass.tests.test_catalog_badge hass.tests.test_catalog_unchanged -v` ran 36 tests, OK. Pre-push tests passed. CI `check` passed at 43f93b6.

Limits: a place edit is never refused; `shop.js` and the proposal text are unchanged.

## H19 health reports applied changes whose preview check failed (AV1537-11) — October 31, 2026

Branch rb/av1537-11 from origin/main fe8971e (AV1537-11, PR #91: commits eab712c, f6f40cd, dc5992f, d2a7476, merged as 340515b9d2b7d7a96270acc2db960a976590266c). For the operator: `hass/health.py` reports `unverified` with a count of applied changes whose preview check failed in the last 72 hours (`--unverified-hours N`, at least 1); a database without `checked_at` is skipped. Count only: no code, summary or sender. The count clears once the change is undone or the window passes. `docs/hass/SUPPORT.md` gains an `unverified` section. Added `hass/tests/test_health_unverified.py`.

Checks at PR head d2a7476: PR #91 lists the eight edge paths but records no run output; its spec acceptance command is `python3 -m unittest hass.tests.test_health_unverified hass.tests.test_health hass.tests.test_health_unreadable hass.tests.test_support_doc -v`. CI `check` passed at d2a7476.

Limits: the preview check is not re-run; alert delivery and timers are attended operator work.

## H19 health reports guest counts unreadable or unset (AV1537-12) — October 31, 2026

Branch rb/av1537-12 from origin/main 340515b (AV1537-12, PR #100: commit 6b3e836, merged as 4f33ef95773e4384cd150b777196c4471d251d52). For the operator: `hass/health.py` reports `guest-counts` `unreadable` when `guestCountsDb` is set but cannot be opened read-only, and `unset` when it is not set while an upcoming scheduled hike takes RSVPs; `hikes unreadable` is info only. The detail is always a fixed word, never a path, name or address. `docs/hass/SUPPORT.md` gains a `guest-counts` section. Added `hass/tests/test_health_guests.py`.

Checks at PR head 6b3e836 (recorded in PR #100): `python3 -m unittest hass.tests.test_health_guests hass.tests.test_health hass.tests.test_health_unverified hass.tests.test_support_doc -v` ran 41 tests, OK. Pre-push tests were not run (host busy). CI `check` passed at 6b3e836.

Limits: no capacity or over-booking check; guest names are never read; `status` and `hikes.py` are unchanged.

## H20/H25 statebackup drill runs the restore drill in one command (AV1537-13) — October 31, 2026

Branch rb/av1537-13 from origin/main fe8971e (AV1537-13, PR #90: commit 9f31f11, merged as 5ffc2d70ded975d35e9e5d0a6515f0a61053fa3e). For the operator: `python3 hass/statebackup.py drill BACKUP --into NEWDIR --worktree DRILLWT` runs `verify`, `restore --paused` into a new dir, then the read-only health check and history on it, and prints one JSON line of check ids and counts (`ok`, `corrupt` with `step: verify`, or `drill-failed` with its step; the restored dir is kept). It adds no write path of its own. The drill never restores onto the writer worktree: restore's attended refusal stands. `docs/hass/SUPPORT.md` uses it for restore steps 2–3. Added `hass/tests/test_statebackup_drill.py`.

Checks at PR head 9f31f11 (recorded in PR #90): `python3 -m unittest hass.tests.test_statebackup_drill hass.tests.test_statebackup hass.tests.test_statebackup_paused hass.tests.test_health hass.tests.test_support_doc -v` ran 37 tests, OK. CI `check` passed at 9f31f11.

Limits: no live restore, no deletion of drill dirs, no timers and no backup retention.

## H25 owner known-limits page tied to the code (AV1537-14) — October 31, 2026

Branch rb/av1537-14 from origin/main 53669fe (AV1537-14, PR #97: commits f8049fb, e22a272, merged as 422a4a953ead456f56f09412e0da56aa296bb89d). For Michael: `docs/hass/LIMITS.md` lists in plain words what Hass can take: one photo per message (JPEG or PNG, up to 20 MB), waiting changes expire, at most 20 things per message, history 5, memory 20, name search 10, and the text sizes. Each number cites its code constant; `hass/conversation.py` names `HISTORY_MAX = 5`. `docs/hass/README.md` links the page. Added `hass/tests/test_limits_doc.py`, which fails when a number and its constant disagree.

Checks at commit f8049fb (recorded in PR #97): `python3 -m unittest hass.tests.test_limits_doc hass.tests.test_conversation hass.tests.test_status_pause -v` ran 34 tests, OK. Pre-push tests passed. CI `check` passed at PR head e22a272.

Limits: no limit value changes (owner call); support contact text and voice notes are out of scope.

## H10 label reader suggests name, brand and category (AV1537-15) — October 31, 2026

Branch rb/av1537-15 from origin/main ca364a6 (AV1537-15, PR #103: commits 2692d21, 2f41ba9, merged as c09719988c755ce34b44ab4824c117b76b37aae7). For Michael: when a new photo opens a needs-details draft and a label reader is configured, the reply may add `The label looks like: <brand> <name> (<category>). Is that right? Say which product it is either way.` Label facts are only a question: ops stay `product.set_photo {photo}` and nothing is filled in. Maker, organic and origin are never read from a photo. New `hass/label_reader.py` (loopback local model, injectable transport) reads the metadata-free web copy outside the transaction and drops a value with a claim term, control characters, an unknown category or one over `TEXT_LIMITS`; any failure leaves the reply unchanged. `docs/hass/IMPLEMENTATION.md` section. Added `hass/tests/test_label_reader.py`.

Checks at PR head 2f41ba9 (recorded in PR #103): `python3 -m unittest hass.tests.test_label_reader hass.tests.test_interpreter_local hass.tests.test_conversation hass.tests.test_media hass.tests.test_media_time hass.tests.test_proposal_full_text` ran 60 tests, OK. Pre-push tests passed. CI `check` passed at 2f41ba9.

Limits: not wired into a service; no live model call in tests or CI, no model change and no Mac bridge.

## H08 bridge marks tapbacks as reactions and drops receipts (AV1737-01) — October 31, 2026

Branch rb/av1737-01 from origin/main a962d6cb64555 (AV1737-01, PR #121: commits a2559b0, 1cea46b, ffeeee4, merged as 81af8aec4663bd73646f376a5c1608f07f591f09). For Michael: a tapback (BlueBubbles `associatedMessageType` a non-empty string or an integer) reaches Hass as `kind` `reaction`, with no interpreter call; any other tapback type is dropped as `malformed`. An `updated-message` without a positive integer `dateEdited` is a delivery or read update and is dropped as `receipt`; a real edit stays `edited`, and a group chat is still refused first. `hass/bridge.py` `normalize()`, synthetic fixtures `reaction.json` and `receipt.json`; one `test_attachment_reply.py` edit case now carries `dateEdited`. Added `hass/tests/test_bridge_reactions.py`.

Checks at PR head ffeeee4 (recorded in PR #121): `python3 -m unittest hass.tests.test_attachment_reply hass.tests.test_bridge hass.tests.test_bridge_reactions hass.tests.test_bridge_pictures` ran 38 tests, OK; full hass discovery at 1cea46b ran 880 tests, OK (skipped=5). Pre-push tests were not run (host busy). CI `check` passed at ffeeee4.

Limits: fixtures only: no live Mac or BlueBubbles connection and no model call; the reply to a reaction or edit is AV1737-03 and edit ids are AV1737-02.

## H08/H16 each real edit gets its own inbox id (AV1737-02) — November 1, 2026

Branch rb/av1737-02 from origin/main e4a8e49 (AV1737-02, PR #124: commit 2b7e1fd, merged as 125796885c3277933275ef3bf663074a3f49a0e1). For Michael: each real edit gets its own inbox id, `<guid>:edited:<dateEdited>`, and its received time from `dateEdited`, so a second edit of a message is queued instead of being taken for a duplicate, while the same edit delivered twice is still one duplicate. An overflowing `dateEdited` is dropped as `malformed`. New messages and reactions keep the guid and `dateCreated`. `hass/bridge.py` only; the inbox schema is unchanged. Added `hass/tests/test_bridge_edit_ids.py`.

Checks at PR head 2b7e1fd (recorded in PR #124): `python3 -m unittest discover -s hass/tests -t . -v` ran 923 tests, OK (skipped=10), including `hass.tests.test_bridge_edit_ids`. Pre-push tests passed. CI `check` passed at 2b7e1fd.

Limits: an edit is queued but its text is not read (AV1737-03); no inbox schema change and no live bridge.

## H08/H17 one fixed reply to an owner reaction or edit (AV1737-03) — November 1, 2026

Branch rb/av1737-03 from origin/main bdc80aa (AV1737-03, PR #136: commits e4597a4, b6700d8, merged as 02f1e1bd905a309b3588ed8874af555cd15add7a). For Michael: when he reacts to a message or edits one he sent, Hass sends one fixed reply, `I only read new messages, so that reaction or edit changed nothing. Send yes, no or the change as a new message.`, and records `not-read`. Reactions never approve: whatever the wording, there is no draft, approval, usage row or interpreter call, and a duplicate gets one reply. Edited text is not read. Echoes stay `echo`, a stranger's edit or reaction stays a silent `edited-ignored`, and a reaction never expires a waiting draft. `hass/conversation.py` (`NOT_READ_REPLY`); eight existing tests now expect `not-read` and the reply. Added `hass/tests/test_not_read_reply.py`.

Checks at commit e4597a4 (recorded in PR #136): `python3 -m unittest discover -s hass/tests -t . -v` ran 957 tests, OK (skipped=10), including `hass.tests.test_not_read_reply`. Pre-push tests at b6700d8 were not run (host busy; the try before failed only on a QA test whose port another builder held). CI `check` passed at b6700d8.

Limits: an edit's new text is never read and a reaction never approves; the bridge and the live Mac bridge are unchanged.

## H05/H22 owner text over the length cap gets one reply, never interpreted (AV1737-04) — November 1, 2026

Branch rb/av1737-04 from origin/main 5370850e (AV1737-04, PR #142: commit d2ca315, merged as dbf8c7bc485b8b912c23e3a9323bca03ab9f2318). For Michael: owner text over `MAX_OWNER_TEXT = 4000` characters gets one reply, `That message is over 4000 characters, so I did not read it and nothing changed. Send a shorter change.`, disposition `too-long`. It is never sent to the interpreter, no daily interpreter call is counted, and a waiting draft keeps its state and expiry. Commands, keywords and `remember` are handled before the check; exactly 4000 characters still goes through. `hass/conversation.py`; one `docs/hass/LIMITS.md` bullet. Added `hass/tests/test_owner_text_cap.py`.

Checks at PR head d2ca315 (recorded in PR #142): the spec command `python3 -m unittest discover -s hass/tests -t . -v`, which includes `hass.tests.test_owner_text_cap`, passed in the pre-push tests (no count recorded). CI `check` passed at d2ca315.

Limits: no bridge-side truncation, no per-field limit change and no interpreter prompt change.

## H17 bare yes repeats the waiting question with its code (AV1737-05) — October 31, 2026

Branch rb/av1737-05 from origin/main e4a8e49 (AV1737-05, PR #123: commits 8df662f, 41c4be9, merged as 2114508f5b2a69d0178bea507fb7e6e374cb4c6d). For Michael: a bare `yes` (or `approve`, `approved`) when no proposal waits but needs-details questions do now repeats each question, oldest first, as `<code> still needs details: <question>` instead of `Nothing is waiting for approval.`; nothing changes state and no approval row is written, also while paused. With a proposal waiting, `yes` works as before; `yes <question code>` gives the same line. `hass/conversation.py`; three existing tests expect the new line. Added `hass/tests/test_bare_yes_question.py`.

Checks before the final main merge (recorded in PR #123, run under `memcap`): `python3 -m unittest discover -s hass/tests -t .` ran 906 tests, OK (skipped=10), including `hass.tests.test_bare_yes_question`. Pre-push tests were not run (host busy). CI `check` passed at 41c4be9.

Limits: a question is never approved; no new command and no `status` wording change.

## H05/H06 an added record's proposal lists each field on its own line (AV1737-06) — November 1, 2026

Branch rb/av1737-06 from origin/main d31d732 (AV1737-06, PR #126: commit 3cec8a6, merged as a7350a83bd8d39863e14d2d6f51a8a8b13a79836). For Michael: a proposal that adds a product, maker or hike shows `<collection> <key>: new` and then one `  <field>: <value>` line per field, sorted, text in full. Empty fields are left out; at most 40 field lines, then `  … and N more fields`; a line break inside a value continues indented, so it cannot pass for a reply line of its own. Edit and removal lines, the summary, the draft hash and the stored ops are unchanged. `hass/conversation.py` (`_added`); one `test_proposal_full_text.py` expectation changed. Added `hass/tests/test_proposal_added.py`.

Checks at PR head 3cec8a6 (recorded in PR #126): `python3 -m unittest discover -s hass/tests -t .` ran 933 tests, OK (skipped=10), including `hass.tests.test_proposal_added`. Pre-push tests passed. CI `check` passed at 3cec8a6.

Limits: display only; time formatting is AV1737-07 and interpreter output is unchanged.

## H04/H05 hike start times read as weekday and Pacific date and time (AV1737-07) — November 1, 2026

Branch rb/av1737-07 from origin/main 0ac16c3 (AV1737-07, PR #153: commits 38318a4, a815d10, merged as f35586f4018f928874f6a4256c3a9c9cee31410e). For Michael: hike start times in proposals (`startsAt` edit lines and the added-hike field line) and in `status` (upcoming and passed-hike lines) read as weekday plus Pacific date and time, such as `Sat 2026-11-07 09:00 PST`, across the daylight-saving change; a bad or naive value is shown as written, never raised. Expiry, pause and waiting times keep their format and no other field is reformatted. `hass/conversation.py` (`_hike_time`); three status tests expect the weekday form. Added `hass/tests/test_hike_time_text.py`.

Checks at PR head a815d10: PR #153 records no run output (it points to the card's review request); its spec acceptance command is `python3 -m unittest discover -s hass/tests -t . -v` and its new test is `hass.tests.test_hike_time_text`. CI `check` passed at a815d10.

Limits: no site-side date formatting, warning-text change or locale setting.

## H06 result check covers every touched record, at most 5 (AV1737-08) — November 1, 2026

Branch rb/av1737-08 from origin/main eca8b8b (AV1737-08, PR #158: commit 25e1c6c, merged as 820a1b2a7acb2c4f110b2b9978b197275f1cb558). For Michael: after a change is applied, the result check captures every distinct touched record (`VERIFY_MAX = 5`), not only the first. The first failing capture stops the check and the reason names the record, `not verified: <collection> <key>: <error>`; records beyond five are named in one log line. The first screenshot keeps its name and is still the one sent. `hass/conversation.py` `verify`; two existing tests expect the record name. Added `hass/tests/test_verify_all_records.py`.

Checks at PR head 25e1c6c (recorded in PR #158, run under `memcap`): `python3 -m unittest hass.tests.test_verify_all_records hass.tests.test_status_pause hass.tests.test_health_unverified hass.tests.test_undo hass.tests.test_preview` ran 44 tests, OK (skipped=3). Pre-push tests were not run (host busy). CI `check` passed at 25e1c6c.

Limits: the preview checks themselves, undo verification and the real Playwright previewer are unchanged.

## H04 hike.create refuses a same-day twin (AV1737-09) — November 1, 2026

Branch rb/av1737-09 from origin/main 2114508f (AV1737-09, PR #130: commits b8e2769, 1e8c57f8f24a4ca7, merged as 27aa3ef5c1305a752517a276722f2049afd0bdd2). For Michael: `hike.create` refuses a second scheduled hike with the same title (case and inner spacing ignored) on the same Pacific day: `<existing id> is already scheduled with this title on <date>; update it instead`. Cancelled and completed hikes, another day and a route idea holding the id do not count; an unparseable start is skipped; the capacity question and the past-start refusal still come first. `hass/ops/hikes.py` (`_hike_twin`); five existing tests changed a second title only. Added `hass/tests/test_hike_twin.py`.

Checks at PR head 1e8c57f8f24a4ca7: PR #130 records no run output; its spec acceptance command is `python3 -m unittest discover -s hass/tests -t . -v` and its new test is `hass.tests.test_hike_twin`. CI `check` passed at 1e8c57f8f24a4ca7.

Limits: `hike.update` has no twin check; the id scheme and site rendering are unchanged.

## H06/H14 undo of a hike change carries the guest warnings (AV1737-10) — November 1, 2026

Branch rb/av1737-10 from origin/main bdc80aa (AV1737-10, PR #129: commits 74994e6, fdbb764, 66fc694, 1f9d98a, merged as a1b3f96412d724406f98fb0abe33e9df052f7337). For Michael: an undo that cancels a hike (undo of `hike.create`, or a restored `cancelled`), moves its start back or turns RSVPs off carries the forward op's draft warning: `<id> has N confirmed guests; nobody is notified automatically`, the move line, or `<id> guest count unavailable; check RSVPs before approving`. Warnings never refuse, and a refused undo adds none. `hass/ops/history.py`. Added `hass/tests/test_undo_guest_warnings.py`.

Checks before the final main merge (recorded in PR #129): `python3 -m unittest discover -s hass/tests -t . -v` ran 932 tests, OK (skipped=10), including `hass.tests.test_undo_guest_warnings`. Pre-push tests were not run (host busy). CI `check` passed at 1f9d98a.

Limits: nobody is notified; the capacity and past-start refusals and the forward ops are unchanged.

## Site: a full hike says so with no RSVP button; one place is singular (AV1737-11) — November 1, 2026

Branch rb/av1737-11 from origin/main 2114508f (AV1737-11, PR #128: commits 20948e5311ff501661, 91b9d10, merged as bdc80aa8f11fe573c43fc042a2accbeaf0feb95f). For guests: on `/hike` a hike with open RSVPs and no places left shows `This hike is full.` and no RSVP button; one place left reads `1 place available`; closed RSVPs still read `RSVP details will be shared when confirmed.` `storefront-mockup/community.js` (one line); `storefront-mockup/community-ui-qa.cjs` adds a fixture-only block and edits no existing assertion.

Checks at commit 20948e5311ff501661 (recorded in PR #128): `python3 storefront-mockup/community-qa.py` printed `Community UI passed`, and with the old `community.js` the new block failed `Full hike offered an RSVP`; `python3 -m unittest discover -s hass/tests -t .` ran 922 tests, OK (skipped=10). Pre-push tests were not run (host busy). CI `check` passed at 91b9d10.

Limits: the server capacity rule and its 409 path are unchanged; no waitlist, live community DB or deploy.

## Site: a cancelled hike stays listed, marked Cancelled, until its day ends (AV1737-12) — November 1, 2026

Branch rb/av1737-12 from origin/main bdc80aa (AV1737-12, PR #134: commit 197e9f1, merged as fc811de599db8f05dd9e74979c82acd87759b542). For guests: a cancelled hike stays on `/hike` until midnight Pacific at the end of its day, labelled `CANCELLED`, titled `Cancelled: …`, with `This hike is cancelled. Nothing else is needed from you.` instead of an RSVP button; after that it is gone. Scheduled, past and empty views are unchanged. `storefront-mockup/community.js` (`showCancelled`); `storefront-mockup/community-ui-qa.cjs` adds a block and reverses the one RF1720-2 assertion this unit replaced.

Checks at PR head 197e9f1 (recorded in PR #134): `python3 storefront-mockup/community-qa.py` printed `Community UI passed`, and with the old `community.js` it failed `Cancelled hike from earlier today not listed`. Pre-push tests passed. CI `check` passed at 197e9f1.

Limits: nobody is notified of a cancellation; no server change, cancellation reason, live community DB or deploy.

## Site forms: a refused RSVP or signup names the problem (AV1737-13) — November 1, 2026

Branch rb/av1737-13 from origin/main d31d732 (AV1737-13, PR #127: commit b45bdad, merged as b4062763d4562e56fbc69f0d6e4c59a832b80ae6). For guests: a refused signup or RSVP gets its own existing message (email, no update kind chosen, name, party size, `Please use the form on the page.`) instead of `Please check your name, email, and form selections.`, which stays for bad JSON and every other error, so nothing from Python leaks. A refusal writes no row. `storefront-mockup/community-server.py` (`FormError`); `storefront-mockup/community-qa.py` adds cases only.

Checks at PR head b45bdad (recorded in PR #127, run under `memcap` through a wrapper on port 3193): `python3 storefront-mockup/community-qa.py` printed `Community UI passed` and exited 0; with the old server it failed on the first bad-email case. Pre-push tests passed. CI `check` passed at b45bdad.

Limits: no front-end copy change, email delivery, live community DB or deploy.

## H19 health reports disk-low for the state or backups filesystem (AV1737-14) — November 1, 2026

Branch rb/av1737-14 from origin/main 2114508f (AV1737-14, PR #131: commit dd3febf, merged as c7070f8b4fc115dbd854aa6f0b5158f518740a84). For the operator: `hass/health.py --min-free-mb N` reports `disk-low` when the state dir's or the `--backups` dir's filesystem has less free space. The detail is free MB and the store name, never a path: `state: <n> MB free` or `backups: <n> MB free`, rounded down to 50 MB so `--seen` notifies only on a change; an unreadable filesystem is `<store>: free space unreadable`. Off by default; a value under 1 is a usage error. `docs/hass/SUPPORT.md` gains a `disk-low` section. Added `hass/tests/test_health_disk.py`.

Checks at PR head dd3febf (recorded in PR #131): `python3 -m unittest hass.tests.test_health_disk hass.tests.test_health hass.tests.test_health_backup_verify hass.tests.test_health_inbox hass.tests.test_health_model hass.tests.test_health_seen -v` ran 50 tests, OK. Pre-push tests passed. CI `check` passed at dd3febf.

Limits: nothing is deleted or rotated to free space; no health timer (attended) and no send.

## H17/H20 support inbox-integrity names the backup inbox snapshot (AV1737-15) — November 1, 2026

Branch rb/av1737-15 from origin/main 125796885c (AV1737-15, PR #133: commit 6c35a8f, merged as d0a3bf31c66a25dc48a2bbbff611e1a62564167d). For the operator: the `inbox-integrity` entry in `docs/hass/SUPPORT.md` no longer says backups lack the inbox. It names `python3 hass/statebackup.py verify BACKUP` on the newest backup (it checks that backup's `inbox.sqlite3` snapshot), then `pause changes`, leaving the damaged file untouched and the isolated restore drill, and warns that a restored inbox can replay or miss later messages. Live inbox replacement stays attended: stop and ask before any live replacement of `inbox.sqlite3`. Docs only, 3 lines.

Checks at PR head 6c35a8f (recorded in PR #133): `python3 -m unittest hass.tests.test_support_doc -v` ran 8 tests, OK; full hass discovery ran 950 tests, OK (skipped=10). Pre-push tests passed. CI `check` passed at 6c35a8f.

Limits: no live restore or queue edit; `statebackup.py` and the other support sections are unchanged.

## Catch-up index: units merged to main with no ledger entry (CATCHUP-AVB-21) — November 2, 2026

INCOMPLETE - current as of November 2, 2026, covered 177 of 177 merged units that had no `## ... (<UNIT>)` heading at origin/main 68501fc (PR #278 merge); these are index lines only, not full narratives. Each line gives the unit, its newest merge PR, the merge SHA on main and the branch's own commit subject. No checks were re-run for this index and no CI result is claimed; the PR and its CI record are the evidence. Full per-unit entries (guest/operator effect, checks at the PR head, limits) are still to be written by each unit's owner. Units are grouped by family, and each family heading below names its units in parentheses.

## Catch-up: AV0022 units merged without an entry (AV0022-01, AV0022-02, AV0022-03, AV0022-04, AV0022-06, AV0022-07, AV0022-08, AV0022-13, AV0022-14, AV0022-15, AV0022-16) — November 2, 2026

- AV0022-01 — PR #192, merged 2026-11-01 as 29a0d8089b45cb56f160be3226b61c845017f0d2: [AV0022-01] H10: an upright phone photo with a rotation tag is accepted (fresh Orientation-only EXIF)
- AV0022-02 — PR #152, merged 2026-11-01 as 76554c679b732fc3cac53ddf3301f9fcbc1ab203: [AV0022-02] H10: product.add can take a stored photo instead of an image file
- AV0022-03 — PR #209, merged 2026-11-01 as d5e3ba5351fff25fe13cd1fb298e91d1b1a9078a: AV0022-03 H05: pending drafts carry their ops so a correction resends the whole change
- AV0022-04 — PR #216, merged 2026-11-01 as 8f9eab83bebc2a97b087508af0327d5bbabca7e8: AV0022-04 H12: a photo question answered with a new product becomes product.add with that photo
- AV0022-06 — PR #194, merged 2026-11-01 as e8b8574e2365843b9a5db171d74fe8f40c4607f2: [AV0022-06] H16: a yes sent in time still approves after a delay
- AV0022-07 — PR #206, merged 2026-11-01 as 9257731dfb4007b56e0b85d8a50091bc587e1c35: [AV0022-07] H06: a second bare undo drafts the change before, not the undo
- AV0022-08 — PR #218, merged 2026-11-01 as 28900431cfde142b9a5405ad94b02d444784a4c4: [AV0022-08] H17: show <code> repeats a draft's full text and screenshot
- AV0022-13 — PR #154, merged 2026-11-01 as a82b8d2f5062ad64be90e680876073c95f300fc7: [AV0022-13] H13: hours refusals number lines from 1 and say how many were sent
- AV0022-14 — PR #155, merged 2026-11-01 as 1227f0882b327b4459ae7cd9d4a48f2dc7d803a7: [AV0022-14] H19/H21: health --writer names photo copies no product uses (info only)
- AV0022-15 — PR #196, merged 2026-11-01 as 188d3c640fcf637539c1a34eea86a00a7b036768: [AV0022-15] H25: LIMITS.md names hours, message, find and alias limits and upright photos
- AV0022-16 — PR #225, merged 2026-11-02 as 7a4850feb321579c5da5db629f1498fe03589bd7: AV0022-16 H09: interpreter eval set v2, 40 cases (routes, recap, clear, full-op revises, photos, claims)

## Catch-up: AV1537 units merged without an entry (AV1537-16) — November 2, 2026

- AV1537-16 — PR #150, merged 2026-11-01 as 973253d6f515edd7d10816a6f739f7ba629d3f7f: [AV1537-16] Ledger: AV1537-01..15 sections, hass/README lines, ledger checker covers the 15 ids

## Catch-up: AV1737 units merged without an entry (AV1737-16) — November 2, 2026

- AV1737-16 — PR #167, merged 2026-11-01 as fe1edacb1725b91c2c35cf807e2cbe57d7e818c9: [AV1737-16] Ledger: AV1737-01..15 sections, README lines, checker ids

## Catch-up: AV2022 units merged without an entry (AV2022-01, AV2022-02, AV2022-03, AV2022-05, AV2022-06, AV2022-07, AV2022-08, AV2022-09, AV2022-10, AV2022-11, AV2022-12, AV2022-13, AV2022-14) — November 2, 2026

- AV2022-01 — PR #137, merged 2026-11-01 as 41ed9e45641165d1a95d18b92727780e0380782a: [AV2022-01] H05: interpreter prompt lists hikes and route ideas
- AV2022-02 — PR #191, merged 2026-11-01 as 3167b924d4410829b4399a3b92475fbc821fbec9: [AV2022-02] H13: interpreter prompt shows the current store hours and address
- AV2022-03 — PR #195, merged 2026-11-01 as 21e06aed15dd446743fca7f9bdbae3c4eb0c0c11: [AV2022-03] H04: interpreter knows today's Pacific date
- AV2022-05 — PR #140, merged 2026-11-01 as 76990116c47e57f4d0c2eaefdb767d6a86811074: [AV2022-05] H12: a voice note gets a 'please type it' reply
- AV2022-06 — PR #169, merged 2026-11-01 as 341c1469c7d34b8b61112b38774d2d5686927e75: [AV2022-06] H06/H17: history lists the last 5 approved changes only
- AV2022-07 — PR #179, merged 2026-11-01 as ffdf942c079a4a4855e4169892cf831d46702f28: [AV2022-07] H05: "ok" or "go ahead" asks for yes <code>, never approves
- AV2022-08 — PR #184, merged 2026-11-01 as c708a99d5240fae5fe0a849fab258e7272879485: [AV2022-08] H08: owner sender match ignores email case and phone punctuation
- AV2022-09 — PR #141, merged 2026-11-01 as 5370850e8157d594d8c7fbd8f535c75fb484bd8b: [AV2022-09] H10: BlueBubblesPhotos downloads a message's attachments (fake transport)
- AV2022-10 — PR #170, merged 2026-11-01 as dec67f5bfc0466fa7478334a92e7f14b39ebb858: [AV2022-10] H06: maker result check looks at the maker's product card
- AV2022-11 — PR #175, merged 2026-11-01 as 81c130c144bb46961f9a1bdff7d7acb7f0219659: [AV2022-11] H06: completed and cancelled hikes get a real result check
- AV2022-12 — PR #149, merged 2026-11-01 as e4a23a4076aa7725f7f76cab9377e1786121bf41: [AV2022-12] site: a real hike shows its route and trail-information link
- AV2022-13 — PR #193, merged 2026-11-01 as a8879cb6dc088e0a25a84a0baa6b52f1f1ae4594: [AV2022-13] H21: retention report counts approvals and closed memory rows
- AV2022-14 — PR #144, merged 2026-11-01 as 2e80eab13e4d84ad0a30088101b7e50885422c09: [AV2022-14] H25: phone guide for the owner, every quoted command parses

## Catch-up: AVB units merged without an entry (AVB-02, AVB-03, AVB-04, AVB-05, AVB-06, AVB-07, AVB-08, AVB-10, AVB-11, AVB-12, AVB-13, AVB-14, AVB-15, AVB-16, AVB-17, AVB-18, AVB-19, AVB-20, AVB-22, AVB-23, AVB-24, AVB-25) — November 2, 2026

- AVB-02 — PR #204, merged 2026-11-01 as 47b7469dbdb3c4a6336fde8cb9a0aefaf1b1ff78: [AVB-02] H08: ownerChat must be the owner's one-to-one chat
- AVB-03 — PR #207, merged 2026-11-02 as 512d611ff98747d4681a18622b9afb34d835b81e: [AVB-03] H05: a yes sent before a draft existed never approves it
- AVB-04 — PR #205, merged 2026-11-01 as fc3f748c1ba056e7df0997b6cf3b6f57d8028e2c: [AVB-04] H03: maker and source links are real https web addresses
- AVB-05 — PR #210, merged 2026-11-01 as a70035e7d6934eec2b0b8629371bc886c3d72f03: [AVB-05] H04: a hike more than 400 days away asks to check the year
- AVB-06 — PR #214, merged 2026-11-01 as a07af0325c6af3010a26bb87deb6229e6fd2a7d5: [AVB-06] H06: undo re-checks a product it makes active again
- AVB-07 — PR #213, merged 2026-11-01 as 2ca57110a450b4d6e92963fa72d410091488f1cc: [AVB-07] H16: replies held over 10 minutes are sent marked delayed
- AVB-08 — PR #215, merged 2026-11-01 as 355865689990904c9033f95a7d36230ea1803eeb: [AVB-08] H09: negative demo transcript, end to end
- AVB-10 — PR #226, merged 2026-11-02 as 04cf6f9639b01dca4e1ad4fb697526e2067d03cb: [AVB-10] H10: label line names a matching maker and an already-listed product
- AVB-11 — PR #230, merged 2026-11-02 as 495e3369396d07c25a0d564db2cd55fcf58ebd04: [AVB-11] H11: every common audio format gets the voice-note reply
- AVB-12 — PR #217, merged 2026-11-02 as b02fc73dec497d193789329575a1b77aba7247c5: [AVB-12] H12: a photo already on a product opens no new draft
- AVB-13 — PR #219, merged 2026-11-01 as 07758d0134bfa4ce1dc02672d75f438a4abea330: AVB-13: owner-editable home-page intro line (store.set_intro)
- AVB-14 — PR #260, merged 2026-11-02 as a197f64a1db22f62c354e1342cd6e4fef1d16274: [AVB-14] H14: RSVPs back on re-checks the stored capacity
- AVB-15 — PR #220, merged 2026-11-02 as bd8561dda8f5cb0a24c1f251d98bed2ebe9c94b9: [AVB-15] H15: re-sending a saved fact changes nothing
- AVB-16 — PR #261, merged 2026-11-02 as 474052f4cad5ae3858e05f62a9f1beed9fe05256: [AVB-16] H20: backups record the writer worktree's content commit
- AVB-17 — PR #222, merged 2026-11-02 as 19814994a527a9733759c79a8715cfcefd5240e6: [AVB-17] H19: support doc states service and Mac behaviour
- AVB-18 — PR #227, merged 2026-11-02 as c6d119f43728c14a028ffb97db98aa9297f91492: [AVB-18] H23: opt-in policy for narrow automatic changes (unwired)
- AVB-19 — PR #231, merged 2026-11-02 as 374d1f168f91fc60be680a73b66eb96ed7ab016e: [AVB-19] H24: design-change scope checker
- AVB-20 — PR #285, merged 2026-11-02 as c321154ec16fabb1103e75b95ebba3221bd41b42: [AVB-20] standing acceptance run per H id
- AVB-22 — PR #221, merged 2026-11-02 as 98430a45ab243166a3c59494dbde03ed82981fe7: [AVB-22] F07: local post draft from a product photo
- AVB-23 — PR #228, merged 2026-11-02 as e43a1e5e28c45a634408f57e8ff01de7da5ba215: [AVB-23] F04: morning shelf report from confirmed availability
- AVB-24 — PR #232, merged 2026-11-02 as a32d3b4086f4d389678132321d5e5476ff6e6d15: [AVB-24] F03: private price and margin calculator
- AVB-25 — PR #229, merged 2026-11-02 as c12b0a4ef2988ac9476c25aac333f2f00834648e: [AVB-25] catalog filters survive reload and can be shared

## Catch-up: FAV units merged without an entry (FAV-03) — November 2, 2026

- FAV-03 — PR #278, merged 2026-11-02 as 68501fcccbd3e1abd22caf5a415aca674015949a: [FAV-03] H10: fixture_chat --labels/--label-model wire the label reader

## Catch-up: RF0050 units merged without an entry (RF0050-1, RF0050-2, RF0050-3) — November 2, 2026

- RF0050-1 — PR #156, merged 2026-11-01 as b12aabffdf2c4089a60825ac92a0ff33709f7ba7: [RF0050-1] H01: sitegen --check flags a symlinked generated file or folder
- RF0050-2 — PR #160, merged 2026-11-01 as 212a695d9da82554318fa0483f5e96133c84dc0d: [RF0050-2] H19: health refuses a minutes/hours window over 100 years as bad usage
- RF0050-3 — PR #157, merged 2026-11-01 as 3ec572fae990dea43b5e59a52d965ed122e37ac5: [RF0050-3] H02/H06: history survives a record or draft of the wrong shape

## Catch-up: RF0110 units merged without an entry (RF0110-1, RF0110-2, RF0110-3, RF0110-4, RF0110-5) — November 2, 2026

- RF0110-1 — PR #161, merged 2026-11-01 as 65a8bb5824fbf72e1aeaa455b6544cff2b933065: [RF0110-1] H20: verify refuses a backup whose config.json is not an object naming a worktree
- RF0110-2 — PR #162, merged 2026-11-01 as fcd8d4b3ed045a75166bc864d2bfd5e312c63977: [RF0110-2] H01: non-UTF-8 or too-deep content JSON is a ContentError
- RF0110-3 — PR #163, merged 2026-11-01 as 0f8d31bccade1555cb37b011e05dd4e644f3a411: [RF0110-3] H05/H08: loopback URLs refuse port 0
- RF0110-4 — PR #168, merged 2026-11-01 as 39b2602f31d9b6facc22bd164859348b11ace23c: [RF0110-4] H16: inbox status: no negative pending age; clock_behind
- RF0110-5 — PR #172, merged 2026-11-01 as f49051c02ae31f5223a96f7b12adfcf15860480b: [RF0110-5] H06: malformed screenshot checks are a named failed run

## Catch-up: RF0140 units merged without an entry (RF0140-3, RF0140-4, RF0140-5, RF0140-6, RF0140-7) — November 2, 2026

- RF0140-3 — PR #239, merged 2026-11-02 as 234201c2e7c4f41f79339243e331109d1aea2c40: [RF0140-3] F07: social draft refuses unreadable content in JSON
- RF0140-4 — PR #244, merged 2026-11-02 as 42781dffab88ae3d0412d37d0b3d72c893668ae0: [RF0140-4] F07: no free-text hashtags or mentions in a draft
- RF0140-5 — PR #238, merged 2026-11-02 as b563f497feb076590f3babc72850d7307a475b69: [RF0140-5] F04: a shelf check dated after today is named
- RF0140-6 — PR #241, merged 2026-11-02 as 45a0945c303fbd5b8784b8978d53239ac31a06b5: [RF0140-6] H10: attachment guids from BlueBubbles are bounded, unique; non-int totalBytes is shape
- RF0140-7 — PR #240, merged 2026-11-02 as 276df4ab4ff2e039e1c2cb0f20c5e9d329de6ff2: [RF0140-7] H04: route.edit refuses a title another route idea or hike already uses

## Catch-up: RF0250 units merged without an entry (RF0250-1, RF0250-2, RF0250-3, RF0250-4, RF0250-5, RF0250-6) — November 2, 2026

- RF0250-1 — PR #243, merged 2026-11-02 as 4688998cb4a5edd59d10d5d1b6ee37849dcbf053: [RF0250-1] SHOP-2: install records a pre-write read failure naming the site path
- RF0250-2 — PR #242, merged 2026-11-02 as b289fa613e41637c2552b67aa6e8e4651155d359: [RF0250-2] H05: an unencodable request is a failed call, not a crash
- RF0250-3 — PR #245, merged 2026-11-02 as 723a9626512e10fa8af0cb907d137cc0e3cf18cc: [RF0250-3] H03/H05: a denied maker is not a named maker
- RF0250-4 — PR #246, merged 2026-11-02 as 0b56e020b49120c683b049e22e07525dc998c87a: [RF0250-4] H10: label reader drops barcodes, prices and bare sizes as name/brand
- RF0250-5 — PR #258, merged 2026-11-02 as 96a7c3ebc09e7608eb5e8f258329e8be9e1bdfdd: [RF0250-5] H21: retention report counts web copies without an original (webOrphans)
- RF0250-6 — PR #247, merged 2026-11-02 as febdb181a718a51329fd9465b7ca9e2e31ece44f: [RF0250-6] H09: eval replies file is owner-only and written whole

## Catch-up: RF0310 units merged without an entry (RF0310-1, RF0310-2, RF0310-3, RF0310-4, RF0310-5, RF0310-6) — November 2, 2026

- RF0310-1 — PR #249, merged 2026-11-02 as 27d7718d107404af0df4f135c4b8f0dbcb9f6491: [RF0310-1] H13: hours and address need real words
- RF0310-2 — PR #248, merged 2026-11-02 as c3dc86ad1aabbd487869c57b9caec7d7bff0e501: [RF0310-2] H10: placeholder alt text with an article or number is refused
- RF0310-3 — PR #255, merged 2026-11-02 as 155f5381de2b418a17027588375f08c8d911599e: RF0310-3 H10: an unreadable site photo is a refusal, not an io-error
- RF0310-4 — PR #250, merged 2026-11-02 as 3932dba14868965b152b1061646424a0700ad6cc: [RF0310-4] H15: memory text refuses hidden and direction characters
- RF0310-5 — PR #251, merged 2026-11-02 as fa897f390f16b76d6a64655d5a18d584956d9701: [RF0310-5] H06: undo refuses a misshaped stored hike before as record is malformed
- RF0310-6 — PR #257, merged 2026-11-02 as 49e783426925e800b177fb8c008acf4fc53f109a: [RF0310-6] H06/H10: restoring a product checks its image like setting one

## Catch-up: RF0420 units merged without an entry (RF0420-11, RF0420-12) — November 2, 2026

- RF0420-11 — PR #252, merged 2026-11-02 as 83afeafd44143d742249a42cd7cd19f3cfd6947c: [RF0420-11] margins: plain ASCII numbers only (underscores, non-ASCII digits, leading + refused naming the field)
- RF0420-12 — PR #253, merged 2026-11-02 as 75888cb5da3d2c3dd8eb87e91fbeaa8ee8fa97d6: [RF0420-12] design check: only plain files on the design surface

## Catch-up: RF0450 units merged without an entry (RF0450-12) — November 2, 2026

- RF0450-12 — PR #254, merged 2026-11-02 as 25bd4f9944fa3638c764b2ce92574c2c0e11cd5a: [RF0450-12] H10: a short photo download is size-mismatch; message guid control chars refused

## Catch-up: RF0550 units merged without an entry (RF0550-1, RF0550-2, RF0550-3, RF0550-4, RF0550-5) — November 2, 2026

- RF0550-1 — PR #256, merged 2026-11-02 as 40ac5623e6d711d32494249e3e7dc35fd77b26e4: [RF0550-1] H06: screenshots written whole via temp+rename, never through a link
- RF0550-2 — PR #266, merged 2026-11-02 as 97160ec2899f8294d217f17534b175e03c18b516: [RF0550-2] H06: a damaged change record is an unreadable preview target, never a crash
- RF0550-3 — PR #259, merged 2026-11-02 as ef207d2e940f2395ace8c0dce990be9fb15eaca3: [RF0550-3] SHOP-4: an approved change is not 'waiting for your OK'
- RF0550-4 — PR #262, merged 2026-11-02 as f2919de67845ad277e1575922505850231a69459: [RF0550-4] H09: eval cases that can never be scored are refused by line
- RF0550-5 — PR #264, merged 2026-11-02 as 840d5f856dfad46dab5e70511c07a9851e28dd54: [RF0550-5] H24: design check diffs from the merge base

## Catch-up: RF0620 units merged without an entry (RF0620-1, RF0620-2, RF0620-3, RF0620-4, RF0620-5) — November 2, 2026

- RF0620-1 — PR #263, merged 2026-11-02 as da6e2656b73a189cd193bf24dee0e9e27ac74556: [RF0620-1] morning report: misshaped product records named, exit 1
- RF0620-2 — PR #265, merged 2026-11-02 as 28a345585d8a65f09b1c97f518cbf4160165d75a: [RF0620-2] confirm_selection: a check stale on arrival is refused
- RF0620-3 — PR #269, merged 2026-11-02 as 68c7f1d984dd3506e13d79160d89b3edb46ae633: [RF0620-3] store ops: a spacing-only change is 'already says that'
- RF0620-4 — PR #268, merged 2026-11-02 as feebb89301c5a974433140b037be5f538373865b: [RF0620-4] label reader: never offers text the catalog refuses
- RF0620-5 — PR #267, merged 2026-11-02 as 88d1e23c93bd838feaaa064d1eca7c9b52f9cc97: [RF0620-5] social draft: misshaped products refused; alt text checked

## Catch-up: RF0720 units merged without an entry (RF0720-1, RF0720-2) — November 2, 2026

- RF0720-1 — PR #271, merged 2026-11-02 as 5e3e38764273ca5b90e0b96dd72fa09c41ab2201: [RF0720-1] route.edit: a spacing-only change is 'already says that'
- RF0720-2 — PR #270, merged 2026-11-02 as 79367397ad42e4eb1d25e911b9c351c5280c2225: [RF0720-2] catalog edits: a spacing-only change is unchanged

## Catch-up: RF0740 units merged without an entry (RF0740-1) — November 2, 2026

- RF0740-1 — PR #274, merged 2026-11-02 as ac9515acbeab5b0955773c3393435c65fd77de37: [RF0740-1] sitegen: every target checked before any write

## Catch-up: RF0805 units merged without an entry (RF0805-6, RF0805-7) — November 2, 2026

- RF0805-6 — PR #22, merged 2026-10-31 as ded64a9c454b45e7845f9c2b6b2d0e362dfca9f1: [RF0805-6] H10: private photo original store (no wiring)
- RF0805-7 — PR #46, merged 2026-10-31 as 85223ca4834d7130fa918c4fc193647fdd6a119e: [RF0805-7] H10: metadata-free web copy of a stored photo (no wiring)

## Catch-up: RF0835 units merged without an entry (RF0835-4, RF0835-5) — November 2, 2026

- RF0835-4 — PR #26, merged 2026-10-31 as 2eec03d91a5c931855a42d0d560419427102689c: [RF0835-4] H15: remember / forget / memory chat commands
- RF0835-5 — PR #49, merged 2026-10-31 as 84092357f0a79057b4fb00db8e4c9c53c3295534: [RF0835-5] H12: owner photo/file gets a "not supported yet" reply

## Catch-up: RF0850 units merged without an entry (RF0850-5, RF0850-6) — November 2, 2026

- RF0850-5 — PR #50, merged 2026-10-31 as fc494c3bef657a003cab97cd8194d24ece2071f2: [RF0850-5] H20: backup and restore the photo originals (--media, content-hash verify, --media-into)
- RF0850-6 — PR #24, merged 2026-10-31 as e0e463410c67c35ac5a2ccc7fef89b621991d4da: [RF0850-6] Ledger: H08 prep bridge adapter (BL-AV-3) and QA-script safety (BL-AV-2)

## Catch-up: RF1005 units merged without an entry (RF1005-5, RF1005-6) — November 2, 2026

- RF1005-5 — PR #31, merged 2026-10-31 as 9320452ef330adf23867622576d0adfb6bcdc8e0: [RF1005-5] Ledger: H16, H19, H15, H09, H20 paused, H10 imageAlt sections
- RF1005-6 — PR #48, merged 2026-10-31 as 358c9f65e637ccdee66074a5d2df953c6912ebc8: [RF1005-6] Hass: owner command card checked against the parser

## Catch-up: RF1058 units merged without an entry (RF1058-9, RF1058-10, RF1058-12) — November 2, 2026

- RF1058-9 — PR #44, merged 2026-10-31 as 5072a833717b163e97ee4a6b1e9e45cf04b7d414: [RF1058-9] H19: health verifies the newest backup
- RF1058-10 — PR #45, merged 2026-10-31 as e50279a42307f2e8813240e07f04129db90bce67: [RF1058-10] H13: preview checks a desktop-width page too
- RF1058-12 — PR #35, merged 2026-10-31 as ba546cb97294e474ef9b1a632ec0dbf7f73b1b1a: [RF1058-12] Ledger: H17 support path, H16 fixture_chat --queue, H20 inbox backup

## Catch-up: RF1105 units merged without an entry (RF1105-12) — November 2, 2026

- RF1105-12 — PR #38, merged 2026-10-31 as d2af3b7b0d44a437d8202377e6fcdc25316e3f93: [RF1105-12] H21: test that no private runtime file is tracked

## Catch-up: RF1120 units merged without an entry (RF1120-8) — November 2, 2026

- RF1120-8 — PR #56, merged 2026-10-31 as f2576fee25132a3704300895ee49e98ec022946f: [RF1120-8] Ledger: bridge nonce pruning, output hygiene, editor/sitegen io errors, fixture line check, backup list

## Catch-up: RF1150 units merged without an entry (RF1150-8, RF1150-9) — November 2, 2026

- RF1150-8 — PR #55, merged 2026-10-31 as 2206cff1bb7cf7c6e82cffd4910296dc7fbf9fe5: [RF1150-8] H19: health --writer reports writer worktree problems apply would refuse
- RF1150-9 — PR #59, merged 2026-10-31 as 5332f829dbee67c966afc79d38d7a1074a5e4e76: [RF1150-9] H03: product and maker add refuse a duplicate name (candidate; blocked on test_product_alt conflict)

## Catch-up: RF1200 units merged without an entry (RF1200-3, RF1200-4, RF1200-7, RF1200-8) — November 2, 2026

- RF1200-3 — PR #41, merged 2026-10-31 as a987a09bfa2a950a78c819e2f88462228808c070: [RF1200-3] H06: undo refuses an unreadable change record
- RF1200-4 — PR #61, merged 2026-10-31 as 17b476e3f070df0a569a4449153b7ab00e70ed99: [RF1200-4] H03: product.edit warns when it removes the Organic badge
- RF1200-7 — PR #42, merged 2026-10-31 as 0d2deff9e4bfd5e9969fc783514a7c6d09eef90d: [RF1200-7] H01/H13: store limits checked by the content validator
- RF1200-8 — PR #62, merged 2026-10-31 as de3f8149f31bbc45c1b6eaf2c32b7dbe3edded48: [RF1200-8] Ledger: health --seen, atomic backup, RSVP capacity/warnings/status, picture replies

## Catch-up: RF1210 units merged without an entry (RF1210-5) — November 2, 2026

- RF1210-5 — PR #52, merged 2026-10-31 as 8e72326e15e587dc8030c2bc390922224148bf2d: [RF1210-5] H06: preview overlay never writes through the assets link

## Catch-up: RF1230 units merged without an entry (RF1230-8, RF1230-9, RF1230-11) — November 2, 2026

- RF1230-8 — PR #60, merged 2026-10-31 as a1dc396e8bb3d545c98949cba3ee266ede32dd50: [RF1230-8] H16: an unreadable queued message is marked unreadable; the drain continues
- RF1230-9 — PR #66, merged 2026-10-31 as 983ddd9e13b133073e63a13cb64a9270194d786f: [RF1230-9] H02: image argument refuses a link or a path outside the site folder (candidate; breaks harness-linked assets)
- RF1230-11 — PR #64, merged 2026-10-31 as c424d897951a49037b231919b138dc3c4cb742bb: [RF1230-11] H19: health reports inbound messages dropped as unreadable (inbox-unreadable)

## Catch-up: RF1239 units merged without an entry (RF1239-3) — November 2, 2026

- RF1239-3 — PR #57, merged 2026-10-31 as e87ca28e1a38469dcf810c8297fc6f8b784b1613: [RF1239-3] H04: hike ids keep accented letters as plain letters

## Catch-up: RF1240 units merged without an entry (RF1240-4, RF1240-5, RF1240-9) — November 2, 2026

- RF1240-4 — PR #65, merged 2026-10-31 as 3a13e27edd00a91b121263d8b4218005ee7f8286: [RF1240-4] H04: moving a hike warns about confirmed guests
- RF1240-5 — PR #69, merged 2026-10-31 as 9bdcad4ead577caa67369674f14ff86a5b6a4315: [RF1240-5] H04: capacity with RSVPs off is named in the proposal
- RF1240-9 — PR #63, merged 2026-10-31 as 6a5328b8c15b817beb94466b4ea7137a0208c885: [RF1240-9] H01: generated writes refuse a linked folder

## Catch-up: RF1300 units merged without an entry (RF1300-9, RF1300-10, RF1300-11, RF1300-12) — November 2, 2026

- RF1300-9 — PR #67, merged 2026-10-31 as 92e4c2d941d9ff0f794f657fbb7d2c921b17ccef: [RF1300-9] H01: event startsAt offset must be Pacific time at that moment
- RF1300-10 — PR #80, merged 2026-10-31 as a82ab1405bcb22770eed8c577c0a58c8677cd370: [RF1300-10] H01: content text refuses control, zero-width and direction characters
- RF1300-11 — PR #68, merged 2026-10-31 as 7ae191d31c6dcbb5dbe048e93b80f79d3837cfb5: [RF1300-11] H03: edits skip unchanged fields; an edit that changes nothing is refused by name
- RF1300-12 — PR #71, merged 2026-10-31 as 7b131182f18a57ee02bc1c45e4fcb812d0b459ac: [RF1300-12] H03: lookup ignores accents and curly apostrophes

## Catch-up: RF1500 units merged without an entry (RF1500-9, RF1500-10, RF1500-11, RF1500-12, RF1500-13) — November 2, 2026

- RF1500-9 — PR #164, merged 2026-11-01 as ea74aef7aaf648610da0b707d094c72d79f70630: [RF1500-9] H06: history --limit must be 1 to 500
- RF1500-10 — PR #165, merged 2026-11-01 as 04bbcb9aef253c41bac91ae429de4794705b6f1a: [RF1500-10] H06/H17: show names a wrong-shape record unreadable
- RF1500-11 — PR #171, merged 2026-11-01 as 9d361151ddd425c663043c09f97d13e1786afaae: RF1500-11 H10: label reader drops placeholder answers and a brand that only echoes the name
- RF1500-12 — PR #173, merged 2026-11-01 as 8764e8fbf3571c0628333fe0affa767225b35dcd: [RF1500-12] H10/H19: media verify checks sidecar time, source and byte type
- RF1500-13 — PR #174, merged 2026-11-01 as 3eb86551f9c950e165ddc2441b4d9ba14da240c7: [RF1500-13] H08/H10: photo source timeout must be 1-120 seconds

## Catch-up: RF1510 units merged without an entry (RF1510-10, RF1510-11, RF1510-12) — November 2, 2026

- RF1510-10 — PR #176, merged 2026-11-01 as 538906f584a0ff5068009e61b6dd61dfa5e9d639: [RF1510-10] H16: inbox status refuses a linked or non-regular queue file
- RF1510-11 — PR #177, merged 2026-11-01 as 5df72221693c98cebdff157de81ecf43fb87b482: [RF1510-11] H15: memory history refuses a linked conversation file
- RF1510-12 — PR #178, merged 2026-11-01 as f29be6de1a3c5fb754f3f2040353aea96380412c: [RF1510-12] H09: fixture_chat input errors name the flag, not the path

## Catch-up: RF1520 units merged without an entry (RF1520-8, RF1520-9, RF1520-10, RF1520-11, RF1520-12) — November 2, 2026

- RF1520-8 — PR #180, merged 2026-11-01 as eae5c570e392f44a13c44fee31aa6d9ba5f66a05: [RF1520-8] H16: deeply nested inbound JSON is rejected, not a crash
- RF1520-9 — PR #166, merged 2026-11-01 as bc13a81209920ca996cef49804488b66620e70cb: [RF1520-9] Refuse unsafe conversation database files
- RF1520-10 — PR #181, merged 2026-11-01 as 5592411bda1d32c2ccd3af5f932fe361001c4210: [RF1520-10] H06: undo refuses a too-deep record cleanly
- RF1520-11 — PR #182, merged 2026-11-01 as 0907e4769616ad68a1d6fb89e86cc704275e855e: [RF1520-11] H16: inbox queue file is never opened through a link
- RF1520-12 — PR #185, merged 2026-11-01 as 87793ee193bd42d07e131c30b51c4b855cbeedfc: [RF1520-12] H19: health names a linked state database (state-db), never opens it

## Catch-up: RF1650 units merged without an entry (RF1650-1, RF1650-2, RF1650-3, RF1650-5, RF1650-8, RF1650-12) — November 2, 2026

- RF1650-1 — PR #92, merged 2026-10-31 as a808bd1d31247cbcdf66be83f1373d3b65d10ea1: [RF1650-1] H04: route.edit changes a route idea's text (id, status, source locked)
- RF1650-2 — PR #143, merged 2026-11-01 as 8584d68ca2383e68a563ddaa063548980663f3a9: [RF1650-2] H15: owner-approved memory source must name an applied, not-undone change
- RF1650-3 — PR #104, merged 2026-10-31 as df99c97c6abc286587ba5523f4b96c99b6c69ed9: [RF1650-3] H06: undo of an undo is refused with a plain reason
- RF1650-5 — PR #101, merged 2026-10-31 as bd2944001349f5717b4805b296e2766ccc96e6dc: [RF1650-5] H10: photo originals need a real, zoned received time
- RF1650-8 — PR #107, merged 2026-10-31 as dea25e3b8d1314f6231dcf80ca7063c6edad87d1: [RF1650-8] site search: accents and curly apostrophes no longer hide products
- RF1650-12 — PR #105, merged 2026-10-31 as 8743826d6987b1c2c98a35dd4a04d183901238de: [RF1650-12] H19: health names a long pause (paused-long) + SUPPORT.md

## Catch-up: RF1710 units merged without an entry (RF1710-1, RF1710-2, RF1710-3, RF1710-4, RF1710-5, RF1710-6) — November 2, 2026

- RF1710-1 — PR #109, merged 2026-10-31 as cb771c16531125593359cf4deb3655f7a1dd615a: [RF1710-1] H20: statebackup diff OLD NEW names what changed between two backups
- RF1710-2 — PR #106, merged 2026-10-31 as e3471acceaf4fdbbdb8a673aa90677a967e43622: [RF1710-2] H10: media verify checks the private photo store (read-only)
- RF1710-3 — PR #110, merged 2026-10-31 as 97413d91c135ebfaf5bbc0462517872eb2c04352: [RF1710-3] H16: inbox status shows queue counts (read-only)
- RF1710-4 — PR #112, merged 2026-10-31 as 55b70914b6b53d4112176feea618c97c71f45d21: [RF1710-4] H15: memory.py history shows the audit trail of owner memory (read-only)
- RF1710-5 — PR #108, merged 2026-10-31 as 90c2c6b2cb6002becaad258e5497a07d0019672f: [RF1710-5] H19: health reports broken owner-memory rules (memory-invariant, count only)
- RF1710-6 — PR #118, merged 2026-10-31 as c28b394c36bce935d1d2f3b08319867a9d7662e8: [RF1710-6] H19: health --media reports a damaged photo store (media-store, count only)

## Catch-up: RF1720 units merged without an entry (RF1720-4) — November 2, 2026

- RF1720-4 — PR #120, merged 2026-10-31 as e4a8e4946ab4d902e0754f27b7f9f9f3e17e3a32: [RF1720-4] Ledger: RF1720-1..3 sections

## Catch-up: RF1730 units merged without an entry (RF1730-4) — November 2, 2026

- RF1730-4 — PR #125, merged 2026-11-01 as 83f595774e486f9cfa6ca533526ceedb269fffc3: [RF1730-4] Ledger: RF1730-1..3 sections

## Catch-up: RF1750 units merged without an entry (RF1750-1, RF1750-2, RF1750-3, RF1750-4) — November 2, 2026

- RF1750-1 — PR #186, merged 2026-11-01 as b98e73fbda5e41664969b447e52c5d6203aa3be8: [RF1750-1] H06/H17: a wrong-shape install entry is named, never a traceback
- RF1750-2 — PR #187, merged 2026-11-01 as 3da11bb017a59538de8ba4b5eec48527ab67e418: [RF1750-2] SHOP-2: install refuses by name on an unreadable change record
- RF1750-3 — PR #183, merged 2026-11-01 as 697370b4348394320017795dadabea9f6f911072: [RF1750-3] H21: retention refuses a database that is not a regular file
- RF1750-4 — PR #189, merged 2026-11-01 as a0ef8e4c75cdc58b26ebb6f2a0759e255db5e541: [RF1750-4] SHOP-4: a zone-less install time is an unknown time

## Catch-up: RF1800 units merged without an entry (RF1800-1) — November 2, 2026

- RF1800-1 — PR #190, merged 2026-11-01 as a14566096946cd3107ebc04bfba22476754bca8c: [RF1800-1] H06: undo reads only regular, non-link change and draft records

## Catch-up: RF1910 units merged without an entry (RF1910-1, RF1910-2) — November 2, 2026

- RF1910-1 — PR #188, merged 2026-11-01 as bfa0b272a68a3a48b18ec4ad1d863be87cdc9b6e: [RF1910-1] H20: state config is read only as a regular file with a worktree
- RF1910-2 — PR #200, merged 2026-11-01 as 0a7174fae1fcb77d45c14c657d0678b075df9d54: [RF1910-2] H08: service settings read only from a regular config file

## Catch-up: RF1920 units merged without an entry (RF1920-1, RF1920-2, RF1920-3, RF1920-4, RF1920-5, RF1920-6, RF1920-7, RF1920-8, RF1920-9) — November 2, 2026

- RF1920-1 — PR #198, merged 2026-11-01 as 062008c226feafb16edfc0e5b1f0a9d267820c39: [RF1920-1] H16/H20: writer lock is opened only as a regular file
- RF1920-2 — PR #197, merged 2026-11-01 as 16bb7947875b55f8cff76ef260742465ce200ad4: [RF1920-2] H21: retention sidecar reads are bounded and never crash
- RF1920-3 — PR #199, merged 2026-11-01 as be14d4fec111353f3d6866baaa2986b2e3c227c8: [RF1920-3] H19/H20: backup manifest reads never hang or crash
- RF1920-4 — PR #201, merged 2026-11-01 as 3a6a546df7fbc1462f06353822e0bd58f7d9ea2c: [RF1920-4] too-deep makers.json/community.json is unreadable, never a RecursionError
- RF1920-5 — PR #202, merged 2026-11-01 as f6175003bfefe888e3b93dbf546312ee16f8cb69: [RF1920-5] H05/H09: prepare refuses deep or huge requests cleanly
- RF1920-6 — PR #203, merged 2026-11-01 as b742e82d8f5b440bb144dc9831f6dee376322566: [RF1920-6] media verify: oversize or too-deep sidecar is 'sidecar invalid'; _existing opens O_NONBLOCK + fstat
- RF1920-7 — PR #211, merged 2026-11-01 as 5f0c8098dedd32c9218656743f4df752ea5d5475: [RF1920-7] H16: inbox status never prints or crashes on a bad start_at
- RF1920-8 — PR #208, merged 2026-11-01 as 0c01867fde4f2bf7a94651e6d850eff57113a140: [RF1920-8] H15: memory history prints only text cells; a BLOB or number key, kind, date or value is 'unreadable'
- RF1920-9 — PR #212, merged 2026-11-01 as 0179355f21abf51c2caa393ebc32caa60776c547: [RF1920-9] H19: seen-file read is bounded and never follows a swap

## Catch-up: RF2020 units merged without an entry (RF2020-1) — November 2, 2026

- RF2020-1 — PR #132, merged 2026-11-01 as 549c9e189a53358dd872a4ab93b0d48a51e96e6e: [RF2020-1] claims: ask about grade, process and diet claims the owner did not say

## Catch-up: RF2030 units merged without an entry (RF2030-4, RF2030-5, RF2030-6, RF2030-7) — November 2, 2026

- RF2030-4 — PR #139, merged 2026-11-01 as fd37d0df1b588ca8e1c9575489eab05a31b40c8c: [RF2030-4] claims: a negated owner word is not a stated claim
- RF2030-5 — PR #146, merged 2026-11-01 as 0ac16c3bfebdda8a598c77293562b6a533422ee9: [RF2030-5] claims: list-of-text fields (store hours lines) are checked like text fields
- RF2030-6 — PR #135, merged 2026-11-01 as 51885699ce2653e831726bb9cacd157f8150ed71: [RF2030-6] retention: --days/--now reaching before year 1 is bad usage (exit 2)
- RF2030-7 — PR #138, merged 2026-11-01 as 3cf1223afb729674c867cfb1490b78272e084103: [RF2030-7] interpret check: more than 20 changes asks the owner to split them

## Catch-up: RF2310 units merged without an entry (RF2310-11) — November 2, 2026

- RF2310-11 — PR #235, merged 2026-11-02 as 748a6fbfa91276b14544cccdfc20bb39198725d3: [RF2310-11] H14: hike capacity has a sane ceiling (MAX_EVENT_CAPACITY = 1000)

## Catch-up: RF2320 units merged without an entry (RF2320-10, RF2320-11) — November 2, 2026

- RF2320-10 — PR #234, merged 2026-11-02 as 78480b6aa7fae3f98c95b52c4a4c92d789dc7fd1: [RF2320-10] owner answers: damaged install and queue values read as unknown
- RF2320-11 — PR #233, merged 2026-11-02 as 78cbefd962f556b428ae20463adc330110146c71: [RF2320-11] receiver: envelopes over 64 KiB rejected before parsing

## Catch-up: RF2330 units merged without an entry (RF2330-9) — November 2, 2026

- RF2330-9 — PR #236, merged 2026-11-02 as 8abd941253479ae7b2a29a7f715092b1933a7bd3: [RF2330-9] H10: screenshot and app default names and links are not imageAlt

## Catch-up: SHOP units merged without an entry (SHOP-1, SHOP-2, SHOP-3, SHOP-4) — November 2, 2026

- SHOP-1 — PR #148, merged 2026-11-01 as efc46d8a39cd8ce928042c26b1a081ca9eec45f1: [SHOP-1] catalog shows when Michael last checked the selection and per-item availability
- SHOP-2 — PR #147, merged 2026-11-01 as 47753fcd71c239d3de0e29e2430909e404e991fc: [SHOP-2] install an applied change into the running site (hass/install.py, editor install verb)
- SHOP-3 — PR #151, merged 2026-11-01 as eca8b8bd6482d828cb4aea51592470c906eb07fa: [SHOP-3] inbound receiver up to the live connection: sealed envelope -> draft for approval on fixtures; CONNECT.md lists what G must do
- SHOP-4 — PR #159, merged 2026-11-01 as a04821029723d2bbc67e8364ff97d08599d1e2f9: [SHOP-4] owner answers: did it work?, stop changes, history and recovery say where the change is now

## H04 route.edit corrects a route idea's wording (RF1650-1) — October 31, 2026

Branch rb/rf1650-1 from origin/main b75fd83 (RF1650-1, PR #92: head 469331d, merged as a808bd1d31247cbcdf66be83f1373d3b65d10ea1). For Michael: `route.edit` changes the wording of a route idea (title, place, character, distance, difficulty, elevation, elevationLabel, duration, routeType, terrain, description) through the usual draft and approval, and `undo` puts the old text back. The id, status, RSVPs and source links of a route idea are not editable (they are not arguments, so the request is `invalid`). Refused: an unknown id, a real hike id (`use hike.update`), values that already match (`already says that`); no field given asks for details. `hass/ops/routes.py`; added `hass/tests/test_route_edit.py`.

Checks at PR head 469331d (recorded in PR #92): `python3 -m unittest hass.tests.test_route_edit hass.tests.test_hike_ops hass.tests.test_undo hass.tests.test_revert_records hass.tests.test_content -v` ran 51 tests, OK. PREPUSH-TESTS PASS.

Limits: no adding or removing route ideas, no turning an idea into a hike, no editing source links, no site script change, no interpreter prompt change.

## H15 an owner-approved memory source must name an applied, not-undone change (RF1650-2) — November 1, 2026

Branch rb/rf1650-2 from origin/main 5370850e (RF1650-2, PR #143: head 6ed6a12, merged as 8584d68ca2383e68a563ddaa063548980663f3a9). For Michael: a remembered or corrected fact with the source `owner-approved:<id>` is stored only when `<id>` looks like `chg-` and 12 hex characters and `<state>/changes/<id>.json` is a regular file (no symlink) whose state is `applied` with no `revertedBy`; anything else is refused with `unverified source` and nothing is written. The change id is kept as `approved_change`. Owner-stated and operator sources are unchanged. `hass/memory.py`; added `hass/tests/test_memory_source.py`; `test_memory.py` and `test_memory_history.py` changed their change-id inputs only (G approved the two-file scope on 2026-11-01).

Checks at PR head 6ed6a12 (recorded in PR #143): `python3 -B -m unittest hass.tests.test_memory_source hass.tests.test_memory hass.tests.test_memory_chat hass.tests.test_memory_history -v` ran 36 tests, OK. PREPUSH-TESTS PASS.

Limits: no chat wiring of approved facts, no alias memory, no retention rule, no schema change.

## H06 undo of an undo is refused with a plain reason (RF1650-3) — October 31, 2026

Branch rb/rf1650-3 (RF1650-3, PR #104: head dfdde7f, merged as df99c97c6abc286587ba5523f4b96c99b6c69ed9). For Michael: `undo` of a change that was itself an undo is refused with `<id> is an undo; to bring the change back, ask for it again`; nothing is drafted and the original stays marked undone. An unreadable, symlinked or malformed draft file is refused as `<id> draft is unreadable`. Every other undo behaves as before. A redo is not offered (ask for the change again). `hass/ops/history.py`; added `hass/tests/test_undo_twice.py`.

Checks at PR head dfdde7f (recorded in PR #104): `python3 -m unittest hass.tests.test_undo_twice hass.tests.test_undo hass.tests.test_revert_records hass.tests.test_conversation -v` ran 38 tests, OK.

Limits: no redo command (a redo is not offered; ask for the change again), `revertedBy` is never cleared, a bare `undo` still picks the same draft, `COMMANDS.md` is unchanged.

## H15 correcting a remembered fact to the same value is refused (RF1650-4) — November 3, 2026

Branch rb/rf1650-4 from origin/main ff87a4c (RF1650-4, PR #340: head b6386d0, merged as 2a13159361bbe35a4aa95f8278c460eea7f1de74). For Michael: `Memory.correct` with exactly the value already remembered raises `already remembered` and writes nothing (no superseded row, no new date); a value that differs only in case or inner spacing still corrects. The alias command catches it and replies `Not saved: already remembered.` (`memory-invalid`). `hass/memory.py`, `hass/conversation.py` (`_alias` only); `hass/tests/test_memory_unchanged.py` extended, and its alias same-target test now expects the refusal instead of an update.

Checks at PR head b6386d0 (recorded in PR #340): `python3 -m unittest hass.tests.test_memory_unchanged hass.tests.test_memory hass.tests.test_memory_chat hass.tests.test_memory_source -v` ran 41 tests, OK. PREPUSH-TESTS NOT-RUN (host busy).

Limits: no value normalisation, `remember` is unchanged, no retention rule, no alias memory change.

## H10 photo originals need a real, zoned received time (RF1650-5) — October 31, 2026

Branch rb/rf1650-5 (RF1650-5, PR #101: head 84fb340, merged as bd2944001349f5717b4805b296e2766ccc96e6dc). For Michael: `media.store_original` refuses a `received_at` that is not a timezone-aware ISO-8601 time (`yesterday`, a date alone, a time with no offset, an empty or non-text value) with `received_at must be a timezone-aware ISO-8601 time`; nothing is created or written. A valid time is stored as given, and a duplicate keeps the first sidecar. `hass/media.py`; added `hass/tests/test_media_time.py`.

Checks at PR head 84fb340 (recorded in PR #101): `python3 -m unittest hass.tests.test_media_time hass.tests.test_media hass.tests.test_media_web hass.tests.test_statebackup_media -v` ran 34 tests, OK.

Limits: existing sidecars are not rewritten, times are not converted to UTC, no retention or deletion, web copies unchanged.

## Site: search finds products despite accents and curly apostrophes (RF1650-8) — October 31, 2026

Branch rb/rf1650-8 from origin/main 422a4a9 (RF1650-8, PR #107: head 53f0b3d929f, merged as dea25e3b8d1314f6231dcf80ca7063c6edad87d1). For guests: the catalog search folds accents and apostrophe shapes and ignores case, so `jalapenos` finds Jalapeños, `chevre` finds Chèvre, and `lion's`, `lion’s` and `lionʼs` all find the two lion’s mane products; `lions` still finds nothing. Brand and category filters, counts and paging are unchanged. `storefront-mockup/shop.js` (one `fold` helper); `storefront-mockup/catalog-only-qa.cjs` adds the assertions.

Checks at PR head 53f0b3d929f (recorded in PR #107): `storefront-mockup/catalog-only-qa.cjs` run with a loopback `community-server.py` exited 0 (the old `shop.js` failed its first new assertion), and the hass unittests ran 765 tests, OK (skipped=5). PREPUSH-TESTS PASS.

Limits: no fuzzy or typo search, no maker-name search, no Hass lookup, the Organic badge rule and layout are unchanged.

## H04 hike.create same-day twin refusal: RF1740-5 is superseded by AV1737-09 (RF1740-5) — November 4, 2026

Nothing was built under RF1740-5 and no PR exists. Its behaviour, `hike.create` refusing a second scheduled hike with the same title on the same Pacific day, already shipped as AV1737-09 (commit b8e2769, merged as 27aa3ef5c1305a752517a276722f2049afd0bdd2; see the AV1737-09 section above). The frozen RF1740-5 design contradicts the merged `hass/tests/test_hike_twin.py`, so building it would have regressed main. The operator closed the RF1740-5 card as superseded on 2026-11-03, and the RF1740-8 acceptance that a `hass/tests/test_hike_create_repeat.py` exists is dropped: that test belongs to the superseded unit and is not created.

Checks: none of its own; the AV1737-09 command stands, `python3 -m unittest hass.tests.test_hike_twin -v`.

Limits: no code, test or behaviour change comes from RF1740-5.

## H04 a bad RSVP party size makes that event's guest count unavailable (RF1740-6) — November 3, 2026

Branch rb/rf1740-6 from origin/main e3602ca (RF1740-6, PR #321: commits af4605a, 75dc1b4, merged as 9a824cda9865182af5f6df74fc9133bada78e083). For Michael: a stored RSVP row whose `party_size` is missing, not a whole number, or under 1 makes that event's guest count unavailable instead of a smaller number. Lowering capacity for that event is refused with `guest count unavailable`, and a cancel carries the `guest count unavailable; check RSVPs before approving` draft warning (the cancel still applies). A bad row on another event does not stop this event being counted. `hass/ops/hikes.py` (`GUEST_QUERY`, new `guest_counts_checked`; `guest_counts` keeps its signature and now raises `ValueError` when any event has a bad row, so every caller says unavailable or unreadable); the query still never selects a name or an email. Added `hass/tests/test_hike_guest_rows.py`.

Checks at PR head 75dc1b4 (recorded in PR #321): `python3 -m unittest hass.tests.test_hike_guest_rows hass.tests.test_hike_guest_warning hass.tests.test_hike_move_warning hass.tests.test_hike_ops -v` ran 32 tests, OK. PREPUSH-TESTS PASS.

Limits: the owner text is unchanged and no existing test was edited; `health` now reports its guest-counts check unreadable for a database holding a bad row (fails closed); no RSVP data is repaired or rewritten.

## H10 product.set_photo refuses a symlinked or non-directory photo folder (RF1740-7) — November 4, 2026

Branch rb/rf1740-7 (RF1740-7, PR #341: head a32fbd3, merged as 96447aa9afd34375e2b7365db527018f6a70cefa). For Michael: `product.set_photo`, and `product.add` with a photo (both go through `photos.install`), refuse with the fixed reply `the site photo folder is unusable` when `assets` or `assets/products` under the site directory is a symlink or not a directory, including a dangling link. The check is an `lstat` of each folder before the site file is read or any asset is queued; nothing is queued and the product is unchanged. `hass/ops/photos.py`; two existing expectations changed (`test_set_photo.py` now expects the new reply, `test_set_photo_site_read.py` expects the two folder lstats first). Added `hass/tests/test_set_photo_folder.py`.

Checks at PR head a32fbd3 (recorded in PR #341): `python3 -m unittest hass.tests.test_set_photo_folder hass.tests.test_set_photo hass.tests.test_undo -v` ran 24 tests, OK.

Limits: missing folders are unchanged (the editor creates them); the media store checks and `editor.py` are unchanged; the reply names no path or sha.

## H16 a wrongly typed queued payload becomes done/unreadable and no longer stalls the inbox (RF0220-10) — November 4, 2026

Branch rb/rf0220-10 from origin/main 8108de8 (RF0220-10). For Michael: a stored message that decodes but has a wrongly typed field (text, sender, chat, kind, received time or provider id not a string; `from_me` not a true/false; `attachments` not a whole number of 0 or more, including null, true/false and decimals) is now marked done as `unreadable` with its payload erased, and the next message is handled in the same drain. Before, a null `attachments` made the handler raise on every drain and held back every later message. `hass/inbox.py` (new private `_decode_payload`, used inside the existing decode catch). Genuine handler errors, including a TypeError or ValueError from a valid message, still propagate and stay retryable; photo retries and history rows are unchanged. Added `hass/tests/test_inbox_payload_types.py` (5 tests, 46 subtests; fail on the old `inbox.py`).

Checks: `python3 -B -m unittest hass.tests.test_inbox_payload_types` ran 5 tests, OK; the wider inbox, retention and receiver test lists are recorded in the PR body.

Limits: fixture data only; no enqueue validation, schema, receiver, status output, retention or conversation code changed; no timestamp parsing or string-content rules added.

## H05/F04 shelf check: words only for the products named in it (AV1102-01) — November 4, 2026

Branch rb/av1102-01 from origin/main dbe7400 (AV1102-01, PR #395, merged as 0c88f376716983fc104f0f77255f8a0491a0b9e7). Each product now carries an internal `available_on` day, never published. `store.confirm_selection` sets the word and the day only for the products it names; the site shows a product's word only when its day is the store check day and that check is fresh (not stale); otherwise it shows `Last confirmed <its day>`, and a product with no valid confirmed word or day shows no label. `product.set_availability` (allowed only after today's check) also sets the word and day, so an unnamed product can show a current word. The morning report counts the rest as not confirmed. `product.set_availability` is refused until today's check exists (G decision, November 3). `hass/content_model.py`, `hass/ops/store.py`, `hass/ops/catalog.py`, `hass/sitegen.py`, `hass/morning_report.py`, `docs/hass/COMMANDS.md`.

Checks at PR head: the PR's Acceptance section records the nine-module command `python3 -B -m unittest hass.tests.test_selection_per_product_day hass.tests.test_selection_checked hass.tests.test_selection_backdate_window hass.tests.test_morning_report hass.tests.test_morning_report_names hass.tests.test_auto_policy hass.tests.test_store_ops hass.tests.test_content hass.tests.test_commands_doc -v`, run from the clone root, with 89 tests passing (OK) at head 61c5e04ed7de13e35b72a95b4856a8c12c85bba7. Its new test file is `hass.tests.test_selection_per_product_day`, and the edited ones are `hass.tests.test_selection_checked`, `hass.tests.test_morning_report` and `hass.tests.test_morning_report_names`; `hass/sitegen.py --check` reported the generated files unchanged.

Limits: no product in the content source carries a word yet, so no generated file changed; the Available today filter, the status shelf line and clearing a word are other units.

## Site: See all from this maker in the catalog (AV1102-02) — November 4, 2026

Branch rb/av1102-02 from origin/main 8eaadd1 (AV1102-02, PR #357, merged as abbc594e9ff2602609593c786c3e0d43ea8ee1e2). For guests: a maker with two or more products gets a `See all N from <name>` button in its Meet the maker panel; it filters the grid to that maker, shows a `From <maker>` chip with `Show everything`, and is kept in the address as `from=<key>` only for a valid maker. A bad `from`, or a link with `?item=`, drops the filter. `storefront-mockup/shop.js`, `storefront-mockup/style.css`, `storefront-mockup/catalog-only-qa.cjs`.

Checks at PR head ce5cb32112d4 (recorded in PR #357): `storefront-mockup/catalog-only-qa.cjs` run against a loopback server exited 0 with no errors, and `python3 -m unittest hass.tests.test_product_alt` ran 9 tests, OK. PREPUSH-TESTS NOT-RUN (host busy).

Limits: the Available today filter, maker pages and the meaning of the brand filter are unchanged.

## Site: Available today filter in the catalog (AV1102-03) — November 4, 2026

Branch rb/av1102-03 (AV1102-03, PR #401, merged as d3c988e2cfb59b252e8776c4bad99eaa5a02b7f9). For guests: an Available today checkbox shows only cards whose current word is Available today or Limited, is kept in the address as `avail=1` and restored on reload. It exists only when some card carries a current word; `Last confirmed` cards never count, any other `avail` value is dropped, and `?item=` still wins. `storefront-mockup/shop.js`, `storefront-mockup/style.css`, `storefront-mockup/catalog-only-qa.cjs`; added `hass/tests/test_availability_words_pin.py`.

Checks at PR head (recorded in PR #401): `storefront-mockup/catalog-only-qa.cjs` ran with a loopback server, exit 0 with 170 cards and no errors, and `python3 -m unittest hass.tests.test_availability_words_pin hass.tests.test_selection_checked hass.tests.test_product_alt -v` ran 23 tests, OK.

Limits: the words and the per-product day are other units; the control is inserted after the producer label, not inside it.

## Site: home page shows the next hike line (AV1102-04) — November 3, 2026

Branch rb/av1102-04 (AV1102-04, PR #339: head c4ec917c0a8d, merged as b905e1ce96ae08ef20e104c6b64aec376842c5cb). For guests: with a scheduled upcoming hike the home page shows `Next hike: <weekday>, <month> <day>, <time> - <title>` under the intro, linking to `/hike#upcoming-hikes`; with none, or on a failed or non-JSON community reply, the element stays hidden. Sample hikes never feed it. `hass/templates/index.html`, regenerated `storefront-mockup/index.html`, `storefront-mockup/community.js`, `storefront-mockup/style.css`, `storefront-mockup/community-ui-qa.cjs`.

Checks at PR head c4ec917c0a8d (recorded in PR #339): `storefront-mockup/community-qa.py` ran with `storefront-mockup/community-ui-qa.cjs` against a temporary server and passed, and `python3 -B -m unittest hass.tests.test_generated_targets hass.tests.test_generated_links hass.tests.test_content hass.tests.test_design_check -v` ran 51 tests, OK. PREPUSH-TESTS NOT-RUN (budget).

Limits: no new API, and no RSVP or personal data on the home page; the hike card fields and the calendar link are other units.

## H17/F04 status shows a shelf check line (AV1102-05) — November 3, 2026

Branch rb/av1102-05 (AV1102-05, PR #324, merged as 146b072e884d3b3e21831c2c66fa159af09eaa89). For Michael: `status` (and `did it work?`) shows one `Shelf check: <day>` line after `Changes:`; `not done yet` with no check, a call-to-confirm tail after a week, a clock warning when dated after today, and no line when the content is unreadable. The words come from `morning_report.check_line`, shared with the morning report. `hass/morning_report.py`, `hass/conversation.py`, `docs/hass/COMMANDS.md`; added `hass/tests/test_status_shelf_check.py`.

Checks at PR head: the PR body records no command or count. The new `hass.tests.test_status_shelf_check` is the check, and `hass.tests.test_status_pause` and `hass.tests.test_content_deep_json` had their expected status lines updated.

Limits: read-only and still works while paused; the report command, per-product days and the site wording are other units.

## H05 interpreter prompt lists each product's brand (AV1102-06) — November 4, 2026

Branch rb/av1102-06 (AV1102-06, PR #322: head d7f1f399636d, merged as 06ac45ae7a15948093f67d421c76d098905c6037). For Michael: each product line in the interpreter prompt carries the stored brand (`displayBrand`, else `brand`, else empty), so naming a brand matches one listed product. The brand is quoted like every other value. `hass/interpreter_prompt.py`; added `hass/tests/test_interpreter_prompt_brand.py`.

Checks at PR head d7f1f399636d (recorded in PR #322): `python3 -B -m unittest hass.tests.test_interpreter_prompt_brand hass.tests.test_interpreter_prompt hass.tests.test_interpreter_prompt_shapes hass.tests.test_interpreter_prompt_store hass.tests.test_interpreter_prompt_community hass.tests.test_interpreter_eval -v` ran 49 tests, OK.

Limits: the site's `From the market` label is not copied; the home text lines, the design rule, notes and eval cases are other units.

## H05 interpreter prompt lists the current home-page text (AV1102-07) — November 4, 2026

Branch rb/av1102-07 (AV1102-07, PR #353: head 8bfe3deb371e, merged as 200f56648c4b1ea5a6cdeaa6707ab580c91a5538). For Michael: the prompt's store section now also lists the intro (or the default intro), each headline line, the story and the notice with its last day, so a partial edit can resend the whole value. A wrongly typed field is skipped, never raised. `hass/interpreter_prompt.py` (helper `_home_text_lines`).

Checks at PR head 8bfe3deb371e (recorded in PR #353): `python3 -B -m unittest hass.tests.test_interpreter_prompt_home_text hass.tests.test_interpreter_prompt_store hass.tests.test_interpreter_prompt hass.tests.test_interpreter_prompt_shapes hass.tests.test_interpreter_prompt_community hass.tests.test_interpreter_eval -v` ran 54 tests, OK. PREPUSH-TESTS NOT-RUN (budget).

Limits: no new prompt rule, the byte cap is unchanged, and a notice without a usable last day lists its text only.

## H05 interpreter prompt: design requests are unsupported (AV1102-08) — November 4, 2026

Branch rb/av1102-08 (AV1102-08, PR #361: head 3196d95f51bd, merged as da238f09d2cc5abf30534c4ae2c58012ab00c7f1). For Michael: one last prompt rule answers a request to change layout, colours, fonts, page structure or to add a section or page with the fixed reply `design changes cannot be made by message yet`; words, hours, photos, hikes and route ideas are not design changes. Design changes stay unbuilt: there is no keyword filter and `design_check` stays unwired. `hass/interpreter_prompt.py` (`DESIGN_UNSUPPORTED`).

Checks at PR head 3196d95f51bd (recorded in PR #361): `python3 -B -m unittest hass.tests.test_interpreter_prompt_design hass.tests.test_interpreter_prompt hass.tests.test_interpreter_prompt_shapes hass.tests.test_interpreter_prompt_store hass.tests.test_interpreter_prompt_community hass.tests.test_interpreter_eval hass.tests.test_interpreter_eval_cases hass.tests.test_interpreter_eval_out` ran 68 tests, OK. PREPUSH-TESTS NOT-RUN (busy host).

Limits: `conversation.py` is unchanged; the brand column, home text, notes and scored eval rows are other units.

## H15 saved notes reach the interpreter as preferences (AV1102-09) — November 4, 2026

Branch rb/av1102-09 (AV1102-09, PR #368: head 7f3c97849d7b, merged as 4c123ebbe1335cc5d7549547fe5edff29492fc67). For Michael: the newest 20 saved notes, leaving out aliases, are sent to the interpreter with a request, and only when there is at least one; with none the request is unchanged. A note is never proof of a claim: a new prompt rule says a note never supplies a claim, a date, a time, a price or a quantity, and the claim check still reads only the owner's message, so a claim copied from a note still asks. A missing notes table or a read error sends no notes. `hass/conversation.py`, `hass/interpreter_local.py`, `hass/interpreter_prompt.py`; added `hass/tests/test_interpreter_notes.py`.

Checks at PR head 7f3c97849d7b (recorded in PR #368): `python3 -B -m unittest hass.tests.test_interpreter_notes hass.tests.test_interpreter_local hass.tests.test_interpreter_local_strict hass.tests.test_interpreter_request_encode hass.tests.test_interpreter_today hass.tests.test_interpreter_prompt hass.tests.test_memory hass.tests.test_memory_chat hass.tests.test_memory_alias hass.tests.test_memory_source hass.tests.test_claims hass.tests.test_conversation -v` ran 113 tests, OK. PREPUSH-TESTS NOT-RUN (budget).

Limits: notes are not shown in replies or used in `find`, and no eval rows for notes belong to this unit.

## H09 interpreter eval set v4 (AV1102-10) — November 4, 2026

Branch rb/av1102-10 (AV1102-10, PR #388, merged as 78728cc3110104921f20c8ecba2d850c0527f719). Eight cases (e56 to e63) are appended, so the set has 63 cases. They cover a brand naming one or two products, one headline word, an unclear story fix, two design requests, and two cases with saved notes. `load_cases` accepts an optional list of up to 20 notes and reports a bad one by line number, never by text. The added recorded replies are hand-written scorer fixtures, not a model run. `hass/interpreter_eval.py`; case and reply fixtures; `hass/tests/test_interpreter_eval_cases.py`.

Checks (recorded in PR #388): `python3 -B -m unittest hass.tests.test_interpreter_eval hass.tests.test_interpreter_eval_cases hass.tests.test_interpreter_eval_out hass.tests.test_interpreter_prompt -v` ran 45 tests, OK; scoring gave 63 cases, 60 passed, the same three earlier failures.

Limits: no `--live` run and no model call; scoring rules, exit codes and prompt text are unchanged.

## H17/F04 report adds a Waiting for you block (AV1102-11) — November 4, 2026

Branch rb/av1102-11 (AV1102-11, PR #374: head 1565286126822448710d, merged as 173a346eb642aba0020b9bdc6d86db18eabc4f69). For Michael: `report` adds `Waiting for you:` with the same draft lines `status` shows, then `Photos waiting for details: N`, or `Waiting for you: nothing`. It also follows the line saying the shelf report is unavailable. Read-only, works while paused. `status` shares the new helper `_waiting_lines`. `hass/conversation.py`, `docs/hass/COMMANDS.md`; added `hass/tests/test_report_waiting.py`.

Checks at PR head 1565286126822448710d (recorded in PR #374): `python3 -B -m unittest hass.tests.test_report_waiting hass.tests.test_report_command hass.tests.test_conversation hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_status_pause hass.tests.test_status_photos hass.tests.test_morning_report hass.tests.test_status_shelf_check hass.tests.test_post_command hass.tests.test_find` ran 94 tests, OK. PREPUSH-TESTS NOT-RUN (busy host).

Limits: no stock or sales numbers, no timed push, and `status` output is unchanged.

## F03 margin command in chat (AV1102-12) — November 4, 2026

Branch rb/av1102-12 (AV1102-12, PR #380: head 9bdbdcd7b9b5, merged as 84bf0904a2801280be47f1b2c8cc30e6f8ac30d5). For Michael: `margin <pack cost> for <units> at <margin>%` (optionally `shrink <S>%`) replies with each calculation step. Suggestion only; nothing stored: the reply is a price idea, with no draft, memory, file or usage row and no model call, and it works while paused. A bad input gets `Not calculated:` with the field named, and a malformed margin message gets the usage line. `hass/conversation.py`, `docs/hass/COMMANDS.md`; added `hass/tests/test_margin_chat.py`.

Checks at PR head 9bdbdcd7b9b5 (recorded in PR #380): `python3 -B -m unittest hass.tests.test_margin_chat hass.tests.test_margins hass.tests.test_margins_percent_decimals hass.tests.test_margins_plain_numbers hass.tests.test_margins_price_check hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_conversation` ran 65 tests, OK. PREPUSH-TESTS NOT-RUN (budget).

Limits: supplier costs are not stored, there is no reverse price check in chat, no rounding endings and no price op.

## H25 acceptance map matches main (AV1102-13) — November 3, 2026

Branch rb/av1102-13 (AV1102-13, PR #325: head 1735d11bfabb, merged as 5c1f439e47aef66bbad5f90fc38b396ba2e08a37). `hass/acceptance.py` now maps H23 to `test_auto_policy` and H24 to the three `test_design_check` modules, and lists 12 more existing test modules on H09, H10, H12, H13, H17 and H20; a full run covers 25 ids with 3 not covered (was 5). `hass/tests/test_acceptance_runner.py` pins the new map.

Checks at PR head 1735d11bfabb (recorded in PR #325): `python3 -B -m unittest hass.tests.test_acceptance_runner -v` ran 7 tests, OK. PREPUSH-TESTS PASS.

Limits: H23 stays opt-in and unwired, H24 still has no message path, and acceptance stays local evidence, not a CI job.

## H25 IMPLEMENTATION.md baseline matches main (AV1102-14) — November 4, 2026

Branch rb/av1102-14 (AV1102-14, PR #330: head 2e16d7575e8d, merged as 74e1be361473ce5df8cc80b4fec8a2640cf05772). Docs only: `docs/hass/IMPLEMENTATION.md` now says the listed Hass modules are built and none is connected to the owner's channel, replaces the unchecked service claim with a source check dated November 3, and lists one row per built module. Text from the message flow section on is unchanged.

Checks at PR head 2e16d7575e8d (recorded in PR #330): `python3 -B -m unittest hass.tests.test_limits_doc hass.tests.test_phone_guide hass.tests.test_support_doc hass.tests.test_tracked_private hass.tests.test_commands_doc -v` ran 38 tests, OK. PREPUSH-TESTS NOT-RUN; four browser-based `test_hike_ics` tests failed locally without the CI browser setup and CI decides.

Limits: no feature state changed, the plan sections are untouched, and no row says live, connected or installed.

## H18 owner trial task list proposal (AV1102-15) — November 3, 2026

Branch rb/av1102-15 (AV1102-15, PR #329: head 0cb83e0f01ac, merged as 298ec1c8aa5eec59fa7cd1d8681c445a3bb4d8b2). Docs only: `docs/hass/TRIAL.md` holds a 21-row task table with an example message and what success looks like, a blank record form per task, what counts as done, and what is not in the trial. Proposal only; the trial is not run. Michael and G agree the list. `docs/hass/README.md` links it.

Checks (recorded in PR #329): `python3 -B -m unittest hass.tests.test_limits_doc hass.tests.test_phone_guide hass.tests.test_support_doc hass.tests.test_tracked_private hass.tests.test_commands_doc` ran 38 tests, OK; every operation and command named in the table was checked against the code.

Limits: no trial is run or scheduled, no results are recorded, and later operations such as maker hide and route hide are not yet rows.

## H25 handover steps and open decisions (AV1102-16) — November 3, 2026

Branch rb/av1102-16 (AV1102-16, PR #334: head 90943c7ef9ef, merged as e53c5454aafbe37f80637682c9052116cb43ff47). Docs only: `docs/hass/HANDOVER.md` lists the release steps (acceptance run, backup restore drill, phone guide and limits for Michael, the trial, a private launch only) and an open-decisions table with owners and line-anchored sources; `docs/hass/README.md` links it. It records no decision and claims no step happened.

Checks at PR head 90943c7ef9ef (recorded in PR #334): `python3 -B -m unittest hass.tests.test_limits_doc hass.tests.test_phone_guide hass.tests.test_support_doc hass.tests.test_tracked_private hass.tests.test_commands_doc` ran 38 tests, OK; `python3 -B hass/acceptance.py` summarised 25 ids, 22 pass, 0 fail, 3 not covered. PREPUSH-TESTS NOT-RUN (busy host).

Limits: no decision is made, the drill is not run, and the trial and feature states are other units.

## H10/H12/H16 photo GUIDs with surrogate code points are refused before any URL is built (RF1100-21) — November 5, 2026

Branch rb/rf1100-21 from origin/main a4435ca (RF1100-21). For Michael: a message or attachment GUID holding a lone surrogate code point (U+D800-U+DFFF, which UTF-8 cannot encode) used to escape as an uncaught `UnicodeEncodeError` while the photo URL was built. A direct `BlueBubblesPhotos.fetch` call now raises the fixed `ValueError` before the password file or any transport is touched; a surrogate in the first n attachment GUIDs of the provider metadata is the normal `shape` refusal, raised before any download (even of valid earlier items). `hass/bridge_photos.py` (new private `_valid_guid`, used for both guards; docstring updated). Real non-ASCII text (accents, NBSP, emoji), a JSON-escaped surrogate pair that decodes to one emoji, the 200-code-point limit and attachments after the first n behave as before. Added `hass/tests/test_bridge_photos_unicode.py`.

Checks: `python3 -B -m unittest hass.tests.test_bridge_photos hass.tests.test_bridge_photos_ids hass.tests.test_bridge_photos_size hass.tests.test_bridge_photos_tail hass.tests.test_bridge_photos_unicode hass.tests.test_ledger_rf1120`.

Limits: fixture transports only; `bridge.py`, URL/password policy, duplicate-key and count handling are unchanged. The fixed ValueError text now ends with "or surrogate code points" (the existing size test uses assertIn on an earlier part).

## H20 state and media restore publish with atomic no-replace (RF1100-19) — November 5, 2026

Branch rb/rf1100-19. For Michael: `statebackup restore` and `drill` now publish the restored state and media directories with the same kernel no-replace rename the content restore already used, so a directory created by someone else at that moment (even an empty one) is kept instead of silently replaced. The call fails with the existing one-line error JSON (exit 1), takes back only the state/staging trees it made itself, and leaves the backup untouched. `hass/statebackup.py` (two call replacements); added `hass/tests/test_statebackup_restore_atomic.py` (5 tests; all 5 fail on the old code).

Checks: `python3 -B -m unittest hass.tests.test_statebackup_restore_atomic` ran 5 tests, OK; wider statebackup list in the PR body.

Limits: fixture data only; rollback moves, preflight refusals and wording, the helper and the manifest are unchanged; no lock service or symlink-race redesign.

## H21 retention counts only completed .png screenshots (RF1100-18) — November 5, 2026

Branch rb/rf1100-18 (RF1100-18). For Michael: the read-only retention report counts a screenshot only when it is a regular file whose name ends in lowercase .png; notes, .json, extensionless files, .png.tmp temp files, .PNG, links, FIFOs and folders no longer add to the screenshot files or bytes. `hass/retention.py` (_shots filter); added `hass/tests/test_retention_screenshots.py` (5 tests; 2 fail on the old code).

Checks: `python3 -B -m unittest discover -s hass/tests -t . -p "test_retention*.py"` ran 49 tests, OK.

Limits: nothing is deleted, no retention period is chosen, no image bytes are read, the scan does not recurse, and the report keys and wording are unchanged.

## H10/H19 media verify checks web copies against their safe derivative (RF1100-20) — November 5, 2026

Branch rb/rf1100-20 (RF1100-20). For Michael: `media.py verify` (and `health --media`) now compares each existing private web copy with the metadata-free bytes computed in memory from its hash-valid original. A changed, empty, truncated or metadata-restored web file is one `web content mismatch: <12 hex>` problem; an original the sanitizer refuses with a matching web file is `web unverifiable: <12 hex>`. `hass/media.py` (`verify_store` only); added `hass/tests/test_media_verify_web.py` (8 tests, 4 fail on the old `media.py`). Health still shows only the count.

Checks: `python3 -B -m unittest hass.tests.test_media_verify_web` ran 8 tests, OK; the wider media/health list is recorded in the PR body.

Limits: verification never writes or generates a web copy; a store with no web copy stays healthy; an original already bad is reported once and its web copy is not compared; sanitizer rules and `health.py` are unchanged.

## Site: catalog search matches shelf names and Organic (AV1222-01) — November 5, 2026

Branch rb/av1222-01 (AV1222-01, PR #412, merged as 8c8dace13bf2cd7f15feed8097f08f293af2b97d). For guests: the catalog search also matches each card's shelf name and its Organic badge, so `organic`, `flowers` or `dairy & cheese` find cards; descriptions, the search text cap, the address and the `?q=` restore are unchanged. `storefront-mockup/shop.js`, `storefront-mockup/catalog-only-qa.cjs`.

Checks at PR head: `PLAYWRIGHT_MODULE=$HOME/pw-tools/node_modules/playwright QA_OUT_DIR=<tmp> PREVIEW_URL=<local server> node storefront-mockup/catalog-only-qa.cjs` against a local community server exited 0 with all 170 cards, as recorded in the PR; no Python test pins shop.js. PREPUSH-TESTS NOT-RUN.

Limits: only the shelf name and the Organic badge were added to what search reads; the other filters and the sort are unchanged.

## H06 product result check reads availability and photo (AV1222-02) — November 4, 2026

Branch rb/av1222-02 (AV1222-02, PR #403, merged as 6489f3d9c1a0e3974f8b186dc53c377aa6391119). For Michael: a product change's result check also compares the card's availability word with the record and, after a photo change, the card image with the new image. A failed check reaches him through the existing `check failed` reply. `hass/preview.py`, `hass/screenshot.cjs`, `hass/conversation.py`, `hass/editor.py`.

Checks at PR head: `PLAYWRIGHT_MODULE=$HOME/pw-tools/node_modules/playwright python3 -B -m unittest hass.tests.test_preview_product_checks hass.tests.test_preview hass.tests.test_preview_target_shapes hass.tests.test_preview_checks_shape` ran 29 tests, OK (recorded in PR #403).

Limits: the stale-word rule is not re-implemented (the site's own label function decides); a product with no store check has no availability check; the product page itself is not read.

## H06 store result check reads intro and selection line (AV1222-03) — November 5, 2026

Branch rb/av1222-03 (AV1222-03, PR #407, merged as 8b416bf555b2f326fbcb0a26e5903652295dacf0). For Michael: the store change result check also finds the home-page intro and, after `store.confirm_selection`, the `Selection last checked` line; the failed check is named in the reply. `hass/preview.py`, `hass/screenshot.cjs`, `hass/owner_answers.py`, `hass/conversation.py`.

Checks at PR head: `PLAYWRIGHT_MODULE=$HOME/pw-tools/node_modules/playwright python3 -B -m unittest hass.tests.test_preview_store_checks hass.tests.test_preview_store_address hass.tests.test_preview_target_shapes hass.tests.test_owner_answers hass.tests.test_owner_answers_shapes -v` OK (recorded in PR #407). prepush.py was not run.

Limits: only the intro and the selection line were added; unknown check names are not shown to the owner; the notice check is unchanged.

## H13 store phone (AV1222-04) — November 5, 2026

Branch rb/av1222-04 (AV1222-04, PR #428, merged as 87a5611c72c2c10f5855a86c88722ae5a492a499). For Michael: `store.set_phone` takes a ten-digit US number in any common spacing and the Visit block shows it as a tap-to-call link; the stale selection line then offers the number to call; `store.clear_phone` removes it and undo restores the earlier value; a failed check is named as the phone number. The phone is described here in words and no number is quoted. `hass/ops/store.py`, `hass/content_model.py`, `hass/sitegen.py`, `hass/owner_answers.py`.

Checks at PR head: `PLAYWRIGHT_MODULE=$HOME/pw-tools/node_modules/playwright python3 -B -m unittest hass.tests.test_store_phone hass.tests.test_store_ops hass.tests.test_selection_checked hass.tests.test_content hass.tests.test_interpreter_prompt_store hass.tests.test_preview_target_shapes hass.tests.test_preview_store_checks hass.tests.test_interpreter_prompt_design` ran 89 tests; after the test_content fixture fix, `hass.tests.test_content hass.tests.test_store_phone` ran 31 tests, OK (recorded in PR #428). PREPUSH-TESTS NOT-RUN.

Limits: US numbers only; the demo content has no phone, so the generated pages are unchanged until Michael sets one.

## H06 hike result check reads date, meet and places (AV1222-05) — November 5, 2026

Branch rb/av1222-05 (AV1222-05, PR #440, merged as bc2bf8013e9120b95e4a39ebe854d56b08c6eeb0). For Michael: a scheduled hike's result check compares the card's date line, Meet line, places-left line and the changed meeting fields with the record, not only the title. `hass/preview.py`, `hass/screenshot.cjs`, `hass/tests/test_preview_hike_results.py`.

Checks at PR head: `PLAYWRIGHT_MODULE=$HOME/pw-tools/node_modules/playwright python3 -B -m unittest hass.tests.test_preview_hike_results` ran 19 tests, OK (recorded in PR #440).

Limits: cancelled and completed hikes keep their earlier check; the date format is mirrored from community.js, so a format change there fails the check loudly; `screenshot.cjs` went a few lines over its budget.

## H06 route idea result check (AV1222-06) — November 5, 2026

Branch rb/av1222-06 (AV1222-06, PR #464, merged as ac12687cf00e07c8fd6d892f75a97ca81c22657f). For Michael: a route idea change is checked where /hike shows the route (a linked hike's Route line or the sample invitation); a hidden route needs no place; a route shown nowhere is said in the reply and is not reported as checked. `hass/preview.py`, `hass/screenshot.cjs`, `hass/conversation.py`, `hass/owner_answers.py`.

Checks at PR head: `PLAYWRIGHT_MODULE=$HOME/pw-tools/node_modules/playwright python3 -B -m unittest hass.tests.test_preview_route_results hass.tests.test_preview_target_shapes` ran 23 tests, OK (recorded in PR #464). PREPUSH-TESTS NOT-RUN.

Limits: a route shown nowhere gets no content check; hidden is read from the route's status as it is on main.

## H09 photo demo with the real previewer (AV1222-07) — November 4, 2026

Branch rb/av1222-07 (AV1222-07, PR #408, merged as 867e8d0cb444a672e133fc5ec611f02f1dc3d61b). Test only: the photo demo (photo and caption, draft, yes, undo, yes) runs once through the real Chromium previewer, reading the check results from the captures, not the reply text. `hass/tests/test_demo_browser_photo.py`.

Checks at PR head: `PLAYWRIGHT_MODULE=$HOME/pw-tools/node_modules/playwright python3 -B -m unittest hass.tests.test_demo_browser_photo hass.tests.test_demo_browser hass.tests.test_demo_transcript_photo -v` (recorded in PR #408; the new tests take about 25 s).

Limits: the class skips when `PLAYWRIGHT_MODULE` is unset; the fixture is unchanged; no production code changed.

## H04/H05 interpreter prompt lists scheduled hike details (AV1222-08) — November 4, 2026

Branch rb/av1222-08 (AV1222-08, PR #389, merged as 93b49a409da8bec3fabdbdce3baede86ad29629d). The prompt lists each scheduled hike's meeting point, capacity, bring and access note (at most 12, then an ask-the-owner line), so "also bring sunscreen" can become a whole-text hike.update built from the current value. `hass/interpreter_prompt.py`, `hass/tests/fixtures/interpreter-prompt.txt`.

Checks at PR head 485ed2b: `python3 -B -m unittest hass.tests.test_interpreter_prompt hass.tests.test_interpreter_prompt_community hass.tests.test_interpreter_prompt_shapes hass.tests.test_interpreter_cap hass.tests.test_interpreter_request_encode -v` plus the other prompt tests ran 128 tests, OK (recorded in PR #389). PREPUSH-TESTS NOT-RUN.

Limits: `PROMPT_MAX_BYTES` is not raised, and the worst case with every catalog text at its limit was already over it before this unit; no clock, guest names or RSVP data are in the prompt.

## H09 interpreter eval set v5 (AV1222-09) — November 5, 2026

Branch rb/av1222-09 (AV1222-09, PR #434, merged as d61b69678d4855d2e0e32b61cd7da4440c14d4fd). Six more cases (phone set and clear, short number asks, and whole-text hike.update for bring, access note and meeting point) take the set from 63 to 69; the new events fixture is laid over a copy of the content and never written. `hass/tests/test_interpreter_eval.py` and `hass/tests/test_interpreter_eval_out.py` count pins moved.

Checks at PR head: `python3 -B -m unittest hass.tests.test_interpreter_eval hass.tests.test_interpreter_eval_cases hass.tests.test_interpreter_eval_out -v` ran 42 tests, OK (recorded in PR #434).

Limits: the six reply rows are synthetic and no recorded model run is claimed; it runs without a model.

## F03 saved purchase cost per product (AV1222-10) — November 4, 2026

Branch rb/av1222-10 (AV1222-10, PR #390, merged as aaf7d30981e6d64e08dff51bf5ce7e7d42cd7f84). For Michael: `cost <id>: <pack cost> for <units>` saves a cost per product (a bad field is named; the same cost again changes nothing) and `margin <id> at <M>%` reads it. The cost is private; it is never on the website, and the notes reader skips `cost.` keys so it never reaches the interpreter. No cost is quoted here. `hass/conversation.py`, `docs/hass/COMMANDS.md`.

Checks at PR head b0de00a5: `python3 -B -m unittest hass.tests.test_purchase_cost hass.tests.test_margins hass.tests.test_memory_chat hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_conversation -v` ran 64 tests, OK (recorded in PR #390). PREPUSH-TESTS NOT-RUN.

Limits: the older pack-cost form of margin still works and is unchanged; a generic remember of a cost key is refused.

## F07 post hike command (AV1222-11) — November 4, 2026

Branch rb/av1222-11 (AV1222-11, PR #399, merged as ddaad23f7880697c0e0c92cc78b50c6562517242). For Michael: `post hike <id>` replies with the hike's social draft in chat. Draft only; nothing is posted, nothing is stored, and it works while paused. `hass/conversation.py`, `hass/tests/test_post_hike_command.py`.

Checks at PR head: `python3 -B -m unittest hass.tests.test_post_hike_command hass.tests.test_post_command hass.tests.test_social_draft_hike hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_conversation` ran 55 tests, OK (recorded in PR #399).

Limits: `hass/social_draft.py` is unchanged; the help line is shorter than the spec wording because of the 70-character help limit.

## H25 phone guide and limits for phone, cost and post hike (AV1222-12) — November 5, 2026

Branch rb/av1222-12 (AV1222-12, PR #438, merged as 72dbe74448537346c4fcc81768ec034267177ca8). Docs and constants: `docs/hass/PHONE_GUIDE.md` explains the store phone, `post hike` and the private prices pair; `docs/hass/LIMITS.md` gains a Phone and prices section tied to code constants (`PHONE_DIGITS`, the pack cost maximum and the unit range).

Checks at PR head 743ca102c01a: `python3 -B -m unittest hass.tests.test_phone_guide hass.tests.test_limits_doc hass.tests.test_margins hass.tests.test_store_phone` ran 41 tests, OK, 2 skipped (recorded in PR #438). PREPUSH-TESTS NOT-RUN.

Limits: the guide keeps its 110-line cap and section order; no limit value or error message changed.

## H03/H17 hidden command lists hidden products and makers (AV1222-13) — November 4, 2026

Branch rb/av1222-13 (AV1222-13, PR #409, merged as ab2f6cd318411dcbdfb48485815a048d1b2a2c4a). For Michael: `hidden` lists hidden products by id and hidden makers by key (at most 20 lines, then a count of the rest) with the restore line, or says nothing is hidden. Read-only, works while paused. `hass/conversation.py`, `hass/tests/test_hidden_command.py`.

Checks at PR head e123c6dd: `python3 -B -m unittest hass.tests.test_hidden_command hass.tests.test_find hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_conversation` ran 48 tests, OK (recorded in PR #409). prepush.py not run.

Limits: held products and visible makers never appear; the list reads stored text without the full content validation, so a name with markup shows as stored.

## Site: Clear filters button in the catalog (AV1222-14) — November 5, 2026

Branch rb/av1222-14 (AV1222-14, PR #425, merged as 8a53dcfd861791204a26ca2f22cd0244eed8d285). For guests: a Clear filters button shows whenever a shelf, search, maker, from or available filter is set (also in the empty state); it resets all five, drops them from the address (other parameters and the hash stay) and returns focus to the search box. `storefront-mockup/shop.js`, `storefront-mockup/style.css`, regenerated `storefront-mockup/index.html`, `storefront-mockup/catalog-only-qa.cjs`.

Checks at PR head: `node storefront-mockup/catalog-only-qa.cjs` against a local server exited 0 with all 170 cards, and `python3 -B -m unittest hass.tests.test_catalog_clear_filters hass.tests.test_selection_checked hass.tests.test_generated_targets -v` ran 21 tests, OK (recorded in PR #425). PREPUSH-TESTS NOT-RUN.

Limits: the hidden button keeps its space so desktop does not shift; no other filter behaviour changed.

## Site: drop dead commerce CSS (AV1222-15) — November 5, 2026

Branch rb/av1222-15 (AV1222-15, PR #432, merged as 02465a63ddbba690f2d67d9431fd11ed891d2344). No visible change: `storefront-mockup/style.css` loses only rules whose every selector matches nothing the site builds (merch, weekly, box, price, cart and quantity classes); no live selector was touched. New `hass/tests/test_style_no_commerce.py` fails if they return.

Checks at PR head: `python3 -B -m unittest hass.tests.test_style_no_commerce hass.tests.test_design_check hass.tests.test_selection_checked hass.tests.test_generated_targets` ran 40 tests, OK; `storefront-mockup/catalog-only-qa.cjs` exited 0 (recorded in PR #432). The new test was red on the old style.css.

Limits: no before/after screenshots were taken; the design checker flags only the new test file; archive and QA scripts are untouched.

## H04/H05 interpreter prompt lists hikes and route ideas (AV2022-01) — November 1, 2026

Branch rb/av2022-01 (AV2022-01, PR #137, merged as 41ed9e45641165d1a95d18b92727780e0380782a). The prompt includes hikes and undated route ideas, never RSVP counts or guest data.

Checks at PR head 9d90307a: `python3 -m unittest discover -s hass/tests -t . -v` — 978 tests in 316.516s, OK (skipped=10) (recorded in PR #137). Discovery uses the default pattern `-p 'test*.py'`.

Limits: Store hours/address, today's date, the club block, live model calls and interpret_check id validation are outside this unit.

## H13/H05 interpreter prompt shows current hours and address (AV2022-02) — November 1, 2026

Branch rb/av2022-02 (AV2022-02, PR #191, merged as 3167b924d4410829b4399a3b92475fbc821fbec9). The prompt reads current store hours and address.

Checks at PR head 5ddd021a: `python3 -m unittest discover -s hass/tests -t . -v` — 1338 tests in 832.405s, OK (skipped=21) (recorded in PR #191). Discovery uses the default pattern `-p 'test*.py'`.

Limits: No per-line store.set_hours operation, shop-name or club-organizer/sender change, or live model call; the quoted full run preceded the final main merge, after which 16 prompt tests passed.

## H04/H05 interpreter knows today's Pacific date (AV2022-03) — November 1, 2026

Branch rb/av2022-03 (AV2022-03, PR #195, merged as 21e06aed15dd446743fca7f9bdbae3c4eb0c0c11). The prompt supplies the current Pacific date.

Checks at PR head 64f75999: `python3 -m unittest hass.tests.test_interpreter_today -v` — 10 tests, OK (recorded in PR #195).

Limits: No Python date parsing, resolving relative dates ourselves, proposal-date wording changes, live model call or interpreter_eval fixture change.

## H03 unstated brand, maker place or link asks first (AV2022-04) — November 4, 2026

Branch rb/av2022-04 (AV2022-04, PR #346, merged as 9d92913443071cf62ee1ae349bee8245544c5a55). Unstated brand, maker place and link claims ask for owner facts first.

Checks at PR head ecc16c0: `python3 -m unittest hass.tests.test_claims_sources hass.tests.test_undo hass.tests.test_claims` — 31 tests, OK after merging origin/main (recorded in PR #346).

Limits: Maker name/story and product name/description term scanning are unchanged; no fetching or validating links or live model call.

## H11/H12 voice notes get a please-type-it reply (AV2022-05) — November 1, 2026

Branch rb/av2022-05 (AV2022-05, PR #140, merged as 76990116c47e57f4d0c2eaefdb767d6a86811074). Audio is refused, never transcribed or stored; a voice note gets a request to type instead.

Checks at PR head fa8a9d27: `python3 -m unittest discover -s hass/tests -t . -v` — 995 tests in 401.986s, OK (skipped=10) (recorded in PR #140). Discovery uses the default pattern `-p 'test*.py'`.

Limits: No transcription, audio storage, MP3/WAV/OGG detection, bridge attachment metadata or LIMITS.md wording change.

## H06/H17 history lists approved changes only (AV2022-06) — November 1, 2026

Branch rb/av2022-06 (AV2022-06, PR #169, merged as 341c1469c7d34b8b61112b38774d2d5686927e75). Chat history lists approved changes only.

Checks at PR head b1f23cd2: `python3 -m unittest discover -s hass/tests -t . -v` — PASS, rc 0 via prepush (no full-suite count recorded); a targeted run recorded 104 tests, OK (recorded in PR #169). Discovery uses the default pattern `-p 'test*.py'`.

Limits: No paging, history-all variant, editor CLI history change or undo-selection rule change.

## H05/H17 near-approval asks for the explicit yes code (AV2022-07) — November 1, 2026

Branch rb/av2022-07 (AV2022-07, PR #179, merged as ffdf942c079a4a4855e4169892cf831d46702f28). Near-approval words request yes <code>; they never approve a draft.

Checks at PR head 1413841914b: `python3 -m unittest discover -s hass/tests -t . -v` — 1305 tests in 687.003s, OK (skipped=21), before the final main merge (recorded in PR #179). Discovery uses the default pattern `-p 'test*.py'`.

Limits: No approval on these words, emoji/reaction approvals, other languages or HELP_TEXT/COMMANDS.md wording change.

## H08 sender matching ignores email case and phone punctuation (AV2022-08) — November 1, 2026

Branch rb/av2022-08 (AV2022-08, PR #184, merged as c708a99d5240fae5fe0a849fab258e7272879485). Owner sender matching ignores email case and phone punctuation; no configured sender value is quoted here.

Checks at PR head da932439: `memcap -- python3 -m unittest hass.tests.test_ledger_rf1120 hass.tests.test_output_hygiene hass.tests.test_owner_sender_match hass.tests.test_state_db_nofollow` — 20 tests in 19.297s, OK (recorded in PR #184).

Limits: No ownerChat matching, multi-owner roles, bridge sender parsing, real contact details or live BlueBubbles call.

## H08/H10 BlueBubblesPhotos fetches attachments with a fake transport (AV2022-09) — November 1, 2026

Branch rb/av2022-09 (AV2022-09, PR #141, merged as 5370850e8157d594d8c7fbd8f535c75fb484bd8b). BlueBubbles is loopback-only with no password in errors; attachment fetching is tested with a fake transport.

Checks at PR head 99950540171662e: `python3 -m unittest discover -s hass/tests -t . -v` — 1000 tests in 390.431s, OK (skipped=10) (recorded in PR #141). Discovery uses the default pattern `-p 'test*.py'`.

Limits: No live Mac/BlueBubbles call, service/runner wiring, HEIC conversion, storage or bridge.py edit; fake transports and repository fixtures only.

## H06 maker result check reads the maker's product card (AV2022-10) — November 1, 2026

Branch rb/av2022-10 (AV2022-10, PR #170, merged as dec67f5bfc0466fa7478334a92e7f14b39ebb858). Maker result checking reads the maker's product card.

Checks at PR head 2104281921d: `python3 -m unittest discover -s hass/tests -t . -v` — 1207 tests in 510.607s, OK (skipped=15); gated capture tests separately ran 8 tests, OK (recorded in PR #170). Discovery uses the default pattern `-p 'test*.py'`.

Limits: No shop.js data attributes, makers-page change, product/hike result-check change or deploy.

## H06 completed and cancelled hikes get a result check (AV2022-11) — November 1, 2026

Branch rb/av2022-11 (AV2022-11, PR #175, merged as 81c130c144bb46961f9a1bdff7d7acb7f0219659). Completed and cancelled hikes receive a real preview result check.

Checks at PR head 162f514f: `python3 -m unittest hass.tests.test_preview_hike_results hass.tests.test_preview_store_address -v` — 17 tests in 35.932s, OK (recorded in PR #175).

Limits: No community.js rendering, guest counts or RSVP server change, live-site check or deploy.

## site real hikes show route and trail-information link (AV2022-12) — November 1, 2026

Branch rb/av2022-12 (AV2022-12, PR #149, merged as e4a23a4076aa7725f7f76cab9377e1786121bf41). A real hike shows its route and trail-information link.

Checks at PR head 1049f825: `python3 storefront-mockup/community-qa.py` — Community UI passed, exit 0; full hass discovery separately recorded 1058 tests, OK (skipped=10) (recorded in PR #149).

Limits: No copying route fields into events, trail map/explorer or hike-page template change, or deploy beyond the normal on-merge path.

## H21 retention counts approval and closed-memory rows (AV2022-13) — November 1, 2026

Branch rb/av2022-13 (AV2022-13, PR #193, merged as a8879cb6dc088e0a25a84a0baa6b52f1f1ae4594). Retention reports counts only and deletes nothing, including approval and closed-memory row counts.

Checks at PR head 02f49e4b: `python3 -m unittest discover -s hass/tests -t . -v` — 1337 tests in 841.465s, OK (skipped=21), before the last main merge; after merge, 31 retention tests were OK and prepush hass unittests passed (recorded in PR #193). Discovery uses the default pattern `-p 'test*.py'`.

Limits: No deletion or pruning (an owner decision), statebackup, health output, SUPPORT.md wording or live-state access.

## H25 phone guide documents commands the parser accepts (AV2022-14) — November 1, 2026

Branch rb/av2022-14 (AV2022-14, PR #144, merged as 2e80eab13e4d84ad0a30088101b7e50885422c09). The owner phone guide documents commands checked against the parser.

Checks at PR head 7d666798: `python3 -m unittest hass.tests.test_phone_guide hass.tests.test_commands_doc hass.tests.test_limits_doc hass.tests.test_support_doc -v` — 32 tests in 0.017s, OK (recorded in PR #144).

Limits: No command, HELP_TEXT or COMMANDS.md change, owner trial, Mac setup docs, screenshots or publication beyond the repository.

## H13: one dated home-page notice (AV1322-01) — November 3, 2026

Branch rb/av1322-01 (AV1322-01, PR #328, merged as c2bc3b3b2a0ac262ef1f3190b76d3cc14fd93797). store.set_notice / store.clear_notice keep one dated home-page notice (text <=160, until <=60 days ahead, Pacific); the page is byte-identical with no notice; preview checks noticeShown. hass/ops/home.py, hass/content_model.py, hass/sitegen.py, template, preview.

Checks at PR head: `python3 -B -m unittest hass.tests.test_store_notice hass.tests.test_store_ops hass.tests.test_store_intro hass.tests.test_store_limits hass.tests.test_content hass.tests.test_interpreter_prompt hass.tests.test_interpreter_prompt_store -v` ran 73 tests, OK (2 skipped) (recorded in PR #328; historical evidence, not rerun for this ledger).

Limits: Without JavaScript the notice remains until regeneration; no notice leaves the generated page unchanged.

## H04: route.add drafts a new route idea (AV1322-02) — November 3, 2026

Branch rb/av1322-02 (AV1322-02, PR #308, merged as 2ca87c38ee202619b33660785fac273a8b86ea2b). route.add drafts a new undated route idea (all fields, public https sourceUrl); slug clashes get -2/-3; undo removes the added idea (history.py change). hass/ops/routes.py, hass/ops/history.py, hass/README.md.

Checks at PR head: `python3 -B -m unittest hass.tests.test_route_add hass.tests.test_route_edit hass.tests.test_route_edit_titles hass.tests.test_route_edit_spacing hass.tests.test_content hass.tests.test_interpreter_prompt hass.tests.test_interpreter_prompt_community hass.tests.test_undo` ran 72 tests, OK (recorded in PR #308; historical evidence, not rerun for this ledger).

Limits: Route ideas remain undated; missing source facts ask for the link and name, and undo refuses a subsequently edited idea.

## H04: hide and restore a route idea (AV1322-03) — November 3, 2026

Branch rb/av1322-03 (AV1322-03, PR #317, merged as 1944ae3ece6433c2b6f1df2c2a5b8cc6e0abe72b). route.hide / route.restore take an idea off and back on the generated route list; a scheduled hike linked to a hidden idea is refused; output byte-identical with none hidden. hass/ops/routes.py, hass/content_model.py, hass/sitegen.py, hass/ops/hikes.py.

Checks at PR head: `python3 -B -m unittest hass.tests.test_route_hide hass.tests.test_route_edit hass.tests.test_content hass.tests.test_migration_baseline_shape hass.tests.test_hike_ops hass.tests.test_generated_io hass.tests.test_interpreter_prompt_community` ran 77 tests, OK (recorded in PR #317; historical evidence, not rerun for this ledger).

Limits: A scheduled hike using the idea blocks hiding it; cancelled and completed hikes do not.

## H04/H17: find lists hikes and route ideas (AV1322-04) — November 3, 2026

Branch rb/av1322-04 (AV1322-04, PR #313, merged as df10f4eb1b69559b5b1717521367e2fced0ec791). find <words> also lists hikes (Pacific weekday/date/time, status, ordered by start) and route ideas (by title); read-only, same answer while paused. hass/conversation.py, docs/hass/COMMANDS.md.

Checks at PR head: `python3 -B -m unittest hass.tests.test_find_hikes hass.tests.test_find hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_hike_ids` ran 37 tests, OK (recorded in PR #313; historical evidence, not rerun for this ledger).

Limits: Read-only, including while paused; unreadable hike dates are named rather than guessed.

## F04: report command in chat (AV1322-05) — November 4, 2026

Branch rb/av1322-05 (AV1322-05, PR #323, merged as 8f56b35577d3aa59aba91f01ea9869c9de8c6f71). the whole message 'report' (or 'morning report') replies the morning shelf report from writer worktree content; fixed refusal line when unavailable; read-only, works paused. hass/conversation.py, docs/hass/COMMANDS.md.

Checks at PR head: `python3 -B -m unittest hass.tests.test_report_command hass.tests.test_morning_report hass.tests.test_morning_report_shapes hass.tests.test_morning_report_future hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_status_pause -v` ran 61 tests, OK (recorded in PR #323; historical evidence, not rerun for this ledger).

Limits: Read-only, with no expiry sweep or scheduled delivery; unavailable content gets a fixed refusal.

## F04: morning report names today's and tomorrow's hikes (AV1322-06) — November 3, 2026

Branch rb/av1322-06 (AV1322-06, PR #311, merged as e3602ca300f599daa7285b65decdb68263439ba8). morning report gains a Hikes line for events starting today or tomorrow (Pacific) with confirmed/capacity or 'guest count unavailable'; byte-identical when there are none. hass/morning_report.py.

Checks at PR head: `python3 -B -m unittest hass.tests.test_morning_report_hikes hass.tests.test_morning_report hass.tests.test_morning_report_shapes hass.tests.test_morning_report_future hass.tests.test_health_guests -v` ran 44 tests, OK (recorded in PR #311; historical evidence, not rerun for this ledger).

Limits: Cancelled, completed and out-of-window hikes are omitted; unavailable guest counts are never reported as zero.

## F07: post command drafts a caption in chat (AV1322-07) — November 4, 2026

Branch rb/av1322-07 (AV1322-07, PR #366, merged as 9e3f3aade1b4efb6bc2e4d5e79a8ca79240b37ae). post <product id> replies 'Draft post (not posted)' with social_draft's caption and the product's site photo attached; plain refusals; read-only, works paused. hass/conversation.py, docs/hass/COMMANDS.md.

Checks at PR head: `python3 -B -m unittest hass.tests.test_post_command hass.tests.test_social_draft hass.tests.test_social_draft_inputs hass.tests.test_social_draft_shapes hass.tests.test_social_draft_tags hass.tests.test_social_draft_text hass.tests.test_help hass.tests.test_commands_doc hass.tests.test_attachment_reply` ran 80 tests, OK (recorded in PR #366; historical evidence, not rerun for this ledger).

Limits: Draft only; nothing is posted or scheduled, and symlink photos are refused.

## F07: hike announcement draft (AV1322-08) — November 3, 2026

Branch rb/av1322-08 (AV1322-08, PR #312, merged as df53f65af355ec4c3fa6933377d5bd62acd9e8ef). social_draft.py --hike ID prints a local hike announcement draft (title, Pacific weekday date and time, Meet at, Route line, fixed tags); ordered refusals; nothing posted, no network. hass/social_draft.py.

Checks at PR head: `python3 -B -m unittest hass.tests.test_social_draft_hike hass.tests.test_social_draft hass.tests.test_social_draft_inputs hass.tests.test_social_draft_shapes hass.tests.test_social_draft_tags hass.tests.test_social_draft_text -v` ran 61 tests, OK (recorded in PR #312; historical evidence, not rerun for this ledger).

Limits: Draft only; nothing is posted or fetched. Cancelled, past, incomplete or tagged hikes are refused.

## Site: hike page: Add to calendar link (AV1322-09) — November 3, 2026

Branch rb/av1322-09 (AV1322-09, PR #318, merged as 620149050ed05e62b4e430b02d23428354f51005). each upcoming scheduled hike on /hike gets an 'Add to calendar' .ics data link (one VEVENT, RFC 5545 escaping, 75-octet folding); no server change, no new site file. storefront-mockup/community.js.

Checks at PR head: `python3 -B -m unittest hass.tests.test_hike_ics hass.tests.test_content_starts_at hass.tests.test_status_past_hikes hass.tests.test_https_links -v` ran 38 tests, OK (recorded in PR #318; historical evidence, not rerun for this ledger).

Limits: No link for cancelled, completed, started or unreadable hikes, or the sample invitation; duration is fixed at two hours.

## Site: catalog: link to one product (AV1322-10) — November 4, 2026

Branch rb/av1322-10 (AV1322-10, PR #315, merged as bd41e06fa74603f1662732a499d1331a91b7dcd4). each product card ends with a 'Link to this' link; ?item=<id> focuses and centers that card (wins over filters); unknown/empty/over-80-char item is ignored. storefront-mockup/shop.js.

Checks at PR head: `python3 -B -m unittest hass.tests.test_https_links hass.tests.test_generated_links hass.tests.test_product_alt hass.tests.test_design_check` ran 49 tests, OK (recorded in PR #315; historical evidence, not rerun for this ledger).

Limits: Unknown, empty or overlong item values are ignored; the next filter change drops the item parameter.

## H25: docs: feature states from the 2026-11-02 audits (AV1322-11) — November 3, 2026

Branch rb/av1322-11 (AV1322-11, PR #316, merged as 945b9fa35d702013ad4172f7d49a5662d40e7f42). docs/hass/FEATURES.md gains a State column (Done/Partly/Not built/Needs G) on the three H tables from the 2026-11-02 audits; hass/README.md H16/H17/H14 lines updated. Docs only.

Checks at PR head: `python3 -B -m unittest hass.tests.test_support_doc hass.tests.test_commands_doc hass.tests.test_limits_doc hass.tests.test_phone_guide -v` ran 33 tests, OK (recorded in PR #316; historical evidence, not rerun for this ledger).

Limits: States describe the dated audits, not fresh live acceptance; owner and launch decisions remain held.

## H25: home-page limits in LIMITS.md (AV1322-12) — November 3, 2026

Branch rb/av1322-12 (AV1322-12, PR #337, merged as ff87a4c6cc52197e3a79e7f986bcd31679199e17). docs/hass/LIMITS.md gains a Home page section (intro 160, headline 40/line, story 400, notice 160, notice 60 days ahead, home photo 20 MB) tied to code constants; test_limits_doc REQUIRED set grows. Docs + constants.

Checks at PR head: `python3 -B -m unittest hass.tests.test_limits_doc hass.tests.test_store_limits hass.tests.test_text_limits -v` ran 26 tests, OK (recorded in PR #337; historical evidence, not rerun for this ledger).

Limits: Documentation and required-claim constants only; no production limit changes.

## H25: phone guide: home page and route ideas (AV1322-13) — November 4, 2026

Branch rb/av1322-13 (AV1322-13, PR #372, merged as 78958c1d0622366ff50417dd981193d4e4db09c5). docs/hass/PHONE_GUIDE.md gains 'Change the home page' and 'Route ideas' sections plus one More commands paragraph; test_phone_guide SECTIONS list grows. Docs only.

Checks at PR head: `python3 -B -m unittest hass.tests.test_phone_guide hass.tests.test_commands_doc hass.tests.test_support_doc -v` ran 23 tests, OK (recorded in PR #372; historical evidence, not rerun for this ledger).

Limits: Guide stays within its existing length cap; no live channel or publication is connected.

## H09: interpreter eval v3: home page and route cases (AV1322-14) — November 3, 2026

Branch rb/av1322-14 (AV1322-14, PR #338, merged as 47f90b8517a1f882c7160eae7c87bb540b16dc1e). interpreter eval set grows 40 to 55 cases (e41-e55): home-page ops (set_headline/story/home_image/notice) and route.add/hide/restore incl. the no-source question case; offline scorer unchanged. hass/interpreter_eval.py + fixtures.

Checks at PR head: `python3 -B -m unittest hass.tests.test_interpreter_eval hass.tests.test_interpreter_eval_cases hass.tests.test_interpreter_eval_out hass.tests.test_interpreter_request_encode` ran 37 tests, OK (recorded in PR #338; historical evidence, not rerun for this ledger).

Limits: Offline synthetic cases only; no live model call, and the three deliberate wrong replies still fail.

## H20: health: info when the newest backup has no content bundle (AV1322-15) — November 5, 2026

Branch rb/av1322-15 (AV1322-15, PR #319, merged as 836c43ed97337201ce508aadceeaa467f51e9582). health --backups adds one info entry 'backup-content' ('content restores from Git only') when the newest complete backup's manifest lists no content.bundle; fixed words, never a path; ok/notify/exit unchanged. hass/health.py, docs/hass/SUPPORT.md.

Checks at PR head: `python3 -B -m unittest hass.tests.test_health_backup_content hass.tests.test_health hass.tests.test_support_doc hass.tests.test_statebackup -v` ran 28 tests, OK (recorded in PR #319; historical evidence, not rerun for this ledger).

Limits: Info only, with no path or commit in the detail; older backups are ignored and ok, notify and exit status are unchanged.

AVO-SPECIALS-1 (branch rb/avo-specials-1): weekly specials. Additive `store.specials` list (content_model.py), a "This week's specials" section at the top of the home/shop page rendered only for specials active on the Pacific date plus a small client-side date check (hass/specials.py), and the editor ops specials.add, specials.edit, specials.remove, specials.clear_expired (hass/ops/specials.py) with undo, preview target and the normal approval flow. No price field; the site shows no prices anywhere except inside an owner-written deal line. Tests: hass/tests/test_specials.py (browser tests need PLAYWRIGHT_MODULE). The Hass chat skill is the separate SKILLS-SPECIALS-1 card.

## RF0844-13: trail map recovers from a failed Topo image — November 9, 2026

Branch rb/rf0844-13. trail-explorer.js: the existing basemap image-error recovery (official-guide fallback, one `Try loading the map again` button, enlarged-dialog cleanup with exact overflow restore) now admits the Topo image as well as the aerial one; the old check ignored any error whose href was not aerial. Retry still starts from the aerial default. trail-map-retry-qa.cjs gains five cases (Topo 404, 404 while enlarged with a non-empty previous overflow, undecodable and aborted Topo image, detached/replaced wrapper ignored, supported layers and single-flight retries), each waiting for a real image error event at 390 and 1440 px.

Checks: `node storefront-mockup/trail-map-retry-qa.cjs storefront-mockup` (local Chromium, loopback only) passed 20 checks on the builder's clone; the new Topo cases failed before the fix. Not deployed; no physical-device or Safari check.

## RF0844-12: community email refuses ASCII controls — November 9, 2026

Branch rb/rf0844-12. storefront-mockup/community-server.py: `email_address` now refuses any remaining U+0000–U+001F or U+007F after the existing strip/lower step with the existing 'Please enter a valid email address.' error (never stripped into a different address), so subscriptions no longer save and RSVPs no longer claim places for addresses with an embedded NUL, SOH, ESC or DEL. Order, 409 precedence, length/shape checks and consent merging are unchanged. New hass/tests/test_community_email_controls.py runs the real handler on a loopback port with a scratch config and database and compares full row snapshots.

Checks: `python3 -B -m unittest hass.tests.test_community_email_controls -v` ran 5 tests, OK on the builder's clone (failed before the fix). Not deployed; no email is sent and no historical row is cleaned.

## RF0854-12: shared dialogs stay open for clicks inside their padding — November 9, 2026

Branch rb/rf0854-12. script.js: the shared Privacy/RSVP `<dialog>` used to close on every click whose target was the dialog itself, and a click on its own padding or border has that target too. It now closes only when the pointer lies outside the dialog's rectangle, measured at click time; child clicks, the Close button and native Escape are unchanged. static-site-qa.cjs gains real mouse-coordinate checks at 390 and 1440 px (each point confirmed by elementFromPoint and the rectangle before the click): padding clicks keep Privacy open (also after a resize) and keep the real RSVP form open with its typed synthetic values, while a backdrop click, Close and Escape still close it and return focus; nothing is posted or stored.

Checks: `node storefront-mockup/static-site-qa.cjs DIR` on a fresh `hass/sitegen.py --publish` folder outside the repo (local Chromium, loopback only) passed on the builder's clone; the new padding check failed before the fix. Not deployed; no physical-device or Safari check.

## RF0854-13: stale Available today filter retires at the next catalog render — November 9, 2026

Branch rb/rf0854-13. shop.js: right after renderCatalog's existing refreshFreshness(), retireStaleAvail() checks the whole catalog; when no product still carries a current word (an open page aged its shelf check from seven to eight days), the Available today checkbox is unchecked and removed, and only ?avail is dropped with replaceState (other params, duplicates, hash, item and status line untouched; no history write when avail is absent). The render then continues with the other filters and repaints in full. Before the fix, the same page kept avail=1 and showed 0 selections while a reload showed the full list. catalog-only-qa.cjs gains fixed-clock cases (Pacific Nov 7 = age seven, Nov 8 = age eight): checked control on search/view/shelf renders with reload equivalence, unchecked control on load more with no history write, paginated repaint without duplicates, preserved view/shelf/search/maker/from/item/status/focus/scroll, and current words outside the results (Sold out included) keeping the control.

Checks: `node storefront-mockup/catalog-only-qa.cjs` against an isolated loopback static server over a fresh `python3 -B hass/sitegen.py --publish` build passed on the builder's clone; the new cases failed on main's shop.js. Not deployed; no physical-device or Safari check.

MAIN-RED fix (statebackup bundle determinism): `git bundle create` in statebackup.create now runs with `-c pack.threads=1`. With the default thread count Git delta-packs the same HEAD differently from run to run (probe: 25 bundles of one fixture commit gave 3 distinct hashes; with one thread, 1), so two backups of an unchanged commit carried different content.bundle hashes and test_statebackup_diff (identical backups differ in nothing; added/removed/changed) failed intermittently on main since run 42743080672 and locally on 330191b too. Not a clock or environment change; no merged PR reverted.

## RF1915-13: closed open-requests age by instant, not by timestamp spelling — November 10, 2026

Branch rb/rf1915-13. openreq.py: `OpenRequests.sweep` compared `closed_at` text with the cutoff text, so a row stamped with another UTC offset was erased up to hours late (+02:00) or early (-07:00, even exactly at the cutoff). The closed-row phase now parses each stored `closed_at` as an aware instant (offsets and Z), converts to UTC, and erases only an instant strictly earlier than now minus the unchanged 24 hours, measured in elapsed time across DST. A `closed_at` that is NULL, not text, zone-less or unparseable has unknown age and is held untouched. A naive or non-datetime clock raises `ValueError("retention requires an aware clock")` before any write (no table yet stays lazy). Live-request expiry, the immediate erasure of legacy-kind rows, retained rows and the schema are unchanged. test_open_requests.py gains six real-store cases: mixed offsets for every closed state, microsecond cutoff, DST, held unknown-age rows, live and other data untouched, naive clock.

Checks: `python3 -B -m unittest hass.tests.test_open_requests` ran 33 tests, OK on the builder's clone; the six new cases failed on main's openreq.py. Not deployed; no backup-erasure claim.

## RF1915-11: correspondence prune skips impossible calendar-named files — November 10, 2026

Branch rb/rf1915-11. hass/corrlog.py: CorrLog.prune() parsed every regular, non-symlink file named like a day with strptime inside one loop, so a stray file named like 2026-02-30.jsonl raised ValueError, which record() swallowed before opening today's file: the first correspondence row of the day was lost (a second record in the same instance worked) and the prune command died with a traceback. The date is now parsed per candidate; a ValueError means an unknown file, left untouched (name, bytes, mode), and the scan continues, so valid expired days are still deleted whole at the unchanged 90-day UTC cutoff. OSError handling, the once-a-day scan, the count and the CLI wording are unchanged. test_corrlog.py (Retention) gains four regressions on synthetic temporary state: impossible names skipped while a valid expired file is deleted, the first and second record of a day both written (also on the next UTC day), cutoff and leap-day boundaries, and the CLI printing `Deleted 1 old day files.` then `Deleted 0 old day files.` with empty stderr.

Checks: `python3 -B -m unittest hass.tests.test_corrlog` ran 68 tests, OK on the builder's clone; the four new tests failed (3 errors, 1 failure) with the fix removed. Not deployed or merged; no live state touched.


## RF1915-10: require both sides of new-item comparison evidence

Branch rb/rf1915-10. Actual builder: sol-reviewer (gpt-6.1-sol). The offline preview command now returns 1 if any BEFORE or AFTER result fails, after collecting all three cases and writing the existing preview.json. Capture order, diagnostics, JSON schema/format and missing-PLAYWRIGHT_MODULE exit 2 are unchanged. No renderer, product, published content or committed preview artifact changed.

Builder checks: the new BEFORE-only regression failed on the old predicate in all three subcases (first, last and all BEFORE failures returned 0 instead of 1). After repair, `python3 -B -m unittest hass.tests.test_newitem` ran 53 tests, `python3 -B -m unittest hass.tests.test_ledger_rf1120` ran 3, and `python3 -B -m unittest hass.tests.test_ci_shards` ran 25: all OK under the host memcap wrapper. Five new main-level tests cover BEFORE-only, AFTER/both-side, all-pass, complete retained diagnostics/JSON after early failure, and missing Playwright with no output side effects. These aggregation tests use synthetic capture/photo dependencies and external temporary output; they do not prove Chromium ran or establish fresh rendering quality. No server, live operation, publication or send was performed.

## RF1635-7: backlog purge compares timestamp instants — November 10, 2026

Branch rb/rf1635-7. hass/skills/backlog.py: Backlog.purge() compared received_at to the cutoff as strings, so an offset-stamped row could be kept up to hours too long (+02:00) or deleted early (-07:00, including at exactly 90 days). It now converts the clock (UTC, before subtracting the days) and each stored stamp to UTC instants and deletes only rows strictly older than the cutoff, open or closed, per row by id and original stamp. Unparseable, date-only or zone-less stamps have unknown age and are kept; a naive clock raises a fixed ValueError before any delete. record(), stored bytes, the CLI wording and the 90-day period are unchanged.

Checks: `python3 -B -m unittest hass.tests.test_skills_backlog` on the builder clone (new offset, microsecond, DST, legacy-row, unknown-age and CLI tests). Not deployed; no live state touched; old backups are not erased.

Review fix (same branch): stored stamps are now compared to the cutoff as aware instants without converting them to UTC, so valid range-edge stamps such as `0001-01-01T00:00:00+02:00` or `9999-12-31T23:59:59.999999-02:00` no longer raise OverflowError and abort the purge; later expired rows are still deleted. New test `test_purge_survives_range_edge_stamps_and_continues`.

Branch rb/rf1915-12. hass/label_eval.py: _read_photo now checks the bytes it actually read (0 < length <= MAX_PHOTO) and raises the existing fixed refusal when a file shrank to empty or grew past the cap after fstat; live() still checks every photo before any transport call and writes nothing on refusal. A file shrinking to a nonempty allowed length is still admitted; no snapshot guarantee. Valid input and output are byte-identical.

Checks: `python3 -B -m unittest hass.tests.test_label_eval` on the builder clone (new changed-after-fstat and boundary tests; the empty/oversize ones fail without the fix). Not deployed; no live model run.

## AVO-FIX-559b: preserve source-block context and historical predicates — November 13, 2026

Branch rb/hass-live-add-2, PR #559, final operator-admitted Codex escalation after three SEC-3 RETURNs. Maker-site facts are admitted only after every sentence in their complete source block is understood as an allowed affirmative fact; unknown context drops the whole block. Private provenance retains the complete supporting blocks. Product-making history no longer becomes the maker's founding year or masks an explicit founding date. Exact-draft owner approval and the operator security hold are unchanged; the PR stays draft.

Builder evidence: 147 focused maker-site, production-dispatch/photo/undo and SEC-2 tests pass. The new real-HTML production-path table had 10 failing subtests on the prior candidate and passes after repair (11 cases, including literal multi-sentence controls and complete provenance). Preserved second- and third-RETURN probes replayed against this clone, with both four-test receipt suites passing and zero commits without yes. No live state, publication or credentials touched. Diagnosis posted before code edits on PR #559; independent review and operator release remain outstanding.

## AVB-09: one generated capability inventory — November 13, 2026

The skill declarations now explicitly name pack, changing targets, approval class, sandbox support, declared audit fields and audience. Missing/invalid fields fail the lint; mixed-pack `SKILLS` exports are rejected. The legacy approval execution field and all existing plans, previews and policy gates are unchanged. A2/A3 stay unavailable, not silently treated as A1. The new `hass/capabilities.py` generates `docs/hass/capabilities.json` and the owner page `CAPABILITIES.md`; `help` appends the same registry-derived skills to the existing fixed-command examples. CI tests reject missing/stale generated files. The FAQ is honestly labelled as request-recording only, and the empty till pack is visible. These describe source capabilities, not the installed runtime or permission to publish. AVB-10/11 retain the audit writer/per-target sandbox work.

Builder evidence: generator `--check` passed; 63 focused metadata/help/model/lint/demo tests passed, including missing metadata, drift without writes, retired/new entries, target/approval inconsistencies, real conversation help parity in fixtures and no approval/control changes. The existing voice tests passed in the earlier 87-test focused selection. The first full CI found that the demo's independent plain-words checker rejects the heading word “Skills”; the heading now uses ordinary words and the metadata test also runs that checker. Both original failing demo assertions pass unchanged. An additional broad local compatibility run reached its fixed 1500-second limit without a final verdict and is not counted as passing. No host settings, live runtime, services, credentials, messages or records were read or changed. Rollback: revert this PR; no state migration or setting change is involved.
