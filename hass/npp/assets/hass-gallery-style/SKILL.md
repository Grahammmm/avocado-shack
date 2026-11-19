---
name: hass-gallery-style
description: Use when drafting gallery cards. Match the live style.
---

# Avocado Shack gallery style

## When to use
Use for a proposed product card, its photo, and the short chat that presents it. This is a measured house style, not authority to publish, add a shelf, or assert an unverified fact. Preserve the real site's renderer and source-of-truth validation; if essential information is missing, ask only for that information. Otherwise present the rendered card image and one short line, not a transcript or inventory read-back. Never expose private cost or inventory quantities in a public card or in this report.

## Evidence and scope
Observed [the live site](https://theavocadoman.com/) on 2026-11-18 (20:02 UTC, approximate capture window), read-only; desktop, expanded maker and mobile screenshots in `shots/`. The supplied owner examples are `g-examples/site-gallery-today.jpg` and `g-examples/hass-reply-today.jpg`. Code source is private `Grahammmm/avocado-shack` main at `71bb3bad150d358a37c79833db2d970dc03ea693`: `storefront-mockup/shop.js` (card and view rules), `style.css` (layout), `catalog-products.js` (published records), `producers.js`/`producers.json` (makers); Hass's `publish_live.py` and `docs/hass/PUBLISHING.md` name the live URL. Repository prose about an exclusively private sandbox and prices is historical; current source and the actual public page take precedence for what renders now. No login, site modification or server start was performed.

The screenshot's **105 selections means the default packaged-goods view, not the whole site**. The same live catalog has 170 records: 105 packaged and 65 fresh-produce/flowers; the 105 are pantry 61, dairy 20, drinks 15, bread 4, meat 3, eggs 1, vegetables 1 (the chips are a special packaged exception). All 105 were extracted from the live browser's catalog, and their name, description, category, and image path match the checked-out source at the cited commit. `gallery-fields.tsv` has exactly those 105 records, including every visible field, alternate text and the expanded-maker data. One additional non-food flower from the other 65 appears among the twelve examples; it is not included in 105-card statistics. No household/wood-glue product was present among the 170 live records.

## Card anatomy — render order and conditional fields
Desktop: four cards in a row at the captured 1440px viewport. Each has (1) image; (2) small bold displayed brand; (3) large dark-green serif product name; (4) optional selling price, if present; (5) rust-colored `Based in <maker place>`, `From <supplier>` when supplier is present, or `Ask us about the source in store.`; (6) optional Organic and/or New badge and optional availability line; (7) one short product description; (8) optional closed `Meet the maker` disclosure with +; (9) `Link to this` and a divider. There is no separate serving-suggestion field: that suggestion is usually woven into `description`. Opening the maker disclosure shows a story paragraph, optional `Visit <maker>` external link, and, only for makers with at least two catalog items, `See all N from <maker>`. No maker record or neither story nor URL means no disclosure; a URL without story uses `Based in <place>` inside. Visible brand fallback is `From the market`; don't invent a maker.

Mobile at 390px: one column, 112×112px image at left and brand/title/origin/badges to the right; description, disclosure, link run below across the card. Image's whole square is contained rather than cover-cropped; copy remains readable and varies in height. `Link to this` is a deep link; alt text for stock images is `<name> (illustration)` rather than a visible caption. CSS current source uses a 4:3 image box on larger screens and object-fit contain; mobile square under 520px.

### Measured lengths, 105 packaged items
Counts are nonempty values; lengths count Unicode code points including spaces and punctuation; words are whitespace-separated; percentiles use nearest rank `ceil(p*n)`, no interpolation. Expanded-maker text is counted **per product**, not once per unique maker. Alt and URLs are machine/a11y fields, not extra visible prose. Full values and IDs are in the TSV.

| Field | Present / 105 | Words p50 / p90 | Characters p50 / p90 |
|---|---:|---:|---:|
| Display brand | 105 | 2 / 3 | 9 / 20 |
| Product name | 105 | 3 / 5 | 23 / 29 |
| Origin line, including prefix/fallback | 105 | 5 / 6 | 32 / 36 |
| Description (including serving suggestion) | 105 | 25 / 28 | 140 / 156 |
| Expanded maker name | 96 | 2 / 3 | 8 / 20 |
| Expanded maker place | 96 | 3 / 4 | 22 / 27 |
| Expanded maker story | 96 | 44 / 47 | 271 / 280 |
| Maker URL | 96 | 1 / 1 | 40 / 45 |
| Image path | 105 | 1 / 1 | 38 / 38 |
| Image alt text | 105 | 4 / 6 | 38 / 44 |
| Deep-link URL | 105 | 1 / 1 | 56 / 56 |
| Organic badge | 13 | 1 / 1 | 7 / 7 |
| New badge | 0 | — | — |
| Availability | 0 | — | — |
| Selling price | 0 | — | — |
| Fixed `Meet the maker` label (when present) | 96 | 3 / 3 | 14 / 14 |
| Fixed `Link to this` label | 105 | 3 / 3 | 12 / 12 |

All 105 descriptions have two or three sentence endings (88 have two, 17 three). Treat p90 as a **soft target**, not a hard rule or proof that a longer truthful item is invalid. A good default is around 25 words / 140 characters and 2 short sentences; use the real renderer and check fit. There are zero prices in this observed sample, but current `card()` explicitly renders an optional `sellingPrice` after the title: do **not** claim the current renderer forbids prices. The live sample has no New or availability labels; code can show them from time-dependent source records (`New` for the first 14 Pacific days; availability ages to last-confirmed). Never fabricate current availability, New status, origin, organic certification or product claims.

## Voice: do / don't
- **Do** sound like a welcoming, grounded Central Coast neighborhood grocer: warm, observant, practical and conversational, not corporate, breathless or an instruction manual. Use present tense and implied second-person imperatives (`Pour`, `Slice`, `Keep`) alongside short fragments and occasional gentle personification. Name the actual product, maker or place where known, then give a credible use or pairing and a modest human beat.
- **Do** write two short sentences or occasional three, with plain food and table imagery. Not every first sentence needs the product name: `Enough cream to give the coffee some body.` is a complete house-style opening. Serving suggestions are everyday, sensory and specific rather than generic benefit lists. Vary phrasing; existing catalog families do repeat templates, but reuse is observation, not an instruction to duplicate boilerplate across unrelated items.
- **Do** phrase known origin as the maker's base, not proof the ingredients were grown there. Regions occur (`Based in Northern California`, `Based in California’s Central Coast`) as well as town/state. If unknown, use the actual source fallback. Maker story is collapsed, separate from the serving copy: its factual history and place come from the maker's documented source, typically third person and present/past tense with an occasional inviting line; attach an actual public maker link if known. Omit absent unsupported stories.
- **Don't** recite private intake, label every attribute, give a feature/spec bullet list, pad with marketing superlatives, invent factual attributes, health/certification/ingredient/performance claims or imply a manufacturer's base is provenance for all ingredients. Existing descriptions do include claims such as organic and raw: those are examples of existing copy, not license to assume they are verified for a new item. Source or omit each new factual claim.
- **Don't** put cost, stock count, personal information, approval instructions, a line saying something is private, or the assistant's internal reasoning in public-facing copy. Do not send a wall of explanatory chat or reprint the listing as plain text when a rendered card can show it. Keep reasonable public selling price distinct from private cost; render price only if present and allowed by current product policy.

## Image recipe — match the actual gallery
Make the real item recognizable and faithful. Single centered product or cohesive same-item group, largely front-facing label with full shape visible; pale warm ivory seamless background, soft even studio light and, when present, a very light contact shadow. No busy shelf, hands, unrelated props, text overlays, price stickers, added badges or borders. Product shape controls width/height (egg carton wide, bottle tall); do not warp or re-imagine branding, ingredients, certifications, size, package or label. Inspect the result against the original at mobile thumbnail scale; if identity or text is uncertain, ask/label fallback rather than invent a plausible label.

All **105** sampled images are `.webp`, 800×800 pixels, under `storefront-mockup/assets/products/photo-product-NNN.webp`; sampled byte size p50 54,630, p90 87,762, min 23,672, max 108,476 bytes in the matching checked-out source. Visible box is wider 4:3 on desktop but contains the square; mobile is square. Existing published product images are illustrated/AI-derived (renderer appends `(illustration)` to alt unless image path matches owner-installed `assets/products/photo-<16 hex>.jpg|png`). `image-generation-log.json` documents edits of shelf photos into square warm-ivory images; `optimize-images.cjs` records WebP optimization. These are renderings, not proof of precise packaging; the historical prompt permits a representative item for unclear variants, but **do not copy that risky allowance** for a new product. For an owner photo, current naming/alt rules distinguish it from stock; preserve original pixels and source photo, label any fallback, and never silently present an illustration as a verified real photo. An earlier 170-image measurement in `docs/hass/ITEM-STANDARD.md` reports median background #fef8ec and ~90.5% longest-side subject fill; this is useful guidance, not a fresh 105-image color measurement or a mandatory new hard gate.

## Non-food and wood glue
The default 105 contain no non-food. In the all-items view there is one non-food flower listing, `Mixed flower bouquet`, with the same image-first layout and short use/context copy; its unknown maker triggers `From the market`, source fallback and no maker panel. It is not evidence of an existing household shelf. For wood glue, use the identical **renderer and truthful fields**, a concise practical-use description only if supported, no culinary `serving suggestion`, and a faithful clean-background photo. Do not invent manufacturer location, a maker story, package claims or a new shelf; investigate/ask where essential and omit optional unknowns. A suitable supported shelf for glue is a product-policy/schema decision, not proven by the flower example.

## Owner's examples: current Hass vs live gallery
| Dimension | Live reference | Hass example and corrective action |
|---|---|---|
| Chat length | Product copy is ~25 words median; story stays collapsed | The screenshot has a long inventory-style bubble, repeated customer-facing copy and approval explanation. Ask only missing questions or show the actual card image plus one brief approval line. |
| Privacy/read-back | No internal cost or quantity on gallery cards | The bubble repeats private intake and says it is private. Do not repeat those details; keep them out of card and reply. |
| Product card | Real card has brand, title, optional price, origin/fallback, optional badges/availability, short description, optional maker disclosure and link | Preview shows brand, title, price, fallback source, New, Available today, long feature description and link; it lacks a maker panel. Missing maker is a legitimate renderer fallback when unknown, not proof every listing must have one. Research/ask rather than fabricate. New/availability are conditional, not inherently wrong; check their underlying state and date. |
| Description | Short natural use and human context; no separate serving field | Glue preview is spec/feature heavy rather than a short use-oriented gallery description. Don't repurpose food-serving language for glue or assert unsupported performance features. |
| Image | Centered, clean ivory background and consistent contained frame | The preview has a small casual photo with a busy colored background, rather than the full gallery image treatment. Produce a faithful gallery-style image and render the real site card, preserving real label details. |

## Twelve golden examples — direct live descriptions
The following are verbatim product descriptions, not new claims. Structured `golden/*.json` fixtures preserve photo path and all rendered card fields including optional/empty price, badges, availability, maker-story/link and deep link. Eleven are drawn from the 105 packaged sample; the final bouquet is from the separate fresh view. Review actual image files at `https://theavocadoman.com/<photo_path>` if needed. Fixtures are examples, not a source to invent facts for other products.

1. **Montaña de Oro Sea Salt tortilla chips** — Taco Works; Based in San Luis Obispo, California (`photo-product-018`, vegetables).

   > Taco Works chips with Montaña de Oro sea salt, made in San Luis Obispo. Open the bag when the guacamole is ready. Nobody needs a more complicated plan.

2. **Cal Poly eggs** — Cal Poly; Based in San Luis Obispo, California (`photo-product-024`, eggs).

   > Cook gently, season well. Eggs can turn a piece of toast into breakfast and a pot of leftovers into dinner.

3. **Straus half-and-half** — Straus; Based in Northern California (`photo-product-025`, dairy).

   > Enough cream to give the coffee some body. Pour a little, taste, and let the cup tell you whether it needs more.

4. **Brian's sourdough bread** — Brian's; Based in Atascadero, California (`photo-product-015`, bread).

   > Sourdough from Brian’s in Atascadero. A crust worth tearing, a loaf that belongs beside soup. Butter is enough; the rest is optional.

5. **Linn's triple berry preserves** — Linn's; Based in Cambria, California (`photo-product-002`, pantry).

   > Triple berry preserves for buttered toast, a bowl of yogurt, or a plain cake that deserves a little company. Keep a jar where breakfast happens.

6. **Big Sur Honey Company honey** — Big Sur Honey Company; Based in Big Sur, California (`photo-product-042`, pantry).

   > Honey from a family apiary in Big Sur. Raw and unfiltered, with a place behind the jar. Start with a spoonful, then bring out the bread.

7. **Dried mushrooms** — Mighty Cap Mushrooms; Based in Paso Robles, California (`photo-product-044`, pantry).

   > Dried mushrooms are a pantry shortcut to a deeper meal. Soak them, strain the liquid, and use both in rice, soup, or a slow sauce.

8. **Maple Valley dark and robust maple syrup** — Maple Valley; Based in Cashton, Wisconsin (`photo-product-052`, pantry).

   > Organic dark and robust maple syrup from a Wisconsin cooperative. This is a place for pancakes, yes, but also oatmeal and a warm slice of cornbread.

9. **Crimson lentils** — From the market; Ask us about the source in store. (`photo-product-138`, pantry).

   > A quick-cooking pulse for soup, dal, or the base of a simple dinner. Toast a few spices in oil before the lentils meet the pot.

10. **Alle-Pia Calabrese salamini** — Alle-Pia; Based in California’s Central Coast (`photo-product-021`, meat).

   > Calabrese salamini from Alle-Pia on the Central Coast. Slice thin, bring out bread and cheese, and let the table fill up slowly.

11. **Fair Hills Farm apple juice** — Fair Hills Farm; Based in San Miguel, California (`photo-product-007`, drinks).

   > Apple juice from Fair Hills Farm in San Miguel. Pour it cold with breakfast: the orchard belongs at the table as much as the toast does.

12. **Mixed flower bouquet** — From the market; Ask us about the source in store. (`photo-product-006`, flowers).

   > A little color for the kitchen table. No occasion required.

## Repo copy (NPP-A)
This file is the GALLERY-STYLE study copied as is (2026-11-18). In the repo the files it names live next to it:
`golden/*.json` (the twelve cards, shape in `card.schema.json`), `gallery-fields.tsv` (the 105 measured records) and `limits.json` (generated from the
TSV by `python3 scripts/hass/npp_limits.py`; never edit it by hand). The screenshots (`shots/`, `g-examples/`) stay in the
private report folder and are not runtime assets. Hash-pinned in `hass/npp/pins.json`: change a file here only through a
card that refreshes the pin (`hass-npp-maintain`).
