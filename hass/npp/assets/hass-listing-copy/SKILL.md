---
name: hass-listing-copy
description: Use when choosing the public wording of a new card (S5). Pick reviewed template and phrase IDs only.
---

# Listing copy (pipeline stage S5, with the S7 conformance gate)

## When to use
Stage S5 selects wording for `name`, `imageAlt`, `description` and the optional `story` of one product. It also governs
any later edit that asks for different wording ("shorter", "less fancy"). Public copy is built from reviewed sentences
and typed slots only (design R2.2): less varied wording is accepted so that an unsupported fact can never be added as prose.

## What the model does
The model sees: the product kind and category, the allowed template and phrase IDs for those, and the kept fact IDs
(if any). It never sees the price, cost, quantity, the owner's sentences or the photo. It returns `listing.schema.json`:
template and phrase IDs only. Choose by fit: a maker and town known, use the maker-and-town description; no maker, the
plain one. Vary phrases within the kind so cards in one shelf do not read identically, but never to add meaning.

## What code does
1. Binds each slot to an independently resolved typed value (`copy-templates.json` `slot_types`): item from S2, brand,
   maker and town from the owner's words or a verified official-site fact, label size from S2 confirmed by OCR, fact slots
   from kept facts. A slot is a typed value with provenance, never a sentence, quote or chat span.
2. Renders the pinned template with the chosen reviewed phrases (`voice-phrases.json`, kind and category allowed).
3. Compares the **whole** field to that rendering (S7). Unknown IDs, extra fields, a token outside the rendering, a
   needed slot that cannot be bound, or a story with no kept fact: the field takes its deterministic default (`defaults`)
   and the reply line says `basic wording`. An optional story without support is simply absent.
4. Applies the existing gates unchanged afterwards: `claims.unstated`, and with `liveSite` `live_policy.unsaid` and
   `live_policy.check`. After removing an offending value it rebuilds and rechecks the affected field.

## Rules
- A description carries no researched fact: only identity, maker (when provenance allows), kind, label size and reviewed
  use or pairing wording. A story binds at least one kept fact (`nature`, `makes` or `founded`) and is third person.
- Non-food gets practical-use wording, no serving words. A candle with food words in its name is still a candle.
- Digits in public copy come only from a copied label size or a kept `founded` year. No money, no private number, in any
  spelling, ever (design 1.9).
- Limits: `hass-gallery-style/limits.json` (description 2 to 3 sentences, soft 156 and hard 200 characters; story soft 280
  and hard 340). Warn above the p90, fail above the hard limit.
- Gallery voice: warm, grounded neighbourhood grocer; see `hass-gallery-style`. Superlatives (`banned_words`) never appear.

## Pitfalls
- Adding a phrase to the bank that quietly asserts something (an ingredient, a method, a place). A phrase is reviewed
  for assertions or it does not go in.
- Letting a lexicon of "factual words" stand in for the conformance check. A lexicon is a secondary lint only.
- Choosing a template whose slots cannot be bound: pick the maker template only when maker (and town) are bound.
- Editing a template or phrase without refreshing the pin and running the cases that name copy (30, 36).
