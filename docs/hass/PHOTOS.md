# Product-photo detail reads

With `itemIntake: true` and the existing label reader configured, a single new
product photo is read once, outside the conversation's write transaction. Only
the metadata-free web copy goes to the existing interpreter route. Codex and its
one local fallback are unchanged; this change does not add a model, key, service,
network permission or live run. Photo effort remains the configured effort.

## What is read

The reader requests a JSON object with these optional strings:

- `name`, `brand`, `category` (a value from the supplied catalog categories)
- `product_type`, `size` (printed size/volume/weight and units), `count` (pack count,
  **not** shop stock), `colour`, `finish`, `materials`
- `barcode` (fully legible digits only, preserved as text including leading zeroes)
- `description` (a plain one- or two-sentence website draft)

`features`, `warnings` and `printed_claims` are lists of printed lines. Missing or
unreadable details stay absent; the model is told not to invent hidden text,
benefits, materials or origins. Lists are bounded to 24 entries per field, lines
to 400 characters and descriptions to the existing 600-character content limit.
Unknown keys are ignored. Controls, markup, template delimiters and money text
are refused. Claim terms found in ordinary detail fields are moved into
`printed_claims`, including lookalike-letter claims in name/brand/category.

For the reported Gorilla bottle this retains Wood Glue, 4 fl. oz. (118 mL),
Dries Natural Color and Made in USA, instead of keeping only its brand and name.
No photo-derived price, cost or shop quantity is accepted.

## Interview and caption

The owner first sees the ordinary details and confirms them with a plain `yes`.
They fill only missing name/maker/category slots; caption facts are not replaced.
Each printed claim then gets its **own** question:

> The label says: Made in USA. Put that on the website?

Only a plain explicit `yes` includes that claim in the candidate description.
`no` and `skip` exclude it; an ambiguous answer asks again; `cancel` drops the
request. Confirmation of the photograph is not approval of its claims, and neither
answer applies a website change. The final exact draft still needs owner approval.

A caption such as `Bought for $1, sell for $2, 20 of them` fills private cost
`1.00`, price `2.00` and quantity `20` (each) in that same request. Complete
finance clauses separated by commas, semicolons, newlines or an appropriate
`and` are read by fixed code; other caption words use the normal interpreter.
Ambiguous or conflicting amounts are not guessed. Private finance clauses are
not sent with the image or fed into the public-description interpreter.
Previously supplied answers are not asked again.

All details, the photo confirmation and each claim decision stay in the private
request. When the draft is applied, its private intake record also retains a
`photo_read` receipt; claims remain unverified label wording, not verified facts.
Size, pack count, barcode and warnings are retained here even when the catalog
has no public field for them. Rejecting the read never fills public slots.

## Existing gates and limits

Content, house wording, owner approval and protected live-site claim checks are
unchanged. A label `yes` is not an override of a live-policy hold. If the photo's
description or approved wording cannot pass those checks, the proposal says it
was left off and keeps the details privately. The catalog still shows no prices;
photo size numbers do not bypass its existing no-number description check.

A failed read leaves the existing interview and typed caption values intact.
The setting-off/legacy photo path remains a question, not automatic product ops.
Multiple-photo and attachment safety boundaries are unchanged.

Offline tests: `hass.tests.test_photo_detail_read` supplies a canned JSON model
reply for the task's reported glue details and drives the real Conversation,
dispatcher, draft and apply path using a synthetic stored photo. This proves the
contract and consent flow, **not** new live OCR accuracy on the original bottle.
