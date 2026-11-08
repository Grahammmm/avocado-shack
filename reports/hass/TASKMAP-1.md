# HASS-TASKMAP-1 report

Card t_b5c979c0 · author sonnet-coder · 2026-11-08 · against `origin/main` 56c9070. Design only. The deliverable is
[`docs/hass/TASKMAP.md`](../../docs/hass/TASKMAP.md).

## What was done

Wrote the task map in seven parts (decisions first): 39 everyday tasks with ESTIMATED frequency, input, effect and today's
status; the tier for each and the manual-first path; the cloud dispatch (spool files, operator-owned bridge, proposal contract,
failure wording, cap, lane, audit, why code writes the change, comparison with "local model dispatches straight to Opus"); the
weekly skill factory and rule learning; the new skills (receipts and expenses, supplier order drafts, social drafts, holiday
closures, prices gate, Hass-started prompts); a 17-card build order with owned files and builder tiers; eight decisions for G.

## What was read

`reports/hass/SKILLS-SPEC.md` (whole), `docs/hass/COMMANDS.md`, `LIMITS.md`, `VOICE.md`, `IMPLEMENTATION.md`, `BRIDGE_WIRING.md`,
`SKILLS.md`, `HERMES_START.md`, `FEATURES.md` (F03, F05, F07, F09), `hass/skills/backlog.py`, `corrlog.py`, `social_draft.py`,
`specials.py`, `statebackup.py` (layout list), `content_model.py` (store keys), the op lists of `ops/store.py`, `home.py`,
`specials.py`, `morning_report.py` (the `--for-g` line), and the file lists of PRs #529, #530, #531. `reports/hass/LIVE-PLAN-1.md`
does not exist yet (HASS-LIVE-PLAN-1 in progress), so nothing from it is used. The PR list and states were read with `gh pr
list` on 2026-11-08.

## Findings worth the reader's time

1. Merged skills are **not reachable from chat**: `conversation.py` on main has no skill dispatch. FW-2 (#525) and FW-3 (#526) are
   the critical path. Read 2026-11-08: #525 and #504 each had one failing check beside passing ones; #526 and #531 were green.
2. "Do a lot manually at first" has one limit for site changes: the only approved writer is a draft Mike approves in his chat, so
   the manual lane needs an ingest (card 4, HASS-MANUAL-1) before the operator can do a site change for him.
3. The `stop` word already means "stop changes", so the reminder stop word is `reminders off`.
4. A ledger file beside the database would be refused by `statebackup._scan` (closed layout list); the ledger goes in
   `conversation.sqlite3`, like the backlog and notes.
5. The cloud lane cannot restyle a photo: a reading model returns only numbers (subject box, rotation), and the Pillow renderer
   from #504 makes the picture. Image generation stays unapproved (SKILLS-SPEC D6).
6. Tier 3 is only needed for the "nicer" description and the photo plan; every task in G's list reaches "no model needed once a
   phrasing is learned", except understanding a new phrasing and reading a receipt photo, which stay local-model jobs.

## Limits

* No frequency is measured (nothing is live). Cap, timeout, quiet-hour and promotion numbers are **proposals**.
* Not verified: the router at `127.0.0.1:8010` serves only local models for Hass's model name; the backup folder stays on the box;
  the real latency of a cloud card through the dispatcher.
* No code, service, host.json, Mac, live state, real owner message or finance record was touched or read. Nothing was sent.
* Model-written parts: none; all text above is a design, not an accepted outcome.
