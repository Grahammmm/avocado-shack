---
name: hass-product-identify
description: Use when reading an owner's product photo (S2). Fill the fixed JSON; never infer price or origin.
---

# Identify a product from its photo (pipeline stage S2)

## When to use
Stage S2 of the new-product pipeline: one vision read of the owner's photo (and the back-of-pack photo, if sent in the
same message) to the fixed schema `identify.schema.json`. The runtime asks `gpt-6.2-sol` at effort low (see `pins.json`)
with local Qwen as the in-budget fallback. Code, not the model, decides what to do with the answer.

## Procedure
1. Look at the product, not the room. Read only what is printed on the package or visible on the item.
2. Fill every field of `identify.schema.json`; use `null` or `[]` when something cannot be read. Never guess to fill a gap.
3. `kind`: `food`, `drink`, `non-food` or `fresh` (loose produce or flowers with no package). The kind follows the
   object, not the label wording: a "lavender honey candle" is `non-food`.
4. `item`: the plain product name as a shopper would say it (`Raspberry jam`), keeping the product kind. Never drop the kind
   (a candle stays a candle). Do not add the brand to `item`.
5. `brand_on_label`: the brand exactly as printed, or `null`. It is a research and mismatch hint only; the pipeline never
   publishes it by itself (see `hass-maker-research`).
6. `size_text`: the net weight or volume exactly as printed (`10 oz`), or `null`. `label_words`: up to 12 distinct label
   words you can read with confidence, as printed. `visible_claims`: claim words printed on the package (`Organic`,
   `immune support`), recorded so code can drop or keep them under the existing claims rule. Recording a claim is not
   permission to publish it.
7. `has_person_or_screen`: true when a person, a face, a hand holding it up, a phone or computer screen, or a chat is in
   the frame. This flag keeps the raw owner photo off the website.
8. `confidence`: a number from 0 to 1 per field. Low confidence makes code ask a question; it does not stop the read.
9. `is_product`: false when the photo shows no sellable item (sunset, selfie, screenshot, receipt).

## Never infer
Selling price, cost, quantity, origin or town, maker, certification not printed, health benefit, ingredients not printed,
production method. A price tag or price sticker in the photo is not a selling price: leave it out and set nothing from it.

## Pitfalls
- Reading an owner's cost sticker or a shelf price into `label_words` or `size_text` puts private numbers in public text.
  Number-like tokens go in `label_words` only when they are part of printed product wording (`No. 9`), never a price.
- A blurry or irrelevant photo is `is_product: false` or low `confidence.item`, not a best guess.
- Do not translate or "correct" label spelling.

## Examples
`examples.json` holds six reviewed few-shot reads (code injects them; they are valid against the schema and checked in CI).
