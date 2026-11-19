---
name: hass-listing-edit
description: Use when the owner changes a drafted card in plain words (S10). Grammar first, then map or ask; never paste.
---

# Listing edits (pipeline stage S10)

## When to use
The owner answers a delivered card with a change: "make it $4", "made by Miners", "shorter", "use my photo". Each applied
patch builds a new immutable version (`<code>-<n+1>`); version n is never changed.

## Procedure
1. Try the deterministic forms in `edit-grammar.json`, in order. A form that matches gives a field patch directly.
2. If none matches, send the model the message and the listing schema and ask for `edit.schema.json`: a patch list or
   `ask`. The model never writes public text. `ask` is a first-class answer and costs one question, not a guess.
3. A wording request ("shorter", "less fancy") reruns S5 for that field only, with the same reviewed templates.
4. A picture request gets `edits.picture_request`: "Send me another photo and I'll use that one." A new photo is a new sha
   with its own S6 (the polish decision is write-once, and a restart never starts a second edit).
5. Re-validate (S7) and re-render (S8) the new version. If the message cannot be mapped, ask ONE question and leave the
   card unchanged.

## Rules
- An owner message is never pasted into public text (F1). A value he sets (a price, a name, a maker) is a typed field
  value that goes through the same templates and gates as any other.
- `made by X` sets the maker; a town goes with it only in the same message or when asked. `from X` is the supplier line.
- Brand, maker and town become public only under the existing rule: his words, or a verified official-site fact
  (`hass-maker-research`). The existing live gates stay the last word.
- A message that arrives while version n+1 is building (before S7) is folded into n+1; later it supersedes n+1.
- Nothing here publishes. Approval is `yes <code>-<n>` of a delivered card (design 1.3).

## Pitfalls
- Matching `from` inside a sentence ("from 3 to 4 dollars"): forms match the whole message.
- Treating "add: ..." as public text. It is a note the model maps to a slot, or it is asked about.
- Letting a price edit also change the unit silently: a unit that is not said stays as it was.
