# Skill cases (fixtures/skills)

One cases file per skill: `hass/tests/fixtures/skills/<group>/<skill name>.jsonl`, one JSON object per line. Every skill
group card adds only its own files here; the kit (`hass/skills/testkit.py`) and the two generic runners
(`hass/tests/test_skills_plans.py`, `hass/tests/test_skills_cases.py`) pick them up by themselves. A group folder
starting with `_` is the kit's own self-test and is never run as a skill (see `_selftest/`).

## Run

```
python3 hass/skills/testkit.py run hass/tests/fixtures/skills/<group>/<name>.jsonl     # one skill
python3 hass/skills/testkit.py all                                                    # every skill
python3 hass/skills/testkit.py selftest                                               # the kit proving itself
python3 -B -m unittest hass.tests.test_skills_plans hass.tests.test_skills_cases -v   # what CI runs
```

Exit code 0 when every row passes, 1 when a row fails, 2 when the file cannot be read. Each failing row names the
problem code and the first thing that differs.

## Plan row (level 2: slots in, exact ops out; no model, no git)

```json
{"id": "plan-describe", "plan": true, "skill": "stock.set", "slots": {...}, "ctx": {}, "expect_ops": [{"op": "...", "args": {...}}]}
```
`expect_error` (text the refusal contains) replaces `expect_ops` for a refused combination. The kit also checks the plan
contract: only registry ops, 1 to 20 of them, the same answer twice, the slots not changed. `skill` is needed only when
the file name is not the skill name.

## Case row (level 3: the real Conversation, Editor, sitegen and claims on a scratch writer worktree)

```json
{"id": "clean-1", "kind": "clean", "version": 1,
 "texts": ["eggs are out"],
 "replies": [{"skill": "stock.set", "slots": {...}}],
 "expect": {"skill": "stock.set", "disposition": "proposed", "ops": [...], "diff": [...], "files": [...], "preview": {"kind": "product"}}}
```

* `kind`: `clean`, `vague`, `typo`, `multi`, `refuse`, `photo`, `turns`.
* `texts` are the owner's messages, in order (distinct). `replies` is the recorded interpreter reply for each: a skill reply
  `{"skill", "slots"}` or `{"calls": [{"skill", "slots"}, ...]}` goes through the skill's own `plan`; a `{"question"}`,
  `{"unsupported"}` or raw `{"ops"}` reply is played as it is. A plan that raises (a refusal) becomes an `unsupported`
  reply carrying the exception's `reply` text.
* `version`: the skill version the row was written for; a different skill version fails the row as `stale-row`.
* `approve: false` stops after the draft and the wrong-code check (no apply, no undo).
* `seed`: `{"community": {"events": [...]}}` (a content file name: `products`, `makers`, `community` or `store`, then the
  top-level keys to replace). Put a record on the scratch page before the row starts: validated, regenerated and committed,
  so the row's diff and its undo are measured from that start state. A seed the content rules refuse is a `bad-row`. Use it
  when the repository content has none of what the skill acts on (it has no hikes).
* `I set:` line: a skill module may define `SET_PHRASES = {skill name: fn(slots as the owner gave them, ctx) -> [plain phrases]}`.
  The kit's stand-in dispatcher calls it for every plan and puts `I set: <phrases>.` in front of the proposal text (what
  SKILLS-FW-3's dispatcher does with the defaults it shows), so `expect.set_line` and `reply_not_contains: ["I set:"]` read it
  in an actual owner reply. A module without the hook gets no line from the kit.
* `setup` (optional): a list of `{op, args}` ops applied through the real editor before the row starts, so the row can begin
  from a state the shop's content does not have (for example a hidden product to bring back). They are the row's base, never
  part of its diff or its undo. Used by `items/item.restore.jsonl`.
* `undo: true` (optional marker): the row ends in an approved draft that the kit then undoes; the kit fails the row if it did not.
* **Proposal notes** (assumed contract, `items.py` is the first user): when a skill's module defines `notes(name, slots, ctx)` returning
  `{say, set, warn}` lists of lines, the kit plays it after the skill's plan and appends the lines (once each, in that order) to the reply of
  a message that ends in a draft. This is what the dispatcher is assumed to show beside the proposal; the live conversation does not show them yet.

`expect` fields (all optional except `diff` when the row ends in a draft):

| field | checks |
|---|---|
| `skill` | the skill (or list) whose plan ran |
| `disposition` / `dispositions` | how the last message (or each message) ended: `proposed`, `question`, `unsupported`, `refused`, ... |
| `question_contains`, `reply_contains`, `reply_not_contains` | words in the last owner reply (case does not matter). When the final message ends in a draft, the reply also carries the skill's proposal notes (see below) |
| `left_off`, `set_line` | words in a `Left off:` / `I set:` line of the reply (the `I set:` lines come from a skill's proposal notes) |
| `ops` | the exact ops of the draft |
| `diff` | the exact content change: `[{"file", "path", "before", "after"}]`. `path` is a key path such as `products[photo-product-001].description` or `hours`; `before` is absent for something added, `after` for something removed; JSON is compared parsed, key order ignored |
| `files` | required on every row that ends in a draft: the exact set of files the commit touched (content and generated); a missing or extra file is `wrong-diff` |
| `preview` | required on every row that ends in a draft: fields the preview request of the final proposal (the last message's) must contain, e.g. `{"kind": "product", "id": "photo-product-001"}` |
| `residue` | what `undo` leaves behind: `[{"file", "path"}]`; empty or absent means the tree must come back identical |
| `allow_words` | words a reply may show although they look technical (a product's own name) |

### What the runner does with a row

1. Starts a scratch writer worktree and private state (a copy of the repo content, a fixed Sunday 09:00 PST clock, a synthetic owner).
2. Sends each text. After **every** message the worktree must be unchanged: no commit, no file (`write-before-yes`).
3. If the last message ended in a draft: asks the preview of the final proposal (the request that last message caused is recorded and checked, no browser; an earlier proposal's preview never counts), sends `yes zzzz` with a wrong code (nothing may change), then `yes <code>`.
4. Compares the commit with `expect.diff` and `expect.files` (`wrong-diff`) and with the skill's declared `edits` (`edit-undeclared`).
5. Sends `undo`, then `yes <code>` for the undo draft. The real worktree is then checked: nothing uncommitted or untracked, content equal to the start except the row's `residue`, every other file as at the start, and every site file equal to a fresh render of the restored content (the editor re-sorts JSON keys on every write, so site files are judged against that render, not the start's bytes). The skill's `residue` sentence must say so (`undo-not-identical`, `residue-undeclared`).
6. Checks every owner-facing reply for plain words: no internal id (`photo-product-001`), operation or skill name, `json`, `slot`, hash or braces (`jargon`). The draft's own record lines are the conversation's house format and are left alone.

A model-written text is machine-valid here, never accepted: a person reads it in the acceptance report.

## The kit proves itself

`_selftest/toy.py` has four toy skills (not in any registry). `_selftest/toy.jsonl` has plan and case rows; a row with
`"must_fail": "<code>"` (and optionally `"fault": "write-on-prepare" | "undo-leaves" | "undo-stale-generated" | "undo-dirty" | "skip-later-preview"`, a deliberately broken skill path)
has to fail for exactly that code, and every other row has to pass. `must_fail` and `fault` are refused in any other file.

Not covered yet (later cards): pictures (`photo` rows need the house render of SKILLS-PIC-1), the real dispatcher
(SKILLS-FW-3; until then the kit turns skill replies into ops itself), and the live-model run (`ACC-1`).

## `qa1/`: owner regressions from the HASS-QA-1 battery

`qa1/owner-battery.jsonl` is not one skill's file: each row replays an owner's own words from the HASS-QA-1 battery
(2026-11-09) with the reply the real local model (`qwen3.8:27b-thinkingcap-q6`) gave for them, in the ops-only path the shop
runs by default (no `skill` in the replies, so the kit plays the recorded `ops`, `question` or `unsupported` as it is). The kit's
fixed Sunday clock is the clock the battery was recorded on, so the rows pass on any calendar day. Hike, refusal-wording and
preview-check conversations are HASS-CHAT-1's (`hass/tests/fixtures/chat/scenarios.json`) and are not repeated here; the
full per-conversation ledger and its coverage map are in `reports/hass/QA-1.md` (agent-work).
