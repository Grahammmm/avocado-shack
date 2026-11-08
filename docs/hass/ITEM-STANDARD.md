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
| Producer's town ("Based in ..." under the name) | REQUIRED when a maker is named; the value must be a town ("Town, State"), not a region | maker `place` | No maker: the generic line above (no town). Maker place missing: **"Based in undefined"** (verified). Empty place: **"Based in "** with nothing after it. A region ("California’s Central Coast") is shown as is: it looks fine but is not a town (6 makers, 15 products today; the 16th town gap is SLO Cider, a brand with no maker record). | "Based in Arroyo Grande, California". |
| One-line description (2 or 3 short sentences, 59 to 167 characters measured, limit 600) | REQUIRED | `description` | Empty paragraph, zero height: the card just ends (silent). A 600-character text makes a card about 10 times taller than its neighbours. | House voice, 2 or 3 sentences, ends with a full stop, no digit, `!`, `?`, price, size or hype word, no claim Mike did not say. Hass drafts it; Mike approves. |
| Picture | REQUIRED, house style (section 2) | `image` (file must exist) | Missing file or empty path: a broken-picture box (the page still writes the caption "<name> (illustration)", so the box shows that text); refused on save for an active product. | A house-style picture. Mike's own photo is an UPGRADE (170 of 170 are stock pictures today; `photos to take` already tracks it). |
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
| Clean frame (border pixels still ivory) | 99.2% | 94.5% to 100% | 86.5% | at least 90%, **hard** for a new picture; existing 015 (86.5%), 093 (89.9%) and 110 (88.7%) are named, grandfathered exceptions (section 2.1) |
| Subject: longest side as share of the frame | 90.5% | 79% to 97% | 70.5% to 100% | soft: 79% to 97% (the usual range); the render aims at 90%; a subject touching the frame edge is normal (40 of 170 do) |
| Subject width / height | 85% / 79% | 48 to 97% / 51 to 94% | | follows the product shape |
| Centre of the subject | +1.3% across, +0.5% down | -3.5% to +9.3% across, -1.5% to +4.1% down | up to +13% across | within +-4% down, +-10% across |
| Margin below / above / left / right | 9.5% / 11.5% / 9.5% / 6.0% | below 3.5% to 22.3%, above 2.0% to 26.8% | below 2.5% to 28% | at least 2.5% below |
| Subject area | 40% of the frame | 23% to 56% | 16% to 64% | 20% to 60% |
| Shadow under the subject | 2.1 levels darker than the ivory | -0.4 to 5.8 | up to 7.4 | **optional**: 0 to 7.5 levels, never harder. 124 of 170 have at least 1 level, 46 have none |
| Look | one real product or group, true packaging colours, no props, hands, text overlays, prices or borders; subject brightness 140 and colour strength 0.48 median | | | soft checks only |
| File name | `photo-product-NNN.webp` equals the product id (170 of 170); next number = highest + 1 | | | owner photo: `photo-<sha16>.jpg`, written by `photos.install` |
| Alt text | none stored; the page writes "<name> (illustration)" | | | see section 1 |
| On the page | desktop and tablet: a **4:3 box** (274 x 206 px in a 1280 px window) with the square picture centred, `object-fit: contain`, side bars in page colour #f5f0e6 (9, 8, 6 levels darker than the picture ivory); phone under 520 px: a **112 x 112 px square thumbnail** | | | the subject must still read at 112 px: the 90% fill matters |

### 2.1 Hard, soft and grandfathered (how the check treats the existing pictures)

One rule set, three classes, so "the picture check" and "the existing pictures" can never contradict each other. Evidence: `reports/hass/itemstd-1/picture-envelope.json` (written by `check_envelope.py.txt`, read only, no picture or measurement was altered).

* **Hard** (a NEW render or photo that fails any of these is not accepted): 800 x 800; no EXIF, colour profile or alpha; at most 160 KB; background within 28 levels of #fef8ec; clean frame at least 90%.
* **Soft** (advice only: a plain retake tip to Mike, never a refusal): file 31 to 99 KB; background within 17; background variation at most 6; longest side 79% to 97% of the frame; centre within 4% down and 10% across; margin below at least 2.5%; subject area 20% to 60%; shadow at most 7.5 levels; subject at least 80% of the frame so it reads in the 112 px phone thumbnail.
* **Grandfathered**: an existing picture that fails a hard check is named in `hass/style/item-standard.json` (`grandfathered`: id, the check, the measured value, the reason). The catalog run reports it as "passes, grandfathered", not as a failure.

Result on the 170 active pictures: **all pass size, metadata, file size and background**; **167 pass every hard check; 3 fail one, the clean-frame check, and are the named exceptions: 015 Brian's sourdough bread (86.5%), 110 Cookies and Cream chocolate (88.7%, tan background #f9e9d6), 093 Avocado Shack (Hands) (89.9%)**. Each of the three is also in the least-typical list below, and all three sit on a warmer tan background (#f6ecdf, #f8ede1, #f9e9d6). 54 of 170 miss at least one soft check (counts: file size 18, background beyond 17 levels 9, background variation 5, subject size 12, centre down 9, centre across 7, subject area 7, thumbnail fill 11); that is expected, the soft values are the edges of the usual range, and the pictures G likes include them.

How the build plan uses this (card ITEMSTD-3): the catalog test passes when exactly those 3 ids fail exactly the clean-frame check and nothing else fails a hard check, so a fourth failure breaks CI, and a grandfathered picture that starts to pass makes the test say "remove it from the list". A grandfathered id leaves the list when its picture is replaced (Mike's own photo, or a new render). Option not taken: lowering the clean-frame rule to 85% would admit all 170 but would weaken the check for every new render; it stays a one-number change in the settings file if G ever prefers it (technical, reversible, no decision needed now).

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
Fixed asking order: name, shelf, producer, producer's town. A photo is never a gap question (decision E; the `photos to take` command covers it). Description, caption and the house sentence are drafted by Hass, never asked.

## 4. The ask-Mike flow (design in the skill shape; wording follows `docs/hass/VOICE.md`)

Five new skills (card ITEMSTD-5): `gap.fill`, `gap.list`, `gap.later`, `gap.stop`, `gap.start`. They have two different natures, and the design keeps them apart:

| Skill | What it does | Approval | Live class | Changes |
|---|---|---|---|---|
| `gap.fill` | turns his answer into an update of the item or maker | `owner-yes` (a normal draft, `yes <code>`) | `private-only` (brand, producer and place are protected fields, D4) | content, through `editor.prepare` as every skill |
| `gap.list` | says what is missing, most visible first | `none` | `read-only` | no content; at most the question counter (below) |
| `gap.later` | pauses the open question until tomorrow | `none` | `read-only` | question-control state only |
| `gap.stop` | pauses all gap questions | `none` | `read-only` | question-control state only |
| `gap.start` | turns gap questions back on | `none` | `read-only` | question-control state only |

**Immediate stop (the rule that settles "do stop and pause wait behind an approval?").** `later`, `stop asking` and `ask me again` never create a draft, never need `yes`, and take effect in the same message transaction as their reply, before any question can be sent. They change only private question-control state in `conversation.sqlite3` (the same kind of private row as `open_requests` and `backlog`), never content, so the owner-yes path, the claims gate and the live policy are not involved and not weakened. They work while changes are paused (`stop changes`), after the interpreter's daily limit and while the interpreter is down, because the exact words are read by code first (the same way `stop changes`, `status` and `undo` are). A fuzzier sentence ("please stop bugging me about the farms") goes to the interpreter, which can only answer with `gap.stop`; even then no approval is asked. Only a **whole message** counts as a stop word: "Smith Farm, later we'll know the town" is an answer, not a stop. Updates to the website (`gap.fill`) keep the existing owner approval, the claims gate and the protected live boundary exactly as for `item.edit` and `maker.edit`.

### 4.1 The one asking policy (canonical; every other place in these documents points here)

A **gap question** is any message sentence in which Hass asks Mike for a missing detail of an item or maker (who made or grew it, which town, which shelf when in doubt, what the about text should say). One gap question per reply at most (VOICE rule 4).

| Policy | Value |
|---|---|
| Daily budget | **3 gap questions per owner per Pacific calendar day, counted when sent. Every gap question counts, whatever started it**: adding an item, `what's missing`, a question tacked on to a reply, and a follow-up to an answer (the town after the farm). Nothing is exempt. |
| Quiet hours | no gap question between 8 pm and 8 am Pacific; a question that would be asked then waits for his next message after 8 am (in version 1 Hass never starts a message, decision B) |
| Who | an owner's own chat only (never G's chat, never a stranger) |
| What does NOT count | the skill's own required slots (the name and shelf of an item he is adding, the photo he is sending): they are the skill's questions, not gap questions. Anything Mike volunteers ("the tomatoes are from Smith Farm") is welcome at any time and is never limited: the budget limits what Hass asks, not what Mike says. |
| Budget used up | Hass does not ask. A new item is still drafted, with today's honest fallback ("From the market"), the draft says "Still missing: ..." and the gap row is kept; the question waits for his next message on a day with budget left and between 8 am and 8 pm. `what's missing` still lists everything (a list is an answer to his command, not a question) and ends "I'll ask again tomorrow." |
| `later` | pauses **that** question until **8 am the next Pacific day**; nothing else is paused; the question already used one of today's three |
| ignored question (no reply in 24 hours) | treated exactly as `later` |
| `no` to a question | that item's question is not asked again for 7 days |
| two ignored questions in a row | all gap questions rest for 7 days (a quiet week), or until he asks `what's missing` or answers any gap question |
| `stop asking` | pauses all gap questions, for good, until `ask me again` (his word, not `resume`: `resume` already means "let approvals apply again"); `what's missing` still works because he asked |
| `ask me again` | clears `stop asking`, every `later` and the quiet week; it does **not** reset today's count, so it cannot be used to get past three |
| `I don't know` | accepted; recorded; that field is not asked again for 60 days (the item shows the honest fallback); `what's missing` still lists it as "you weren't sure" |
| `stop changes` | no gap question is asked while changes are paused; it is a separate switch from `stop asking` |
| draft waiting for his yes, or interpreter down | no gap question (never on a reply that ends "Reply yes to save it") |

**Proposed relaxation, G's choice, NOT part of the default (decision D in `reports/hass/ITEMSTD-1.md`):** count only the questions Hass adds on its own (the tacked-on ones), and let questions Mike starts (adding an item, `what's missing`) and the follow-up to an answer he just gave run without the count and outside quiet hours. It makes filling the catalog much faster, and it is a setting (`gap.count_mode: all` is the default, `unprompted` is the relaxation). It is off until G answers. Everything below is written for the default.

**Worked sequence (default policy; Tuesday and Wednesday, Pacific time).** The wording is checked by `hass/voice.py` (section 4.6).

| When | Mike | Hass | Count today |
|---|---|---|---|
| Tue 10:05 | sends a photo, "tomatoes" | the farm is missing, so the reply is the question "Who grew the tomatoes this week?" (the draft comes after the answer) | 1 of 3 |
| 10:06 | "Smith Farm in Arroyo Grande" | one answer fills the farm and the town; the draft: "Smith Farm in Arroyo Grande, for the tomatoes. Reply yes to save it, or no to cancel." | 1 |
| 11:30 | `report` | the report, then one tacked-on question about the almonds | 2 |
| 11:31 | `later` | "OK, I'll ask again tomorrow." The almonds are paused until Wed 8 am | 2 |
| 13:00 | adds figs | "Same farm as last time, Smith Farm in Arroyo Grande?" | 3 of 3 |
| 13:01 | "same" | the draft for the figs, as for any change | 3 |
| 15:00 | adds blueberries | the draft is made with "From the market" and says "Still missing: who grew the blueberries. I'll ask again tomorrow." before "Reply yes to save it, or no to cancel." **No fourth question.** | 3 |
| 15:10 | `what's missing` | the list, no question, last line "I'll ask again tomorrow." | 3 |
| 15:20 | "blueberries are from Smith Farm" | he said it himself: a normal change, drafted, not limited, and the blueberry gap closes | 3 |
| Wed 07:55 | "morning" | nothing asked (before 8 am) | 0 |
| Wed 08:10 | `report` | the report, then the almonds question (the first allowed moment; the almonds are the most visible gap) | 1 of 3 |

### 4.2 `gap.fill` (the skill that turns an answer into a draft)

```
name        gap.fill                       group gap             version 1
label       "fill in a missing detail"
summary     Turn Mike's answer about a missing farm, maker, town or about text into one draft update.
triggers    "Smith Farm in Arroyo Grande" · "the tomatoes are from Smith Farm" · "same farm as last time"
            · "Smth Farm in Arroyo Grande" (typo) · "they're in Arroyo Grande" (vague, only with an open question)
            · "the peppers and the zucchini are from them too" (multi) · "I don't know" (recorded, no draft)
slots       item        product_ref   required  default derive:open_gap  ask "Which item is that for?"
            maker_name  text (maker name limit)  owner_words  required unless:unknown  default derive:last_maker_if_same
                                              ask "Who grew the {item} this week?" (fresh) or "Who makes the {item}?" (packaged)
            town        text "Town, State"  owner_words  required: false  (code asks when a new maker has none)
            also        list of product_ref  optional, at most 6 on the same shelf with the same gap
            same        bool  optional ("same farm", "same as last time")
            unknown     bool  optional ("I don't know", "no idea")
rules       gap-still-open · owner-words-only · town-state · maker-not-held · no-claim-words · answers-only-the-asked-field
plan        known maker:   [product.edit{id, brand, producerKey, displayBrand}] per item (the item.edit maker slot, reused)
            new maker:     [maker.add{key, name, place, story}] first (story = fallback sentence "<name> is based in <town>.", D5), then the product.edit
            town only:     [maker.edit{key, place}]
            unknown:       [] (no op; records `unknown` in the private state)
edits       hass/content/products.json  products[id].brand, .producerKey, .displayBrand
            hass/content/makers.json    makers[key]  (new maker or place)
            generated: storefront-mockup/catalog-products.js, index.html
side effects maker-create (new maker only), private-note (the answered or unknown mark in the gap state)
preview     product:<the item's name>
approval    owner-yes    live_class private-only    undo revert; residue: the gap state is not rolled back (the item simply shows as missing again on the next check); a new maker stays on file (hide it with maker.hide)
refuse      the maker is hidden → "<name> is hidden. Bring them back first." · a claim word he did not say ("organic", "family farm") → left off, listed under Left off · a town with no state that the catalog cannot supply → asks "Which state?", never guesses · more than 6 items → asks with the count · the item is held or hidden → names the state · the gap is already filled → "It already says Smith Farm. Nothing to change."
cases       hass/tests/fixtures/skills/gap/gap.fill.jsonl   (10+ rows)
```

Scenarios the fixture must contain (each a multi-turn row, real `Conversation` and `Editor` on a scratch tree): 1 farm and town in one answer, new maker; 2 farm only, then "Which town is Smith Farm in?", then the town; 3 a maker already on file (no `maker.add`); 4 "same farm as last time" with the saved maker; 5 up to 6 items on one shelf in one draft; 6 `I don't know` (no draft, recorded, not asked for 60 days); 7 typo and vague answer joined to the open question ("Smth Farm", "they're in Arroyo Grande"); 8 refusals: hidden maker, unsaid "organic", a town without a state; 9 the answer arrives after Mike answered it another way (nothing is drafted, "It already says ..."); 10 undo of the draft returns the tree to the earlier state apart from the declared residue; 11 the open question expired and the answer is a new request; 12 `no` cancels the open question and starts the 7-day rest.

**How an answer finds its item.** The open question is stored as an `open_requests` row (skill `gap.fill`, the item or maker, the asked field, the question, `expires_at`). The next message from that owner is read against it **after** the stop words are checked (so `later` can never be taken as a farm named "Later"). Code reads the easy answers first (a maker already on file, "Name in Town", "Name, Town, State", "same", "don't know", `no`); everything else goes to the interpreter in continue mode with the snapshot. A gap question lives until 8 pm the next day (a small `ttl` in `openreq.py`, ITEMSTD-5 owns it after FW-3 merges), not 30 minutes. The answer fills only the asked field and the next gap field of the **same** item (so "Smith Farm in Arroyo Grande" fills farm and town); it never fills a different item's field.

**What an answer does.** The producer name and town come only from his words (claims gate unchanged: no "organic" or "family farm" unless he said it). A maker already on file is reused; a new maker needs a name and a town and gets the D5 fallback about text. A town without a state takes the state of the same town already in the catalog; otherwise Hass asks "Which state?" and never guesses. The draft says it in his words: "Smith Farm in Arroyo Grande, for the tomatoes. Reply yes to save it, or no to cancel." The description is not rewritten automatically. For fresh produce the site shows no week, so when the farm changes next week Mike just says so ("the tomatoes are from Jones Farm now", `item.edit`); `gap.fill` offers "Same farm as last time?" and never assumes it.

### 4.3 `gap.list` (the "what's missing" command)

```
name        gap.list                       group gap             version 1
label       "list what the website is missing"
summary     List the missing details in plain words, most visible first.
triggers    "what's missing" · "whats missing" · "what is missing on the site" · "whats mising" (typo)
            · "what do you still need from me" (vague) · "what's missing for the cheese and the vegetables" (multi: scope)
slots       scope  enum all|packaged|fresh|makers  optional  default all
rules       recompute-from-saved-copy · held-never-listed · most-visible-first · list-is-not-a-question
plan        []  (no op)
edits       none
side effects private-note  ONLY when the reply ends with a question (writes today's count and the open question); otherwise none
preview     none
approval    none         live_class read-only    undo forget (drops the open question it wrote); residue: none
refuse      no gaps → "Nothing is missing that I know of." · paused by `stop asking` → the list is still shown (he asked) and ends without a question · quiet hours, budget used up or changes paused → the list is shown, ends "I'll ask again tomorrow.", no question
cases       hass/tests/fixtures/skills/gap/gap.list.jsonl   (10+ rows)
```

The order is the visibility tier in `catalog-gaps.json`: 1 a generic source line on a packaged card (the view the shop opens on), 2 the same on a fresh card, 3 a region where a town should be, 4 a shelf worth a look, 5 minor notes; ties by shelf order. The list shows at most 3 lines plus a count of the rest, built from the saved copy, never from memory (so a gap he already fixed another way is not listed). It ends with the first question only if the budget, quiet hours and pauses allow it; then that question is counted and stored like any other. The list is the only place photos appear, as one closing line ("N items still show a stock picture"); the existing `photos to take` command stays.

Scenarios: 1 plain list with the question; 2 scope `fresh`; 3 list at 9 pm (no question); 4 fourth question of the day (list, no question); 5 after `stop asking` (list, no question); 6 while changes are paused; 7 nothing missing; 8 a gap fixed by hand is not listed; 9 a held product is never listed; 10 more than 3 gaps ("and 5 more"); 11 refusal: a maker the site does not have; 12 refusal: a message that only looks like the command ("what's missing from the order?" goes to the interpreter); 13 undo row: the open question the list wrote is dropped.

### 4.4 `gap.later`, `gap.stop`, `gap.start` (question control, immediate, no approval)

```
name        gap.later                      version 1   label "ask me about it tomorrow"
summary     Pause the open gap question until 8 am tomorrow.
triggers    "later" · "not now" · "ask me tomorrow" · "laer" (typo) · "later, I'm busy" (vague) · "later, and ask about the cheese first" (multi: reorders)
slots       question  open_gap  optional  default derive:open_gap      (never a date: `later` is always tomorrow 8 am)
rules       only-with-an-open-question · whole-message · never-an-answer
plan        []   effect: gap_state.paused_until = next Pacific day 08:00 for that item and field; the open request is closed as `paused`
edits       none          side effects private-note           preview none
approval    none          live_class read-only                undo forget (clears the pause; "ask me again" does the same); residue none
refuse      no open gap question → "There's nothing I'm waiting on." · `later` inside a longer answer is not a stop
cases       hass/tests/fixtures/skills/gap/gap.later.jsonl   (10+ rows)

name        gap.stop                       version 1   label "stop asking about missing details"
summary     Pause every gap question until Mike says ask me again.
triggers    "stop asking" · "stop asking me" · "no more questions" · "stp asking" (typo) · "enough with the questions" (vague) · "stop asking and show me what's missing" (multi: list, no question)
slots       none
rules       whole-message · stop-is-not-stop-changes
plan        []   effect: owner_gap.stopped = true; any open gap question is closed as `paused`; the gap rows stay
edits       none          side effects private-note           preview none
approval    none          live_class read-only                undo forget (a later `ask me again`); residue none
refuse      already stopped → "I'm already not asking. Say ask me again when you want me to." · plain `stop` stays the existing stop-changes command
cases       hass/tests/fixtures/skills/gap/gap.stop.jsonl   (10+ rows)

name        gap.start                      version 1   label "start asking again"
summary     Turn gap questions back on and clear every pause.
triggers    "ask me again" · "start asking" · "you can ask again" · "askme again" (typo) · "ok go ahead and ask" (vague) · "ask me again, the cheese first" (multi)
slots       none
rules       whole-message · does-not-reset-the-count
plan        []   effect: owner_gap.stopped = false, quiet week cleared, every `later` cleared; today's count is kept
edits       none          side effects private-note           preview none
approval    none          live_class read-only                undo forget (a later `stop asking`); residue none
refuse      not stopped → "I was already asking. I'll ask when it's a good time."
cases       hass/tests/fixtures/skills/gap/gap.start.jsonl   (10+ rows)
```

Scenarios for each (10 or more rows, 2 refusals and 1 undo as the lint demands): the exact word with and without a trailing full stop; a typo; the word inside a longer answer (must be an answer, not a stop); the word while changes are paused; the word after the interpreter's daily limit; the word with no open question; two in a row; the effect on the next question (none is sent before 8 am tomorrow for `later`, none at all after `stop asking`); `ask me again` that does not reset today's count; the effect is visible in `status` (one new line: "Gap questions: paused until you say ask me again."). Every reply is one short plain sentence: "OK, I'll ask again tomorrow.", "OK. I won't ask about missing details until you say ask me again.", "OK, I'll ask about missing details again."

### 4.5 When Hass asks, and what it remembers

Three triggers (a fourth, Hass starting a message by itself, is NOT in version 1, decision B):
1. While adding an item or maker (`item.add`, `maker.add`): the completeness check runs on the planned record before the draft; each missing REQUIRED field is the next gap question, in the fixed order, as long as the budget and the hours allow (4.1). Otherwise the draft carries the fallback and "Still missing: ...".
2. On his command `what's missing` (`gap.list`).
3. Tacked on to a reply that has no other question ("Saved, but not on the website yet. ...", `report`): one gap question. Never on a reply that already ends with "Reply yes to save it".

Fixed asking order: name, shelf (only a yes/no when in doubt), producer, producer's town, photo (never asked as a gap question, decision E). Description, caption and the house sentence are drafted by Hass, never asked.

**Memory (private tables in `conversation.sqlite3`, 90 days, same backup and retention rules as `open_requests`; never in git, logs, reports or what is sent to the interpreter):**

| Table | Columns | Used for |
|---|---|---|
| `gap_state` | owner, subject (product or maker), field, state (open, answered, unknown, paused), asked_count, last_asked_at, answered_at, unknown_until, paused_until | never ask the same thing twice: before every question the gap is recomputed from the current content, so an answer given any other way clears it |
| `gap_budget` | owner, pacific_day, count | the three a day |
| `owner_gap` | owner, stopped, quiet_until, ignored_in_a_row | `stop asking` and the quiet week |

For fresh produce Hass offers "Same farm as last time, Smith Farm in Arroyo Grande?" when he marks the item in, and "Same farm for the peppers and the zucchini too?" for up to 6 items of one shelf still missing a farm (one question, one draft, one count).

### 4.6 Wording, and the one-time checklist

Every line Hass would send in this section is written as a quoted line starting with `> ` and is run through `hass/voice.py` by the script `reports/hass/itemstd-1/check_voice.py.txt` (result in `reports/hass/ITEMSTD-1.md` section 8); the card's own test must do the same for every template.

**`what's missing`** (whole message; also `whats missing`, `what is missing`):

> Here's what the website is still missing:
> Almonds, cashews and 6 other packaged items don't say who makes them.
> 56 fresh items say "From the market" instead of a farm. The first few: blackberries, blueberries, figs.
> 6 makers show a region instead of a town: Straus, Alle-Pia, Corberosa and 3 more.
> Who supplies the almonds?

and, over the budget:

> I'll ask again tomorrow.

**One-time friendly checklist** (shown the first time Mike adds an item, and on `new item`):

> For each new item I need: a photo, the name, who made or grew it, and which town they're in. I'll work out the rest. If you don't know something, say you don't know and I'll leave it for later.

**Questions (templates, fixed order):**

> What is it called?
> Which shelf should it go on?
> Who grew the tomatoes this week?
> Who makes the jam?
> Which town is Smith Farm in?
> Which state is Arroyo Grande in?
> Could you send me a photo of the tomatoes?
> Same farm as last time, Smith Farm in Arroyo Grande?
> Avocado Shack is shown as the brand on the cashews. Who grows or makes them?

Replies to the stop words:

> OK, I'll ask again tomorrow.
> OK. I won't ask about missing details until you say ask me again.
> OK, I'll ask about missing details again.
> There's nothing I'm waiting on.
> It already says Smith Farm. Nothing to change.
> Smith Farm in Arroyo Grande, for the tomatoes. Reply yes to save it, or no to cancel.
> Blueberries, from the market for now. Still missing: who grew them. I'll ask again tomorrow. Reply yes to save it, or no to cancel.

Every real question for today's catalog is in `reports/hass/catalog-gaps.json`, already checked with `hass/voice.py`.

## 5. Not part of the standard (backlog)
Instagram post preparation: `reports/hass/ITEMSTD-1.md` section 7.
