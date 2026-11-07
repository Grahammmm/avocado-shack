# HASS-LIVE-AUDIT-1: what works live, a self-test, and a ranked fix plan

Date: 2026-11-07, 14:35-14:50 PST, on AgentOrange. Author: opus-coder (card t_d5a579b9).
Live runtime: `~/.local/share/hass/runtime` at reviewed main `1d5f267` (clean); host mode `approvals: hold`,
`previewer: true`, `pictures: true`; owner = G's own phone (2 owner sender addresses configured); interpreter
`qwen3.6:35b-a3b-64k` on Ollama. Mac forwarder, receiver, worker, health timer and backup timer installed today.

How evidence was collected: only counts, check ids, unit states and key names. Nothing here read the envelope key, any
password, any host or state secret value, or any message text (sqlite read-only `COUNT(*)` queries, `inbox.py status`,
`health.py` without `--seen`/`--alert-log`, `systemctl --user`, `journalctl` of the hass units, whose lines carry
class names and counts only). No restart, no send, no model change, no live site. The live model was called only with
synthetic eval cases.

## Summary in plain words

Hass is connected for real: G's texts reach AgentOrange from the Mac, `status` gets exactly one answer, the answer
reaches the phone, and Hass correctly ignores its own reply when it comes back. The health check runs every 5 minutes.
**It cannot yet make a single change.** Every change request times out in the model, so no draft has ever been made
on the live system, and approval, preview, undo, photos, hikes and memory have never run live. All 22 testable feature
groups pass their unit tests; three (H07, H18, H25) need people and devices.

The 5 biggest gaps:

1. **The model is too slow, so nothing can be drafted.** The 35B model runs only on CPU (GPUs full; `size_vram: 0`)
   and the system prompt is about 11,000 tokens. Three synthetic requests: all three timed out at 30 s (90.1 s total).
   A longer timeout (t_3fc752e0) is needed but is not enough on its own: a minute or more per text is too slow for a
   phone conversation. A model that fits on a GPU, or a much shorter prompt, is the real fix.
2. **No backup exists yet**, and the restore drill has only ever run on fixtures. The first backup runs at 03:30.
3. **The worker crash loop went unnoticed by health.** At 14:10-14:12 the worker failed 26 times in a row (a
   `ConfigError`) and `health.py` has no check that the services are running; it would only notice after 15 minutes
   of a stuck inbox. The new self-test reports it.
4. **Approvals, undo and the safety controls have never run live.** Approvals are on hold (correct for now), so
   yes/no, undo, pause, expiry and the stranger guard are proved only by tests (and now by the synthetic self-test).
   The daily model cap is set to 1000, which is not a real limit.
5. **Michael's needs are mostly untested on real inputs.** Photos to product drafts (vision model never run on a real
   photo), voice notes (not transcribed), reminders and a daily summary to the phone (not built), and design
   changes (no path) are the gaps. Michael's own phone and the H07 Mac check have not happened.

## A. Requirement matrix

States: **WORKS-LIVE** (proved on the live system by the command shown), **TESTED-ONLY** (unit/acceptance tests
pass, never run live), **NOT-RUN** (neither), **BROKEN** (fails live).

Test evidence for every row: `python3 -B hass/acceptance.py` at `1d5f267`, 2026-11-07 14:36 PST:
`{"summary": {"ids": 25, "pass": 22, "fail": 0, "not covered": 3}}` (per-id test counts in the table).

Live evidence commands (outputs abbreviated, counts only):

- L1 `python3 -B hass/inbox.py status --state ~/.local/state/hass/state` (14:46):
  `{"dispositions": {"echo": 6, "reader-failed": 2, "status": 4}, "done": 12, "pending": 0, "nonces": 416,
  "start_at": "2026-11-07T21:58:49Z"}`
- L2 read-only counts of relay and conversation stores (14:46): `relay total 6, acked 6, handed_unacked 0,
  last_pull_age_s 5; outbox total 6, unsent 0; drafts_by_state {}` (no draft has ever been created).
- L3 `python3 -B hass/health.py --state .. --backups .. --writer --model http://127.0.0.1:11434 --host-dir ..
  --min-free-mb 1024` (14:36): `"ok": false, "problems": [{"check": "backup-age", "detail": "no complete backup"}]`
  (so db-integrity, writer, model reachable, relay, mac-silent, inbox-stuck, outbox-stuck, disk all pass).
- L4 `systemctl --user list-units 'hass*'`: receiver and worker `active running`; health and backup timers `active
  waiting`; `hass-backup.timer` LAST `-` (never ran). `journalctl --user -u hass-worker`: 26 crash restarts with
  `{"error": "ConfigError", "result": "error"}` 14:10:00-14:12:25, steady since 14:12:30.
- L5 `scripts/hass/live_selftest_model.py --url http://127.0.0.1:11434 --model qwen3.6:35b-a3b-64k` (synthetic
  cases e01, e03, e25): `{"cases": 3, "failedCalls": 3, "passed": 0, "seconds": 90.1}`; `/api/ps`: `size_vram: 0`;
  real prompt size from `interpreter_prompt.build`: `44036 chars, ~11009 tokens`.
- L6 `grep HASS-HEALTH ~/agent-work/modes/ALERTS.log`: `2026-11-07T22:00:00Z HASS-HEALTH 8ab50b0e6e19 backup-age`
  (one line, then quiet: alert-once works).
- L7 `scripts/hass/live_selftest.sh --model qwen3.6:35b-a3b-64k` (14:45): `pass=7 warn=4 fail=1 failed:model`
  (full output in section B).

Reading L1+L2: 6 owner messages (4 `status`, 2 change requests that failed in the model) produced exactly 6 replies,
all pulled and acknowledged by the Mac, and 6 echoes (Hass's own replies arriving back in Messages) were ignored.
So one reply per message reached the phone and the echo guard works.

| ID | Feature | Tests (acceptance) | Live state | Evidence / why |
| --- | --- | --- | --- | --- |
| H01 | One product/maker/event data source | pass (32) | WORKS-LIVE (read) | L3 `writer` check passes; L1 `status` replies read content. No live write yet. |
| H02 | Private editing service | pass (12) | TESTED-ONLY | No apply has run live (L2: 0 drafts; approvals hold). |
| H03 | Add/edit/hide/restore product or maker | pass (9) | BROKEN | The 2 live change requests failed in the model (`reader-failed`, L1); L5. |
| H04 | Draft and update real hikes | pass (8) | BROKEN | Same interpreter path as H03 (L5). |
| H05 | Approve, revise, cancel in the same chat | pass (23) | NOT-RUN | No draft exists to approve (L2); approvals on hold by design. Synthetic: PASS (cancelled/expired codes, section B). |
| H06 | Preview, result, undo | pass (9) | NOT-RUN | Needs an applied draft. |
| H07 | Mac bridge compatibility check | not covered | WORKS-LIVE (partly) | Text in and out works: L1 (12 handled, 416 nonces), L2 (6 replies acked, last Mac pull 5 s ago), 6 echoes. Not done: attachment in/out, versions, permissions, SIP and restart/sleep behaviour recorded; on G's phone, not Michael's. |
| H08 | Owner-only text channel | pass (43) | WORKS-LIVE (partly) | Owner chat and echo guard live (L1 `echo: 6`). Stranger, group and duplicate delivery never exercised live (no `ignored` disposition); synthetic PASS. |
| H09 | Demo: text, draft, approve, update, screenshot, undo | pass (14) | BROKEN | Chain stops at the draft step (L5). |
| H10 | Photos to product drafts | pass (30) | NOT-RUN | No photo sent live; label/vision model never run on a real photo. |
| H11 | Voice notes | pass (7) | NOT-RUN | Recognised but not transcribed (by design today). |
| H12 | Text plus attachments in one conversation | pass (32) | NOT-RUN | No attachment sent live. |
| H13 | Hours, home copy, image slots | pass (41) | BROKEN | Needs the interpreter (L5). |
| H14 | Hike management, guest totals | pass (16) | NOT-RUN | Reads work in tests; no live hike asked. Changes need the interpreter. |
| H15 | Owner memory | pass (18) | NOT-RUN | `remember`/`forget` need no model but were not tried live. |
| H16 | Durable queue, restart recovery | pass (26) | WORKS-LIVE (partly) | Worker crash-looped 2 min (L4); afterwards pending 0 (L1), nothing lost or doubled. Mac outage/offline and reply-failure reconciliation not seen live; synthetic PASS (retry, no duplicate). |
| H17 | Status, cancel, undo, pause | pass (26) | WORKS-LIVE (status) | `status: 4` handled and answered (L1, L2). Cancel/undo/pause not tried live. |
| H18 | Owner trial on Michael's devices | not covered | NOT-RUN | Needs Michael's phone and an agreed task list (G). |
| H19 | Managed operation, health checks | pass (25) | WORKS-LIVE (partly) | Health timer every 5 min, one alert line, then quiet (L3, L6). Gaps: no service-down check (L4 crash loop unseen); Mac sleep/reboot unmeasured. |
| H20 | Backups and recovery | pass (25) | NOT-RUN | Backup timer never ran; `backups/` empty (L3 `backup-age`, L4). Restore drill fixtures only. |
| H21 | Privacy, retention, access | pass (9) | TESTED-ONLY | Logs carry counts and class names only (checked in L4 journal). Retention periods not decided; nothing deletes. |
| H22 | Usage limits | pass (7) | WORKS-LIVE (weak) | `interpreterDailyCap` is set (1000/day) and shown in `status`; 1000 is not an agreed limit (G). Model failures stop safely: the reply says nothing was drafted. |
| H23 | Opt-in automatic changes | pass (10) | NOT-RUN | Policy module not wired; needs owner opt-in. |
| H24 | Design changes through Hass | pass (35) | NOT-RUN | No path from a request to a checked code change. |
| H25 | Release and handover | not covered | NOT-RUN | Release step; needs the above. |

CONNECT.md section 2 smoke checks (step 8, in its order):

| Smoke check | Live state | Evidence |
| --- | --- | --- |
| `host.py check` and `start-point` before services | WORKS-LIVE | Start point recorded `2026-11-07T21:58:49Z` (L1); services run (L4). |
| Owner texts `status`, gets one reply | WORKS-LIVE | L1 `status: 4`; L2 6 replies for 6 messages, all acked; 6 echoes ignored. |
| A stranger's text gets no reply and no draft | NOT-RUN live | No stranger message yet. Synthetic PASS: `test_4_stranger_is_ignored` (owner chat: ignored by host; other chat: dropped on the Mac). |
| Owner texts a small change, a draft arrives, owner replies `no`, nothing changes | BROKEN | No draft arrives: the model times out (L1 `reader-failed: 2`, L2 0 drafts, L5). |
| `inbox.py status` shows messages done, no backlog | WORKS-LIVE | L1 `pending: 0`, `oldest_pending_minutes: null`. |

## B. The self-test (scripts/hass/live_selftest.sh)

In the docs PR on branch `rb/hass-live-audit-1`: `scripts/hass/live_selftest.sh`, its helpers
`live_selftest_synth.py` and `live_selftest_model.py`, `hass/tests/test_live_selftest.py` (CI runs
`--synthetic-only`), a paragraph in `docs/hass/OPERATIONS.md`, and the candidate timer files.

Read-only on the live system: it restarts nothing, sends nothing, writes nothing in the Hass state or host dirs, opens
no key or password and reads no message text. All inputs are synthetic.

| Check | What it proves | Requirement covered |
| --- | --- | --- |
| synthetic `test_1` | real Mac `Spool`+`Forwarder` -> HTTP -> real `host.Server` -> `Worker` -> draft -> relay -> forwarder pull and ack | forwarder to receiver path, draft |
| synthetic `test_2` | `status` gets one reply and no draft | status |
| synthetic `test_3` | a failed BlueBubbles send is not acked, is re-handed after 60 s and sent once; a lost ack does not send twice | reply-delivery recovery, duplicate replies |
| synthetic `test_4` | stranger in the owner chat ignored by the host; stranger chat dropped on the Mac; no draft, reply or write | stranger ignored |
| synthetic `test_5`/`test_6` | in private mode (where a valid yes would apply), `yes CODE` after `no CODE`, or after expiry, applies nothing | cancelled or expired code does nothing |
| runtime, runtime-after | runtime checkout clean before and after the synthetic run (the worker refuses a dirty runtime) | |
| services | receiver and worker active; systemd crash-restart counter | restart behaviour |
| timers, backup | health and backup timers active, last run and exit; a backup under 26 h old | health and backup timers |
| health | `health.py` read-only: db integrity, stuck inbox/outbox/relay, mac-silent, writer, model reachable, disk | |
| inbox | pending backlog and age | |
| model (`--model`) | 3 synthetic eval cases through the local model with the production timeout, scored | draft round trip with `interpreter_eval` live cases |
| growth | state size, free disk, hass journal lines per 24 h, compared with the last run | disk/log growth |

Run on the live box, 2026-11-07 14:45 PST (`--model qwen3.6:35b-a3b-64k`):

```
PASS runtime checkout 0edf4fd31595 clean
PASS synthetic {"failed": 0, "ran": 6, "synthetic": "pass"}
PASS runtime-after still clean
PASS service:hass-receiver active, 0 restarts
WARN service:hass-worker active, systemd restart counter 26 (crash restarts since the unit was loaded)
PASS timer:hass-health active, last run Sat 2026-11-07 14:40:03 PST
WARN timer:hass-backup active, has not run yet
WARN backup no backup under 26 h old
WARN health problems: backup-age
PASS inbox pending 0, done 12
FAIL model {"cases": 3, "failed": ["e01", "e03", "e25"], "failedCalls": 3, "passed": 0, "seconds": 90.1}
PASS growth state 176 KB, free 259805 MB, hass journal 185 lines/24h; since last run 0 h ago: state 4 KB, journal was 182 lines/24h
HASS-SELFTEST 2026-11-07T22:45:19Z pass=7 warn=4 fail=1 skip=0 failed:model
```

(That run was from the PR worktree; after merge the operator runs it from the runtime checkout.)

Nightly candidate (not installed): `reports/hass/hass-selftest.service.candidate` and
`reports/hass/hass-selftest.timer.candidate`, also copied to `~/agent-work/reports/hass/`. Systemd user oneshot,
02:50 Pacific (after nightly CI at 02:23, before the 03:30 backup), `Nice=10`, `TimeoutStartSec=15min`, same
hardening as `hass-health.service`, `SuccessExitStatus=1`. It appends the summary to
`~/.local/state/hass-selftest/selftest.log` and replaces `~/agent-work/modes/HASS-SELFTEST.line` with the one summary
line for the ops brief. `systemd-analyze --user verify` passes on both. Picking that line up in the ops brief is a
small follow-up in the brief generator; adopting the timer is an operator step.

## C. Ranked fix-and-improve plan

Effort: S (under a day), M (1-3 days), L (more). Risk: risk of the change itself. "Needs" names who must decide or
act; "operator" means an internal operator or agent step with no G decision.

| Rank | Item | Area | Effort | Risk | Needs |
| --- | --- | --- | --- | --- | --- |
| 1 | **Make drafting work: a model that answers in under ~20 s.** Measure (t_3fc752e0 table, add `prompt_eval_count`/`duration`), then choose: (a) a small model that fits the free GPU memory (GPU0 had ~6.6 GB free) only for Hass; (b) give Hass a GPU slot; (c) stay on CPU with timeout 120 and `think: false`. CPU with an 11k-token prompt will stay at a minute or more per text. | speed | S (measure) + S (switch) | low; reversible via host.json | G (model and GPU choice; model changes are G's), operator after |
| 2 | Configurable timeout and `think: false` (t_3fc752e0, in progress; do not duplicate) | speed | S | low | operator (merge, update runtime commit, restart worker) |
| 3 | Shorter prompt: send only the ops and records the request can touch (two-step: classify, then a small per-op prompt), or cap catalog lines; keep the model warm (`keep_alive` long, a warm-up call after worker start) so the cached system prompt is reused | speed | M | medium (interpreter quality; rerun the 69-case eval before and after with `compare`) | operator |
| 4 | Health: add a service-down check (`systemctl --user is-active` receiver and worker, crash-restart counter) or adopt the nightly self-test; also `StartLimitBurst`/`StartLimitIntervalSec` on the worker so a config error stops restarting and alerts instead of looping every 5 s | reliability | S | low | operator |
| 5 | First backup and a restore drill on the real state (the timer runs 03:30; then `statebackup.py drill` into a new dir) | reliability | S | low (restores into a new dir) | operator |
| 6 | Canned and model-free replies for common asks: status, help, find, show, history, report and remember/forget already skip the model; add the next most common asks Michael uses, and keep reads answered while a change waits on the model (today the worker drains one message at a time, so a `status` waits behind a slow change) | speed | M | low | operator; Michael's list of common asks |
| 7 | "Working on it" reply when a request will take longer than ~10 s, so the owner is not left guessing | speed/safety | S | low | operator |
| 8 | Real usage limit: set `interpreterDailyCap` to an agreed number (today 1000) | safety | S | low | G (H22 limit) |
| 9 | Kill switch and pause runbook: `pause changes` by text works in tests; document one stop command for G (stop worker and forwarder) and test it in the self-test by reading the paused flag | safety | S | low | operator; G confirms the procedure |
| 10 | Live smoke of the safety guards with synthetic text from a second phone: stranger, group chat, duplicate delivery, `no`, expired code, `pause`/`resume` | safety | S | low | G (second phone or contact; G sends the texts) |
| 11 | Turn approvals from `hold` to `private` after 1-3 pass, then exercise approve, preview, undo on private content only | safety | S | medium | G (approval mode change) |
| 12 | Clock: both hosts must stay within 5 minutes (the envelope window); AgentOrange is NTP-synced; add a Mac clock check to the Mac setup check, and have the forwarder report repeated `rejected` (it retries every 60 s forever today) | reliability | S | low | operator; G on the Mac |
| 13 | Mac sleep, logout, reboot and macOS/BlueBubbles updates: run the H07 compatibility check and record versions; disable sleep; pin BlueBubbles (no auto-update), re-run the self-test after any update; `mac-silent` alerts when the Mac stops pulling | reliability | M | medium (BlueBubbles REST shapes are UNVERIFIED in code) | G (Mac access) |
| 14 | Duplicate replies: the Mac records `sent` after the send, so a crash between the two can send one reply twice (small window; the synthetic test shows a lost ack does not). Record intent before sending and reconcile with BlueBubbles' sent messages on restart | reliability | M | medium | operator |
| 15 | Spool and retries: the Mac spool keeps payloads until delivered; delivery backoff caps at 300 s; outage notice after 10 min. Add spool size and oldest-pending to the forwarder `status` read by the self-test through the relay | reliability | M | low | operator |
| 16 | What happens when the model is wrong: every change is a draft with a code, approval names one version, undo reverses only that change (all tested). Add a weekly eval run (69 cases) and track the pass rate; refuse ops with low confidence as a question | safety | M | low | operator |
| 17 | Retention: decide periods (OPERATIONS.md proposal) and build HASS-RETAIN-1 | safety | M | medium (deletion) | G (periods), then operator |
| 18 | Photos to product drafts: run the label reader on a real vision model with real (non-private) product photos, then one live photo from the owner phone; check alt text and stripped location | capability | M | low | G (vision model choice), Michael (photos) |
| 19 | Website edits: hours, headline, story, home image and product edits are built; prove each live once in private mode with preview screenshots to the phone (`pictures: true` is on) | capability | S once 1 and 11 are done | low | G (approval mode) |
| 20 | Status and undo on the phone: status works live; try `undo` live after the first private apply | capability | S | low | — |
| 21 | Reminders (e.g. "remind me Friday to order eggs"): not built; needs a scheduled outbound message, which is an outbound-send policy question | capability | M | medium | G (outbound messages), Michael (wants it?) |
| 22 | Daily summary to the phone: `morning_report.py` exists (F04 is later work); a once-a-day text needs a timer and an outbound message | capability | M | medium | G (outbound), Michael (content and time) |
| 23 | Voice notes: transcription with a local speech model, read back before acting (H11) | capability | M | medium | G (model), Michael |
| 24 | Design changes through Hass (H24): request to an isolated code change with visual checks | capability | L | high | G (scope) |
| 25 | Michael's trial (H18) on his own phone with an agreed task list, after 1-19 | capability | M | medium | G and Michael |

Notes behind the ranking:

- Restart behaviour: units restart on failure every 5 s; at that pace systemd's default start limit (5 starts in
  10 s) never trips, so a bad config loops forever (L4 shows 26 loops in 2 minutes). Messages are safe meanwhile
  (durable inbox; pending 0 afterwards).
- What happens when the model is slow today: the owner gets "I could not work that out right now, so nothing was
  drafted" after 30 s, nothing changes, and the message is marked `reader-failed`. That is safe but useless.
- Hold mode is the right setting until rank 1 is fixed; a draft must exist before any approval matters.

## Not done here, on purpose

No service was restarted, no model or timeout changed, no message sent, no live site touched, and no key, password or
message text read. t_3fc752e0 owns the timeout/think change and its timing table.
