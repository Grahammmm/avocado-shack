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
