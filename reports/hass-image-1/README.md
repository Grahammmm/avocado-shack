# HASS-IMAGE-1: photo polish test evidence

These tests ran on a scratch copy only (`~/agent-work/scratch/hass-image-1`), never on the live runtime. The six
input photos are generic scratch product photos.

Model route: Hermes' own `openai-codex` image plugin, signed in with ChatGPT/Codex OAuth. Hass holds no key.
`MODEL = "openai-codex:gpt-image-2-high"` in `hass/photo_polish.py`. Each call is an image edit of Mike's photo, not
text-to-image.

| Test | Result | Evidence |
|---|---|---|
| T1 contract (stub transport) | 17/17 | `python3 -m unittest hass.tests.test_photo_polish` |
| T2 real calls (6 photos x high + medium) | 12/12 calls returned an edit | `t2-results.json`, `contact-sheet-t2.jpg` |
| T3 fidelity gate | 12/12 real edits kept; 34/34 deliberate bad outputs rejected | `t3-results.json`, `t3-results-recolour-product.json`, `t3-bad-samples.jpg` |
| T4 site card | 2/2 | `t4-card-phone-on.png`, `t4-card-plain-on.png`, `t4-*.json` |
| T5 end to end (polish on / off / call failing) | 6/6 runs finish | `t5-results.json` |
| T6 privacy | 6/6 clean | `t5-results.json` (`privacy`) |

**T2.** All calls returned a 1254 x 1254 PNG of 1.6 to 3.2 MB. The high tier took 16.0 to 24.5 s and the medium tier
17.1 to 22.6 s, so they are about equally fast. Both tiers pass the gate on all six photos, so the gate gives no
reason to prefer either one. High stays the default because G chose the high tier. In the T5 runs, the real call took
19 to 28 s, well inside the 90 s limit.

**T3.** The gate needs no model. Everything is measured on the published square (`frame`):
- Match: the product, found by the house cutout mask, must be found again in Mike's photo (grey and saturation
  correlation of at least 0.55).
- Colour: the mean hue may move at most 30 degrees, and the chromaticity at most 0.08.
- Label words read by tesseract: each one must look like the same spot of Mike's photo (correlation of at least 0.35).
  A 4+ letter word scoring under 0.45 must also be read on the photo itself.

The deliberate bad outputs, all rejected:
- 6 painted relabels (`SUNNY BRAND`), rejected as text or match.
- 6 product-only recolours, rejected as colour.
- 6 whole-picture channel swaps, rejected as style.
- 6 doubled products and 6 swapped products, rejected as match, colour or text.
- 4 real gpt-image-2 edits that were asked to change the product (relabel, extra item, recolour), rejected as text,
  match or colour.

The margins are modest. The lowest real match is 0.581 (produce), against the 0.55 threshold. Any rejection only
falls back to the house render, so a false rejection is safe.

**T4.** The new card's image box is 278 x 208, the same as its neighbours. The picture loads as an 800 x 800 image.
The alt text describes the product only. The card HTML and the catalog entry contain no `AI`, `generated`, `enhanced`,
`edited`, `openai`, `gpt` or `polish`, and no price, cost or quantity. The published JPEG carries no EXIF, XMP or C2PA
metadata.

**T5.** The reply to the photo takes 0.03 to 0.13 s. The polish runs in a background thread after the reply, so the
interview never waits. The runs behave like this:
- `on`: the polished picture is published.
- `off`: the house render is published and nothing is logged.
- `fail`: the house render is published and one `polish-api` correspondence-log row is written. Nothing is said to
  the owner.

**T6.** No published file contains the original photo's or the web copy's bytes, a full photo sha, an owner, chat or
media path, or a private intake field.
