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
- `recover` (also run before every apply) settles journals left by an interrupted write: committed → `applied`, HEAD still at base → files restored and `failed` (needs a new approval). It never re-applies.

```sh
python3 hass/editor.py init --state DIR --worktree WT    # WT: linked worktree on its own branch
python3 hass/editor.py prepare REQUEST.json --state DIR
python3 hass/editor.py apply CHANGE_ID --hash DRAFT_HASH --state DIR
python3 hass/editor.py show CHANGE_ID | recover | ops   # --state DIR or HASS_STATE_DIR
```

The state dir must be owned by the current user, mode 0700 and outside the repository and the writer worktree; otherwise every command exits 2. Exit codes: 0 `ok`/`applied`/`already-applied`, 1 any other result, 2 usage or unsafe state dir.
