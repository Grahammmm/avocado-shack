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
