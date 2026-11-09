# Hass and Clover: items and stock straight from the till (HASS-CLOVER-1)

**Status: design plus a fixture-tested prototype. Nothing is wired into the running Hass service. No credential, no network call and no live data exist in this change.**
G decided on 2026-11-09 that Hass talks to Clover directly so that Mike (the owner) can make SKUs and manage inventory by text. This page is the
design (the seven questions, one chosen answer each) and describes the code in `hass/clover/`. It builds on `reports/hass/SKILLS-SPEC.md`
(5.2 asked these questions; the answers are mapped at the end) and `docs/hass/TASKMAP.md` (T26 "Price change", gated until Clover).

## Credential rule (read this first)

G's standing fleet rule is that no agent handles credentials; this design keeps its spirit.

* The Clover API token is created by **G himself** and put by **G himself** into **one file** on AgentOrange (steps in "What G does", below).
* The only program that ever reads the file is the **Hass service** (a deterministic program, never an LLM worker). The code that reads it is
  `hass/clover/credential.py`, and it is the only code that holds the value.
* **No worker, reviewer, operator session, card body, comment, log, test fixture, error message or chat may contain, read or print the token or the
  file's content.** Tests use a made-up fake token and recorded fixtures; a test fails if a token-shaped string appears in a fixture.
* The module reads the token's **path** from the host/state settings (`tokenFile`), never the token itself.
* Before reading, the module checks on the open descriptor that the file is a regular file (no symlink), **owned by the service user**, mode **exactly 600**,
  not empty or larger than 512 bytes, in a folder only that user can write to. Any other state is refused with one fixed reason word
  (`unreadable`, `not-regular`, `owner`, `mode`, `folder`, `size`, `format`); the reason never contains the path or any bytes.
* The `Token` object prints as `Token(<redacted>)`, cannot be pickled, copied or inspected, and the Authorization header exists only inside the request
  handed to the HTTP layer. Request headers print as names only. **No code path logs a header.** A foreign error message (a transport failure, a Clover
  error body) is never repeated: the client reports a status number or a fixed phrase.
* A note on G's wording "root-only file": the Hass service runs as the owner's user account (`systemctl --user`), and a root-owned file is unreadable
  by it. So the file is owned by that service user, mode 600 (root can still read it; no other account can). If G wants a root-owned file, the alternative
  is a systemd `LoadCredential=` unit setting, which needs root and a decision from G; it is not chosen here.

## The seven answers in one line each

1. **Auth and scopes:** Clover Platform REST v3 with a *merchant-generated API token* (one merchant, internal tool), Bearer header; the token permission page only has coarse Read/Write per data category, so READ = *Inventory: Read* and every write kind = *Inventory: Write* (nothing else ticked); sandbox first, production only after a go-live card.
2. **Data model:** a private link table (`product id -> Clover item id + SKU`) keeps the site free of SKUs and prices; match by link, then the link's SKU, then **exact** name, never fuzzy for writes; one-sided items are reported, never auto-created.
3. **SKU:** `AS-<CAT>-<NAME up to 18>-<NN>`, e.g. `AS-PAN-SUNSHINE-OLIVE-OIL-01`; deterministic, issued once and never changed, collision-checked against every SKU and barcode in the till and again live right before the create.
4. **Write safety:** every write is a draft in plain words, needs the owner's `yes <code>` bound to the asker, daily cap, a big price move needs a second yes, no deletes (hide only), journalled before and after so `undo` restores, Clover decides price and stock, the site never shows a price; no checkout, payment, refund, discount or order calls exist.
5. **Inventory flows:** `how many X`, `low stock` (reads); `received 12 X`, `set X to 7`, `X sold out`, `new item: ...`, `change price of X to ...` (drafts); a count that reaches zero (or restarts from zero) carries the website's Sold out / Available word in the same draft, one yes.
6. **Sync:** read-only pull every 15 minutes plus on demand, a private cache, answers older than 20 minutes labelled "as of", "can't reach the till" when it is down, nothing quoted after 24 hours, writes never from cache; only items and stock are pulled, no sales or customer data, nothing leaves the box except the HTTPS calls to Clover.
7. **Rollout:** G makes a developer account, a sandbox merchant and a sandbox token; build cards follow on the sandbox; a go-live card (G approves) swaps in a read-only production token first and a write token only after a clean read-only week.

---

## 1. Auth and scopes

**API and token type.** Clover REST Platform API v3, JSON over HTTPS, `Authorization: Bearer <token>`, a `User-Agent` header (Clover's reference lists it as
required). Clover offers two token kinds: an *OAuth* token (needs a developer app, a site URL, a browser consent by the merchant, access tokens that expire in 30
minutes and a refresh token the program must rotate and store) and a *merchant-generated API token* made in the merchant's own dashboard. Clover's own FAQ recommends the
second for "internal tools or integrations where you control both the application and the merchant environment" and "if your integration is intended for only one
merchant". That is this case, and it keeps one static secret in one file instead of a rotating pair. **Chosen: merchant-generated API token.**
Open risk, to be settled in the sandbox and at go-live: Clover's pages describe these tokens mostly for test merchants, and say test-merchant tokens are for the
sandbox only ("do not use the test merchant API tokens in the production environment"; "production apps must use API tokens generated using the relevant OAuth flow").
So the **sandbox token and the production token are different tokens in different files**, and the go-live checklist includes a step where G confirms Mike's real dashboard
offers *Settings, Business Operations, API tokens*. If it does not, the fallback is a private OAuth app, which is a separate design and a G decision.

**Base URLs.** Sandbox `https://apisandbox.dev.clover.com`; production, North America, `https://api.clover.com`. The client has exactly these two hosts, builds every URL
itself, never follows a redirect (the real transport refuses 3xx, so the Authorization header cannot be sent to another host) and refuses any other host or scheme.

**Scopes.** Clover's token permissions are per data category and only Read or Write ("Each category of endpoints corresponds to either a Read or Write permission"). There is
no per-item or per-field scope, so *"the minimum for each write"* is the same single permission, and the limit between "set price" and "set stock" is kept in code (drafts,
the client's path allow-list), not by the token.

| Need | Clover permission to tick | Endpoints (all under `/v3/merchants/{mId}`) |
|---|---|---|
| Read items, stock, categories, tags | **Inventory: Read** only | `GET /items` (`expand=itemStock,categories,tags`, `limit` up to 1000, `offset`, `filter=modifiedTime>=ms`, `filter=sku=...`), `GET /items/{id}`, `GET /item_stocks`, `GET /item_stocks/{id}`, `GET /categories`, `GET /tags` |
| Create item | **Inventory: Write** | `POST /items` (required: `name`, `price` in cents), then `POST /category_items` to file it |
| Set price | **Inventory: Write** | `POST /items/{id}` with `{"price": cents}` |
| Set stock | **Inventory: Write** | `PUT /item_stocks/{id}` with `{"quantity": n}` (the item update cannot change stock: Clover says so) |
| Set SKU | **Inventory: Write** | `POST /items/{id}` with `{"sku": "..."}` |
| Hide / show (the only "remove") | **Inventory: Write** | `POST /items/{id}` with `{"hidden": true|false}` |

Never ticked: Customers, Employees, Merchant, Orders, Payments, Ecommerce, or anything else. So even a stolen token could not read sales or customers or take a payment.
Because Write is one indivisible permission, the production rollout uses **two token files**: a *read* token (Inventory: Read only) first, and a second *write* token
(Inventory: Read + Write) created only at the write go-live. Until the write file exists, Hass cannot change anything in the till however the code behaves.
Clover answers **401 for both a bad token and a missing permission** (its 401 page says so), so a permission mistake looks like "the till refused the key".

**What Hass writes to Clover.** `name`, `price` (cents), `priceType: FIXED`, `sku`, `hidden`, the item-category link, and the stock `quantity`. Never `code` (the barcode:
read, used for matching, never written), tax (the till's default applies and the draft says so), `cost`, `available` or `autoManage` (Clover manages those; Hass leaves them).

**Rate limits** (Clover, "API usage and rate limits"): **16 requests per second and 5 concurrent per token** (50/s and 10 concurrent per app); a breach is HTTP 429 with an
`X-RateLimit-...` header naming the limit, and a concurrency breach carries `Retry-After`. The client is synchronous (one request at a time), spaces requests at least 0.25 s
(4/s), retries 429 and 5xx up to 3 times (waiting `Retry-After` seconds, clamped to 1-30, else 1, 2, 4 seconds), then raises `RateLimited` (the reply says "the till is busy,
try again in a minute"). A normal day is a handful of requests every 15 minutes; the limits are not a design pressure.

**Sandbox.** All build and rehearsal use a Clover **sandbox test merchant** (created in the developer dashboard under *Test Merchants*; Clover provides a sample inventory file to
import). Live calls (production host) only after G approves a go-live card; the settings block refuses `environment: production` unless `liveApproved: true` is set, and a
go-live card, not code, sets it.

## 2. Data model

| Clover item field | Hass site product field | Rule |
|---|---|---|
| `id` | (none: kept in the private link) | the stable key for every write |
| `name` | `name` | **never synced**. The site's name and the till's name may differ; a mismatch is reported (`status`), not fixed |
| `sku` | (none: kept in the private link) | the site has no SKU by design; `sku` is a refused word in site text (`live_policy.COMMERCE_WORDS`) |
| `code` (barcode) | (none) | read-only to Hass; a matching aid |
| `price` (cents), `priceType` (`FIXED`, `VARIABLE`, `PER_UNIT`), `unitName` | **never** | prices stay off the site (AGENTS.md catalog-only scope; the live policy refuses price words). Variable-price items have no price to change |
| `categories` (names) | `category` (one of the nine site words) | a settings map `categoryMap` {site word: Clover category name}; Hass never creates a Clover category |
| `tags` | none | read and cached, used for nothing in v1 |
| `itemStock.quantity`, `stockAlertThreshold` | `available` (`yes` / `limited` / `no`) | **only** through an approved draft (see flow 5). The site never shows a count |
| `hidden`, `available`, `autoManage` | `status` (`active`/`hidden`/`held`) | different meanings (hidden on the Register vs. hidden on the website); a disagreement is reported, never copied |
| `modifiedTime` (ms) | (none) | the stale check and the incremental sync |
| `cost`, tax rates, modifiers, employee or customer fields | n/a | **dropped on read** (the mapper is a whitelist) |
| (none) | `brand`, `producerKey`, `description`, `image`, `displayBrand` | site-only; never sent to Clover |

**The link.** The private table `<state>/clover/links.json` (mode 0600, never in Git, rebuilt by `link` messages and by the SKU recorded at creation) holds
`{product id: {"cloverId": ..., "sku": ...}}`. A site product has no price, SKU or count and the content model is closed, so this table is the only place the two sides meet.

**Matching order** (`hass.clover.mapper.match`): (1) the stored link, (2) the SKU in that link when the item's id changed (item recreated), (3) the **exact** name, ignoring only
letter case, spacing and curly apostrophes (accents stay significant), and only when exactly one site product and exactly one till item hold that name. A name match is good for
reading; it is stored as a link only after Mike's `yes` to "link these?". Anything with two candidates is *ambiguous* and Hass asks Mike to name the SKU. A link whose item vanished is
*broken* and is reported, **not** repaired by name behind his back. **Writes never use anything looser than an exact SKU or an exact visible name** (`resolve_exact`); the "Did you
mean ..." help (`suggest`, every word of the query present in the name) is read-only and can never pick a write target. A hidden item is writable only by its exact SKU.

**One side only.**
* *On the till, not on the site:* listed on request ("on the till but not on the site: 14"). Hass never creates a site product from it; "put X on the site" starts the existing new-product flow with its own picture and words.
* *On the site, not on the till:* stock questions say "X is on the website but not in the till, so I have no count." Hass offers to add it to the till (Mike supplies the price; the draft is flow 6).
* *Broken or ambiguous link:* named, with the SKUs to choose from. No write happens until Mike names one.

## 3. SKU generation

Mike: "new item: Sunshine olive oil, 12.50, pantry". Hass reads it with a fixed pattern (no model), turns `12.50` into **1250 cents** by integer arithmetic (no floats; more than two decimals, zero,
negative or over $1,000.00 is refused with a plain sentence), checks `pantry` is one of the site's nine categories, and builds:

> Did you mean to add this to the till?
>   Item: Sunshine olive oil
>   SKU: AS-PAN-SUNSHINE-OLIVE-OIL-01 (made up by me, the next free number)
>   Price: $12.50 each
>   Category: Pantry
>   Count: not counted yet (say 'received 12 Sunshine olive oil' to start counting)
>   Tax: your till's usual setting; I set none
> Nothing goes on the website.
> Reply yes a1b2 to do this, or no a1b2 to drop it. Nothing changes until you say yes.

**Scheme** (`hass/clover/sku.py`): `AS-<CAT>-<NAME>-<NN>`.
* `AS` marks a SKU Hass made. `CAT` is three letters from the site category (fruit FRU, vegetables VEG, dairy DAI, eggs EGG, meat MEA, pantry PAN, drinks DRK, bread BRD, flowers FLW; anything else `GEN`).
* `NAME`: accents dropped, capitals, apostrophes removed (`Linn's` becomes `LINNS`), small joining words (the, a, of, and, ...) left out, cut at a word boundary to at most 18 characters.
* `NN`: the first of 01-99 not already used by **any** SKU **or barcode** in the till, hidden items included, compared ignoring case. At most 28 characters in all.
* **Deterministic:** the same name, category and till contents always give the same SKU. **Readable:** a person can tell what it is. **Stable:** a SKU is issued once and never regenerated: renaming an item
  or changing its category leaves it; Hass refuses to change a SKU that exists. **Unique:** checked against the cache when the draft is made and again against the live till (`GET /items?filter=sku=<sku>`)
  right before the create is sent; a clash there means a new draft with the next number, never an overwrite.
* **Duplicate name:** if the till already has a visible item with exactly this name there is no new SKU: "Sunshine olive oil is already in the till (SKU AS-PAN-SUNSHINE-OLIVE-OIL-01). Did you mean to change its price or its count?"
  A longer name that shortens to the same 18 characters ("Sunshine olive oil 1 litre") gets the next number (`-02`).
* "give X a SKU" (for an item already in the till with none) drafts the same scheme and only for an item with an empty SKU. 99 numbers used up for one short name is reported ("give the item a more specific name").
* Unknown until the sandbox rehearsal: Clover's maximum SKU length and whether it matches case-insensitively. The scheme stays well under any plausible limit and compares case-insensitively to be safe.

## 4. Write safety (money-adjacent)

* **Every Clover write is a draft** (`hass/clover/drafts.py`): plain words for the exact change (item, SKU, price before and after, count before and after), the exact Clover calls it would make, a journal record
  (`before`, `after`), and the stale-check values. Builders only build; nothing here sends anything.
* **Approval is the existing approval.** The conversation layer turns the draft into a proposal with a code; only the owner's `yes <code>` applies it, bound to sender, chat, change id, draft hash, base revision and expiry,
  exactly as for a site change (`docs/hass/COMMANDS.md`). A bare `yes`, a reaction, an edit or a `yes?` approves nothing. `stop changes` stops Clover writes too. A draft's id is `clv-` plus 12 hex of the SHA-256 of
  its full content, so a changed draft is a different draft and needs its own yes.
* **Daily cap:** at most `dailyWriteCap` Clover changes per Pacific day (default 20). Over the cap: "I have already made 20 changes to the till today, which is my daily limit. Nothing was changed. The count starts again at
  midnight Pacific." Checked when the draft is made and again at apply. `undo` is exempt (it only puts back what was there) but still needs its own yes.
* **Big price moves need a second yes.** A new price more than `priceConfirmPct` (default 25%) above or below the old one is flagged, tested exactly in integers (not on the rounded percentage). The draft says
  "that is a 36.0% increase ... I will ask once more after your yes"; the first yes produces a second proposal with a **new** code (a code is never reissued) and only that second yes applies.
  A price must be between $0.01 and `maxPriceCents` (default $1,000.00) as a typo guard.
* **No deletes, hide only.** There is no DELETE call anywhere in the code (a test checks every draft's methods are POST or PUT on `/items`, `/item_stocks` or `/category_items`). Taking an item off is `hidden: true`;
  "show it again" is `hidden: false`. A count record is never deleted either.
* **Journal and undo.** Before a call, the apply step writes an *intent* row (draft, before, after) to `<state>/clover/journal.sqlite3` (0600); after the call it reads the item back from Clover, compares, and settles
  the row `applied` or `failed`. A restart settles rows left `intent` by reading the item (the same idea as the editor's `recover`): it never applies twice. `undo` drafts the inverse (`build_undo`): old price,
  old count, old SKU, hidden flag back, or hide a created item. It **refuses to overwrite a newer value**: if the price, count or SKU changed again after the draft, Hass says so and asks what Mike wants.
  One honest limit: the first-ever count on an item that had none cannot be undone (that would be deleting the count record, which Hass never does); Hass says so and offers "set X to <number>".
* **Stale check at apply:** the item is re-read live; if its `modifiedTime` or its stock's `modifiedTime` moved since the draft (a sale decrements stock on its own), the draft is stale, nothing is written, and Mike gets a fresh draft
  that needs its own yes. "Received 12" is computed from the till's current count and shown as both numbers ("Count: 12 -> 24"), and the live re-read makes that arithmetic race-safe.
* **Clover is the source of truth for price and stock.** The site never shows a price or a count; the live policy still refuses price words in site changes (`COMMERCE_WORDS`, the "prices" protected sentences, the
  interpreter's `PRICE_REPLY`). Clover messages are parsed by fixed patterns **before** the interpreter, so a price Mike types for the till never enters a site draft, an interpreter prompt or the audit; a site operation
  produced by a Clover draft carries only a product id and one of the three availability words (a test checks no price, count or SKU can ride along).
* **No checkout, payment, refund, discount or order authority, ever.** The token has no Orders or Payments permission, the client's path allow-list has no such path, and the draft builders have no such kind. Adding one
  would be a new design, a new card and a G decision.
* **Data class `finance-local`.** Prices and counts are handled by local code only: no model writes a Clover reply or sees a Clover answer, and none of it is sent to a cloud model.

## 5. Inventory flows Mike can text

Clover commands are exact patterns; anything else still goes to the interpreter exactly as today. (Build card HASS-CLOVER-4 adds them to `COMMANDS.md`, `help` and the parser tests; this card changes none of those.)

| Mike texts | Kind | Hass replies | Also changes the website? |
|---|---|---|---|
| `how many Sunshine olive oil do we have` | read | `Sunshine olive oil: 12 in the till.` (labelled if old; a near name is a "Did you mean", never a guess) | no |
| `low stock` | read | `Sold out: ... Low (5 or fewer): Eggs, dozen 2. 1 item(s) have no count in the till, so I can't tell.` | no |
| `received 12 Sunshine olive oil` | write (set count = till count + 12) | `Add stock to ...? Count: 12 -> 24, Received: 12` + yes line | only if the site says Sold out: marks it **Available today** in the same draft |
| `set Sunshine olive oil to 7` / `... to 0` / `Sunshine olive oil is sold out` | write (set count) | `Set the count of ...? Count: 12 -> 7` or `Mark ... as sold out? Count: 12 -> 0` | at 0: marks it **Sold out** (if the site does not already say so); from 0 up, back to Available; otherwise no site change |
| `new item: Sunshine olive oil, 12.50, pantry` | write (create + category link) | the "Did you mean to add ..." draft in section 3 | no (a new till item is not on the site until Mike says "put it on the site") |
| `change price of Sunshine olive oil to 14.00` | write (set price) | `Change the price of ...? Price: $12.50 -> $14.00 each (+12.0%)`; a big move adds the second-yes line | **never** (the site shows no price) |
| `give X a SKU`, `hide X on the till`, `show X on the till` | write | the plain draft for that change | no |
| `undo` / `undo <code>` | write (inverse) | the restoring draft, or the reason it cannot | the site part is reversed in the same draft when the original had one |

Every write ends `Reply yes <code> to do this, or no <code> to drop it. Nothing changes until you say yes.` Reads work while paused and change nothing.
**One change, one yes:** "sold out on Clover marks sold out on the site through the EXISTING live path" means the draft carries the typed op `product.set_availability {id, available}` next to the Clover calls. One proposal,
one `yes <code>`. Apply order: Clover first (read back and journalled), then the site op through the normal editor and live-release path. If the Clover write fails, the site is not touched. If Clover succeeds and the site step
fails, Hass says exactly that ("The till is updated; the website is not yet - I'll try again / say 'retry'"); the next sync shows the difference and offers a draft to mark the site, never a silent change. `undo` reverses both.
The existing shelf-check rule is unchanged: when no shelf check is recorded for today, the existing question ("Before I change that, is the shelf list right for today?") comes first and the bundle waits for it.
**Precedence:** when a product is linked to a till item and Clover is reachable, a count message goes to the bundle above; when it is not linked, or the till is unreachable, the message follows today's site-only stock skill
unchanged. "Got more honey in" with a linked product asks "How many came in?" (a till count needs a number); "just mark it available" keeps the site-only path.

## 6. Sync, cache, staleness, privacy

* **Pull** (read-only, the client in section 1): every 15 minutes an incremental pull (`filter=modifiedTime>=` the last pull minus 2 minutes, `expand=itemStock,categories,tags`), plus a full pull nightly at 03:15 Pacific that replaces the
  cache (this catches items removed in the till). **On demand:** a question about one item re-reads that item first if the cache is over 5 minutes old; a write always re-reads the item live (at draft time and again at apply).
* **Cache:** `<state>/clover/cache.json` (0600, replaced atomically) holds the whitelisted item fields and the time of the pull, plus a short hash of the merchant id so a sandbox cache is never read as production. It is derivable
  (excluded from backups); the link table and journal are not (included). No `cost`, no sales, no customer or employee data exists in it.
* **Staleness label** (`hass/clover/reads.py`): up to 20 minutes old, answered as is; older, `(till count as of 3:09 pm)` (`Sun 4:30 pm` if not today); Clover unreachable: `I can't reach the till right now. The last count I have is from 2:00 pm,
  so treat it as old.` before the answer; over 24 hours old: no count is quoted at all ("I have not been able to read the till since Sun 2:30 pm, so I will not quote a count that old.").
* **When Clover is unreachable** (network down, 5xx after retries, 429 after retries, 401 after the token is revoked or expired): reads answer from the cache with the label above; **writes are refused** ("I can't reach the till, so nothing
  was changed") and a 401 is reported as a health problem to the operator by reason word only (the token is never mentioned). The site and the rest of Hass are unaffected.
* **Privacy:** only the six read endpoints above are ever called (the client refuses `/orders`, `/payments`, `/customers`, `/employees`, `/refunds`, anything else, any other method, any other host); sales and customer data are **never**
  requested; nothing leaves the box except the HTTPS requests to the Clover host, and no model is involved (section 4). Logs carry the path template and the status number only. `status` shows counts of items, never prices.

## 7. Rollout and who does what

| Step | Who | What |
|---|---|---|
| 0. This card | sonnet-coder, reviewer queued by the operator | design, `hass/clover/`, fixture tests, `docs/hass/CLOVER.md`. No credential, no network |
| 1. Accounts | **G** | Clover developer account, one sandbox test merchant (with Clover's sample inventory imported), one sandbox API token, stored as below |
| 2. HASS-CLOVER-2 (build) | worker | settings block `clover` in `<state>/config.json` (loader checks, host KEYS), `UrllibTransport`, cache, sync job, read commands, `status` line; **sandbox only**; health shows the credential reason word |
| 3. HASS-CLOVER-3 (build) | worker | apply step (intent row, live re-read, stale check, call, read-back, journal), undo, cap, second-yes; sandbox only |
| 4. HASS-CLOVER-4 (build) | worker | owner commands, `help`, `COMMANDS.md`, parser-before-interpreter wiring, the site bundle and its undo |
| 5. Sandbox rehearsal | worker + G reads | run section "Sandbox acceptance" with the sandbox token; evidence on the card |
| 6. Go-live card | **G approves** | see the checklist |

**Sandbox acceptance** (all unverified facts from Clover's pages that the rehearsal must prove): partial `POST /items/{id}` changes only the sent field; `POST /items` with `sku`; `POST /category_items` path and body; `PUT /item_stocks/{id}`
with `{"quantity": n}` sets (not adds) and works on an item with no stock record; `GET /items?filter=sku=` works; `sku: ""` clears a SKU; the SKU length limit and case rule; 401 vs 403 behaviour; 429 headers; paging
past 1000; a sale in the sandbox register changes the count (so the stale check fires); a hidden item stays listed; and that the only requests made are the six reads and the four writes (the transport's request log).

**Go-live checklist** (G approves each): (a) sandbox acceptance evidence reviewed; (b) G confirms Mike's real Clover dashboard has *Settings, Business Operations, API tokens* (else stop: OAuth fallback is a new design); (c) G creates a **production read token**
(Inventory: Read only), stores it in the production token file, and sets `environment: production`, `liveApproved: true` via a reviewed config change; (d) **read-only week:** sync and reads only, compared with the till by eye;
(e) G creates the **write token** (Inventory: Read + Write) and a second file; the daily cap starts at 5; (f) first live writes watched by G on one test item that Mike creates and hides; (g) revocation drill: G revokes the token in the Clover
dashboard and Hass shows the reason word and refuses writes; (h) the cap is raised to its normal value.

## What G does (the exact steps)

All of this is G's own hands; no worker, tool or chat sees the token. **Sandbox first.**
1. In the Clover **Global Developer Dashboard** create a developer account if there is none, then *Test Merchants*, create one (a sandbox test merchant) and import Clover's sample inventory.
2. *Launch Dashboard* on that test merchant, then **Settings, View all settings, Business Operations, API tokens, Create new token**. Name it `hass-sandbox`. Tick **only** the inventory permissions: **Inventory: Read** and **Inventory: Write**
   (the sandbox token is allowed both; the labels in Clover's page are "Read inventory" and "Write inventory"). Tick **nothing** for customers, employees, merchant, orders, payments or ecommerce. Create the token and keep the page open.
   (Clover suggests a dedicated Admin employee for generating tokens; do that.)
3. On AgentOrange, as the Hass service user, with `<state>` the `state` folder named in `host.json`:
   `install -d -m 700 <state>/clover`, then `umask 077; read -rs T; printf '%s' "$T" > <state>/clover/sandbox.token; unset T; chmod 600 <state>/clover/sandbox.token`
   (paste the token at the silent prompt; it is not echoed and not stored in shell history). Check with `ls -l <state>/clover/sandbox.token`: it must read `-rw-------`, owned by the service user, and nothing else may be printed or shared.
4. Give the **sandbox merchant id** (13 characters, shown in the dashboard URL; it is an identifier, not a secret) on the HASS-CLOVER-2 card.
5. Later, only at the go-live card: the **production read token** (Inventory: **Read** only, name `hass-read`, file `<state>/clover/production-read.token`), and after the read-only week the **write token** (Inventory Read + Write, name `hass-write`,
   file `<state>/clover/production-write.token`). Same mode 600, same owner. Never paste a token into a card, comment or chat.

## Mapping to the open questions in SKILLS-SPEC 5.2

1 POS: Clover. 2 Direction: read and, by approved draft, write items and stock only. 3 Source of truth: Clover for price and count; Hass content for words, pictures, makers; the site word follows only through an approved draft. 4 Identity: the private
link table, exact matching, one-sided items reported. 5 Prices on the site: never. 6 Approvals: the same owner `yes <code>`, a daily cap, a second yes for big price moves, no deletes. 7 Money/customer data: items and stock only; no sales,
customers or card data, ever. 8 Where processed: local code only; no model sees Clover data. 9 Credentials: G creates and installs one file; the service reads it; revocation drill at go-live. 10 Counts vs words: counts live in Clover; the site
shows a word. 11 Failure: cached answers labelled old, writes refused, nothing quoted after 24 hours. 12 Refunds, voids, shrink, spoilage: not pulled (they are sales data); a count can drift when sales happen, which is why every write re-reads first.

## The prototype in this change

`hass/clover/` (stdlib only; not imported by any live module): `credential.py` (token file check, `Token`, redaction), `client.py` (read-only client, injected transport, pacing, retries, allow-list), `transport.py` (the real HTTPS layer with host allow-list and
no redirects, never called by a test against a network; plus the replay layer the tests use), `mapper.py` (whitelist parse, cents maths, matching, exact resolve), `sku.py`, `config.py`, `drafts.py` (five write kinds plus undo), `reads.py` (read replies and
staleness). Tests: `hass/tests/test_clover_{credential,client,mapper,sku,drafts,reads}.py` on hand-written fixtures in `hass/tests/fixtures/clover/` (fake merchant `FAKEMERCH0001`, fake ids, fake token string); every test runs with sockets
patched so any network attempt fails the run. `python3 -B hass/acceptance.py` is unaffected.

## Sources (public Clover developer pages; retrieved 2026-11-09)

* Rate limits: https://docs.clover.com/dev/docs/api-usage-rate-limits
* Permissions (Read/Write per category; inventory endpoints): https://docs.clover.com/dev/docs/permissions
* Merchant-specific API tokens: https://docs.clover.com/dev/docs/gdp-create-merchant-specific-api-token and https://docs.clover.com/dev/docs/generate-a-test-api-token
* Test merchant id and token; sandbox only: https://docs.clover.com/dev/docs/merchant-id-and-api-token-for-development
* OAuth and tokens FAQ (merchant-generated tokens for internal tools; 30-minute OAuth tokens): https://docs.clover.com/dev/docs/oauth-and-tokens-faqs
* Base URLs, Bearer auth: https://docs.clover.com/dev/docs/making-rest-api-calls ; 401 behaviour: https://docs.clover.com/dev/docs/401-unauthorized
* Manage items (create, view with `expand=itemStock`, money in cents): https://docs.clover.com/dev/docs/managing-items-item-groups
* Reference: https://docs.clover.com/dev/reference/inventorygetitems (filters, `limit` max 1000), https://docs.clover.com/dev/reference/inventorycreateitem, https://docs.clover.com/dev/reference/inventoryupdateitem (cannot change stock),
  https://docs.clover.com/dev/reference/inventoryupdateitemstock, https://docs.clover.com/dev/reference/inventorygetitemstock
* Filters and expansion: https://docs.clover.com/dev/docs/applying-filters ; tags: https://docs.clover.com/dev/docs/managing-tags
* Item-category association (`POST /v3/merchants/{mId}/category_items`): named in Clover's reference index https://docs.clover.com/dev/reference/llms.txt; the path was read from a third-party mirror of the spec
  (https://skmtc.dev/clover/apis/platform-api/docs/v3/merchants/:mId/category_items/post), so it is on the sandbox acceptance list.

Limits of this research: only public pages were read, no Clover account was used, and the token-permission dialog itself (its exact checkbox labels) was not seen, only Clover's text about it. Where a fact came from a search excerpt rather than a full page it is
on the sandbox acceptance list above.
