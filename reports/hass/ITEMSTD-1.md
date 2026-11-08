# HASS-ITEMSTD-1: the item standard, measured picture standard, catalog audit and the ask-Mike flow

Card t_ac0390cd · repo Grahammmm/avocado-shack · written against `origin/main` 56c9070 · 2026-11-08 · **design and audit only**. No site content, product data, picture or code was changed;
nothing was published, sent or restarted; no owner message was read; no Mac, host.json or live state was touched. Deliverables: `docs/hass/ITEM-STANDARD.md` (the standard), this report, `reports/hass/catalog-gaps.json` (198 rows),
plus evidence in `reports/hass/itemstd-1/` (picture measurements, eyeball sheet, the four scripts as `.py.txt`).

## 0. Decisions for G (each with my recommendation; none blocks the build of the checker)

| # | Decision | Recommend | Alternative | Why |
|---|---|---|---|---|
| A | Should every item, fresh produce included, show who made or grew it and the town (your tomato example)? | **Yes.** Required; "I don't know" is accepted and shows today's honest "From the market". | Only packaged goods need a maker | 56 fresh items show the generic line today; it is the biggest visible gap |
| B | May Hass **start** a question on its own (a text to Mike), or only ask while Mike is already talking to it? | **Only while he is talking to it (version 1).** Revisit after a trial. | Hass sends one question a morning | A message Hass starts is new outbound communication (needs your yes); card HASS-TASKMAP-1 is designing the same limits for all Hass-started messages, so decide both together. G-REASON would be `outbound` |
| C | Word to turn gap questions back on after `stop asking` | **`ask me again`** | `resume` | `resume` already means "let approvals apply again" |
| D | Limits: 3 counted questions a day, none 8 pm to 8 am, a follow-up to an answer he just gave not counted, `what's missing` and adding an item not counted | **As written** | stricter or looser numbers | reversible; the numbers are settings |
| E | Photos: keep "own photo" out of the gap questions (170 of 170 are stock pictures; it would take months at 3 a day) and keep the `photos to take` command | **Yes** | ask for photos too | |
| F | Adopt the measured picture numbers as the check, including "shadow optional" and "background within 17 levels of #fef8ec" | **Yes** | keep #504's looser per-channel check | 46 of 170 of the pictures you like have no shadow |
| G | Leave the card box as it is (4:3 on desktop with side bars a shade darker than the picture, square on a phone) | **Leave it; you like it** | make the page colour match the picture ivory | cosmetic, one CSS value |

## 1. Answer in plain words

* **80 of 170 products (47%) have an information gap. The most common missing field is the producer's town (80 products)**, then the producer itself (64). **Plus all 170 still show the stock picture** instead of Mike's own photo (an upgrade, tracked by `photos to take`, not counted as a gap).
* **Gaps by field:** town 80 (64 with no maker or farm at all, 1 brand with no maker record: SLO Cider, 15 whose maker's place is a region). Producer 64: 62 say "From the market", 2 are branded Avocado Shack (Hass avocado, cashews). **Makers:** 6 of 26 show a region, not a town: Straus (7 products), Alle-Pia (3), Sierra Nevada (2), Corberosa, Massa Organics, Ava's (1 each). All 26 have an about text and a website.
* **Measured picture standard:** 800 x 800 square, WEBP lossy, no metadata, about 62 KB; warm ivory background #fef8ec (254, 248, 236); the product's longest side fills 90% (79 to 97%), centred (+1% across, +0.5% down), about 9.5% empty below it; soft shadow 0 to 7 levels (a quarter have none); name `photo-product-NNN.webp`; no stored caption (the page writes "<name> (illustration)").
* **Rendered today (checked in a browser):** no producer = "From the market" above the name and "Ask us about the source in store." under it, no "Meet the maker" box. A missing description is a silent empty paragraph; a missing town would read "Based in undefined". The editor refuses to save these, so only hand edits can produce the last two.

## 2. The picture standard

Full table, best and worst ten, and the comparison with PR #504 are in `docs/hass/ITEM-STANDARD.md` section 2. Evidence: `itemstd-1/picture-measurements.json` (per-picture numbers and distributions), `itemstd-1/best-and-worst.jpg`.
My measurement and #504's agree to rounding. Where they differ: JPEG vs WEBP (deliberate), per-channel background envelope (too loose: admits 27 levels from the median), shadow scored as required (27% of the set has none), "8% bottom margin" (measured 9.5%), a page box described as square (4:3 on desktop), no 112 px phone check. 40 of 170 pictures touch the frame edge, so "margin" is a typical value, not a rule.
Outliers beyond 2.5 robust sigma: background colour 16 pictures, centre across 20, frame not clean 17, uneven background 12, centre down 10, bottom margin 10, subject size 1 (029), shadow 2 (094, 156). 0 identical and 0 near-identical pictures (32 px comparison).

## 3. The catalog audit (all numbers from `catalog-gaps.json`; one row per product and maker)

| Finding | Count |
|---|---|
| Products 172 (170 active, 2 held for a manufacturer concern: not asked about), makers 26 (0 hidden) | |
| Producer class: has a maker 105, "From the market" 62, own brand with no maker 3 (Hass avocado, cashews: Avocado Shack; Zero non-alcoholic cider: SLO Cider, a brand with no maker record) | |
| Packaged 105, fresh 65 | |
| Visibility tier 1 (generic source line on a **packaged** card, the view the shop opens on): 8 (almonds, black beans, chickpeas, crimson lentils, pistachios, red beans, trail mix, cashews) | 8 |
| Tier 2 (generic source line on a **fresh** card): 11 fruit incl. Hass avocado, 44 vegetables, 1 flower bouquet | 56 |
| Tier 3 (a region where a town should be): 15 products of 6 makers, plus the cider | 16 |
| Tier 4 (shelf worth a look): tortilla chips on Vegetables (hard-coded as packaged in `shop.js`); cantaloupe on Vegetables while watermelon and honeydew are on Fruit | 2 |
| Stock picture (the code's own test in `photos to take`) | 170 |
| No stored picture caption | 170 |
| No availability word, and no shelf check day recorded | 170 |
| Exact duplicates, repeated descriptions, identical pictures | 0 |
| Near-duplicate names (7 pairs, all different flavours or forms: cheddars, jams, preserves, fresh vs dried mushrooms, white-chocolate bars) | 7 |
| Generic name beside specific ones on one shelf (Potatoes, Lettuce, Mushrooms, Peppers, and more): worth a human look, not an error | see `audit` in the JSON method |
| Inconsistent category names | none: a closed list of 9 keys, labels match the filter buttons; 3 shelves hold 1 to 3 items (Eggs 1, Flowers 1, Meat 3) |
| Odd characters | only legitimate ones: Montaña de Oro, Jalapeños, Chèvre (search folds accents) |
| Text length | descriptions 59 to 167 characters (none missing or over); one 44-character name; 32 names begin with the producer name already shown right above them |
| Makers with one product (no "See all from" link) | 9 |

By maker (what is missing): Straus town; Alle-Pia town; Sierra Nevada town; Corberosa town; Massa Organics town; Ava's town; every other maker complete. "(no maker on file)": 65 products (the producer gap). Full by-maker lists are in `catalog-gaps.json` `by_maker`.
Each row carries `missing`, `display_problems`, `needs_a_look`, `visibility_tier`, `ask_order` and **`question`**, the one plain question (checked with `hass/voice.py`: 176 questions, none breaks a voice rule), for example "Who grew the blackberries this week?", "Who supplies the almonds?", "Which town is Straus in? The website says Northern California."

## 4. Other findings worth knowing
* `shop.js` hard-codes the "Organic" badge (name contains organic, or one of four maker keys) and the packaged exception (tortilla chips). Both are rules in code, not data; Hass must never set a badge on its own.
* The intro sentence on the page says "An avocado from Morro Bay" while the Hass avocado card says "Ask us about the source in store."
* The ask-flow cannot invent: AGENTS.md says never invent origins; every town must come from Mike or a known source.

## 5. How this changes the skills (concrete edits) and the cards to write

One source: the human standard is `docs/hass/ITEM-STANDARD.md`; the picture numbers stay in #504's `hass/style/house-style.json` (already measured, agrees); a new `hass/style/item-standard.json` holds the fields and asking order. No second picture spec.

| Spec / card | Edit |
|---|---|
| **SKILLS-ITEMADD-1** (card 14, not started; needs #504 merged) | Add rule `standard-complete`: run `check_product` on the planned record before the draft; each missing REQUIRED field becomes the next question in the fixed order (name, shelf, producer, town, photo); "I don't know" is accepted (brand stays "Producer not identified") and opens a gap record. Producer ask: "Who grew it this week?" (fresh) / "Who makes it?" (packaged). Slot `place` must be a town ("Town, State", rule `town-state`). Offer "Same farm as last time?". Proposal gets one line "Still missing: ...". Show the one-time checklist on first use. Picture target = section 2. Side effect `gap-row`. |
| **SKILLS-ITEMPIC-1** (card 15) | `house-picture` rule reads the measured thresholds (background distance 17 / hard 28, shadow optional, bottom margin at least 2.5%, 112 px fill at least 80%); alt text is required and real for an owner photo; retake advice for tan/warm or busy backgrounds. |
| **SKILLS-PIC-1** (card 13, flag-gated render) | Render target is the table in section 2; the check it calls is the aligned one (ITEMSTD-3); compare with the 10 best pictures in a test. |
| **SKILLS-MAKERS-1** (merged #528) | Follow-up card MAKERS-2: rule `town-state` on `maker.add` and `maker.edit` place (a region is refused with "Which town?"; he may say "I don't know the town" and the gap stays open); the "based in" fallback story stays (D5). |
| **SKILLS-ITEMS-1** (merged #527) | No edit: `item.edit`'s maker slot is reused by `gap.fill`. |
| In flight: FW-2 #525, FW-3 #526, HIKES-1 #530, SHOP-1 #531, SPECIALS-1 #529, PR #504, TASKMAP-1 | **No change to any of them now** (they are in review; touching them risks scope creep). Needed later: after FW-3 merges, ITEMSTD-5 adds a `ttl` to `openreq.py` and a way for Hass to open a request with no owner message (system id). #504 must merge before ITEMADD-1 / PIC-1 start (its head moved to `ff732f1` since the skills spec). TASKMAP-1 designs the limits for Hass-started messages; decision B should follow it. |

Cards to write, in build order (tier per WORKER-GUIDE: routine = Sol Medium; substantial = Sol High; reviewer for Sol output = opus-coder):

| # | Card | Files owned | Needs | Tier |
|---|---|---|---|---|
| 1 | **ITEMSTD-2 checker** | C `hass/itemstd.py`, C `hass/style/item-standard.json`, C `hass/tests/test_itemstd.py` (reproduces `catalog-gaps.json` counts on the saved content; every question passes `voice.check`) | this PR | Sol Medium |
| 2 | **ITEMSTD-3 picture check aligned** | M `hass/house_style.py`, M `hass/style/house-style.json`, M `hass/tests/test_newitem.py` thresholds only | #504 merged, Pillow in CI (#522 merged) | Sol Medium; all 170 pictures must pass, the 8 synthetic defects must fail |
| 3 | **SKILLS-MAKERS-2 town rule** | M `hass/skills/makers.py`, its fixtures, `docs/hass/skills/makers.md` | 1 | Sol Medium |
| 4 | **SKILLS-PIC-1** (existing, edited as above) | `hass/ops/photos.py`, `test_house_render_seam.py` | 2, FW-3 | Sol High, independent review |
| 5 | **SKILLS-ITEMADD-1** (existing, edited) | `hass/skills/item_add.py`, fixtures, docs | 1, 3, 4, FW-3, #504 | Sol High |
| 6 | **SKILLS-ITEMPIC-1** (existing, edited) | `hass/skills/item_picture.py`, fixtures, docs | 2, 4 | Sol Medium |
| 7 | **ITEMSTD-5 ask flow** | C `hass/skills/gaps.py`, C `hass/skills/gapstate.py`, M `hass/skills/openreq.py` (ttl), M `hass/conversation.py` (sole owner), M `docs/hass/COMMANDS.md`, `LIMITS.md`, fixtures `gaps/` (at least 10 rows per skill, multi-turn) | 1, 3, FW-3 merged, decisions A to E | Sol High; Opus review (touches the state machine) |
| 8 | **Catalog fill run** (operator, not code) | none | 7 live in private mode | Mike answers about 80 items at 3 a day plus on-demand sessions; the checker shows the count falling |

## 6. The ask-Mike flow: summary and conflicts
Full design is `docs/hass/ITEM-STANDARD.md` section 4. Two conflicts found: (1) `resume` is taken (decision C); (2) the spec says Hass "sends nothing unasked", so version 1 asks only inside a conversation Mike started or on a reply he asked for (decision B). A `no` already cancels an open question and counts as a decline. The example wording in that document is a design; the ITEMSTD-2 and ITEMSTD-5 tests must run `voice.check` on it (the 176 catalog questions already pass).

## 7. Feature backlog: Instagram post for a new item (do not build now)
**What it would do:** when an item is added, or on a command like `post <item>`, render its picture to Instagram sizes in the site's look (ivory, centred, soft shadow): feed portrait 4:5 (1080 x 1350) or square (1080 x 1080), optionally a 3-picture carousel (the item; the maker and town; a serving idea); write a caption in the shop's voice from the house description plus "From <maker> in <town>" (never a price, size or unsaid claim), with the fixed small hashtag set (today `#AvocadoShack` plus one fixed tag per shelf; never from free text); send Mike a preview image. **Mike posts it himself**: Hass never publishes to or sends from a social account. An approval-gated "post for me" is a later G decision (needs a business Instagram account, an API app and credentials in the vault, so login, outbound and publication all apply).
**Depends on:** the item standard (maker, town, photo, description must be complete), the picture render with a canvas size option (SKILLS-PIC-1), `social_draft.build` (exists, caption and tags), `social_draft` recap work in SOCIAL-1, and the image-send path to the owner chat (`bridge_attach.send_png`, endpoint unverified on the real Mac).
**Open questions for G:** 1) feed 4:5, square or stories; carousel yes or no. 2) the hashtag set and a location tag. 3) May Hass mention or tag the maker's account (it never invents a handle; Mike would supply it)? 4) Emoji in captions (VOICE.md says none unless Mike used one). 5) Post at add time or only when he asks. 6) Maker permission to use names and pictures. 7) Later: post-for-me, yes or no.

## 8. Method and limits
* Scripts (`itemstd-1/*.py.txt`, run with `python3`, Pillow 10.2, no numpy): `measure_pictures` (per file: size, format, RIFF chunks, border colour, subject box, margins, shadow), `analyze_pictures` (distributions, robust-deviation score for best and worst, outliers, near-duplicates, sheet), `audit_catalog` (rules over `products.json` and `makers.json`), `build_gaps` (rows and voice-checked questions).
* Rendered facts come from the page's own `card()` function and CSS in headless Chrome on a loopback copy of `storefront-mockup/` (read only), with one field removed at a time and a 1280 px and 390 px window.
* **Machine-valid, not accepted:** best and worst lists are a statistical conformity score (9 measures, robust deviation from the median), not a quality judgment; a human should eyeball the sheet. The shelf hints (2 items) and the generic-name list are heuristics. Real-photo behaviour of the render is still unmeasured (only synthetic photos in #504). The question wording is a draft for a human to read. Weights of the score are mine; thresholds in section 2 are proposals for decision F.
