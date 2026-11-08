# HASS-TASKMAP-1 report

Card t_b5c979c0 · author sonnet-coder · 2026-11-08 · against `origin/main` 56c9070. Design only. The deliverable is
[`docs/hass/TASKMAP.md`](../../docs/hass/TASKMAP.md).

## What was done

Wrote the task map in seven parts (decisions first): 39 everyday tasks with ESTIMATED frequency, input, effect and today's
status; the tier for each and the manual-first path; the cloud dispatch (spool files, operator-owned bridge, proposal contract,
failure wording, dollar cap, lane, audit, why code writes the change, comparison with "local model dispatches straight to Opus"); the
weekly skill factory with its export contract and rule learning; the new skills (receipts and expenses with a private-action
contract, supplier order drafts, social drafts, holiday closures, prices gate, Hass-started prompts); an 18-row build order (17
scheduled cards) with owned files and builder tiers; nine decisions for G.

## Round 2 (after review RETURN at 362120d, docs only, same two files)

1. **Factory export (4.4, card 2).** Free summaries and the first-160-characters fallback are no longer exportable. Output is closed
   codes, integers and fixed sentences only, through a classifier that fails closed (`finance`, `sensitive`, `unclassified`) and an
   independent export guard; traces carry closed fields; a canary test plan covers summary, fallback and trace paths. Card 2 is now
   tier S.
2. **Dollar cap (3.5, G9, cards 15-16).** A per-Pacific-day currency cap, default `$0` (nothing queued), per-attempt reservations
   (retries and the strong lane each reserve), atomic check-and-append under a lock, settle on return, full reservation when cost or
   usage is unknown, overrun closes the day, every unknown fails closed. The amount is G's (G9); nothing invents it. Job counts remain a
   second fence.
3. **Private-action contract (5.1a, new card 4, HASS-PRIVACT-1).** How a hash-bound owner approval saves a ledger row: `drafts.kind`,
   neutral summaries, `private_pending`, one atomic idempotent transaction, recovery, pause, void and undo, outbox redaction, test
   kit ownership. Card 1 gains the `private_action` field and lint; `conversation.py` gets exactly two serial editors (cards 3, 4).
4. **Proposal contract (3.3).** Layer 0 (object), layer A (structural fields: schema and range only) and layer B (generated text
   fields: the prose prohibitions), with a valid description envelope, a valid photo plan, and 13 invalid controls. The example
   lengths and hashes were computed for this page.
5. **Opening statement.** Building is separated from enabling: every card builds on fixtures; each enablement (G1 plus G9, G2, G3, G4,
   G7) is off until its named answer.

Cards after the renumber: 1 MODEL-2, 2 FACTORY-1, 3 CMD-1, 4 PRIVACT-1, 5 MANUAL-1, 6 SOCIAL-2, 7 SAY-1, 8 LEDGER-1, 9 ORDERS-1,
10 LEDGER-2, 11 AVO-CLOSURE-1, 12 CLOSURE-1, 13 SAY-2, 14 PATTERN-1, 15 CLOUD-1, 16 CLOUD-2, 17 CLOUD-3, 18 PRICE-1 (unscheduled).

## What was read

`reports/hass/SKILLS-SPEC.md` (whole), the approval, undo and recover paths of `hass/conversation.py` (round 2), `docs/hass/COMMANDS.md`, `LIMITS.md`, `VOICE.md`, `IMPLEMENTATION.md`, `BRIDGE_WIRING.md`,
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
