# HASS-FAST-1: the 👀 on receipt, per-stage timing, faster replies

Card t_09e48987, 2026-11-07, author sonnet-coder. Synthetic messages only. Nothing was restarted, no Mac, key, `~/.config/hass`, fleet model or real owner message was touched. Files: `reports/hass/fast-1/` (bench, raw results, prompt sizes).

## 1. Answers

1. **Ack method chosen: a text `👀`, not a tapback.** The tapback needs BlueBubbles' Private API (`/api/v1/message/react`; BlueBubbles docs: "requires the Private API"), which the runbook keeps off, and even with it on, BlueBubbles can only send the six classic tapbacks (love, like, dislike, laugh, emphasize, question): there is no 👀 tapback. I could not test the live server (it runs on the Mac, off limits); the new read-only `hass_forwarder.py ackcheck --config FILE` (one GET of `/api/v1/server/info`, sends nothing) lets the operator confirm `privateApi: false` on the real server.
2. **Three biggest speed wins (plain words):**
   - **Stop the model running on the slow CPU**: use the model the fleet already keeps on the GPUs. MEASURED by HASS-MODEL-1: 2-6 s per free-text request instead of 60-90 s. Needs card HASS-INTERP-OPENAI-1 plus the fleet operator's OK.
   - **Stop waiting for the one-minute catch-up**: "model-free commands answer in about a minute" matches the old 60 s catch-up poll exactly, which means the BlueBubbles webhook is probably not waking the forwarder (verify with the new stage log: `accepted via=poll`). This PR makes the poll 15 s and pulls replies every second for 3 minutes after an owner message. MEASURED: reply 2.4-3.5 s -> 1.4-1.5 s with a working webhook; 22-47 s -> 5-11 s without one. Fixing the webhook itself is worth the rest (operator card below).
   - **Keep the CPU model loaded and trim its prompt** (only until the GPU route is live): MEASURED 23-28 s per request kept loaded vs 60-90 s now; the prompt is 44,036 characters (about 12.6k tokens), 81% of it product descriptions; trimming is ESTIMATED to cut CPU prefill (34 s of 39 s compute) by about 3-4x.
3. The 👀 goes out within **0.05-0.11 s** of the forwarder storing the message in the bench (BlueBubbles stand-in with a 0 s send). The real AppleScript send adds an unmeasured 1-3 s (ESTIMATE), so "within 2 s" is likely but must be confirmed on the live stage log (`ack-start` -> `ack-end`); an ack send is capped at 4 s and can never hold the loop longer.

## 2. Part A: what was built (Mac forwarder + host)

- **When**: the forwarder stores a NEW message from the owner's own address in the owner's one-to-one chat (`msg.kind == new`, not `from_me`, `sender_key(sender) == sender_key(address in ownerChat)`, sent less than 120 s ago). The ack runs in `Forwarder.cycle` after `fetch` and before `deliver`: before the receiver or any model.
- **Never**: a stranger in the owner chat, another chat or a group, Hass's own messages (including its own 👀), edits, reactions, a message found late by the catch-up poll (>120 s old), an ack that waited >30 s, while changes are paused, or when the host has not answered. The stranger is still forwarded exactly as before (the host decides; it records `ignored` and replies nothing).
- **Paused**: a new sealed read-only relay op `state` (host answers `paused: true/false`, true also when the store cannot be read: `host.paused_flag` reads `conversation.sqlite3` with `mode=ro`). The Mac asks every 5 s and trusts the answer 30 s. The owner's own pause command (`stop changes`, `pause`, ...) also holds the 👀 for 60 s because the host has not read it yet. A pause command queued >60 s behind a slow request can still be acked once; the 👀 never applies anything and approvals stay gated by the host.
- **Exactly once**: spool table `ack(provider_id PRIMARY KEY, state, ...)`; the row is created only when the inbound row is newly inserted (webhook, catch-up, replay and restart find it present), moves `pending -> sending` (committed) `-> sent | failed`, and a `sending` row after a crash is never sent again (at-most-once beats a double 👀). No retry on failure.
- **Never blocks**: every ack error is recorded and ignored; `ack()` itself is wrapped so even a broken table cannot stop the loop; the default ack sender clamps its HTTP timeout to 4 s.
- **Switch**: optional config key `"ack": false`. Deploy order: **host first, then Mac** (a new Mac against an old host sends no 👀 and breaks nothing; an old Mac against a new host is unaffected).
- **Commands that reply fast**: decision: **ack them too**. Measured command replies are 1.4-1.5 s at best (bench, 0 s BlueBubbles send) and 5-47 s when the webhook is silent; with the AppleScript send they are not reliably under 3 s, so the 👀 is not a double message in practice, and having the Mac guess which texts are commands would duplicate the host's parser and make the 👀 inconsistent. Revisit once the live stage log shows command replies under 3 s (one-line skip in `Spool.owner_arrived`).
- Tests (`hass/tests/test_fast_ack.py`, 45 tests, plus the unchanged forwarder/host/relay/receiver suites): owner acked once before delivery; stranger sender (no 👀, no reply, still recorded `ignored` by the real host); other chat, group, echo, no handle, reaction, edit, look-alike address, late message, stale ack; replay via webhook + catch-up + direct accept + restart = one 👀; crash mid-send never resends; paused/unknown/TTL/hold; send failure and any exception swallowed; cycle order fetch -> ack -> post; end-to-end with the real forwarder, host Server, Receiver, Worker, Conversation (pause stops the 👀, resume restores it, replay adds none, the host's own echo never causes one).

## 3. Part B: measured stage table

Method: `reports/hass/fast-1/stage_bench.py` runs the real forwarder, real host Server/Receiver/Worker/Conversation (temp state, throwaway key) in real time with the real intervals; BlueBubbles is a Python function (0 s send) and the model is a 0 s fixture. Each stage writes a line to a read-only log (`hass/stagelog.py`: time, stage, SHA-256 of the id cut to 12 hex; no text, sender, chat or path). Seconds after the owner pressed send; "before" = pre-FAST-1 intervals (pull 5 s, catch-up 60 s, no 👀); raw lines in `stage-bench-results.json`.

| run | webhook | found by | accepted | 👀 sent | receiver stored | worker picks up | interpreter (stub) | reply queued | reply pulled = BB send |
|---|---|---|---|---|---|---|---|---|---|
| before, `status` (3 phases) | on | webhook | 0.03-0.06 | - | 0.12-0.21 | 0.29-0.76 | - | 0.34-0.79 | 2.54-3.41 |
| before, `hours` (3 phases) | on | webhook | 0.03-0.04 | - | 0.15-0.17 | 0.22-0.82 | 0 | 0.28-0.86 | 2.43-3.46 |
| before, `status` | off | poll | 46.0 / 16.0 | - | 46.1 / 16.0 | 46.1 / 16.9 | - | 46.2 / 17.0 | 47.1 / 22.0 |
| after, `status` (3 phases) | on | webhook | 0.01-0.03 | 0.05-0.08 | 0.07-0.11 | 0.09-0.69 | - | 0.11-0.72 | 1.36-1.43 |
| after, `hours` (3 phases) | on | webhook | 0.03 | 0.08-0.09 | 0.11 | 0.34-0.75 | 0 | 0.38-0.79 | 1.44-1.48 |
| after, `status` | off | poll | 10.0 / 4.0 | 10.0 / 4.1 | 10.0 / 4.1 | 10.3 / 4.1 | - | 10.3 / 4.2 | 11.4 / 5.4 |

End to end (min / median / max, s): before webhook-on 2.43 / 2.90 / 3.46; before webhook-off 22.0 / 47.1 / 47.1 (2 phases); **after webhook-on 1.36 / 1.44 / 1.48; after webhook-off 5.4 / 11.4 / 11.4**. The 1.4 s floor is the worker's 1 s tick plus the 1 s reply pull; not lowered here (the worker tick is pinned by `test_host`).

Stages not simulated, from earlier MEASURED numbers (HASS-MODEL-1, same box): interpreter on CPU qwen3.6 thinking on/unloaded: 60-90 s (G's observation; 223 s for a cold load); CPU kept loaded, thinking off: 25.8 s quiet, 82.8 s shared (prefill 34 s of 39 s compute); fleet GPU Qwen3.8 27B: 2.3 s p50 / 5.4 s p95 (10.8 s right after a catalog change). BlueBubbles' real send: not measured (ESTIMATE 1-3 s). Livelog check: after the operator deploys, `python3 hass/stagelog.py <spool>/stages.jsonl <hostdir>/stages.jsonl` prints the same table from real traffic (ids are hashed). The same live log answers the one open question: whether `accepted` says `via=webhook` or `via=poll`.

Where the old ~3 minutes for free text goes (MEASURED + one inference): model 60-90 s; a single-threaded worker means a command sent behind a slow request waits for it (not changed: needs ordering design, card 6); webhook silent -> up to 60 s catch-up wait (inference from the "about a minute" for model-free commands, confirmable with the stage log); reply pull up to 5 s; the rest is BlueBubbles send and queueing behind other cards' use of the same Ollama.

## 4. Levers, ranked by gain (M = measured, E = estimated)

| # | Lever | Gain per request | Status |
|---|---|---|---|
| 1 | **Route free text to the fleet's resident GPU Qwen3.8** (HASS-MODEL-1 route G) | 60-90 s -> 2-6 s (M, HASS-MODEL-1) | Card to write: HASS-INTERP-OPENAI-1 (adapter, `api` key) + operator OK for the fleet's single slot (each Hass call holds it 1-11 s). Not built: needs a model change. |
| 2 | **Make the BlueBubbles webhook wake the forwarder** (if it is not) + shorter catch-up | commands: ~60 s -> 1.4-1.5 s (webhook) or 5-11 s (poll only) (M in bench; whether the live webhook works is the inference above) | Poll 15 s + 1 s reply pull for 3 min: **built here**. Operator card: HASS-WEBHOOK-CHECK-1 (read the new log for `via=poll`; check the BlueBubbles webhook URL/token on the Mac). |
| 3 | **CPU fallback done properly**: model kept loaded (`keep_alive`), thinking off, 120 s timeout | 60-90 s -> 23-28 s quiet (M, MODEL-1) | Existing card t_aefc2c07 owns the keys; not duplicated. |
| 4 | **Static system-prompt prefix + shorter prompt** (1: caching, shorter) | CPU prefill 34 s -> about 8 s if product descriptions are only sent for products the message names (E); ~1-2 s with a loaded model that reuses the prefix (E: MODEL-1 saw no reuse on Ollama, unexplained). The prompt is already static-first (role, rules, ops = 6,953 chars, 16%); the catalog is 36.5k chars, 35.5k of it product rows (`prompt-sizes.json`). On the GPU route the llama-server reuses the prefix already (0.8-2 s). | Card: HASS-PROMPT-SLIM-1 (changes what the model sees: needs the interpreter eval). Not built. |
| 5 | **Rules and canned replies for common asks** (hours, availability by shelf, "did it work", yes/no) | 25-180 s -> 1.4-3 s for those asks (E). "did it work", yes/no, status, help, memory, thanks already skip the model; hours/availability do not. Only 1 of 69 eval messages hit the rules path, but the eval set holds change requests, so the real share of questions is unknown. | Card: HASS-ANSWERS-1 (read-only `hours`/`what is out of stock` answers; must not intercept edits like "change hours to ..."). Not built: new owner-facing replies. |
| 6 | **Separate lane for model-free commands** so they do not wait behind a 90 s request | command behind a slow request: up to 90 s -> about 1.5 s (E) | Card: HASS-LANES-1 (needs an ordering design so a `yes` never overtakes its draft). Partly built: each message's replies are now flushed right after that message, not after the whole drain. |
| 7 | **"Working on it, about a minute" at 5 s** (behind the 👀) | no speed gain; removes the silence (perceived) | Card: HASS-WORKING-NOTE-1. Not built: new wording is G's product choice, and on the GPU route (2-6 s) it would almost never fire. |
| 8 | **A GPU window for Hass** | 60-90 s -> about 3-6 s | **Not done, and not recommended.** Ollama is CPU-only by configuration (`CUDA_VISIBLE_DEVICES=-1`); using a GPU needs an Ollama restart (not allowed) and the free VRAM (6.6 GB + 2.9 GB) cannot hold a useful model (gemma4:12b needs 7.6 GB + context). Room means stopping the fleet's Qwen3.8 27B (about 33 GB; 1-2 min reload) and pausing the local-worker lane for the window. Lever 1 gives the same speed with no disruption. |

Built in this PR (no model change): the 👀 ack, `state` op, stage log + `hass/stagelog.py`, `ackcheck`, fast reply pull, 15 s catch-up, per-message reply flush, `via=` on `accepted`. Left, with a named card each: levers 1, 2 (operator part), 4, 5, 6, 7.

## 5. Needs G / operator

Nothing needs G. Operator steps (internal): deploy host then Mac by the usual script; restart of `hass-receiver` and `hass-worker` to pick up `state` and the stage log (not done by me); optional `"ack": false` in the Mac config to switch the 👀 off.

## 6. Limits

BlueBubbles shapes remain UNVERIFIED on a real Mac; the bench uses a 0 s stand-in; the single-threaded bench shares one clock for both machines (the live join of Mac and host logs depends on their clocks being in step); the stage log's `reply-queued` joins a reply to the message being handled, exact because replies are now flushed per message.
