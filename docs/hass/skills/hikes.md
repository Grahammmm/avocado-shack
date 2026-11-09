# Hike skills (SKILLS-HIKES-1)

Six skills let Hass add, change, move, cancel, repeat and write up a hike, and draft the post about a hike that has happened.
They are in `hass/skills/hikes.py`. Design: `reports/hass/SKILLS-SPEC.md` 3.10 to 3.15. Authoring guide: `docs/hass/SKILLS.md`.
Wording follows `docs/hass/VOICE.md`: short, plain, no ids, "I can't do that yet" said honestly.

The model reads the sentence and fills slots. These skills turn the slots into typed `hike.*` ops. They write nothing themselves:
every draft still goes through the editor, the claims check, the preview and the owner's `yes <code>`. Nothing is sent to
anyone: a move or a cancel never tells guests, and the draft says so when guests have signed up.

## The six skills

| Skill | What the owner says | Slots (R = asked when missing) | Plans |
|---|---|---|---|
| `hike.add` | "add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water" | R title (default: "<place> hike"), R day, R time, R meeting place; sign-up (default off), guest limit, no limit, route idea, difficulty, distance, duration, bring, access note, description | `hike.create` |
| `hike.edit` | "change the Cass Hill meeting point to the upper lot" | R which hike; any of title, meeting place, the text fields, sign-up, guest limit | `hike.update` |
| `hike.reschedule` | "push the Morro Rock stroll to 10am" | R which hike; R a day or a time (the other keeps its value) | `hike.update` (date, time) |
| `hike.cancel` | "cancel the Point Buchon hike, rained out" | R which hike; a one-line note | `hike.cancel` |
| `hike.repeat` | "do the Cass Hill hike again on the 29th at 9" | R which hike, R day, R time | `hike.repeat` |
| `hike.recap` | "the Cass Hill hike went well, 9 people, saw whales" | R which hike, R how it went | `hike.complete` (not yet marked done), `hike.recap` (already done: corrects the words) |

Slot names are snake_case (the lint requires it): `meeting_point`, `access_note`. They become `meetingPoint` and `accessNote` in
the ops and the content.

### What is never invented

* **Sign-up is off** unless the owner said otherwise (decision D8). The proposal carries the line `I set: sign-up off.`
  (see "The `I set:` line" below). A guest limit is written only with sign-up on and only if he gave the number. "Sign-up on" with
  no number and no "no limit" is left to the editor, which asks "how many can come, or is there no limit?" (HASS-E2E-HIKE-1 found
  the model adding `rsvpEnabled: true` and `capacity: 10`, and `capacity: 1`.)
* **His words decide the direction, not their presence** (rule `hike-no-invention`, add and edit alike). Sign-up on needs his
  latest sign-up instruction to be on: "sign-up off", "no sign-up", "without rsvps", "don't let people sign up" never turn it on
  ("no limit" is about the guest limit and is taken out first, so "sign up with no limit" stays on; a later "actually no sign
  ups" beats an earlier "sign up please"). A guest limit needs a number he tied to guests: "15 spots", "max 15", "limit of 15",
  "cap Cass Hill at 3", "twelve people". The 12 in "December 12", a clock time, a year, "5 miles", "2 liters" or a number he took
  back ("not 12 spots, 20 spots") is not one; his latest limit wins. Sign-up said off while the slots say on, sign-up said on
  while the slots say off, an edit that turns sign-up off with no word about it, a limit together with "no limit", or "no
  limit" without his words for it, all get one plain question ("I'm not sure if you want guests to be able to sign up. Should
  they?" or "You didn't say how many can come ...") and nothing is drafted.
* Difficulty, distance, duration, bring, the access note and the description are written exactly as he gave them (case and
  spelling kept) and never filled in. A trail fact he did not say is asked about by the claims check, not written.
* A place that is not a route idea is plain meeting-point text. `trailId` is set only when he names a route idea. A new hike is
  never forced onto a trail (HASS-HIKE-FLOW-1).
* The title is his if he gave one; otherwise "<place> hike" from the route idea or the meeting place, with a trailing
  "trailhead", "gate", "parking lot" and the like dropped. A place with no name of its own ("the gate") gets a question instead.

### Refusals and questions (one plain reply, nothing drafted)

* A day or time that has passed, or more than 400 days away. A twin: a scheduled hike with the same title that day.
* A hike that is cancelled or already done (change, move), already cancelled (cancel), not started yet or cancelled (recap).
* A move to the day and time it already has. A price in any text (`The website doesn't show prices`).
* Sign-up or a guest limit that his own words do not contain, or contain the other way ("sign-up off" never turns it on). A
  guest limit needs a number tied to guests, not a date.
* A move with neither a day nor a time asks "What day or time should it move to?".

The rules run twice: in the dispatcher (when it is present) and again inside each plan, so a plan can never draft what a rule
refuses. Guests who signed up never block a move or a cancel; the editor's own warning stays on the draft ("N guests have signed
up, and nobody is told automatically"). If the guest count cannot be read, the editor refuses a change to the guest limit and
warns on a move or cancel, and the draft says it cannot see the guests.

### Undo

Every skill drafts `history.revert` through `undo`; it needs its own `yes <code>`.

* `hike.add`, `hike.repeat`: the hike stays on the page as **cancelled**. The editor cannot delete an event.
* `hike.edit`, `hike.reschedule`, `hike.cancel`: back exactly as it was. Guests were not told, before or after.
* `hike.recap`: a hike that has already started stays done. Undo refuses to reopen it (it would be scheduled in the past). Send a
  new recap to correct the words.

### Live boundary (`live_policy`, unchanged)

`hike.reschedule` and `hike.cancel` are `chat-live` while sign-up is off (HASS-LIVE-PLAN-1: a hike with sign-up on stays private). `hike.add`, `hike.edit`, `hike.repeat` and `hike.recap` are `private-only`
because they can carry difficulty, distance, duration, an access note or a route link, which `live_policy` protects. A test
checks both classes against `live_policy.check` on real drafts.

## The post about a hike that happened

`hikes.recap_announcement(content, hike_id)` returns `{"draft": True, "caption"}` or `{"draft": False, "reason"}`. The caption is
the title, the Pacific day ("Saturday, November 14"), his recap exactly as written (cut at a sentence end only if it would be
too long for one post), then `#AvocadoShack #NorthCoastHikingClub`. It adds nothing: no people count, no thanks, no link, no
account. It refuses a hike that is not done, one that was cancelled, one with no recap, and a recap containing `#` or `@`. It
posts, schedules and saves nothing.

    python3 hass/skills/hikes.py announce <hike id>

`social_draft.py` belongs to SKILLS-SOCIAL-1, which owns the skill `social.recap` and `social_draft.build_recap`. This card does
not edit it. SOCIAL-1 can call `recap_announcement` or replace it.

## How it fits with the rest (interface assumptions)

Nothing here edits `conversation.py`, `interpreter_prompt.py`, the router or `dispatch.py` (SKILLS-FW-2 PR 525, FW-3 PR 526).
It was proved with the test kit and works with the dispatcher in PR 526 as written. What it assumes:

* `ctx` has `content` (read-only), `today` (a date or an ISO string), `now` (aware) and `texts` (the owner's words so far). Each is
  optional: a plan row may give only `today`. Without `content` a rule that needs the hike simply gives no verdict.
* Rules are `RULES[id](slots, texts, ctx) -> None | (reply, reason)` and a default `derive:place_title` is a function of this
  module. `hikes.py` registers its rules and `place_title` with `hass.skills.dispatch` when that module exists, with `setdefault`
  so it never replaces another skill's rule. Rule ids start with `hike-` except `no-price`. The spec calls the twin rule `twin`;
  it is `hike-twin` here because `item.add` has a different twin rule and the dispatcher's table is shared.
* **The `I set:` line** (D8). The dispatcher in PR 526 renders a default as `name: value`, which would read "I set: signup:
  False." A skill module may therefore carry its own wording: `hikes.SET_PHRASES["hike.add"](slots, ctx)` returns the plain phrases
  of what the skill chose for him, from the slots **as he gave them, before defaults** (`["sign-up off", "the title “Mill Creek
  hike”"]`, sign-up first; empty when he said it himself), and `hikes.set_line(phrases)` joins them: `I set: sign-up off.`
  * **Consumed here:** the test kit's stand-in dispatcher (`testkit.py`, `SkillInterpreter._plan` and `Scratch._with_set_line`) calls
    the hook for every plan and puts the line in front of the real Conversation's proposal text, as FW-3's
    `Conversation._draft(..., prefix=...)` does. So the fixtures assert the line in an actual owner reply
    (`expect.set_line`, on every add that leaves sign-up off), and `test_the_owner_reply_of_a_real_draft_carries_the_line_through_the_kit`
    proves it with and without him saying sign-up.
  * **Not consumed yet by the real dispatcher.** PR 526 has no hook, and this card does not edit `dispatch.py`. `hikes._register()` hands
    `SET_PHRASES` to `dispatch.SET_PHRASES` only if that dict exists. The change FW-3 needs is small: in `apply_defaults`, when
    `SET_PHRASES.get(skill.name)` exists, build `shown` from `fn(slots_before_defaults, ctx)` instead of `"name: value"` (and keep
    the generic text for skills without one), and add `SET_PHRASES: dict = {}` next to `DERIVERS`. Until then, hikes plus PR 526
    would show `I set: signup: False` (jargon, caught by `voice`); the follow-up is recorded on the card and on PR 526.
* A partial change to a text ("add sunscreen to what to bring") sends the whole new text, which includes words already on the
  page. The dispatcher's owner-words check (`traceable`) counts only the owner's messages, so it would drop those old words and
  list the field under "Left off". The words on the page being edited should count as the owner's. This is not changed here.
* The spec says the dispatcher asks for a guest limit when sign-up is on and none was given. Here the editor already asks that
  (`needs-details`), so `capacity` is optional and a separate `no_limit` slot carries "no limit".

## Tests

    python3 -B -m unittest hass.tests.test_skills_hikes hass.tests.test_skills_plans hass.tests.test_skills_cases -v
    python3 hass/skills/testkit.py run hass/tests/fixtures/skills/hikes/hike.add.jsonl

Case rows are in `hass/tests/fixtures/skills/hikes/<skill>.jsonl` (107 rows: plan rows for the exact ops, case rows through the
real Conversation, Editor, sitegen and claims, with the exact content diff and undo back to the start). They include:

* the three live texts of 2026-11-08, word for word (`live-1-mill-creek`, `live-2-fiscalini-alone`, `live-3-fiscalini-new-hike`)
  and the whole sequence ending in a draft, not a question (`live-sequence-ends-in-a-draft`);
* the HASS-E2E-HIKE-1 text with the invented sign-up and capacity, which is refused, and the same text drafted without them;
* the sign-up and guest-limit evidence rule, one sentence said in each direction: "sign-up off" is never turned on, "December 12"
  is never a guest limit, and the controls (nothing said = off with the `I set:` line, sign-up on with no limit, sign-up on with 15
  spots, sign-up off said by him = off with no `I set:` line), on add and on edit;
* a refusal or question for each rule above, and a row that undoes every draft that can be undone.

Every recorded row names the hike it changes: `test_every_recorded_row_changes_the_hike_its_words_name_on_the_day_they_name` checks
the seeded title (or its date) against the owner's words, and the weekday he says against the day in the slots.

Rows record the interpreter's reply; a person still reads every model-written text in the acceptance report (SKILLS-ACC-2).
Machine-valid is not accepted.

### Changes to the test kit that this card needed

The kit (`hass/skills/testkit.py`, SKILLS-TK-1) had four gaps that a hike skill hits:

1. **`seed` on a row**: `{"community": {"events": [...]}}` puts a hike on the scratch page before the row starts, validated,
   regenerated and committed. The repository content has no events, so edit, move, cancel, repeat and recap could not be
   tested without it. The row's diff and its undo are measured from the seeded state. Only `products`, `makers`, `community`
   and `store` can be seeded; a seed the content rules refuse is a `bad-row`.
2. **`undo.residue`**: the kit looked for `skill.residue`, which only the toy skills have. A real skill's residue is
   `skill.undo.residue`, so every skill with a declared residue failed as `residue-undeclared`.
3. **`ctx.texts`**: the kit's context now carries the owner's texts, as the dispatcher's does, so a rule that reads the owner's
   words (the invented sign-up check) is tested for real.
4. **`SET_PHRASES`**: the stand-in dispatcher asks the skill's module for `SET_PHRASES[skill name]` (when it has one) and puts the
   `I set:` line in front of the proposal text. Without that, the `expect.set_line` check of the kit could never see a skill's
   own wording of a default. A module without the hook is unchanged.

`model.lint_cases` counts undo rows as `kind: "undo"` or `undo: true`; the kit refuses both (it undoes every approved draft
itself). So `skill_lint(..., repo_root=...)` reports "at least 1 undo row" for any skill. `test_skills_hikes` checks the
equivalent (a row that is approved and undone) instead. One of the two files should change in a later card.
