# Hass listing edits: grammar-only baseline

On 65 synthetic owner texts, **grammar: 29** (patch or picture reply), **ask: 7** (recognized form asks instead of editing), **mapper: 22** (would reach an installed mapper; without one, returns `ask_edit_unclear`), **unclear: 7** (no form and no mapper call; returns `ask_edit_unclear` even with a mapper installed). The [full fixture table](../../hass/tests/test_npp_edit_phrases.py) measures `edits.read`, not chat intake or model accuracy: raw prices are tested as typed, and separately labeled finance-split fixtures show what happens after local parsing supplies the price and unit. Exact wording such as `shorter` and `use my photo` works locally, while adding `please` to either reaches the mapper. `add: great on toast` asks instead of copying the suggestion to the listing.

| Owner text | Mapper eligibility or local ask ID |
| --- | --- |
| `make it 4 bucks` | `ask_edit_unclear` |
| `$4.50 a pound` | `ask_edit_unclear` |
| `each not per lb` | `mapper` |
| `make it four bucks` | `mapper` |
| `four dollars and fifty cents a pound` | `mapper` |
| `sell it for five dollars each` | `mapper` |
| `actually 4 or 5 bucks` | `ask_edit_unclear` |
| `per pound please` | `mapper` |
| `call it "Wildflower Honey"` | `mapper` |
| `rename it to Orchard Honey` | `mapper` |
| `call it Wildflower Honey!` | `mapper` |
| `it's Miners' honey` | `mapper` |
| `no maker` | `mapper` |
| `leave the maker blank` | `mapper` |
| `swap the supplier to Lantern Kitchen` | `mapper` |
| `take the source off` | `mapper` |
| `shorter please` | `mapper` |
| `make the description a little shorter` | `mapper` |
| `make it 2 lines shorter` | `ask_edit_unclear` |
| `say it's nice with tea on a cold day` | `mapper` |
| `move that to dairy` | `mapper` |
| `put it under fruit please` | `mapper` |
| `category: snacks` | `mapper` |
| `use my photo please` | `mapper` |
| `use the photo I just sent` | `mapper` |
| `use photo 2` | `ask_edit_unclear` |
| `asdf hjkl` | `mapper` |
| `what did you put for the maker` | `ask_edit_unclear` |
| `Hass, is this on the site yet?` | `ask_edit_unclear` |
