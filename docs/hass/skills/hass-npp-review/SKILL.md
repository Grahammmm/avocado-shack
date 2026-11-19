---
name: hass-npp-review
description: Use for the weekly Hass new-product review (HASS-NPP-WEEKLY). Redact, list findings, one failing case per defect.
---

# Weekly review of the Hass new-product pipeline

## When to use
Every Monday 09:00 PT, when astra-orchestrator opens `HASS-NPP-WEEKLY` (design section 4c). Two lanes: **local-worker** (local
model, because transcripts hold private cost and quantity) reads transcripts and job receipts and writes the redacted
findings; a builder lane then turns each real defect into one failing case plus its fix.

## Procedure (local-worker)
1. Read the week's private transcript rows and `<mediaRoot>/npp/<job-id>/receipt.json` files. Do not copy any of it off the host.
2. Write a **redacted** findings list. One line per: owner edit, fallback, question, "no", slow job (over 75 s), judge score
   under 4. Replace every digit run with `<n>`, drop phone numbers, emails and street names, and never record cost or quantity
   (only the flags `has_cost` and `has_qty`).
3. Mark each line with the stage (S1 to S13), the fallback or guard code, and the case id it matches, if any. A repeat of a
   closed failure class is logged as a repeat incident.
4. Read the trend first: `~/agent-work/reports/hass-npp/metrics.tsv` (first-card validator pass rate, judge mean and minimum,
   approved without edit, edits per listing, questions per listing, fallback rate per kind, time to card p50 and p90,
   guard replies per listing, repeat incidents). Targets: judge mean 4.2 or more, approved without edit 70% or more,
   picture fallback 10% or less, p90 75 s or less, repeat incidents 0.

## Procedure (builder, per finding)
1. Write one failing case from the redacted line using the template below. Ids are `npp-YYYYMMDD-n`, permanent.
2. Fix the asset or code, show the case failing before and passing after, then follow `hass-npp-maintain`.
3. Each finding has an owner on the card. A chat note never closes a finding.

## Case template
```
{"id": "npp-YYYYMMDD-n", "title": "...", "contracts": ["<what it protects>"], "path": "listing|question|contract",
 "terminal": "published|asking|retake|expired|card_out", "settings": {...}, "turns": [...], "expect": {...}}
```
Photos are synthetic or product-only, never people or chat screenshots. Fixtures hold no real price, cost, quantity or name.

## Pitfalls
- A transcript line that still carries a number or a name in the findings list: redact again before it leaves local-worker.
- Closing a finding because the owner "didn't mind". The case exists so it does not come back.
- Fixing the symptom in a reply template when the cause is an asset or a gate. Name the stage first.
