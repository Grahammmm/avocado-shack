# hass/npp/assets

Runtime assets of the new-product pipeline (HASS-NPP). Each folder is one skill or rule set in SKILL.md shape, written
by the NPP-A card. Hass runs from a released runtime, so it reads these files from the repo and never from a mutable
Hermes profile skill. Every file here is hash-pinned in `../pins.json`.

| Folder | Stage | Contents |
|---|---|---|
| `hass-gallery-style` | S5, S7, judge | gallery style, 12 golden cards, measured `limits.json` (generated) |
| `hass-product-identify` | S2 | read schema, six examples |
| `hass-missing-info` | S3 | rule table |
| `hass-maker-research` | S4 | official-site policy, fact schema, verifier prompt |
| `hass-listing-copy` | S5, S7 | selection schema, reviewed templates and voice phrases |
| `hass-product-photo` | S6 | picture policy (no new thresholds) |
| `hass-listing-edit` | S10 | edit grammar, mapping schema |
| `hass-npp-reply` | S3, S9, S11, S13 | every owner-facing line |
| `hass-style-judge` | offline | rubric, calibration set |

Change an asset: edit it, run `python3 scripts/hass/npp_limits.py` (only if the TSV changed) and
`python3 scripts/hass/npp_limits.py pins`, then the cases named by the asset. See `docs/hass/skills/hass-npp-maintain/SKILL.md`.
