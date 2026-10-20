# Avocado Shack private commerce build

This project executes the build specification in ../planning. It is an internal build, not a live shop. No public DNS, live payment or outbound marketing changes are authorized here.

## Foundation

Medusa 2.21.2 (MIT core; restricted enterprise RBAC/SSO not used), Node 24.21.0, PostgreSQL 18.4 provided by project-local embedded-postgres 18.4.0-beta.17, and Next 16.3.8. The database wrapper has a beta version and must be replaced with a managed/operated PostgreSQL service before a trial. Exact application dependencies are pinned in the local manifests and lockfiles. Backend and storefront have separate React dependencies to satisfy their upstream contracts.

The command gateway owns private evidence, drafts, approvals, pickup schedules, checkout bindings and packing tasks. Medusa owns products, prices, online stock, reservations, carts, payments and orders. Stripe is the external payment processor. The hosted-checkout provider replaces the native PaymentIntent provider; it does not create a second payment lifecycle.

## Run locally

1. Use Node 24 (the pinned version is in `.nvmrc`). The existing local build has `.runtime/node/bin/node`. With a fresh checkout, install compatible Node before installing dependencies. Run `npm ci` in `commerce`, then in `commerce/storefront`.
2. From `commerce`, run `.runtime/node/bin/node scripts/setup.mjs`. It prepares the private environment and `.runtime/access.txt` without replacing existing credentials. If using an independently installed Node 24, use `node` in these commands instead.
3. For the first database only, start `scripts/database.mjs` in a separate terminal. From `backend`, run `XDG_CONFIG_HOME=../.runtime/config MEDUSA_DISABLE_TELEMETRY=true ../.runtime/node/bin/node ../node_modules/@medusajs/cli/dist/index.js db:migrate`. From `commerce`, run `scripts/bootstrap.mjs` and `scripts/prepare-media.mjs` with the same Node runtime. Existing media/intake files must remain in the workspace.
4. Stop the separate database terminal. Start the whole preview with `.runtime/node/bin/node scripts/start.mjs`. Successful startup prints `READY: Private storefront http://127.0.0.1:3100/`. Ctrl-C stops its own component process groups in reverse order.
5. Open the preview and use the owner, packer or visitor password from `.runtime/access.txt`. This file contains role passwords only. Never share `.runtime/config.json` or `backend/.env`; they also hold database and backend secrets.

For an optimized internal storefront, stop the stack, run `NEXT_TELEMETRY_DISABLED=1 ../.runtime/node/bin/node node_modules/next/dist/bin/next build` from `storefront`, then run `.runtime/node/bin/node scripts/start.mjs --optimized` from `commerce`. The launcher requires a built storefront and uses `next start`. Rebuild after changing storefront code; a running optimized storefront does not pick up source edits. This mode still uses the local development commerce backend and is not a public-production deployment.

The combined launcher waits for database, backend, gateway and storefront readiness and disables framework telemetry. It was exercised against the persisted local database, not an empty fresh machine. A secure approved connection for physical-phone access is not configured; browser phone-size testing uses the local preview. Stripe credentials and public hosting are not set up.

## Data and owner workflow

The owner supplied 33 unique store/product photos; three exact duplicates remain linked in the original intake manifest. All 33 cached photos and 33 previews are verified present. The 36 imported original source paths are currently unavailable; new uploads retain their source bytes privately. Those are private evidence, not 33 verified products. The owner separately confirmed Hass avocados at $2 each and 12 allocated to online pickup. No other prices, quantities or box recipes are fabricated.

Astra uses explicit-text rules, Apple Vision label reading and the project-local Qwen3-VL 2B model through Ollama. Each photo is interpreted separately before suggestions are combined. Names remain proposals: the model can misread labels and varieties. Price, quantity and stock action come from explicit owner text, and unknown fields remain blank. Photo capture produces private drafts with exact-version review. Applied updates use supported Medusa workflows and stock readback. New-arrival receipts freeze their target quantity to avoid adding stock twice on retry.

The interpreter is a separate optional process in `astra/server.mjs`, on loopback port 3400. Its dedicated worker credential cannot authenticate engine commands. POST `/interpret` accepts an owner message and validated uploaded-image filenames and returns proposed fields plus label evidence. The gateway accepts bounded known fields only, independently validates stock/payment rules, and requires owner approval. A replacement local interpreter can implement that interface; no cloud model or external photo transmission is configured. If the worker stops, the gateway preserves explicit text and private evidence with an unavailable notice while shopping and packing continue. Restart the combined stack to restore it. Worker authentication, path validation and real worker-outage commerce regression are recorded in `evidence/astra-worker-smoke.log`.

Published box offers have a “Draft a new version” action. It creates a private proposal; approval replaces the storefront offer while retaining the original accepted recipe in earlier orders. The real replacement journey is not yet demonstrated because owner box prices, contents and costs are pending. An authenticated owner can approve product changes. A packer cannot publish products or prices. The store remains available if the interpreter is offline. Owner-dictation support is through the phone keyboard. Personal iMessage, SMS numbers, eSIM purchases and SkipperCast changes are excluded.

## Pickup and tax

Published shop hours are used at the user's direction: Monday–Friday 9am–6pm, Saturday 9am–5pm, Sunday closed. All windows display America/Los_Angeles time. Initial internal defaults are hourly windows, 30-minute cutoff/lead time and 12 orders per window; final operational capacity needs owner confirmation.

Raw fresh avocado sold for take-home pickup is configured as an exempt food product under California Regulation 1602. This is not a blanket zero-tax configuration for all goods. Unconfirmed taxable categories cannot be approved for sale in the current path. Sources: https://avoshack.com/hours/ and https://www.cdtfa.ca.gov/lawguides/vol1/sutr/1602.html .

## Checks and limitations

Run `.runtime/node/bin/node --test gateway/*.test.mjs`. Integration checks and exact results are in `evidence/`. A simulator is clearly labeled and cannot establish real Stripe completion. Real Stripe requires secure authorized test keys, signed webhook processing, and an exercised paid-order/refund round trip.

The user authorized mock checkout on October 5, 2026 and deferred Stripe account creation. Demo acceptance therefore uses explicitly labeled simulated payments. Real Stripe payment, webhook and refund validation remain mandatory before taking actual orders.

For a private offline backup, stop the database cleanly and run `.runtime/node/bin/node scripts/backup.mjs`. Restart the original database, then run `.runtime/node/bin/node scripts/restore-test.mjs`. Restoration uses a separate local database on port 55433 and compares business records with the original; it does not overwrite the original. Backups include the database, uploaded originals/derivatives, the entire imported inventory-intake directory and private configuration, and stay in ignored `.runtime/backups` folders. The verifier compares hashes and exact file sets for uploaded and imported assets as well as 33 selected business tables and private configuration. This is a tested local recovery method, not a production backup service.

Online-bin movement controls record receipts, transfers, recounts, spoilage and corrections. A correction must select an earlier applied movement for that same product; the original history remains intact. Recent history shows the before/after counts and reasons. They protect checkout reservations and read back engine stock. Owner safety buffers leave a configured number of units unavailable to new checkout without changing physical counts. Availability subtracts current engine reservations once; existing accepted checkouts are preserved. Buffer changes require the current version and a reason. Refund controls are owner-only; refunds do not automatically restock inventory. Stock-race and isolated backup/restore evidence is saved in `evidence/`.

Expiry and stock-release tests, concurrent basket tests, role restrictions, simulated order replay, and preparing/ready/collected engine fulfillment have passed. Current-schema backup/restore and combined restart have passed. Open work includes actual owner-approved box purchase evidence, reviewed identity/package matching, and remaining physical-phone, keyboard/zoom and active packing-form QA. See ../BUILD_LEDGER.md for the acceptance ledger. No production-readiness claim is made.

## Owner and packing-team walkthrough

### Add or update a product

1. Sign in as Michael / owner using the private access file. Open Astra.
2. Attach the actual product photo and write its name, selling unit, price and online-bin quantity. For the confirmed sample: “Hass avocado, each, $2, 12 available for online pickup.” This is a recount of the online bin. “12 new Hass avocados” is a receipt and needs its pool confirmed.
3. Read the questions and exact draft. Supply missing details; do not use a shelf photograph as proof of hidden stock or product claims. Astra proposes visible identities locally. Confirm the exact product and selling package. For a multi-photo update, select the numbered photo that should appear in the store, then save and review the current version.
4. Reject an unwanted unapplied draft with a reason, or approve that exact version. Rejection retains evidence and cannot be undone by editing or approving; send a new update if the proposal changes. Success is “Applied and verified” after the engine readback. Editing a draft requires a new approval. If an operation reports an error, use the recorded retry in Recovery; do not send the same arrival again as a new receipt.
5. Open Recent store activity to review persisted actions and receipts. It is owner-only; detailed before/after records are optional. For website copy, send “Change the welcome to: …”, “Website heading: …” “Website note: …”, or “Set the store hours to: …”. Successive messages accumulate privately. Review the exact version in Website copy and owner note before publishing. Displayed hours do not alter pickup-window settings or accepted instructions. Send “Feature Hass avocado” to draft a homepage feature from that approved product, or “Stop featuring products” to remove it. Review its real image and price before publishing. A changed product revision blocks feature approval until reviewed again. For booking closures, send “Close pickup on YYYY-MM-DD” or “Reopen pickup on YYYY-MM-DD”. Review the exact windows before approval. A changed window invalidates the proposal, and accepted instructions are preserved. Other content commands are not yet complete. Open Shop and confirm the real photo, selling unit, price and description. A draft is never a purchasable product.

### Demonstrate a pickup order

1. Use Store preview access. Open Hass avocado, choose a whole quantity, and add it to the basket.
2. Check the basket, enter an internal test email ending in `.invalid`, and select an offered pickup window. Do not use a real customer's details for demonstrations.
3. If a failed checkout reports that the basket changed, use “Release previous checkout and try again.” It keeps your basket and cancels only an unpaid checkout. A paid checkout needs owner refund review. Continue to the explicitly labeled simulator. Simulate success; no money is charged and no outbound confirmation email is configured.
4. The status page should show the stored order reference, items, total and accepted pickup window. Its return link requires the original authenticated session. A payment return URL alone cannot mark an order paid.
5. A paid test order uses real online-bin allocation. After the demonstration, an owner must review any refund and any stock movement separately. Do not automatically reset bins or overwrite counts while real packing is in progress.

### Pack and resolve a shortage

1. Sign in as Packing team. Open Packing and assign the paid order.
2. Mark it preparing, then mark the promised items picked. Follow the accepted pack sheet; a later catalog edit does not authorize a substitution.
3. If an item is missing, record the shortage and let the owner resolve it or refund it. Do not mark it ready with a different product.
4. Check the actual contents explicitly and mark packed. Then mark ready for pickup. The server rejects skipped steps and uses the recorded packed contents. Mark collected only after the customer actually collects it. In a demo, label these as simulated staff actions.
5. A late payment on a closed checkout appears in Recovery as payment review and creates no packing task. Its Stripe refund resolution remains an integration gate; do not pack it or treat the simulator as real money. Refunds are owner-only. A refund does not put food back into the online bin; use a separate recorded stock movement only when the physical stock warrants it.

### Before a small trial

Resolve automatic photo interpretation and remaining desktop/mobile checks; confirm real box recipes and costs, pickup capacity/lead time, handling/allergen evidence and final customer policies. Configure and test actual Stripe Checkout, signed events and refunds. Move the beta local database wrapper to operated PostgreSQL and establish an approved secure phone connection. Keep marketing, delivery and shipping inactive until their own eligibility, consent and operating rules are ready.

The Node 24 provider uses explicit TypeScript entrypoints and Medusa's loader. Do not add a second `--import tsx` to the documented CLI commands: clean migration testing found that double compilation fails. Backend TypeScript checks pass separately. `AVO_DATABASE_PORT` and `AVO_INTAKE_PATH` support isolated verification; the main preview uses the documented default database port.

### Immediate special messages

For an already approved individual product, send `Special: product name, each, $price, quantity available for online pickup`. Use its exact unit. Astra prepares a private ordinary product update; approval changes its price and total online allocation. The reviewed note makes clear that there is no scheduled end or automatic restoration. Accepted checkouts keep their original price. Restore the normal price/allocation with another reviewed product update. Percentage discounts such as `25% off` resolve against the reviewed regular price using integer cents. Immediate specials reject dates (use the separate dated workflow), boxes, missing values and ambiguous product names. Use the separate dated-special workflow below for a scheduled offer.

Cart creation and recovery use the saved server quote's line prices through Medusa's supported workflow. A later catalog-price edit cannot alter that accepted checkout. Browser prices are ignored, and the engine total must match the saved quote. Verified with `evidence/frozen-price-recovery.log`.

### Dated special messages

Send `Scheduled special: product name, each, $price, quantity available for online pickup; starts: YYYY-MM-DD 9am; ends: YYYY-MM-DD 6pm`. Ordinary times use America/Los_Angeles. ISO timestamps with offsets also work; missing/repeated daylight-saving times require an explicit offset. Identity, unit, a lower fixed price, quantity and exact dates are required.

The private review shows the real photo, regular/special price, local dates, old/new online quantity and affected listings/checkouts. Approval sets the total online bin quantity **now**, with reservation protection, then creates a native Medusa dated price list. Expiry returns pricing to normal automatically and never adds stock. Later stock receipts require owner review. Overlapping offers and changed product/physical-stock sources are rejected. Close an open scheduled offer before editing that product. Canceling an offer disables its dated price without changing stock or accepted checkouts.

Listings and product details show the active end time. Checkout uses native calculated prices; a changed displayed total requires review. Accepted purchases retain their server quote through retries, offer cancellation/expiry and cart recovery. The exact offer ID and dates persist with discounted orders. `scheduled-special-live.log`, `scheduled-natural-expiry.log`, `scheduled-recovery-regression.log` and `scheduled-packing-regression.log` record simulator verification. Complete conversation coverage and final visual QA remain unfinished.

Inventory targets use durable operation references. The engine stores the stock quantity and its application receipt together using the native inventory workflow. If an acknowledgment is lost, retry reads that receipt and returns current stock; it does not restore an old balance over later movements or fulfillment. Product approvals also freeze their source balance/revision. Internal fault and restart evidence is in `stock-receipt-recovery.log`, `product-stock-receipt.log`, and `stock-receipt-restart-summary.json`. Receipt metadata is retained for the PoC; establish a long-term retention/storage policy before launch.

### Closing an interrupted update after a replacement

If an approval fails and a newer reviewed update replaces it, retrying the old approval cannot overwrite the newer catalog revision. Open that failed draft in Astra and use **Close after the newer update** with a reason. The server verifies the selected replacement is the current applied revision of the same product, then records the relationship. This action changes no product or stock and cannot revive the old draft. The closed draft retains its evidence and leaves the exception queue. Recovered stock entries in Recent store activity distinguish the earlier target from current stock. Simulator evidence: `superseded-product-live.log` and `superseded-rejection-regression.log`.

### Late payment review and simulator refund

Cancellation retains the closed native payment session and saves cancellation intent before contacting the provider. Recovery finishes an unpaid cancellation; a payment arriving during cancellation or after closure goes to owner refund review and creates no packing task. A closed native session cannot be reopened by cart creation recovery.

In simulator mode, the owner can use **Refund simulated late payment** in the processing-problems section. The engine authorizes/captures the verified original simulator reference and refunds it through the supported payment-module API. The ordinary order-refund workflow cannot be used here because no order exists. Refund verification releases any remaining temporary checkout hold, leaves physical stock unchanged, and updates the customer status/owner queue. Losing the final website acknowledgment remains retryable with the same payment/refund records. Old simulator records whose native session was deleted can adopt only their original simulator reference for refund, never initiate a new charge.

This late-refund action is explicitly disabled in Stripe mode until a real test-mode round trip and refund-status verification pass. An API-created Stripe refund may be pending or fail; native bookkeeping alone does not prove provider success. Official reference: https://docs.stripe.com/api/refunds/object. Evidence: `late-refund-live.log`, `legacy-late-refund.log`, `cancellation-intent-live.log` and the late-refund cancellation/recovery/packing regression logs. All test money is simulated.

### Offline webhook adapter checks

Run `scripts/payment-webhook-smoke.mjs` with the isolated Node runtime while the local database is available. It uses fixture-only Stripe secrets and the actual SDK signature verifier; no Stripe API calls are enabled. PostgreSQL writes remain in one transaction and the script confirms zero fixture rows after rollback. It checks raw string/Buffer inputs, duplicate and out-of-order evidence, bad/missing/altered/stale signatures, live-mode rejection and no automatic completion. This is adapter evidence only; a real test account and HTTP delivery/refund round trip are still required before payment integration is accepted. See `evidence/payment-webhook-summary.json` and Stripe’s raw-body guidance at https://docs.stripe.com/webhooks/signature.

Both immediate and dated specials accept `$1.50` or `25% off` in the price position. Percentages support up to two decimal places, greater than zero and less than 100. The gateway resolves the selling-unit price once from the reviewed regular price, rounds to the nearest cent (half cents up), and shows the dollar result before approval. It rejects free/ineffective discounts and a price edited to disagree with its reviewed rule. A changed source price/revision requires a fresh proposal. Dated price lists store the approved dollar amount; they do not silently recalculate after a later regular-price change. Evidence: `percentage-full-unit.log`, `percentage-immediate-live.log` and `percentage-scheduled-live.log`.

Owner product messages can include explicit semicolon-separated or line-separated `Description:`, `Package size:`, `Ingredients:`, `Allergens:`, `Handling:` and `Category:` values. These remain private until exact-version approval. Empty detail values propose clearing that detail. Missing details retain the existing reviewed values when identity and selling unit match one known product. No label-derived certifications or tax classes are inferred.

### Review a shelf photo

Open **Your product photos** in Astra. All 33 imported photos have local label evidence and manually reviewed candidate notes. These notes suggest identity only; they do not confirm supplier claims, price, package, quantity or availability. The two whole-store overviews are context.

Expand **Product candidates to review** and choose **Review …** for one item. This creates a separate private draft linked to the same evidence. Confirm its exact name/variant, selling package and unit, price and online-bin quantity. Review readable labels as evidence, including ingredients and handling when applicable. Save the draft, then approve its exact version only after unresolved questions are answered. Incomplete or restricted products cannot enter checkout.

### Compare before approving

Product review displays current and proposed price and physical online-bin quantity. A receipt adds units; a recount sets the total. Use **Refresh price and stock comparison** if another movement happened. If product revision or physical count changes after review, web approval rejects the old comparison before applying. Review the new values. Applied operation receipts keep retries from duplicating stock.

### Phone photos and privacy

JPEG, PNG, WebP and readable HEIC uploads are supported, up to six files of 8 MB each. The complete batch is validated before saving files. Browser JPEGs apply orientation, fit within 1400×1800 without cropping or enlargement, and strip metadata. Source bytes remain private. On this Mac, HEIC uses the local system codec if Sharp lacks HEVC support; another host needs a compatible decoder. The technical HEIC fixture passed, but a fresh camera-original HEIC still needs verification.

Unapproved photo derivatives are owner-only. Approved catalog/site photos remain available within authenticated preview access. Customers retain their own accepted order images after catalog changes; packing staff retain order-task photos. Raw originals are not served.

### Packing without pop-ups

Assignment, shortage reporting/resolution and full refund use labeled inline forms. Enter the team member or reason, then save or cancel. Failed saves preserve the typed value. Refunds do not restock food; use a separately recorded movement only after checking the physical bin. Read the saved state before continuing.

### Current acceptance limits

The private sample journey and consequential stock/payment/task recovery checks are exercised in simulator mode. Clean full-stack restart and isolated backup restore preserve paid order records and packing work. This is not full build completion: local automatic identity suggestions are installed and tested, but still require owner correction; real box recipes/prices/costs are missing; full phone/desktop keyboard/zoom/visual walkthrough is unverified; real Stripe account-backed checkout/webhook/refund is deferred. Owner confirmation is still needed for operating capacity/lead time, other goods' handling/tax and trial policies.

Storefront availability uses native stock minus reservations and owner safety buffers for each exact product/box choice. Listings and details show sold out; **Refresh availability** reloads the market. Local basket limits are advisory; the server checks shared stock and pickup capacity again before payment. An unchanged accepted checkout keeps its original quote despite later catalog edits.

Ordinary dictated price units such as “Hass avocado, $2 each, 12 available for online pickup” also work. If the message says only “$2 each” without an online count, Astra asks for quantity; it never uses the price as a stock count.

### Local photo model and current browser checks — October 6

Ollama 0.35.1 and Qwen3-VL 2B Instruct are installed locally. The executable and model files live under `.runtime`; Ollama also created its normal local identity directory `~/.ollama`. No login service or global app installation was added. The supervised launcher starts the optional model on `127.0.0.1:11435`, with cloud features disabled. The gateway and authenticated worker remain separate. Stop the preview launcher to stop its model process. A duplicate launcher now rejects occupied project ports before creating services.

The official runtime checksum and model manifest digest are saved in `evidence/local-vision-install.json`. Sources: [official runtime release](https://github.com/ollama/ollama/releases/tag/v0.35.1) and [model registry](https://ollama.com/library/qwen3-vl:2b-instruct). The model download passed SHA256 verification. No supplied photos were transmitted to a cloud model.

All 33 cached real photos produced private model proposals in about 108 seconds, with no request failures. This is processing coverage, not proof of correct product identification. Some labels/varieties were overly specific, and one bread display was classified as context. The owner must correct suggestions. Each photo in a six-photo batch now receives its own interpretation; mixed images cannot silently collapse into one product. The bounded response exposes names and classification only, never commerce commands, prices, stock, certification or authorization.

Multi-photo review requires a primary-photo selection from that update's immutable evidence. The server rejects out-of-range choices and approval without selection. The exact draft version remains required. The selected image persists across owner reloads and is the image passed to the native catalog workflow. `primary-photo-live.log` proves private selection and rejection safeguards; the test draft was rejected and the public catalog stayed unchanged.

Responsive browser QA covered shop/product/basket/pickup, test payment and cancellation, empty-search recovery, boxes unavailable, policies, owner intake/review, and packing queue/history. Effective phone widths checked included 375 before the changes and 355/416 for the final interface; desktop width was 1422. These are browser viewport checks, not a physical-device claim. Final owner inputs use at least 16px text, sampled controls have about 44px touch height, and these layouts have no horizontal overflow. A keyboard navigation check showed a visible focus ring. Twenty-eight rendered storefront text samples passed computed contrast checks. Full keyboard navigation, 200% text zoom, physical-phone camera capture and active packing-form interactions still need verification.

The owner photo queue now defaults to pending updates, with a history checkbox. Loading no longer flashes an empty store. A search with no matches explains the result and offers a working reset. Optimized builds and 68 boundary tests pass. Current evidence: `local-vision-corpus.json`, `local-vision-live-summary.json`, `local-vision-six-photo-final.log`, `browser-qa-summary.json`, `browser-contrast-summary.json`, `primary-photo-live-summary.json`, and `local-photo-boundary-unit.log`.

The final optional-worker outage regression also passed the full simulator checkout, packing-stage/shortage/replay and refund flow with the new gateway. The confirmed online allocation returned to 12. The fallback draft was rejected and the worker restored (`local-vision-worker-regression.log`). The primary-photo selector and saved selection were checked on the narrow responsive interface, including keyboard focus (`mobile-primary-photo-review.png`).
