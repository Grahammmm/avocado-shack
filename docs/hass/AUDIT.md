# The audit log (AVB-10)

One record of every action Hass takes, on the website and on the till. It answers: who asked, which skill planned it,
which draft code the owner saw, who said yes, what it changed (site or till, sandbox or live), how it ended, and what undid it.
It is the shape in HASS-ARCHITECTURE section 5 (AVB-02).

## Where it is and what it holds

- `<state>/audit/<UTC day>.jsonl`, folder 0700, files 0600. Append-only: a line is added under a lock, flushed to disk and
  never edited. It stays on the box and is part of the nightly state backup (`statebackup.py create`).
- One JSON line per step: `at`, `seq`, `action`, `step`, `who`, `msg`, `skill`, `pack`, `target`, `env`, `draft`,
  `approval`, `approved_by`, `result`, `subjects`, `fields`, `refs`, `undo_of`. The meaning of each key is in the header
  of `hass/audit.py`.
- Ids, codes and fixed words only. **Never** message text, owner words, prices, counts, phone numbers, addresses or tokens:
  every key is on a closed list, every value must match its pattern, and a run of five digits is refused outside the id keys.
  A line that breaks a rule is not written at all.
- The detailed records stay where they are, and the audit line points at them (`refs`): the change record and release
  journal by `change`, the writer commit by `commit`, the till journal (AVB-15) by `till`. The correspondence log, the stage
  times and the release journal are unchanged.

## Who writes it

- The chat (`hass/conversation.py`) writes `drafted`, `refused` (`said-no`, `expired`, `replaced`, `policy`), `approved`,
  `applied` (`undone` for an undo, with `undo_of`), `failed` (`stale`, `refused`, `busy`, `interrupted`, ...) and `verified`.
  The lines of one message are written only after its database transaction commits, so a rolled-back approval leaves none.
  A full disk never costs a reply: the chat keeps answering and the line is lost.
- The skills dispatcher (`hass/skills/dispatch.py`) writes the actions that make no draft, each its own action (one id per
  message and skill call), `target: local`: `answered` (result `ok`, approval `A0`) for a read-only skill such as
  `report.shelf` or `answer.site`, and `refused` before any draft: `refused` (the skill's own refusal, a held or hidden
  record, a mixed message), `policy` (an ask to post or send), `cap` (too many changes), `failed` (the plan failed),
  `backlog` (written down for Graham) and `said-no` (the owner dropped his open request). Never the request or the answer.
- The till engine (AVB-15) calls `AuditLog(state, clock).record(step, ..., pack="till", target="till", env="sandbox",
  strict=True)` before and after each till write. With `strict=True` a line that cannot be written raises `AuditError`, so
  the write does not happen without its record. `record` returns True only when every byte of the line is written and
  flushed: a short write goes on from where it stopped; a write that stops (no progress, an error, a full disk) raises.
  Earlier lines are never touched; a torn end has no newline, so the reader skips it, `check` counts it as bad, and the next
  line starts on a line of its own.

## Who reads it

- The owner's `history` command: the newest approved actions, site and till, newest yes first. A website change is told in
  its own words (from its draft); a till change says which till and where it stands, from its newest line and that line's
  result: "saved and checked" only when the check passed after the write went through; "saved, but I couldn't check it"
  when the check failed; "it didn't go through, so nothing changed" only for a stop before any write (`stale`, `cap`,
  `policy`, `refused`, `said-no`, `expired`, `replaced`); any other failure, or one after the write, says "I'm not sure
  where it stands, so please check it". Answers and refusals are not changes and are not listed. Changes approved before
  the audit log existed are still listed after them.
- On the box (prints ids and codes only):
  - `python3 hass/audit.py history --state DIR [--limit N]`: one line per approved action, newest first
  - `python3 hass/audit.py show --state DIR [--days N] [--action ID]`: the raw lines
  - `python3 hass/audit.py check --state DIR`: every line against the rules; exit 1 if any line breaks one

## Rollback

Revert the PR. The three older logs were never changed. The `audit/` folder then stays in the state folder; the older
`statebackup.py` refuses an unknown folder, so the operator moves it out of the state folder (for example to
`<state>.audit-kept/`) before the next 03:30 backup.

## Not done here (named follow-ups)

- Retention: the design keeps the log 2 years (OPERATIONS H21); nothing prunes it yet, and `retention.py` does not report it.
- `published` and `verified` steps from the live release engine (`publish_live.py`); today the release journal holds them and
  the `applied` line points at it by `change`.
- The skill contract fields (`pack`, `logs`) come with AVB-09; until then a draft line says `pack: site` and a draft-less
  line takes the pack of its skill group (`report`/`social`: reports, `answer`/`backlog`: core, `page.faq`: front, else site).
- Plain chat commands with no skill (`status`, `help`, `history` itself, memory) are reads and write no line.
