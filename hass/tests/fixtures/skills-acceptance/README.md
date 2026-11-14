# Skills acceptance fixtures (SKILLS-SPEC 4.3, card 18)

The offline acceptance engine is `hass/skills/acceptance_run.py`. It plays recorded interpreter replies through the real
`Conversation`, `Dispatcher`, skills registry, `Editor`, `sitegen` and `claims` on a throwaway writer worktree and state dir,
with a frozen clock (Sunday 2026-11-08 09:00 Pacific, one minute per message) and a synthetic owner. Only the interpreter
(recorded), the screenshot and the outbound chat are in-memory stand-ins. It touches nothing live and never edits `testkit.py`.

```
python3 -B hass/skills/acceptance_run.py --selftest                 # the engine proving itself: 8 rows, 4 faults (exit 0)
python3 -B hass/skills/acceptance_run.py [--rows FILE]              # every row of messages.jsonl (default; refuses when missing)
python3 -B hass/skills/acceptance_run.py --record ROW [--rows FILE] # write the MISSING expected/ROW.json and print it
python3 -B -m unittest hass.tests.test_skills_acceptance_offline    # what CI runs
```

Exit 0: every assertion met. 1: an assertion failed. 2: a malformed row, fixture, flag or setup (nothing ran). The thresholds are
constants in the module (`THRESHOLDS`): offline structural, outcome, diff and undo are 100%, wrong drafts, unstated or invented
claims and writes before approval are 0. No flag or API argument lowers them; an unknown or weakening flag exits 2. The live bars
of 4.3 are kept as `LIVE_BARS` for card 19 and are not evaluated here.

**A passing run is not human acceptance, and a partial or `--selftest` run is never the full-site acceptance** that gates
SKILLS-POS-0. Model-written text and pictures are read by a person.

## Row (messages.jsonl, one JSON object per line, schema version 1, closed)

```json
{"id": "hours-friday", "schema_version": 1, "tag": "primary", "skill": "shop.hours", "skill_version": 1,
 "texts": ["we're open till 7 on fridays now"],
 "replies": [{"skill": "shop.hours", "slots": {"hours": ["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Saturday 9am–5pm · Closed Sunday"]}}],
 "expect": {"skills": ["shop.hours"], "dispositions": ["proposed"], "expected": "hours-friday.json", "undo": true}}
```

* `id`: `[a-z0-9][a-z0-9_-]*`, unique in the file. `tag`: primary, vague, typo, multi, turns, refuse, photo or selftest.
* `skill` / `skill_version`: the skill the row is about (`none` and `null` for a command or question path). A version that is not the
  registry's is stale and refuses the run.
* `texts`: the owner's messages in order (an empty text is allowed only for a photo turn). `replies`: the recorded interpreter
  replies, an ordered queue consumed ONLY when `Conversation` really calls the interpreter (commands and cheap answers do not).
  A reply is exactly what the model would return (`{"skill", "slots"}`, `{"calls": [...]}`, `{"question"}`, `{"unsupported"}`):
  the real dispatcher validates and resolves it, so slot values are the model's words ("lemons"), not ids. Running out of replies
  or leaving one unused fails the row. Replies are never keyed by message text.
* `expect.skills`: the allowed skills, observed from what actually ran (`none` = a command, question or refusal path). `expect.dispositions`:
  the exact production disposition after each text (`proposed`, `question`, `unsupported`, `backlog`, ...; `question` is not collapsed into
  `needs-details`). `reply_contains` / `reply_not_contains`: fragments of the last reply (before any approval). `expected`: required for a row
  that ends in a proposal, `<id>.json`. `undo`: after the approval, `undo` then its own `yes`.
* `expect.picture` (photo rows): `{kind: product|hero, type: jpeg|png, size: [w, h], house: off|pass|warn}`. A product picture is square when
  `house_render` is on; a home hero is exempt. A `warn` row must name the warning the owner sees before approving (`reply_contains`).
* Optional: `setup` (ops applied through the real editor before the row), `seed` (content keys written and regenerated before the row),
  `photos` (`[{turn, fixture}]`: owner turn index and a fixture-root-relative `.jpg`/`.png`, no `..`, no symlink; the photo goes through
  `Conversation._photo` and the media store), `house_render` (the `houseRender` setting), `offsets` (extra minutes before each text, 0 to 2880).
* Self-test only (`_selftest/`): `fault` and `must_fail`; they are refused in any ordinary file.

## expected/<id>.json (version 1)

`{schema_version, diff, files, assets, residue}`: `diff` is the committed content diff as `{file, path, before?, after?}` entries (parsed JSON,
key order ignored; a key or list item that appears or disappears is one entry), `files` every changed file (content, generated, pictures),
`assets` every added or changed picture as relative path to SHA-256, `residue` the exact allowed leftovers after undo
(`{content: [entries], assets: {path: sha}}`). There is no whole-file exemption. The path keys are the testkit's (`products[id].field`).

`--record ROW` observes a real scratch approval and undo and writes ONLY a missing `expected/ROW.json` (exclusive create, no symlink
followed); it never overwrites, never edits `messages.jsonl`, and refuses a symlinked fixture folder. **The printed candidate is the
engine's observation, not evidence that the row is right: a person reads every line against the spec before it is committed.**

## What is asserted (4.3 items 1-5 and 7-9)

Routing, disposition, no write before yes (content, generated files and `assets/products` hashed, HEAD and tree clean, also after a wrong
yes), the exact diff, files and picture hashes on approval, content rules (validation, text limits, no price or size nobody said, no
invented capacity, difficulty or sign-up, no unstated claim, picture name, type, size, metadata and house check), undo back to the tree
except the declared residue (the skill's Undo sentence AND the pinned entries), duplicate delivery after every message and approval, and
no owner text, sender, chat or path in `interpreter_audit` or the stage log. Item 6 (the browser preview) is the live runner's.

## Handover to the full corpus (AV1109-17)

AV1109-17 adds `messages.jsonl`, `expected/` and `chain.jsonl` here and consumes this engine and schema unchanged. The engine accepts any
registered skill; skill coverage is enforced there, not here. `_selftest/` is the engine's own and is never run as a skill.

## Primary corpus (AV1109-17)

`messages.jsonl` holds one `tag=primary` row for every active registered skill (41 at this commit, derived from `load_skills()` by
`PrimaryCorpus`, never hard-coded; the retired `page.faq` keeps its name but has no row) plus five `tag=photo` companions: 46 rows, 32 `expected/` goldens. The first owner text of each
primary row is the first numbered example sentence of the skill's catalog entry (SKILLS-SPEC section 3; specials.md for the five
specials skills; social.md for social.maker; skills/front.md for the four front skills), tags such as `(p)` removed. **This is a partial acceptance run (Primary only, not the
historical 72 rows) and a passing run is not human acceptance.** The builder read each golden against the typed plan and the skill's
declared edits and Undo sentence (for example hike.add keeps a cancelled event, page.photo keeps its hero file, stock.restock changes
`products.json` only); that is a builder check, not a G or owner review.

Exchanges: where the router ties two skills (SKILLS-SPEC 2.5) or a first example is incomplete, the row is a short honest exchange:
item.add (stock?), item.hide (plums are not on the site, then "the lemons"), item.picture, stock.restock (three honeys, then the pick),
maker.add (state), specials.add (end day), specials.show, social.item/hike/recap. `more honey coming Thursday` is Thursday 2026-11-12.
`morning report` is an existing command, so its row is command-covered (no model call, disposition `report`).

RF0535-13 refreshes only the house-render JPEG hashes for jar-white-sheet.jpg and bottle-grey-wall-tilted.jpg,
including the forward/undo chain goldens and final residue assertion. Real scratch approval/undo with Pillow 12.0.0
on main `db18a64` reproduced the old hashes; the affine-fit renderer produced the new hashes with identical content
diffs, asset paths, changed-file inventories and undo content. Source photos and all acceptance checks are unchanged.

Photos (`photos/`, copied byte for byte from `reports/hass/newitem-1/synthetic/`): clean jar-white-sheet.jpg (item.add),
bottle-grey-wall-tilted.jpg (item.picture), jar-phone-rotated.jpg (page.photo, hero, no product render), bottle-bench-png.png and
jar-cutout-alpha.png (item.add companions, `house_render` on, 800x800 jpeg); warned bag-bench-small.jpg, jar-dark-wood.jpg,
bag-red-cloth.jpg (item.add companions).

### Held rows (pinned to today's behaviour; each needs its owner, then a re-record)

* `photo-bag-bench-small`, `photo-jar-dark-wood`, `photo-bag-red-cloth`: a warned picture is refused (`not-drafted`); the D6 knowingly-approved
  fallback of AV1109-05 is not available, so no warning-then-yes path is claimed. These rows have no golden.
* `primary-item-restore`: now proposes, applies and undoes; hidden resolution is allowed only for this skill. Held products remain refused.
* `primary-page-about`, `primary-maker-edit` (`question`): `traceable()` in `hass/skills/dispatch.py` never accepts an owner-words value containing "and"
  (it is a clause splitter), so the owner's own sentence is asked for again.
* `primary-stock-set` (`question`, `question`): the router ties stock.set with stock.checked and the follow-up ties again.
* `primary-hike-reschedule`: now checks exact undo with an isolated empty RSVP database. The old failure was the missing guest-count fixture, not byte restoration; the production capacity gate is unchanged.
* `primary-hike-recap` retains `undo: false`; recap repair is outside this card.

## Forty non-primary rows (AV1109-18)

`messages.jsonl` appends exactly forty `acc-*` rows, one exclusive tag each: `vague` 10, `typo` 8, `multi` 8, `refuse` 8, `turns` 6 (counted by
`hass/tests/test_skills_acceptance_groups.py`; the report template `reports/hass/SKILLS-ACCEPTANCE-TEMPLATE.md` shows the measured counts). Total corpus =
registry-derived Primary + the five photo companions + 40 = 83 at this commit. Every text is synthetic. Two engine controls were added (the rest of the
engine is unchanged): `senders` (a row text may come from a `stranger`, who is ignored before any model call) and `expect.approval: "paused"` (the
proposal is made under the current policy and the real `yes <code>` is refused with no write; such a row has no golden and no undo).

Goldens (`expected/acc-*.json`, 22) exist only for rows that end in a proposal; the other 18 rows assert an unchanged site tree (content, generated
files and assets/products byte-identical, HEAD and tree clean) and are not given empty goldens. Each golden but one was recorded once with `--record ROW` and then
read against the typed plan, the skill's declared edits and its Undo sentence; that is a builder check, not an owner review. Review inventory:
typo-01 eggs shelf word `no` + shelf-check day; typo-02 one new hike (Cass Hill gate, Sat 14 Nov 9am); typo-03 `Cal Poly strawberry jam` hidden;
typo-04 eggs sold-out flag cleared; typo-05 avocado `limited` + shelf-check day; typo-06 Linn's story; typo-07 Friday hours; typo-08 notice until 27 Nov;
multi-02 two new hikes in one draft; multi-03 two new makers; multi-04 three products (plums, dried figs, walnut oil, added by `setup`) hidden;
multi-05 two product descriptions; multi-06 two hike meeting points; multi-07 two sold-out flags cleared; multi-08 hours + notice in one draft;
refuse-02 the maker without the "certified organic ... since 1990" story the owner never said (`Left off (you didn't say it): story`);
turns-01 the hike built over three messages; turns-02 reschedule to 10am after a one-word answer; turns-03 only the corrected Friday 8pm; turns-05 the
fresh request after the 30-minute request TTL (offset 31 minutes); turns-06 the lemons picture sent before the words (photo bound by real dispatch); multi-01 lemons yes, strawberries no, peppers limited + shelf-check day
(hand-written, because the row cannot be recorded while it fails; its seven diff entries were checked by running the same slots under a reworded message that the
router does not tie, which drafted and undid identically).

Known failures (genuine, recorded, not accepted; the row keeps its SKILLS-SPEC 4.3 expectation of zero questions, one exact approved diff and a clean undo):
* `acc-multi-01` (`wrong-disposition`): the router ties the shelf-check and stock skills on "the strawberries are sold out", so the owner gets a question
  instead of one draft although every slot was given. The offline thresholds are not met until the owner fixes the router; then delete the
  `KNOWN_FAILURES` entries in `test_skills_acceptance_groups.py` and `test_skills_acceptance_offline.py`.

Behaviour pinned to today's code (not a claim that it is right; each needs its owner, then a re-record):
* `acc-vague-03` ends `refused` with the question "What should change on Guacamole?" (the dispatcher words a missing field as a refusal).
* `acc-turns-04`: with a hike question open, a new notice sentence is asked about again (`question`, `question`) instead of dropping the old slots into a draft.
* `acc-refuse-02`: the interpreter-invented claim is not refused outright; the dispatcher leaves the story off and drafts the maker without it.
* `acc-refuse-08`: `pause` returns `pause`, the proposal still drafts, and `yes <code>` returns `paused` (draft kept, tree unchanged).
* The multi-item `item.hide` row uses three `item.hide` calls, because the dispatcher's `items` slot takes one product name per call.

## Persistent change-and-undo chain (AV1109-19)

From the repository root:

```
python3 -B hass/skills/acceptance_run.py --chain hass/tests/fixtures/skills-acceptance/chain.jsonl
python3 -B -m unittest hass.tests.test_skills_acceptance_offline hass.tests.test_skills_acceptance_chain
```

`--chain FILE` is exclusive with `--rows`, `--record` and `--selftest` (including empty explicit options).
It has the same exits: 0 all assertions pass, 1 an assertion fails, 2 invalid input before scratch creation.
Ordinary row admission, missing-only recording and thresholds are unchanged. Chain files use a separate
namespace: contiguous `chain-01` through `chain-NN` (at most 24), one text per `tag=turns` row. The full fixture
and its inventory test require exactly 24. Setup, seed, house-render and photos belong only to the first row;
photo turn indices are global, zero-based forward request indices. Continuations pin exact request skill,
slots, asked slot, calls and attachment hashes; a slotless plan question additionally pins its exact question.
Proposals pin the complete typed ops, a forward golden and `undo: true`. Every existing inverse golden is
validated before scratch; a missing inverse fails before any undo delivery, never counts as full success.

### Count convention and task order

This is **24 scripted forward requests, not 24 total messages**. The driver opens one real session and keeps
all approved changes while adding Pebble jam and its new maker (01–03), marking it in (04), changing description
(05) and picture (06), hiding/restoring the seeded lemons (07–08), adding a future hike (09–11), moving it (12),
changing its meeting point (13), cancelling it (14), changing Friday hours (15–16), adding a dated notice (17–18),
changing the home intro (19–20), getting a read-only caption (21–22), reading the current report (23), and logging
one unsupported request privately (24). Clear owner wording is intentional where the router legitimately ties;
no router bypass or canned read-only answer is used.

The 13 original approvals are 03,04,05,06,07,08,11,12,13,14,16,18,20. Only then does the driver undo their original
codes in strict reverse order, each once, using a new named approval for each inverse, never undo-of-undo.
The passing fixture reports **24 requests, 128 controls, 152 deliveries, 13 originals and 13 inverses**.
Controls include wrong-code yes, named approvals, undo requests and duplicate replays; duplicates are actual
deliveries too. Forward-only counts are 24 requests, 63 controls, 87 deliveries. Counts are observed at the real
say/replay boundaries. No direct apply, clock reset, snapshot restoration or safety exception is used.

### Golden review and exact residue

The builder independently specified the forward and reverse deltas against the typed plans/history contract,
then cross-checked the real run; neither a recorder nor a passing machine check is semantic acceptance.
There are exactly 13 `chain-NN.json` and 13 `chain-undo-NN.json` goldens. Each checks the immediately preceding
approved tree, including exact content presence/values, complete changed-file set and picture hashes. Inverse
review inventory: intro/notice remove their added keys; hours restore the original Friday grouping; cancel,
meeting-point and reschedule restore the prior hike record; hike creation leaves that original hike cancelled;
restore/hide return lemons through hidden to its initial active state; picture restores the old reference and
alt text while retaining the orphan file; description and stock restore their original values; item+maker undo
hides both new records, removes the item's availability/day and removes the new shelf-check day.

The final inverse (`chain-undo-03.json`) pins the complete residual added records: hidden Pebble Kitchen,
hidden Pebble jam (original description/image, no stock word/day), and the cancelled added hike (original
start and meeting point, no cancellation note). Both exact committed picture paths and SHA-256s remain pinned.
All other parsed content and original assets must match the initial tree; generated bytes must equal fresh
sitegen for that exact residue and git must be clean. There is no whole-file exemption. The final vague request
remains exactly one open private backlog row, checked separately, never an exception to public-tree equality.

The full offline test checks one session, all 37 ordered results at 100%, all exact counts, 26 applied drafts,
private backlog, and sanitized residual hashes. Mini-chain negatives retain checks for schema/mixed modes,
missing/malformed inverses, corrupt middle deltas, wrong targets, preapproval writes, duplicate/privacy faults,
stale requests, cancelled/expired/stale approvals, undeclared residue, orphan bytes, dirty and stale generated
files. Machine-valid photos/caption still require human review; this is not live or full-site acceptance.
