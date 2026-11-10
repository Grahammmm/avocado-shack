# Shelf report skill (SKILLS-SOCIAL-1 part 3, AV1109-08)

One read-only skill, `report.shelf`, in `hass/skills/reports.py`. Spec: `reports/hass/SKILLS-SPEC.md` section 3.30. It answers
shelf questions from the existing report engine (`hass/morning_report.py`). It changes nothing, asks for no approval, keeps no
stock counts and sends nothing on its own.

| What Mike says (examples) | What he gets |
|---|---|
| "what's sold out?" · "wat is low today" · "how are we doing" · "what's on the shelves" · "what's sold out and what hikes are coming up" · "what did I check last" · "anything waiting for me?" | exactly `morning_report.render(morning_report.facts(content, today))`: no intro, no waiting list, no question, no clock of its own |
| "how many eggs do we have" | `I don't keep counts; the last check says eggs: limited` (the product's own word, see below) |
| "email me the report every morning" | `I don't send reports on my own. Ask me for the morning report when you want it.` (no schedule, no email, no backlog row) |

The model only picks the skill (the sentences above are its examples). Code writes the answer: the skill declares no slots and its
plan is empty (`plan_shelf` returns `[]` and reads nothing).

## The report text

Same inputs, same bytes as the `report` command's first part: the last shelf check and whether it is old, dated in the future or
missing; available / running low / sold out / not confirmed counts of products (never stock counts); the running-low and sold-out
names (duplicates once, "Salt (2)"; hidden and held products never); hikes today or tomorrow (guest counts say they are unavailable,
never 0). The engine caps its own text at 1200 characters. Mike's own product names stay marked (`voice.quote`), and the ordinary
voice and plain outbox deliver it.

**Longer than an everyday message.** A full report can pass the 600-character everyday limit, so `dispatch.READ_ONLY_LONG` (a set
beside `READ_ONLY`) lets `Dispatcher._read_only` pass `long_ok=True` for this skill only. Nothing is cut and the strict voice check
still applies to everything else (no `ids_ok`, no catching of voice errors). `hass/skills/reports.py` adds `report.shelf` to the set when it
is imported; the caption skills (AV1109-06) use the same set.

## A count question

"How many eggs do we have" is read by code from Mike's own words (`how many` / `how much` / `number of`…), the product is found with
`kinds.product_ref` (his nicknames count), and Hass answers with that product's own recorded word and nothing else: `yes` →
"available", `limited` → "limited", `no` → "sold out". The word counts only as the report counts it: it must be dated on the latest
shelf check. A missing, invalid, undated or older word is "not confirmed". It never borrows another product's word and never turns
a word into a quantity. When the check itself is old, in the future or missing, the report's own sentence for that is added on a second line.

* Unknown or unclear product: the finder's one question (`I don't know a product called that. What is it called on the site?`,
  `Which one do you mean: …?`). Nothing is guessed.
* Held or hidden product: `That one isn't in the shelf report right now, so I can't say what the last check found.`
* A count of things in general ("how many things are sold out", "how many hikes", "how many do we have") is the report itself,
  which already holds the shelf counts and the hikes.

## Unreadable content

If the report cannot be read (a product record without a usable name, or no content), Mike gets the report command's own sentence:
`I can't read the shelf report right now, so I can't tell you what's on the shelves. Nothing has changed.` No error or file detail.

## The `report` command stays the command

The whole messages `report` and `morning report` are the `report` command (`conversation.parse_command`), which runs before any skill
and never reaches the model. It alone appends the waiting list and asks the once-a-day shelf-check question (`SHELF_ASK`, recorded
in `control.shelf-asked`). The skill is only for other wordings and never writes `shelf-asked`, so asking the skill twice does not
use up the command's question and the command still asks under its old conditions.

## What is and is not written

The skill makes no `editor.prepare`, `apply` or publish call, no commit or content change, no draft, approval, backlog row, schedule
or `shelf-asked` write (the tests record all of these). The ordinary framework bookkeeping for any message still happens (the message
and its reply in the outbox, usage, closing an open request); this is not a promise of zero database writes. A repeat of the question
is answered again; a bare `undo` afterwards says there is nothing to undo.

## Routing note

The router (`hass/skills/router.py`, unchanged) scores a plain "what's sold out?" about equal with the three stock skills, which share
those words, so with the real router the owner is first asked which task he means and the pick he then makes stands. The typo,
vague, multi, count and email sentences lead the router's list and are answered at once.

## Tests and fixtures

`hass/tests/fixtures/skills/reports/report.shelf.jsonl` has 13 versioned rows (all ten sentences of the spec, three refusals and the
no-op `undo` as a `turns` row). The kit (`test_skills_cases`) plays the recorded text back; `hass/tests/test_skills_reports.py` replays
every row through the real Dispatcher and Conversation (skills mode both, a scripted skill-reply stand-in for the model, writer
content edited per row) and compares the delivered text byte for byte. Like `specials.show`, the lint's "undo row" count cannot be met
by a kit row. Run: `python3 -B -m unittest hass.tests.test_skills_reports hass.tests.test_skills_cases hass.tests.test_voice`.


## Site answers (AV1109-09, SKILLS-SPEC 3.31)

`answer.site` is another read-only skill. The model supplies only `kind`, optional `subject` and optional `day`;
code writes the answer. Undeclared answer/text/summary slots are discarded, never sent. The closed kinds are:

| Kind | Source and answer |
|---|---|
| `hours` | Saved `store.hours`, for the supplied day or Pacific today. Original matching clause, not invented opening/closing times. Unclear or conflicting clauses show the stored lines with an honest caveat. |
| `next_hike` | Next real scheduled event strictly after now, ordered by aware instant then id: title, Pacific day/time and its own meeting point. Missing details say so. |
| `hike_count` | Count of that same valid upcoming set, explicitly called upcoming hikes. No samples, past, cancelled or completed events or route ideas. |
| `product` | Existing product resolver (including nicknames), saved active product and its own last-check shelf word, with the shelf report's stale/missing/future caveats. This does not verify a live installation. |
| `product_maker` | Only that product's `producerKey` linked to a visible maker: saved name and place. Missing maker/place is stated honestly. |
| `maker_story` | Existing maker resolver, then saved story verbatim, not a summary. Only this kind gets a per-call long-answer exception; all strict voice rules remain. |
| `hike_signups` | Existing real-hike resolver, then confirmed party-size sum from trusted `guestCountsDb`, opened read-only by `guest_counts_checked`. No participant names/emails are selected. |

A readable RSVP table with no rows for the hike confirms **0**. Missing setting, unreadable path/table, or a malformed
party size for that hike means **unavailable**, never a guess. Bad rows for another hike do not spoil a confirmed count.
No creation, repair, migration, participant listing, network access or cached estimate is involved.

Examples: “what time do we close Saturday”, “who makes eggs and where”, “tell me Sunny Farm story”,
“when and where is our next hike”, “how many signed up for Cass Hill”. Names are resolved by the existing product,
maker and hike resolvers. Unknown kinds/subjects or incorrect slot combinations use the existing catch-all and one backlog
row; missing kind asks one question. Resolver questions on this catch-all path do not establish a continuation.
Sales, prices and numeric stock-count questions are refused with one backlog row and no edits, even if the model labels
them as hours. The separate `report.shelf` count behavior is unchanged. Read-only plans return no ops and need no approval.

The versioned `answer.site.jsonl` cases are replayed through real Conversation + Dispatcher in `test_skills_reports`,
including poisoned model prose, refusal bookkeeping, strict voice delivery, a no-op undo and confirmed/unavailable totals.
All content and RSVP fixtures are synthetic and outside canonical stores.
