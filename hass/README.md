# Hass tooling

Private owner-assistant tooling for the Avocado Shack site. Plan: [docs/hass](../docs/hass/README.md).

## H01: one validated content source

`hass/content/` is the single editable source for site content. Edit it, never the generated files.

| Source | Contents | Generates |
| --- | --- | --- |
| `content/products.json` | Catalog records with `status` `active`, `hidden` or `held`. Held records keep their `hold` reason/source. | `storefront-mockup/catalog-products.js` (active only, public fields only) |
| `content/makers.json` | Maker profiles keyed by `producerKey`, with https source links | `storefront-mockup/producers.js`, `storefront-mockup/producers.json` |
| `content/community.json` | Club details, real events (empty until Michael confirms one) and undated route ideas | `storefront-mockup/community.json` |
| `content/store.json` | Store name, street address, town and opening-hours lines | Store slots in `storefront-mockup/index.html` and `hike/index.html` |
| `templates/index.html`, `templates/hike/index.html` | Page layout with `{{store.*}}` slots | The two pages above |

Not generated: `held-products.json` stays as the historical hold evidence (its sample prices are not copied into the source), and `hiking-preview.json` keeps the labelled sample invitation separate from real events.

Validation is closed: unknown fields are rejected, so prices, units, baskets and similar commerce fields cannot enter the source. Text fields reject markup and `$`; links must be https; categories must match the site filters; `producerKey` must name a maker; active images must exist; events need an exact start with UTC offset, `America/Los_Angeles`, a known status, a meeting point when RSVPs are on and a positive capacity. Route ideas stay undated with RSVPs off, and sample ids cannot become events. Records keep their own field order so the output stays byte-identical.

```sh
python3 hass/sitegen.py --check        # generated site files match the source (CI)
python3 hass/sitegen.py --write        # regenerate after editing hass/content
python3 hass/sitegen.py --out DIR      # render into a scratch directory
python3 hass/migration_check.py        # H01 migration invariants (CI via the tests)
python3 -m unittest discover -s hass/tests -t . -v
```

`content/migration-baseline.json` is the frozen record of the site at the migration commit: 170 listing ids, 26 maker keys, 30 source links and the 2 held ids, plus the SHA-256 of the pre-migration site files. The migration check fails if a baseline listing is deleted (hiding is allowed), a maker or source link disappears, a held product leaves `held` or appears in the catalog, or a committed site file differs from the generated output. It also reports whether the output is still identical to the pre-migration files.

Tests write only to temporary directories; they never touch the checkout, the live service or the community database.

## H02: private typed editing service

`hass/editor.py` turns typed operations into a validated draft and applies one approved draft as a single writer. There is no HTTP or socket listener; the only callers are the Python API and the CLI, run as the same OS user. The production op registry (`hass/ops/`) is empty until later units add modules exporting `OPS`.

- Request: JSON `{"ops": [{"op": "<name>", "args": {...}}]}`, at most 64 KiB and 1–20 ops, no other keys. Argument kinds are closed: `id`, `maker_key`, `text`, `text_list`, `url` (https), `enum`, `bool`, `int`, `date`, `time`, `image`. Unknown ops/args, wrong kinds, markup or `$` in text and control characters give `invalid`; a missing required argument gives `needs-details`. No paths, commands, SQL or free-form values.
- `prepare` validates the edited content, renders the site and stores `<state>/drafts/<change_id>.json` (0600) bound to `content_revision` (SHA-256 over the four content files and two templates). Same ops on the same revision give the same `change_id`/`draft_hash`. The worktree is not written.
- `apply` takes `<state>/writer.lock` (held → `busy`), refuses the main checkout, branch `main`, a detached HEAD, a dirty worktree or a missing Git identity, and returns `stale` when the revision moved. It writes only `hass/content/{products,makers,community,store}.json` and the 6 generated files, runs `sitegen --check` and the migration check, and commits `hass content: <change_id>` with a sign-off. No push. A second apply returns `already-applied`; a failed check restores the owned files from HEAD and records `failed`.
- `recover` (also run before every apply) first refuses the main checkout, branch `main` and a detached HEAD without writing, then settles journals left by an interrupted write: committed → `applied`, HEAD still at base → files restored and `failed`. It never re-applies: applying a `failed` change returns `failed` again, and preparing the same ops again yields a new `change_id`/`draft_hash` that needs a new approval.

```sh
python3 hass/editor.py init --state DIR --worktree WT    # WT: linked worktree on its own branch
python3 hass/editor.py prepare REQUEST.json --state DIR
python3 hass/editor.py apply CHANGE_ID --hash DRAFT_HASH --state DIR
python3 hass/editor.py show CHANGE_ID | recover | ops   # --state DIR or HASS_STATE_DIR
```

The state dir must be owned by the current user, mode 0700 and outside the repository and the writer worktree; otherwise every command exits 2. Exit codes: 0 `ok`/`applied`/`already-applied`, 1 any other result, 2 usage or unsafe state dir.

## H03: product and maker ops

`hass/ops/catalog.py` adds eight typed ops to the registry: `product.add|edit|hide|restore` and `maker.add|edit|hide|restore`, plus a read-only `lookup(content, "product"|"maker", query)`. Ops take exact ids/keys only; an ambiguous name is resolved with `lookup` first (`{"match": id}` for one hit, `{"candidates": [...]}` for none or several, at most 10).

- "Remove" means hide. No op deletes a product or maker; hidden products keep their record and image and `product.restore` brings them back.
- Held products (`photo-product-040`, `-133`) are refused by every op with the recorded reason and source. Releasing a hold is not an op.
- `product.add` takes the next id above the highest (never reuses a gap), status `active`, `producerKey` `null` unless given. `product.edit` changes only the named fields; `clearProducer` sets `producerKey` to `null`.
- A maker may carry an optional `"hidden": true`. `maker.hide` is refused while an active product names the maker (the reason lists the ids); hidden makers are left out of `producers.js` and `producers.json`, and an active product may not name one.
- An add or edit that makes a product newly match the shop's organic rule (name contains "organic", or maker Ocean Ranch, Straus, Green Gold or Massa Organics) gets the draft warning `adds Organic badge to <id>`; the owner decides at approval.
- Facts (names, places, stories, links, organic status) come only from the arguments; there are no price, stock or basket fields.

## H04: real-hike ops

`hass/ops/hikes.py` adds `hike.create|update|cancel|complete`. Every event field comes from the arguments: nothing is copied from a route idea or `hiking-preview.json`, and there is no `id` argument, so a sample or route-idea id can never become an event. `trailId` only links to a route idea.

- The start is the local `date` + `time` in `America/Los_Angeles`, written with its offset (`2026-12-05T09:00:00-08:00`). A time that happens twice (DST ends) or not at all (DST starts) gives `needs-details` on `time`; a start in the past is `refused`. A new `date` keeps the local time, a new `time` keeps the local date.
- With `rsvpEnabled` true, `hike.create` needs exactly one of `capacity` or `noCapacityLimit: true`. `hike.update` with `capacity` reads `guest_counts(settings["guestCountsDb"])` (read-only SQLite, seat totals only, no names or emails) and refuses a capacity below the confirmed guests; an unset or unreadable database is refused (`guest count unavailable`). Existing RSVPs are never changed.
- `hike.cancel` and `hike.complete` (only once the start has passed; optional `recap`) work on `scheduled` events; a cancelled or completed event refuses every later op.
- No op sends, queues or drafts a message, and `club.emailConnected` stays `false`. Real hikes need the owner's confirmed details; the committed events list stays empty.

## H05: approval state machine and fixture conversation

`hass/conversation.py` turns owner messages into H02 drafts and applies a draft only after an approval bound to sender, chat, change id, draft hash, base revision and expiry. The interpreter (replaceable; only `FixtureInterpreter` exists) returns typed ops, a question or "unsupported"; it never sees approvals and never calls the editor. A fixture is not iMessage: no messaging integration exists yet.

- Settings in `<state>/config.json` `settings`: `ownerSenders` (non-empty list), `ownerChat`, `approvalTtlSeconds` (int ≥ 60). Missing or invalid → `ConfigError`; there are no defaults. Real addresses are configuration, never committed.
- Store `<state>/conversation.sqlite3` (0600): `messages`, `drafts`, `approvals`, `outbox`. Duplicates, `fromMe` echoes, edited messages and anything not from an owner sender in the owner chat get no reply and no state change; for those only the message id and disposition are stored, never the text.
- `yes|approve|approved` / `no|cancel|reject` (optionally `+ code`) act only on one `proposed` draft; several → the reply lists the codes. Expired, replaced or cancelled codes are named and nothing is written. A code is never reissued: repeating a closed draft (same hash) gets a new code and needs `yes <new code>`, so a late `yes` or `yes <old code>` writes nothing. Stale base → `rejected` (`stale`) and a new proposal that needs its own `yes`.
- Draft states: `needs-details → proposed | rejected`, `proposed → approved | rejected | expired`, `approved → applied | failed | rejected (stale)`, `applied → verified | reverted`; anything else raises.
- Each result and its reply are committed before `flush(adapter)` sends; a failed send leaves the reply queued. On start `recover()` settles drafts left `approved` from the H02 change record (`applied` or `failed`) and never applies again.

```sh
python3 hass/fixture_chat.py --state DIR --fixture hass/tests/fixtures/conversation-basic.jsonl --interpreter MAP.json
```

Prints the outbox as JSON lines (sends nothing anywhere); exit 2 for an unsafe state dir or missing settings.

## H06: preview, history and undo

`hass/preview.py` copies the writer worktree's tracked `storefront-mockup` files to a temp dir (assets symlinked), lays the rendered files over them, starts that copy's `community-server.py` on a free `127.0.0.1` port with a fresh empty temp database and only `PATH`/`HOME`, and runs `hass/screenshot.cjs` (Chromium, 390×844). The browser may only GET from the preview origin; any POST or other host is aborted. The server is always stopped and the copy removed; PNGs are written 0600 to `<state>/screenshots/`, never into Git.

- Given a `previewer` (`Conversation(..., previewer=Previewer(worktree))`), every proposal carries `<change_id>-proposal.png` (a failed capture adds `Preview unavailable: <error>` and still proposes). After an apply, `verify()` needs current generated files, `migration_check` passing and the result screenshot's checks passing (the product card and its description, a scheduled hike's title, every hours line, no page error): then `verified` and `Applied and checked <code>` + PNG; otherwise the draft stays `applied` with `not verified: <error>` and the reply says the preview check failed. Nothing is re-applied. Without a previewer the H05 behaviour is unchanged (`fixture_chat.py` has none yet).
- `history` replies the last 5 drafts (code, state, summary, short commit); `python3 hass/editor.py history --state DIR [--limit N]` prints change records newest first as JSON lines (ops, commit, `revertedBy`).
- `undo` (newest applied draft) or `undo <code>` proposes `history.revert`, which needs its own `yes`. It sets back only that change's records, and only while each still holds the value the change wrote (else `conflict: <collection> <key> changed after <change_id>`, no draft). An added product/maker/hike is hidden/cancelled, never deleted. The editor then sets `revertedBy` and the original draft becomes `reverted`. No repository reset, no `git revert`, no community-DB restore.

Browser tests (`hass/tests/test_preview.py`) skip only when `PLAYWRIGHT_MODULE` is unset. On Agent Orange:

```sh
export PLAYWRIGHT_MODULE=/home/user/.hermes/hermes-agent/node_modules/playwright
export CHROMIUM_PATH=/home/user/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell
```
