# Hass skills: authoring guide

A skill is one thing Hass can do for the owner, written as data plus one small pure function. The interpreter picks a
skill and fills its slots with the owner's words. Code checks the slots, plans the ops and asks the one missing
question. The editor, the claims gate, the live boundary, the preview and `yes <code>` approval do not change.

Design and catalog: `reports/hass/SKILLS-SPEC.md`. This page covers what exists after SKILLS-FW-1: the model, the
registry, the lint, the slot resolvers and the catch-all backlog.

## Where things live

| File | What it is |
|---|---|
| `hass/skills/model.py` | `Skill`, `Slot`, `Trigger`, `Undo`, `SLOT_KINDS`, the lint functions |
| `hass/skills/__init__.py` | `load_skills()` (finds every module's `SKILLS`), `skill_lint(skills, ops_registry)` |
| `hass/skills/kinds.py` | resolvers for the skill-level slot kinds (`product_ref`, `maker_ref`, `hike_ref`, `route_ref`, `shelf`, `availability`, `day`, `clock`, `attachment`) |
| `hass/skills/backlog.py` | the "I can't do that yet" store, plus the skills `backlog.log` and `page.faq` |

To add a skill, add a module to `hass/skills/` that exports `SKILLS = (...)`. No list is edited, so two cards never
touch the same file. A duplicate skill name raises when the registry loads.

## The fields every skill fills

`name` (`group.verb`, never reused or renamed; retire with `status="retired"`), `label` (owner words, never the id),
`summary` (at most 120 characters), `triggers` (at least 6 `Trigger(text, tag)` examples with tags `clean`, `vague`,
`typo`, `multi`; at least one each of vague, typo and multi; no text may appear in two skills), `slots`, `rules`
(named, tested rule ids), `plan`, `edits`, `side_effects`, `preview`, `approval`, `live_class`, `undo`, `refuse`,
`cases` and `version`.

* `plan(slots, ctx)` is pure: it returns a list of `{"op": ..., "args": ...}` using only registered ops, at most 20, and
  never touches a file or the network. A skill whose `approval` is `none` plans nothing.
* `edits` lists `(file, key path)` the plan can change. Files are `hass/content/<name>.json` for a collection the editor
  writes, or generated `storefront-mockup/...` files. A read-only skill declares none.
* `Slot.required` is `True`, `False`, or `"if:<slot>"` / `"unless:<slot>"`. A required slot has an `ask` of at most 14
  words; an optional slot never asks. `owner_words=True` marks a slot that can carry a claim.
* `Undo(mode, residue)`: `revert` drafts `history.revert`; `forget` drops a private row; `none` is read-only. The residue
  says what undo cannot remove ("none" when nothing stays).
* `cases` is `hass/tests/fixtures/skills/<group>/<name>.jsonl` (10 rows, 2 refusals, 1 undo). Fixture files belong to
  the group's card; the lint checks them only when it is given `repo_root`.

## Capability metadata (AVB-09)

[What Hass can do](CAPABILITIES.md) and `capabilities.json` are generated, never hand-maintained.
Run `python3 hass/capabilities.py` after changing a declaration; `--check` writes nothing and fails on drift.
`test_capabilities` runs this check in CI. `help` uses the same registry rows alongside the fixed command examples.
Neither view reads host settings or claims that this version is installed or enabled live.

Every declaration explicitly fills these fields (missing values fail the skill lint):

| Field | Values and rule |
|---|---|
| `pack` | `site`, `front`, `till`, `reports`, `core` (general help, no changing target). Each module's `SKILLS` export contains one pack only. Existing reply implementations may be shared. |
| `targets` | An ordered tuple: empty for read-only, `('site',)` for site/front writes, `('till',)` for till writes, or `('till', 'site')` for the sole allowed companion. This declares identity types, not sandbox/live selection. |
| `approval_class` | A0 for legacy `approval='none'`; A1 for `approval='owner-yes'`. A2/A3 are reserved and rejected until their executors and additional gates exist. The existing `approval` execution field is unchanged. |
| `sandbox` | `none-needed` for read-only, `preview` for private preview, `full` for the existing private writer. A writing `chat-live` skill and every till write must be `full`. This does not implement AVB-11's per-target switch. |
| `logs` | Explicit tuple (may be empty) of `subjects`, `fields`, `counts_ref`. Names only, never field values, text, prices or tokens. These declare future audit fields; AVB-10 owns the audit writer. |
| `who` | `owner` or `g-only`; all current registry skills are `owner`. Metadata is not a new permission grant. |
| `patterns` | Optional tuple of fixed code-parsed phrases; mandatory if a future slot carries a price/count. No parsing or Clover writes are added here. |
| `status` | Existing `active` or `retired`. Both remain in the manifest; retired entries are not returned by the registry's `get`. |

The front-end FAQ entry currently records a request, not a page change; the generated views say so. No till
skill is registered yet. Fixed commands and the separate till parser are not silently advertised as new skills.
AVB-11 owns per-target sandbox resolution; AVB-12/17 own the till parser's registry migration.

## The lint

`skill_lint(skills, ops_registry, repo_root=None, golden=None)` returns a list of problems (empty = clean). It checks
every mandatory field above, slot names and kinds, trigger duplicates across skills, edits files, the read-only /
approval pairing, and (with `golden={name: [slots, ...]}`) that each plan returns only registered ops, at most 20.
With `repo_root` it also checks the case files. The check against `live_policy.check` on the golden plans arrives with
the shared case runner (SKILLS-TK-1).

## Slot resolvers (`kinds.py`)

Each returns a `Resolved(status, value, candidates, ids, reply)`; `status` is `one`, `several`, `none`, `held`,
`hidden` or `invalid`.

* A held product or maker is never resolvable. A hidden one is named: "restore it first".
* `several` gives plain names (never ids) for one question; at most 10.
* Replies are in plain words with no ids or internal counts. Code keeps the ids in `ids`.

## The "I can't do that yet" backlog

`backlog.log` and `page.faq` are read-only. When nothing fits, a request is policy-blocked, a page is asked for, or a
request is stuck, the caller (a later card wires `conversation.py`) does two things: `Backlog.record(reason, summary,
text)` and sends `CANT_DO` (or `NO_FAQ` for a page). Nothing on the site changes and there is no approval.

* Rows live in the `backlog` table of the private `conversation.sqlite3`. The text is capped at 4000 characters
  (the owner-message cap), kept on the box only, and never goes to git, reports, logs or the interpreter.
* Reasons: `unknown-skill`, `policy`, `unsupported-page`, `stuck`, `price`, `other`.
* Retention (D7): 90 days. `Backlog.purge()` drops older rows; `forget` removes one row by its number.
* Owner view: `Backlog.owner_list()` lists the last ten (number, day, what was asked), with no stored text.
* Operator view: `python3 hass/skills/backlog.py list --state DIR` (summaries; `--text` prints the stored message,
  operator only) and `purge --state DIR`.

## Owner-facing words

Replies follow the plain-words rules: no ids, jargon or counts, "I don't know" and "I can't do that yet" said
honestly. The only number an owner sees is the position in the backlog list, which `forget backlog.<number>` needs.
If `docs/hass/VOICE.md` exists, it wins over anything on this page.
