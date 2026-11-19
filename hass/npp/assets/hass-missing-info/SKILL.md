---
name: hass-missing-info
description: Use when deciding what to ask an owner about a new product (S3). Ask only what code cannot know.
---

# Missing information (pipeline stage S3)

## When to use
Stage S3. It runs in code only: `missing-info.json` is the whole rule table, so the same photo and words always give the
same questions. No model decides what is essential.

## Procedure
1. Run the rule table in `ask_order`. An essential is missing when its `needed_when` holds.
2. Selling price and its unit are never read from a photo, a label, a web page or a model. They come only from the
   owner's words (caption, answer, edit), in a span that is separate from any cost span. A conflicting, ambiguous or
   model-fallback price is treated as missing, so it is asked and never guessed (for example `4 or 5 bucks`).
3. Ask at most two questions in the whole reply, from the fixed templates, in `ask_order`. A missing price is asked with
   the one price-and-unit question unless his words already gave the unit. No read-back, no greeting, no explanation.
4. Ask each essential at most twice in the life of the job. A question that was answered is never asked again.
5. Everything not listed as essential is optional and is omitted when unknown (`omit_dont_ask`). In particular brand,
   maker and town are never asked for.
6. Apply `maker_resolution` (exact, near match, contradiction, new maker) and the duplicate check before replying.

## Rationale
The owner is busy and non-technical (G, 2026-11-18): a reply is either a short question about something Hass cannot know,
or the finished card. The gallery is short and consistent; padding a card with asked-for optional detail is what
made the old reply a wall of text.

## Pitfalls
- Asking for a maker or story because the card would look fuller. That belongs to research or to the owner's own `made by`.
- Treating a bundle or basket price as a per-item price (basket rule, #1046).
- Putting the owner's cost or quantity into any question or note. They stay in the private intake slot.
- Using the Clover cache lookup for anything but the duplicate check (local, read-only).
