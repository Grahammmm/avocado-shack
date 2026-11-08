# The item standard (HASS-ITEMSTD-1, version 1, DRAFT until G answers the decisions in reports/hass/ITEMSTD-1.md)

What every product, maker and product picture on the Avocado Shack site must have, what the site shows today when it is missing, and how Hass
asks Mike for it. Numbers were measured from `hass/content/*.json` and `storefront-mockup/assets/products/` at main `56c9070` (170 active products,
2 held, 26 makers, 182 picture files) and from the real page code (`storefront-mockup/shop.js`, `style.css`) drawn in a browser on a loopback
copy. Method and scripts: `reports/hass/ITEMSTD-1.md` section 8. Nothing on the site, in the content or in any code was changed.
**Keep what G likes:** the card layout stays exactly as it is. This standard only says what must be filled in, and makes the picture match.

## 1. The item standard

REQUIRED = the item is not complete without it (Hass asks; "I don't know" is accepted, recorded, and the item shows the honest fallback).
OPTIONAL = never asked unless Mike offers it.

| Field (site word) | Level | Source of truth | What the site shows TODAY when it is missing (verified in the page) | What it SHOULD show |
|---|---|---|---|---|
| Name | REQUIRED, at most 80 characters, no sizes or digits | `name` | Empty heading; picture caption becomes "undefined (illustration)" (key absent) or " (illustration)". The editor refuses to save this, so it only happens by hand-editing. | Never saved. |
| Shelf (category): Fruit, Vegetables, Dairy & cheese, Eggs, Meat, Pantry, Drinks & coffee, Bread, Flowers | REQUIRED, one of 9 | `category` | Refused on save. A wrong shelf shows the item under the wrong filter (2 today: see section 3 of the report). | The right shelf; a doubtful one is asked as yes/no. |
| Packaged or fresh | REQUIRED but DERIVED, never typed: fresh = Fruit, Vegetables, Flowers; everything else packaged | `category` + one hard-coded exception in `shop.js` (`PACKAGED_IDS`: the tortilla chips, filed under Vegetables) | Decides which view the item appears in: the shop opens on "Packaged goods"; "Fresh produce" and "All items" are the other views. A bagged item on a fresh shelf shows up under Fresh produce. | Fix the shelf (chips to Pantry) and remove the hard-coded exception in a later site card. |
| Who made or grew it (producer, shown as the grey line above the name) | REQUIRED | `brand`, `displayBrand`, `producerKey` (a maker record) | Unknown producer is stored as brand "Producer not identified". The card shows **"From the market"** above the name and the line **"Ask us about the source in store."**; no "Meet the maker" box, no "See all from". A blank brand would draw an **empty line** (about 33 px shorter identity block). A `producerKey` that names no maker draws the brand plus "Ask us about the source in store." | The maker's name; for fresh produce, this week's farm. |
| Producer's town ("Based in ..." under the name) | REQUIRED when a maker is named; the value must be a town ("Town, State"), not a region | maker `place` | No maker: the generic line above (no town). Maker place missing: **"Based in undefined"** (verified). Empty place: **"Based in "** with nothing after it. A region ("California’s Central Coast") is shown as is: it looks fine but is not a town (6 makers, 16 products today). | "Based in Arroyo Grande, California". |
| One-line description (2 or 3 short sentences, 59 to 167 characters measured, limit 600) | REQUIRED | `description` | Empty paragraph, zero height: the card just ends (silent). A 600-character text makes a card about 10 times taller than its neighbours. | House voice, 2 or 3 sentences, ends with a full stop, no digit, `!`, `?`, price, size or hype word, no claim Mike did not say. Hass drafts it; Mike approves. |
| Picture | REQUIRED, house style (section 2) | `image` (file must exist) | Missing file: a broken-picture box; empty path: caption gets " (illustration)". Refused on save for an active product. | A house-style picture. Mike's own photo is an UPGRADE (170 of 170 are stock pictures today; `photos to take` already tracks it). |
| Picture caption (alt text) | OPTIONAL for stock pictures; REQUIRED for Mike's own photos | `imageAlt` | Stock picture: "<name> (illustration)" (0 of 170 set `imageAlt`). Own photo with no caption: just the name. | Own photo: one plain sentence of what it shows, never a file name. |
| Status | REQUIRED, internal | `status` active / hidden / held | Hidden and held products are not drawn at all. | Unchanged. A held product is never asked about. |
| Availability word and day | OPTIONAL | `available`, `available_on`, store `selection_checked_on` | Nothing is drawn. **Today 0 of 170 have a word and no shelf check day is recorded**, so no card says "Available today", "Limited" or "Sold out". Words older than 7 days show "Last confirmed <day>". | Set by the shelf-check skills, not by this flow. |
| "New" badge | OPTIONAL, automatic | `addedOn` (set by `product.add`) | Nothing (0 of 170 have it). | First 14 days after adding. |
| "Organic" badge | derived, not a field | `shop.js organic()`: name contains "organic" or maker is one of 4 hard-coded keys | See section 4 of the report: a hard-coded list; a claim, so Hass never sets it on its own. | Unchanged. |
| Maker name | REQUIRED | maker `name` (key = name) | Refused on save. | |
| Maker "about" text | REQUIRED, 239 to 297 characters measured, limit 600 | maker `story` | Empty story: "Meet the maker" opens to an empty paragraph. | Mike's sentences, or the one-line fallback "<Maker> is based in <town>." (D5). |
| Maker website | OPTIONAL | maker `url` | No "Visit <maker>" link; nothing else changes. | Public https only; never asked. |

## 2. The picture standard (measured, not guessed)

Measured on the 170 pictures of the active products with `reports/hass/itemstd-1/measure_pictures.py.txt` (pure Pillow, subject = pixels more than 30
levels from the picture's own border colour, on a 4x-reduced copy). Full distributions: `reports/hass/itemstd-1/picture-measurements.json`.
The numbers agree with the PR #504 measurement (`house-style.json`) to rounding: background median identical (254, 248, 236), longest side
0.905 vs 0.906, median file 62,170 vs 62,172 bytes, so two independent scripts found the same standard.

| Property | Median | Usual range (p05 to p95) | Extremes | Target for a new picture (and the check) |
|---|---|---|---|---|
| Size | 800 x 800, 1:1 (170 of 170) | none | none | exactly 800 x 800, RGB; hard fail otherwise |
| File | WEBP lossy (one `VP8 ` chunk), made by `optimize-images.cjs` (sharp, quality 84, fit inside 800); no alpha, EXIF, colour profile or XMP (170 of 170) | | | no metadata, hard fail; a new owner photo is saved as JPEG `photo-<16 hex>.jpg` (D1), so the byte target below is the check |
| File size | 62.2 KB (0.78 bit per pixel) | 31.0 to 98.8 KB | 23.7 to 158.9 KB | soft target 31 to 99 KB, hard fail above 160 KB |
| Background | #fef8ec = rgb(254, 248, 236), warm ivory; red 249 to 254, green 237 to 251, blue 224 to 243 | | red 246 to 255, green 233 to 253, blue 214 to 249 | within 17 levels of #fef8ec (colour distance, p95 is 16.9); 105 of 170 are within 6, 139 within 10, 158 within 15; hard fail beyond 28 |
| Background evenness | 1.9 levels of variation along the border | 0.5 to 5.3 | up to 8.3; top and bottom corners differ by 2.3 levels (p95 11.5, max 23) | soft: at most 6 |
| Clean frame (border pixels still ivory) | 99.2% | 94.5% to 100% | 86.5% | at least 90%, hard |
| Subject: longest side as share of the frame | 90.5% | 79% to 97% | 70.5% to 100% | 85% to 96% (the render aims at 90%); a subject touching the frame edge is normal (40 of 170 do) |
| Subject width / height | 85% / 79% | 48 to 97% / 51 to 94% | | follows the product shape |
| Centre of the subject | +1.3% across, +0.5% down | -3.5% to +9.3% across, -1.5% to +4.1% down | up to +13% across | within +-4% down, +-10% across |
| Margin below / above / left / right | 9.5% / 11.5% / 9.5% / 6.0% | below 3.5% to 22.3%, above 2.0% to 26.8% | below 2.5% to 28% | at least 2.5% below |
| Subject area | 40% of the frame | 23% to 56% | 16% to 64% | 20% to 60% |
| Shadow under the subject | 2.1 levels darker than the ivory | -0.4 to 5.8 | up to 7.4 | **optional**: 0 to 7.5 levels, never harder. 124 of 170 have at least 1 level, 46 have none |
| Look | one real product or group, true packaging colours, no props, hands, text overlays, prices or borders; subject brightness 140 and colour strength 0.48 median | | | soft checks only |
| File name | `photo-product-NNN.webp` equals the product id (170 of 170); next number = highest + 1 | | | owner photo: `photo-<sha16>.jpg`, written by `photos.install` |
| Alt text | none stored; the page writes "<name> (illustration)" | | | see section 1 |
| On the page | desktop and tablet: a **4:3 box** (274 x 206 px in a 1280 px window) with the square picture centred, `object-fit: contain`, side bars in page colour #f5f0e6 (9, 8, 6 levels darker than the picture ivory); phone under 520 px: a **112 x 112 px square thumbnail** | | | the subject must still read at 112 px: the 90% fill matters |

**Ten typical (closest to the median on 9 measures) and ten least typical.** "Worst" means least like the others, not ugly: they are mostly packaged goods on a
warmer tan background or off-centre. Eyeball sheet: `reports/hass/itemstd-1/best-and-worst.jpg` (top two rows best, bottom two worst). Paths are under `storefront-mockup/`.

| Best (score, lower is closer) | Worst |
|---|---|
| 164 Red bell peppers 1.01; 169 Cherry tomatoes 1.04; 103 Radicchio 1.04; 073 Ginger 1.07; 016 Oranges 1.09; 130 Gouda 1.10; 149 Green cabbage 1.15; 063 Bok choy 1.18; 010 Cal Poly blackberry jam 1.20; 165 Poblano peppers 1.24 | 015 Brian's sourdough bread 8.8 (low, right-shifted, 3.5% frame margin); 110 Cookies and Cream chocolate 8.2 (tan #f9e9d6); 093 Avocado Shack (Hands) 6.7; 085 Dream Girl Decaf 6.0; 005 Linn's orange marmalade 5.8 (fills the whole width); 024 Cal Poly eggs 5.5 (28% empty below); 094 Cass Hill Blend 5.5; 046 Dried lion's mane mushrooms 5.4; 123 Rosemary Sourdough with olive oil 5.0; 038 Cal Poly white cheddar 5.0 |

(each path is `assets/products/photo-product-<number>.webp`)

**Where PR #504 (`house_style.py`, `newitem_render.py`, still open, head `ff732f1`) differs from the measured standard:**
1. Format: it renders JPEG, the catalog is WEBP. That is the deliberate D1 choice (an owner photo must be `photo-<sha16>.jpg` so the page calls it a photo). Keep, but the byte check is what compares them.
2. Background check: per channel within the catalog min and max plus 6. That admits colours up to 27 levels from the median (the tan corner of the box). Use distance from #fef8ec, 17 target, 28 hard.
3. Soft shadow is scored as required; 46 of 170 (27%) have none. Make it optional, 0 to 7.5 levels.
4. Its report says "8% bottom margin"; its own JSON and this measurement say 9.4 to 9.5%.
5. Its report says the page box is square. It is square only on a phone; on desktop and tablet it is 4:3 with side bars.
6. A deterministic render keeps Mike's pixels; the catalog was AI-relit from shelf photos (`image-generation-log.json`), so framing, background, shadow, size and format can match but the studio light cannot. The checks on subject brightness and colour strength stay soft.
7. Nothing in #504 checks the 112 px phone thumbnail; add a check that the subject fill is at least 80%.

## 3. The completeness check (what the code must do, spec for card ITEMSTD-2)

`check_product(record, makers) -> {complete, missing[], display_problems[], needs_a_look[], ask_order[], question}` and `check_maker(record)`, pure, in
`hass/itemstd.py`, data in `hass/style/item-standard.json`. Missing codes: `name`, `shelf`, `producer`, `producer_town`, `own_photo` (upgrade only), `description`, `story`,
`website` (optional, never asked). A held product returns nothing. The same function writes `reports/hass/catalog-gaps.json`, so the audit and the skill cannot disagree.
Fixed asking order: name, shelf, producer, producer's town, photo. Description, caption and the house sentence are drafted by Hass, never asked.

## 4. The ask-Mike flow (design in the skill shape; wording follows `docs/hass/VOICE.md`)

Skills (new, card ITEMSTD-5): `gap.fill` (answer a question), `gap.list` ("what's missing"), `gap.later`, `gap.stop`, `gap.start`. All are `owner-yes` drafts like any change.

**When Hass asks** (three triggers; a fourth, Hass starting a message by itself, is NOT in version 1, decision B):
1. While adding an item or maker (`item.add`, `maker.add`): the completeness check runs on the planned record before the draft; every missing REQUIRED field becomes the next question. Not counted against the daily limit (Mike started it).
2. On his command `what's missing`: a short plain list, most visible first, then the first question. Not counted.
3. Tacked on to a reply that has no other question (for example "Saved, but not on the website yet. ..." or `report`): one gap question, counted. Never on a reply that already ends with "Reply yes to save it".

**One question at a time, in the fixed order, kept with its item.** The open question is stored as an open request (`open_requests`, skill `gap.fill`) holding the item or maker, the asked field and the question, so a short answer
("Smith Farm in Arroyo Grande") is joined to the right item. A gap question lives until 20:00 the next day, not 30 minutes (needs a small `ttl` in `openreq.py`; ITEMSTD-5 owns that after FW-3 merges).
Answers read by code first (a maker he already has, "Name in Town", "same", "don't know", "later", "stop asking"); anything else goes to the interpreter in continue mode.

**What an answer does:** the producer name and town come only from his words (claims gate unchanged: no "organic" or "family farm" unless he said it). A maker already on file is reused. A new maker needs name and town; only the name arrives: ask the town
next (a follow-up to the answer he just gave does not count against the limit). A town without a state: use the state of the same town already in the catalog; otherwise ask "Which state?" and never guess. The result is drafted like any change:
`maker.add` (when new) plus `item.edit` (producer; `displayBrand` follows), shown as "Smith Farm in Arroyo Grande, for the tomatoes. Reply yes to save it, or no to cancel." Producer, brand and `producerKey` are protected fields: the change is `private-only`, it never goes live from chat (D4).
The description is not rewritten automatically.

**Memory (private table `gap_state` in `conversation.sqlite3`, 90 days, same backup and retention rules as `open_requests`):** per item and field: asked (count, day), answered, unknown ("I don't know" is accepted and not asked again for 60 days unless he asks `what's missing`),
paused. Before every question the gap is recomputed from the current content, so an answer given any other way clears it and nothing is asked twice. For fresh produce Hass offers "Same farm as last time, Smith Farm in Arroyo Grande?" when he marks the item in, and
"Same farm for the peppers and the zucchini too?" for up to 6 items of one shelf still missing a farm (one question, one draft).

**Limits (not a nag):** at most 3 counted gap questions per Pacific day; only in an owner's chat (never G's chat, never a stranger); no new gap question between 8 pm and 8 am; none while a draft waits for his yes, while changes are paused (`stop changes`) or while the interpreter is down; the same item is not asked again for 7 days after a `later`, an ignored question (no reply in 24 hours) or a `no`;
two ignored questions in a row pause all gap questions for 7 days. Stop words: `later` (only while a gap question is open: "OK, I'll ask again tomorrow.") and `stop asking` ("OK. I won't ask about missing details until you say ask me again."). The word to restart is **`ask me again`**, not `resume`:
`resume` already means "let approvals apply again" in `COMMANDS.md`, so it cannot also mean this (decision C). `status` gets one line about it.

**`what's missing`** (whole message; also `whats missing`, `what is missing`). Example (wording must pass `voice.check`; the card's test does that):

> Here's what the website is still missing:
> - Almonds, cashews and 6 other packaged items don't say who makes them.
> - 56 fresh items say "From the market" instead of a farm. The first few: blackberries, blueberries, figs.
> - 6 makers show a region instead of a town: Straus, Alle-Pia, Corberosa and 3 more.
> Want to start? Who supplies the almonds?

Photos stay on the existing `photos to take` command; the list ends with one line saying how many products still show a stock picture.

**One-time friendly checklist** (shown the first time Mike adds an item, and on `new item`): "For each new item I need: a photo, the name, who made or grew it, and which town they're in. I'll work out the rest. If you don't know something, say I don't know and I'll leave it for later."

**Questions Hass asks (templates, fixed order):** "What is it called?" / "Which shelf should it go on?" / "Who grew the tomatoes this week?" (fresh) or "Who makes the jam?" (packaged) / "Which town is Smith Farm in?" / "Could you send me a photo of the tomatoes?" /
"Same farm as last time?" The shop's own brand with no maker: "Avocado Shack is shown as the brand on the cashews. Who grows or makes them?" Every real question for today's catalog is in `reports/hass/catalog-gaps.json`, already checked with `hass/voice.py`.

## 5. Not part of the standard (backlog)
Instagram post preparation: `reports/hass/ITEMSTD-1.md` section 7.
