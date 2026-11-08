# Weekly specials skills (SKILLS-SPECIALS-1)

Five skills on top of the AVO-SPECIALS-1 ops (`specials.add`, `specials.edit`, `specials.remove`, `specials.clear_expired`).
Code: `hass/skills/specials.py`. Model and authoring guide: `docs/hass/SKILLS.md`, spec `reports/hass/SKILLS-SPEC.md` section 2.
The model reads the sentence and fills the slots; this module checks them, plans the typed ops and words the replies. Approval,
preview, claims and undo are the existing ones (`yes <code>`, `undo`).

| Skill | What Mike says (examples) | Plans |
|---|---|---|
| `specials.add` | "put the avocado honey on special this week, 2 for 5 dollars" · "special on jam till Friday" · "new special: free sample Saturday, through the 14th" | `specials.add` |
| `specials.edit` | "extend the honey special to next Sunday" · "change the jam special to 2 for 6 dollars" | `specials.edit` (only what changes) |
| `specials.remove` | "take the special off" · "remove the honey special" | `specials.remove` |
| `specials.clear_expired` | "clear out the old specials" | `specials.clear_expired` |
| `specials.show` | "what are this week's specials" | nothing (read-only answer, `show_reply`) |

## Slots (add)

`product` (a product, optional) · `title` (required unless a product is named; then the product's own name, if it is plain and at most
60 characters) · `deal` (required; **the deal line, shown exactly as typed**; the one place a price may appear) · `end` (**required**;
if missing the one question is "Until what day should it run?") · `start` (optional; today when missing) · `picture` (optional; a
named product's picture is used unless he says no). Edit: `special` (his words: "the honey special", "jam", "the special") plus any of
`title`, `deal`, `start`, `end`, `product`, `clear_product`. Remove: `special`.

## Checks (rule ids are prefixed `specials-`)

`deal-as-typed` (the deal must appear word for word in his texts, standing on its own: not the tail or head of a longer figure or word, so `2 for $5` is refused when he typed `12 for $5`, `$5` when he typed `$5.50`, and a deal cut just before `free`, `off`, `each` or a figure is refused too; a deal missing its front is refused as well (the word before it, with commas stepped over, must not be part of a deal: `get one free` when he typed `buy one get one free`, `for $5` when he typed `12 for $5`, `price` of `half price`); when the edge is unclear he is asked to type the deal; a reworded or cut deal asks him to type it) · `text-limits` (60 characters each,
no markup or hidden characters) · `no-links-or-contact` (no web address, email or phone number) · `price-in-deal-only` (a price in the title
is refused, whether a sign or figure (`$3`, `3 dollars`, `€5`) or spelled out (`five dollars`, `twenty-five cents`, `a buck`), for a typed title, an edit's new title and a product's name used as the title; `five pound jar` is a weight, not a price: D9 stays for every other price) · `end-date-required` · `dates` (last day not past, not before the first day, at most 31 days) ·
`max-six-active` (never more than six on one day; the reply lists the running ones and asks which to take off) · `twin` (same title already
running) · `room` (20 saved at most; offers to clear the finished) · `which` (one special, else one question naming the candidates) ·
`something-to-change` · `not-already-true` · `finished-to-clear`. Each is one function in `specials.RULES`, run by the plan and (when it
exists) by the dispatcher.

## Preview, approval, undo, live

Preview target `home` (the page with the box). Approval `owner-yes`. Undo `revert`; residue **none** (proved: the tree after undo equals the
tree before, including the saved list key). Live class `private-only` for all four changing skills: a deal line may carry a price and
`live_policy` refuses a changed sentence with a price (proved on drafts in the tests); a deal without a price would pass.

## Interface assumptions (the dispatcher SKILLS-FW-3 is not on main)

* `plan(slots, ctx)`: `ctx.today` (date or YYYY-MM-DD); `ctx.content` (read only) and `ctx.texts` optional. A refusal is `specials.Refusal`
  (ValueError with `.reply`, the plain-words text). `day` and `product_ref` slots arrive resolved (ISO date, product id); `special` is plain words.
* `specials.RULES[id](slots, texts, ctx) -> None | (reply, backlog reason)` and `READ_ONLY["specials.show"]` are handed to `hass.skills.dispatch`
  when that module exists (`setdefault`, never replacing another group's rule). Checked against the open FW-3 branch (ee115b5): all 56 tests of this card pass there.
* Day words: `kinds.day` gives "Friday" and ISO dates; "next Sunday" said on a Sunday is two readings, so he is asked which day.

## Found while building (not fixed here: outside the owned files)

1. **`hass/interpret_check.py` refused the `deal` argument** (`STRING_KINDS` lacked it), so every specials draft from chat asked "I need a detail
   as words". One word added here (it is the only edit outside the owned files; a test pins it).
2. **The approval text does not show the special.** `voice.FIELDS` has no `specials` and `voice.value_words` cannot say a list of records, so the
   draft reads "the shop details, a detail: from nothing to more than I can show here". Mike sees the page preview but not the words. Needs a
   small voice/conversation change (a follow-up card).
3. With the current FW-3 dispatcher a rule hit is logged to the backlog and a plan refusal's `.reply` is replaced by its generic "could not set that up".
4. The lint's per-skill "undo row" count cannot be met: the kit rows have no `undo` field (the kit undoes every draft itself).

## Tests and fixtures

`hass/tests/fixtures/skills/specials/<skill>.jsonl` (time-stable rows: plan golden, questions, refusals, recorded answers) are run by `test_skills_plans` /
`test_skills_cases`. `hass/tests/fixtures/specials/e2e.jsonl` holds the draft, wrong-code, yes, exact diff, undo rows that need a calendar: their dates are
`{d+N}` offsets from the shop's real today (the editor uses the real clock), some start from pre-saved specials; `show-content.json` feeds the show rows.
`hass/tests/test_skills_specials.py` runs all of it plus the rules, finder, voice, live boundary and hook tests.
Run: `python3 -B -m unittest hass.tests.test_skills_specials hass.tests.test_skills_cases hass.tests.test_skills_plans`.
