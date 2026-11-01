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
A read or decode error gives one stderr line `sitegen: io error: <ExcName>` (or `migration_check: ...`) and exit 2, never a path or file bytes; `--write`/`--out` refuse a symlinked generated file.

Tests write only to temporary directories; they never touch the checkout, the live service or the community database.
`hass/tests/test_output_hygiene.py` (H21) checks on fixture canaries that `fixture_chat`, `health`, `statebackup` and `editor history` output carries no sender or message text.

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
A CLI read or decode error prints `{"result": "io-error", "problems": ["<ExcName>"]}` (class name only) and exits 2; library calls still raise.

## H03: product and maker ops

`hass/ops/catalog.py` adds eight typed ops to the registry: `product.add|edit|hide|restore` and `maker.add|edit|hide|restore`, plus a read-only `lookup(content, "product"|"maker", query)`. Ops take exact ids/keys only; an ambiguous name is resolved with `lookup` first (`{"match": id}` for one hit, `{"candidates": [...]}` for none or several, at most 10).

- "Remove" means hide. No op deletes a product or maker; hidden products keep their record and image and `product.restore` brings them back.
- Held products (`photo-product-040`, `-133`) are refused by every op with the recorded reason and source. Releasing a hold is not an op.
- `product.add` takes the next id above the highest (never reuses a gap), status `active`, `producerKey` `null` unless given. `product.edit` changes only the named fields; `clearProducer` sets `producerKey` to `null`.
- A maker may carry an optional `"hidden": true`. `maker.hide` is refused while an active product names the maker (the reason lists the ids); hidden makers are left out of `producers.js` and `producers.json`, and an active product may not name one.
- An add or edit that makes a product newly match the shop's organic rule (name contains "organic", or maker Ocean Ranch, Straus, Green Gold or Massa Organics) gets the draft warning `adds Organic badge to <id>`; the owner decides at approval.
- A `maker.edit` that changes `place` drafts as usual with one warning: `changes the "Based in" line on N active product card(s) of maker <key> (town search follows it)`, or `maker <key> has no active products; no product card changes`. Hidden and held products are not counted; an unchanged `place` never warns.
- Facts (names, places, stories, links, organic status) come only from the arguments; there are no price, stock or basket fields.

## H04: real-hike ops

`hass/ops/hikes.py` adds `hike.create|update|cancel|complete`. Every event field comes from the arguments: nothing is copied from a route idea or `hiking-preview.json`, and there is no `id` argument, so a sample or route-idea id can never become an event. `trailId` only links to a route idea.

- The start is the local `date` + `time` in `America/Los_Angeles`, written with its offset (`2026-12-05T09:00:00-08:00`). A time that happens twice (DST ends) or not at all (DST starts) gives `needs-details` on `time`; a start in the past is `refused`. A new `date` keeps the local time, a new `time` keeps the local date.
- With `rsvpEnabled` true, `hike.create` needs exactly one of `capacity` or `noCapacityLimit: true`, and so does `hike.update` when it turns RSVPs on for an event without a capacity. `hike.update` with `capacity` reads `guest_counts(settings["guestCountsDb"])` (read-only SQLite, seat totals only, no names or emails) and refuses a capacity below the confirmed guests; an unset or unreadable database is refused (`guest count unavailable`). Existing RSVPs are never changed. A `capacity` given while RSVPs are off is kept but adds the draft warning `<id>: RSVPs are off, so capacity N has no effect until RSVPs are turned on`, and turning RSVPs on with a stored capacity (none given) adds `<id>: RSVPs turned on with the stored capacity N`; neither is refused.
- `hike.update` with `clear: [names]` deletes those optional fields (any hike text except `meetingPoint`, or `trailId`) in the same draft as any set fields. A name that is not a hike field (`clear: <name> is not a hike field`), a field that can never be removed (title, date, time, meetingPoint, RSVPs, capacity: `clear: <name> cannot be removed`; use `noCapacityLimit` for capacity) or one also set (`<name> cannot be set and cleared together`) is refused; clearing only absent fields changes nothing.
- `hike.cancel` and `hike.complete` (only once the start has passed; optional `recap`) work on `scheduled` events; a cancelled or completed event refuses every later op. `hike.cancel` or `hike.update` turning RSVPs off on an event with confirmed guests adds the draft warning `<id> has N confirmed guests; nobody is notified automatically` (`<id> guest count unavailable; check RSVPs before approving` when the count cannot be read) and is never refused for it; `hike.update` moving such an event's date or time adds `<id> moves to <YYYY-MM-DD HH:MM> Pacific; N confirmed guests are not told automatically` instead (only the RSVPs-off warning when the same request turns RSVPs off).
- No op sends, queues or drafts a message, and `club.emailConnected` stays `false`. Real hikes need the owner's confirmed details; the committed events list stays empty.

## H05: approval state machine and fixture conversation

`hass/conversation.py` turns owner messages into H02 drafts and applies a draft only after an approval bound to sender, chat, change id, draft hash, base revision and expiry. The interpreter (replaceable; only `FixtureInterpreter` exists) returns typed ops, a question or "unsupported"; it never sees approvals and never calls the editor. A fixture is not iMessage: no messaging integration exists yet.

- Settings in `<state>/config.json` `settings`: `ownerSenders` (non-empty list), `ownerChat`, `approvalTtlSeconds` (int ≥ 60). Missing or invalid → `ConfigError`; there are no defaults. Real addresses are configuration, never committed.
- Store `<state>/conversation.sqlite3` (0600): `messages`, `drafts`, `approvals`, `outbox`. Duplicates, `fromMe` echoes, edited messages and anything not from an owner sender in the owner chat get no reply and no state change; for those only the message id and disposition are stored, never the text.
- `yes|approve|approved` / `no|cancel|reject` (optionally `+ code`) act only on one `proposed` draft; several → the reply lists the codes. Expired, replaced or cancelled codes are named and nothing is written. A code is never reissued: repeating a closed draft (same hash) gets a new code and needs `yes <new code>`, so a late `yes` or `yes <old code>` writes nothing. Stale base → `rejected` (`stale`) and a new proposal that needs its own `yes`.
- Draft states: `needs-details → proposed | rejected | expired` (a question lapses after `approvalTtlSeconds` like a proposal; an answer refreshes it, a later one starts a new request), `proposed → approved | rejected | expired`, `approved → applied | failed | rejected (stale)`, `applied → verified | reverted`; anything else raises.
- Each result and its reply are committed before `flush(adapter)` sends; a failed send leaves the reply queued. On start `recover()` settles drafts left `approved` from the H02 change record (`applied` or `failed`) and never applies again.

```sh
python3 hass/fixture_chat.py --state DIR --fixture hass/tests/fixtures/conversation-basic.jsonl --interpreter MAP.json
```

Prints the outbox as JSON lines (sends nothing anywhere); exit 2 for an unsafe state dir or missing settings.
Every fixture line is checked before anything is handled or queued: a bad line exits 2 with `fixture_chat: fixture line <n>: <field> <rule>`, naming the field, never its value.

## H06: preview, history and undo

`hass/preview.py` copies the writer worktree's tracked `storefront-mockup` files to a temp dir (assets symlinked), lays the rendered files over them, starts that copy's `community-server.py` on a free `127.0.0.1` port with a fresh empty temp database and only `PATH`/`HOME`, and runs `hass/screenshot.cjs` (Chromium, 390×844). The browser may only GET from the preview origin; any POST or other host is aborted. The server is always stopped and the copy removed; PNGs are written 0600 to `<state>/screenshots/`, never into Git.

- Given a `previewer` (`Conversation(..., previewer=Previewer(worktree))`), every proposal carries `<change_id>-proposal.png` (a failed capture adds `Preview unavailable: <error>` and still proposes). After an apply, `verify()` needs current generated files, `migration_check` passing and the result screenshot's checks passing (the product card and its description, a scheduled hike's title, every hours line, no page error): then `verified` and `Applied and checked <code>` + PNG; otherwise the draft stays `applied` with `not verified: <error>` and the reply says the preview check failed. Nothing is re-applied. Without a previewer the H05 behaviour is unchanged; `fixture_chat.py --preview` runs a fixture with the writer worktree's previewer.
- `history` replies the last 5 drafts (code, state, summary, short commit); `python3 hass/editor.py history --state DIR [--limit N]` prints change records newest first as JSON lines (ops, commit, `revertedBy`).
- A change record that cannot be read is listed by `editor.py history` as `state` `unreadable` with `ops: []`; the other records are unchanged.
- `undo` (newest applied draft) or `undo <code>` proposes `history.revert`, which needs its own `yes`. It sets back only that change's records, and only while each still holds the value the change wrote (else `conflict: <collection> <key> changed after <change_id>`, no draft). An added product/maker/hike is hidden/cancelled, never deleted. The editor then sets `revertedBy` and the original draft becomes `reverted`. No repository reset, no `git revert`, no community-DB restore.

Browser tests (`hass/tests/test_preview.py`) skip only when `PLAYWRIGHT_MODULE` is unset. On Agent Orange:

```sh
export PLAYWRIGHT_MODULE=/home/user/.hermes/hermes-agent/node_modules/playwright
export CHROMIUM_PATH=/home/user/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell
```

## H13: store hours and address

`hass/ops/store.py` adds `store.set_hours` and `store.set_address` to the registry; they go through the normal draft, approval and single-writer path and change only `content/store.json` (and so the store slots of the generated pages).

```json
{"ops": [{"op": "store.set_hours", "args": {"hours": ["Monday–Saturday 9am–6pm", "Closed Sunday"]}}]}
{"ops": [{"op": "store.set_address", "args": {"streetAddress": "100 Example Street"}}]}
```

- `store.set_hours` takes `hours` (a text list) and replaces all lines. Refused: more than 7 lines, a line over 60 characters (`hours line <i>` counts from 0), a repeated line, or hours equal to the current ones.
- `store.set_address` takes `streetAddress` and/or `town`; only the given fields change. No argument gives `needs-details` (`streetAddress`, `town`); a value over 80 characters or an unchanged address is refused.
- `name` and `schemaVersion` are not arguments (unknown argument → `invalid`). Text kinds reject markup, `$` and control characters as usual.
- Undo: the store is one record, so `undo` of an older store change after a later one gives `conflict: store store changed after <change_id>`; undo the newest first.

Limits: H13 is partial; home-page copy and image slots are not built.

## H17: status, pause and resume (with H14 guest totals)

`hass/conversation.py` treats a whole message `status`, `pause` / `pause changes` or `resume` / `resume changes` as a command (lower case, trailing `.`/`!` ignored, as for `yes`); anything longer, such as `pause the hike`, goes to the interpreter. Only owner senders in the owner chat are heard, as in H05.

- `pause changes` stores one `control` row in the conversation store (the table is created by the first pause) and survives restarts. While paused, drafts are still prepared and each proposal ends with `Changes are paused; send resume changes before yes.`; an approval for one draft gets `Changes are paused; <code> was not applied. Send resume changes, then yes <code>.` and writes no approval, moves no state and keeps the expiry. `no`/`cancel` still work; undo drafts are gated the same way. A second pause answers `Changes are already paused (since …).`
- `resume changes` removes the row and lists the codes still waiting; it never applies anything. When not paused it answers `Changes are not paused.`
- `status` is read-only (even a lapsed proposal is only hidden, not expired): `Changes: on` or `Changes: paused since …`, each waiting or needs-details draft (or `Nothing is waiting for approval.`), `Last change: <code> <state>: <summary> (<commit7>)` with the failed or `not verified: …` reason, and for every upcoming scheduled hike `Hike <title> <local start>: <n> confirmed of <capacity|no limit>` (`RSVPs off` for a hike without RSVPs).
- Guest totals come from `hikes.guest_counts(settings["guestCountsDb"])`, an optional setting in `<state>/config.json` (seat totals only, no names or emails). Unset, missing or wrong-schema database → `guest count unavailable`, never 0; unreadable worktree content → `Hikes: unavailable`.
- `hass/health.py --seen FILE` still prints its one JSON line when that file cannot be written (full disk, read-only folder): `notify` is true and `info` holds `seen file not updated`, with no path.

Limits: H17 and H14 are partial. The support path for each health problem is `docs/hass/SUPPORT.md`.

## H20 prep: private state backup and restore drill

`hass/statebackup.py` backs up a settled state dir, checks a backup and restores it into a new state dir for a drill. It prints one JSON line; exit 0 `ok`, 1 any other result, 2 unsafe dir or usage (`unsafe-state`).

```sh
python3 hass/statebackup.py create --state DIR --out DIR      # OUT: existing dir of yours, mode exactly 0700
python3 hass/statebackup.py list --out DIR                    # read-only, before verify/restore: each hass-state-* entry, newest first
python3 hass/statebackup.py verify BACKUP
python3 hass/statebackup.py restore BACKUP --into DIR --worktree WT   # WT: a separate drill worktree
```

- `create` writes `<out>/hass-state-<UTC stamp>/`: `config.json`, `drafts/`, `changes/`, `screenshots/` (0600/0700), SQLite online-backup snapshots of `inbox.sqlite3` (the H16 queue, when present; taken first) and then `conversation.sqlite3`, and `MANIFEST.json` (SHA-256 per file) last; `writer.lock` is never copied. Refused: `out` missing, not 0700, or inside the state dir, the repository or the writer worktree (exit 2); a symlinked or odd `config.json`/`writer.lock` before either is opened, any symlink or unknown entry (`refused`, each named); a held writer lock (`busy`); a pending journal (`unsettled`, run `editor.py recover` first); an existing backup dir of the same stamp (`exists`).
- `create` builds in a dot-named `.hass-state-<stamp>.partial-<pid>` folder and renames it to `hass-state-<stamp>` only after `MANIFEST.json` is written, so a failed run leaves no `hass-state-*` folder and the stamp stays free.
- `verify` checks the manifest layout, every hash and mode, unlisted files and symlinks and `PRAGMA integrity_check`; damage gives `corrupt` naming the file.
- `restore` verifies first, refuses an existing `--into` (left untouched), the recorded writer worktree (an attended operation) and a worktree that fails the editor checks, builds the new state dir beside `--into` and renames it into place. Only `config.json` `worktree` is rewritten.

No network, no Git writes, no deletion of source data. Limits: drill on isolated copies only; no live restore, scheduling, retention, off-box copy or encryption.

## H08 prep: bridge adapter (fixtures only)

`hass/bridge.py` is tested only against synthetic fixtures (`hass/tests/fixtures/bridge/`). Nothing here listens, connects to a Mac or BlueBubbles, or sends a message; there is no CLI or config key.

- `normalize(event)`: a BlueBubbles `new-message` / `updated-message` webhook event becomes an `Inbound` (`kind` `new` / `edited`, `isFromMe` → `from_me`, `dateCreated` ms → UTC `received_at`), or a `Drop` naming why: `unsupported-event`, `group-or-unknown-chat` (only one `iMessage;-;…` chat passes), `attachments-not-supported` (H10/H12) or `malformed`. The owner filter stays in `Conversation`, which records an `updated-message` reusing a seen guid as `duplicate`.
- `seal()` / `unseal()`: Mac → Agent Orange envelope `{v, ts, nonce, body, mac}`, HMAC-SHA256 over canonical JSON with a key of at least 32 bytes. `unseal` raises `EnvelopeError` `shape`, `version`, `mac`, `stale` (more than 300 s off) or `replay` (nonce already in `seen`); only a valid envelope adds its nonce (BL-AV-4 persists `seen`).
- `BlueBubblesSender(base_url, password_file)`: an `Outbox` adapter that POSTs `/api/v1/message/text` (`chatGuid`, fresh `tempGuid`, `message`, `method: apple-script`) to `http(s)://127.0.0.1|localhost:<port>` only, without proxies or redirects. The password file must be a regular 0600-style file (no group/other access) and is read per send. Failures raise `BridgeError(code, status, path)`; no error carries the URL, query string or password. A reply with attachments (the H06 preview PNG) is sent as its text plus one fixed `PICTURE_NOTE` line, so the outbox moves on; the picture is never read or sent and stays in the private state dir. Inbound attachments are still dropped by `normalize`.

## H16 part: durable inbound queue

`hass/inbox.py` `Inbox(state_dir, start_at=None)` keeps `<state>/inbox.sqlite3` (0600) next to the conversation store. Every inbound message is written there before any processing; nothing is backfilled as a command.

- **Start point.** The first open must pass `start_at` (timezone-aware ISO-8601) and records it; later opens reuse it, and a different value raises `start point already recorded as <iso>`. The module never moves it.
- `enqueue(msg)` → `queued`, `duplicate` (id already stored, nothing changes) or `history` (received before the start point; only id and time are kept, it never becomes a command). A `received_at` that is empty, has no zone or is not a date raises `ValueError` and stores nothing.
- `drain(conversation)` hands pending messages to `Conversation.handle` in `(received_at, provider_id)` order and marks each `done` with its disposition only afterwards. A crash in between re-delivers the message and `Conversation` answers `duplicate` without a second write; an exception stops the drain and leaves that message and later ones pending.
- Payloads are erased once a message is done (history rows never store one); retention periods stay H21.
- `seen()` is the persistent nonce set for the bridge envelope (`bridge.unseal(..., seen=inbox.seen())`), so a replayed envelope is refused after a restart; nonces older than one day are pruned when a new one is recorded.

No worker, timer, CLI or live adapter: fixtures only.

## Retention report (H21)

`python3 hass/retention.py report --state DIR --days N [--media ROOT] [--backups DIR]` prints one JSON line: how many inbox and conversation rows, outbox replies, drafts, screenshots, photo originals (and web copies) and state backups are older than N days, with the oldest kept date of each. `--days` is required (a whole number ≥ 1).

- Read-only: SQLite opens with `mode=ro`, nothing is created, written or deleted (`"deletes": 0`). No ids, text or file names are printed.
- A missing or unreadable store reports `"unavailable"` (exit 1); an unsafe path (missing, symlink) exits 2. A photo whose sidecar has no `received_at` counts as `undated`, never guessed.
- The owner picks the retention period (owner action 4). Nothing deletes or prunes yet; that is a later unit.
